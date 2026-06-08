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
