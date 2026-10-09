"""Reads the market_trends table (written by compute_trends.py on a schedule) for the
dashboard. Previously read the EMR/Spark job's JSON output from S3 — replaced with a plain
table once EMR was no longer available; same shape, just a query instead of a file read.
"""

from flask import Blueprint, jsonify

from decorators import login_required
from models import MarketTrend

bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@bp.get("/latest")
@login_required
def latest():
    tickers = [row[0] for row in MarketTrend.query.with_entities(MarketTrend.ticker).distinct()]
    rows = []
    for ticker in tickers:
        latest_row = (
            MarketTrend.query.filter_by(ticker=ticker).order_by(MarketTrend.date.desc()).first()
        )
        if latest_row is not None:
            rows.append(latest_row.to_dict())
    rows.sort(key=lambda r: r["ticker"])
    return jsonify(rows)


@bp.get("/series/<ticker>")
@login_required
def series(ticker):
    rows = (
        MarketTrend.query.filter_by(ticker=ticker.upper()).order_by(MarketTrend.date.asc()).all()
    )
    return jsonify(ticker=ticker.upper(), series=[r.to_dict() for r in rows])
