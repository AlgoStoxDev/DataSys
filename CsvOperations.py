from pathlib import Path
import pandas as pd 
from numpy import append
import numpy as np
import logging
import datetime
import os
from typing import Optional, List, Tuple, Dict, Union


# Ceate Logs directory and file if not exists
if not os.path.exists("logs/CsvOperations"):
    os.makedirs("logs/CsvOperations") 
if not os.path.exists(f"logs/CsvOperations/{datetime.datetime.today().strftime('%Y-%m-%d')}.log"):
    open(f"logs/CsvOperations/{datetime.datetime.today().strftime('%Y-%m-%d')}.log", 'a').close()


# 1. Create a custom logger
logger = logging.getLogger('my_app')
logger.setLevel(logging.DEBUG)  # Set the lowest level to capture all events

# 2. Create handlers
c_handler = logging.StreamHandler()        # Console handler
f_handler = logging.FileHandler(f"logs/CsvOperations/{datetime.datetime.today().strftime('%Y-%m-%d')}.log") # File handler
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
fetch_plan = []

class csvOperations:
    def __init__(self, file_path):
        self.file_path = file_path



    def is_csv_valid(self,filepath: str) -> str:
        """
        Return a string indicating the validation status of the CSV file.
        """
        path = Path(filepath)
        if not path.exists() or path.stat().st_size == 0:
            logger.warning(f"CsvOperations: CSV file {filepath} does not exist or is empty on {datetime.datetime.now()} falling back to fetch and save new data.")
            return "CSV file does not exist or is empty"

        try:
            # Get headers without reading data
            columns = pd.read_csv(filepath, nrows=0).columns.tolist()
        except Exception:
            logger.info(f"CsvOperations: Failed to read CSV file's headers on filepath: {filepath} on {datetime.datetime.now()}.")
            return "NO CSV FILE HEADERS"

        required = {'timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'candle_type'}
        if not required.issubset(columns):
            logger.warning(f"CsvOperations: CSV file {filepath} is missing required columns on {datetime.datetime.now()}. Required: {required}, Found: {set(columns)}. Falling back to fetch and save new data.")
            return "MISSING REQUIRED COLUMNS"

        try:
            sample = pd.read_csv(filepath, nrows=10)
        except Exception:
            logger.warning(f"CsvOperations: Failed to read CSV file {filepath} on {datetime.datetime.now()}.")
            return "CSV CAN BE CORRUPTED OR UNREADABLE"

        if len(sample) == 0:
            logger.warning(f"CsvOperations: CSV file {filepath} has no data rows on {datetime.datetime.now()}. Falling back to fetch and save new data.")
            return "CSV FILE HAS NO DATA"

        ts = sample['timestamp']
        if ts.isnull().any() or (ts <= 0).any():
            logger.warning(f"CsvOperations: CSV file {filepath} has invalid timestamps on {datetime.datetime.now()}. Falling back to fetch and save new data.")
            return "INVALID TIMESTAMP VALUES"

        # Check that OHLCV columns are numeric (not all NaN)
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if not pd.api.types.is_numeric_dtype(sample[col]):
                logger.warning(f"CsvOperations: CSV file {filepath} has non-numeric values in column {col} on {datetime.datetime.now()}. Falling back to fetch and save new data.")
                return "NON-NUMERIC VALUES FOUND"
            if sample[col].isnull().all():
                logger.warning(f"CsvOperations: CSV file {filepath} has all null values in column {col} on {datetime.datetime.now()}. Falling back to fetch and save new data.")
                return "ALL VALUES IN COLUMN ARE NULL"

        logger.info(f"CsvOperations: CSV file {filepath} is valid on {datetime.datetime.now()}.")
        return "CSV IS VALID"


    def save_to_csv(self, df, symbol, exchange, interval, append=False):
        try:
            import pandas as _pd

            # Handle list of DataFrames (as before)
            if isinstance(df, list):
                if not df:
                    logger.warning(f"CsvOperations: [save_to_csv] empty list was passed ({df}) on {datetime.datetime.now()}. Nothing to save.")
                    return
                df = _pd.concat(df)
                df = df[~df.index.duplicated(keep='first')]
                df.sort_index(inplace=True)

            # Ensure we have a DataFrame (may already be processed)
            data = df.copy()

            if isinstance(data.index, _pd.DatetimeIndex):
                epoch = _pd.Timestamp("1970-01-01", tz="utc")
                if data.index.tz is None:
                    utc_idx = data.index.tz_localize("utc")
                    logger.info(f"CsvOperations: Localized naive datetime index to UTC for symbol {symbol} on {datetime.datetime.now()}.")
                else:
                    utc_idx = data.index.tz_convert("utc")
                    logger.info(f"CsvOperations: Converted datetime index to UTC for symbol {symbol} on {datetime.datetime.now()} for calculations")
                if 'timestamp' not in data.columns:
                    data['timestamp'] = ((utc_idx - epoch) // _pd.Timedelta('1s')).astype(int)
                    logger.info(f"CsvOperations: Added timestamp column for symbol {symbol} on {datetime.datetime.now()}.")
                if 'datetime' not in data.columns:
                    data['datetime'] = data.index
                    logger.info(f"CsvOperations: Added datetime column from index for symbol {symbol} on {datetime.datetime.now()}.")
                data = data.reset_index(drop=True)
            # Normalise column names to lowercase (just in case)
            rename_map = {
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
                "Timestamp": "timestamp", "Datetime": "datetime",
            }
            data.rename(columns=rename_map, inplace=True)
            logger.info(f"CsvOperations: Normalized column names for symbol {symbol} on {datetime.datetime.now()}.")

            # Define the exact column order we want in the CSV
            desired_cols = ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'candle_type']
            # Keep only columns that exist (to tolerate missing candle_type, etc.)
            existing = [c for c in desired_cols if c in data.columns]
            data = data[existing]
            logger.info(f"CsvOperations: Reordered columns for symbol {symbol} on {datetime.datetime.now()}.")

            filepath = f"data/{symbol}/{exchange}/{interval}.csv"

            # Write – without the index (because datetime is a column)
            if append:
                # Appending assumes the file already has exactly the same headers
                data.to_csv(filepath, mode='a', header=False, index=False)
                logger.info(f"CsvOperations: Appended data to CSV file for symbol {symbol} on {datetime.datetime.now()}.")
            else:
                data.to_csv(filepath, mode='w', header=True, index=False)
                logger.info(f"CsvOperations: Saved new CSV file for symbol {symbol} on {datetime.datetime.now()}.")
        except Exception as e:
            logger.error(f"CsvOperations: An unexpected error occurred while saving CSV for symbol {symbol} on {datetime.datetime.now()}. THE ERROR WAS: {e}")

    def interval_to_timedelta(self, interval: str) -> datetime.timedelta:
        """
        Convert Yahoo Finance style interval (e.g., '1m', '5m', '1h', '1d') to timedelta.
        Raises ValueError for unsupported intervals.
        """
        if not isinstance(interval, str) or len(interval) < 2:
            raise ValueError(f"Invalid interval format: {interval}")
        unit = interval[-1]
        try:
            value = int(interval[:-1])
        except ValueError:
            raise ValueError(f"Interval value must be integer: {interval}")
        
        if unit == 'm':
            return datetime.timedelta(minutes=value)
        elif unit == 'h':
            return datetime.timedelta(hours=value)
        elif unit == 'd':
            return datetime.timedelta(days=value)
        else:
            raise ValueError(f"Unsupported interval unit '{unit}'. Use 'm', 'h', or 'd'.")

        
    def to_utc_naive_timestamp(self, ts: Union[datetime.datetime, pd.Timestamp, float, int, str], exchange_tz: str = None) -> pd.Timestamp:
        """
        Convert various timestamp representations to a UTC‑naive pandas Timestamp.
        
        Args:
            ts: input timestamp.
            exchange_tz: IANA timezone name (e.g., 'Asia/Kolkata') for naive inputs.
                        If None and ts is naive, we assume UTC (legacy behaviour).
        
        Returns:
            pd.Timestamp with UTC time but timezone naive.
        """
        if isinstance(ts, (datetime.datetime, pd.Timestamp)):
            pd_ts = pd.Timestamp(ts)
            if pd_ts.tz is not None:
                # Convert to UTC and then remove timezone info
                pd_ts = pd_ts.tz_convert('UTC').tz_localize(None)
                logger.debug(f"Converted tz aware {ts} to UTC naive: {pd_ts}")
            else:
                # Naive input: localize to exchange timezone if provided, else assume UTC
                if exchange_tz:
                    try:
                        pd_ts = pd_ts.tz_localize(exchange_tz).tz_convert('UTC').tz_localize(None)
                        logger.debug(f"Localized naive {ts} to {exchange_tz} then to UTC‑naive: {pd_ts}")
                    except Exception as e:
                        logger.error(f"Failed to localize to {exchange_tz}: {e}. Falling back to UTC.")
                        pd_ts = pd_ts.tz_localize('UTC').tz_localize(None)
                else:
                    pd_ts = pd_ts.tz_localize('UTC').tz_localize(None)
                    logger.debug(f"Naive input with no exchange_tz, assumed UTC: {pd_ts}")
            return pd_ts
        elif isinstance(ts, (int, float)):
            # Numeric – treat as Unix seconds (UTC)
            return pd.Timestamp(ts, unit='s', tz='UTC').tz_localize(None)
        elif isinstance(ts, str):
            # Parse string, then convert via the datetime branch
            dt = pd.to_datetime(ts)
            return self.to_utc_naive_timestamp(dt, exchange_tz)
        else:
            raise TypeError(f"Unsupported type: {type(ts)}")

    def ts_to_unix(self, ts: pd.Timestamp) -> float:
        """Convert pandas Timestamp to Unix seconds (float)."""
        return ts.timestamp()

    def check_csv_coverage(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_ts: Union[datetime.datetime, pd.Timestamp, float, int, str],
        end_ts: Union[datetime.datetime, pd.Timestamp, float, int, str]
    ) -> Dict[str, Union[Optional[Tuple[float, float]], List[Tuple[float, float]]]]:
        """
        Check CSV coverage and return missing data ranges as Unix timestamps.
        
        Returns:
            {
                'prepend': (start_missing_unix, end_missing_unix) or None,
                'postpend': (start_missing_unix, end_missing_unix) or None,
                'midpend': [(start_gap_unix, end_gap_unix), ...]
            }
        """
        logger.info(f"Checking CSV coverage for {symbol}/{exchange}/{interval} from {start_ts} to {end_ts}")
        
        # --- Step 0: Validate and convert inputs ---
        try:
            delta = self.interval_to_timedelta(interval)
            logger.debug(f"Interval {interval} -> timedelta {delta}")
        except ValueError as e:
            logger.error(f"Invalid interval: {e}")
            raise
        
        # Convert start_ts and end_ts to UTC-naive pandas Timestamps for internal comparison
        try:
            start = self.to_utc_naive_timestamp(start_ts)
            end = self.to_utc_naive_timestamp(end_ts)
            if start >= end:
                raise ValueError(f"start_ts ({start}) must be before end_ts ({end})")
            logger.debug(f"Normalized start={start}, end={end}")
        except Exception as e:
            logger.error(f"Invalid start/end timestamps: {e}")
            raise
        
        # --- Step 1: Build file path and read CSV ---
        filepath = f"data/{symbol}/{exchange}/{interval}.csv"
        if not os.path.exists(filepath):
            logger.error(f"CSV file not found: {filepath}")
            raise FileNotFoundError(f"CSV not found: {filepath}")
        
        # Read raw CSV without parsing dates
        try:
            df = pd.read_csv(filepath)
            logger.info(f"Loaded CSV from {filepath}, rows={len(df)}")
        except Exception as e:
            logger.error(f"Failed to read CSV: {e}")
            raise
        
        # --- Step 2: Handle empty CSV ---
        if df.empty:
            logger.warning(f"CSV is empty: {filepath}")
            # Full range is missing as prepend (postpend/midpend irrelevant)
            prepend = (start.timestamp(), end.timestamp())
            return {
                'prepend': prepend,
                'postpend': None,
                'midpend': []
            }
        
        # --- Step 3: Parse 'timestamp' column robustly ---
        if 'timestamp' not in df.columns:
            logger.error("CSV missing 'timestamp' column")
            raise KeyError("CSV missing 'timestamp' column")
        
        # Make a copy of the raw column for inspection
        raw_ts = df['timestamp']
        logger.debug(f"Raw timestamp column sample: {raw_ts.head(3).tolist()}, dtype={raw_ts.dtype}")
        
        # Step 3a: Try to parse as numeric (seconds or milliseconds)
        parsed_series = None
        try:
            # Try converting to numeric (errors='coerce')
            numeric_vals = pd.to_numeric(raw_ts, errors='coerce')
            if numeric_vals.notna().any():
                median_val = numeric_vals.median()
                # Decide unit based on median magnitude
                # Typical Unix seconds: 1.6e9 (2020), milliseconds: 1.6e12
                if median_val > 1e11:  # 100 billion -> definitely milliseconds
                    unit = 'ms'
                    logger.debug(f"Detected unit='ms' (median={median_val:.0f})")
                else:
                    unit = 's'
                    logger.debug(f"Detected unit='s' (median={median_val:.0f})")
                parsed_series = pd.to_datetime(numeric_vals, unit=unit, utc=True)
                logger.info(f"Parsed timestamps as numeric with unit='{unit}'")
        except Exception as e:
            logger.debug(f"Numeric parsing failed: {e}")
        
        # Step 3b: If numeric failed, try string parsing
        if parsed_series is None:
            logger.debug("Falling back to string parsing of timestamps")
            parsed_series = pd.to_datetime(raw_ts, utc=True, errors='coerce')
        
        # Drop rows where timestamp conversion failed
        before_drop = len(parsed_series)
        parsed_series = parsed_series.dropna()
        if len(parsed_series) < before_drop:
            logger.warning(f"Dropped {before_drop - len(parsed_series)} rows due to invalid timestamps")
        
        # Remove timezone information (convert to naive UTC)
        parsed_series = parsed_series.dt.tz_localize(None)
        
        # Drop duplicate timestamps (keep first occurrence)
        duplicate_mask = parsed_series.duplicated(keep='first')
        if duplicate_mask.any():
            logger.warning(f"Dropping {duplicate_mask.sum()} duplicate timestamps")
            parsed_series = parsed_series[~duplicate_mask]
        
        # Assign back to DataFrame
        df['timestamp'] = parsed_series
        # Drop any rows where timestamp is NaT (should already be dropped, but safe)
        df = df.dropna(subset=['timestamp'])
        
        if df.empty:
            logger.warning("After parsing and cleaning, no valid timestamps remain")
            prepend = (start.timestamp(), end.timestamp())
            return {'prepend': prepend, 'postpend': None, 'midpend': []}
        
        logger.debug(f"Valid timestamps count: {len(df)}")
        
        # --- Step 4: Sort and get boundaries ---
        df = df.sort_values('timestamp').reset_index(drop=True)
        first_ts = df['timestamp'].iloc[0]
        last_ts = df['timestamp'].iloc[-1]
        logger.debug(f"CSV time range: {first_ts} -> {last_ts}")
        
        # --- Step 5: Prepend missing range ---
        prepend = None
        if first_ts > start:
            prepend = (start, first_ts)
            logger.info(f"Prepend needed: from {start} to {first_ts}")
        else:
            logger.debug("No prepend needed")
        
        # --- Step 6: Postpend missing range ---
        postpend = None
        if last_ts < end:
            postpend = (last_ts, end)
            logger.info(f"Postpend needed: from {last_ts} to {end}")
        else:
            logger.debug("No postpend needed")
        
        # --- Step 7: Detect midpend (gaps inside CSV) ---
        gaps = []
        # Epsilon for floating point safety (1 second)
        epsilon = datetime.timedelta(seconds=1)
        timestamps = df['timestamp'].tolist()
        
        for i in range(len(timestamps) - 1):
            curr = timestamps[i]
            nxt = timestamps[i+1]
            expected_next = curr + delta
            # If the gap is larger than delta + epsilon, there is a missing range
            if nxt > expected_next + epsilon:
                start_gap = expected_next
                end_gap = nxt - delta
                # Only include if start_gap <= end_gap (should always be true for valid gaps)
                if start_gap <= end_gap:
                    gaps.append((start_gap, end_gap))
                    logger.debug(f"Gap detected: between {curr} and {nxt}, missing from {start_gap} to {end_gap}")
        
        if gaps:
            logger.info(f"Found {len(gaps)} gap(s) inside CSV")
        else:
            logger.debug("No internal gaps detected")
        
        # --- Step 8: Convert all pd.Timestamp ranges to Unix seconds (float) ---
        def convert_range(rng: Tuple[pd.Timestamp, pd.Timestamp]) -> Tuple[float, float]:
            return (rng[0].timestamp(), rng[1].timestamp())
        
        result = {
            'prepend': convert_range(prepend) if prepend else None,
            'postpend': convert_range(postpend) if postpend else None,
            'midpend': [convert_range(g) for g in gaps]
        }
        
        logger.info(f"Coverage check complete: prepend={result['prepend']}, postpend={result['postpend']}, midpend count={len(result['midpend'])}")
        return result
    
    def _validate_dataframes(self,existing_df: pd.DataFrame, new_df: pd.DataFrame, required_cols: set) -> None:
        """Validate column consistency and basic types."""
        if new_df is None or new_df.empty:
            raise ValueError("New DataFrame is empty. Nothing to merge.")
        missing_existing = required_cols - set(existing_df.columns)
        if missing_existing and not existing_df.empty:
            raise ValueError(f"Existing CSV missing columns: {missing_existing}")
        missing_new = required_cols - set(new_df.columns)
        if missing_new:
            raise ValueError(f"New data missing columns: {missing_new}")
        # Ensure timestamp is numeric
        new_df['timestamp'] = pd.to_numeric(new_df['timestamp'], errors='coerce')
        if new_df['timestamp'].isnull().any():
            raise ValueError("New data contains invalid timestamps (non-numeric).")
        # Drop duplicate timestamps within new data
        before = len(new_df)
        new_df = new_df.drop_duplicates(subset=['timestamp'], keep='first').copy()
        if len(new_df) < before:
            logger.warning(f"Dropped {before - len(new_df)} duplicate timestamps within new data (kept first).")
        # Ensure existing is sorted (if not empty)
        if not existing_df.empty and not existing_df['timestamp'].is_monotonic_increasing:
            logger.warning("Existing DataFrame not sorted by timestamp. Sorting now.")
            existing_df = existing_df.sort_values('timestamp').reset_index(drop=True)


    def merge_prepend(self, existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
        """
        Insert new_df at the beginning (prepend) of existing_df.
        Returns a new DataFrame with prepended data.
        """
        logger.info("Merging with PREPEND mode: adding data at the top.")
        required_cols = set(existing_df.columns) if not existing_df.empty else set(new_df.columns)
        self._validate_dataframes(existing_df, new_df, required_cols)

        # Ensure new_df timestamps are smaller than any in existing
        if not existing_df.empty and new_df['timestamp'].max() >= existing_df['timestamp'].min():
            logger.warning("Prepended data has timestamps not all smaller than existing first timestamp. Sorting will fix order anyway.")
        result = pd.concat([new_df, existing_df], ignore_index=True)
        result = result.sort_values('timestamp').reset_index(drop=True)
        logger.info(f"Prepend complete. New total rows: {len(result)}")
        return result


    def merge_postpend(self, existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
        """
        Append new_df at the end (postpend) of existing_df.
        Returns a new DataFrame with appended data.
        """
        logger.info("Merging with POSTPEND mode: adding data at the bottom.")
        required_cols = set(existing_df.columns) if not existing_df.empty else set(new_df.columns)
        self._validate_dataframes(existing_df, new_df, required_cols)

        if not existing_df.empty and new_df['timestamp'].min() <= existing_df['timestamp'].max():
            logger.warning("Appended data has timestamps overlapping existing. Sorting will deduplicate.")
        result = pd.concat([existing_df, new_df], ignore_index=True)
        result = result.sort_values('timestamp').reset_index(drop=True)
        logger.info(f"Postpend complete. New total rows: {len(result)}")
        return result


    def merge_midpend(self, existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
        """
        Insert new_df into the middle of existing_df based on timestamps.
        Uses binary search to find insertion index.
        Returns a new DataFrame with data inserted at the correct position.
        """
        logger.info("Merging with MIDPEND mode: inserting data between existing rows.")
        required_cols = set(existing_df.columns) if not existing_df.empty else set(new_df.columns)
        self._validate_dataframes(existing_df, new_df, required_cols)

        if existing_df.empty:
            logger.warning("Existing DataFrame empty. Treating as prepend.")
            return self.merge_prepend(existing_df, new_df)

        # Ensure new_df is sorted
        new_df = new_df.sort_values('timestamp').reset_index(drop=True)
        first_new_ts = new_df['timestamp'].iloc[0]
        last_new_ts = new_df['timestamp'].iloc[-1]

        # Binary search to find insertion index (position where first new timestamp should go)
        # Use side='left' to insert before any existing timestamp that equals first_new_ts (shouldn't happen)
        pos = np.searchsorted(existing_df['timestamp'], first_new_ts, side='left')
        logger.debug(f"First new timestamp = {first_new_ts}, insertion index = {pos}")

        # Optional: verify that the new data fits entirely in the gap (not overlapping existing)
        if pos > 0:
            left_ts = existing_df['timestamp'].iloc[pos-1]
            if left_ts >= first_new_ts:
                logger.warning(f"New data start timestamp {first_new_ts} is not greater than previous existing timestamp {left_ts}. Possible overlap.")
        if pos < len(existing_df):
            right_ts = existing_df['timestamp'].iloc[pos]
            if right_ts <= last_new_ts:
                logger.warning(f"New data end timestamp {last_new_ts} is not less than next existing timestamp {right_ts}. Possible overlap.")

        # Concatenate: rows before pos, then new data, then rows from pos onward
        result = pd.concat([existing_df.iloc[:pos], new_df, existing_df.iloc[pos:]], ignore_index=True)
        # Final safety sort (should be unnecessary, but ensures correctness)
        result = result.sort_values('timestamp').reset_index(drop=True)
        logger.info(f"Midpend insertion complete. New total rows: {len(result)}")
        return result

    def merge_new_data_into_csv(
        csv_path: str,
        new_data_df: pd.DataFrame,
        sort_by: str = 'timestamp',
        inplace: bool = True,
        atomic_write: bool = True
    ) -> Union[pd.DataFrame, bool]:
        """
        Merge newly downloaded data into an existing CSV file.
        Automatically handles prepend, postpend, and midpend gaps via timestamp sorting.

        Args:
            csv_path (str): Full path to the existing CSV file.
            new_data_df (pd.DataFrame): DataFrame with new data (must have the same columns as CSV).
            sort_by (str): Column name to sort by (default 'timestamp').
            inplace (bool): If True, overwrite the CSV and return True on success.
                        If False, return the merged DataFrame without writing.
            atomic_write (bool): If True, write to a temp file then rename (safer).

        Returns:
            - If inplace=True: bool (True on success).
            - If inplace=False: pd.DataFrame (merged data).

        Raises:
            FileNotFoundError: If CSV does not exist and no new data provided.
            ValueError: If column mismatch or empty new data.
            Exception: For any write/sort failure.
        """
        logger.info(f"Starting merge operation for CSV: {csv_path}")

        # Step 0: Validate new_data_df
        if new_data_df is None or new_data_df.empty:
            logger.warning("new_data_df is empty. Nothing to merge.")
            if inplace:
                return True
            else:
                return pd.DataFrame()

        # Define required columns (as per DataProcessor output)
        required_cols = {'timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'candle_type'}
        missing_in_new = required_cols - set(new_data_df.columns)
        if missing_in_new:
            logger.error(f"New data missing required columns: {missing_in_new}")
            raise ValueError(f"New data missing columns: {missing_in_new}")

        # Step 1: Read existing CSV (if exists)
        if os.path.exists(csv_path):
            try:
                # Read with specific dtypes for performance and correctness
                existing_df = pd.read_csv(
                    csv_path,
                    dtype={
                        'timestamp': 'int64',
                        'open': 'float64',
                        'high': 'float64',
                        'low': 'float64',
                        'close': 'float64',
                        'volume': 'float64',
                        'candle_type': 'category'
                    },
                    parse_dates=['datetime']  # datetime column as datetime object (naive)
                )
                logger.info(f"Read existing CSV: {len(existing_df)} rows.")
            except Exception as e:
                logger.error(f"Failed to read existing CSV: {e}")
                raise
        else:
            logger.warning(f"CSV file does not exist: {csv_path}. New data will become the whole file.")
            existing_df = pd.DataFrame(columns=required_cols)

        # Step 2: Validate column consistency
        missing_in_existing = required_cols - set(existing_df.columns)
        if missing_in_existing and not existing_df.empty:
            logger.error(f"Existing CSV missing columns: {missing_in_existing}")
            raise ValueError(f"Existing CSV missing columns: {missing_in_existing}")
        # Align column order (new data may have extra columns; we drop them)
        new_data_df = new_data_df[list(required_cols)]

        # Step 3: Clean new data
        # Ensure timestamp is integer
        new_data_df['timestamp'] = pd.to_numeric(new_data_df['timestamp'], errors='coerce')
        new_data_df = new_data_df.dropna(subset=['timestamp'])
        # Remove duplicate timestamps within new data
        before = len(new_data_df)
        new_data_df = new_data_df.drop_duplicates(subset=['timestamp'], keep='first')
        after = len(new_data_df)
        if after < before:
            logger.warning(f"Removed {before - after} duplicate timestamps from new data (kept first).")

        # Convert datetime column to consistent type (string or datetime) – keep as is
        # We'll sort by timestamp, so datetime column can be any type.

        logger.info(f"New data cleaned: {len(new_data_df)} rows.")

        # Step 4: Concatenate
        combined = pd.concat([existing_df, new_data_df], ignore_index=True, sort=False)
        logger.info(f"Concatenated DataFrame has {len(combined)} rows before deduplication.")

        # Step 5: Remove duplicates across entire dataset (by timestamp)
        before_dedup = len(combined)
        combined = combined.drop_duplicates(subset=['timestamp'], keep='first')
        after_dedup = len(combined)
        if after_dedup < before_dedup:
            logger.warning(f"Removed {before_dedup - after_dedup} duplicate timestamp rows (overlap between existing and new).")

        # Step 6: Sort by timestamp
        combined = combined.sort_values(sort_by).reset_index(drop=True)
        logger.info(f"Sorted merged DataFrame. Final row count: {len(combined)}.")

        # Optional validation: check monotonic increasing
        if not combined['timestamp'].is_monotonic_increasing:
            logger.error("Sorted DataFrame is not monotonic! This should not happen.")
            raise ValueError("Sorting failed to produce monotonic timestamps.")

        # Step 7: Write back or return
        if inplace:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(csv_path), exist_ok=True)
                if atomic_write:
                    temp_path = csv_path + ".tmp"
                    combined.to_csv(temp_path, index=False)
                    os.replace(temp_path, csv_path)  # atomic on Unix, also works on Windows
                    logger.info(f"Atomic write successful: {csv_path}")
                else:
                    combined.to_csv(csv_path, index=False)
                    logger.info(f"Wrote merged data directly to {csv_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to write CSV: {e}")
                raise
        else:
            return combined

    def load_csv_to_df(self, filepath) -> pd.DataFrame:
        if not os.path.exists(filepath):
            logger.error(f"CSV file not found: {filepath}")
            raise FileNotFoundError(f"CSV not found: {filepath}")
        try:
            df = pd.read_csv(filepath)
            logger.info(f"Loaded CSV from {filepath}, rows={len(df)}")
            return df
        except Exception as e:
            logger.error(f"Failed to read CSV: {e}")
            raise