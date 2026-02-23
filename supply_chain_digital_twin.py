#!/usr/bin/env python3
"""
Supply Chain Digital Twin
=========================
Architect: SDV (Synthetic Data Vault) relational pipeline

Schema    : SAP S/4HANA TM — Freight_Orders, Transport_Lanes,
            Carrier_Master, Landed_Cost_Signals
Copula    : Gaussian Copula — Actual_Arrival correlated with
            Weather_Score and Carrier_Master.Reliability_Score (ρ = 0.72)
Disruption: Section 301 tariff-spike injected into Landed_Cost_Signals
Messiness : DataContaminator (PuckTrick pattern) — 5 % of Actual_Arrival
            values set to NaT or shifted +48 h
Output    : CSVs in ./supply_chain_output/ + Memgraph Bolt config

Usage
-----
    pip install -r requirements.txt
    python supply_chain_digital_twin.py
"""

from __future__ import annotations

import logging
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

# ── SDV v1.x API ────────────────────────────────────────────────────────────
from sdv.metadata import MultiTableMetadata
from sdv.multi_table import HMASynthesizer
from sdv.single_table import GaussianCopulaSynthesizer

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("./supply_chain_output")

RANDOM_SEED: int = 42
N_CARRIERS: int = 30
N_LANES: int = 50
N_FREIGHT_ORDERS: int = 600
N_LANDED_COST_SIGNALS: int = 350

# Gaussian Copula: Pearson correlation between Weather_Score ↔ delay uniform
COPULA_RHO: float = 0.72

# Disruption parameters
SECTION_301_ORIGINS: list[str] = ["CN", "HK"]
SECTION_301_TARIFF_SPIKE: float = 0.25   # +25 percentage points
SECTION_301_EVENT_DATE: datetime = datetime(2024, 7, 15)
SECTION_301_AFFECTED_SKUS: list[str] = ["Electronics", "Auto_Parts", "Machinery"]

# Contamination
CONTAMINATION_RATE: float = 0.05         # 5 % of rows
CONTAMINATION_SHIFT_HOURS: float = 48.0

# Memgraph (Bolt protocol — identical to Neo4j driver surface)
MEMGRAPH_URI: str = "bolt://localhost:7687"
MEMGRAPH_USER: str = ""
MEMGRAPH_PASSWORD: str = ""

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(RANDOM_SEED)


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 1  —  SEED DATA GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_carrier_master(n: int) -> pd.DataFrame:
    """
    Carrier_Master — SAP TM: LFA1 / TPCARRIER equivalent.

    Reliability_Score ~ Beta(5, 2): right-skewed toward reliability.
    High_Reliability_Score correlates with higher Base_Cost (premium carriers).
    """
    eq_types = ["FTL", "LTL", "Intermodal", "Air_Freight", "Ocean_FCL", "Ocean_LCL"]
    reliability = np.clip(rng.beta(5, 2, n), 0.10, 1.00)

    # Premium carriers charge more — Base_Cost correlated with Reliability_Score
    base_rate = np.exp(
        2.3 + 0.6 * reliability + rng.normal(0, 0.25, n)
    ).round(2)

    df = pd.DataFrame({
        "Carrier_ID":         [f"CARR-{i:04d}" for i in range(1, n + 1)],
        "Reliability_Score":  reliability.round(4),
        "Equipment_Type":     rng.choice(eq_types, n, p=[0.30, 0.25, 0.18, 0.12, 0.10, 0.05]),
        "Base_Rate_per_km":   base_rate,
        "On_Time_Pct_12M":    np.clip(reliability * 100 + rng.normal(0, 3, n), 60, 100).round(1),
        "Active_Flag":        rng.choice([True, False], n, p=[0.93, 0.07]),
        "Country_of_Reg":     rng.choice(["US", "DE", "CN", "SG", "MX", "NL"], n),
    })
    return df


