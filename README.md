# Centrica Energy — Synthetic Trading Data Demo

Synthetic energy-trading dataset for demonstrating **DANA** (Devin's Data Analyst Agent) on Centrica-style trading data. Models a post-trade data platform across power, gas, LNG, carbon, and renewables desks.

## Quick Start

```bash
# Generate seed data (if seed_data.sql doesn't exist)
pip install numpy
python seed_data.py

# Set up PostgreSQL and load data
chmod +x setup.sh
./setup.sh

# Connect
psql postgresql://centrica_demo:demo_password@localhost:5432/centrica_trading
```

## Schema

| Table | Description | Rows |
|-------|-------------|------|
| `desks` | 5 trading desks (UK Power, Continental Gas, LNG Trading, Renewables, Carbon & Emissions) | 5 |
| `traders` | 17 traders across desks with seniority levels | 17 |
| `counterparties` | 30 realistic energy sector counterparties | 30 |
| `products` | 11 products (power, gas, LNG, carbon, renewable certificates) | 11 |
| `trades` | Buy/sell trades across all desks, 90-day history | ~2,500+ |
| `positions` | Daily EOD positions for last 30 trading days | ~350 |
| `daily_pnl` | Daily P&L by desk and trader | ~540 |
| `risk_metrics` | VaR, concentration, Greeks per desk per day | ~160 |
| `market_data` | Spot + forward curves per product per day | ~350 |
| `vessels` | LNG carriers (capacity, charterer, flag, MMSI) | 10 |
| `cargos` | LNG cargoes (load/discharge, status, qty, freight) — 7 in-transit | 13 |
| `cargo_positions` | Daily AIS snapshots per in-transit cargo, last 30 days | ~224 |
| `arb_spreads` | Daily JKM–TTF cross-region arb spread (chart-ready) | ~32 |

## LNG Cargo → Cross-Region Arbitrage

Layered on top of the trading data: LNG cargoes, their daily AIS positions, and a
JKM–TTF cross-region arbitrage spread. The arb economics use the existing
`market_data` JKM (`PRD_JKM`, $/MMBtu) and TTF (`PRD_TTF`, €/MWh) benchmarks:

```
TTF_usd_per_mmbtu = (TTF_eur_per_mwh / 3.412) * 1.08   -- MWh→MMBtu, EURUSD
gross_arb         = JKM_usd - TTF_usd
net_arb           = gross_arb - (freight_asia - freight_europe) - regas_delta
cargo_pnl_impact  = net_arb * cargo.qty_mmbtu
```

`favored_region = 'Asia'` when `net_arb > 0`; the `alert_band_usd` ($1.50) flags a
spread dislocation when breached. Validate the cargo anomalies with
`python validate_cargo.py` (prints PASS/FAIL per anomaly).

## Seeded Anomalies

These are embedded in the data for the live demo. DANA should be able to discover each one:

### 1. UK Power Desk — £2.1M P&L Loss (June 5)
- **What:** UK Power desk shows a sharp ~£2.1M loss on 2026-06-05
- **Root cause:** Trader James Carter (TR_001) executed a 50,000 MWh UK Baseload buy with **Vitol (CP_002)** at **£82.40/MWh** — significantly above the book average of ~£78/MWh
- **Discoverable via:** `daily_pnl` → drill into `trades` by counterparty

### 2. LNG Desk — Shell Energy Concentration Breach
- **What:** Shell Energy (CP_004) represents **~28%** of LNG desk exposure, exceeding the **20% concentration limit**
- **Discoverable via:** `risk_metrics.max_counterparty_concentration_pct` vs `concentration_limit_pct`

### 3. Continental Gas Desk — Stale Marks
- **What:** NBP Gas and TTF Gas positions have **unchanged market prices** from June 4–8 (3 trading days frozen at £83.50 and €36.50 respectively)
- **Discoverable via:** `positions.market_price` unchanged across consecutive dates

### 4. Carbon Desk — VaR Breach
- **What:** Daily VaR hit **~£4.2M** against a **£3.5M limit** (~120% utilization) starting June 3
- **Discoverable via:** `risk_metrics.var_1d_95` vs `var_limit` where `var_utilization_pct > 100`

### 5. LNG Cargo — Missed Diversion Arb (CRG_0007)
- **What:** Cargo **CRG_0007** on the **"Arctic Voyager"** (3,500,000 MMBtu) is `destination_locked` to **Europe**, while the Asia net arb is **~$1.80/MMBtu** → roughly **$6.3M** of value left on the table
- **Root cause:** Destination committed before the Asia premium opened up; the vessel can no longer divert
- **Discoverable via:** `cargos` (`destination_locked = TRUE`, `discharge_region = 'Europe'`) × `arb_spreads.favored_region = 'Asia'`; impact = `net_arb_usd × qty_mmbtu`

### 6. LNG Load-Port Concentration — Sabine Pass
- **What:** **Sabine Pass** accounts for **~28%** of in-transit cargo volume, over the **20%** single-load-port limit
- **Root cause:** Multiple cargoes (incl. the hero CRG_0007) loading at the same US Gulf terminal
- **Discoverable via:** `cargos` grouped by `load_port` for `status = 'in_transit'`, share of total `qty_mmbtu`

### 7. Stale AIS — Frozen Vessel Tracking
- **What:** **2 cargoes** (CRG_0003, CRG_0005) have **frozen** `cargo_positions` (lat/lon/eta unchanged) and a `last_ais_update` stuck at **2026-06-04** through 2026-06-08 (3+ days), flagged `ais_status = 'stale'`
- **Root cause:** Lapsed AIS feed — position/ETA no longer refreshing
- **Discoverable via:** `cargos.last_ais_update` lagging `AS_OF`, or `cargo_positions` with unchanged `lat/lon` across consecutive dates / `ais_status = 'stale'`

### 8. Arb Spread Dislocation — JKM–TTF Blowout
- **What:** Daily `arb_spreads.net_arb_usd` breaches the **$1.50 alert band**, rising to **>$2.50/MMBtu** from **2026-06-03** onward (baseline ~$1.20 beforehand)
- **Root cause:** JKM–TTF spread widening; Asia paying a sustained premium over Europe
- **Discoverable via:** `arb_spreads.net_arb_usd > alert_band_usd` over consecutive dates

## Products & Price Ranges

| Product | Type | Unit | Currency | Price Range |
|---------|------|------|----------|-------------|
| UK Baseload Power | power | MWh | GBP | £70–86 |
| UK Peak Power | power | MWh | GBP | £83–107 |
| NBP Natural Gas | gas | therm | GBP | 70–100p |
| TTF Natural Gas | gas | MWh | EUR | €25–45 |
| Henry Hub Gas | gas | MMBtu | USD | $2.70–4.30 |
| JKM LNG | lng | MMBtu | USD | $10–16 |
| Brent-linked LNG | lng | MMBtu | USD | $10.50–16.50 |
| EU Carbon (EUA) | carbon | tonne | EUR | €55–75 |
| UK Carbon (UKA) | carbon | tonne | GBP | £37–53 |
| ROC | renewable_certificate | ROC | GBP | £45–55 |
| GoO | renewable_certificate | MWh | EUR | €1.70–3.30 |

## Counterparties

30 realistic energy-sector counterparties including: EDF Trading, Vitol, Trafigura, Shell Energy, RWE Supply & Trading, Engie, Vattenfall, Statkraft, Equinor, TotalEnergies Trading, BP Gas Marketing, Ørsted, Axpo, Uniper, Gazprom Marketing, Mercuria, Gunvor, Koch, Macquarie, Goldman Sachs Commodities, and others.

## Reproducibility

All data is generated with `numpy.random.seed(42)`. Running `python seed_data.py` will always produce identical output.

## Files

- `schema.sql` — PostgreSQL DDL
- `seed_data.py` — Python data generator (requires `numpy`)
- `seed_data.sql` — Generated INSERT statements (auto-created by `seed_data.py`)
- `setup.sh` — One-command database setup script
- `validate_cargo.py` — Asserts the 4 LNG cargo arbitrage anomalies reproduce
