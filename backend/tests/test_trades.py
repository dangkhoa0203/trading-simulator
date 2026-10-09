"""Trade execution: the buy/sell math, weighted-average cost, and the cases that must be
rejected (insufficient cash, insufficient holding, bad input) — this is the part of the app
where a silent bug means wrong money numbers, so it gets the most coverage."""

import trades


def _trade(client, auth_headers, portfolio_id, **kwargs):
    return client.post(f"/api/portfolios/{portfolio_id}/trades", json=kwargs, headers=auth_headers)


def test_buy_creates_a_new_holding(client, auth_headers, portfolio, monkeypatch):
    monkeypatch.setattr(trades, "get_price", lambda ticker: (150.0, False))

    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=10)

    assert res.status_code == 201
    body = res.get_json()
    assert body["cash_balance"] == 100000.0 - 1500.0
    assert body["transaction"]["ticker"] == "AAPL"
    assert body["transaction"]["side"] == "BUY"
    assert body["transaction"]["quantity"] == 10.0
    assert body["transaction"]["price"] == 150.0


def test_buy_more_updates_weighted_average_cost(client, auth_headers, portfolio, monkeypatch):
    # Buy 10 @ 100, then 10 @ 200 — average cost should land exactly between them.
    monkeypatch.setattr(trades, "get_price", lambda ticker: (100.0, False))
    _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=10)

    monkeypatch.setattr(trades, "get_price", lambda ticker: (200.0, False))
    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=10)

    from models import Holding
    holding = Holding.query.filter_by(portfolio_id=portfolio.id, ticker="AAPL").first()
    assert res.status_code == 201
    assert float(holding.quantity) == 20.0
    assert float(holding.avg_cost) == 150.0


def test_buy_rejected_when_cash_insufficient(client, auth_headers, portfolio, monkeypatch):
    monkeypatch.setattr(trades, "get_price", lambda ticker: (1_000_000.0, False))

    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=1)

    assert res.status_code == 400
    assert "insufficient cash" in res.get_json()["error"]
    # No partial state: cash balance must be untouched.
    from models import Portfolio
    assert float(Portfolio.query.get(portfolio.id).cash_balance) == 100000.0


def test_sell_reduces_holding_and_refunds_cash(client, auth_headers, portfolio, monkeypatch):
    monkeypatch.setattr(trades, "get_price", lambda ticker: (100.0, False))
    _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=10)

    monkeypatch.setattr(trades, "get_price", lambda ticker: (120.0, False))
    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="SELL", quantity=4)

    assert res.status_code == 201
    body = res.get_json()
    # Started with 100000, spent 1000 buying, now +480 selling 4 @ 120.
    assert body["cash_balance"] == 100000.0 - 1000.0 + 480.0

    from models import Holding
    holding = Holding.query.filter_by(portfolio_id=portfolio.id, ticker="AAPL").first()
    assert float(holding.quantity) == 6.0


def test_sell_all_of_a_holding_removes_the_row(client, auth_headers, portfolio, monkeypatch):
    monkeypatch.setattr(trades, "get_price", lambda ticker: (100.0, False))
    _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=5)
    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="SELL", quantity=5)

    assert res.status_code == 201
    from models import Holding
    assert Holding.query.filter_by(portfolio_id=portfolio.id, ticker="AAPL").first() is None


def test_sell_rejected_without_a_holding(client, auth_headers, portfolio, monkeypatch):
    monkeypatch.setattr(trades, "get_price", lambda ticker: (100.0, False))

    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="SELL", quantity=1)

    assert res.status_code == 400
    assert "insufficient holding" in res.get_json()["error"]


def test_sell_rejected_for_more_than_is_held(client, auth_headers, portfolio, monkeypatch):
    monkeypatch.setattr(trades, "get_price", lambda ticker: (100.0, False))
    _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=5)

    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="SELL", quantity=6)

    assert res.status_code == 400
    assert "insufficient holding" in res.get_json()["error"]


def test_rejects_missing_symbol_or_bad_side(client, auth_headers, portfolio):
    res = _trade(client, auth_headers, portfolio.id, ticker="", side="BUY", quantity=1)
    assert res.status_code == 400

    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="HOLD", quantity=1)
    assert res.status_code == 400


def test_rejects_non_positive_quantity(client, auth_headers, portfolio):
    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=0)
    assert res.status_code == 400

    res = _trade(client, auth_headers, portfolio.id, ticker="AAPL", side="BUY", quantity=-5)
    assert res.status_code == 400


def test_backtest_trade_uses_historical_price_not_a_client_supplied_one(client, auth_headers, portfolio, monkeypatch):
    # The whole point of backtesting is the price is looked up server-side for the given
    # date — a malicious client passing its own "price" field must have no effect.
    monkeypatch.setattr(trades, "get_price_on_date", lambda ticker, date: (42.0, date[:10]))

    res = _trade(
        client, auth_headers, portfolio.id,
        ticker="AAPL", side="BUY", quantity=1, date="2024-01-15", price=1.0,
    )

    assert res.status_code == 201
    assert res.get_json()["transaction"]["price"] == 42.0


def test_backtest_trade_reports_the_actual_date_used(client, auth_headers, portfolio, monkeypatch):
    # The requested date can fall on a weekend/holiday — get_price_on_date falls back to the
    # nearest prior trading day, and the response should say so rather than lying about it.
    monkeypatch.setattr(trades, "get_price_on_date", lambda ticker, date: (42.0, "2024-01-12"))

    res = _trade(
        client, auth_headers, portfolio.id,
        ticker="AAPL", side="BUY", quantity=1, date="2024-01-14",  # a Sunday
    )

    assert res.status_code == 201
    body = res.get_json()
    assert body["actual_trade_date"] == "2024-01-12"
    assert body["transaction"]["executed_at"].startswith("2024-01-12")


def test_trade_requires_authentication(client, portfolio):
    res = client.post(f"/api/portfolios/{portfolio.id}/trades", json={"ticker": "AAPL", "side": "BUY", "quantity": 1})
    assert res.status_code == 401


def test_cannot_trade_another_users_portfolio(client, portfolio, app):
    from extensions import db
    from models import User
    from tokens import make_token

    with app.app_context():
        other = User(auth0_sub="auth0|other", email="other@example.com", display_name="Other")
        db.session.add(other)
        db.session.commit()
        other_token = make_token(other.id)

    res = client.post(
        f"/api/portfolios/{portfolio.id}/trades",
        json={"ticker": "AAPL", "side": "BUY", "quantity": 1},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res.status_code == 404
