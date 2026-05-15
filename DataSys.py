from pdb import run
from RequestHanlder import ReqsHandler 
from CsvOperations import csvOperations
from DataFetcher import (
    fetch_groww_historical_raw,
    fetch_yfinance_data)
from DataProcessor import YFinanceDataProcessor,GrowwDataProcessor   
from config import FETCHING_ENGINES
import logging 
from config import *
import datetime
import time
import os
import pandas as pd

rh = ReqsHandler()
yf_dp = YFinanceDataProcessor()
groww_dp = GrowwDataProcessor()
csv_ops = csvOperations(file_path=None) 
fetch = fetch_groww_historical_raw
fetch_yf = fetch_yfinance_data
dt2ts = rh.datetime_to_timestamp
ts2dt = rh.timestamp_to_datetime

# Ceate Logs directory and file if not exists
if not os.path.exists("logs/Data_Sys"):
    os.makedirs("logs/Data_Sys") 
if not os.path.exists(f"logs/Data_Sys/{datetime.datetime.today().strftime('%Y-%m-%d')}.log"):
    open(f"logs/Data_Sys/{datetime.datetime.today().strftime('%Y-%m-%d')}.log", 'a').close()

# 1. Create a custom logger
logger = logging.getLogger('my_app')
logger.setLevel(logging.DEBUG)  # Set the lowest level to capture all events

# 2. Create handlers
c_handler = logging.StreamHandler()        # Console handler
f_handler = logging.FileHandler(f"logs/Data_Sys/{datetime.datetime.today().strftime('%Y-%m-%d')}.log") # File handler
c_handler.setLevel(logging.WARNING)           # Only show INFO+ in terminal
f_handler.setLevel(logging.DEBUG)          # Save everything to the file

# 3. Create formatters and add them to handlers
format_str = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
c_handler.setFormatter(format_str)
f_handler.setFormatter(format_str)

# 4. Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)
fetch_plan = []

