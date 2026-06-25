#!/usr/bin/env python3
"""
Centrica Energy — LNG Cargo Arbitrage Dashboard generator.

Deterministic (numpy seed=42). Computes the cargo / arbitrage demo data straight
from the interface contract (CARGO_ARBITRAGE_PLAN.md) and writes a single,
fully self-contained `dashboard/index.html` with the data embedded and every
chart hand-rolled as inline SVG. The output file opens offline in any browser
with ZERO network calls (no CDN, no backend, no build step).

Usage:
    python dashboard/generate.py        # writes dashboard/index.html
"""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

import numpy as np

np.random.seed(42)

# ---------------------------------------------------------------------------
# Contract constants (authoritative — see CARGO_ARBITRAGE_PLAN.md §7)
# ---------------------------------------------------------------------------
AS_OF = dt.date(2026, 6, 8)
AS_OF_LABEL = "08 Jun 2026"
ALERT_BAND = 1.50           # $/MMBtu — net-arb dislocation alert band
BREACH_START = dt.date(2026, 6, 3)
NET_ARB_TODAY = 2.61        # $/MMBtu — JKM–TTF net arb, AS_OF
EURUSD = 1.08
MWH_TO_MMBTU = 3.412

EUROPE = "#3aa6ff"          # Centrica blue
ASIA = "#f5a623"            # amber


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


