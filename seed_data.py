#!/usr/bin/env python3
"""
Centrica Energy — Synthetic Trading Data Generator

Generates realistic energy-trading data with seeded anomalies for a DANA demo.
Uses numpy seed=42 for full reproducibility.

Anomalies embedded:
  1. UK Power desk: £2.1M loss on 2026-06-05 driven by Vitol (CP_884)
     — outsized baseload forward fill at £82.40 vs book avg £78.20
  2. LNG Trading desk: Shell Energy = 28% concentration (threshold 20%)
  3. Continental Gas desk: 2 stale marks (positions not revalued for 3 trading days)
  4. Carbon desk: VaR breach — £4.2M vs £3.5M limit

LNG cargo → cross-region arbitrage anomalies:
  A1. Missed diversion arb: CRG_0007 (Arctic Voyager) locked to Europe while
      Asia net arb = $1.80/MMBtu on 3.5M MMBtu ⇒ ~$6.3M left on the table
  A2. Load-port concentration: Sabine Pass ≈ 28% of in-transit volume (20% limit)
  A3. Stale AIS: 2 cargoes frozen Jun 4 → 8 (ais_status='stale')
  A4. Spread dislocation: net_arb past the $1.50 band to >$2.50/MMBtu from Jun 3

Usage:
    python seed_data.py          # writes seed_data.sql
"""
from __future__ import annotations

import datetime as dt
import math
import numpy as np
from pathlib import Path

np.random.seed(42)

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def trading_days(end: dt.date, n: int) -> list[dt.date]:
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(days))

AS_OF = dt.date(2026, 6, 8)          # last completed trading day
ALL_DAYS_90 = trading_days(AS_OF, 65) # ~90 calendar days ≈ 65 trading days
ALL_DAYS_30 = [d for d in ALL_DAYS_90 if d >= AS_OF - dt.timedelta(days=45)]  # last ~30 trading days
ANOMALY_DAY = dt.date(2026, 6, 5)    # UK Power P&L anomaly

DELIVERY_PERIODS = [
    ("2026-07-01", "2026-09-30", "Q3 2026"),
    ("2026-10-01", "2026-12-31", "Q4 2026"),
    ("2027-01-01", "2027-12-31", "Cal 2027"),
]

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
DESKS = [
    ("DESK_UKP",  "UK Power",            "Sarah Mitchell",  "UK",     "power"),
    ("DESK_GAS",  "Continental Gas",      "Hans Richter",    "Europe", "gas"),
    ("DESK_LNG",  "LNG Trading",         "David Chen",      "Global", "lng"),
    ("DESK_REN",  "Renewables",          "Emma Johansson",  "UK",     "renewables"),
    ("DESK_CRB",  "Carbon & Emissions",  "Marc Dupont",     "Europe", "carbon"),
]

TRADERS = [
    # UK Power (4)
    ("TR_001", "James Carter",       "DESK_UKP", "head",   "2018-03-12"),
    ("TR_002", "Sophie Patel",       "DESK_UKP", "senior", "2020-06-01"),
    ("TR_003", "Michael Hughes",     "DESK_UKP", "senior", "2019-11-15"),
    ("TR_004", "Lucy Freeman",       "DESK_UKP", "junior", "2024-01-08"),
    # Continental Gas (4)
    ("TR_005", "Lars Müller",        "DESK_GAS", "head",   "2017-09-20"),
    ("TR_006", "Paolo Rossi",        "DESK_GAS", "senior", "2019-04-14"),
    ("TR_007", "Anna Kowalski",      "DESK_GAS", "senior", "2021-02-01"),
    ("TR_008", "Felix Braun",        "DESK_GAS", "junior", "2025-03-10"),
    # LNG Trading (3)
    ("TR_009", "Kenji Tanaka",       "DESK_LNG", "head",   "2016-07-01"),
    ("TR_010", "Diana Chen",         "DESK_LNG", "senior", "2020-08-15"),
    ("TR_011", "Alexei Petrov",      "DESK_LNG", "junior", "2024-06-01"),
    # Renewables (3)
    ("TR_012", "Elena Walsh",        "DESK_REN", "head",   "2019-01-07"),
    ("TR_013", "Rory Green",         "DESK_REN", "senior", "2021-10-01"),
    ("TR_014", "Freya Lindqvist",    "DESK_REN", "junior", "2025-01-15"),
    # Carbon & Emissions (3)
    ("TR_015", "Thomas Durand",      "DESK_CRB", "head",   "2018-05-20"),
    ("TR_016", "Isabel Navarro",     "DESK_CRB", "senior", "2020-03-01"),
    ("TR_017", "Oliver Becker",      "DESK_CRB", "junior", "2024-09-01"),
]

