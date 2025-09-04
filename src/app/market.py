import time
import yfinance as yf
import logging
from typing import Tuple

logger = logging.getLogger("stock-alerts")

def get_open_and_last(ticker: str) -> Tuple[float, float]:
    for interval in ("1m", "5m", "15m"):
        for attempt in range(2):
            df = yf.Ticker(ticker).history(period="1d", interval=interval, auto_adjust=False)
            if not df.empty:
                open_today = float(df.iloc[0]["Open"])
                last_price = float(df.iloc[-1]["Close"])
                logger.debug("Intraday %s: %s open=%.4f last=%.4f",
                             ticker, interval, open_today, last_price)
                return open_today, last_price
            logger.debug("Empty intraday data (%s, %s), retry %d",
                         ticker, interval, attempt + 1)
            time.sleep(0.4)

    df = yf.Ticker(ticker).history(period="1d", interval="1d", auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"No data available for {ticker}")
    row = df.iloc[-1]
    open_today, last_price = float(row["Open"]), float(row["Close"])
    logger.debug("Fallback daily %s: open=%.4f last=%.4f",
                 ticker, open_today, last_price)
    return open_today, last_price

# import time
# import yfinance as yf
# import logging
# from typing import Tuple

# logger = logging.getLogger("stock-alerts")


# def get_open_and_last(ticker: str) -> Tuple[float, float]:
    """
    Retrieve today's opening price and the latest available price for a ticker.

    Strategy:
      1. Try intraday data with finer intervals ("1m", "5m", "15m").
         - Use the very first "Open" of the day.
         - Use the most recent "Close" (last candle).
         - Retry once per interval in case Yahoo delivers empty DataFrames.
      2. If no intraday data is available (e.g., market closed),
         fall back to daily interval ("1d").
    """
    # : Loop over intraday intervals ("1m", "5m", "15m")
    # for interval in ("1m", "5m", "15m"):

        # : For each interval, attempt up to two retries
        # for attempt in range(2):
        #     df = yf.Ticker(ticker).history(
        #         period="1d", interval=interval, auto_adjust=False
        #     )
        #     if not df.empty:
        #         open_today = float(df.iloc[0]["Open"])
        #         last_price = float(df.iloc[-1]["Close"])
        #         logger.debug(
        #             "Intraday %s: interval=%s open=%.4f last=%.4f",
        #             ticker, interval, open_today, last_price,
        #         )
        #         return open_today, last_price
        #     logger.debug(
        #         "Empty intraday data (%s, %s), retry %d",
        #         ticker, interval, attempt + 1,
        #     )
        #     time.sleep(0.4)

    # : Fallback to daily data ("1d" interval) and raise RuntimeError if empty
    # df = yf.Ticker(ticker).history(period="1d", interval="1d", auto_adjust=False)
    # if df.empty:
    #     raise RuntimeError(f"No data available for {ticker}")

    # : Extract open and close from the last row, log them, and return
    # row = df.iloc[-1]
    # open_today, last_price = float(row["Open"]), float(row["Close"])
    # logger.debug(
    #     "Fallback daily data %s: open=%.4f last=%.4f",
    #     ticker, open_today, last_price,
    # )
    # return open_today, last_price

    #pass  # Remove once implemented
