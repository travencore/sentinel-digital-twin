#!/usr/bin/env python3
"""
Supply Chain Digital Twin — Sentinel Dashboard
===============================================
Streamlit visualization layer for the Digital Twin pipeline output.

Panels
──────
  1. KPI metric cards   — P&L Risk · Avg Tariff Hike · Healed Records · Disruptions
  2. Cost comparison    — China/HK Landed Cost vs. Mexico Nearshore per SKU (bar)
  3. Order status       — 600 Freight Orders: Clean vs. Delayed breakdown (donut)
  4. Agent Console      — colour-coded Sentinel audit trail
  5. Intelligence tables — top Section 301 signals + nearshoring decision matrix

Usage
─────
    streamlit run dashboard.py
    streamlit run dashboard.py -- --output /path/to/supply_chain_output
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
#  PAGE CONFIG  (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Supply Chain Digital Twin | Sentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
#  DESIGN TOKENS — Logistics Blue / Dark Enterprise palette
# ─────────────────────────────────────────────────────────────────────────────

C = {
    "bg0":      "#0E1117",   # deep matte black — Midnight Gamma base
    "bg1":      "#161B22",   # card / sidebar surface
    "bg2":      "#21262D",   # elevated surface / hover
    "blue":     "#1F6FEB",   # Logistics Blue (primary accent)
    "blue_lt":  "#58A6FF",   # light accent / metric values
    "cobalt":   "#1F77B4",   # On-Time orders (high-contrast cobalt)
    "orange":   "#FF8C00",   # Delayed orders  (Safety Orange — WCAG AA)
    "text":     "#E6EDF3",   # primary text
    "muted":    "#8B949E",   # secondary / label text
    "green":    "#3FB950",   # success / Mexico / savings delta
    "emerald":  "#00C875",   # Mexico Nearshore bar (vivid emerald)
    "amber":    "#D29922",   # warning / tariff delta
    "red":      "#F85149",   # danger / China tariff exposure
    "cyan":     "#00D4FF",   # health / self-healing metric
    "purple":   "#C792EA",   # navigate node colour
    "border":   "#30363D",   # subtle dividers
}

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL CSS INJECTION
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(f"""
<style>
  /* ── Global font — Inter / Arial minimum 12 px ────────────────────────── */
  html, body, [class*="css"], .stApp {{
      font-family: 'Inter', Arial, 'Helvetica Neue', system-ui, sans-serif;
      font-size: 13px;
  }}

  /* ── App shell ──────────────────────────────────────────────────────────── */
  .stApp {{
      background-color: {C["bg0"]};
      color: {C["text"]};
  }}
  .block-container {{
      padding-top: 1.4rem;
      max-width: 1420px;
  }}

  /* ── Sidebar ────────────────────────────────────────────────────────────── */
  [data-testid="stSidebar"] {{
      background-color: {C["bg1"]};
      border-right: 1px solid {C["border"]};
  }}
  [data-testid="stSidebar"] .stButton button {{
      background: {C["bg2"]};
      color: {C["blue_lt"]};
      border: 1px solid {C["border"]};
      border-radius: 6px;
      font-size: 12px;
  }}
  [data-testid="stSidebar"] .stButton button:hover {{
      border-color: {C["blue"]};
  }}

  /* ── Custom KPI card (replaces st.metric for full colour control) ────────── */
  .kpi-card {{
      background: {C["bg1"]};
      border: 1px solid {C["border"]};
      border-radius: 10px;
      padding: 1rem 1.25rem 0.85rem;
      height: 100%;
  }}
  .kpi-label {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: {C["muted"]};
      margin-bottom: 0.35rem;
  }}
  .kpi-value {{
      font-size: 2rem;
      font-weight: 800;
      letter-spacing: -0.025em;
      line-height: 1.15;
      margin-bottom: 0.3rem;
  }}
  .kpi-delta {{
      font-size: 12px;
      line-height: 1.4;
  }}

  /* ── Plotly chart containers ─────────────────────────────────────────────── */
  [data-testid="stPlotlyChart"] {{
      border: 1px solid {C["border"]};
      border-radius: 10px;
      overflow: hidden;
      background: {C["bg0"]};
  }}

  /* ── Section headers ────────────────────────────────────────────────────── */
  .sh {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.13em;
      color: {C["muted"]};
      border-bottom: 1px solid {C["border"]};
      padding-bottom: 0.35rem;
      margin-bottom: 0.9rem;
      margin-top: 0.25rem;
  }}

  /* ── Recommendation badges ───────────────────────────────────────────────── */
  .badge-nearshore {{
      background: {C["green"]}1A;
      color: {C["green"]};
      border: 1px solid {C["green"]}4D;
      border-radius: 20px;
      padding: 5px 16px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.05em;
      display: inline-block;
  }}
  .badge-maintain {{
      background: {C["amber"]}1A;
      color: {C["amber"]};
      border: 1px solid {C["amber"]}4D;
      border-radius: 20px;
      padding: 5px 16px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.05em;
      display: inline-block;
  }}

  /* ── Agent Console ───────────────────────────────────────────────────────── */
  .console {{
      background: {C["bg0"]};
      border: 1px solid {C["border"]};
      border-left: 3px solid {C["blue"]};
      border-radius: 6px;
      padding: 1rem 1.3rem;
      font-family: "SF Mono", "Fira Code", "Cascadia Code", monospace;
      font-size: 12px;
      line-height: 1.75;
      max-height: 320px;
      overflow-y: auto;
  }}
  .l-idx   {{ color: {C["muted"]};    margin-right: 0.6rem; }}
  .l-mon   {{ color: {C["blue_lt"]}; }}
  .l-ana   {{ color: {C["amber"]};   }}
  .l-cln   {{ color: {C["green"]};   }}
  .l-nav   {{ color: {C["purple"]};  }}
  .l-def   {{ color: {C["text"]};    }}

  /* ── Self-healing pill ───────────────────────────────────────────────────── */
  .heal-pill {{
      background: {C["bg1"]};
      border: 1px solid {C["border"]};
      border-left: 3px solid {C["cyan"]};
      border-radius: 6px;
      padding: 0.65rem 1rem;
      font-size: 12px;
      margin-top: 0.6rem;
  }}

  /* ── DataFrames ──────────────────────────────────────────────────────────── */
  [data-testid="stDataFrame"] {{
      border: 1px solid {C["border"]};
      border-radius: 8px;
  }}

  /* ── Dividers ────────────────────────────────────────────────────────────── */
  hr {{ border-color: {C["border"]}; margin: 1.5rem 0; }}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_OUTPUT = Path(__file__).parent / "supply_chain_output"


