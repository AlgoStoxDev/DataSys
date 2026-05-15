from __future__ import annotations
import yfinance as yf
import pandas as pd 
import time
import datetime
from RequestHanlder import ReqsHandler
from typing import Any, Dict, Optional, Union
import logging
import requests
import os

to_dt = ReqsHandler().timestamp_to_datetime

# Set up logging

# Ceate Logs directory and file if not exists
if not os.path.exists("logs/Data_Fetcher"):
    os.makedirs("logs/Data_Fetcher") 
if not os.path.exists(f"logs/Data_Fetcher/{datetime.datetime.today().strftime('%Y-%m-%d')}.log"):
    open(f"logs/Data_Fetcher/{datetime.datetime.today().strftime('%Y-%m-%d')}.log", 'a').close()


# 1. Create a custom logger
logger = logging.getLogger('my_app')
logger.setLevel(logging.DEBUG)  # Set the lowest level to capture all events

# 2. Create handlers
c_handler = logging.StreamHandler()        # Console handler
f_handler = logging.FileHandler(f"logs/Data_Fetcher/{datetime.datetime.today().strftime('%Y-%m-%d')}.log") # File handler
mf_handler = logging.FileHandler(f"logs/Data_Sys/{datetime.datetime.today().strftime('%Y-%m-%d')}.log") # File handler for my_app.log
c_handler.setLevel(logging.WARNING)           # Only show INFO+ in terminal
f_handler.setLevel(logging.DEBUG)
mf_handler.setLevel(logging.WARNING)           # Only show WARNING+ in my_app.log
          # Save everything to the file

# 3. Create formatters and add them to handlers
format_str = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
c_handler.setFormatter(format_str)
f_handler.setFormatter(format_str)
mf_handler.setFormatter(format_str)
# 4. Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)
logger.addHandler(mf_handler)

def to_unix_timestamp(ts):
    """
    Converts various inputs (numeric, datetime, string) to a Unix timestamp integer.
    """
    if isinstance(ts, (int, float)):
        # Handles both ints and problematic floats like 1778092200.0
        return int(ts)
    elif isinstance(ts, datetime):
        # Crucial: convert to UTC to get an absolute timestamp, then to int
        return int(ts.astimezone(datetime.timezoneezone.utc).timestamp())
    elif isinstance(ts, str):
        # Parse the string first
        dt = pd.to_datetime(ts).to_pydatetime()
        return int(dt.astimezone(datetime.timezone.utc).timestamp())
    else:
        raise TypeError(f"Unsupported type for timestamp conversion: {type(ts)}")
    
class GrowwAPIError(Exception):
    """Custom exception for Groww API errors."""
    pass

def fetch_groww_historical_raw(
    symbol: str,
    exchange: str,
    start_ts: Union[int, float, str],
    end_ts: Union[int, float, str],
    interval: Union[int, str],
    *,
    token: str,
    segment: str = "CASH",
    timeout: int = 20,
    retries: int = 3,
    backoff_seconds: float = 1.5,
) -> Dict[str, Any]:
    """
    Fetch raw historical candle data from Groww and return the JSON exactly as received.

    Notes:
      - Uses the legacy /v1/historical/candle/range endpoint.
      - Returns Groww's raw JSON response without reshaping candles.
      - For equities and indices, segment is usually CASH.
      - For derivatives, segment is usually FNO.
    """
    start_ts = to_unix_timestamp(start_ts)
    end_ts = to_unix_timestamp(end_ts)
    if not symbol or not symbol.strip():
        logger.error(f"DataFetcher: Invalid symbol provided for fetching Groww historical data on {datetime.datetime.now()}.")
        raise ValueError("symbol is required")
    if not exchange or not exchange.strip():
        logger.error(f"DataFetcher: Invalid exchange provided for fetching Groww historical data on {datetime.datetime.now()}.")
        raise ValueError("exchange is required")
    
    try:
        interval_int = int(interval)
        logger.info(f"DataFetcher: Fetching Groww historical data for {symbol} on {exchange} with interval {interval_int} minutes.")
    except Exception as exc:
        logger.error(f"DataFetcher: Invalid interval provided for fetching Groww historical data on {datetime.datetime.now()}.")
        raise ValueError("interval must be an integer number of minutes") from exc

    if interval_int <= 0:
        logger.error(f"DataFetcher: Invalid interval provided for fetching Groww historical data on {datetime.datetime.now()}.")
        raise ValueError("interval must be greater than 0")

    url = "https://api.groww.in/v1/historical/candle/range"
    params = {
        "exchange": exchange.strip().upper(),
        "segment": segment.strip().upper(),
        "trading_symbol": symbol.strip().upper(),
        "start_time": start_ts,
        "end_time": end_ts,
        "interval_in_minutes": interval_int,
    }
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "X-API-VERSION": "1.0",
    }

    last_error: Optional[Exception] = None
    with requests.Session() as session:
        for attempt in range(1, retries + 1):
            try:
                resp = session.get(url, params=params, headers=headers, timeout=timeout)

                # Retry on transient server / rate-limit problems.
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise GrowwAPIError(
                        f"Transient HTTP {resp.status_code}: {resp.text[:300]}"
                    )

                resp.raise_for_status()
                logger.info(f"DataFetcher: Successfully fetched Groww historical data for {symbol} on {exchange} with interval {interval_int} minutes.")
                try:
                    return resp.json()
                except ValueError as exc:
                    logger.error(f"DataFetcher: Failed to parse Groww historical data response as JSON for {symbol} on {exchange} with interval {interval_int} minutes on {datetime.datetime.now()}. Response was: {resp.text[:300]}")
                    raise GrowwAPIError(
                        f"Groww returned non-JSON response: {resp.text[:300]}"
                    ) from exc


            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(backoff_seconds * attempt)
                    logger.warning(f"DataFetcher: Attempt {attempt} failed for fetching Groww historical data for {symbol} on {exchange} with interval {interval_int} minutes. Retrying... Error: {exc}")
                else:
                    logger.error(f"DataFetcher: All attempts failed for fetching Groww historical data for {symbol} on {exchange} with interval {interval_int} minutes. Error: {exc}")
                    break

