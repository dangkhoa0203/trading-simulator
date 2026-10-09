"""CSV transaction export: correct header, numeric formatting (no currency symbols, fixed
decimals, trimmed-trailing-zero quantities), chronological order, and the UTF-8 BOM Excel
needs."""

import csv
import io

from extensions import db
from models import Transaction


def _add_transaction(portfolio, ticker, side, quantity, price, executed_at=None):
    t = Transaction(portfolio_id=portfolio.id, ticker=ticker, side=side, quantity=quantity, price=price)
    if executed_at is not None:
        t.executed_at = executed_at
    db.session.add(t)
    db.session.commit()
    return t


def test_csv_requires_authentication(client, portfolio):
    res = client.get(f"/api/portfolios/{portfolio.id}/transactions.csv")
    assert res.status_code == 401


def test_csv_404s_for_another_users_portfolio(client, portfolio, app):
    from models import User
    from tokens import make_token

    with app.app_context():
        other = User(auth0_sub="auth0|csv-other", email="csvother@example.com", display_name="Other")
        db.session.add(other)
        db.session.commit()
        other_token = make_token(other.id)

    res = client.get(
        f"/api/portfolios/{portfolio.id}/transactions.csv",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res.status_code == 404


def test_csv_has_correct_headers_and_content_type(client, auth_headers, portfolio):
    res = client.get(f"/api/portfolios/{portfolio.id}/transactions.csv", headers=auth_headers)
    assert res.status_code == 200
    assert res.content_type.startswith("text/csv")
    assert "attachment" in res.headers["Content-Disposition"]


def test_csv_starts_with_a_utf8_bom(client, auth_headers, portfolio):
    res = client.get(f"/api/portfolios/{portfolio.id}/transactions.csv", headers=auth_headers)
    assert res.data[:3] == b"\xef\xbb\xbf"


def test_csv_formats_numbers_without_currency_symbols(client, auth_headers, portfolio):
    _add_transaction(portfolio, "AAPL", "BUY", 120, 165.2)

    res = client.get(f"/api/portfolios/{portfolio.id}/transactions.csv", headers=auth_headers)
    text = res.data.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))

    assert rows[0] == ["Date", "Time (UTC)", "Ticker", "Side", "Quantity", "Price", "Total"]
    data_row = rows[1]
    assert data_row[2] == "AAPL"
    assert data_row[3] == "BUY"
    assert data_row[4] == "120"  # whole-share quantity, no trailing .000000
    assert data_row[5] == "165.20"  # price always 2 decimals
    assert data_row[6] == "19824.00"  # computed total, 2 decimals
    for cell in (data_row[4], data_row[5], data_row[6]):
        assert "$" not in cell  # plain numbers so spreadsheets import them as numeric


def test_csv_keeps_fractional_quantity_for_crypto(client, auth_headers, portfolio):
    _add_transaction(portfolio, "BTC-USD", "BUY", 0.45, 52000.0)

    res = client.get(f"/api/portfolios/{portfolio.id}/transactions.csv", headers=auth_headers)
    rows = list(csv.reader(io.StringIO(res.data.decode("utf-8-sig"))))
    assert rows[1][4] == "0.45"


def test_csv_rows_are_chronological(client, auth_headers, portfolio):
    import datetime

    _add_transaction(portfolio, "AAPL", "BUY", 1, 100, executed_at=datetime.datetime(2024, 3, 2, tzinfo=datetime.timezone.utc))
    _add_transaction(portfolio, "AAPL", "BUY", 1, 100, executed_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc))

    res = client.get(f"/api/portfolios/{portfolio.id}/transactions.csv", headers=auth_headers)
    rows = list(csv.reader(io.StringIO(res.data.decode("utf-8-sig"))))
    assert rows[1][0] == "2024-01-01"
    assert rows[2][0] == "2024-03-02"


def test_csv_empty_portfolio_has_header_only(client, auth_headers, portfolio):
    res = client.get(f"/api/portfolios/{portfolio.id}/transactions.csv", headers=auth_headers)
    rows = list(csv.reader(io.StringIO(res.data.decode("utf-8-sig"))))
    assert len(rows) == 1