# ---------------------------------------------------------------------------
# 1. JKM–TTF net-arbitrage series (last 30 trading days)
# ---------------------------------------------------------------------------
def build_arb_series() -> list[dict]:
    days = trading_days(AS_OF, 30)
    rows = []
    # Gentle upward drift; stays mostly inside the $1.50 band early, then the
    # spread dislocates and breaches hard from 2026-06-03.
    base = np.linspace(0.78, 1.42, len(days))
    noise = np.random.normal(0.0, 0.11, len(days))
    for i, d in enumerate(days):
        if d >= BREACH_START:
            # Breach region: net arb blows past the band, rising above $2.50.
            ramp = {
                dt.date(2026, 6, 3): 2.55,
                dt.date(2026, 6, 4): 2.63,
                dt.date(2026, 6, 5): 2.58,
                dt.date(2026, 6, 8): NET_ARB_TODAY,
            }
            net = ramp[d]
        else:
            net = round(float(base[i] + noise[i]), 4)
            net = max(0.45, min(net, 1.62))
        # Reconstruct plausible JKM / TTF legs around the net arb.
        ttf_usd = round(11.40 + float(np.random.normal(0, 0.18)), 4)
        freight_regas_delta = 0.62  # freight_asia − freight_europe + regas delta
        gross = round(net + freight_regas_delta, 4)
        jkm = round(ttf_usd + gross, 4)
        rows.append(
            {
                "date": d,
                "jkm": jkm,
                "ttf": ttf_usd,
                "gross_arb": gross,
                "net_arb": round(net, 2),
                "favored": "Asia" if net > 0 else "Europe",
                "band": ALERT_BAND,
                "breach": net > ALERT_BAND,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 2. Cargoes in transit (map + concentration + diversion table)
# ---------------------------------------------------------------------------
def build_cargoes() -> list[dict]:
    # qty in MMBtu; lat/lon are mid-voyage AIS snapshots.
    # Hero cargo CRG_0007 (Arctic Voyager) is locked to Europe while Asia pays
    # +$1.80/MMBtu → 1.80 × 3.5M ≈ $6.3M left on the table.
    cargoes = [
        dict(cargo_id="CRG_0007", vessel="Arctic Voyager", charterer="Shell Energy",
             load_port="Sabine Pass", load_region="US Gulf", discharge_region="Europe",
             qty=3_500_000, net_arb=1.80, locked=True, ais="live",
             lat=40.5, lon=-45.0, status="in_transit"),
        dict(cargo_id="CRG_0004", vessel="Boston Express", charterer="Vitol",
             load_port="Corpus Christi", load_region="US Gulf", discharge_region="Europe",
             qty=3_620_000, net_arb=0.82, locked=False, ais="stale",
             lat=45.0, lon=-20.0, status="in_transit"),
        dict(cargo_id="CRG_0006", vessel="Gaslog Salem", charterer="TotalEnergies",
             load_port="Freeport", load_region="US Gulf", discharge_region="Asia",
             qty=3_620_000, net_arb=0.58, locked=False, ais="live",
             lat=30.0, lon=130.0, status="in_transit"),
        dict(cargo_id="CRG_0001", vessel="Al Rekayyat", charterer="QatarEnergy",
             load_port="Ras Laffan", load_region="Middle East", discharge_region="Asia",
             qty=3_600_000, net_arb=0.45, locked=False, ais="live",
             lat=12.0, lon=75.0, status="in_transit"),
        dict(cargo_id="CRG_0002", vessel="Mozah", charterer="QatarEnergy",
             load_port="Calcasieu Pass", load_region="US Gulf", discharge_region="Europe",
             qty=3_400_000, net_arb=0.26, locked=False, ais="live",
             lat=42.0, lon=-30.0, status="in_transit"),
        dict(cargo_id="CRG_0003", vessel="Maran Gas Apollo", charterer="Shell Energy",
             load_port="Sabine Pass", load_region="US Gulf", discharge_region="Asia",
             qty=3_400_000, net_arb=0.18, locked=False, ais="live",
             lat=15.0, lon=-80.0, status="in_transit"),
        dict(cargo_id="CRG_0005", vessel="Sevilla Knutsen", charterer="RWE Supply",
             load_port="Cameron", load_region="US Gulf", discharge_region="Asia",
             qty=3_500_000, net_arb=0.12, locked=False, ais="stale",
             lat=5.0, lon=110.0, status="in_transit"),
    ]
    for c in cargoes:
        c["opportunity"] = c["net_arb"] * c["qty"]
    return cargoes


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def fmt_money_m(v: float) -> str:
    return f"${v / 1_000_000:.1f}M"


def fmt_mmbtu(v: float) -> str:
    return f"{v / 1_000_000:.2f}M"


# ---------------------------------------------------------------------------
# SVG: net-arb line chart with shaded alert band + breach highlight
# ---------------------------------------------------------------------------
def svg_line_chart(series: list[dict]) -> str:
    W, H = 920, 320
    ml, mr, mt, mb = 56, 24, 22, 46
    pw, ph = W - ml - mr, H - mt - mb
    vals = [r["net_arb"] for r in series]
    ymin, ymax = 0.0, max(3.0, max(vals) + 0.3)

    def x(i: int) -> float:
        return ml + pw * i / (len(series) - 1)

    def y(v: float) -> float:
        return mt + ph * (1 - (v - ymin) / (ymax - ymin))

    # gridlines + y labels
    grid = []
    yticks = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    for t in yticks:
        if t > ymax:
            continue
        yy = y(t)
        grid.append(
            f'<line x1="{ml}" y1="{yy:.1f}" x2="{ml + pw}" y2="{yy:.1f}" '
            f'stroke="#1d2a3a" stroke-width="1"/>'
            f'<text x="{ml - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'fill="#6b8099" font-size="11">{t:.1f}</text>'
        )

    # shaded alert band 0..1.50
    band_top, band_bot = y(ALERT_BAND), y(0.0)
    band = (
        f'<rect x="{ml}" y="{band_top:.1f}" width="{pw}" '
        f'height="{band_bot - band_top:.1f}" fill="#143b2e" opacity="0.55"/>'
        f'<line x1="{ml}" y1="{band_top:.1f}" x2="{ml + pw}" y2="{band_top:.1f}" '
        f'stroke="#33c08a" stroke-width="1.5" stroke-dasharray="6 4"/>'
        f'<text x="{ml + pw - 6}" y="{band_top - 7:.1f}" text-anchor="end" '
        f'fill="#33c08a" font-size="11">$1.50 alert band</text>'
    )

    # breach shading (from BREACH_START to end)
    bi = next(i for i, r in enumerate(series) if r["date"] >= BREACH_START)
    breach_rect = (
        f'<rect x="{x(bi):.1f}" y="{mt}" width="{ml + pw - x(bi):.1f}" '
        f'height="{ph}" fill="#ff4d4d" opacity="0.10"/>'
        f'<text x="{x(bi) - 6:.1f}" y="{mt + 14}" text-anchor="end" '
        f'fill="#ff7a7a" font-size="11">spread dislocation \u25b6</text>'
    )

    # main net-arb line (split: normal vs breach colouring)
    pts = [(x(i), y(r["net_arb"])) for i, r in enumerate(series)]
    line_norm = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts[: bi + 1])
    line_breach = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts[bi:])
    poly = (
        f'<polyline points="{line_norm}" fill="none" stroke="#3aa6ff" stroke-width="2.5"/>'
        f'<polyline points="{line_breach}" fill="none" stroke="#ff4d4d" stroke-width="2.5"/>'
    )

    # markers in breach region + today's dot
    dots = []
    for i in range(bi, len(series)):
        px, py = pts[i]
        dots.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.2" fill="#ff4d4d"/>')
    tx, ty = pts[-1]
    dots.append(
        f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="5" fill="#ff4d4d" stroke="#fff" stroke-width="1.5"/>'
        f'<text x="{tx - 9:.1f}" y="{ty + 5:.1f}" text-anchor="end" fill="#ff9a9a" '
        f'font-size="13" font-weight="800">${NET_ARB_TODAY:.2f}</text>'
    )

    # x labels (every 5th day)
    xlabels = []
    for i, r in enumerate(series):
        if i % 5 == 0 or i == len(series) - 1:
            xlabels.append(
                f'<text x="{x(i):.1f}" y="{mt + ph + 18}" text-anchor="middle" '
                f'fill="#6b8099" font-size="10">{r["date"].strftime("%d %b")}</text>'
            )

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
        f'aria-label="JKM minus TTF net arbitrage, last 30 trading days">'
        f"{''.join(grid)}{band}{breach_rect}{poly}{''.join(dots)}{''.join(xlabels)}"
        f'<text x="{ml}" y="{mt - 6}" fill="#9fb3c8" font-size="11">$/MMBtu</text>'
        f"</svg>"
    )


