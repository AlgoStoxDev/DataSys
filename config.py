# =====================================================
# TIMEZONE & FORMAT DEFAULTS
# =====================================================
UTC_TIMEZONE: str = "Asia/Kolkata"
std_fmt: str = "%Y-%m-%d %H:%M:%S"

# =====================================================
# DEFAULT SYMBOL, EXCHANGE, INTERVAL
# =====================================================
Symbol: str = "TATA"
Exchange: str = "NSE"
Interval: str = "1m"

# =====================================================
# CSV CONFIGURATION
# =====================================================
REQUIRED_HEADERS: list[str] = ["timestamp", "open", "high", "low", "close", "volume"]

# =====================================================
# API REQUEST LIMITS (in seconds)
# =====================================================
HISTORICAL_REQUEST_LIMITS: dict[str, int | float] = {
    # 7 days
    "1m": 7 * 86400,
    # 15 days
    "5m": 15 * 86400,
    # 30 days
    "10m": 30 * 86400,
    # 150 days
    "60m": 150 * 86400,
    # 365 days
    "240m": 365 * 86400,
    # 1080 days
    "1d": 1080 * 86400,
    # unlimited
    "1w": float("inf")
}

# =====================================================
# TOTAL HISTORICAL DATA AVAILABLE (in seconds)
# =====================================================
HISTORICAL_DATA_AVAILABILITY: dict[str, int | float] = {
    # 90 days
    "1m": 90 * 86400,
    "5m": 90 * 86400,
    "10m": 90 * 86400,
    "60m": 90 * 86400,
    "240m": 90 * 86400,
    # unlimited
    "1d": float("inf"),
    "1w": float("inf")
}

# =====================================================
# PERFORMANCE OPTIMIZATION SETTINGS
# =====================================================
ENABLE_TIMESTAMP_CACHING: bool = True  # Cache ZoneInfo objects
BATCH_CONVERSION_THRESHOLD: int = 10  # Min timestamps for batch conversion
MAX_CHUNKS_PER_REQUEST: int = 1000  # Safety limit on chunk count
DATETIME_CACHE_SIZE: int = 1000  # LRU cache size for datetime conversions

# =====================================================
# CSV FILE SETTINGS
# =====================================================
CSV_ENCODING: str = "utf-8"
CSV_DELIMITER: str = ","
CSV_NEWLINE: str = ""

# =====================================================
# DEFAULT REQUEST PARAMETERS
# =====================================================
DEFAULT_SYMBOL: str = Symbol
DEFAULT_EXCHANGE: str = Exchange
DEFAULT_INTERVAL: str = Interval
DEFAULT_TIMEZONE: str = UTC_TIMEZONE
DEFAULT_FORMAT: str = std_fmt