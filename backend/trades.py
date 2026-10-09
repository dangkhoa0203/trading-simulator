from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, g, jsonify, request

from decorators import login_required
from extensions import db
from market import get_price, get_price_at_date
from models import Holding, Portfolio, Transaction

bp = Blueprint("trades", __name__, url_prefix="/api/portfolios")


def _get_owned_portfolio(portfolio_id):
    portfolio = Portfolio.query.get(portfolio_id)
    if portfolio is None or portfolio.user_id != g.user_id:
        return None
    return portfolio


@bp.post("/<int:portfolio_id>/trades")
@login_required
def create_trade(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    ticker = (data.get("ticker") or "").strip().upper()
    side = (data.get("side") or "").strip().upper()
    raw_quantity = data.get("quantity")
    trade_date = data.get("date")  # optional: backtest at a historical price instead of live

    if not ticker or side not in ("BUY", "SELL"):
        return jsonify(error="ticker and side (BUY/SELL) are required"), 400
    if not isinstance(raw_quantity, (int, float)) or raw_quantity <= 0:
        return jsonify(error="quantity must be a positive number"), 400

    price_stale = False
    executed_at = None
    try:
        if trade_date:
            days = int(data.get("days") or 365)
            price = get_price_at_date(ticker, trade_date, days=days)
            executed_at = datetime.strptime(trade_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            price, price_stale = get_price(ticker)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 502

    quantity = Decimal(str(raw_quantity))
    price = Decimal(str(price))
    cost = quantity * price

    holding = Holding.query.filter_by(portfolio_id=portfolio.id, ticker=ticker).first()

    if side == "BUY":
        if cost > portfolio.cash_balance:
            return jsonify(error="insufficient cash balance"), 400
        portfolio.cash_balance -= cost
        if holding is None:
            holding = Holding(portfolio_id=portfolio.id, ticker=ticker, quantity=quantity, avg_cost=price)
            db.session.add(holding)
        else:
            total_cost = holding.quantity * holding.avg_cost + cost
            holding.quantity += quantity
            holding.avg_cost = total_cost / holding.quantity
    else:
        if holding is None or holding.quantity < quantity:
            return jsonify(error="insufficient holding quantity"), 400
        portfolio.cash_balance += cost
        holding.quantity -= quantity
        if holding.quantity == 0:
            db.session.delete(holding)

    transaction = Transaction(portfolio_id=portfolio.id, ticker=ticker, side=side, quantity=quantity, price=price)
    if executed_at is not None:
        transaction.executed_at = executed_at
    db.session.add(transaction)
    db.session.commit()

    return jsonify(
        transaction=transaction.to_dict(),
        cash_balance=float(portfolio.cash_balance),
        price_stale=price_stale,
    ), 201