def _resolve_output_dir() -> Path:
    """Support `streamlit run dashboard.py -- --output PATH`."""
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg in ("--output", "-o") and i + 1 < len(argv):
            return Path(argv[i + 1])
    return DEFAULT_OUTPUT


OUTPUT_DIR = _resolve_output_dir()

# ─────────────────────────────────────────────────────────────────────────────
#  DATA LOADING  (cached 60 s)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_csv(name: str) -> pd.DataFrame:
    p = OUTPUT_DIR / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@st.cache_data(ttl=60)
def load_report() -> dict:
    p = OUTPUT_DIR / "sentinel_report.json"
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _usd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:.2f}"


def _kpi(label: str, value: str, delta: str,
         val_color: str, delta_color: str) -> str:
    """Render a single KPI card with full colour control (replaces st.metric)."""
    return (
        f'<div class="kpi-card">'
        f'  <div class="kpi-label">{label}</div>'
        f'  <div class="kpi-value" style="color:{val_color};">{value}</div>'
        f'  <div class="kpi-delta" style="color:{delta_color};">{delta}</div>'
        f'</div>'
    )


def _log_css(line: str) -> str:
    u = line.upper()
    if "[MONITOR]"  in u: return "l-mon"
    if "[ANALYZE]"  in u: return "l-ana"
    if "[CLEAN]"    in u: return "l-cln"
    if "[NAVIGATE]" in u: return "l-nav"
    return "l-def"


# Shared Plotly layout base — transparent so Midnight Gamma theme shows through
_PLY = dict(
    paper_bgcolor="rgba(0,0,0,0)",   # transparent — lets container bg show
    plot_bgcolor ="rgba(0,0,0,0)",
    font=dict(
        color=C["text"],
        family="Inter, Arial, 'Helvetica Neue', system-ui, sans-serif",
        size=13,                     # global minimum 13 px
    ),
    margin=dict(l=24, r=24, t=56, b=24),
    hoverlabel=dict(bgcolor=C["bg2"], bordercolor=C["border"], font_size=13),
)