# ---------------------------------------------------------------------------
# SVG: simplified cargo-tracking map
# ---------------------------------------------------------------------------
def svg_map(cargoes: list[dict]) -> str:
    W, H = 920, 360
    ml, mr, mt, mb = 8, 8, 8, 8
    pw, ph = W - ml - mr, H - mt - mb
    LON0, LON1 = -100.0, 150.0
    LAT0, LAT1 = 0.0, 65.0

    def px(lon: float) -> float:
        return ml + pw * (lon - LON0) / (LON1 - LON0)

    def py(lat: float) -> float:
        return mt + ph * (1 - (lat - LAT0) / (LAT1 - LAT0))

    # ocean backdrop + lon/lat graticule
    parts = [f'<rect x="{ml}" y="{mt}" width="{pw}" height="{ph}" rx="8" fill="#0b2238"/>']
    for lon in range(-100, 151, 25):
        gx = px(lon)
        parts.append(
            f'<line x1="{gx:.1f}" y1="{mt}" x2="{gx:.1f}" y2="{mt + ph}" '
            f'stroke="#123049" stroke-width="1"/>'
            f'<text x="{gx:.1f}" y="{mt + ph - 4}" text-anchor="middle" '
            f'fill="#3f5e7a" font-size="9">{lon}\u00b0</text>'
        )
    for lat in range(0, 66, 15):
        gy = py(lat)
        parts.append(
            f'<line x1="{ml}" y1="{gy:.1f}" x2="{ml + pw}" y2="{gy:.1f}" '
            f'stroke="#123049" stroke-width="1"/>'
            f'<text x="{ml + 4}" y="{gy - 3:.1f}" fill="#3f5e7a" font-size="9">{lat}\u00b0</text>'
        )

    # cargo dots
    for c in cargoes:
        cx, cy = px(c["lon"]), py(c["lat"])
        color = EUROPE if c["discharge_region"] == "Europe" else ASIA
        if c["ais"] == "stale":
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="11" fill="none" '
                f'stroke="#ff4d4d" stroke-width="2" stroke-dasharray="4 3"/>'
            )
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="{color}" '
            f'stroke="#06121f" stroke-width="1.5"/>'
        )
        label = c["vessel"]
        if c["cargo_id"] == "CRG_0007":
            label = "\u2605 " + label
        parts.append(
            f'<text x="{cx:.1f}" y="{cy - 12:.1f}" text-anchor="middle" '
            f'fill="#cdddee" font-size="10">{html.escape(label)}</text>'
        )

    # legend
    lx, ly = ml + 14, mt + 18
    parts.append(
        f'<g font-size="11" fill="#cdddee">'
        f'<circle cx="{lx}" cy="{ly}" r="6" fill="{EUROPE}"/>'
        f'<text x="{lx + 12}" y="{ly + 4}">Europe-bound</text>'
        f'<circle cx="{lx}" cy="{ly + 22}" r="6" fill="{ASIA}"/>'
        f'<text x="{lx + 12}" y="{ly + 26}">Asia-bound</text>'
        f'<circle cx="{lx}" cy="{ly + 44}" r="7" fill="none" stroke="#ff4d4d" '
        f'stroke-width="2" stroke-dasharray="4 3"/>'
        f'<text x="{lx + 12}" y="{ly + 48}">Stale AIS</text>'
        f"</g>"
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
        f'aria-label="Cargo tracking map">{"".join(parts)}</svg>'
    )


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------
def build_html() -> str:
    series = build_arb_series()
    cargoes = build_cargoes()

    in_transit = [c for c in cargoes if c["status"] == "in_transit"]
    n_in_transit = len(in_transit)
    stale = [c for c in in_transit if c["ais"] == "stale"]

    # load-port concentration (Sabine Pass)
    total_qty = sum(c["qty"] for c in in_transit)
    by_port: dict[str, float] = {}
    for c in in_transit:
        by_port[c["load_port"]] = by_port.get(c["load_port"], 0.0) + c["qty"]
    top_port = max(by_port, key=by_port.get)
    top_port_pct = 100.0 * by_port[top_port] / total_qty

    # top-5 diversion opportunities
    top5 = sorted(cargoes, key=lambda c: c["opportunity"], reverse=True)[:5]
    hero = max(cargoes, key=lambda c: c["opportunity"])

    # KPI cards
    kpis = [
        ("In-transit cargoes", str(n_in_transit), "LNG desk · live AIS", "ok"),
        ("Top diversion opportunity", fmt_money_m(hero["opportunity"]),
         f'{hero["vessel"]} · {hero["cargo_id"]}', "warn"),
        ("Active anomalies", "4", "see anomaly desk below", "warn"),
        ("JKM–TTF net arb (today)", f"${NET_ARB_TODAY:.2f}",
         f"vs ${ALERT_BAND:.2f} band · breached", "alert"),
    ]
    kpi_html = "".join(
        f'<div class="kpi kpi-{tone}">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-value">{html.escape(value)}</div>'
        f'<div class="kpi-sub">{html.escape(sub)}</div>'
        f"</div>"
        for label, value, sub, tone in kpis
    )

    # top-5 table rows
    rows_html = ""
    for c in top5:
        hero_cls = " hero" if c["cargo_id"] == hero["cargo_id"] else ""
        status = "Locked \u2192 EU" if c["locked"] else "Divertible"
        status_cls = "badge-alert" if c["locked"] else "badge-ok"
        route = f'{c["load_region"]} \u2192 {c["discharge_region"]}'
        rows_html += (
            f'<tr class="{hero_cls.strip()}">'
            f'<td class="mono">{c["cargo_id"]}</td>'
            f'<td>{html.escape(c["vessel"])}</td>'
            f'<td>{html.escape(route)}</td>'
            f'<td class="num">{fmt_mmbtu(c["qty"])}</td>'
            f'<td class="num">${c["net_arb"]:.2f}</td>'
            f'<td class="num strong">{fmt_money_m(c["opportunity"])}</td>'
            f'<td><span class="badge {status_cls}">{status}</span></td>'
            f"</tr>"
        )

    # anomaly cards
    stale_ids = ", ".join(c["cargo_id"] for c in stale)
    anomalies = [
        ("Missed diversion arbitrage", fmt_money_m(hero["opportunity"]),
         f'{hero["cargo_id"]} ({hero["vessel"]}) is locked to Europe while Asia '
         f'pays +${hero["net_arb"]:.2f}/MMBtu. {fmt_mmbtu(hero["qty"])} MMBtu '
         f'\u00d7 ${hero["net_arb"]:.2f} \u2248 {fmt_money_m(hero["opportunity"])} '
         f'left on the table.'),
        ("Load-port concentration", f"{top_port_pct:.1f}% vs 20%",
         f'{top_port} accounts for {top_port_pct:.1f}% of in-transit volume \u2014 '
         f'over the 20% single-load-port limit.'),
        ("Stale AIS tracking", f"{len(stale)} cargoes",
         f'{stale_ids} AIS positions frozen Jun 4 \u2192 Jun 8 '
         f'(3+ trading days). Vessel location unknown / unverified.'),
        ("Spread dislocation", f"${NET_ARB_TODAY:.2f} vs $1.50",
         f'JKM\u2013TTF net arb has blown past the $1.50 alert band to '
         f'>$2.50/MMBtu since 2026-06-03.'),
    ]
    anomaly_html = "".join(
        f'<div class="anomaly">'
        f'<div class="anomaly-head">'
        f'<span class="anomaly-num">{i + 1}</span>'
        f'<span class="anomaly-title">{html.escape(title)}</span>'
        f'<span class="anomaly-metric">{html.escape(metric)}</span>'
        f"</div>"
        f'<div class="anomaly-body">{html.escape(body)}</div>'
        f"</div>"
        for i, (title, metric, body) in enumerate(anomalies)
    )

    line_svg = svg_line_chart(series)
    map_svg = svg_map(in_transit)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Centrica Energy · LNG Cargo Arbitrage</title>
