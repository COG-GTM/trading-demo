-- Centrica Energy — Synthetic Trading Data Schema
-- PostgreSQL 14+

DROP TABLE IF EXISTS arb_spreads CASCADE;
DROP TABLE IF EXISTS cargo_positions CASCADE;
DROP TABLE IF EXISTS cargos CASCADE;
DROP TABLE IF EXISTS vessels CASCADE;
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

-- ===== LNG Cargo → Cross-Region Arbitrage =====

-- Reference table — mirrors counterparties
CREATE TABLE vessels (
    vessel_id     TEXT PRIMARY KEY,         -- 'VSL_001'
    vessel_name   TEXT NOT NULL,            -- 'Arctic Voyager'
    mmsi          TEXT NOT NULL,            -- AIS join key (real feed maps on this)
    capacity_m3   INTEGER NOT NULL,         -- 145000-266000
    charterer     TEXT NOT NULL,            -- maps to a counterparty name
    flag_country  TEXT NOT NULL
);

-- Transactional — mirrors trades
CREATE TABLE cargos (
    cargo_id              TEXT PRIMARY KEY,                 -- 'CRG_0001'
    vessel_id             TEXT NOT NULL REFERENCES vessels(vessel_id),
    charterer_cp_id       TEXT NOT NULL REFERENCES counterparties(counterparty_id),
    load_port             TEXT NOT NULL,                    -- 'Sabine Pass'
    load_region           TEXT NOT NULL,                    -- 'US Gulf' | 'Middle East'
    discharge_region      TEXT NOT NULL CHECK (discharge_region IN ('Europe','Asia')),
    discharge_port        TEXT,                             -- nullable while divertible
    status                TEXT NOT NULL CHECK (status IN ('loading','in_transit','discharged','diverted')),
    destination_locked    BOOLEAN NOT NULL,                 -- FALSE = divertible (arb-able)
    load_date             DATE NOT NULL,
    eta                   DATE NOT NULL,
    qty_mmbtu             NUMERIC(16,2) NOT NULL,           -- ~3.0M-3.8M per std cargo
    purchase_price_usd    NUMERIC(12,4) NOT NULL,           -- $/MMBtu (HH-linked)
    freight_usd_mmbtu     NUMERIC(10,4) NOT NULL,           -- route-dependent
    regas_usd_mmbtu       NUMERIC(10,4) NOT NULL,
    last_ais_update       TIMESTAMP NOT NULL                -- staleness detector reads this
);
CREATE INDEX idx_cargos_status ON cargos(status);
CREATE INDEX idx_cargos_eta ON cargos(eta);

-- Daily AIS time series — mirrors positions/market_data
CREATE TABLE cargo_positions (
    cargo_pos_id   BIGSERIAL PRIMARY KEY,
    obs_date       DATE NOT NULL,
    cargo_id       TEXT NOT NULL REFERENCES cargos(cargo_id),
    lat            NUMERIC(9,5) NOT NULL,
    lon            NUMERIC(9,5) NOT NULL,
    speed_knots    NUMERIC(5,2) NOT NULL,
    heading_deg    NUMERIC(5,1) NOT NULL,
    eta            DATE NOT NULL,
    dest_region    TEXT NOT NULL,                  -- snapshot of intended destination
    days_in_transit INTEGER NOT NULL,
    ais_status     TEXT NOT NULL CHECK (ais_status IN ('live','stale'))
);
CREATE INDEX idx_cargo_pos_cargo_date ON cargo_positions(cargo_id, obs_date);

-- Daily, chart-ready — mirrors market_data
CREATE TABLE arb_spreads (
    arb_id            BIGSERIAL PRIMARY KEY,
    obs_date          DATE NOT NULL,
    jkm_usd_mmbtu     NUMERIC(10,4) NOT NULL,      -- from market_data PRD_JKM
    ttf_usd_mmbtu     NUMERIC(10,4) NOT NULL,      -- PRD_TTF converted via 3.412 & EURUSD
    gross_arb_usd     NUMERIC(10,4) NOT NULL,      -- jkm - ttf
    net_arb_usd       NUMERIC(10,4) NOT NULL,      -- after freight + regas deltas
    favored_region    TEXT NOT NULL CHECK (favored_region IN ('Europe','Asia')),
    alert_band_usd    NUMERIC(10,4) NOT NULL       -- e.g. 1.50; breach => dislocation
);
CREATE INDEX idx_arb_date ON arb_spreads(obs_date);
