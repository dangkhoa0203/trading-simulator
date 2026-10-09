"""Portfolio value threshold alerts.

The check itself (`POST /internal/check-alerts`) lives here in the Flask app rather than in
the Lambda that triggers it, so the DB models and price-fetching logic aren't duplicated in
a second codebase — Lambda would also need a psycopg2 build for its Linux runtime, which
doesn't cross-compile from a local macOS pip install without a Docker/layer detour. Instead
Lambda (lambda/price_alert_checker) is a trivial stdlib-only HTTP call on an EventBridge
schedule, and this endpoint does the actual work, guarded by a shared secret since it isn't
a user-facing route.
"""

from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request

from decorators import login_required
from extensions import db
from market import get_price
from models import Alert, Portfolio, WatchlistItem

bp = Blueprint("alerts", __name__)

BASELINE_VALUE = 100000.00
THRESHOLD_PCT = 5.0


def _portfolio_total_value(portfolio):
    total = float(portfolio.cash_balance)
    for holding in portfolio.holdings:
        try:
            price, _stale = get_price(holding.ticker)
            total += price * float(holding.quantity)
        except RuntimeError:
            continue
    return total


def _check_watchlist_alerts():
    triggered = []
    pending = WatchlistItem.query.filter(
        WatchlistItem.alert_direction.isnot(None), WatchlistItem.triggered_at.is_(None)
    ).all()
    for item in pending:
        try:
            price, _stale = get_price(item.ticker)
        except RuntimeError:
            continue

        target = float(item.target_price)
        crossed = (item.alert_direction == "above" and price >= target) or (
            item.alert_direction == "below" and price <= target
        )
        if crossed:
            item.triggered_at = datetime.now(timezone.utc)
            triggered.append(item.id)
    return triggered


@bp.post("/internal/check-alerts")
def check_alerts():
    secret = request.headers.get("X-Internal-Secret", "")
    if not secret or secret != current_app.config["INTERNAL_TASK_SECRET"]:
        return jsonify(error="forbidden"), 403

    created = []
    for portfolio in Portfolio.query.all():
        already_unread = Alert.query.filter_by(portfolio_id=portfolio.id, is_read=False).first()
        if already_unread is not None:
            continue

        total_value = _portfolio_total_value(portfolio)
        pct_change = (total_value - BASELINE_VALUE) / BASELINE_VALUE * 100

        if abs(pct_change) >= THRESHOLD_PCT:
            direction = "up" if pct_change > 0 else "down"
            alert = Alert(
                portfolio_id=portfolio.id,
                alert_type="value_threshold",
                message=f"Portfolio value is {direction} {abs(pct_change):.1f}% from the ${BASELINE_VALUE:,.0f} baseline (now ${total_value:,.2f}).",
                threshold_pct=THRESHOLD_PCT,
                triggered_value=total_value,
            )
            db.session.add(alert)
            created.append(portfolio.id)

    watchlist_triggered = _check_watchlist_alerts()

    db.session.commit()
    return jsonify(
        checked=Portfolio.query.count(),
        alerts_created=len(created),
        portfolio_ids=created,
        watchlist_alerts_triggered=watchlist_triggered,
    )


def _get_owned_portfolio(portfolio_id):
    portfolio = Portfolio.query.get(portfolio_id)
    if portfolio is None or portfolio.user_id != g.user_id:
        return None
    return portfolio


@bp.get("/api/portfolios/<int:portfolio_id>/alerts")
@login_required
def list_alerts(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    alerts = Alert.query.filter_by(portfolio_id=portfolio.id).order_by(Alert.created_at.desc()).all()
    return jsonify([a.to_dict() for a in alerts])


@bp.post("/api/portfolios/<int:portfolio_id>/alerts/<int:alert_id>/read")
@login_required
def mark_alert_read(portfolio_id, alert_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    alert = Alert.query.filter_by(id=alert_id, portfolio_id=portfolio.id).first()
    if alert is None:
        return jsonify(error="not found"), 404

    alert.is_read = True
    db.session.commit()
    return jsonify(alert.to_dict())
