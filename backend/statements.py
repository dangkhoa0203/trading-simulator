"""Portfolio statement export — PDF (for reading) and CSV (for importing into a spreadsheet).

Fetches the portfolio data the already-authenticated user has access to and renders it
in-process via pdf_export.build_pdf (reportlab) — previously POSTed to a separate ECS-hosted
microservice; folded in-process since there's no orchestrator making that split pay for itself.
"""

import csv
import io

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


def _format_quantity(value):
    # Fixed-cost whole-share trades read as "120", fractional crypto as "0.45" — not
    # "120.000000"/"0.450000", which is what str(Decimal) or a blind :.6f would give.
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


@bp.get("/<int:portfolio_id>/transactions.csv")
@login_required
def transactions_csv(portfolio_id):
    portfolio = _get_owned_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not found"), 404

    transactions = (
        Transaction.query.filter_by(portfolio_id=portfolio.id).order_by(Transaction.executed_at.asc()).all()
    )

    buffer = io.StringIO()
    # Plain numeric columns (no currency symbols, fixed decimal places) so Excel/Sheets/
    # pandas import Price/Quantity/Total as numbers, not text, with no further cleanup.
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(["Date", "Time (UTC)", "Ticker", "Side", "Quantity", "Price", "Total"])
    for t in transactions:
        quantity = float(t.quantity)
        price = float(t.price)
        executed = t.executed_at
        writer.writerow(
            [
                executed.strftime("%Y-%m-%d") if executed else "",
                executed.strftime("%H:%M:%S") if executed else "",
                t.ticker,
                t.side,
                _format_quantity(quantity),
                f"{price:.2f}",
                f"{quantity * price:.2f}",
            ]
        )

    # UTF-8 BOM so Excel (which otherwise guesses the system codepage) opens this correctly
    # rather than mangling anything non-ASCII — harmless for plain-ASCII tickers too.
    csv_bytes = b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")

    return send_file(
        io.BytesIO(csv_bytes),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{portfolio.name.replace(' ', '_')}_transactions.csv",
    )
