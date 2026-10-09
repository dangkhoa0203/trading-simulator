"""Shared fixtures: an in-memory SQLite app (same models as Postgres, no network/DB setup
needed) plus a logged-in test client using a real signed bearer token."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AUTH0_DOMAIN", "example.us.auth0.com")
os.environ.setdefault("AUTH0_CLIENT_ID", "test-client-id")
os.environ.setdefault("AUTH0_CLIENT_SECRET", "test-client-secret")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["INTERNAL_TASK_SECRET"] = "test-internal-secret"

import pytest

from app import create_app
from extensions import db as _db
from models import Portfolio, User
from tokens import make_token


@pytest.fixture()
def app():
    flask_app = create_app()
    flask_app.config.update(TESTING=True)

    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    u = User(auth0_sub="auth0|test123", email="trader@example.com", display_name="Test Trader")
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture()
def portfolio(app, user):
    p = Portfolio(user_id=user.id, name="Test Portfolio", cash_balance=100000.00)
    _db.session.add(p)
    _db.session.commit()
    return p


@pytest.fixture()
def auth_headers(app, user):
    with app.app_context():
        token = make_token(user.id)
    return {"Authorization": f"Bearer {token}"}
