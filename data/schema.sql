-- TradeNow RDS schema (PostgreSQL)
-- Users are authenticated via Auth0; auth0_sub is the Auth0 subject identifier,
-- not a locally-managed password.

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    auth0_sub       VARCHAR(255) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    display_name    VARCHAR(100) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE portfolios (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    base_currency   VARCHAR(3) NOT NULL DEFAULT 'USD',
    cash_balance    NUMERIC(18,2) NOT NULL DEFAULT 100000.00,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE holdings (
    id              SERIAL PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol          VARCHAR(16) NOT NULL,
    quantity        NUMERIC(18,6) NOT NULL DEFAULT 0,
    avg_cost        NUMERIC(18,6) NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, symbol)
);

CREATE TABLE transactions (
    id              SERIAL PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol          VARCHAR(16) NOT NULL,
    side            VARCHAR(4) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity        NUMERIC(18,6) NOT NULL CHECK (quantity > 0),
    price            NUMERIC(18,6) NOT NULL CHECK (price > 0),
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE market_trends (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(16) NOT NULL,
    date            DATE NOT NULL,
    close           NUMERIC(18,6) NOT NULL,
    ma_7d           NUMERIC(18,6),
    ma_30d          NUMERIC(18,6),
    trend           VARCHAR(4),
    UNIQUE (symbol, date)
);

CREATE TABLE alerts (
    id              SERIAL PRIMARY KEY,
    portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    alert_type      VARCHAR(32) NOT NULL,
    message         TEXT NOT NULL,
    threshold_pct   NUMERIC(6,3),
    triggered_value NUMERIC(18,6),
    is_read         BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_portfolios_user_id ON portfolios(user_id);
CREATE INDEX idx_holdings_portfolio_id ON holdings(portfolio_id);
CREATE INDEX idx_transactions_portfolio_id ON transactions(portfolio_id);
CREATE INDEX idx_alerts_portfolio_id ON alerts(portfolio_id);
