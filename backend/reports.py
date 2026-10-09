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
    symbols = [row[0] for row in MarketTrend.query.with_entities(MarketTrend.symbol).distinct()]
    rows = []
    for symbol in symbols:
        latest_row = (
            MarketTrend.query.filter_by(symbol=symbol).order_by(MarketTrend.date.desc()).first()
        )
        if latest_row is not None:
            rows.append(latest_row.to_dict())
    rows.sort(key=lambda r: r["symbol"])
    return jsonify(rows)


@bp.get("/series/<symbol>")
@login_required
def series(symbol):
    rows = (
        MarketTrend.query.filter_by(symbol=symbol.upper()).order_by(MarketTrend.date.asc()).all()
    )
    return jsonify(symbol=symbol.upper(), series=[r.to_dict() for r in rows])
