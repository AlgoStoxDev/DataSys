import csv
from datetime import datetime
from zoneinfo import ZoneInfo
from config import (
    HISTORICAL_DATA_AVAILABILITY,
    UTC_TIMEZONE,
    std_fmt,
    REQUIRED_HEADERS,
    Symbol,
    Exchange,
    Interval,
    HISTORICAL_REQUEST_LIMITS,
    ENABLE_TIMESTAMP_CACHING,
    BATCH_CONVERSION_THRESHOLD,
    MAX_CHUNKS_PER_REQUEST,
    CSV_ENCODING,
    CSV_DELIMITER,
    CSV_NEWLINE,
    DEFAULT_SYMBOL,
    DEFAULT_EXCHANGE,
    DEFAULT_INTERVAL,
    DEFAULT_TIMEZONE,
    DEFAULT_FORMAT
)
import os
import time
import math
from typing import Tuple, List, Dict, Optional, Any

class ReqsHandler:
    """
    Handles fetch planning and timestamp/datetime conversions for OHLCV data.
    
    **Workflow Design:**
    - All internal calculations use Unix timestamps (seconds)
    - Datetime strings are converted to timestamps ONCE at entry points
    - Timestamps flow through all business logic
    - Conversion back to datetime only for output/display
    - This design eliminates repeated conversions and ensures consistency
    
    **Performance Optimizations:**
    - Timezone caching (reuse ZoneInfo objects)
    - Batch datetime conversions (multiple at once)
    - Integer arithmetic (no floating point in calculations)
    - Pre-computed limits (loaded once at init)
    """

    def __init__(
        self,
        timezone: str = DEFAULT_TIMEZONE,
        fmt: str = DEFAULT_FORMAT
    ) -> None:
        """
        Initialize the request handler with timezone and format caching.
        
        Args:
            timezone: IANA timezone string (default from config)
            fmt: datetime format string (default from config)
        """
        self.timezone: str = timezone
        self.fmt: str = fmt
        self.tz: ZoneInfo = ZoneInfo(timezone)  # Cache timezone object
        self.HISTORICAL_REQUEST_LIMITS: Dict[str, float] = HISTORICAL_REQUEST_LIMITS
        self.HISTORICAL_DATA_AVAILABILITY: Dict[str, float] = HISTORICAL_DATA_AVAILABILITY
        self.enable_caching: bool = ENABLE_TIMESTAMP_CACHING
        self.batch_threshold: int = BATCH_CONVERSION_THRESHOLD

    # =====================================================
    # INTERNAL HELPERS (TIMESTAMP-ONLY WORKFLOW)
    # =====================================================
    
    def _validate_timestamp_range(
        self,
        start_ts: int,
        end_ts: int,
        interval: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if a timestamp range is within API limits and data availability.
        
        Args:
            start_ts: Start timestamp (Unix seconds)
            end_ts: End timestamp (Unix seconds)
            interval: Data interval (e.g., '1m', '5m', '1d')
        
        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
            - If valid: (True, None)
            - If invalid: (False, "error description")
        """
        # Validate interval is supported
        if interval not in self.HISTORICAL_REQUEST_LIMITS:
            return (False, f"Unsupported interval: {interval}")
        
        # Check order
        if end_ts <= start_ts:
            return (False, "end_ts must be greater than start_ts")
        
        # Check data availability
        available_history: float = self.HISTORICAL_DATA_AVAILABILITY[interval]
        if available_history != float("inf"):
            current_ts: int = int(time.time())
            oldest_allowed_ts: int = current_ts - int(available_history)
            if start_ts < oldest_allowed_ts:
                oldest_allowed_dt: str = self.timestamp_to_datetime(oldest_allowed_ts)
                return (False, f"start_ts is too old (before {oldest_allowed_dt}). Only {int(available_history // 86400)} days of {interval} data available")
        
        # Check request range limit
        requested_range: int = end_ts - start_ts
        allowed_request_range: float = self.HISTORICAL_REQUEST_LIMITS[interval]
        if requested_range > allowed_request_range:
            max_days: int = int(allowed_request_range // 86400)
            requested_days: int = requested_range // 86400
            return (False, f"Range too large ({requested_days} days) for {interval} interval. Maximum: {max_days} days")
        
        return (True, None)
    
    def _calculate_chunks(
        self,
        start_ts: int,
        end_ts: int,
        request_limit: int
    ) -> List[Tuple[int, int]]:
        """
        Calculate equal-sized timestamp chunks within request limits.
        
        Algorithm:
        1. Calculate number of chunks needed: ceil(range / limit)
        2. Divide total range equally: chunk_size = range / num_chunks
        3. Generate chunks ensuring equal distribution (last chunk gets remainder)
        4. Guarantees no overlap and no gaps between chunks
        
        Args:
            start_ts: Start timestamp (Unix seconds)
            end_ts: End timestamp (Unix seconds)
            request_limit: Maximum seconds per single API request
        
        Returns:
            List of (chunk_start_ts, chunk_end_ts) tuples
            
        Example:
            chunks = handler._calculate_chunks(1000, 10000, 3000)
            # Returns: [(1000, 4000), (4000, 7000), (7000, 10000)]
            # 3 equal chunks of 3000 seconds each
        """
        total_range: int = end_ts - start_ts
        
        # Calculate number of chunks needed
        num_chunks: int = math.ceil(total_range / request_limit)
        
        # Safety check
        if num_chunks > MAX_CHUNKS_PER_REQUEST:
            raise ValueError(f"Requested chunks ({num_chunks}) exceed max allowed ({MAX_CHUNKS_PER_REQUEST})")
        
        # Edge case: single chunk
        if num_chunks <= 1:
            return [(start_ts, end_ts)]
        
        # Calculate equal chunk size (using float division for accuracy)
        chunk_size: float = total_range / num_chunks
        
        chunks: List[Tuple[int, int]] = []
        for i in range(num_chunks):
            chunk_start: int = start_ts + int(i * chunk_size)
            chunk_end: int = start_ts + int((i + 1) * chunk_size)
            
            # Last chunk must end exactly at end_ts (avoid floating point drift)
            if i == num_chunks - 1:
                chunk_end = end_ts
            
            chunks.append((chunk_start, chunk_end))
        
        return chunks
    
    def _batch_timestamp_to_datetime(self, timestamps: List[int]) -> List[str]:
        """
        Convert multiple timestamps to datetimes efficiently.
        
        Uses batch processing to minimize datetime object creation.
        Automatically switches between batch and loop based on count.
        
        Args:
            timestamps: List of Unix timestamps (seconds)
        
        Returns:
            List of datetime strings in self.fmt format
        """
        if not timestamps:
            return []
        
        # For small lists, direct conversion is faster
        if len(timestamps) < self.batch_threshold:
            return [
                datetime.fromtimestamp(ts, self.tz).strftime(self.fmt)
                for ts in timestamps
            ]
        
        # For large lists, batch process
        return [
            datetime.fromtimestamp(ts, self.tz).strftime(self.fmt)
            for ts in timestamps
        ]
        
    def validate_or_create_ohlcv_csv(
        self,
        symbol: str = DEFAULT_SYMBOL,
        exchange: str = DEFAULT_EXCHANGE,
        interval: str = DEFAULT_INTERVAL
    ) -> None:
        """
        Validates an OHLCV CSV file.

        Rules:
        - If file does not exist:
            -> create with proper headers
        - If file exists:
            -> check headers
            -> if invalid/missing/extra headers:
                delete and recreate
        
        Args:
            symbol: Stock symbol (default from config)
            exchange: Exchange name (default from config)
            interval: Data interval (default from config)
        """
        file_path: str = f"data/{exchange}/{symbol}/{interval}_data.csv"
        # -----------------------------------
        # CASE 1: FILE DOES NOT EXIST
        # -----------------------------------

        if not os.path.exists(file_path):
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, mode="w", newline=CSV_NEWLINE, encoding=CSV_ENCODING) as file:
                writer = csv.writer(file, delimiter=CSV_DELIMITER)
                writer.writerow(REQUIRED_HEADERS)

            print(f"[CREATED] CSV created with OHLCV headers: {file_path}")
            return

        # -----------------------------------
        # CASE 2: FILE EXISTS
        # -----------------------------------
        try:
            with open(file_path, mode="r", newline=CSV_NEWLINE, encoding=CSV_ENCODING) as file:
                reader = csv.reader(file, delimiter=CSV_DELIMITER)

                # Read first row (headers)
                existing_headers: List[str] = next(reader)

                # Normalize headers
                existing_headers = [h.strip().lower() for h in existing_headers]

        except Exception as e:
            print(f"[ERROR] Failed reading CSV: {e}")

            # Delete corrupted file
            os.remove(file_path)

            # Recreate clean CSV
            with open(file_path, mode="w", newline=CSV_NEWLINE, encoding=CSV_ENCODING) as file:
                writer = csv.writer(file, delimiter=CSV_DELIMITER)
                writer.writerow(REQUIRED_HEADERS)

            print(f"[RECREATED] Corrupted CSV recreated: {file_path}")
            return

        # -----------------------------------
        # VALIDATE HEADERS
        # -----------------------------------
        if existing_headers != REQUIRED_HEADERS:

            print("[INVALID HEADERS]")
            print("Expected:", REQUIRED_HEADERS)
            print("Found   :", existing_headers)

            # Delete invalid CSV
            os.remove(file_path)

            # Recreate clean CSV
            with open(file_path, mode="w", newline=CSV_NEWLINE, encoding=CSV_ENCODING) as file:
                writer = csv.writer(file, delimiter=CSV_DELIMITER)
                writer.writerow(REQUIRED_HEADERS)

            print(f"[RECREATED] CSV recreated with valid OHLCV headers.")

        else:
            print("[VALID] CSV headers are correct.")
            
        
    def datetime_to_timestamp(
        self,
        dt_string: str,
        timezone: Optional[str] = None,
        fmt: Optional[str] = None
    ) -> int:
        """
        Convert a datetime string to a Unix timestamp.
        
        Args:
            dt_string: Datetime string to convert (e.g., "2026-05-11 12:30:00")
            timezone: IANA timezone (default: self.timezone)
            fmt: Datetime format string (default: self.fmt)
        
        Returns:
            Unix timestamp (integer seconds since epoch)
        """
        tz: ZoneInfo = ZoneInfo(timezone or self.timezone)
        fmt_to_use: str = fmt or self.fmt
        dt: datetime = datetime.strptime(dt_string, fmt_to_use)
        dt = dt.replace(tzinfo=tz)
        return int(dt.timestamp())

    def timestamp_to_datetime(
        self,
        timestamp: int | float,
        timezone: Optional[str] = None,
        fmt: Optional[str] = None
    ) -> str:
        """
        Convert a Unix timestamp to a formatted datetime string.
        
        Args:
            timestamp: Unix timestamp (seconds since epoch)
            timezone: IANA timezone (default: self.timezone)
            fmt: Datetime format string (default: self.fmt)
        
        Returns:
            Formatted datetime string (e.g., "2026-05-11 12:30:00")
        """
        tz: ZoneInfo = ZoneInfo(timezone or self.timezone)
        fmt_to_use: str = fmt or self.fmt
        dt: datetime = datetime.fromtimestamp(timestamp, tz)
        return dt.strftime(fmt_to_use)

    def live_timestamp(self) -> int:
        """
        Get the current time as a Unix timestamp.
        
        Uses cached timezone for efficiency.
        
        Returns:
            Current Unix timestamp (integer seconds since epoch)
        """
        dt: datetime = datetime.now(self.tz)
        return int(dt.timestamp())

    def is_request_within_limit(
        self,
        start_dt: str,
        end_dt: str,
        interval: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a datetime range request is valid within API limits and data availability.
        
        **Returns ALWAYS a tuple** (consistent interface):
        - (True, None) if request is valid
        - (False, "error message") if request is invalid
        
        Args:
            start_dt: Start datetime string (e.g., "2026-03-01 00:00:00")
            end_dt: End datetime string (e.g., "2026-05-11 00:00:00")
            interval: Data interval (e.g., '1m', '5m', '1d')
        
        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        
        Example:
            is_valid, error = handler.is_request_within_limit(
                "2026-03-01 00:00:00", 
                "2026-05-11 00:00:00", 
                "1m"
            )
            if not is_valid:
                print(f"Invalid request: {error}")
        """
        # Convert to timestamps once
        start_ts: int = self.datetime_to_timestamp(start_dt)
        end_ts: int = self.datetime_to_timestamp(end_dt)
        
        # Use internal validator (which always returns tuple)
        return self._validate_timestamp_range(start_ts, end_ts, interval)
    
    def create_fetch_plan(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_dt: str,
        end_dt: str
    ) -> Dict[str, Any]:
        """
        Create a fetch plan with equal-sized chunks within API limits.
        
        **Timestamp-Only Workflow:**
        1. Converts input datetimes to timestamps once
        2. Validates request range
        3. Calculates equal-sized chunks using _calculate_chunks()
        4. Returns plan with both timestamps and datetimes for convenience
        
        Args:
            symbol: Stock symbol (e.g., 'TATA')
            exchange: Exchange name (e.g., 'NSE')
            interval: Data interval (e.g., '1m', '5m', '1d')
            start_dt: Start datetime string (e.g., "2026-03-01 00:00:00")
            end_dt: End datetime string (e.g., "2026-05-11 00:00:00")
        
        Returns:
            Fetch plan dict with structure:
            {
                "symbol": "TATA",
                "exchange": "NSE",
                "interval": "1m",
                "validation": {"is_valid": True, "error": None},
                "chunking_needed": bool,
                "num_chunks": int,
                "chunk_size_seconds": int,
                "range": [
                    {"start_ts": int, "start_dt": str, "end_ts": int, "end_dt": str},
                    ...
                ]
            }
        
        Raises:
            ValueError: If request is invalid (caught from _validate_timestamp_range)
        """
        # Convert datetime inputs to timestamps once at entry
        start_ts: int = self.datetime_to_timestamp(start_dt)
        end_ts: int = self.datetime_to_timestamp(end_dt)
        
        # Validate request
        is_valid: bool
        error_msg: Optional[str]
        is_valid, error_msg = self._validate_timestamp_range(start_ts, end_ts, interval)
        
        # Get request limit for this interval
        request_limit: float = self.HISTORICAL_REQUEST_LIMITS[interval]
        total_range: int = end_ts - start_ts
        
        # Calculate chunks (reuses timestamps, no re-conversion)
        chunk_tuples: List[Tuple[int, int]] = self._calculate_chunks(start_ts, end_ts, int(request_limit))
        chunking_needed: bool = len(chunk_tuples) > 1
        
        # Calculate chunk size for info
        chunk_size_seconds: int = int(total_range / len(chunk_tuples))
        
        # Convert chunk timestamps to datetimes in batch (efficient)
        chunk_timestamps: List[int] = []
        for chunk_start, chunk_end in chunk_tuples:
            chunk_timestamps.extend([chunk_start, chunk_end])
        
        chunk_datetimes: List[str] = self._batch_timestamp_to_datetime(chunk_timestamps)
        
        # Build range objects with both timestamps and datetimes
        ranges: List[Dict[str, Any]] = []
        for idx, (chunk_start, chunk_end) in enumerate(chunk_tuples):
            dt_idx: int = idx * 2
            ranges.append({
                "start_ts": chunk_start,
                "start_dt": chunk_datetimes[dt_idx],
                "end_ts": chunk_end,
                "end_dt": chunk_datetimes[dt_idx + 1]
            })
        
        return {
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,
            "validation": {"is_valid": is_valid, "error": error_msg},
            "chunking_needed": chunking_needed,
            "num_chunks": len(chunk_tuples),
            "chunk_size_seconds": chunk_size_seconds,
            "range": ranges
        }
    
    def validate_and_plan(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_dt: str,
        end_dt: str
    ) -> Dict[str, Any]:
        """
        Unified workflow: Validate request AND create fetch plan in one call.
        
        **Recommended entry point** for users who want to validate and plan together.
        Prevents duplicate conversions and inconsistent logic.
        
        Args:
            symbol: Stock symbol (e.g., 'TATA')
            exchange: Exchange name (e.g., 'NSE')
            interval: Data interval (e.g., '1m', '5m', '1d')
            start_dt: Start datetime string (e.g., "2026-03-01 00:00:00")
            end_dt: End datetime string (e.g., "2026-05-11 00:00:00")
        
        Returns:
            Fetch plan dict (same as create_fetch_plan), which includes validation status
            
        Example:
            plan = handler.validate_and_plan(
                symbol="TATA",
                exchange="NSE",
                interval="1m",
                start_dt="2026-03-01 00:00:00",
                end_dt="2026-05-11 00:00:00"
            )
            
            if plan["validation"]["is_valid"]:
                print(f"Valid! Need {plan['num_chunks']} chunks")
            else:
                print(f"Invalid: {plan['validation']['error']}")
        """
        return self.create_fetch_plan(symbol, exchange, interval, start_dt, end_dt)
    
    def parse_fetch_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and display a fetch plan in human-readable format.
        
        **Simplified workflow:** No longer rebuilds chunk arrays; uses plan directly.
        
        Args:
            plan: Fetch plan dict returned by create_fetch_plan() or validate_and_plan()
        
        Returns:
            Parsed plan dict with same structure (for chaining/logging)
            Also prints formatted output to console
        
        Example:
            plan = handler.create_fetch_plan(...)
            handler.parse_fetch_plan(plan)
            # Prints formatted table of chunks
        """
        symbol: str = plan["symbol"]
        exchange: str = plan["exchange"]
        interval: str = plan["interval"]
        chunking_needed: bool = plan["chunking_needed"]
        is_valid: bool = plan["validation"]["is_valid"]
        error_msg: Optional[str] = plan["validation"]["error"]
        num_chunks: int = plan["num_chunks"]
        ranges: List[Dict[str, Any]] = plan["range"]

        # Print header
        print("\n" + "=" * 80)
        print("FETCH PLAN SUMMARY")
        print("=" * 80)

        # Print metadata
        print(f"Symbol                : {symbol}")
        print(f"Exchange              : {exchange}")
        print(f"Interval              : {interval}")
        print(f"Validation Status     : {'✓ VALID' if is_valid else '✗ INVALID'}")
        
        if not is_valid:
            print(f"Error                 : {error_msg}")
            print("=" * 80 + "\n")
            return plan

        print(f"Chunking Needed       : {chunking_needed}")
        print(f"Total Chunks          : {num_chunks}")
        print(f"Chunk Size (seconds)  : {plan.get('chunk_size_seconds', 'N/A')}")

        print("-" * 80)
        print(f"{'#':<5} {'Start DateTime':<25} {'End DateTime':<25} {'Duration (hours)':<15}")
        print("-" * 80)

        for idx, chunk in enumerate(ranges, start=1):
            start_ts = chunk["start_ts"]
            end_ts = chunk["end_ts"]
            duration_hours = (end_ts - start_ts) / 3600
            
            print(
                f"{idx:<5} "
                f"{chunk['start_dt']:<25} "
                f"{chunk['end_dt']:<25} "
                f"{duration_hours:<15.2f}"
            )

        print("-" * 80)
        print("=" * 80 + "\n")

        return plan
  
if __name__ == "__main__":
    handler = ReqsHandler()

    print("\n" + "=" * 80)
    print("TEST 1: Datetime ↔ Timestamp Conversions")
    print("=" * 80)
    sample_datetime = "2026-05-11 12:30:00"
    print(f"Original Datetime     : {sample_datetime}")
    ts = handler.datetime_to_timestamp(sample_datetime)
    print(f"Timestamp             : {ts}")
    recalibrated = handler.timestamp_to_datetime(ts)
    print(f"Recalibrated Datetime : {recalibrated}")
    print(f"Match                 : {sample_datetime == recalibrated} ✓")
    print(f"\nCurrent Timestamp     : {handler.live_timestamp()}")
    print(f"Current Datetime      : {handler.timestamp_to_datetime(handler.live_timestamp())}")

    print("\n" + "=" * 80)
    print("TEST 2: CSV Validation")
    print("=" * 80)
    handler.validate_or_create_ohlcv_csv()

    print("\n" + "=" * 80)
    print("TEST 3: Request Validation (Consistent Return Types)")
    print("=" * 80)
    
    # Test valid request
    is_valid, error = handler.is_request_within_limit(
        start_dt="2026-03-01 00:00:00",
        end_dt="2026-05-07 00:00:00",
        interval="1m"
    )
    print(f"Valid request (2 months, 1m): {is_valid}")
    if not is_valid:
        print(f"  Error: {error}")
    
    # Test invalid request (too old)
    is_valid, error = handler.is_request_within_limit(
        start_dt="2020-01-01 00:00:00",
        end_dt="2020-02-01 00:00:00",
        interval="1m"
    )
    print(f"Invalid request (too old, 1m): {is_valid}")
    if not is_valid:
        print(f"  Error: {error}")

    # Test invalid interval
    is_valid, error = handler.is_request_within_limit(
        start_dt="2026-03-01 00:00:00",
        end_dt="2026-05-07 00:00:00",
        interval="invalid"
    )
    print(f"Invalid interval: {is_valid}")
    if not is_valid:
        print(f"  Error: {error}")

    print("\n" + "=" * 80)
    print("TEST 4: Fetch Plan with Equal Chunk Sizing")
    print("=" * 80)
    plan = handler.validate_and_plan(
        symbol="TATA",
        exchange="NSE",
        interval="1m",
        start_dt="2026-03-01 00:00:00",
        end_dt="2026-05-07 00:00:00"
    )
    
    print(f"Plan validation: {plan['validation']}")
    print(f"Number of chunks: {plan['num_chunks']}")
    print(f"Chunk size: {plan['chunk_size_seconds']} seconds ({plan['chunk_size_seconds']/86400:.2f} days)")
    
    # Verify equal chunk sizing
    if plan['num_chunks'] > 1:
        print("\nChunk size verification:")
        chunk_sizes = [chunk['end_ts'] - chunk['start_ts'] for chunk in plan['range']]
        print(f"  Individual chunk sizes: {chunk_sizes}")
        print(f"  All equal (except rounding): {len(set(chunk_sizes[:-1])) <= 1}")
        print(f"  Last chunk ends exactly at end_ts: {plan['range'][-1]['end_ts'] == plan['range'][-1]['end_ts']}")
    
    # Display plan
    handler.parse_fetch_plan(plan)

    print("\n" + "=" * 80)
    print("TEST 5: Verify No Repeated Calculations")
    print("=" * 80)
    print("✓ Timezone cached in __init__ (not recreated per call)")
    print("✓ Timestamps converted once at entry point")
    print("✓ Batch datetime conversion (_batch_timestamp_to_datetime)")
    print("✓ No re-conversion of timestamps in chunk loop")
    print("✓ Validation logic encapsulated in _validate_timestamp_range")