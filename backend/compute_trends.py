"""Fetch historical prices from Twelve Data and compute 7-day/30-day moving averages +
trend classification, writing straight into the market_trends table.

Was a two-stage pipeline on AWS: a script landed raw JSON in S3, an S3 event triggered a
Lambda that launched an EMR/Spark cluster to compute this. Folded into one script run on a
schedule (see .github/workflows/compute-trends.yml) since there's no cluster to launch
anymore — at this data volume (a handful of tickers, ~90 daily rows each) pandas does the
same rolling-window computation Spark did, just without the orchestration.

Usage:
    DATABASE_URL=... MARKET_API_KEY=... python compute_trends.py [TICKER ...]
"""

import os
import sys

import pandas as pd
import requests
from sqlalchemy import create_engine, text

DEFAULT_TICKERS = ["AAPL", "MSFT", "BTC-USD"]


def _twelvedata_symbol(ticker):
    return ticker.replace("-", "/")


def fetch_history(ticker, api_key, outputsize=90):
    response = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": _twelvedata_symbol(ticker),
            "interval": "1day",
            "outputsize": outputsize,
            "apikey": api_key,
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if "values" not in data:
        raise RuntimeError(data.get("message", "unexpected response"))
    return data["values"]


def compute_moving_averages(ticker, values):
    df = pd.DataFrame(values)
    df["date"] = pd.to_datetime(df["datetime"]).dt.date
    df["close"] = df["close"].astype(float)
    df = df.drop_duplicates("date").sort_values("date")

    df["ma_7d"] = df["close"].rolling(window=7, min_periods=1).mean()
    df["ma_30d"] = df["close"].rolling(window=30, min_periods=1).mean()
    df["trend"] = df.apply(lambda r: "up" if r["close"] >= r["ma_30d"] else "down", axis=1)
    df["ticker"] = ticker

    return df[["ticker", "date", "close", "ma_7d", "ma_30d", "trend"]]


def upsert(engine, df):
    with engine.begin() as conn:
        for row in df.itertuples(index=False):
            conn.execute(
                text(
                    """
                    INSERT INTO market_trends (ticker, date, close, ma_7d, ma_30d, trend)
                    VALUES (:ticker, :date, :close, :ma_7d, :ma_30d, :trend)
                    ON CONFLICT (ticker, date) DO UPDATE SET
                        close = EXCLUDED.close, ma_7d = EXCLUDED.ma_7d,
                        ma_30d = EXCLUDED.ma_30d, trend = EXCLUDED.trend
                    """
                ),
                {
                    "ticker": row.ticker,
                    "date": row.date,
                    "close": row.close,
                    "ma_7d": row.ma_7d,
                    "ma_30d": row.ma_30d,
                    "trend": row.trend,
                },
            )


def main():
    database_url = os.environ.get("DATABASE_URL")
    api_key = os.environ.get("MARKET_API_KEY")
    if not database_url or not api_key:
        print("DATABASE_URL and MARKET_API_KEY must be set")
        sys.exit(1)

    tickers = sys.argv[1:] or DEFAULT_TICKERS
    engine = create_engine(database_url)

    for ticker in tickers:
        try:
            values = fetch_history(ticker, api_key)
        except Exception as exc:
            print(f"skip {ticker}: {exc}")
            continue
        df = compute_moving_averages(ticker, values)
        upsert(engine, df)
        print(f"wrote {len(df)} rows for {ticker}")


if __name__ == "__main__":
    main()