COUNTERPARTIES = [
    ("CP_001", "EDF Trading",               "utility",       "A",    "France"),
    ("CP_002", "Vitol",                      "trading_house", "BBB+", "Netherlands"),
    ("CP_003", "Trafigura",                  "trading_house", "BBB",  "Singapore"),
    ("CP_004", "Shell Energy",               "oil_major",     "AA-",  "UK"),
    ("CP_005", "RWE Supply & Trading",       "utility",       "A-",   "Germany"),
    ("CP_006", "Engie",                      "utility",       "A",    "France"),
    ("CP_007", "Vattenfall",                 "utility",       "A-",   "Sweden"),
    ("CP_008", "Statkraft",                  "utility",       "A",    "Norway"),
    ("CP_009", "Equinor",                    "oil_major",     "AA-",  "Norway"),
    ("CP_010", "TotalEnergies Trading",      "oil_major",     "A+",   "France"),
    ("CP_011", "BP Gas Marketing",           "oil_major",     "A",    "UK"),
    ("CP_012", "Ørsted",                     "utility",       "BBB+", "Denmark"),
    ("CP_013", "Axpo",                       "utility",       "A-",   "Switzerland"),
    ("CP_014", "Uniper",                     "utility",       "BBB",  "Germany"),
    ("CP_015", "Gazprom Marketing",          "sovereign",     "BB+",  "Russia"),
    ("CP_016", "Mercuria Energy",            "trading_house", "BBB",  "Switzerland"),
    ("CP_017", "Gunvor Group",               "trading_house", "BBB-", "Cyprus"),
    ("CP_018", "Koch Supply & Trading",      "industrial",    "A",    "USA"),
    ("CP_019", "Macquarie Group",            "bank",          "A+",   "Australia"),
    ("CP_020", "Goldman Sachs Commodities",  "bank",          "A+",   "USA"),
    ("CP_021", "Centrica Energy Marketing",  "utility",       "BBB+", "UK"),
    ("CP_022", "SSE Energy Supply",          "utility",       "A-",   "UK"),
    ("CP_023", "Drax Group",                 "utility",       "BBB",  "UK"),
    ("CP_024", "EDP Renewables",             "utility",       "BBB+", "Portugal"),
    ("CP_025", "Naturgy",                    "utility",       "BBB",  "Spain"),
    ("CP_026", "PGNiG",                      "sovereign",     "BBB+", "Poland"),
    ("CP_027", "JERA",                       "industrial",    "A",    "Japan"),
    ("CP_028", "Korea Gas Corporation",      "sovereign",     "AA-",  "South Korea"),
    ("CP_029", "Pertamina",                  "sovereign",     "BBB",  "Indonesia"),
    ("CP_030", "Pavilion Energy",            "industrial",    "A-",   "Singapore"),
]

PRODUCTS = [
    ("PRD_UKBL",  "UK Baseload Power",                    "power",                 "MWh",   "GBP"),
    ("PRD_UKPK",  "UK Peak Power",                        "power",                 "MWh",   "GBP"),
    ("PRD_NBP",   "NBP Natural Gas",                      "gas",                   "therm", "GBP"),
    ("PRD_TTF",   "TTF Natural Gas",                      "gas",                   "MWh",   "EUR"),
    ("PRD_HH",    "Henry Hub Natural Gas",                "gas",                   "MMBtu", "USD"),
    ("PRD_JKM",   "JKM LNG",                              "lng",                   "MMBtu", "USD"),
    ("PRD_BLNG",  "Brent-linked LNG",                     "lng",                   "MMBtu", "USD"),
    ("PRD_EUA",   "EU Carbon Allowances (EUA)",           "carbon",                "tonne", "EUR"),
    ("PRD_UKA",   "UK Emission Allowances (UKA)",         "carbon",                "tonne", "GBP"),
    ("PRD_ROC",   "Renewable Obligation Certificates",    "renewable_certificate", "ROC",   "GBP"),
    ("PRD_GOO",   "Guarantee of Origin (GoO)",            "renewable_certificate", "MWh",   "EUR"),
]

# Desk→product mapping
DESK_PRODUCTS = {
    "DESK_UKP": ["PRD_UKBL", "PRD_UKPK"],
    "DESK_GAS": ["PRD_NBP", "PRD_TTF", "PRD_HH"],
    "DESK_LNG": ["PRD_JKM", "PRD_BLNG"],
    "DESK_REN": ["PRD_ROC", "PRD_GOO"],
    "DESK_CRB": ["PRD_EUA", "PRD_UKA"],
}

DESK_TRADERS = {}
for t in TRADERS:
    DESK_TRADERS.setdefault(t[2], []).append(t[0])

# Realistic price ranges by product (mid, half-width)
PRICE_RANGES = {
    "PRD_UKBL": (78.0, 8.0),    # £70-86/MWh (centered near £78 for book avg ~78.20)
    "PRD_UKPK": (95.0, 12.0),   # £83-107/MWh
    "PRD_NBP":  (85.0, 15.0),   # 70-100 p/therm
    "PRD_TTF":  (35.0, 10.0),   # €25-45/MWh
    "PRD_HH":   (3.50, 0.80),   # $2.70-4.30/MMBtu
    "PRD_JKM":  (13.0, 3.0),    # $10-16/MMBtu
    "PRD_BLNG": (13.5, 3.0),    # $10.5-16.5/MMBtu
    "PRD_EUA":  (65.0, 10.0),   # €55-75/tonne
    "PRD_UKA":  (45.0, 8.0),    # £37-53/tonne
    "PRD_ROC":  (50.0, 5.0),    # £45-55/ROC
    "PRD_GOO":  (2.50, 0.80),   # €1.70-3.30/MWh
}

PRODUCT_CURRENCIES = {p[0]: p[4] for p in PRODUCTS}

