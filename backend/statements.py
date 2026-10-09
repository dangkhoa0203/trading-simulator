"""Portfolio PDF statement export.

Fetches the portfolio data the already-authenticated user has access to, POSTs it to the
ECS-hosted pdf-service (a stateless renderer with no DB/auth access of its own — see
pdf-service/app.py), and streams the resulting PDF bytes straight back to the browser. The
browser never talks to the PDF service directly.
"""

import requests
from flask import Blueprint, current_app, g, jsonify, request, send_file
from io import BytesIO

from decorators import login_required
from market import get_price
from models import Portfolio, Transaction

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
            "symbol": holding.symbol,
            "quantity": float(holding.quantity),
            "avg_cost": float(holding.avg_cost),
        }
        try:
            price, _stale = get_price(holding.symbol)
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

    try:
        response = requests.post(
            f"{current_app.config['PDF_SERVICE_URL']}/generate",
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return jsonify(error=f"PDF service unavailable: {exc}"), 502

    return send_file(
        BytesIO(response.content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{portfolio.name.replace(' ', '_')}_statement.pdf",
    )
