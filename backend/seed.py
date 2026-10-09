"""Seed a demo user with a sample portfolio for local/manual testing.

Usage: python seed.py
"""

from app import create_app
from extensions import db
from models import Holding, Portfolio, User

DEMO_AUTH0_SUB = "demo|tradenow-seed-user"

SEED_HOLDINGS = [
    ("AAPL", 10, 180.00),
    ("MSFT", 5, 410.00),
    ("BTC-USD", 0.25, 61000.00),
]


def main():
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(auth0_sub=DEMO_AUTH0_SUB).first()
        if user is None:
            user = User(
                auth0_sub=DEMO_AUTH0_SUB,
                email="demo@tradenow.local",
                display_name="Demo User",
            )
            db.session.add(user)
            db.session.commit()

        portfolio = Portfolio.query.filter_by(user_id=user.id, name="Demo Portfolio").first()
        if portfolio is None:
            portfolio = Portfolio(user_id=user.id, name="Demo Portfolio", cash_balance=50000.00)
            db.session.add(portfolio)
            db.session.commit()

        for ticker, quantity, avg_cost in SEED_HOLDINGS:
            holding = Holding.query.filter_by(portfolio_id=portfolio.id, ticker=ticker).first()
            if holding is None:
                db.session.add(Holding(portfolio_id=portfolio.id, ticker=ticker, quantity=quantity, avg_cost=avg_cost))
        db.session.commit()

        print(f"Seeded user id={user.id} ({user.email}), portfolio id={portfolio.id} with {len(SEED_HOLDINGS)} holdings")


if __name__ == "__main__":
    main()
