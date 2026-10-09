from flask import Blueprint, jsonify, request

from decorators import login_required
from market import INTRADAY_INTERVALS, get_history

bp = Blueprint("market_routes", __name__, url_prefix="/api/market")


@bp.get("/history/<ticker>")
@login_required
def history(ticker):
    interval = request.args.get("interval")
    if interval is not None and interval not in INTRADAY_INTERVALS:
        return jsonify(error=f"interval must be one of {sorted(INTRADAY_INTERVALS)}"), 400

    days = request.args.get("days", default=30, type=int) or 30
    days = max(7, min(days, 730))

    try:
        data = get_history(ticker.upper(), days=days, interval=interval)
    except Exception as exc:
        return jsonify(error=str(exc)), 502

    return jsonify(ticker=ticker.upper(), history=data)
