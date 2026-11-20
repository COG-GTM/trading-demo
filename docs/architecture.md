# Architecture

`trading-demo` is a synthetic energy-trading dataset for demonstrating DANA (Devin's Data Analyst Agent). It has no application server: Python generators produce SQL and a static HTML dashboard, a shell script loads the SQL into PostgreSQL, and analysts (or DANA) query the database.

![trading-demo architecture](diagrams/architecture.png)

Source: [`diagrams/architecture.dot`](diagrams/architecture.dot) (Graphviz). Regenerate the PNG and [SVG](diagrams/architecture.svg) with `docs/diagrams/render.sh` after editing it (needs `graphviz`).

## Components

| Component | Role |
|-----------|------|
| `schema.sql` | PostgreSQL DDL for 13 tables (9 trading-core, 4 LNG cargo/arbitrage) plus indexes. |
| `seed_data.py` | Deterministic generator (`numpy.random.seed(42)`). All reference data, cargo definitions, arbitrage constants and the 8 seeded anomalies are constants in this file. Writes `seed_data.sql` next to itself. |
| `seed_data.sql` | Committed output of `seed_data.py`: 4,314 `INSERT` statements wrapped in one `BEGIN`/`COMMIT`. Regenerating it reproduces the committed file byte for byte. |
| `setup.sh` | One-shot loader for Debian/Ubuntu: `apt-get install postgresql`, starts the service, **drops and recreates** database `centrica_trading` and role `centrica_demo` (password `demo_password`), loads `schema.sql` then `seed_data.sql` as the `postgres` superuser, then grants the demo role access. Needs `sudo`. |
| PostgreSQL `centrica_trading` | The dataset analysts query. |
| `validate_cargo.py` | Shells out to `psql` (no Python DB driver) against `$CENTRICA_DSN` (default `postgresql://centrica_demo:demo_password@localhost:5432/centrica_trading`) and prints PASS/FAIL for cargo anomalies A1–A4 (README anomalies 5–8); exits 1 if any fail. |
| `dashboard/generate.py` | Writes `dashboard/index.html`. It does **not** connect to the database: the cargo list and the JKM–TTF net-arb series are hard-coded copies of the seeded values. It also reconstructs JKM/TTF legs around the net arb with its own random draws, but the page plots only the net arb. |
| `dashboard/index.html` | Committed, self-contained page (inline CSS and SVG, no scripts, no external requests): KPI tiles, JKM–TTF net-arb chart with the $1.50 alert band and breach shading from 2026-06-03 (the sustained >$2.50 dislocation), cargo tracking map, top-5 diversion opportunities, anomaly desk for A1–A4. |

## Data model

Trading core (from the initial dataset):

- Reference: `desks` (5), `traders` (17, each on one desk), `counterparties` (30), `products` (11).
- Transactional: `trades` (2,564) reference desk, trader, counterparty and product.
- Daily series: `positions` (352), `daily_pnl` (544), `risk_metrics` (160), `market_data` (352).

LNG cargo → cross-region arbitrage layer:

- `vessels` (10) — LNG carriers; `charterer` is a counterparty name (text, not a foreign key).
- `cargos` (13; 7 `in_transit`, 3 `loading`, 2 `discharged`, 1 `diverted`) — references `vessels` and, through `charterer_cp_id`, `counterparties`.
- `cargo_positions` (224) — daily AIS snapshots for in-transit cargoes, `ais_status` `live`/`stale`.
- `arb_spreads` (32) — daily JKM–TTF spread. `seed_data.py` engineers `net_arb_usd` per day (baseline, $1.80 on 2026-06-02, >$2.50 from 2026-06-03) and derives the legs from it: `ttf_usd = ttf_eur / 3.412 * 1.08`, `jkm = ttf_usd + net_arb + 0.40 (freight delta) + 0.30 (regas delta)`, `gross_arb = jkm - ttf_usd`. `arb_spreads` is not computed from `market_data` rows.

The as-of date for every series is 2026-06-08.

## Flows

1. **Generate (optional):** `python seed_data.py` rewrites `seed_data.sql`; `python dashboard/generate.py` rewrites `dashboard/index.html`. Both are deterministic and already committed.
2. **Load:** `./setup.sh` installs PostgreSQL and loads `schema.sql` + `seed_data.sql`.
3. **Analyse:** connect with `psql` (or point DANA at the DSN) and find the anomalies listed in the README.
4. **Validate:** `python validate_cargo.py` checks the four LNG anomalies in the loaded database.
5. **Present:** open `dashboard/index.html` directly in a browser; it needs neither the database nor a network connection.

## Keeping things in sync

The dashboard and `seed_data.py` share numbers but no code. If cargo definitions, arb constants or the anomaly dates in `seed_data.py` change, update the hard-coded lists in `dashboard/generate.py`, regenerate both outputs, and re-run `validate_cargo.py` against a freshly loaded database.
