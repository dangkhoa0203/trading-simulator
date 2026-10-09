from flask import Blueprint, g, jsonify, request

from decorators import login_required
from extensions import db
from market import get_price
from models import Holding, Portfolio

bp = Blueprint("portfolios", __name__, url_prefix="/api/portfolios")


def _get_owned_portfolio(portfolio_id):
    portfolio = Portfolio.query.get(portfolio_id)
    if portfolio is None or portfolio.user_id != g.user_id:
        return None
    return portfolio


@bp.get("")
@login_required
def list_portfolios():
    portfolios = Portfolio.query.filter_by(user_id=g.user_id).all()
    return jsonify([p.to_dict() for p in portfolios])


@bp.post("")
@login_required
def create_portfolio():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    portfolio = Portfolio(
        user_id=g.user_id,
        name=name,
        base_currency=data.get("base_currency", "USD"),
        cash_balance=data.get("cash_balance", 100000.00),
    )
    db.session.add(portfolio)
    db.session.commit()
    return jsonify(portfolio.to_dict()), 201


@bp.get("/<int:portfolio_id>")
@login_required
def get_portfolio(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    payload = portfolio.to_dict()
    holdings = []
    holdings_value = 0.0
    for holding in portfolio.holdings:
        entry = holding.to_dict()
        try:
            price, stale = get_price(holding.ticker)
            entry["current_price"] = price
            entry["price_stale"] = stale
            entry["market_value"] = price * float(holding.quantity)
            holdings_value += entry["market_value"]
        except RuntimeError:
            entry["current_price"] = None
            entry["price_stale"] = None
            entry["market_value"] = None
        holdings.append(entry)

    payload["holdings"] = holdings
    payload["total_value"] = float(portfolio.cash_balance) + holdings_value
    return jsonify(payload)


@bp.patch("/<int:portfolio_id>")
@login_required
def update_portfolio(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        portfolio.name = data["name"]
    if "base_currency" in data:
        portfolio.base_currency = data["base_currency"]
    db.session.commit()
    return jsonify(portfolio.to_dict())


@bp.delete("/<int:portfolio_id>")
@login_required
def delete_portfolio(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404
    db.session.delete(portfolio)
    db.session.commit()
    return "", 204


@bp.get("/<int:portfolio_id>/holdings")
@login_required
def list_holdings(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404
    return jsonify([h.to_dict() for h in portfolio.holdings])


@bp.post("/<int:portfolio_id>/holdings")
@login_required
def upsert_holding(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    ticker = (data.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify(error="ticker is required"), 400

    holding = Holding.query.filter_by(portfolio_id=portfolio.id, ticker=ticker).first()
    if holding is None:
        holding = Holding(portfolio_id=portfolio.id, ticker=ticker)
        db.session.add(holding)

    holding.quantity = data.get("quantity", holding.quantity)
    holding.avg_cost = data.get("avg_cost", holding.avg_cost)
    db.session.commit()
    return jsonify(holding.to_dict()), 201


@bp.delete("/<int:portfolio_id>/holdings/<int:holding_id>")
@login_required
def delete_holding(portfolio_id, holding_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    holding = Holding.query.filter_by(id=holding_id, portfolio_id=portfolio.id).first()
    if holding is None:
        return jsonify(error="not found"), 404

    db.session.delete(holding)
    db.session.commit()
    return "", 204