# Exchange → yfinance ticker suffix
EXCHANGE_SUFFIX = {
    "NSE": ".NS",
    "BSE": ".BO",
    "NYSE": "",
    "NASDAQ": "",
    "LSE": ".L",
    "TSE": ".T",
    "HKEX": ".HK",
    "ASX": ".AX",
    # add more as needed
}

def fetch_yfinance_data(
    symbol: str,
    exchange: Optional[str] = None,
    interval: str = "1d",
    start_ts: Optional[Union[int, float]] = None,
    end_ts: Optional[Union[int, float]] = None,
) -> pd.DataFrame:
    """
    Fetch raw historical data from Yahoo Finance in a single request.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g., "RELIANCE", "AAPL").
    exchange : str, optional
        Exchange code (e.g., "NSE", "BSE"). Adds the correct suffix.
    interval : str
        Data interval. Valid: "1m","2m","5m","15m","30m","60m","90m","1h",
        "1d","5d","1wk","1mo","3mo".
    start_ts : int, float, or datetime, optional
        Start time (Unix seconds, timestamp float, or datetime). None = earliest available.
    end_ts : int, float, or datetime, optional
        End time (Unix seconds, timestamp float, or datetime). None = now.

    Returns
    -------
    pd.DataFrame
        Columns: Open, High, Low, Close, Adj Close, Volume. Index: datetime.
    """
    start_ts = to_unix_timestamp(start_ts) if start_ts is not None else None
    end_ts = to_unix_timestamp(end_ts) if end_ts is not None else None
    logger.warning(f"DataFetcher: Using FallBack method to fetch data for symbol {symbol} on {exchange} with interval {interval} starting at {start_ts} and ending at {end_ts} from Yahoo Finance.")
    try:
        # Build full ticker
        suffix = EXCHANGE_SUFFIX.get(exchange.upper(), "") if exchange else ""
        ticker = f"{symbol.upper()}{suffix}"

        start_dt = start_ts
        end_dt = end_ts

        # Single fetch – letting Yahoo handle the range directly
        df = yf.download(
            tickers=ticker,
            start=start_dt,
            end=end_dt,
            interval=interval,
            progress=False,
            auto_adjust=False,  # keeps 'Adj Close' column separate
        )
        logger.info(f"DataFetcher: Successfully fetched Yahoo Finance data for symbol {symbol} on {exchange} with interval {interval} starting at {start_ts} and ending at {end_ts}.")
        return df
    
    except Exception as exc:
        logger.error(f"DataFetcher: Failed to fetch Yahoo Finance data using fallback method for symbol {symbol} on {exchange} with interval {interval} starting at {start_ts} and ending at {end_ts}. Error: {exc}")
        raise exc