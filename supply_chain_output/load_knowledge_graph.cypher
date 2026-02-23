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