class DataSys:
    def __init__(self, ):
        pass
        


    def handling(self, Symbol :str,Exchange :str,Interval :str,start_ts,end_ts,csv_validation : bool = True):
        if csv_validation == True:
            valid_csv = rh.validate_or_create_ohlcv_csv(Symbol, Exchange, Interval)
            
            if valid_csv == "created":
                logger.info(f"CSV file for {Symbol} on {Exchange} at {Interval} was created.")
            elif valid_csv == "recreated_due_to_read_error":
                logger.warning(f"CSV file for {Symbol} on {Exchange} at {Interval} was recreated due to a read error.")
            elif valid_csv == "recreated_due_to_invalid_headers":
                logger.warning(f"CSV file for {Symbol} on {Exchange} at {Interval} was recreated due to invalid headers.")
            else:
                logger.info(f"CSV file for {Symbol} on {Exchange} at {Interval} is valid and ready for use.")
                
        try:
            limit_check = rh.is_request_within_limit(start_ts, end_ts, Interval)
            if limit_check == "Chunking_not_needed":
                logger.info(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} is within the allowed limit. No chunking needed.")
                logger.info(f"""Fetching Plan :
                [
                    Symbol: {Symbol}
                    Exchange: {Exchange}
                    Interval: {Interval}
                    Start Date: {ts2dt(start_ts)}
                    Start Timeframe: {start_ts}
                    End Date: {ts2dt(end_ts)}
                    End Timeframe: {end_ts}
                    ]
                """)
                return {
                    "symbol": Symbol,
                    "exchange": Exchange, 
                    "interval": Interval,
                    "range": {
                        "start_ts": start_ts,
                        "end_ts": end_ts
                    },
                    "chunking_needed": False
                }
            
            elif limit_check == "Chunking_needed":
                logger.info(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} exceeds the allowed limit. chunking the requests.")
                chunks = rh.create_fetch_plan(Symbol, Exchange, Interval, start_ts, end_ts)
                plan = rh.parse_fetch_plan(chunks)
                logger.info(f"""Fetching Plan :
                [
                    Symbol: {plan['symbol']}
                    Exchange: {plan['exchange']}
                    Interval: {plan['interval']}
                    Chunks : \n{'\n'.join(str(chunk) for chunk in plan['chunks'])}
                ]
                """)
                return{
                    "symbol": plan['symbol'],
                    "exchange": plan['exchange'],
                    "interval": plan['interval'],
                    "chunks": plan['chunks'],
                    "chunking_needed": True
                }
        except ValueError as e:
            if e == f"Unsupported interval: {Interval}":
                logger.error(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} failed due to unsupported interval.")
            elif e == "end_ts must be greater than start_ts":
                logger.error(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} failed because end timestamp is not greater than start timestamp.")
            elif str(e).startswith(f"{Interval} data only available since"):
                logger.error(f"Request for {Symbol} on {Exchange} at {Interval} from {start_ts} to {end_ts} on {datetime.datetime.now()} failed because requested data is not available for the entire requested range.")
                
            else:
                logger.error(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} failed due to an unexpected error: {str(e)}")

    def groww_chunk_to_df(self, candles):
        columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(candles, columns=columns)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        return df

    def data_fetching_and_processing(self, fetch_plan):
        if FETCHING_ENGINES == "Groww":
            if fetch_plan["chunking_needed"] == False:
                symbol = fetch_plan["symbol"]
                exchange = fetch_plan["exchange"]
                interval = fetch_plan["interval"]
                start_ts = fetch_plan["range"]["start_ts"]
                end_ts = fetch_plan["range"]["end_ts"]

                data =fetch(symbol=symbol, exchange=exchange, interval=interval, start_ts=start_ts, end_ts=end_ts, token="your_token_here")
                processed_dfs = groww_dp.process(pd.DataFrame(data["candles"]), exchange, interval)
                return processed_dfs
            
            elif fetch_plan["chunking_needed"] == True:
                symbol = fetch_plan["symbol"]
                exchange = fetch_plan["exchange"]
                interval = fetch_plan["interval"]
                chunks = fetch_plan["chunks"]
                all_chunks = []
                for chunk in chunks:
                    start_ts = chunk[1]
                    end_ts = chunk[3]
                    data =fetch(symbol=symbol, exchange=exchange, interval=interval, start_ts=start_ts, end_ts=end_ts, token="your_token_here")
                    time.sleep(0.5)
                    df_chunk = self.groww_chunk_to_df(data["candles"])
                    all_chunks.append(df_chunk)
                processed_dfs = groww_dp.process(all_chunks, exchange, interval)
                return processed_dfs
                
        elif FETCHING_ENGINES == "yFinance":
            if fetch_plan["chunking_needed"] == False:
                symbol = fetch_plan["symbol"]
                exchange = fetch_plan["exchange"]
                interval = fetch_plan["interval"]
                start_ts = fetch_plan["range"]["start_ts"]
                end_ts = fetch_plan["range"]["end_ts"]
                data =fetch_yf(symbol=symbol, exchange=exchange, interval=interval, start_ts=start_ts, end_ts=end_ts)
                processed_dfs = yf_dp.process(data, exchange, interval)
                return processed_dfs
            
            elif fetch_plan["chunking_needed"] == True:
                symbol = fetch_plan["symbol"]
                exchange = fetch_plan["exchange"]
                interval = fetch_plan["interval"]
                chunks = fetch_plan["chunks"]
                all_chunks = []
                for chunk in chunks:
                    start_ts = chunk[1]
                    end_ts = chunk[3]
                    data =fetch_yf(symbol=symbol, exchange=exchange, interval=interval, start_ts=start_ts, end_ts=end_ts)
                    all_chunks.append(data)
                    time.sleep(0.5)

                if all_chunks:
                    data = pd.concat(all_chunks, ignore_index=True)
                    data = data[~data.index.duplicated(keep='first')]
                    data = data.sort_index()
                    processed_dfs = yf_dp.process(data, exchange, interval)
                    return processed_dfs

                else:
                    final_df = pd.DataFrame()
                    return final_df 
                    
    def data_to_csv(self, df, Symbol, Exchange, Interval):
        csv_ops.save_to_csv(df, Symbol, Exchange, Interval)
    
    def run(self, Symbol, Exchange, Interval,start_dt, end_dt):
        start_ts = dt2ts(start_dt)
        end_ts = dt2ts(end_dt)
        filepath = f"data/{Symbol}/{Exchange}/{Interval}.csv"
        valid = csv_ops.is_csv_valid(filepath)
        if valid == "CSV file does not exist or is empty" or valid == "NO CSV FILE HEADERS" or valid == "MISSING REQUIRED COLUMNS" or valid == "CSV CAN BE CORRUPTED OR UNREADABLE" or valid == "CSV FILE HAS NO DATA":
            fetch_plan = self.handling(Symbol, Exchange, Interval,start_ts, end_ts, csv_validation=True)
            if fetch_plan is not None:
                processed_dfs = self.data_fetching_and_processing(fetch_plan)
                self.data_to_csv(processed_dfs, Symbol, Exchange, Interval)
        if valid == "INVALID TIMESTAMP VALUES" or valid == "NON-NUMERIC VALUES FOUND" or valid == "ALL VALUES IN COLUMN ARE NULL":
            fetch_plan = self.handling(Symbol, Exchange, Interval,start_ts, end_ts, csv_validation=False)
            if fetch_plan is not None:
                processed_dfs = self.data_fetching_and_processing(fetch_plan)
                self.data_to_csv(processed_dfs, Symbol, Exchange, Interval)

        if valid == "CSV IS VALID":
            logger.info(f"CSV file for {Symbol} on {Exchange} at {Interval} already has valid data. No fetching needed.")
            csv_retention_plan = csv_ops.check_csv_coverage(Symbol, Exchange, Interval, start_ts, end_ts)
            if csv_retention_plan is not None:
                prepend_start = csv_retention_plan['prepend'][0]
                prepend_end = csv_retention_plan['prepend'][1]
                prepend = (prepend_start, prepend_end)
                postpend_start = csv_retention_plan['postpend'][0]
                postpend_end = csv_retention_plan['postpend'][1]
                postpend = (postpend_start, postpend_end)
                midpend = []
                if csv_retention_plan['midpend']:   
                    for mid in csv_retention_plan['midpend']:
                        mid_start = mid[0]
                        mid_end = mid[1]
                        midpend.append((mid_start, mid_end))
                if prepend is not None:
                    print("I am in prepend")
                    print(ts2dt(prepend[0]), ts2dt(prepend[1]))
                    fetch_plan_prepend = self.handling(Symbol, Exchange, Interval, prepend[0],prepend[1], csv_validation=False)
                    if fetch_plan_prepend is not None:
                        processed_dfs_prepend = self.data_fetching_and_processing(fetch_plan_prepend)
                        csv_ops.merge_prepend(existing_df=csv_ops.load_csv_to_df(filepath), new_df=processed_dfs_prepend).to_csv(filepath, index=False)
                if postpend is not None:
                    fetch_plan_postpend = self.handling(Symbol, Exchange, Interval, postpend[0], postpend[1], csv_validation=False)
                    print("I am in postpend")
                    print(ts2dt(postpend[0]), ts2dt(postpend[1]))
                    if fetch_plan_postpend is not None:
                        processed_dfs_postpend = self.data_fetching_and_processing(fetch_plan_postpend)
                        csv_ops.merge_postpend(existing_df=csv_ops.load_csv_to_df(filepath), new_df=processed_dfs_postpend).to_csv(filepath, index=False)
                if midpend is not None:
                    for mid in midpend:
                        fetch_plan_midpend = self.handling(Symbol, Exchange, Interval, mid[0], mid[1], csv_validation=False)
                        if fetch_plan_midpend is not None:
                            processed_dfs_midpend = self.data_fetching_and_processing(fetch_plan_midpend)
                            csv_ops.merge_midpend(existing_df=csv_ops.load_csv_to_df(filepath), new_df=processed_dfs_midpend).to_csv(filepath, index=False)

if __name__ == "__main__":
    handler = DataSys()
    handler.run(Symbol="RELIANCE", Exchange="NSE", Interval="5m",start_dt="2026-05-07 00:00:00", end_dt="2026-05-13 23:59:59")