# Quantity ranges by product (min, max) per trade
QTY_RANGES = {
    "PRD_UKBL": (500, 50000),
    "PRD_UKPK": (200, 20000),
    "PRD_NBP":  (10000, 500000),
    "PRD_TTF":  (1000, 100000),
    "PRD_HH":   (5000, 200000),
    "PRD_JKM":  (50000, 500000),
    "PRD_BLNG": (50000, 500000),
    "PRD_EUA":  (500, 50000),
    "PRD_UKA":  (200, 20000),
    "PRD_ROC":  (100, 10000),
    "PRD_GOO":  (500, 50000),
}

# Risk parameters by desk
DESK_RISK = {
    "DESK_UKP": {"var_base": 2_800_000, "var_limit": 4_000_000, "conc_limit": 20.0},
    "DESK_GAS": {"var_base": 2_200_000, "var_limit": 3_500_000, "conc_limit": 20.0},
    "DESK_LNG": {"var_base": 3_000_000, "var_limit": 5_000_000, "conc_limit": 20.0},
    "DESK_REN": {"var_base": 800_000,   "var_limit": 1_500_000, "conc_limit": 25.0},
    "DESK_CRB": {"var_base": 2_500_000, "var_limit": 3_500_000, "conc_limit": 20.0},
}

# ---------------------------------------------------------------------------
# LNG cargo → cross-region arbitrage config
# ---------------------------------------------------------------------------
# Unit math (see Knowledge note 07-arb-economics):
#   TTF_usd_per_mmbtu = (TTF_eur_per_mwh / 3.412) * EURUSD   (1 MWh = 3.412 MMBtu)
#   gross_arb = JKM_usd - TTF_usd
#   net_arb   = gross_arb - (freight_asia - freight_europe) - regas_delta
EURUSD            = 1.08
MWH_PER_MMBTU     = 3.412
FREIGHT_ASIA_USD  = 1.20     # $/MMBtu, US Gulf → Asia (longer voyage)
FREIGHT_EUROPE_USD = 0.80    # $/MMBtu, US Gulf → Europe
REGAS_DELTA_USD   = 0.30     # $/MMBtu regas cost differential
FREIGHT_DELTA_USD = FREIGHT_ASIA_USD - FREIGHT_EUROPE_USD   # 0.40
ALERT_BAND_USD    = 1.50     # net-arb alert band; sustained breach ⇒ dislocation

ARB_DISLOCATION_START = dt.date(2026, 6, 3)   # Anomaly A4: net_arb > $2.50 from here
HERO_REF_DATE         = dt.date(2026, 6, 2)   # Anomaly A1: Asia net_arb = $1.80 reference
AIS_STALE_FREEZE_DATE = dt.date(2026, 6, 4)   # Anomaly A3: AIS frozen Jun 4 → 8

# Vessels (reference table; charterer maps to a counterparty name)
VESSELS = [
    ("VSL_001", "Boreal Trader",     "311021300", 174000, "Shell Energy",          "Bahamas"),
    ("VSL_002", "Pacific Lantern",   "311021301", 180000, "JERA",                  "Marshall Islands"),
    ("VSL_003", "Gulf Mariner",      "311021302", 266000, "Korea Gas Corporation", "Qatar"),
    ("VSL_004", "Nordic Aurora",     "311021303", 174000, "Equinor",               "Norway"),
    ("VSL_005", "Equatorial Star",   "311021304", 160000, "Pavilion Energy",       "Singapore"),
    ("VSL_006", "Atlantic Crown",    "311021305", 174000, "TotalEnergies Trading", "France"),
    ("VSL_007", "Arctic Voyager",    "311021306", 145000, "Shell Energy",          "Bahamas"),
    ("VSL_008", "Iberian Breeze",    "311021307", 174000, "Naturgy",               "Spain"),
    ("VSL_009", "Coral Endeavour",   "311021308", 210000, "Mercuria Energy",       "Malta"),
    ("VSL_010", "Meridian Spirit",   "311021309", 180000, "Trafigura",             "Singapore"),
]

# Approx (lat, lon) for AIS path interpolation
LOAD_COORDS = {
    "Sabine Pass":     (29.73, -93.87),
    "Corpus Christi":  (27.81, -97.41),
    "Cameron":         (29.79, -93.32),
    "Freeport":        (28.95, -95.31),
    "Ras Laffan":      (25.90,  51.60),
}
DISCHARGE_COORDS = {"Europe": (51.45, 1.30), "Asia": (34.60, 138.90)}

