-- Centrica Energy — Synthetic Trading Data Schema
-- PostgreSQL 14+

DROP TABLE IF EXISTS market_data CASCADE;
DROP TABLE IF EXISTS risk_metrics CASCADE;
DROP TABLE IF EXISTS daily_pnl CASCADE;
DROP TABLE IF EXISTS positions CASCADE;
DROP TABLE IF EXISTS trades CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS counterparties CASCADE;
DROP TABLE IF EXISTS traders CASCADE;
DROP TABLE IF EXISTS desks CASCADE;

-- ===== Reference Tables =====

CREATE TABLE desks (
    desk_id         TEXT PRIMARY KEY,
    desk_name       TEXT NOT NULL,
    desk_head       TEXT NOT NULL,
    region          TEXT NOT NULL,
    commodity       TEXT NOT NULL
);

CREATE TABLE traders (
    trader_id       TEXT PRIMARY KEY,
    trader_name     TEXT NOT NULL,
    desk_id         TEXT NOT NULL REFERENCES desks(desk_id),
    seniority       TEXT NOT NULL CHECK (seniority IN ('junior', 'senior', 'head')),
    start_date      DATE NOT NULL
);

CREATE TABLE counterparties (
    counterparty_id   TEXT PRIMARY KEY,
    counterparty_name TEXT NOT NULL,
    counterparty_type TEXT NOT NULL CHECK (counterparty_type IN ('utility', 'bank', 'industrial', 'sovereign', 'trading_house', 'oil_major')),
    credit_rating     TEXT NOT NULL,
    country           TEXT NOT NULL
);

CREATE TABLE products (
    product_id    TEXT PRIMARY KEY,
    product_name  TEXT NOT NULL,
    product_type  TEXT NOT NULL CHECK (product_type IN ('power', 'gas', 'lng', 'carbon', 'renewable_certificate')),
    unit          TEXT NOT NULL,
    currency      TEXT NOT NULL
);

-- ===== Transactional Tables =====

CREATE TABLE trades (
    trade_id            BIGINT PRIMARY KEY,
    trade_date          DATE NOT NULL,
    desk_id             TEXT NOT NULL REFERENCES desks(desk_id),
    trader_id           TEXT NOT NULL REFERENCES traders(trader_id),
    counterparty_id     TEXT NOT NULL REFERENCES counterparties(counterparty_id),
    product_id          TEXT NOT NULL REFERENCES products(product_id),
    direction           TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
    quantity            NUMERIC(16,2) NOT NULL,
    price               NUMERIC(12,4) NOT NULL,
    currency            TEXT NOT NULL,
    delivery_start      DATE NOT NULL,
    delivery_end        DATE NOT NULL,
    trade_status        TEXT NOT NULL DEFAULT 'confirmed' CHECK (trade_status IN ('confirmed', 'pending', 'cancelled')),
    booking_system_ref  TEXT
);

CREATE INDEX idx_trades_desk_date ON trades(desk_id, trade_date);
CREATE INDEX idx_trades_counterparty ON trades(counterparty_id);
CREATE INDEX idx_trades_trader ON trades(trader_id);
CREATE INDEX idx_trades_product ON trades(product_id);

CREATE TABLE positions (
    position_id     BIGSERIAL PRIMARY KEY,
    position_date   DATE NOT NULL,
    desk_id         TEXT NOT NULL REFERENCES desks(desk_id),
    product_id      TEXT NOT NULL REFERENCES products(product_id),
    net_quantity    NUMERIC(16,2) NOT NULL,
    avg_price       NUMERIC(12,4) NOT NULL,
    market_price    NUMERIC(12,4) NOT NULL,
    unrealized_pnl  NUMERIC(16,2) NOT NULL,
    currency        TEXT NOT NULL
);

CREATE INDEX idx_positions_desk_date ON positions(desk_id, position_date);

CREATE TABLE daily_pnl (
    pnl_id          BIGSERIAL PRIMARY KEY,
    pnl_date        DATE NOT NULL,
    desk_id         TEXT NOT NULL REFERENCES desks(desk_id),
    trader_id       TEXT NOT NULL REFERENCES traders(trader_id),
    realized_pnl    NUMERIC(16,2) NOT NULL,
    unrealized_pnl  NUMERIC(16,2) NOT NULL,
    total_pnl       NUMERIC(16,2) NOT NULL,
    currency        TEXT NOT NULL
);

CREATE INDEX idx_pnl_desk_date ON daily_pnl(desk_id, pnl_date);

CREATE TABLE risk_metrics (
    risk_id                         BIGSERIAL PRIMARY KEY,
    risk_date                       DATE NOT NULL,
    desk_id                         TEXT NOT NULL REFERENCES desks(desk_id),
    var_1d_95                       NUMERIC(14,2) NOT NULL,
    var_limit                       NUMERIC(14,2) NOT NULL,
    var_utilization_pct             NUMERIC(5,2) NOT NULL,
    max_counterparty_concentration_pct NUMERIC(5,2) NOT NULL,
    concentration_limit_pct         NUMERIC(5,2) NOT NULL,
    greeks_delta                    NUMERIC(16,2),
    greeks_gamma                    NUMERIC(16,4),
    greeks_vega                     NUMERIC(16,2)
);

CREATE INDEX idx_risk_desk_date ON risk_metrics(desk_id, risk_date);

CREATE TABLE market_data (
    market_data_id  BIGSERIAL PRIMARY KEY,
    observation_date DATE NOT NULL,
    product_id       TEXT NOT NULL REFERENCES products(product_id),
    spot_price       NUMERIC(12,4) NOT NULL,
    forward_1m       NUMERIC(12,4),
    forward_3m       NUMERIC(12,4),
    forward_6m       NUMERIC(12,4),
    forward_1y       NUMERIC(12,4),
    daily_change_pct NUMERIC(8,4),
    currency         TEXT NOT NULL
);

CREATE INDEX idx_market_data_product_date ON market_data(product_id, observation_date);
