# config.py

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_DT_FORMAT = "%Y-%m-%d %H:%M:%S"

REQUIRED_OHLCV_HEADERS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
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

# Safe chunking style to avoid duplicate boundary candles
CHUNK_BOUNDARY_MODE = "half_open_[start_ts,end_ts)"