# Cargo specs.  CRG_0001-0007 are in_transit (get daily AIS positions).
# (cargo_id, vessel_id, cp_id, load_port, load_region, discharge_region,
#  discharge_port, status, destination_locked, load_date, eta, qty_mmbtu, stale)
CARGOS = [
    ("CRG_0001", "VSL_001", "CP_004", "Sabine Pass",    "US Gulf",     "Europe", None,           "in_transit", False, dt.date(2026,5,24), dt.date(2026,6,13), 3_000_000.00, False),
    ("CRG_0002", "VSL_002", "CP_027", "Corpus Christi", "US Gulf",     "Asia",   None,           "in_transit", False, dt.date(2026,5,18), dt.date(2026,6,17), 2_800_000.00, False),
    ("CRG_0003", "VSL_003", "CP_028", "Ras Laffan",     "Middle East", "Asia",   None,           "in_transit", False, dt.date(2026,5,26), dt.date(2026,6,12), 3_500_000.00, True),
    ("CRG_0004", "VSL_004", "CP_009", "Cameron",        "US Gulf",     "Europe", None,           "in_transit", False, dt.date(2026,5,21), dt.date(2026,6,14), 4_200_000.00, False),
    ("CRG_0005", "VSL_005", "CP_030", "Freeport",       "US Gulf",     "Asia",   None,           "in_transit", False, dt.date(2026,5,15), dt.date(2026,6,18), 3_100_000.00, True),
    ("CRG_0006", "VSL_006", "CP_010", "Corpus Christi", "US Gulf",     "Europe", None,           "in_transit", False, dt.date(2026,5,23), dt.date(2026,6,15), 2_800_000.00, False),
    ("CRG_0007", "VSL_007", "CP_004", "Sabine Pass",    "US Gulf",     "Europe", "Isle of Grain","in_transit", True,  dt.date(2026,5,26), dt.date(2026,6,16), 3_500_000.00, False),
    ("CRG_0008", "VSL_008", "CP_025", "Sabine Pass",    "US Gulf",     "Europe", "Zeebrugge",    "discharged", True,  dt.date(2026,4,28), dt.date(2026,5,18), 3_200_000.00, False),
    ("CRG_0009", "VSL_009", "CP_016", "Cameron",        "US Gulf",     "Asia",   "Futtsu",       "discharged", True,  dt.date(2026,4,22), dt.date(2026,5,21), 3_700_000.00, False),
    ("CRG_0010", "VSL_010", "CP_003", "Corpus Christi", "US Gulf",     "Asia",   "Tianjin",      "diverted",   True,  dt.date(2026,5,2),  dt.date(2026,5,30), 3_400_000.00, False),
    ("CRG_0011", "VSL_002", "CP_027", "Freeport",       "US Gulf",     "Asia",   None,           "loading",    False, dt.date(2026,6,6),  dt.date(2026,7,5),  3_300_000.00, False),
    ("CRG_0012", "VSL_005", "CP_030", "Ras Laffan",     "Middle East", "Asia",   None,           "loading",    False, dt.date(2026,6,7),  dt.date(2026,6,27), 3_000_000.00, False),
    ("CRG_0013", "VSL_004", "CP_009", "Cameron",        "US Gulf",     "Europe", None,           "loading",    False, dt.date(2026,6,8),  dt.date(2026,6,30), 3_600_000.00, False),
]