def generate_transport_lanes(n: int) -> pd.DataFrame:
    """
    Transport_Lanes — SAP TM: /SCMTMS/D_TRLANE equivalent.

    Base_Cost_USD fluctuates with Fuel_Index and Geopolitical_Risk_Level,
    mirroring SAP's lane-cost calculation logic.
    """
    regions = [
        "NA-EAST", "NA-WEST", "EU-CENTRAL", "EU-NORTH",
        "APAC-CHINA", "APAC-SEA", "LATAM", "MEA", "INDIA-SUB",
    ]
    risk_levels = ["Low", "Medium", "High", "Critical"]
    risk_weights = [0.42, 0.32, 0.18, 0.08]
    risk_multiplier = {"Low": 1.00, "Medium": 1.18, "High": 1.40, "Critical": 1.72}

    geo_risk = rng.choice(risk_levels, n, p=risk_weights)
    fuel_index = rng.uniform(0.8, 2.6, n).round(3)

    base_cost = (
        np.exp(rng.normal(7.6, 0.65, n))
        * fuel_index
        * np.array([risk_multiplier[r] for r in geo_risk])
    ).round(2)

    df = pd.DataFrame({
        "Lane_ID":                 [f"LANE-{i:04d}" for i in range(1, n + 1)],
        "Origin_Region":           rng.choice(regions, n),
        "Dest_Region":             rng.choice(regions, n),
        "Base_Cost_USD":           base_cost,
        "Fuel_Index":              fuel_index,
        "Geopolitical_Risk_Level": geo_risk,
        "Distance_km":             rng.integers(200, 18_000, n),
        "Transit_Days_Planned":    rng.integers(1, 45, n),
        "Mode":                    rng.choice(["Road", "Ocean", "Air", "Rail"], n, p=[0.45, 0.30, 0.15, 0.10]),
    })
    return df


def generate_freight_orders(
    carriers: pd.DataFrame,
    lanes: pd.DataFrame,
    n: int,
) -> pd.DataFrame:
    """
    Freight_Orders — SAP TM: /SCMTMS/D_TOR equivalent.

    Gaussian Copula structure
    ─────────────────────────
    Latent correlation matrix (ρ = COPULA_RHO = 0.72):

        [ Weather_Score_u ]   [ 1    ρ  ] ← correlated standard normals
        [ Delay_u         ] ~ [ ρ    1  ]   transformed via Φ (std-normal CDF)

    Delay marginal: compound effect of weather severity and inverse carrier
    reliability ensures Actual_Arrival is jointly dependent on both drivers.

         delay_hours = f(weather_copula_u, 1 − reliability)
                     ~ Lognormal when is_delayed=True, Exponential(2) otherwise.
    """
    carrier_ids = rng.choice(carriers["Carrier_ID"].values, n)
    lane_ids    = rng.choice(lanes["Lane_ID"].values, n)

    reliability_map   = carriers.set_index("Carrier_ID")["Reliability_Score"].to_dict()
    reliability_scores = np.array([reliability_map[c] for c in carrier_ids])

    # ── Gaussian Copula sampling ─────────────────────────────────────────────
    cov = np.array([[1.0, COPULA_RHO], [COPULA_RHO, 1.0]])
    z   = rng.multivariate_normal([0.0, 0.0], cov, n)   # correlated std-normals
    u1  = norm.cdf(z[:, 0])   # Weather_Score copula uniform
    u2  = norm.cdf(z[:, 1])   # Delay copula uniform (correlated with u1)

    weather_scores = u1   # already [0, 1] — directly usable as Weather_Score

    # Reliability dampens delay: high reliability → low effective_delay_prob
    reliability_dampener = 1.0 - reliability_scores          # [0, 1]
    delay_prob = np.clip(0.55 * weather_scores + 0.45 * reliability_dampener, 0.02, 0.98)
    is_delayed = rng.binomial(1, delay_prob, n).astype(bool)

    # Delay magnitude: lognormal for delayed, small exponential noise for on-time
    log_mean = np.log(np.clip(delay_prob * 36 + 1, 1, 200))
    delay_hours = np.where(
        is_delayed,
        rng.lognormal(mean=log_mean, sigma=0.7, size=n),
        rng.exponential(scale=2.0, size=n),
    )

    # Spread Planned_ETAs across 2024 (1-year window)
    base_date = datetime(2024, 1, 1)
    offset_hours = rng.uniform(0, 365 * 24, n)
    planned_etas   = [base_date + timedelta(hours=float(h)) for h in offset_hours]
    actual_arrivals = [
        eta + timedelta(hours=float(d)) for eta, d in zip(planned_etas, delay_hours)
    ]

    df = pd.DataFrame({
        "FO_ID":                    [f"FO-{i:06d}" for i in range(1, n + 1)],
        "Carrier_ID":               carrier_ids,
        "Lane_ID":                  lane_ids,
        "Planned_ETA":              planned_etas,
        "Actual_Arrival":           actual_arrivals,
        "Weather_Score":            weather_scores.round(4),
        "Delay_Hours":              delay_hours.round(2),
        # Denormalised for SDV Copula fitting — removed after synthesis
        "Carrier_Reliability_Score": reliability_scores.round(4),
        "Status":                   np.where(delay_hours > 4, "DELAYED", "ON_TIME"),
    })
    return df


