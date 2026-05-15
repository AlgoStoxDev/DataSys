# ReqsHandler.py

import csv
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from config import (
    DEFAULT_DT_FORMAT,
    DEFAULT_TIMEZONE,
    REQUIRED_OHLCV_HEADERS,
    HISTORICAL_REQUEST_LIMITS,
    HISTORICAL_DATA_AVAILABILITY,
    FETCHING_ENGINES,
    YF_HISTORICAL_DATA_AVAILABILITY,
    YF_HISTORICAL_REQUEST_LIMITS
)

if FETCHING_ENGINES == "Groww":
    pass
elif FETCHING_ENGINES == "yFinance":
    HISTORICAL_REQUEST_LIMITS = YF_HISTORICAL_REQUEST_LIMITS
    HISTORICAL_DATA_AVAILABILITY = YF_HISTORICAL_DATA_AVAILABILITY



class ReqsHandler:
    def __init__(self, timezone=DEFAULT_TIMEZONE, dt_format=DEFAULT_DT_FORMAT):
        self.timezone = timezone
        self.dt_format = dt_format
        self.required_headers = REQUIRED_OHLCV_HEADERS
        self.historical_request_limits = HISTORICAL_REQUEST_LIMITS
        self.historical_data_availability = HISTORICAL_DATA_AVAILABILITY

    def datetime_to_timestamp(self, dt_string, timezone=None, fmt=None):
        timezone = timezone or self.timezone
        fmt = fmt or self.dt_format

        tz = ZoneInfo(timezone)
        dt = datetime.strptime(dt_string, fmt)
        dt = dt.replace(tzinfo=tz)
        return int(dt.timestamp())

    def timestamp_to_datetime(self, timestamp, timezone=None, fmt=None):
        timezone = timezone or self.timezone
        fmt = fmt or self.dt_format

        tz = ZoneInfo(timezone)
        dt = datetime.fromtimestamp(int(timestamp), tz)
        return dt.strftime(fmt)

    def validate_or_create_ohlcv_csv(self, symbol, exchange, interval):
        file_path = f"data/{symbol}/{exchange}/{interval}.csv"
        directory = os.path.dirname(file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        if not os.path.exists(file_path):
            with open(file_path, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(self.required_headers)
                return "created"

        try:
            with open(file_path, mode="r", newline="") as file:
                reader = csv.reader(file)
                existing_headers = next(reader)
                existing_headers = [h.strip().lower() for h in existing_headers]
        except Exception:
            try:
                os.remove(file_path)
            except FileNotFoundError:
                pass

            with open(file_path, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(self.required_headers)
            return "recreated_due_to_read_error"

        if existing_headers != self.required_headers:
            try:
                os.remove(file_path)
            except FileNotFoundError:
                pass

            with open(file_path, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(self.required_headers)
            return "recreated_due_to_invalid_headers"


    def is_request_within_limit(self, start_ts, end_ts, interval):
        if FETCHING_ENGINES == "Groww":
            historical_request_limits = HISTORICAL_REQUEST_LIMITS
            historical_data_availability = HISTORICAL_DATA_AVAILABILITY
            if interval not in self.historical_request_limits:
                raise ValueError(f"Unsupported interval: {interval}")

            if end_ts <= start_ts:
                raise ValueError("end_ts must be greater than start_ts")
            
            
            requested_range = end_ts - start_ts
            

            available_history = historical_data_availability.get(interval, float("inf"))
            if available_history != float("inf"):
                current_ts = int(datetime.now().timestamp())
                oldest_allowed_ts = current_ts - available_history
                if start_ts < oldest_allowed_ts:
                    oldest_allowed_dt = self.timestamp_to_datetime(oldest_allowed_ts)
                    raise ValueError(f"{interval} data only available since {oldest_allowed_dt}")
            allowed_request_range = historical_request_limits[interval]

            if requested_range > allowed_request_range:
                return "Chunking_needed"
            return "Chunking_not_needed"
        elif FETCHING_ENGINES == "yFinance":
            historical_request_limits = YF_HISTORICAL_REQUEST_LIMITS
            historical_data_availability = YF_HISTORICAL_DATA_AVAILABILITY
            if interval not in self.historical_request_limits:
                raise ValueError(f"Unsupported interval: {interval}")

            if end_ts <= start_ts:
                raise ValueError("end_ts must be greater than start_ts")
            
            
            requested_range = end_ts - start_ts

            available_history = historical_data_availability.get(interval, float("inf"))
            if available_history != float("inf"):
                current_ts = int(datetime.now().timestamp())
                oldest_allowed_ts = current_ts - available_history
                if start_ts < oldest_allowed_ts:
                    oldest_allowed_dt = self.timestamp_to_datetime(oldest_allowed_ts)
                    raise ValueError(f"{interval} data only available since {oldest_allowed_dt}")
            allowed_request_range = historical_request_limits[interval]

            if requested_range > allowed_request_range:
                return "Chunking_needed"   
            return "Chunking_not_needed"

    def create_fetch_plan(self, symbol, exchange, interval, start_ts, end_ts):
        
        request_limit = self.historical_request_limits[interval]
        total_range = end_ts - start_ts

        if total_range <= request_limit:
            return {
                "symbol": symbol,
                "exchange": exchange,
                "interval": interval,
                "chunking_needed": False,
                "range": {
                    "start_dt": self.timestamp_to_datetime(start_ts),
                    "start_ts": start_ts,
                    "end_dt": self.timestamp_to_datetime(end_ts),
                    "end_ts": end_ts,
                },
            }

        ranges = []
        cursor = start_ts

        while cursor < end_ts:
            chunk_end = min(cursor + request_limit, end_ts)

            ranges.append({
                "start_dt": self.timestamp_to_datetime(cursor),
                "start_ts": cursor,
                "end_dt": self.timestamp_to_datetime(chunk_end),
                "end_ts": chunk_end,
            })

            cursor = chunk_end

        return {
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,
            "chunking_needed": True,
            "range": ranges,
        }

    def parse_fetch_plan(self, plan):
        symbol = plan.get("symbol")
        exchange = plan.get("exchange")
        interval = plan.get("interval")
        chunking_needed = plan.get("chunking_needed", False)
        raw_range = np.array(plan.get("range"))

        if raw_range is None:
            chunks_2d = np.array([])
        elif chunking_needed is False:
            raw_range = [raw_range]
            chunks_2d = []
            for chunk in raw_range:
                chunks_2d.append([
                    chunk["start_dt"],
                    chunk["start_ts"],
                    chunk["end_dt"],
                    chunk["end_ts"],
                ])
        else:
            chunks_2d = []
            for chunk in raw_range:
                chunks_2d.append([
                    chunk["start_dt"],
                    chunk["start_ts"],
                    chunk["end_dt"],
                    chunk["end_ts"],
                ])
            
                
        return {
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,
            "chunking_needed": chunking_needed,
            "chunks": chunks_2d,
        }
