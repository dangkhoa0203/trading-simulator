"""Portfolio alert checking: the ±5%-from-baseline threshold, the "don't spam while an
unread alert already exists" guard, and the internal-only auth on the check endpoint."""

import alerts


def _set_price(monkeypatch, price):
    monkeypatch.setattr(alerts, "get_price", lambda symbol: (price, False))


def test_check_alerts_requires_the_shared_secret(client):
    res = client.post("/internal/check-alerts")
    assert res.status_code == 403

    res = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "wrong"})
    assert res.status_code == 403


def test_no_alert_when_portfolio_is_near_baseline(client, portfolio, monkeypatch):
    # cash_balance is 100000, no holdings — exactly at baseline, well under 5%.
    res = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})

    assert res.status_code == 200
    body = res.get_json()
    assert body["alerts_created"] == 0

    from models import Alert
    assert Alert.query.filter_by(portfolio_id=portfolio.id).count() == 0


def test_alert_created_when_portfolio_value_rises_past_threshold(client, portfolio, monkeypatch, app):
    from extensions import db
    from models import Holding

    with app.app_context():
        db.session.add(Holding(portfolio_id=portfolio.id, symbol="AAPL", quantity=100, avg_cost=10))
        portfolio.cash_balance = 90000.00  # spent 1000 buying the holding
        db.session.commit()

    # 100 shares @ 100 = 10000 holding value + 90000 cash = 100000... bump the price so the
    # portfolio is up over 5% from the 100000 baseline.
    _set_price(monkeypatch, 150.0)  # 100 * 150 = 15000 + 90000 cash = 105000 -> +5% exactly
    client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})

    _set_price(monkeypatch, 200.0)  # 100*200=20000 + 90000 = 110000 -> +10%, clearly over

    from models import Alert, Portfolio
    Alert.query.filter_by(portfolio_id=portfolio.id).delete()
    from extensions import db
    db.session.commit()

    res = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})

    assert res.status_code == 200
    assert res.get_json()["alerts_created"] == 1
    created = Alert.query.filter_by(portfolio_id=portfolio.id).first()
    assert created.alert_type == "value_threshold"
    assert "up" in created.message


def test_alert_created_when_portfolio_value_drops_past_threshold(client, portfolio, monkeypatch):
    _set_price(monkeypatch, 1.0)
    from extensions import db
    from models import Holding

    db.session.add(Holding(portfolio_id=portfolio.id, symbol="AAPL", quantity=1000, avg_cost=90))
    portfolio.cash_balance = 10000.00  # cash+holding value well under baseline once priced at 1.0
    db.session.commit()

    res = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})

    assert res.status_code == 200
    assert res.get_json()["alerts_created"] == 1
    from models import Alert
    created = Alert.query.filter_by(portfolio_id=portfolio.id).first()
    assert "down" in created.message


def test_no_duplicate_alert_while_one_is_still_unread(client, portfolio, monkeypatch):
    from extensions import db
    from models import Holding

    db.session.add(Holding(portfolio_id=portfolio.id, symbol="AAPL", quantity=100, avg_cost=10))
    portfolio.cash_balance = 90000.00
    db.session.commit()

    _set_price(monkeypatch, 200.0)
    first = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    assert first.get_json()["alerts_created"] == 1

    second = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    assert second.get_json()["alerts_created"] == 0


def test_mark_alert_read_allows_a_new_one_next_check(client, auth_headers, portfolio, monkeypatch, app):
    from extensions import db
    from models import Alert, Holding

    db.session.add(Holding(portfolio_id=portfolio.id, symbol="AAPL", quantity=100, avg_cost=10))
    portfolio.cash_balance = 90000.00
    db.session.commit()

    _set_price(monkeypatch, 200.0)
    client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    alert = Alert.query.filter_by(portfolio_id=portfolio.id).first()

    mark_res = client.post(
        f"/api/portfolios/{portfolio.id}/alerts/{alert.id}/read", headers=auth_headers
    )
    assert mark_res.status_code == 200
    assert mark_res.get_json()["is_read"] is True

    again = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    assert again.get_json()["alerts_created"] == 1
