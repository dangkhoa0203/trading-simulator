"""EMR PySpark job: reads raw historical price JSON from S3 (landed there by
backend/fetch_historical_data.py), computes 7-day and 30-day moving averages plus a simple
up/down trend per symbol, and writes the result back to S3 for the dashboard to read.

Run as an EMR step:
    spark-submit moving_average_job.py <raw-data-bucket> <reports-bucket>
"""

import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def main():
    if len(sys.argv) != 3:
        print("Usage: moving_average_job.py <raw-data-bucket> <reports-bucket>")
        sys.exit(1)

    raw_bucket, reports_bucket = sys.argv[1], sys.argv[2]

    spark = SparkSession.builder.appName("tradenow-moving-averages").getOrCreate()

    raw = spark.read.option("multiLine", "true").json(f"s3://{raw_bucket}/raw/*/*.json")

    # Twelve Data's time_series response nests the symbol under "meta" and the daily rows
    # under "values" — explode that array into one row per (symbol, date). Twelve Data
    # returns crypto pairs as "BTC/USD"; the rest of the app (holdings, trades, the
    # frontend) uses "BTC-USD" everywhere, so normalize to match.
    prices = (
        raw.select(F.regexp_replace(F.col("meta.symbol"), "/", "-").alias("symbol"), F.explode("values").alias("v"))
        .select(
            "symbol",
            F.to_date("v.datetime").alias("date"),
            F.col("v.close").cast("double").alias("close"),
        )
        # Successive fetch_historical_data.py runs pull overlapping rolling windows, so the
        # same (symbol, date) can appear in multiple raw files.
        .dropDuplicates(["symbol", "date"])
    )

    window_7d = Window.partitionBy("symbol").orderBy("date").rowsBetween(-6, 0)
    window_30d = Window.partitionBy("symbol").orderBy("date").rowsBetween(-29, 0)

    with_moving_averages = prices.withColumn("ma_7d", F.avg("close").over(window_7d)).withColumn(
        "ma_30d", F.avg("close").over(window_30d)
    )

    latest_per_symbol = Window.partitionBy("symbol").orderBy(F.col("date").desc())
    latest_summary = (
        with_moving_averages.withColumn("rn", F.row_number().over(latest_per_symbol))
        .filter(F.col("rn") == 1)
        .withColumn("trend", F.when(F.col("close") >= F.col("ma_30d"), "up").otherwise("down"))
        .select("symbol", "date", "close", "ma_7d", "ma_30d", "trend")
        .orderBy("symbol")
    )

    latest_summary.coalesce(1).write.mode("overwrite").json(f"s3://{reports_bucket}/reports/latest")

    # Full daily series (with moving averages) too, for charting the trend over time.
    with_moving_averages.select("symbol", "date", "close", "ma_7d", "ma_30d").coalesce(1).orderBy(
        "symbol", "date"
    ).write.mode("overwrite").json(f"s3://{reports_bucket}/reports/series")

    spark.stop()


if __name__ == "__main__":
    main()
