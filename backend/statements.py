"""Portfolio PDF statement export.

Fetches the portfolio data the already-authenticated user has access to and renders it
in-process via pdf_export.build_pdf (reportlab) — previously POSTed to a separate ECS-hosted
microservice; folded in-process since there's no orchestrator making that split pay for itself.
"""

from flask import Blueprint, g, jsonify, send_file

from decorators import login_required
from market import get_price
from models import Portfolio, Transaction
from pdf_export import build_pdf

bp = Blueprint("statements", __name__, url_prefix="/api/portfolios")


def _get_owned_portfolio(portfolio_id):
    portfolio = Portfolio.query.get(portfolio_id)
    if portfolio is None or portfolio.user_id != g.user_id:
        return None
    return portfolio


@bp.get("/<int:portfolio_id>/statement.pdf")
@login_required
def statement(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    holdings = []
    total_value = float(portfolio.cash_balance)
    for holding in portfolio.holdings:
        entry = {
            "ticker": holding.ticker,
            "quantity": float(holding.quantity),
            "avg_cost": float(holding.avg_cost),
        }
        try:
            price, _stale = get_price(holding.ticker)
            entry["current_price"] = price
            entry["market_value"] = price * float(holding.quantity)
            total_value += entry["market_value"]
        except RuntimeError:
            entry["current_price"] = None
            entry["market_value"] = None
        holdings.append(entry)

    transactions = [
        t.to_dict()
        for t in Transaction.query.filter_by(portfolio_id=portfolio.id).order_by(Transaction.executed_at.desc()).all()
    ]

    payload = {
        "portfolio": {
            "name": portfolio.name,
            "cash_balance": float(portfolio.cash_balance),
            "total_value": total_value,
            "base_currency": portfolio.base_currency,
        },
        "holdings": holdings,
        "transactions": transactions,
    }

    pdf_buffer = build_pdf(payload)

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{portfolio.name.replace(' ', '_')}_statement.pdf",
    )
