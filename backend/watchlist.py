"""Watchlist: tickers a user tracks without necessarily holding, each optionally carrying
a price-target alert ("notify me when AAPL crosses $200"). Checking the alert reuses the
same scheduled /internal/check-alerts job as portfolio value alerts (see alerts.py)."""

from flask import Blueprint, g, jsonify, request

from decorators import login_required
from extensions import db
from market import get_price
from models import WatchlistItem

bp = Blueprint("watchlist", __name__, url_prefix="/api/watchlist")

VALID_DIRECTIONS = ("above", "below")


@bp.get("")
@login_required
def list_watchlist():
    items = WatchlistItem.query.filter_by(user_id=g.user_id).order_by(WatchlistItem.created_at.asc()).all()
    result = []
    for item in items:
        entry = item.to_dict()
        try:
            price, stale = get_price(item.ticker)
            entry["current_price"] = price
            entry["price_stale"] = stale
        except RuntimeError:
            entry["current_price"] = None
            entry["price_stale"] = None
        result.append(entry)
    return jsonify(result)


@bp.post("")
@login_required
def add_watchlist_item():
    data = request.get_json(silent=True) or {}
    ticker = (data.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify(error="ticker is required"), 400

    alert_direction = data.get("alert_direction")
    target_price = data.get("target_price")
    if alert_direction is not None:
        if alert_direction not in VALID_DIRECTIONS:
            return jsonify(error="alert_direction must be 'above' or 'below'"), 400
        if not isinstance(target_price, (int, float)) or target_price <= 0:
            return jsonify(error="target_price must be a positive number when setting an alert"), 400

    item = WatchlistItem.query.filter_by(user_id=g.user_id, ticker=ticker).first()
    if item is None:
        item = WatchlistItem(user_id=g.user_id, ticker=ticker)
        db.session.add(item)

    # Re-adding/re-configuring an existing entry resets any prior trigger.
    item.alert_direction = alert_direction
    item.target_price = target_price
    item.triggered_at = None
    db.session.commit()
    return jsonify(item.to_dict()), 201


@bp.delete("/<int:item_id>")
@login_required
def delete_watchlist_item(item_id):
    item = WatchlistItem.query.filter_by(id=item_id, user_id=g.user_id).first()
    if item is None:
        return jsonify(error="not found"), 404
    db.session.delete(item)
    db.session.commit()
    return "", 204
