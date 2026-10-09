"""Pull historical daily price data from Twelve Data and land it in the raw-data S3 bucket.
This is what Day 6's EMR job reads from.

Usage:
    MARKET_API_KEY=... MARKET_DATA_BUCKET=... python fetch_historical_data.py [SYMBOL ...]

Defaults to the symbols already used in seed.py's demo portfolio if none are given.
"""

import json
import os
import sys
from datetime import datetime, timezone

import boto3
import requests

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "BTC-USD"]


def _twelvedata_symbol(symbol):
    return symbol.replace("-", "/")


def fetch_history(symbol, api_key, outputsize=90):
    response = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": _twelvedata_symbol(symbol),
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
    return data


def main():
    api_key = os.environ.get("MARKET_API_KEY")
    bucket = os.environ.get("MARKET_DATA_BUCKET")
    if not api_key or not bucket:
        print("MARKET_API_KEY and MARKET_DATA_BUCKET must be set")
        sys.exit(1)

    symbols = sys.argv[1:] or DEFAULT_SYMBOLS
    s3 = boto3.client("s3")
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    written = []

    for symbol in symbols:
        safe_symbol = symbol.replace("/", "-")
        try:
            data = fetch_history(symbol, api_key)
        except Exception as exc:
            print(f"skip {symbol}: {exc}")
            continue

        key = f"raw/{safe_symbol}/{run_date}.json"
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data).encode("utf-8"),
            ContentType="application/json",
        )
        print(f"wrote s3://{bucket}/{key} ({len(data['values'])} rows)")
        written.append(safe_symbol)

    # One marker object per run, written last, is what actually triggers the EMR pipeline
    # (see lambda/emr_trigger) — triggering on every individual "raw/" object would fire
    # once per symbol and launch that many redundant clusters, since the Spark job re-reads
    # all raw data regardless of which file changed.
    if written:
        s3.put_object(
            Bucket=bucket,
            Key="_triggers/last-run.json",
            Body=json.dumps({"run_date": run_date, "symbols": written}).encode("utf-8"),
            ContentType="application/json",
        )
        print(f"wrote s3://{bucket}/_triggers/last-run.json (triggers the EMR job)")


if __name__ == "__main__":
    main()