<style>
  :root {{
    --bg: #060f18; --panel: #0d1b2a; --panel2: #0e1c2c; --line: #1b2c40;
    --ink: #e8f1fa; --muted: #8aa0b6; --blue: #3aa6ff; --teal: #33c0a8;
    --amber: #f5a623; --red: #ff4d4d;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: radial-gradient(1200px 600px at 70% -10%, #0d2236 0%, #060f18 60%);
    color: var(--ink); font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 22px 22px 48px; }}
  .topbar {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 20px; border: 1px solid var(--line); border-radius: 14px;
    background: linear-gradient(180deg, #0e2236, #0a1828);
  }}
  .brand {{ display: flex; align-items: center; gap: 14px; }}
  .logo {{
    width: 38px; height: 38px; border-radius: 9px;
    background: linear-gradient(135deg, var(--blue), var(--teal));
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; color: #06121f; font-size: 18px;
  }}
  .brand h1 {{ font-size: 18px; margin: 0; letter-spacing: .2px; }}
  .brand .sub {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
  .asof {{ text-align: right; font-size: 12px; color: var(--muted); }}
  .asof b {{ display: block; font-size: 15px; color: var(--ink); }}

  .grid-kpi {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 16px 0; }}
  .kpi {{
    border: 1px solid var(--line); border-radius: 13px; padding: 15px 16px;
    background: linear-gradient(180deg, #0e1d2d, #0a1622); position: relative; overflow: hidden;
  }}
  .kpi::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--teal); }}
  .kpi-warn::before {{ background: var(--amber); }}
  .kpi-alert::before {{ background: var(--red); }}
  .kpi-label {{ font-size: 11.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .6px; }}
  .kpi-value {{ font-size: 30px; font-weight: 800; margin: 7px 0 3px; }}
  .kpi-alert .kpi-value {{ color: var(--red); }}
  .kpi-warn .kpi-value {{ color: var(--amber); }}
  .kpi-sub {{ font-size: 11.5px; color: var(--muted); }}

  .panel {{
    border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px;
    background: linear-gradient(180deg, #0c1a29, #091420); margin-bottom: 16px;
  }}
  .panel h2 {{ font-size: 14px; margin: 0 0 12px; font-weight: 700; letter-spacing: .3px; }}
  .panel h2 span {{ color: var(--muted); font-weight: 500; font-size: 12px; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{
    text-align: left; color: var(--muted); font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: .5px; padding: 6px 10px; border-bottom: 1px solid var(--line);
  }}
  tbody td {{ padding: 9px 10px; border-bottom: 1px solid #112030; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.mono {{ font-family: ui-monospace, 'SF Mono', Menlo, monospace; color: var(--blue); }}
  td.strong {{ font-weight: 800; }}
  tr.hero {{ background: rgba(255,77,77,.08); }}
  tr.hero td.strong {{ color: var(--red); }}
  .badge {{ font-size: 11px; padding: 3px 9px; border-radius: 20px; font-weight: 600; }}
  .badge-ok {{ background: rgba(51,192,168,.15); color: var(--teal); }}
  .badge-alert {{ background: rgba(255,77,77,.16); color: var(--red); }}

  .grid-anom {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }}
  .anomaly {{
    border: 1px solid var(--line); border-left: 3px solid var(--red); border-radius: 11px;
    padding: 13px 15px; background: linear-gradient(180deg, #0e1a27, #0a141f);
  }}
  .anomaly-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 7px; }}
  .anomaly-num {{
    width: 22px; height: 22px; border-radius: 6px; background: rgba(255,77,77,.18);
    color: var(--red); font-weight: 800; font-size: 12px;
    display: flex; align-items: center; justify-content: center; flex: none;
  }}
  .anomaly-title {{ font-weight: 700; font-size: 13.5px; }}
  .anomaly-metric {{ margin-left: auto; color: var(--red); font-weight: 800; font-size: 13.5px; white-space: nowrap; }}
  .anomaly-body {{ color: var(--muted); font-size: 12.5px; line-height: 1.5; }}
  .footnote {{ color: #5a7088; font-size: 11px; margin-top: 18px; text-align: center; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="brand">
        <div class="logo">C</div>
        <div>
          <h1>Centrica Energy · LNG Cargo Arbitrage</h1>
          <div class="sub">LNG Trading desk (DESK_LNG) · cargo \u2192 cross-region arbitrage</div>
        </div>
      </div>
      <div class="asof">As of<b>{AS_OF_LABEL}</b></div>
    </div>

    <div class="grid-kpi">{kpi_html}</div>

    <div class="panel">
      <h2>JKM\u2013TTF Net Arbitrage <span>\u00b7 last 30 trading days · $/MMBtu</span></h2>
      {line_svg}
    </div>

    <div class="panel">
      <h2>Cargo Tracking <span>\u00b7 in-transit positions by lat/lon, coloured by destination</span></h2>
      {map_svg}
    </div>

    <div class="panel">
      <h2>Top-5 Diversion Opportunities <span>\u00b7 net arb \u00d7 cargo volume</span></h2>
      <table>
        <thead><tr>
          <th>Cargo</th><th>Vessel</th><th>Route</th>
          <th class="num">Qty (MMBtu)</th><th class="num">Net arb $/MMBtu</th>
          <th class="num">$ Opportunity</th><th>Status</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>

    <div class="panel">
      <h2>Anomaly Desk <span>\u00b7 4 active exceptions</span></h2>
      <div class="grid-anom">{anomaly_html}</div>
    </div>

    <div class="footnote">
      Synthetic demo data · deterministic (numpy seed=42) · generated from CARGO_ARBITRAGE_PLAN.md ·
      conversion TTF$/MMBtu = (TTF\u20ac/MWh \u00f7 {MWH_TO_MMBTU}) \u00d7 EURUSD({EURUSD})
    </div>
  </div>
</body>
</html>
"""


def main() -> None:
    out = Path(__file__).resolve().parent / "index.html"
    out.write_text(build_html(), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
