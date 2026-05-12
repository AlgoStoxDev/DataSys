from RequestHanlder import ReqsHandler 
import logging 
from config import *
import datetime
import os

rh = ReqsHandler()
dt2ts = rh.datetime_to_timestamp
ts2dt = rh.timestamp_to_datetime

# Ceate Logs directory and file if not exists
if not os.path.exists("logs"):
    os.makedirs("logs") 
if not os.path.exists(f"logs/{datetime.datetime.today().strftime('%Y-%m-%d')}.log"):
    open(f"logs/{datetime.datetime.today().strftime('%Y-%m-%d')}.log", 'a').close()

# 1. Create a custom logger
logger = logging.getLogger('my_app')
logger.setLevel(logging.DEBUG)  # Set the lowest level to capture all events

# 2. Create handlers
c_handler = logging.StreamHandler()        # Console handler
f_handler = logging.FileHandler(f"logs/{datetime.datetime.today().strftime('%Y-%m-%d')}.log") # File handler
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
    def __init__(self, start_date :str, end_date :str):
        self.start_ts = dt2ts(start_date)
        self.end_ts = dt2ts(end_date)
        


    def handling(self, Symbol :str,Exchange :str,Interval :str):
        valid_csv = rh.validate_or_create_ohlcv_csv(Symbol, Exchange, Interval)
        
        if valid_csv == "created":
            logger.info(f"CSV file for {Symbol} on {Exchange} at {Interval} was created.")
        elif valid_csv == "recreated_due_to_read_error":
            logger.warning(f"CSV file for {Symbol} on {Exchange} at {Interval} was recreated due to a read error.")
        elif valid_csv == "recreated_due_to_invalid_headers":
            logger.warning(f"CSV file for {Symbol} on {Exchange} at {Interval} was recreated due to invalid headers.")
        else:
            logger.info(f"CSV file for {Symbol} on {Exchange} at {Interval} is valid and ready for use.")
        
        # Check if the data requested is present in the CSV file
        

        # if csv file dosent have data then fetch it from groww 
        try:
            limit_check = rh.is_request_within_limit(self.start_ts, self.end_ts, Interval)
            if limit_check == "Chunking_not_needed":
                logger.info(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} is within the allowed limit. No chunking needed.")
                logger.info(f"""Fetching Plan :
                [
                    Symbol: {Symbol}
                    Exchange: {Exchange}
                    Interval: {Interval}
                    Start Date: {ts2dt(self.start_ts)}
                    Start Timeframe: {self.start_ts}
                    End Date: {ts2dt(self.end_ts)}
                    End Timeframe: {self.end_ts}
                    ]
                """)
                return {
                    "symbol": Symbol,
                    "exchange": Exchange, 
                    "interval": Interval,
                    "range": [self.start_ts, self.end_ts],
                    "chunking_needed": False
                }
            
            elif limit_check == "Chunking_needed":
                logger.info(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} exceeds the allowed limit. chunking the requests.")
                chunks = rh.create_fetch_plan(Symbol, Exchange, Interval, self.start_ts, self.end_ts)
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
                logger.error(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} failed because requested data is not available for the entire requested range.")
            else:
                logger.error(f"Request for {Symbol} on {Exchange} at {Interval} on {datetime.datetime.now()} failed due to an unexpected error: {str(e)}")



data = DataSys(
    start_date="2023-01-01 00:00:00",
    end_date="2026-01-02 00:00:00"
)
print(data.handling(Symbol="TATA", Exchange="NSE", Interval="1d"))
if __name__ == "__main__":
    data.handling(Symbol="TATA", Exchange="NSE", Interval="1d")