import logging
from typing import Optional, Dict, List, Tuple
import numpy as np
import pandas as pd
from datetime import datetime, timezone
import os

# Create Logs directory and file if not exists
if not os.path.exists("logs/DataProcessor"):
    os.makedirs("logs/DataProcessor")
if not os.path.exists(f"logs/DataProcessor/{datetime.today().strftime('%Y-%m-%d')}.log"):
    open(f"logs/DataProcessor/{datetime.today().strftime('%Y-%m-%d')}.log", 'a').close()

logger = logging.getLogger('my_app')
logger.setLevel(logging.DEBUG)

c_handler = logging.StreamHandler()
f_handler = logging.FileHandler(f"logs/DataProcessor/{datetime.today().strftime('%Y-%m-%d')}.log")
mf_handler = logging.FileHandler(f"logs/Data_Sys/{datetime.today().strftime('%Y-%m-%d')}.log")
c_handler.setLevel(logging.WARNING)
f_handler.setLevel(logging.DEBUG)
mf_handler.setLevel(logging.WARNING)

format_str = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
c_handler.setFormatter(format_str)
f_handler.setFormatter(format_str)
mf_handler.setFormatter(format_str)

logger.addHandler(c_handler)
logger.addHandler(f_handler)
logger.addHandler(mf_handler)

try:
    import pandas_market_calendars as mcal
    _HAS_MCAL = True
except ImportError:
    _HAS_MCAL = False

EXCHANGE_TIMEZONE: Dict[str, str] = {
    "NSE": "Asia/Kolkata", "BSE": "Asia/Kolkata", "NYSE": "America/New_York",
    "NASDAQ": "America/New_York", "LSE": "Europe/London", "TSE": "Asia/Tokyo",
    "HKEX": "Asia/Hong_Kong", "ASX": "Australia/Sydney",
}
EXCHANGE_CALENDAR: Dict[str, str] = {
    "NSE": "NSE", "BSE": "BSE", "NYSE": "NYSE", "NASDAQ": "NASDAQ",
    "LSE": "LSE", "TSE": "TSE", "HKEX": "HKEX", "ASX": "ASX",
}
INTERVAL_TO_FREQ: Dict[str, str] = {
    "1m": "1min", "2m": "2min", "5m": "5min", "15m": "15min",
    "30m": "30min", "60m": "1h", "90m": "90min", "1h": "1h",
    "1d": "B", "5d": "5B", "1wk": "W-FRI", "1mo": "BMS", "3mo": "3BMS",
}