# ─────────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        f'<div style="padding:0.2rem 0 0.8rem;">'
        f'  <div style="color:{C["blue_lt"]};font-size:1.05rem;font-weight:700;'
        f'  letter-spacing:0.04em;">⬡ SUPPLY CHAIN</div>'
        f'  <div style="color:{C["muted"]};font-size:0.72rem;letter-spacing:0.1em;">'
        f'  DIGITAL TWIN · SENTINEL AGENT</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown(f'<p style="color:{C["muted"]};font-size:0.7rem;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.1em;">Output Directory</p>',
                unsafe_allow_html=True)
    st.code(str(OUTPUT_DIR), language=None)

    st.markdown(f'<p style="color:{C["muted"]};font-size:0.7rem;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.1em;margin-top:1rem;">Data Files</p>',
                unsafe_allow_html=True)

    for fname in [
        "Freight_Orders.csv", "Landed_Cost_Signals.csv",
        "Carrier_Master.csv", "Transport_Lanes.csv",
        "contamination_audit.csv", "sentinel_report.json",
    ]:
        ok    = (OUTPUT_DIR / fname).exists()
        icon  = "✓" if ok else "✗"
        color = C["green"] if ok else C["red"]
        st.markdown(
            f'<div style="color:{color};font-size:0.75rem;font-family:monospace;'
            f'margin:2px 0;">{icon}  {fname}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        f'<p style="color:{C["muted"]};font-size:0.72rem;line-height:1.6;">'
        f'<b style="color:{C["text"]};">Schema</b>  SAP S/4HANA TM<br>'
        f'<b style="color:{C["text"]};">Copula</b>  Gaussian ρ=0.72<br>'
        f'<b style="color:{C["text"]};">Contamination</b>  PuckTrick 5%<br>'
        f'<b style="color:{C["text"]};">Disruption</b>  Section 301 +25pp<br>'
        f'<b style="color:{C["text"]};">Graph</b>  Memgraph Bolt</p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("↺  Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
#  LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────

report   = load_report()
df_fo    = load_csv("Freight_Orders.csv")
df_sig   = load_csv("Landed_Cost_Signals.csv")

if not report and df_fo.empty:
    st.error(
        "No pipeline output found.  "
        "Run `supply_chain_digital_twin.py` → `sentinel_agent.py` "
        f"and ensure `{OUTPUT_DIR}/` contains the CSVs and sentinel_report.json.",
        icon="🚨",
    )
    st.stop()

# Unpack the report
disruption_rpt:  dict = report.get("disruption_report", {})
strategy:        dict = report.get(
    "strategy_recommendations",
    disruption_rpt.get("navigation_strategy", {}),   # fallback path
)
audit_log:  list[str] = report.get("audit_log", [])
healing:         dict = disruption_rpt.get("self_healing", {})
sku_strategies:  dict = strategy.get("sku_strategies", {})

# ─────────────────────────────────────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────────────────────────────────────

hdr_col, badge_col = st.columns([3, 1])

with hdr_col:
    st.markdown(
        f'<h1 style="color:{C["text"]};font-size:1.55rem;font-weight:800;'
        f'margin-bottom:0.1rem;letter-spacing:-0.02em;">'
        f'Supply Chain Digital Twin</h1>'
        f'<p style="color:{C["muted"]};font-size:0.82rem;margin:0;">'
        f'Sentinel Agent  ·  USMCA Nearshoring Navigator  ·  '
        f'SAP S/4HANA TM Schema  ·  HMASynthesizer Gaussian Copula</p>',
        unsafe_allow_html=True,
    )

with badge_col:
    overall = strategy.get("overall_recommendation", "")
    if overall == "SHIFT_TO_NEARSHORE":
        cls, label = "badge-nearshore", "⇢  SHIFT TO NEARSHORE"
    elif overall:
        cls, label = "badge-maintain",  "⟳  MAINTAIN SUPPLIER"
    else:
        cls, label = "", ""
    if cls:
        st.markdown(
            f'<div style="text-align:right;padding-top:0.85rem;">'
            f'<span class="{cls}">{label}</span></div>',
            unsafe_allow_html=True,
        )

st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
#  METRIC CARDS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<p class="sh">Key Risk Indicators</p>', unsafe_allow_html=True)

# Derive values
total_plr_usd    = sum(v.get("estimated_savings_usd", 0) for v in sku_strategies.values())
avg_tariff_pct   = (
    sum(v.get("avg_tariff_rate_pct", 0) for v in sku_strategies.values())
    / max(len(sku_strategies), 1)
)
healed_total     = healing.get("nat_healed", 0) + healing.get("shift_healed", 0)
n_disruptions    = disruption_rpt.get("active_disruptions", 0)
impacted_delayed = disruption_rpt.get("impacted_orders_delayed", 0)
portfolio_sav    = strategy.get("portfolio_avg_savings_pct", 0.0)
n_nearshore_skus = len(strategy.get("skus_recommending_nearshore", []))

m1, m2, m3, m4 = st.columns(4, gap="medium")

with m1:
    # Bright green delta so savings opportunity reads clearly on dark bg
    st.markdown(_kpi(
        label     = "Total P&amp;L Risk — Est. Nearshore Savings",
        value     = _usd(total_plr_usd),
        delta     = f"↑ Portfolio avg  {portfolio_sav:.1f}% savings if nearshored",
        val_color = C["blue_lt"],
        delta_color = C["green"],      # bright green — positive opportunity
    ), unsafe_allow_html=True)

with m2:
    # Red value + amber delta — tariff hike is bad news
    st.markdown(_kpi(
        label     = "Avg Tariff Hike — Post Section 301",
        value     = f"{avg_tariff_pct:.1f}%",
        delta     = f"↑ +{avg_tariff_pct - 7.5:.1f}pp above WTO MFN baseline",
        val_color = C["red"],
        delta_color = C["amber"],
    ), unsafe_allow_html=True)

with m3:
    # Cyan value — distinct "health / data-quality" colour, not financial
    st.markdown(_kpi(
        label     = "Healed Records — PuckTrick Contamination",
        value     = str(healed_total),
        delta     = (f"{healing.get('nat_healed', 0)} NaT repaired  ·  "
                     f"{healing.get('shift_healed', 0)} +48h shifts reversed"),
        val_color = C["cyan"],
        delta_color = C["cyan"] + "AA",   # slightly muted cyan for sub-text
    ), unsafe_allow_html=True)

with m4:
    # Amber value + red delta — active risk
    st.markdown(_kpi(
        label     = "Active Disruption Signals",
        value     = str(n_disruptions),
        delta     = f"↑ {impacted_delayed} delayed orders on hot lanes",
        val_color = C["amber"],
        delta_color = C["red"],
    ), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  CHARTS ROW
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<p class="sh">Strategic Cost Analysis</p>', unsafe_allow_html=True)

chart_l, chart_r = st.columns([3, 2], gap="large")

# ── LEFT — SKU cost comparison grouped bar ────────────────────────────────────
with chart_l:
    if sku_strategies:
        skus         = list(sku_strategies.keys())
        cur_vals     = [v["current_landed_cost_usd"] for v in sku_strategies.values()]
        mex_vals     = [v["mexico_landed_cost_usd"]  for v in sku_strategies.values()]
        sav_pcts     = [v["estimated_savings_pct"]   for v in sku_strategies.values()]
        tariff_pcts  = [v["avg_tariff_rate_pct"]     for v in sku_strategies.values()]

        max_y = max(cur_vals + mex_vals) if cur_vals else 1

        # Build tidy label lists
        china_labels = [f"${v:,.0f}" for v in cur_vals]
        mex_labels   = [f"${v:,.0f}" for v in mex_vals]

        fig_bar = go.Figure()

        fig_bar.add_trace(go.Bar(
            name=f"Current: China/HK (incl. {avg_tariff_pct:.1f}% Section 301 Duties)",
            x=skus,
            y=cur_vals,
            marker_color=C["red"],
            text=china_labels,
            textposition="outside",
            textfont=dict(color=C["text"], size=12,
                          family="Inter, Arial, sans-serif"),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "China / HK landed cost: <b>$%{y:,.0f}</b><br>"
                f"Incl. {avg_tariff_pct:.1f}% Section 301 tariff<br>"
                "<extra></extra>"
            ),
        ))

        fig_bar.add_trace(go.Bar(
            name="Optimized: Mexico Nearshore (USMCA 0% + 15% Ops Overhead)",
            x=skus,
            y=mex_vals,
            marker_color=C["emerald"],
            text=mex_labels,
            textposition="outside",
            textfont=dict(color="#00FF00", size=13,
                          family="Arial Black, Arial, sans-serif"),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Mexico landed cost: <b>$%{y:,.0f}</b><br>"
                "USMCA 0% tariff + 15% logistics overhead<br>"
                "<extra></extra>"
            ),
        ))

        # Savings callouts — at 115 % of tallest bar, inside the 130 % y-axis ceiling
        for i, (sku, pct) in enumerate(zip(skus, sav_pcts)):
            fig_bar.add_annotation(
                x=sku,
                y=max(cur_vals[i], mex_vals[i]) * 1.15,
                text=f"<b>↓ {pct:.1f}%</b><br>savings",
                showarrow=False,
                font=dict(size=12, color=C["emerald"],
                          family="Inter, Arial, sans-serif"),
                align="center",
                bgcolor="rgba(0,0,0,0)",
            )

        # Single update_layout — no **_PLY unpacking to avoid duplicate-margin TypeError
        fig_bar.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            barmode="group",
            bargap=0.30,
            bargroupgap=0.08,
            margin=dict(t=100, b=40, l=40, r=40),
            title=dict(
                text="Landed Cost Comparison per SKU — China/HK  vs  Mexico Nearshore",
                font=dict(size=14, color=C["text"], family="Inter, Arial, sans-serif"),
                x=0,
                pad=dict(b=8),
            ),
            xaxis=dict(
                tickfont=dict(size=13, color=C["text"]),
                tickangle=0,
                automargin=True,
            ),
            yaxis=dict(
                title=dict(text="Avg Landed Cost (USD)",
                           font=dict(size=13, color=C["text"])),
                tickprefix="$",
                tickformat=",.0f",
                tickfont=dict(size=12, color=C["text"]),
                range=[0, max_y * 1.30],
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.04,
                xanchor="center",
                x=0.5,
                font=dict(size=14, color=C["text"],
                          family="Inter, Arial, sans-serif"),
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
                itemclick=False,
                itemdoubleclick=False,
            ),
            font=dict(family="Inter, Arial, sans-serif", size=12),
            hoverlabel=dict(bgcolor=C["bg2"], bordercolor=C["border"], font_size=13),
            height=440,
        )

        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Run the Sentinel Agent to generate nearshoring strategy data.")