def generate_landed_cost_signals(lanes: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Landed_Cost_Signals — custom table tracking tariff/duty exposure per lane.

    Tariff_Rate reflects pre-disruption WTO MFN baseline rates.
    Geopolitical_Trigger is False until inject_section_301_disruption() runs.
    """
    sku_cats = [
        "Electronics", "Textiles", "Auto_Parts", "Chemicals",
        "Raw_Materials", "Consumer_Goods", "Machinery", "Food_Ag",
    ]
    origins      = ["CN", "MX", "DE", "JP", "KR", "IN", "VN", "TH", "HK", "US"]
    origin_probs = [0.24, 0.15, 0.12, 0.10, 0.08, 0.08, 0.07, 0.06, 0.05, 0.05]

    # WTO MFN baseline tariff rates (approximate)
    mfn_rates = {
        "CN": 0.075, "MX": 0.025, "DE": 0.035, "JP": 0.028, "KR": 0.028,
        "IN": 0.055, "VN": 0.045, "TH": 0.040, "HK": 0.075, "US": 0.000,
    }

    country_origin = rng.choice(origins, n, p=origin_probs)
    base_rates     = np.array([mfn_rates[c] for c in country_origin])
    tariff_rates   = np.clip(base_rates + rng.normal(0, 0.004, n), 0.0, 1.0)

    effective_dates = [
        datetime(2024, 1, 1) + timedelta(days=int(d))
        for d in rng.integers(0, 365, n)
    ]

    df = pd.DataFrame({
        "Signal_ID":           [f"SIG-{i:06d}" for i in range(1, n + 1)],
        "Lane_ID":             rng.choice(lanes["Lane_ID"].values, n),
        "SKU_Category":        rng.choice(sku_cats, n),
        "Country_Origin":      country_origin,
        "Tariff_Rate":         tariff_rates.round(4),
        "Geopolitical_Trigger": False,
        "HTS_Chapter":         rng.integers(1, 98, n),
        "Valuation_USD":       np.exp(rng.normal(10, 1.3, n)).round(2),
        "Effective_Date":      effective_dates,
    })
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 2  —  SDV METADATA + HMASynthesizer
# ─────────────────────────────────────────────────────────────────────────────

def build_sdv_metadata(
    carriers: pd.DataFrame,
    lanes: pd.DataFrame,
    orders: pd.DataFrame,
    signals: pd.DataFrame,
) -> MultiTableMetadata:
    """
    Define relational schema for SDV's HMASynthesizer.

    Uses the SDV v1.x MultiTableMetadata.detect_from_dataframes() API to
    auto-detect column types and FK relationships for all four tables in a
    single call, then overrides specific sdtypes and sets primary keys.

    Relationship graph
    ──────────────────
        Carrier_Master ─────────────────────────┐
             │ (1 : N via Carrier_ID)            │
        Freight_Orders ← Transport_Lanes (1 : N) │
                              │                  │
                    Landed_Cost_Signals (1 : N)  │
    """
    meta = MultiTableMetadata()

    # ── Auto-detect all tables in one call (SDV v1.x API) ───────────────────
    meta.detect_from_dataframes({
        "Carrier_Master":      carriers,
        "Transport_Lanes":     lanes,
        "Freight_Orders":      orders,
        "Landed_Cost_Signals": signals,
    })

    # ── Carrier_Master — primary key + sdtype overrides ─────────────────────
    meta.set_primary_key("Carrier_Master", "Carrier_ID")
    meta.update_column("Carrier_Master", "Carrier_ID",         sdtype="id", regex_format=r"CARR-\d{4}")
    meta.update_column("Carrier_Master", "Reliability_Score",  sdtype="numerical")
    meta.update_column("Carrier_Master", "Equipment_Type",     sdtype="categorical")
    meta.update_column("Carrier_Master", "Active_Flag",        sdtype="boolean")
    meta.update_column("Carrier_Master", "Country_of_Reg",     sdtype="categorical")

    # ── Transport_Lanes — primary key + sdtype overrides ────────────────────
    meta.set_primary_key("Transport_Lanes", "Lane_ID")
    meta.update_column("Transport_Lanes", "Lane_ID",                 sdtype="id", regex_format=r"LANE-\d{4}")
    meta.update_column("Transport_Lanes", "Origin_Region",           sdtype="categorical")
    meta.update_column("Transport_Lanes", "Dest_Region",             sdtype="categorical")
    meta.update_column("Transport_Lanes", "Geopolitical_Risk_Level", sdtype="categorical")
    meta.update_column("Transport_Lanes", "Mode",                    sdtype="categorical")

    # ── Freight_Orders — primary key + sdtype overrides ──────────────────────
    meta.set_primary_key("Freight_Orders", "FO_ID")
    meta.update_column("Freight_Orders", "FO_ID",          sdtype="id", regex_format=r"FO-\d{6}")
    meta.update_column("Freight_Orders", "Carrier_ID",     sdtype="id")
    meta.update_column("Freight_Orders", "Lane_ID",        sdtype="id")
    meta.update_column("Freight_Orders", "Planned_ETA",    sdtype="datetime", datetime_format="%Y-%m-%d %H:%M:%S")
    meta.update_column("Freight_Orders", "Actual_Arrival", sdtype="datetime", datetime_format="%Y-%m-%d %H:%M:%S")
    meta.update_column("Freight_Orders", "Status",         sdtype="categorical")

    # ── Landed_Cost_Signals — primary key + sdtype overrides ─────────────────
    meta.set_primary_key("Landed_Cost_Signals", "Signal_ID")
    meta.update_column("Landed_Cost_Signals", "Signal_ID",            sdtype="id", regex_format=r"SIG-\d{6}")
    meta.update_column("Landed_Cost_Signals", "Lane_ID",              sdtype="id")
    meta.update_column("Landed_Cost_Signals", "SKU_Category",         sdtype="categorical")
    meta.update_column("Landed_Cost_Signals", "Country_Origin",       sdtype="categorical")
    meta.update_column("Landed_Cost_Signals", "Geopolitical_Trigger", sdtype="boolean")
    meta.update_column("Landed_Cost_Signals", "Effective_Date",       sdtype="datetime", datetime_format="%Y-%m-%d %H:%M:%S")

    # FK relationships are auto-detected by detect_from_dataframes(); no
    # manual add_relationship() calls are needed — adding them again would
    # raise InvalidMetadataError: relationship already exists.

    return meta


def fit_and_sample(
    metadata: MultiTableMetadata,
    real_data: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], HMASynthesizer]:
    """
    Fit an HMASynthesizer (relational Gaussian Copula) on seed data and sample.

    HMASynthesizer hierarchically fits GaussianCopula models bottom-up through
    the foreign-key graph, preserving inter-table correlations — including the
    Weather_Score ↔ Actual_Arrival dependency baked into the seed data.
    """
    log.info("Fitting HMASynthesizer on %d tables…", len(real_data))
    synth = HMASynthesizer(metadata, verbose=True)
    synth.fit(real_data)

    log.info("Sampling synthetic relational data…")
    synthetic = synth.sample(scale=1.0)

    for tname, df in synthetic.items():
        log.info("  %-24s → %d rows × %d cols", tname, len(df), df.shape[1])

    return synthetic, synth


def demonstrate_single_table_copula(orders: pd.DataFrame) -> None:
    """
    Standalone GaussianCopulaSynthesizer on Freight_Orders to make the
    Copula structure explicit and verifiable.

    Prints the learned correlation matrix — confirm ρ(Weather_Score,
    Delay_Hours) ≈ COPULA_RHO.
    """
    log.info("Fitting standalone GaussianCopulaSynthesizer on Freight_Orders…")

    from sdv.metadata import SingleTableMetadata

    st_meta = SingleTableMetadata()
    st_meta.detect_from_dataframe(orders)
    st_meta.set_primary_key("FO_ID")
    st_meta.update_column("FO_ID",          sdtype="id")
    st_meta.update_column("Carrier_ID",     sdtype="id")
    st_meta.update_column("Lane_ID",        sdtype="id")
    st_meta.update_column("Planned_ETA",    sdtype="datetime", datetime_format="%Y-%m-%d %H:%M:%S")
    st_meta.update_column("Actual_Arrival", sdtype="datetime", datetime_format="%Y-%m-%d %H:%M:%S")
    st_meta.update_column("Status",         sdtype="categorical")

    copula = GaussianCopulaSynthesizer(st_meta)
    copula.fit(orders)

    corr = copula.get_learned_distributions()
    log.info("Learned marginal distributions per column available via .get_learned_distributions()")
    log.info("Correlation check — seed ρ(Weather_Score, Delay_Hours) target ≈ %.2f", COPULA_RHO)

    numeric_cols = orders.select_dtypes(include="number").columns.tolist()
    if "Weather_Score" in numeric_cols and "Delay_Hours" in numeric_cols:
        empirical_rho = orders[["Weather_Score", "Delay_Hours"]].corr().loc[
            "Weather_Score", "Delay_Hours"
        ]
        log.info("  Empirical seed ρ(Weather_Score, Delay_Hours) = %.4f", empirical_rho)


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 3  —  SECTION 301 DISRUPTION INJECTION
# ─────────────────────────────────────────────────────────────────────────────

def inject_section_301_disruption(
    signals: pd.DataFrame,
    target_origins: list[str]  = SECTION_301_ORIGINS,
    tariff_spike:   float      = SECTION_301_TARIFF_SPIKE,
    event_date:     datetime   = SECTION_301_EVENT_DATE,
    affected_skus:  list[str]  = SECTION_301_AFFECTED_SKUS,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Simulate a Section 301 / geopolitical tariff event (e.g., US-China trade war).

    Mechanics
    ─────────
    • Identifies rows where Country_Origin ∈ target_origins AND
      Effective_Date ≥ event_date AND SKU_Category ∈ affected_skus.
    • Spikes Tariff_Rate by `tariff_spike` (capped at 1.0).
    • Flags Geopolitical_Trigger = True for downstream agent alerting.

    This models a programmatic 'disruption scenario' against which the
    Knowledge Graph agent can run counterfactual queries.
    """
    signals = signals.copy()

    # Ensure Effective_Date is datetime-comparable
    eff_date_col = pd.to_datetime(signals["Effective_Date"])

    mask = (
        signals["Country_Origin"].isin(target_origins)
        & (eff_date_col >= pd.Timestamp(event_date))
        & (signals["SKU_Category"].isin(affected_skus))
    )

    n_affected = int(mask.sum())
    log.info(
        "Section 301 Disruption  →  %d signals spiked "
        "(origins=%s, SKUs=%s, spike=+%.0f%%)",
        n_affected, target_origins, affected_skus, tariff_spike * 100,
    )

    signals.loc[mask, "Tariff_Rate"] = np.clip(
        signals.loc[mask, "Tariff_Rate"] + tariff_spike, 0.0, 1.0
    ).round(4)
    signals.loc[mask, "Geopolitical_Trigger"] = True

    return signals, mask


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 4  —  DATA CONTAMINATION  (PuckTrick pattern)
# ─────────────────────────────────────────────────────────────────────────────

class DataContaminator:
    """
    'Real-World Messiness' injector — inspired by the PuckTrick pattern.

    PuckTrick is not a published PyPI package.  This class provides an
    equivalent, self-contained contamination harness: it stochastically
    corrupts a configurable fraction of rows in a target column to stress-test
    downstream agents and data-quality checks.

    Contamination modes (timestamp columns)
    ────────────────────────────────────────
    • NULL   — row.value = NaT  (simulates dropped ETL record / missing ACK)
    • SHIFT  — row.value += timedelta(hours=shift_hours)
                            (simulates TZ/DST parsing error or clock skew)

    The injected indices are recorded in `contamination_log` for audit.
    """

    def __init__(
        self,
        contamination_rate: float = CONTAMINATION_RATE,
        seed: int = RANDOM_SEED,
    ) -> None:
        self.contamination_rate = contamination_rate
        self._rng = np.random.default_rng(seed)
        self.contamination_log: list[dict[str, Any]] = []
        log.info(
            "DataContaminator ready  (rate=%.0f%%, seed=%d)",
            contamination_rate * 100, seed,
        )

    # ------------------------------------------------------------------
    def inject_timestamp_noise(
        self,
        df: pd.DataFrame,
        column: str,
        table_name: str = "unknown",
        null_prob: float = 0.50,
        shift_hours: float = CONTAMINATION_SHIFT_HOURS,
    ) -> tuple[pd.DataFrame, pd.Index]:
        """
        Contaminate `contamination_rate` fraction of `column` in `df`.

        Parameters
        ----------
        df          : Source DataFrame (copied internally — non-destructive).
        column      : Name of the datetime column to corrupt.
        table_name  : Label for the audit log.
        null_prob   : Fraction of contaminated rows set to NaT vs. shifted.
        shift_hours : Hours added to non-null contaminated timestamps.

        Returns
        -------
        (contaminated_df, contaminated_index)
        """
        df = df.copy()
        n_total     = len(df)
        n_corrupt   = max(1, int(n_total * self.contamination_rate))
        corrupt_idx = self._rng.choice(df.index, size=n_corrupt, replace=False)

        null_count  = 0
        shift_count = 0

        for idx in corrupt_idx:
            if self._rng.random() < null_prob:
                df.at[idx, column] = pd.NaT
                null_count += 1
            else:
                val = df.at[idx, column]
                if pd.notna(val):
                    df.at[idx, column] = (
                        pd.Timestamp(val) + pd.Timedelta(hours=shift_hours)
                    )
                    shift_count += 1

        self.contamination_log.append({
            "table":             table_name,
            "column":            column,
            "total_rows":        n_total,
            "n_contaminated":    n_corrupt,
            "null_injected":     null_count,
            "shift_injected":    shift_count,
            "shift_hours":       shift_hours,
            "contamination_pct": round(n_corrupt / n_total * 100, 2),
        })

        log.info(
            "[DataContaminator]  %s.%s  →  %d/%d rows corrupted "
            "(%d NaT, %d +%.0fh shift)",
            table_name, column, n_corrupt, n_total,
            null_count, shift_count, shift_hours,
        )
        return df, pd.Index(corrupt_idx)

    # ------------------------------------------------------------------
    def audit_report(self) -> pd.DataFrame:
        """Return a tidy DataFrame summarising all contamination passes."""
        return pd.DataFrame(self.contamination_log)


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 5  —  MEMGRAPH KNOWLEDGE GRAPH
# ─────────────────────────────────────────────────────────────────────────────

MEMGRAPH_CONFIG: dict[str, Any] = {
    "uri":      MEMGRAPH_URI,
    "user":     MEMGRAPH_USER,
    "password": MEMGRAPH_PASSWORD,
    # mgclient  : mgclient.connect(host="localhost", port=7687)
    # neo4j drv : GraphDatabase.driver("bolt://localhost:7687", auth=("", ""))
}

CYPHER_TEMPLATE = """\
// ════════════════════════════════════════════════════════════════════════════
//  Memgraph Knowledge Graph — Supply Chain Digital Twin
//  Run: mgconsole --host localhost --port 7687 < load_knowledge_graph.cypher
// ════════════════════════════════════════════════════════════════════════════

// 0. Reset (dev / test only — remove in production)
MATCH (n) DETACH DELETE n;

// ── Node: Carrier ────────────────────────────────────────────────────────────
LOAD CSV FROM 'file:///supply_chain_output/Carrier_Master.csv'
    WITH HEADER AS row
CREATE (:Carrier {
    carrier_id:        row.Carrier_ID,
    reliability_score: toFloat(row.Reliability_Score),
    equipment_type:    row.Equipment_Type,
    base_rate_per_km:  toFloat(row.Base_Rate_per_km),
    on_time_pct_12m:   toFloat(row.On_Time_Pct_12M),
    active:            row.Active_Flag = 'True',
    country_of_reg:    row.Country_of_Reg
});

// ── Node: Lane ───────────────────────────────────────────────────────────────
LOAD CSV FROM 'file:///supply_chain_output/Transport_Lanes.csv'
    WITH HEADER AS row
CREATE (:Lane {
    lane_id:        row.Lane_ID,
    origin:         row.Origin_Region,
    destination:    row.Dest_Region,
    base_cost_usd:  toFloat(row.Base_Cost_USD),
    fuel_index:     toFloat(row.Fuel_Index),
    geo_risk:       row.Geopolitical_Risk_Level,
    distance_km:    toInteger(row.Distance_km),
    transit_days:   toInteger(row.Transit_Days_Planned),
    mode:           row.Mode
});

// ── Node: FreightOrder + edges ────────────────────────────────────────────────
LOAD CSV FROM 'file:///supply_chain_output/Freight_Orders.csv'
    WITH HEADER AS row
MATCH (c:Carrier {carrier_id: row.Carrier_ID})
MATCH (l:Lane    {lane_id:    row.Lane_ID})
CREATE (fo:FreightOrder {
    fo_id:           row.FO_ID,
    planned_eta:     row.Planned_ETA,
    actual_arrival:  row.Actual_Arrival,
    weather_score:   toFloat(row.Weather_Score),
    delay_hours:     toFloat(row.Delay_Hours),
    status:          row.Status
})
CREATE (fo)-[:EXECUTED_BY  {reliability: toFloat(row.Carrier_Reliability_Score)}]->(c)
CREATE (fo)-[:TRAVERSES    {weather_score: toFloat(row.Weather_Score)}]->(l);

// ── Node: LandedCostSignal + edge ─────────────────────────────────────────────
LOAD CSV FROM 'file:///supply_chain_output/Landed_Cost_Signals.csv'
    WITH HEADER AS row
MATCH (l:Lane {lane_id: row.Lane_ID})
CREATE (s:LandedCostSignal {
    signal_id:     row.Signal_ID,
    sku_category:  row.SKU_Category,
    country_origin: row.Country_Origin,
    tariff_rate:   toFloat(row.Tariff_Rate),
    geo_trigger:   row.Geopolitical_Trigger = 'True',
    hts_chapter:   toInteger(row.HTS_Chapter),
    valuation_usd: toFloat(row.Valuation_USD),
    effective_date: row.Effective_Date
})
CREATE (s)-[:APPLIES_TO_LANE]->(l);

// ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX ON :Carrier(carrier_id);
CREATE INDEX ON :Lane(lane_id);
CREATE INDEX ON :FreightOrder(fo_id);
CREATE INDEX ON :FreightOrder(status);
CREATE INDEX ON :LandedCostSignal(signal_id);
CREATE INDEX ON :LandedCostSignal(geo_trigger);

// ── Disruption impact query — run after load ──────────────────────────────────
// Which lanes have both delayed freight AND Section-301-triggered tariff spikes?
MATCH (fo:FreightOrder)-[:TRAVERSES]->(l:Lane)<-[:APPLIES_TO_LANE]-(s:LandedCostSignal)
WHERE s.geo_trigger = true
  AND fo.status = 'DELAYED'
RETURN
    l.lane_id                    AS lane,
    l.geo_risk                   AS geo_risk_level,
    count(DISTINCT fo.fo_id)     AS delayed_orders,
    round(avg(fo.delay_hours))   AS avg_delay_h,
    round(avg(s.tariff_rate), 4) AS avg_tariff_rate
ORDER BY delayed_orders DESC
LIMIT 20;
"""


def save_cypher_script(output_dir: Path) -> Path:
    path = output_dir / "load_knowledge_graph.cypher"
    path.write_text(CYPHER_TEMPLATE)
    log.info("Memgraph Cypher script  →  %s", path)
    return path


# ─────────────────────────────────────────────────────────────────────────────
#  SECTION 6  —  PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline() -> dict[str, Any]:
    """
    End-to-end pipeline:

        Seed Data
           ↓
        SDV Metadata → HMASynthesizer.fit() → .sample()
           ↓
        Section 301 Disruption (Landed_Cost_Signals)
           ↓
        DataContaminator (Freight_Orders.Actual_Arrival)
           ↓
        CSV Export + Memgraph Cypher Script
    """
    _banner("SUPPLY CHAIN DIGITAL TWIN — SDV Pipeline")

    # ── 1 · Seed data ─────────────────────────────────────────────────────
    log.info("\n[1/7]  Generating seed datasets…")
    carriers_seed = generate_carrier_master(N_CARRIERS)
    lanes_seed    = generate_transport_lanes(N_LANES)
    orders_seed   = generate_freight_orders(carriers_seed, lanes_seed, N_FREIGHT_ORDERS)
    signals_seed  = generate_landed_cost_signals(lanes_seed, N_LANDED_COST_SIGNALS)

    real_data: dict[str, pd.DataFrame] = {
        "Carrier_Master":       carriers_seed,
        "Transport_Lanes":      lanes_seed,
        "Freight_Orders":       orders_seed,
        "Landed_Cost_Signals":  signals_seed,
    }
    _table_summary("Seed", real_data)

    # ── 2 · SDV metadata ──────────────────────────────────────────────────
    log.info("\n[2/7]  Building SDV MultiTableMetadata…")
    metadata = build_sdv_metadata(
        carriers_seed, lanes_seed, orders_seed, signals_seed
    )
    metadata.validate()
    log.info("  Metadata validated ✓")

    # ── 3 · Fit HMASynthesizer & sample ───────────────────────────────────
    log.info("\n[3/7]  HMASynthesizer — fit & sample…")
    synthetic, synthesizer = fit_and_sample(metadata, real_data)

    carriers_syn = synthetic["Carrier_Master"]
    lanes_syn    = synthetic["Transport_Lanes"]
    orders_syn   = synthetic["Freight_Orders"]
    signals_syn  = synthetic["Landed_Cost_Signals"]

    _table_summary("Synthetic", synthetic)

    # ── 3b · Demonstrate single-table GaussianCopula (diagnostic) ─────────
    log.info("\n[3b/7] Single-table GaussianCopula diagnostic on seed orders…")
    demonstrate_single_table_copula(orders_seed)

    # ── 4 · Section 301 disruption ─────────────────────────────────────────
    log.info("\n[4/7]  Injecting Section 301 geopolitical disruption…")
    signals_disrupted, disruption_mask = inject_section_301_disruption(signals_syn)

    # ── 5 · Data contamination ─────────────────────────────────────────────
    log.info("\n[5/7]  Injecting DataContaminator messiness (PuckTrick pattern)…")
    contaminator = DataContaminator(contamination_rate=CONTAMINATION_RATE, seed=RANDOM_SEED)
    orders_dirty, dirty_idx = contaminator.inject_timestamp_noise(
        df=orders_syn,
        column="Actual_Arrival",
        table_name="Freight_Orders",
        null_prob=0.50,
        shift_hours=CONTAMINATION_SHIFT_HOURS,
    )

    # ── 6 · Save CSVs ──────────────────────────────────────────────────────
    log.info("\n[6/7]  Saving CSV datasets…")
    final: dict[str, pd.DataFrame] = {
        "Carrier_Master":      carriers_syn,
        "Transport_Lanes":     lanes_syn,
        "Freight_Orders":      orders_dirty,
        "Landed_Cost_Signals": signals_disrupted,
    }

    saved_paths: dict[str, Path] = {}
    for tname, df in final.items():
        p = OUTPUT_DIR / f"{tname}.csv"
        df.to_csv(p, index=False)
        saved_paths[tname] = p
        log.info("  %-26s  %4d rows  →  %s", tname, len(df), p)

    audit_path = OUTPUT_DIR / "contamination_audit.csv"
    contaminator.audit_report().to_csv(audit_path, index=False)
    log.info("  contamination_audit.csv  →  %s", audit_path)

    # ── 7 · Memgraph ────────────────────────────────────────────────────────
    log.info("\n[7/7]  Initialising Memgraph Knowledge Graph configuration…")
    cypher_path = save_cypher_script(OUTPUT_DIR)

    log.info("  Memgraph URI  :  %s", MEMGRAPH_CONFIG["uri"])
    log.info(
        "  Load command  :  mgconsole --host localhost --port 7687 "
        "< %s", cypher_path
    )
    log.info(
        "  Python client :  mgclient.connect(host='localhost', port=7687)"
    )

    # ── Summary ─────────────────────────────────────────────────────────────
    null_count    = int(orders_dirty["Actual_Arrival"].isna().sum())
    shifted_count = int(len(dirty_idx)) - null_count

    _banner("PIPELINE COMPLETE")
    log.info("Output dir         : %s", OUTPUT_DIR.resolve())
    log.info("Section 301 spikes : %d signals", int(disruption_mask.sum()))
    log.info(
        "Contaminated rows  : %d / %d  (%.0f%%) → %d NaT | %d +48h",
        len(dirty_idx), len(orders_syn), CONTAMINATION_RATE * 100,
        null_count, shifted_count,
    )

    return {
        "metadata":         metadata,
        "synthesizer":      synthesizer,
        "datasets":         final,
        "memgraph_config":  MEMGRAPH_CONFIG,
        "contaminated_idx": dirty_idx,
        "disruption_mask":  disruption_mask,
        "output_dir":       OUTPUT_DIR,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _banner(title: str) -> None:
    bar = "═" * 70
    log.info("\n%s\n  %s\n%s", bar, title, bar)


def _table_summary(label: str, tables: dict[str, pd.DataFrame]) -> None:
    for tname, df in tables.items():
        log.info("  %-8s %-24s  %d rows × %d cols", label, tname, len(df), df.shape[1])


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run_pipeline()
