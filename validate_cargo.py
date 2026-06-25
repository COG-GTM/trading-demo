#!/usr/bin/env python3
"""Validate the LNG cargo → cross-region arbitrage anomalies in the loaded DB.

Mirrors the project's tooling (shells out to ``psql``, no extra deps) and asserts
each of the 4 seeded cargo anomalies reproduces with the expected figures:

  A1  Missed diversion arb  — CRG_0007 (Arctic Voyager) locked to Europe while
      Asia net arb = $1.80/MMBtu on 3.5M MMBtu  ⇒  ~$6.3M opportunity
  A2  Load-port concentration — Sabine Pass ≈ 28% of in-transit volume (20% limit)
  A3  Stale AIS — 2 cargoes frozen Jun 4 → 8 (lat/lon/eta unchanged, ais='stale')
  A4  Spread dislocation — net_arb > $2.50 vs the $1.50 alert band from Jun 3

Usage:
    python validate_cargo.py
    CENTRICA_DSN=postgresql://user:pw@host:5432/db python validate_cargo.py
"""
from __future__ import annotations

import os
import subprocess
import sys

DSN = os.environ.get(
    "CENTRICA_DSN",
    "postgresql://centrica_demo:demo_password@localhost:5432/centrica_trading",
)

HERO_REF_DATE = "2026-06-02"   # CRG_0007 Asia net-arb reference
DISLOCATION_START = "2026-06-03"
STALE_DATE = "2026-06-04"


def q(sql: str) -> list[list[str]]:
    """Run a query through psql and return rows as lists of string fields."""
    out = subprocess.run(
        ["psql", DSN, "-tAF", "\t", "--no-align", "-c", sql],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed:\n{out.stderr.strip()}")
    return [line.split("\t") for line in out.stdout.strip().splitlines() if line]


def scalar(sql: str) -> str:
    rows = q(sql)
    return rows[0][0] if rows else ""


class Check:
    def __init__(self) -> None:
        self.failed = 0

    def report(self, name: str, ok: bool, detail: str) -> None:
        status = "PASS" if ok else "FAIL"
        if not ok:
            self.failed += 1
        print(f"[{status}] {name}: {detail}")


def main() -> int:
    c = Check()

    # --- A1: Missed diversion arb (CRG_0007) -----------------------------
    row = q(
        "SELECT v.vessel_name, c.destination_locked, c.discharge_region, c.qty_mmbtu "
        "FROM cargos c JOIN vessels v ON v.vessel_id = c.vessel_id "
        "WHERE c.cargo_id = 'CRG_0007';"
    )[0]
    vessel, locked, region, qty = row[0], row[1] == "t", row[2], float(row[3])
    net_arb = float(scalar(
        f"SELECT net_arb_usd FROM arb_spreads WHERE obs_date = '{HERO_REF_DATE}';"
    ))
    favored = scalar(
        f"SELECT favored_region FROM arb_spreads WHERE obs_date = '{HERO_REF_DATE}';"
    )
    opportunity = net_arb * qty
    a1_ok = (
        vessel == "Arctic Voyager" and locked and region == "Europe"
        and abs(qty - 3_500_000) < 1
        and abs(net_arb - 1.80) < 0.01 and favored == "Asia"
        and abs(opportunity - 6_300_000) < 1_000
    )
    c.report(
        "A1 Missed diversion arb", a1_ok,
        f"{vessel} locked={locked} to {region}, Asia net_arb=${net_arb:.2f}/MMBtu "
        f"x {qty:,.0f} MMBtu ⇒ ${opportunity/1e6:.1f}M opportunity (favored={favored})",
    )

    # --- A2: Load-port concentration (Sabine Pass) -----------------------
    sabine_pct = float(scalar(
        "SELECT ROUND(100.0 * SUM(CASE WHEN load_port = 'Sabine Pass' "
        "THEN qty_mmbtu ELSE 0 END) / SUM(qty_mmbtu), 2) "
        "FROM cargos WHERE status = 'in_transit';"
    ))
    top_port = scalar(
        "SELECT load_port FROM cargos WHERE status = 'in_transit' "
        "GROUP BY load_port ORDER BY SUM(qty_mmbtu) DESC LIMIT 1;"
    )
    a2_ok = 27.0 <= sabine_pct <= 29.0 and sabine_pct > 20.0 and top_port == "Sabine Pass"
    c.report(
        "A2 Load-port concentration", a2_ok,
        f"Sabine Pass = {sabine_pct:.1f}% of in-transit volume (limit 20%); "
        f"top load port = {top_port}",
    )

    # --- A3: Stale AIS (2 cargoes frozen Jun 4 → 8) ----------------------
    stale_ids = [r[0] for r in q(
        f"SELECT cargo_id FROM cargos WHERE last_ais_update::date = '{STALE_DATE}' "
        "ORDER BY cargo_id;"
    )]
    frozen_ok = len(stale_ids) == 2
    details = []
    for cid in stale_ids:
        r = q(
            "SELECT COUNT(*), COUNT(DISTINCT (lat, lon)), COUNT(DISTINCT eta), "
            "COUNT(*) FILTER (WHERE ais_status = 'stale') "
            f"FROM cargo_positions WHERE cargo_id = '{cid}' "
            f"AND obs_date BETWEEN '{STALE_DATE}' AND '2026-06-08';"
        )[0]
        n, dpos, deta, nstale = (int(x) for x in r)
        ok = n >= 3 and dpos == 1 and deta == 1 and nstale == n
        frozen_ok = frozen_ok and ok
        details.append(f"{cid}: {n} rows, {dpos} distinct pos, {nstale} stale")
    a3_ok = frozen_ok
    c.report(
        "A3 Stale AIS", a3_ok,
        f"last_ais_update frozen at {STALE_DATE} for {stale_ids}; "
        + "; ".join(details),
    )

    # --- A4: Spread dislocation (net_arb > $2.50 from Jun 3) --------------
    r = q(
        "SELECT MIN(net_arb_usd), MAX(net_arb_usd), MIN(alert_band_usd), "
        "bool_and(net_arb_usd > 2.50), bool_and(favored_region = 'Asia') "
        f"FROM arb_spreads WHERE obs_date >= '{DISLOCATION_START}';"
    )[0]
    mn, mx, band, all_above, all_asia = (
        float(r[0]), float(r[1]), float(r[2]), r[3] == "t", r[4] == "t"
    )
    baseline_max = float(scalar(
        f"SELECT MAX(net_arb_usd) FROM arb_spreads WHERE obs_date < '{HERO_REF_DATE}';"
    ))
    a4_ok = all_above and all_asia and abs(band - 1.50) < 0.01 and baseline_max < 1.50
    c.report(
        "A4 Spread dislocation", a4_ok,
        f"net_arb {mn:.2f}–{mx:.2f} (>$2.50) vs ${band:.2f} band from {DISLOCATION_START}; "
        f"pre-event baseline max ${baseline_max:.2f} (within band)",
    )

    print()
    if c.failed:
        print(f"✗ {c.failed} anomaly check(s) FAILED")
        return 1
    print("✓ All 4 cargo anomalies validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