# ── RIGHT — Freight order status donut ───────────────────────────────────────
with chart_r:
    if not df_fo.empty and "Status" in df_fo.columns:
        status_counts = df_fo["Status"].value_counts()
        on_time = int(status_counts.get("ON_TIME", 0))
        delayed = int(status_counts.get("DELAYED", 0))
        total   = on_time + delayed

        fig_donut = go.Figure(go.Pie(
            # Order: On Time first so Cobalt Blue sits at top of ring
            labels=["On Time", "Delayed"],
            values=[on_time, delayed],
            hole=0.70,                   # modern thin-ring look
            marker=dict(
                colors=[C["cobalt"], C["orange"]],   # Cobalt Blue / Safety Orange
                line=dict(color=C["bg0"], width=5),  # dark gap between segments
            ),
            textinfo="label+percent",
            textfont=dict(
                size=13,
                color=C["text"],
                family="Inter, Arial, sans-serif",
            ),
            pull=[0, 0.05],              # slight pull on Delayed for emphasis
            rotation=90,                 # start ring at top
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Count: <b>%{value:,}</b><br>"
                "Share: %{percent}<extra></extra>"
            ),
        ))

        # Centre KPI — large bold total, immediately readable by an executive
        fig_donut.add_annotation(
            text=(
                f"<b>{total:,}</b>"
                f"<br><span style='font-size:13px;'>Orders</span>"
            ),
            x=0.5, y=0.5,
            font=dict(size=30, color=C["text"],    # size 30, bold white
                      family="Inter, Arial, sans-serif"),
            showarrow=False,
            align="center",
        )

        # Single update_layout — no **_PLY unpacking to avoid duplicate-margin TypeError
        fig_donut.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            title=dict(
                text="Freight Order Status — Sentinel View",
                font=dict(size=14, color=C["text"], family="Inter, Arial, sans-serif"),
                x=0,
                pad=dict(b=8),
            ),
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=1.05,
                font=dict(size=14, color=C["text"],
                          family="Inter, Arial, sans-serif"),
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
                itemclick=False,
                itemdoubleclick=False,
            ),
            margin=dict(l=24, r=130, t=56, b=24),
            font=dict(family="Inter, Arial, sans-serif", size=13),
            hoverlabel=dict(bgcolor=C["bg2"], bordercolor=C["border"], font_size=13),
            height=440,
        )

        st.plotly_chart(fig_donut, use_container_width=True)

        # Self-healing pill — cyan border to match the health metric card
        if healed_total > 0:
            st.markdown(
                f'<div class="heal-pill">'
                f'<span style="color:{C["muted"]};font-size:11px;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:0.1em;">Self-Healing Applied</span><br>'
                f'<span style="color:{C["cyan"]};">✓ {healing.get("nat_healed", 0)} NaT repaired</span>'
                f'&nbsp;&nbsp;&nbsp;'
                f'<span style="color:{C["cyan"]};">'
                f'✓ {healing.get("shift_healed", 0)} +48h shifts reversed</span>'
                f'&nbsp;&nbsp;&nbsp;'
                f'<span style="color:{C["muted"]};">'
                f'{healing.get("unresolvable", 0)} unresolvable</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("Freight_Orders.csv not found in output directory.")

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  AGENT CONSOLE
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<p class="sh">Agent Console — Agentic Reasoning Trace</p>',
            unsafe_allow_html=True)

