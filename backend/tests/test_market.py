"""get_price_on_date's weekend/holiday fallback and future-date guard, plus the
market-history route's interval validation."""

import market


def _history(dates_and_closes):
    return [{"date": d, "close": c} for d, c in dates_and_closes]


def test_get_price_on_date_exact_match(monkeypatch, app):
    monkeypatch.setattr(
        market, "get_history",
        lambda ticker, days=30, interval=None: _history([("2024-01-10", 100.0), ("2024-01-11", 101.0)]),
    )
    with app.app_context():
        price, actual_date = market.get_price_on_date("AAPL", "2024-01-11")
    assert price == 101.0
    assert actual_date == "2024-01-11"


def test_get_price_on_date_falls_back_to_nearest_earlier_trading_day(monkeypatch, app):
    # 2024-01-14 is a Sunday — no bar for it, should fall back to Friday the 12th.
    monkeypatch.setattr(
        market, "get_history",
        lambda ticker, days=30, interval=None: _history(
            [("2024-01-11", 99.0), ("2024-01-12", 100.0)]
        ),
    )
    with app.app_context():
        price, actual_date = market.get_price_on_date("AAPL", "2024-01-14")
    assert price == 100.0
    assert actual_date == "2024-01-12"


def test_get_price_on_date_rejects_a_future_date(app):
    with app.app_context():
        try:
            market.get_price_on_date("AAPL", "2999-01-01")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "future" not in str(exc) or "past" in str(exc)


def test_get_price_on_date_raises_when_nothing_available(monkeypatch, app):
    monkeypatch.setattr(market, "get_history", lambda ticker, days=30, interval=None: [])
    with app.app_context():
        try:
            market.get_price_on_date("AAPL", "2024-01-11")
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass


def test_history_route_rejects_an_invalid_interval(client, auth_headers):
    res = client.get("/api/market/history/AAPL?interval=3min", headers=auth_headers)
    assert res.status_code == 400


def test_history_route_accepts_a_valid_intraday_interval(client, auth_headers, monkeypatch):
    import market_routes
    monkeypatch.setattr(
        market_routes, "get_history",
        lambda ticker, days=30, interval=None: _history([("2024-01-11 09:30:00", 100.0)]),
    )
    res = client.get("/api/market/history/AAPL?interval=15min", headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["history"][0]["close"] == 100.0
