# config.py

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_DT_FORMAT = "%Y-%m-%d %H:%M:%S"
FETCHING_ENGINES = "yFinance"  
REQUIRED_OHLCV_HEADERS = [
    "timestamp",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "candle_type"
]

# Max duration allowed per single API request, in seconds
HISTORICAL_REQUEST_LIMITS = {
    "1m": 7 * 86400,
    "5m": 15 * 86400,
    "10m": 30 * 86400,
    "60m": 150 * 86400,
    "240m": 365 * 86400,
    "1d": 1080 * 86400,
    "1w": float("inf"),
}

# Total historical availability, in seconds
HISTORICAL_DATA_AVAILABILITY = {
    "1m": 90 * 86400,
    "5m": 90 * 86400,
    "10m": 90 * 86400,
    "60m": 90 * 86400,
    "240m": 90 * 86400,
    "1d": float("inf"),
    "1w": float("inf"),
}


# yfinance / Yahoo Finance historical data limits (in seconds)

YF_HISTORICAL_REQUEST_LIMITS = {
    "1m": 7 * 86400,          # 7 days
    "2m": 7 * 86400,
    "5m": 7 * 86400,
    "15m": 60 * 86400,        # 60 days
    "30m": 60 * 86400,
    "60m": 60 * 86400,
    "90m": 60 * 86400,
    "1h": 60 * 86400,
    "1d": float("inf"),       # no practical single-fetch limit (back to IPO)
    "5d": float("inf"),
    "1wk": float("inf"),
    "1mo": float("inf"),
    "3mo": float("inf"),
}

YF_HISTORICAL_DATA_AVAILABILITY = {
    "1m": 7 * 86400,          # only 7 days of 1‑min data exist
    "2m": 7 * 86400,
    "5m": 7 * 86400,
    "15m": 60 * 86400,        # only 60 days of sub‑hourly data (except 1‑5m)
    "30m": 60 * 86400,
    "60m": 60 * 86400,
    "90m": 60 * 86400,
    "1h": 60 * 86400,
    "1d": float("inf"),       # daily/weekly/monthly data go back to the IPO
    "5d": float("inf"),
    "1wk": float("inf"),
    "1mo": float("inf"),
    "3mo": float("inf"),
}

# Safe chunking style to avoid duplicate boundary candles
CHUNK_BOUNDARY_MODE = "half_open_[start_ts,end_ts)"