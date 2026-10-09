from sqlalchemy import CheckConstraint

from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    auth0_sub = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    portfolios = db.relationship("Portfolio", backref="user", cascade="all, delete-orphan")


class Portfolio(db.Model):
    __tablename__ = "portfolios"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    base_currency = db.Column(db.String(3), nullable=False, default="USD")
    cash_balance = db.Column(db.Numeric(18, 2), nullable=False, default=100000.00)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    holdings = db.relationship("Holding", backref="portfolio", cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", backref="portfolio", cascade="all, delete-orphan")
    alerts = db.relationship("Alert", backref="portfolio", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "base_currency": self.base_currency,
            "cash_balance": float(self.cash_balance),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Holding(db.Model):
    __tablename__ = "holdings"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    ticker = db.Column(db.String(16), nullable=False)
    quantity = db.Column(db.Numeric(18, 6), nullable=False, default=0)
    avg_cost = db.Column(db.Numeric(18, 6), nullable=False, default=0)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (db.UniqueConstraint("portfolio_id", "ticker"),)

    def to_dict(self):
        return {
            "id": self.id,
            "ticker": self.ticker,
            "quantity": float(self.quantity),
            "avg_cost": float(self.avg_cost),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    ticker = db.Column(db.String(16), nullable=False)
    side = db.Column(db.String(4), nullable=False)
    quantity = db.Column(db.Numeric(18, 6), nullable=False)
    price = db.Column(db.Numeric(18, 6), nullable=False)
    executed_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    __table_args__ = (CheckConstraint("side IN ('BUY', 'SELL')"),)

    def to_dict(self):
        return {
            "id": self.id,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class MarketTrend(db.Model):
    """Daily close + moving averages per ticker, computed by compute_trends.py on a
    schedule (was an EMR/Spark job writing to S3; folded into a plain script writing
    straight into Postgres once EMR was no longer available)."""

    __tablename__ = "market_trends"

    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(16), nullable=False)
    date = db.Column(db.Date, nullable=False)
    close = db.Column(db.Numeric(18, 6), nullable=False)
    ma_7d = db.Column(db.Numeric(18, 6))
    ma_30d = db.Column(db.Numeric(18, 6))
    trend = db.Column(db.String(4))

    __table_args__ = (db.UniqueConstraint("ticker", "date"),)

    def to_dict(self):
        return {
            "ticker": self.ticker,
            "date": self.date.isoformat() if self.date else None,
            "close": float(self.close),
            "ma_7d": float(self.ma_7d) if self.ma_7d is not None else None,
            "ma_30d": float(self.ma_30d) if self.ma_30d is not None else None,
            "trend": self.trend,
        }


class WatchlistItem(db.Model):
    """A ticker the user wants to track without necessarily holding it, with an optional
    price-target alert (direction + target_price). Checked by the same scheduled job as
    portfolio value alerts (alerts.py's /internal/check-alerts)."""

    __tablename__ = "watchlist_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = db.Column(db.String(16), nullable=False)
    alert_direction = db.Column(db.String(5))  # 'above' | 'below' | NULL (no alert set)
    target_price = db.Column(db.Numeric(18, 6))
    triggered_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("user_id", "ticker"),
        CheckConstraint("alert_direction IN ('above', 'below')"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "ticker": self.ticker,
            "alert_direction": self.alert_direction,
            "target_price": float(self.target_price) if self.target_price is not None else None,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    alert_type = db.Column(db.String(32), nullable=False)
    message = db.Column(db.Text, nullable=False)
    threshold_pct = db.Column(db.Numeric(6, 3))
    triggered_value = db.Column(db.Numeric(18, 6))
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "message": self.message,
            "threshold_pct": float(self.threshold_pct) if self.threshold_pct is not None else None,
            "triggered_value": float(self.triggered_value) if self.triggered_value is not None else None,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