if audit_log:
    lines_html = []
    for i, raw in enumerate(audit_log, start=1):
        safe  = html.escape(raw)
        cls   = _log_css(raw)
        lines_html.append(
            f'<span class="l-idx">[{i:02d}]</span>'
            f'<span class="{cls}">{safe}</span>'
        )

    st.markdown(
        '<div class="console">' + "<br>".join(lines_html) + "</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="console">'
        f'<span style="color:{C["muted"]};">'
        f'No audit log found.  Run sentinel_agent.py to populate the agent trace.'
        f'</span></div>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  INTELLIGENCE TABLES
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<p class="sh">Disrupted Lane Intelligence</p>', unsafe_allow_html=True)

tbl_l, tbl_r = st.columns(2, gap="large")

with tbl_l:
    st.markdown(
        f'<p style="color:{C["muted"]};font-size:0.73rem;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.08em;">'
        f'Top Section 301 Signals</p>',
        unsafe_allow_html=True,
    )
    if not df_sig.empty:
        sig = df_sig.copy()
        sig["Geopolitical_Trigger"] = sig["Geopolitical_Trigger"].astype(str).str.lower()
        triggered = sig[sig["Geopolitical_Trigger"].isin(["true", "1", "yes"])]

        if not triggered.empty:
            cols = [c for c in
                    ["Lane_ID", "SKU_Category", "Country_Origin", "Tariff_Rate", "Valuation_USD"]
                    if c in triggered.columns]
            display = (
                triggered[cols]
                .sort_values("Tariff_Rate", ascending=False)
                .head(10)
                .reset_index(drop=True)
            )
            if "Tariff_Rate" in display.columns:
                display["Tariff_Rate"] = display["Tariff_Rate"].map(lambda x: f"{x*100:.1f}%")
            if "Valuation_USD" in display.columns:
                display["Valuation_USD"] = display["Valuation_USD"].map(lambda x: f"${x:,.0f}")
            st.dataframe(display, use_container_width=True, hide_index=True)
        else:
            st.caption("No geopolitical triggers found.")
    else:
        st.caption("Landed_Cost_Signals.csv not available.")

with tbl_r:
    st.markdown(
        f'<p style="color:{C["muted"]};font-size:0.73rem;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.08em;">'
        f'Nearshoring Decision Matrix</p>',
        unsafe_allow_html=True,
    )
    if sku_strategies:
        rows = [
            {
                "SKU":                sku,
                "Tariff (Post-301)":  f"{d['avg_tariff_rate_pct']:.1f}%",
                "Current Cost (USD)": f"${d['current_landed_cost_usd']:>12,.0f}",
                "Mexico Cost (USD)":  f"${d['mexico_landed_cost_usd']:>12,.0f}",
                "Savings":            f"{d['estimated_savings_pct']:.1f}%",
                "Decision":           d["recommendation"],
            }
            for sku, d in sku_strategies.items()
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No nearshoring strategy data — run sentinel_agent.py first.")

# ─────────────────────────────────────────────────────────────────────────────
#  FOOTER
# ─────────────────────────────────────────────────────────────────────────────

generated_at = disruption_rpt.get("generated_at", "—")
st.markdown("---")
st.markdown(
    f'<p style="color:{C["muted"]};font-size:0.7rem;text-align:center;">'
    f'Supply Chain Digital Twin  ·  Sentinel Agent  ·  '
    f'Last report: <b style="color:{C["text"]};">{generated_at}</b>  ·  '
    f'Schema: SAP S/4HANA TM  ·  Copula: Gaussian ρ=0.72  ·  '
    f'Contamination: PuckTrick 5%  ·  Graph: Memgraph Bolt</p>',
    unsafe_allow_html=True,
)
