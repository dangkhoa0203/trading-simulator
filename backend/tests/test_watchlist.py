"""Watchlist CRUD and the price-target alert check (above/below crossing, one-shot
trigger, reset on re-add)."""

import alerts


def _set_price(monkeypatch, price):
    monkeypatch.setattr(alerts, "get_price", lambda ticker: (price, False))
    import watchlist
    monkeypatch.setattr(watchlist, "get_price", lambda ticker: (price, False))


def test_add_and_list_watchlist_item(client, auth_headers, monkeypatch):
    _set_price(monkeypatch, 187.32)

    res = client.post("/api/watchlist", json={"ticker": "aapl"}, headers=auth_headers)
    assert res.status_code == 201
    assert res.get_json()["ticker"] == "AAPL"

    listed = client.get("/api/watchlist", headers=auth_headers)
    assert listed.status_code == 200
    body = listed.get_json()
    assert len(body) == 1
    assert body[0]["current_price"] == 187.32


def test_ticker_required(client, auth_headers):
    res = client.post("/api/watchlist", json={}, headers=auth_headers)
    assert res.status_code == 400


def test_alert_requires_a_positive_target_price(client, auth_headers):
    res = client.post(
        "/api/watchlist", json={"ticker": "AAPL", "alert_direction": "above", "target_price": -5},
        headers=auth_headers,
    )
    assert res.status_code == 400

    res = client.post(
        "/api/watchlist", json={"ticker": "AAPL", "alert_direction": "sideways", "target_price": 100},
        headers=auth_headers,
    )
    assert res.status_code == 400


def test_delete_watchlist_item(client, auth_headers, monkeypatch):
    _set_price(monkeypatch, 100.0)
    created = client.post("/api/watchlist", json={"ticker": "AAPL"}, headers=auth_headers).get_json()

    res = client.delete(f"/api/watchlist/{created['id']}", headers=auth_headers)
    assert res.status_code == 204
    assert client.get("/api/watchlist", headers=auth_headers).get_json() == []


def test_cannot_delete_another_users_watchlist_item(client, auth_headers, monkeypatch, app):
    from extensions import db
    from models import User
    from tokens import make_token

    _set_price(monkeypatch, 100.0)
    created = client.post("/api/watchlist", json={"ticker": "AAPL"}, headers=auth_headers).get_json()

    with app.app_context():
        other = User(auth0_sub="auth0|other2", email="other2@example.com", display_name="Other")
        db.session.add(other)
        db.session.commit()
        other_token = make_token(other.id)

    res = client.delete(f"/api/watchlist/{created['id']}", headers={"Authorization": f"Bearer {other_token}"})
    assert res.status_code == 404


def test_watchlist_alert_triggers_when_price_crosses_above(client, auth_headers, monkeypatch):
    _set_price(monkeypatch, 150.0)
    client.post(
        "/api/watchlist",
        json={"ticker": "AAPL", "alert_direction": "above", "target_price": 200},
        headers=auth_headers,
    )

    # Still below target — no trigger yet.
    client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    body = client.get("/api/watchlist", headers=auth_headers).get_json()
    assert body[0]["triggered_at"] is None

    # Price crosses the target.
    _set_price(monkeypatch, 201.0)
    res = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    assert len(res.get_json()["watchlist_alerts_triggered"]) == 1

    body = client.get("/api/watchlist", headers=auth_headers).get_json()
    assert body[0]["triggered_at"] is not None


def test_watchlist_alert_triggers_when_price_crosses_below(client, auth_headers, monkeypatch):
    _set_price(monkeypatch, 50.0)
    client.post(
        "/api/watchlist",
        json={"ticker": "AAPL", "alert_direction": "below", "target_price": 40},
        headers=auth_headers,
    )

    _set_price(monkeypatch, 39.0)
    res = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    assert len(res.get_json()["watchlist_alerts_triggered"]) == 1


def test_watchlist_alert_does_not_retrigger_once_fired(client, auth_headers, monkeypatch):
    _set_price(monkeypatch, 250.0)
    client.post(
        "/api/watchlist",
        json={"ticker": "AAPL", "alert_direction": "above", "target_price": 200},
        headers=auth_headers,
    )

    first = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    assert len(first.get_json()["watchlist_alerts_triggered"]) == 1

    second = client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    assert len(second.get_json()["watchlist_alerts_triggered"]) == 0


def test_readding_a_watchlist_item_resets_its_trigger(client, auth_headers, monkeypatch):
    _set_price(monkeypatch, 250.0)
    client.post(
        "/api/watchlist",
        json={"ticker": "AAPL", "alert_direction": "above", "target_price": 200},
        headers=auth_headers,
    )
    client.post("/internal/check-alerts", headers={"X-Internal-Secret": "test-internal-secret"})
    triggered = client.get("/api/watchlist", headers=auth_headers).get_json()[0]
    assert triggered["triggered_at"] is not None

    client.post(
        "/api/watchlist",
        json={"ticker": "AAPL", "alert_direction": "above", "target_price": 300},
        headers=auth_headers,
    )
    reset = client.get("/api/watchlist", headers=auth_headers).get_json()[0]
    assert reset["triggered_at"] is None
    assert reset["target_price"] == 300