class BaseCandleProcessor:
    TARGET_TIMEZONE = "Asia/Kolkata"

    @staticmethod
    def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        required = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required):
            logger.error(f"Missing required columns: {required}")
            raise ValueError(f"DataFrame missing required columns. Need {required}")

        mask = (
            (df['high'] < df[['open', 'close', 'low']].max(axis=1)) |
            (df['low'] > df[['open', 'close', 'high']].min(axis=1)) |
            (df['volume'] < 0) |
            (df[['open', 'high', 'low', 'close']].isnull().any(axis=1)) |
            ((df[['open', 'high', 'low', 'close']] <= 0).any(axis=1))
        )
        dropped = mask.sum()
        if dropped:
            logger.warning(f"Dropping {dropped} invalid candle(s).")
            df = df[~mask].copy()
        return df

    @staticmethod
    def add_timestamp_datetime(df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        epoch = pd.Timestamp("1970-01-01", tz="utc")
        if df.index.tz is None:
            utc_index = df.index.tz_localize("utc")
        else:
            utc_index = df.index.tz_convert("utc")
        df['timestamp'] = ((utc_index - epoch) // pd.Timedelta('1s')).astype(np.int64)
        df['datetime'] = df.index
        return df

    @staticmethod
    def classify_candles(df: pd.DataFrame) -> pd.DataFrame:
        close = df['close'].to_numpy()
        open_ = df['open'].to_numpy()
        conditions = [close > open_, close < open_, np.isclose(close, open_)]
        choices = ['bullish', 'bearish', 'doji']
        df['candle_type'] = np.select(conditions, choices, default='doji')
        df['candle_type'] = df['candle_type'].astype('category')
        return df

    @staticmethod
    def convert_datetime_to_target_tz(df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert 'datetime' column to target timezone (Asia/Kolkata) and then
        make it timezone‑naive, so the CSV shows local wall‑clock time without +05:30.
        Example: 2026-05-07 07:50:00+00:00 -> 2026-05-07 13:20:00
        """
        if 'datetime' not in df.columns:
            logger.error("convert_datetime_to_target_tz: 'datetime' column missing")
            raise KeyError("'datetime' column required")

        df['datetime'] = pd.to_datetime(df['datetime'])
        if df['datetime'].dt.tz is None:
            logger.warning("'datetime' is naive; assuming UTC")
            df['datetime'] = df['datetime'].dt.tz_localize('UTC')

        original_tz = str(df['datetime'].dt.tz)
        # Convert to target timezone, then strip timezone (naive local time)
        df['datetime'] = df['datetime'].dt.tz_convert(BaseCandleProcessor.TARGET_TIMEZONE).dt.tz_localize(None)
        logger.info(f"Converted 'datetime' from {original_tz} to naive {BaseCandleProcessor.TARGET_TIMEZONE} (local time without offset)")
        return df

    @staticmethod
    def finalize(df: pd.DataFrame) -> pd.DataFrame:
        columns = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'candle_type']
        present_cols = [c for c in columns if c in df.columns]
        final = df[present_cols].reset_index(drop=True)
        return final


class YFinanceDataProcessor(BaseCandleProcessor):
    @staticmethod
    def normalize(df: pd.DataFrame, symbol: str = None) -> pd.DataFrame:
        if df.empty:
            return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        rename = {
            'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close',
            'Volume': 'volume', 'Adj Close': 'adj_close',
        }
        df.rename(columns=rename, inplace=True)
        wanted = ['open', 'high', 'low', 'close', 'volume']
        keep = [c for c in wanted if c in df.columns]
        df = df[keep]
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        return df

    @classmethod
    def process(cls, df: pd.DataFrame, exchange: str = None, interval: str = "1d",
                check_continuity: bool = True) -> pd.DataFrame:
        if df.empty:
            logger.warning("Empty yfinance DataFrame, skipping processing.")
            return df

        df = cls.normalize(df)
        df = cls.validate_ohlcv(df)

        if check_continuity and _HAS_MCAL and exchange:
            cls._check_continuity(df, exchange, interval)

        df = cls.add_timestamp_datetime(df)
        df = cls.convert_datetime_to_target_tz(df)   # ← converts to naive IST
        df = cls.classify_candles(df)
        df = cls.finalize(df)
        return df

    @staticmethod
    def _check_continuity(df: pd.DataFrame, exchange: str, interval: str):
        cal_name = EXCHANGE_CALENDAR.get(exchange.upper())
        if not cal_name:
            raise ModuleNotFoundError(f"No calendar for exchange {exchange}")
        cal = mcal.get_calendar(cal_name)
        tz = EXCHANGE_TIMEZONE.get(exchange.upper(), "UTC")
        start = df.index.min().normalize()
        end = df.index.max().normalize()
        if interval in ['1d', '5d', '1wk', '1mo', '3mo']:
            expected = cal.valid_days(start_date=start, end_date=end, tz=tz)
        else:
            freq = INTERVAL_TO_FREQ.get(interval)
            if freq is None:
                raise ValueError(f"Unsupported interval {interval}")
            schedule = cal.schedule(start_date=start, end_date=end)
            expected_list = []
            for row in schedule.itertuples():
                day_range = pd.date_range(row.market_open, row.market_close, freq=freq, tz=tz, inclusive='both')
                expected_list.append(day_range)
            expected = pd.DatetimeIndex(np.concatenate(expected_list)) if expected_list else pd.DatetimeIndex([], tz=tz)
        received = df.index.tz_convert(tz) if df.index.tz is not None else df.index.tz_localize(tz)
        missing = expected.difference(received)
        extra = received.difference(expected)
        if len(missing) > 0:
            logger.warning(f"Missing {len(missing)} expected candles (e.g., {missing[0]})")
        if len(extra) > 0:
            logger.warning(f"Extra {len(extra)} candles not in calendar (e.g., {extra[0]})")


class GrowwDataProcessor(BaseCandleProcessor):
    @staticmethod
    def normalize(df: pd.DataFrame, exchange: str) -> pd.DataFrame:
        if df.empty:
            return df
        tz = EXCHANGE_TIMEZONE.get(exchange.upper(), "UTC")
        df.index = pd.to_datetime(df['datetime'], unit='s', utc=True).dt.tz_convert(tz)
        df.index.name = 'datetime'
        df = df[['open', 'high', 'low', 'close', 'volume']].copy()
        return df

    @classmethod
    def process(cls, df: pd.DataFrame, exchange: str, interval: str = "1d",
                check_continuity: bool = True) -> pd.DataFrame:
        if df.empty:
            logger.warning("Empty Groww DataFrame, skipping processing.")
            return df

        df = cls.normalize(df, exchange)
        df = cls.validate_ohlcv(df)

        if check_continuity and _HAS_MCAL:
            cls._check_continuity(df, exchange, interval)

        df = cls.add_timestamp_datetime(df)
        df = cls.convert_datetime_to_target_tz(df)   # ← converts to naive IST
        df = cls.classify_candles(df)
        df = cls.finalize(df)
        return df

    @staticmethod
    def _check_continuity(df: pd.DataFrame, exchange: str, interval: str):
        YFinanceDataProcessor._check_continuity.__func__(df, exchange, interval)