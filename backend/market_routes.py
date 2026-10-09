from flask import Blueprint, jsonify, request

from decorators import login_required
from market import get_history

bp = Blueprint("market_routes", __name__, url_prefix="/api/market")


@bp.get("/history/<symbol>")
@login_required
def history(symbol):
    days = request.args.get("days", default=30, type=int) or 30
    days = max(7, min(days, 730))

    try:
        data = get_history(symbol.upper(), days=days)
    except Exception as exc:
        return jsonify(error=str(exc)), 502

    return jsonify(symbol=symbol.upper(), history=data)