# ---------------------------------------------------------------------------
# SQL escape helpers
# ---------------------------------------------------------------------------
def esc(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float, np.integer, np.floating)):
        return str(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return f"'{v}'"
    s = str(v).replace("'", "''")
    return f"'{s}'"


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------
class DataGen:
    def __init__(self):
        self.sql_lines: list[str] = []
        self.trade_id = 100000
        self.trades_by_desk_day: dict[tuple[str, dt.date], list[dict]] = {}
        self.all_trades: list[dict] = []

    def emit(self, line: str):
        self.sql_lines.append(line)

    def gen_desks(self):
        self.emit("-- Desks")
        for d in DESKS:
            vals = ", ".join(esc(v) for v in d)
            self.emit(f"INSERT INTO desks VALUES ({vals});")

    def gen_traders(self):
        self.emit("\n-- Traders")
        for t in TRADERS:
            vals = ", ".join(esc(v) for v in t)
            self.emit(f"INSERT INTO traders VALUES ({vals});")

    def gen_counterparties(self):
        self.emit("\n-- Counterparties")
        for c in COUNTERPARTIES:
            vals = ", ".join(esc(v) for v in c)
            self.emit(f"INSERT INTO counterparties VALUES ({vals});")

    def gen_products(self):
        self.emit("\n-- Products")
        for p in PRODUCTS:
            vals = ", ".join(esc(v) for v in p)
            self.emit(f"INSERT INTO products VALUES ({vals});")

    def gen_trades(self):
        self.emit("\n-- Trades")
        for day in ALL_DAYS_90:
            for desk_id, _, _, _, _ in DESKS:
                prods = DESK_PRODUCTS[desk_id]
                traders_for_desk = DESK_TRADERS[desk_id]
                n_trades = int(np.random.randint(4, 12))

                for _ in range(n_trades):
                    self.trade_id += 1
                    product_id = np.random.choice(prods)
                    trader_id = np.random.choice(traders_for_desk)
                    cp_id = np.random.choice([c[0] for c in COUNTERPARTIES])
                    direction = np.random.choice(["buy", "sell"])
                    mid, hw = PRICE_RANGES[product_id]
                    price = round(mid + float(np.random.uniform(-hw, hw)), 4)
                    qmin, qmax = QTY_RANGES[product_id]
                    quantity = round(float(np.random.uniform(qmin, qmax)), 2)
                    deliv = DELIVERY_PERIODS[int(np.random.randint(0, len(DELIVERY_PERIODS)))]
                    status_r = np.random.random()
                    status = "confirmed" if status_r < 0.85 else ("pending" if status_r < 0.95 else "cancelled")
                    ref = f"BK-{self.trade_id}"
                    ccy = PRODUCT_CURRENCIES[product_id]

                    trade = dict(
                        trade_id=self.trade_id, trade_date=day, desk_id=desk_id,
                        trader_id=trader_id, counterparty_id=cp_id, product_id=product_id,
                        direction=direction, quantity=quantity, price=price, currency=ccy,
                        delivery_start=deliv[0], delivery_end=deliv[1],
                        trade_status=status, booking_system_ref=ref,
                    )
                    self.all_trades.append(trade)
                    self.trades_by_desk_day.setdefault((desk_id, day), []).append(trade)

                    self.emit(
                        f"INSERT INTO trades VALUES ({esc(self.trade_id)}, {esc(day)}, "
                        f"{esc(desk_id)}, {esc(trader_id)}, {esc(cp_id)}, {esc(product_id)}, "
                        f"{esc(direction)}, {esc(quantity)}, {esc(price)}, {esc(ccy)}, "
                        f"{esc(deliv[0])}, {esc(deliv[1])}, {esc(status)}, {esc(ref)});"
                    )

        # --- Anomaly 1: Vitol (CP_002) outsized UK Power trade on ANOMALY_DAY ---
        self.trade_id += 1
        vitol_trade = dict(
            trade_id=self.trade_id, trade_date=ANOMALY_DAY, desk_id="DESK_UKP",
            trader_id="TR_001", counterparty_id="CP_002", product_id="PRD_UKBL",
            direction="buy", quantity=50000.00, price=82.40, currency="GBP",
            delivery_start="2026-07-01", delivery_end="2026-09-30",
            trade_status="confirmed", booking_system_ref=f"BK-{self.trade_id}",
        )
        self.all_trades.append(vitol_trade)
        self.trades_by_desk_day.setdefault(("DESK_UKP", ANOMALY_DAY), []).append(vitol_trade)
        t = vitol_trade
        self.emit(
            f"INSERT INTO trades VALUES ({esc(t['trade_id'])}, {esc(t['trade_date'])}, "
            f"{esc(t['desk_id'])}, {esc(t['trader_id'])}, {esc(t['counterparty_id'])}, "
            f"{esc(t['product_id'])}, {esc(t['direction'])}, {esc(t['quantity'])}, "
            f"{esc(t['price'])}, {esc(t['currency'])}, {esc(t['delivery_start'])}, "
            f"{esc(t['delivery_end'])}, {esc(t['trade_status'])}, {esc(t['booking_system_ref'])});"
        )

        # --- Anomaly 2: Extra Shell Energy LNG trades to push concentration ---
        for i in range(8):
            self.trade_id += 1
            shell_trade = dict(
                trade_id=self.trade_id,
                trade_date=ALL_DAYS_30[int(np.random.randint(0, len(ALL_DAYS_30)))],
                desk_id="DESK_LNG", trader_id="TR_009",
                counterparty_id="CP_004", product_id="PRD_JKM",
                direction="buy", quantity=round(float(np.random.uniform(200000, 500000)), 2),
                price=round(13.0 + float(np.random.uniform(-2, 2)), 4),
                currency="USD", delivery_start="2026-07-01", delivery_end="2026-09-30",
                trade_status="confirmed", booking_system_ref=f"BK-{self.trade_id}",
            )
            self.all_trades.append(shell_trade)
            self.trades_by_desk_day.setdefault((shell_trade["desk_id"], shell_trade["trade_date"]), []).append(shell_trade)
            t = shell_trade
            self.emit(
                f"INSERT INTO trades VALUES ({esc(t['trade_id'])}, {esc(t['trade_date'])}, "
                f"{esc(t['desk_id'])}, {esc(t['trader_id'])}, {esc(t['counterparty_id'])}, "
                f"{esc(t['product_id'])}, {esc(t['direction'])}, {esc(t['quantity'])}, "
                f"{esc(t['price'])}, {esc(t['currency'])}, {esc(t['delivery_start'])}, "
                f"{esc(t['delivery_end'])}, {esc(t['trade_status'])}, {esc(t['booking_system_ref'])});"
            )

    def gen_market_data(self):
        self.emit("\n-- Market Data (last 30 trading days)")
        # Build price series per product with realistic vol
        volatility = {
            "PRD_UKBL": 0.025, "PRD_UKPK": 0.030,
            "PRD_NBP": 0.020, "PRD_TTF": 0.020, "PRD_HH": 0.018,
            "PRD_JKM": 0.022, "PRD_BLNG": 0.022,
            "PRD_EUA": 0.035, "PRD_UKA": 0.032,
            "PRD_ROC": 0.010, "PRD_GOO": 0.012,
        }
        for prod_id, _, _, _, ccy in PRODUCTS:
            mid, _ = PRICE_RANGES[prod_id]
            vol = volatility[prod_id]
            spot = mid
            for day in ALL_DAYS_30:
                ret = float(np.random.normal(0, vol))
                spot = round(spot * (1 + ret), 4)
                fwd_1m = round(spot * (1 + float(np.random.normal(0.002, 0.005))), 4)
                fwd_3m = round(spot * (1 + float(np.random.normal(0.005, 0.008))), 4)
                fwd_6m = round(spot * (1 + float(np.random.normal(0.008, 0.012))), 4)
                fwd_1y = round(spot * (1 + float(np.random.normal(0.012, 0.015))), 4)
                daily_chg = round(ret * 100, 4)
                self.emit(
                    f"INSERT INTO market_data (observation_date, product_id, spot_price, "
                    f"forward_1m, forward_3m, forward_6m, forward_1y, daily_change_pct, currency) "
                    f"VALUES ({esc(day)}, {esc(prod_id)}, {esc(spot)}, {esc(fwd_1m)}, "
                    f"{esc(fwd_3m)}, {esc(fwd_6m)}, {esc(fwd_1y)}, {esc(daily_chg)}, {esc(ccy)});"
                )

    def gen_positions(self):
        """EOD positions for last 30 days.  Anomaly 3: Continental Gas has 2
        positions whose market_price hasn't changed for 3 trading days (stale marks)."""
        self.emit("\n-- Positions (last 30 trading days)")

        for day in ALL_DAYS_30:
            for desk_id, _, _, _, _ in DESKS:
                for prod_id in DESK_PRODUCTS[desk_id]:
                    mid, hw = PRICE_RANGES[prod_id]
                    net_qty = round(float(np.random.uniform(-30000, 30000)), 2)
                    avg_price = round(mid + float(np.random.uniform(-hw * 0.3, hw * 0.3)), 4)
                    market_price = round(mid + float(np.random.uniform(-hw * 0.5, hw * 0.5)), 4)

                    # Anomaly 3: stale marks on Continental Gas — last 3 days same mkt price
                    if desk_id == "DESK_GAS" and prod_id in ("PRD_NBP", "PRD_TTF"):
                        stale_start = dt.date(2026, 6, 4)
                        if day >= stale_start:
                            # Freeze market_price at the stale_start value
                            market_price = round(mid - hw * 0.1, 4) if prod_id == "PRD_NBP" else round(mid + hw * 0.15, 4)

                    # unrealized_pnl = (market_price - avg_price) * net_quantity for buys
                    # We track net_quantity sign: positive = net long, negative = net short
                    unrealized_pnl = round((market_price - avg_price) * net_qty, 2)
                    ccy = PRODUCT_CURRENCIES[prod_id]

                    self.emit(
                        f"INSERT INTO positions (position_date, desk_id, product_id, net_quantity, "
                        f"avg_price, market_price, unrealized_pnl, currency) VALUES ("
                        f"{esc(day)}, {esc(desk_id)}, {esc(prod_id)}, {esc(net_qty)}, "
                        f"{esc(avg_price)}, {esc(market_price)}, {esc(unrealized_pnl)}, {esc(ccy)});"
                    )

    def gen_daily_pnl(self):
        """Daily P&L per desk per trader.  Anomaly 1: UK Power on ANOMALY_DAY
        shows a £2.1M loss concentrated on James Carter / Vitol."""
        self.emit("\n-- Daily P&L (last 30 trading days)")

        for day in ALL_DAYS_30:
            for desk_id, _, _, _, _ in DESKS:
                desk_traders = DESK_TRADERS[desk_id]
                for trader_id in desk_traders:
                    # Base P&L: random daily figure scaled by desk
                    scale = {"DESK_UKP": 400000, "DESK_GAS": 250000, "DESK_LNG": 500000,
                             "DESK_REN": 100000, "DESK_CRB": 200000}[desk_id]
                    realized = round(float(np.random.normal(0, scale * 0.4)), 2)
                    unrealized = round(float(np.random.normal(0, scale * 0.6)), 2)
                    total = round(realized + unrealized, 2)
                    ccy = {"DESK_UKP": "GBP", "DESK_GAS": "EUR", "DESK_LNG": "USD",
                           "DESK_REN": "GBP", "DESK_CRB": "EUR"}[desk_id]

                    # Anomaly 1: UK Power on ANOMALY_DAY — James Carter gets -£2.1M;
                    # other UKP traders get small P&L so desk total ≈ -£2.1M
                    if desk_id == "DESK_UKP" and day == ANOMALY_DAY:
                        if trader_id == "TR_001":
                            realized = -600000.00
                            unrealized = -1500000.00
                            total = -2100000.00
                        else:
                            realized = round(float(np.random.normal(0, 15000)), 2)
                            unrealized = round(float(np.random.normal(0, 20000)), 2)
                            total = round(realized + unrealized, 2)

                    self.emit(
                        f"INSERT INTO daily_pnl (pnl_date, desk_id, trader_id, realized_pnl, "
                        f"unrealized_pnl, total_pnl, currency) VALUES ("
                        f"{esc(day)}, {esc(desk_id)}, {esc(trader_id)}, {esc(realized)}, "
                        f"{esc(unrealized)}, {esc(total)}, {esc(ccy)});"
                    )

    def gen_risk_metrics(self):
        """Daily risk metrics.  Anomalies 2 (LNG concentration) and 4 (Carbon VaR breach)."""
        self.emit("\n-- Risk Metrics (last 30 trading days)")

        for day in ALL_DAYS_30:
            for desk_id, _, _, _, _ in DESKS:
                params = DESK_RISK[desk_id]
                var_base = params["var_base"]
                var_limit = params["var_limit"]
                conc_limit = params["conc_limit"]

                var_val = round(var_base + float(np.random.normal(0, var_base * 0.15)), 2)

                # Anomaly 4: Carbon VaR breach on recent days
                if desk_id == "DESK_CRB" and day >= dt.date(2026, 6, 3):
                    var_val = round(4200000 + float(np.random.uniform(-100000, 200000)), 2)

                var_util = round((var_val / var_limit) * 100, 2)

                # Concentration
                conc_pct = round(float(np.random.uniform(8, 18)), 2)

                # Anomaly 2: LNG Shell Energy concentration = 28% on recent days
                if desk_id == "DESK_LNG" and day >= dt.date(2026, 5, 25):
                    conc_pct = round(28.0 + float(np.random.uniform(-0.5, 0.5)), 2)

                delta = round(float(np.random.normal(0, 500000)), 2)
                gamma = round(float(np.random.normal(0, 2000)), 4)
                vega = round(float(np.random.normal(0, 100000)), 2)

                self.emit(
                    f"INSERT INTO risk_metrics (risk_date, desk_id, var_1d_95, var_limit, "
                    f"var_utilization_pct, max_counterparty_concentration_pct, "
                    f"concentration_limit_pct, greeks_delta, greeks_gamma, greeks_vega) VALUES ("
                    f"{esc(day)}, {esc(desk_id)}, {esc(var_val)}, {esc(var_limit)}, "
                    f"{esc(var_util)}, {esc(conc_pct)}, {esc(conc_limit)}, "
                    f"{esc(delta)}, {esc(gamma)}, {esc(vega)});"
                )

    # -----------------------------------------------------------------
    # LNG cargo → cross-region arbitrage
    # -----------------------------------------------------------------
    def gen_vessels(self):
        self.emit("\n-- Vessels (LNG carriers)")
        for v in VESSELS:
            vals = ", ".join(esc(x) for x in v)
            self.emit(f"INSERT INTO vessels VALUES ({vals});")

    def gen_cargos(self):
        """LNG cargoes.  Anomaly A1 (CRG_0007 locked to Europe while Asia pays
        more), A2 (Sabine Pass ≈ 28% of in-transit volume), A3 (2 cargoes with a
        frozen last_ais_update)."""
        self.emit("\n-- Cargos")
        for (cargo_id, vessel_id, cp_id, load_port, load_region, discharge_region,
             discharge_port, status, locked, load_date, eta, qty, stale) in CARGOS:
            # Henry-Hub-linked purchase price + route-dependent freight/regas
            purchase_price = round(9.50 + float(np.random.uniform(-0.8, 0.8)), 4)
            base_freight = FREIGHT_ASIA_USD if discharge_region == "Asia" else FREIGHT_EUROPE_USD
            freight = round(base_freight + float(np.random.uniform(-0.10, 0.10)), 4)
            regas = round(REGAS_DELTA_USD + float(np.random.uniform(-0.05, 0.05)), 4)

            if stale:
                last_ais = dt.datetime.combine(AIS_STALE_FREEZE_DATE, dt.time(6, 0, 0))
            elif status == "in_transit":
                last_ais = dt.datetime.combine(AS_OF, dt.time(6, 0, 0))
            elif status == "loading":
                last_ais = dt.datetime.combine(load_date, dt.time(6, 0, 0))
            else:  # discharged / diverted
                last_ais = dt.datetime.combine(eta, dt.time(6, 0, 0))

            self.emit(
                f"INSERT INTO cargos VALUES ({esc(cargo_id)}, {esc(vessel_id)}, "
                f"{esc(cp_id)}, {esc(load_port)}, {esc(load_region)}, "
                f"{esc(discharge_region)}, {esc(discharge_port)}, {esc(status)}, "
                f"{esc(locked)}, {esc(load_date)}, {esc(eta)}, {esc(qty)}, "
                f"{esc(purchase_price)}, {esc(freight)}, {esc(regas)}, {esc(last_ais)});"
            )

    def gen_cargo_positions(self):
        """Daily AIS snapshots for in-transit cargoes.  Anomaly A3: the 2 stale
        cargoes have lat/lon/eta frozen at the Jun-4 snapshot from Jun 4 → 8."""
        self.emit("\n-- Cargo Positions (daily AIS, in-transit cargoes)")

        def bearing(a, b):
            lat1, lon1 = map(math.radians, a)
            lat2, lon2 = map(math.radians, b)
            dlon = lon2 - lon1
            x = math.sin(dlon) * math.cos(lat2)
            y = (math.cos(lat1) * math.sin(lat2)
                 - math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
            return round((math.degrees(math.atan2(x, y)) + 360) % 360, 1)

        for idx, c in enumerate(CARGOS):
            (cargo_id, vessel_id, cp_id, load_port, load_region, discharge_region,
             discharge_port, status, locked, load_date, eta, qty, stale) = c
            if status != "in_transit":
                continue
            load_xy = LOAD_COORDS[load_port]
            disc_xy = DISCHARGE_COORDS[discharge_region]
            hdg = bearing(load_xy, disc_xy)
            voyage_days = max((eta - load_date).days, 1)

            for day in ALL_DAYS_30:
                eff_date = day
                ais_status = "live"
                if stale and day >= AIS_STALE_FREEZE_DATE:
                    eff_date = AIS_STALE_FREEZE_DATE   # freeze position/eta
                    ais_status = "stale"
                dit = max((eff_date - load_date).days, 0)
                frac = min(dit / voyage_days, 1.0)
                lat = round(load_xy[0] + frac * (disc_xy[0] - load_xy[0]), 5)
                lon = round(load_xy[1] + frac * (disc_xy[1] - load_xy[1]), 5)
                speed = round(14.5 + (idx % 3) * 0.7, 2) if 0.0 < frac < 1.0 else 0.0
                self.emit(
                    f"INSERT INTO cargo_positions (obs_date, cargo_id, lat, lon, "
                    f"speed_knots, heading_deg, eta, dest_region, days_in_transit, "
                    f"ais_status) VALUES ({esc(day)}, {esc(cargo_id)}, {esc(lat)}, "
                    f"{esc(lon)}, {esc(speed)}, {esc(hdg)}, {esc(eta)}, "
                    f"{esc(discharge_region)}, {esc(dit)}, {esc(ais_status)});"
                )

    def gen_arb_spreads(self):
        """Daily JKM–TTF cross-region arb spread (chart-ready).  Anomaly A4: the
        net arb blows past the $1.50 alert band to >$2.50/MMBtu from Jun 3.
        The Jun-2 row is engineered to net_arb = $1.80 (the CRG_0007 reference)."""
        self.emit("\n-- Arb Spreads (JKM–TTF cross-region, last 30 trading days)")
        # TTF (€/MWh) follows the same random-walk logic as market_data; JKM is
        # modelled as TTF_usd + the (engineered) net arb + freight/regas deltas so
        # the JKM–TTF spread series stays formula-consistent and chart-ready.
        ttf_eur = PRICE_RANGES["PRD_TTF"][0]   # 35.0
        ttf_vol = 0.020

        for i, day in enumerate(ALL_DAYS_30):
            ttf_eur = round(ttf_eur * (1 + float(np.random.normal(0, ttf_vol))), 4)
            ttf_usd = round((ttf_eur / MWH_PER_MMBTU) * EURUSD, 4)

            # Baseline net arb sits calmly inside the $1.50 alert band ...
            net = round(1.05 + 0.20 * math.sin(i / 3.0)
                        + float(np.random.normal(0, 0.05)), 4)
            # ... A1 reference: Jun-2 ticks up to exactly $1.80 (Asia) ...
            if day == HERO_REF_DATE:
                net = 1.80
            # ... A4: from Jun-3 the spread dislocates well past $2.50.
            elif day >= ARB_DISLOCATION_START:
                net = round(2.65 + float(np.random.uniform(-0.10, 0.18)), 4)

            jkm = round(ttf_usd + net + FREIGHT_DELTA_USD + REGAS_DELTA_USD, 4)
            gross = round(jkm - ttf_usd, 4)
            favored = "Asia" if net > 0 else "Europe"
            self.emit(
                f"INSERT INTO arb_spreads (obs_date, jkm_usd_mmbtu, ttf_usd_mmbtu, "
                f"gross_arb_usd, net_arb_usd, favored_region, alert_band_usd) VALUES ("
                f"{esc(day)}, {esc(jkm)}, {esc(ttf_usd)}, {esc(gross)}, {esc(net)}, "
                f"{esc(favored)}, {esc(ALERT_BAND_USD)});"
            )

    def write_sql(self, path: str):
        with open(path, "w") as f:
            f.write("-- Auto-generated synthetic data (seed=42). DO NOT EDIT.\n")
            f.write("-- Generated by seed_data.py\n\n")
            f.write("BEGIN;\n\n")
            for line in self.sql_lines:
                f.write(line + "\n")
            f.write("\nCOMMIT;\n")

    def summary(self):
        n_trades = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO trades"))
        n_positions = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO positions"))
        n_pnl = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO daily_pnl"))
        n_risk = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO risk_metrics"))
        n_market = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO market_data"))
        n_vessels = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO vessels"))
        n_cargos = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO cargos"))
        n_cargo_pos = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO cargo_positions"))
        n_arb = sum(1 for l in self.sql_lines if l.startswith("INSERT INTO arb_spreads"))
        print(f"  trades:          {n_trades}")
        print(f"  positions:       {n_positions}")
        print(f"  daily_pnl:       {n_pnl}")
        print(f"  risk_metrics:    {n_risk}")
        print(f"  market_data:     {n_market}")
        print(f"  vessels:         {n_vessels}")
        print(f"  cargos:          {n_cargos}")
        print(f"  cargo_positions: {n_cargo_pos}")
        print(f"  arb_spreads:     {n_arb}")


def main():
    gen = DataGen()
    gen.gen_desks()
    gen.gen_traders()
    gen.gen_counterparties()
    gen.gen_products()
    gen.gen_trades()
    gen.gen_market_data()
    gen.gen_positions()
    gen.gen_daily_pnl()
    gen.gen_risk_metrics()
    gen.gen_vessels()
    gen.gen_cargos()
    gen.gen_cargo_positions()
    gen.gen_arb_spreads()

    out = Path(__file__).parent / "seed_data.sql"
    gen.write_sql(str(out))
    print(f"✓ Wrote {out}")
    gen.summary()
    print(f"  Total SQL lines: {len(gen.sql_lines)}")


if __name__ == "__main__":
    main()
