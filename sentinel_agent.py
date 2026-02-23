'use client';

import React, { useState, useRef, useMemo, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer,
  CartesianGrid, LabelList, ScatterChart, Scatter, ZAxis, Legend, PieChart, Pie,
  Cell, ReferenceLine, LineChart, Line
} from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';

// --- CONSTANTS & HELPERS ---

const COUNTRY_MAP = [
  { code: "CN", name: "China" },
  { code: "MX", name: "Mexico" },
  { code: "VN", name: "Vietnam" },
  { code: "US", name: "United States" },
  { code: "CA", name: "Canada" }
];
const COUNTRY_COLORS = {
  'China': '#3be6b4',
  'Mexico': '#77aeff',
  'Vietnam': '#ffc162',
  'United States': '#eb4d7e',
  'Canada': '#a179e6'
};
const DARK_BG = '#15161b';
const ACCENT_DARK = '#0cf6e9';
const NEON = '#8fffde';

// Format utilities (exec-level)
function formatMoney(v: number): string {
  if (v >= 1_000_000) return `$${(v/1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v/1_000).toFixed(0)}K`;
  return `$${Math.round(v)}`;
}
function formatPct(p: number): string {
  return `${p.toFixed(1)}%`;
}
function formatCount(n: number) { return n.toLocaleString('en-US', {maximumFractionDigits:0}); }
// Tooltips
const IMPACT_TT = "Impact = Annualized lane value × tariff rate.";
const DELTA_TT = "ΔUSD = (China landed cost + tariffs) − (Nearshore landed cost).";
const ORIGIN_TT = "Country of origin (ISO): China=CN, Canada=CA, Mexico=MX, Vietnam=VN, United States=US";

// Seeded PRNG
function mulberry32(a: number) {
  return function() {
    let t = a += 0x6D2B79F5;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  }
}

// --- DEMO DATA: generate plausible, deterministic lanes ---
const RAW_LANES: LaneRaw[] = Array.from({length: 30}).map((_,i) => {
  // seed per lane for testable 0-hydration
  const prng = mulberry32(5555 + i * 97);
  const countries = COUNTRY_MAP.filter(c => c.code !== 'US'); // supply comes to US
  const originIdx = Math.floor(prng() * countries.length);
  const country = countries[originIdx];
  const tariff = +(Math.floor(prng()*26 * 10) / 10).toFixed(1); // 0–25.9%
  // Skus
  const sku = `SKU-${1000 + (i%6)*37 + i}`;
  // Lane value is always >= 50K, <=2.5M
  const value = Math.round(50_000 + prng() * (2_500_000-50_000));
  const impact = Math.round(value * (tariff/100));
  return {
    id: `LN-${100+i}`,
    origin: country.name,
    originCode: country.code,
    sku,
    value,
    tariff,
    impact,
    confidence: (80 + Math.floor(prng()*19)), // always 80–99%
  }
});

type LaneRaw = {
  id: string;
  origin: string;
  originCode: string;
  sku: string;
  value: number;
  tariff: number;
  impact: number;
  confidence: number;
};

// --- COMPONENTS: UI PRIMITIVES ---

const InfoIcon = ({className}:{className?:string}) => (
  <svg width={16} height={16} fill="none" viewBox="0 0 16 16" className={className}>
    <circle cx={8} cy={8} r={7} stroke="#8fffde" strokeWidth={1.5} fill="none" />
    <text x={8} y={12} textAnchor="middle" fontSize={11} fill="#8fffde" fontFamily="Geist Mono">i</text>
  </svg>
);

// Tooltip, appears on hover, accessible for ⓘ
const Tooltip = ({label}: {label:string}) => (
  <span className="relative ml-1 cursor-pointer group inline-block align-middle">
    <InfoIcon />
    <span
      className="z-50 rounded bg-neutral-900 border border-[#222] px-2 py-1 text-xs text-white font-mono shadow absolute left-1/2 -translate-x-1/2 whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none mt-2 transition-opacity duration-150"
      role="tooltip"
    >
      {label}
    </span>
  </span>
);

const Chip = ({label, selected, onClick}:{label:string,selected:boolean,onClick:()=>void}) => (
  <button
    className={`font-mono px-3 py-1 rounded-full text-xs mr-2 mb-2 border transition
      ${selected ? 'bg-[#222] border-[1.5px] border-cyan-500 text-cyan-100' : 'bg-transparent border-[#333] text-neutral-300 hover:border-cyan-400'}`}
    onClick={onClick}
    type="button"
  >{label}</button>
);

const Slider = ({min, max, step, value, setValue}:{min:number,max:number,step:number,value:number[],setValue:(v:number[])=>void}) => {
  // double-range slider, custom implementation for simple range
  return (
    <div className='flex items-center gap-3'>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value[0]}
        onChange={e => setValue([+e.target.value, Math.max(+e.target.value, value[1])])}
        className="range-thumb w-28"
      />
      <span className="font-mono text-xs px-1">–</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value[1]}
        onChange={e => setValue([Math.min(+e.target.value, value[0]), +e.target.value])}
        className="range-thumb w-28"
      />
      <span className="font-mono text-xs bg-[rgba(20,255,200,0.08)] ml-2 px-2 py-0.5 rounded">
        {formatPct(value[0])}–{formatPct(value[1])}
      </span>
    </div>
  );
};

// --- MAIN PAGE ---

export default function ExecDashboard() {
  // --- Filters ---
  const [search, setSearch] = useState('');
  const [selectedOrigins, setSelOrigins] = useState<string[]>([]);
  const [selectedSkus, setSelSkus] = useState<string[]>([]);
  const [tariffRange, setTariffRange] = useState<[number,number]>([0,25]);
  const [sortKey, setSortKey] = useState<'impact'|'value'|'tariff'>('impact');
  const [sortDir, setSortDir] = useState<'desc'|'asc'>('desc');
  // simulation seed controls the random offset
  const [simSeed, setSimSeed] = useState(777);
  // Details panel, live log
  const [showDetails, setShowDetails] = useState(false);
  const [showTerminal, setShowTerminal] = useState(false);

  // Last updated (hydration safe: don't show initially)
  const [lastUpdated, setLastUpdated] = useState<string>('—');
  useEffect(() => {
    const d = new Date();
    setLastUpdated(
      d.toLocaleString('en-US',{month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})
    );
  }, [simSeed]);

  // --- Filter/Sort Data ---
  // pull unique SKU, Origin list from lanes
  const allOrigins = useMemo(() => (
    [...new Set(RAW_LANES.map(l => l.origin))]
  ), []);
  const allSkus = useMemo(() => (
    [...new Set(RAW_LANES.map(l => l.sku))]
  ), []);

  // simulation "deltas": perturb value/tariff a bit, per seed to be 0-hydration
  const lanes = useMemo(() => {
    return RAW_LANES.map((l,i) => {
      const prng = mulberry32(l.id.split('-')[1].length*100 + simSeed + i*300);
      // +/–1–3% to value and tariff (stable per seed)
      const driftTariff = l.tariff + (prng()*2.5 - 1.25);
      const driftValue = l.value + Math.round((prng()*2 - 1)*0.04*l.value); // ~±4%
      const tariff = Math.max(0, Math.min(25, +(driftTariff.toFixed(1))));
      const value = Math.max(50_000, Math.round(driftValue));
      const impact = Math.round(value * (tariff/100));
      return {
        ...l,
        tariff,
        value,
        impact
      }
    });
  }, [simSeed]);

  // Apply filters
  const filtered = useMemo(() => {
    // search matches id/sku/origin/full code
    return lanes.filter(l => {
      let matches = true;
      if (search) {
        const s = search.toLowerCase();
        matches =
          l.id.toLowerCase().includes(s) ||
          l.sku.toLowerCase().includes(s) ||
          l.origin.toLowerCase().includes(s) ||
          l.originCode.toLowerCase().includes(s) ||
          `${l.origin} (${l.originCode})`.toLowerCase().includes(s);
      }
      if (selectedOrigins.length) {
        matches = matches && selectedOrigins.includes(`${l.origin} (${l.originCode})`);
      }
      if (selectedSkus.length) {
        matches = matches && selectedSkus.includes(l.sku);
      }
      if (l.tariff < tariffRange[0] || l.tariff > tariffRange[1]) {
        matches = false;
      }
      return matches;
    });
  }, [lanes, search, selectedOrigins, selectedSkus, tariffRange]);

  // Sorting
  const filteredSorted = useMemo(() => {
    const arr = filtered.slice();
    arr.sort((a,b) => {
      let valA = a[sortKey], valB = b[sortKey];
      if (sortDir === 'desc') return valB - valA;
      return valA - valB;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  // Save ALL lane origins and skus (for filter bar UI)
  const allOriginChips = useMemo(() =>
    COUNTRY_MAP
      .filter(c => allOrigins.includes(c.name))
      .map(c => `${c.name} (${c.code})`)
    , [allOrigins]);

  // --- Derived: KPIs, Chart Data ---

  // KPIs
  // sparkline is deterministic per simSeed/filtered
  function getKpiSpark(prngSeed: number): number[] {
    const base = 12;
    const prng = mulberry32(prngSeed + simSeed);
    // stable series relative to seed
    return Array.from({length:base}, (_,i)=>Math.round(prng() * (7-i*0.3) + (prngSeed%7)*2));
  }

  const kpiTotalLanes = filtered.length;
  const kpiTotalValue = filtered.reduce((s,l)=>s+l.value,0);
  const kpiAvgTariff = filtered.length ? filtered.reduce((s,l)=>s+l.tariff,0)/filtered.length : 0;
  // Potential savings: difference between China & Nearshore lanes impact ($), assuming US can nearshore to MX/VN/CA.
  const kpiSavings = useMemo(() => {
    // For plausible fake: total China impact minus low-tariff lanes.
    const chinaImpact = filtered.filter(l=>l.origin==='China').reduce((s,l)=>s+l.impact,0);
    const avgNearshore = filtered.filter(l=>['Mexico','Vietnam','Canada'].includes(l.origin)).reduce((s,l)=>s+l.impact,0);
    const savings = Math.max(0, chinaImpact - avgNearshore);
    return savings;
  }, [filtered]);

  // --- KPI Strip ---

  const kpis = [
    {
      label: "Total Lanes",
      value: formatCount(kpiTotalLanes),
      accent: NEON,
      spark: getKpiSpark(21)
    },
    {
      label: "Total Value",
      value: formatMoney(kpiTotalValue),
      accent: ACCENT_DARK,
      spark: getKpiSpark(23)
    },
    {
      label: "Avg Tariff",
      value: formatPct(kpiAvgTariff),
      accent: '#9eff5c',
      spark: getKpiSpark(27)
    },
    {
      label: "Potential Savings",
      value: formatMoney(kpiSavings),
      accent: '#e973ff',
      spark: getKpiSpark(35)
    }
  ];

  // Waterfall chart: per-group sum of impact
  const impactGroups = [
    {
      name: "China",
      value: filtered.filter(l=>l.origin==='China').reduce((s,l)=>s+l.impact,0),
      code: 'CN'
    },
    {
      name: "Nearshore",
      value: filtered.filter(l=>['Mexico','Vietnam','Canada'].includes(l.origin)).reduce((s,l)=>s+l.impact,0),
      code: "MX/VN/CA"
    },
    {
      name: "Net Savings",
      value: Math.max(0, filtered.filter(l=>l.origin==='China').reduce((s,l)=>s+l.impact,0) -
                        filtered.filter(l=>['Mexico','Vietnam','Canada'].includes(l.origin)).reduce((s,l)=>s+l.impact,0)),
      code: 'ΔUSD'
    }
  ];

  // Scatter/bubble chart: per-lane, x=tariff, y=value, size=impact, color=origin
  const scatterData = filteredSorted.slice(0, 22).map(l => ({
    id: l.id,
    sku: l.sku,
    origin: l.origin,
    originCode: l.originCode,
    x: +l.tariff.toFixed(3),
    y: +l.value,
    z: Math.sqrt(l.impact),
    impact: l.impact
  }));

  // Tariff histogram
  const histoBuckets = Array.from({length: 6}, (_,i)=>({bin: i*5, count: 0}));
  filtered.forEach(lane=>{
    const idx = Math.min(histoBuckets.length-1, Math.floor(lane.tariff/5));
    histoBuckets[idx].count+=(1);
  });
  // median
  const sortedT = [...filtered.map(l=>l.tariff)].sort((a,b)=>a-b);
  const medianTariff = sortedT.length ? sortedT[Math.floor(sortedT.length/2)] : 0;

  // Origin count, donut chart
  const originAgg = useMemo(() => {
    const out:{[key:string]:number} = {};
    for (const l of filtered) out[l.origin] = (out[l.origin]||0)+1;
    return Object.entries(out).map(([name, count])=>({
      name, count, code: COUNTRY_MAP.find(c=>c.name===name)?.code || ''
    }));
  }, [filtered]);

  // Top5 lanes (by Impact)
  const top5 = filteredSorted.slice(0,5);

  // Decision matrix: compute delta (China landed+tariff)–(nearshore landed)
  const decisionMatrix = useMemo(() => {
    // fake targets for each China lane (could be nearshored to one other nearshore lane)
    let matrix = [];
    for (let c of filteredSorted) {
      if (c.origin !== 'China') continue;
      // fake paired lane: min-tariff among MX/VN/CA with same SKU or random
      const alt = filteredSorted.find(l2 =>
        ['Mexico','Vietnam','Canada'].includes(l2.origin) && l2.sku===c.sku
      ) || filteredSorted.find(l2 => ['Mexico','Vietnam','Canada'].includes(l2.origin));
      if (alt) {
        const delta = (c.value + c.value * (c.tariff/100)) - (alt.value + alt.value * (alt.tariff/100));
        matrix.push({
          from: c,
          to: alt,
          delta: Math.round(delta),
          confidence: Math.round(((c.confidence+alt.confidence)/2))
        });
      }
    }
    return matrix;
  }, [filteredSorted]);

  // --- Handler fns ---
  function resetFilters() {
    setSearch('');
    setSelOrigins([]);
    setSelSkus([]);
    setTariffRange([0,25]);
    setSortKey('impact');
    setSortDir('desc');
  }
  function simulate() {
    setSimSeed(s => s+31);
  }

  return (
    <main className="min-h-screen bg-[#15161b] text-white font-mono relative">
      {/* Main symmetric container */}
      <div className="max-w-7xl mx-auto px-6 pt-8 pb-4">

        {/* FILTER BAR */}
        <motion.div
          className="sticky top-0 z-20 bg-[#171822d9] border-b border-[#222] py-3 backdrop-blur flex flex-col gap-2"
          initial={{ y: -20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{delay:0.1, duration:0.4, type:'spring'}}
        >
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            {/* Search */}
            <input
              value={search}
              onChange={e=>setSearch(e.target.value)}
              className="bg-[#222] rounded px-3 py-1 mr-2 w-48 outline-cyan-400/70
                placeholder:text-neutral-400 border border-[#2a2a36] text-sm font-mono"
              placeholder="Search Lane/SKU/Origin"
            />
            {/* Origin chips */}
            <div className="flex flex-row flex-nowrap overflow-x-auto gap-2 items-center">
              <span className="font-mono text-xs text-neutral-400 mr-1">Origin</span>
              {allOriginChips.map(label =>
                <Chip
                  key={label}
                  label={label}
                  selected={selectedOrigins.includes(label)}
                  onClick={()=>{
                    if (selectedOrigins.includes(label))
                      setSelOrigins(selectedOrigins.filter(s=>s!==label));
                    else setSelOrigins([...selectedOrigins, label]);
                  }}
                />
              )}
              <Tooltip label={ORIGIN_TT} />
            </div>
            {/* SKU chips */}
            <div className="flex flex-row flex-nowrap overflow-x-auto gap-1 items-center">
              <span className="font-mono text-xs text-neutral-400 mx-1">SKU</span>
              {allSkus.slice(0,6).map((sku) =>
                <Chip
                  key={sku}
                  label={sku}
                  selected={selectedSkus.includes(sku)}
                  onClick={()=>{
                    if (selectedSkus.includes(sku))
                      setSelSkus(selectedSkus.filter(s=>s!==sku));
                    else setSelSkus([...selectedSkus, sku]);
                  }}
                />
              )}
            </div>
            {/* Tariff slider */}
            <div className="flex items-center ml-2">
              <span className="font-mono text-xs text-neutral-400 mr-1">Tariff %</span>
              <Slider
                min={0}
                max={25}
                step={0.1}
                value={tariffRange}
                setValue={v=>setTariffRange([+v[0].toFixed(1), +v[1].toFixed(1)])}
              />
            </div>
            {/* Sort dropdown */}
            <div className="flex flex-row items-center ml-2">
              <span className="text-xs font-mono text-neutral-400 mr-1">Sort</span>
              <select
                value={sortKey}
                onChange={e=>setSortKey(e.target.value as any)}
                className="bg-[#222] text-neutral-200 border border-[#333] rounded px-2 py-1 font-mono text-xs outline-cyan-400/70"
              >
                <option value="impact">Impact</option>
                <option value="value">Value</option>
                <option value="tariff">Tariff</option>
              </select>
              <button
                className="ml-1 px-1 text-sm bg-[#232333] border rounded border-[#353545]"
                title="Toggle sort direction"
                onClick={()=>setSortDir(d=>d==='desc'?'asc':'desc')}
                type="button"
              >
                {sortDir==='desc'
                  ? <svg width={12} height={13} viewBox="0 0 14 14" className="inline"><path d="M3 7l4 4 4-4" stroke="#77f1ff" strokeWidth={2} fill="none"/></svg>
                  : <svg width={12} height={13} viewBox="0 0 14 14" className="inline"><path d="M3 10l4-4 4 4" stroke="#77f1ff" strokeWidth={2} fill="none"/></svg>
                }
              </button>
            </div>
            {/* Reset + Simulate */}
            <button className="ml-2 px-3 py-1 rounded-full text-xs bg-neutral-900 border border-cyan-900 font-mono text-cyan-200 hover:bg-cyan-800/30"
              onClick={resetFilters}>Reset</button>
            <button className="ml-1 px-3 py-1 rounded-full text-xs bg-cyan-900/90 font-mono text-cyan-100 border border-cyan-600 shadow hover:bg-cyan-600/30"
              onClick={simulate}>Simulate</button>
            {/* Right align: Last Updated */}
            <div className="flex-grow" />
            <div className="ml-auto flex flex-row items-center text-xs font-mono text-neutral-400">
              Last updated:&nbsp;<span className="text-neutral-100">{lastUpdated}</span>
            </div>
          </div>
        </motion.div>

        {/* KPI STRIP */}
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {kpis.map((k,ix) => (
            <div key={k.label} className="rounded-xl border border-[#222] bg-[#181922] px-4 py-3 flex flex-col"
              style={{minWidth:0}}>
              <div className="flex items-center mb-1">
                <span className="font-mono text-neutral-400 text-xs">{k.label}</span>
                {(k.label==="Avg Tariff" || k.label==="Potential Savings") &&
                  <Tooltip label={k.label==="Avg Tariff"?IMPACT_TT:DELTA_TT} />}
              </div>
              <div className="flex items-end gap-2">
                <span className="text-lg font-bold tracking-wide" style={{color:k.accent}}>{k.value}</span>
                {/* Tiny sparkline */}
                <ResponsiveContainer width={40} height={20}>
                  <LineChart data={k.spark.map(v=>({v}))}>
                    <Line
                      dataKey="v"
                      stroke={k.accent}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          ))}
        </div>

        {/* EXECUTIVE VISUALS (GRIDS) */}
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-7 gap-6">
          {/* Main comparison/impact charts */}
          <div className="col-span-1 lg:col-span-4 flex flex-col gap-6">
            {/* Waterfall Bar */}
            <div className="rounded-2xl bg-[#181922] border border-[#222] px-6 pt-5 pb-3 flex flex-col relative min-h-[265px] shadow">
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-mono text-white tracking-tight flex items-center gap-2">
                  Exec Impact
                  <Tooltip label={'Breakout of landed tariff costs by origin. '+IMPACT_TT} />
                </div>
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={impactGroups}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#232340"/>
                  <XAxis dataKey="name" axisLine={false} tick={{ fill:'#bffcff', fontSize:12, fontFamily:'Geist Mono' }} />
                  <YAxis hide />
                  <Bar dataKey="value" radius={[12,12,0,0]}>
                    {impactGroups.map((entry, ix) => (
                      <Cell key={ix} fill={
                        entry.name==="China"?COUNTRY_COLORS['China']:
                        entry.name==="Nearshore"?COUNTRY_COLORS['Mexico']:'#e973ff'
                      } />
                    ))}
                    <LabelList
                      dataKey="value"
                      content={({ x, y, value, index }) => (
                        <text
                          x={x!+32}
                          y={y!+18}
                          fill="#bffcff"
                          fontSize={13}
                          fontFamily="Geist Mono"
                          fontWeight={600}
                        >{formatMoney(value as number)}</text>
                      )}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            {/* Scatter / Bubble Impact */}
            <div className="rounded-2xl bg-[#181922] border border-[#222] px-6 pt-5 pb-2 flex flex-col relative min-h-[265px] shadow">
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-mono text-white tracking-tight flex items-center gap-2">
                  Lane Impact
                  <Tooltip label={'x=tariff%, y=value, size=impact, color by origin.'+' '+IMPACT_TT} />
                </div>
              </div>
              <ResponsiveContainer width="100%" height={190}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="2 2" stroke="#232340" />
                  <XAxis type="number" dataKey="x" name="Tariff %" unit="%" tick={{ fill:'#bffcff', fontSize:12 }} domain={[0,26]} />
                  <YAxis type="number" dataKey="y" name="Lane Value" domain={[0,Math.max(2_600_000, ...scatterData.map(d=>d.y))]} tickFormatter={formatMoney} tick={{ fill:'#bffcff', fontSize:12 }} />
                  <ZAxis dataKey="z" range={[30, 110]} />
                  <RechartsTooltip
                    content={({active,payload})=>{
                      if (!active || !payload?.length) return null;
                      const p = payload[0].payload;
                      return (
                        <div className="rounded bg-[#232333] border border-[#444] px-3 py-2 text-xs shadow font-mono">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-bold text-base" style={{color:COUNTRY_COLORS[p.origin]}}>{p.origin} ({p.originCode})</span>
                          </div>
                          <div>ID: <b>{p.id}</b></div>
                          <div>SKU: <b>{p.sku}</b></div>
                          <div>Value: {formatMoney(p.y)}</div>
                          <div>Tariff: {formatPct(p.x)}</div>
                          <div>Impact: {formatMoney(p.impact)}</div>
                        </div>
                      );
                    }}
                  />
                  <Legend verticalAlign='top' align='right' height={28} iconType="circle"
                    payload={COUNTRY_MAP.filter(c => scatterData.some(d=>d.origin===c.name)).map(c=>({
                      value: c.name,
                      type: 'circle',
                      color: COUNTRY_COLORS[c.name],
                      id: c.code
                    }))}
                  />
                  <Scatter
                    name="Lanes"
                    data={scatterData}
                    fillOpacity={0.95}
                  >
                    {scatterData.map((p,ix)=>(
                      <Cell
                        key={p.id}
                        fill={COUNTRY_COLORS[p.origin] || ACCENT_DARK}
                        stroke="#213fff"
                        strokeWidth={p.origin==='China'?1.5:0}
                        opacity={0.96}
                      />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* RIGHT COLUMN: HISTOGRAM + DONUT + RISK LIST */}
          <div className="col-span-1 lg:col-span-3 flex flex-col gap-6">
            {/* Tariff Histogram */}
            <div className="rounded-2xl bg-[#181922] border border-[#222] min-h-[105px] px-6 pt-5 pb-2 flex flex-col">
              <div className="flex items-center text-sm font-mono text-white gap-2 mb-1">
                Tariffs
                <Tooltip label={'Lane count by tariff rate. Median marker.'} />
              </div>
              <ResponsiveContainer width="100%" height={54}>
                <BarChart data={histoBuckets}>
                  <XAxis dataKey="bin" axisLine={false} tickLine={false}
                    tickFormatter={v => `${v}–${v+4.9}%`} tick={{ fill:'#aae8de', fontSize:11 }} />
                  <YAxis hide />
                  <Bar dataKey="count" radius={[8,8,0,0]} fill="#4fd7de">
                    <LabelList dataKey="count" position="top"
                      content={({x,y,value})=>
                        value ? <text x={x!+12} y={Math.max(22,y!-3)} fill="#afefff" fontSize={10}>{value as number}</text> : null}
                    />
                  </Bar>
                  <ReferenceLine
                    x={Math.round(medianTariff/5)*5}
                    stroke="#f7ff32" strokeDasharray="3 3"
                    label={<text x={0} y={5} fill="#f7ff32" fontSize={10}>Median</text>}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            {/* Origin Donut (composition) */}
            <div className="rounded-2xl bg-[#181922] border border-[#222] min-h-[130px] px-6 pt-5 pb-2 flex flex-col">
              <div className="flex items-center text-sm font-mono text-white gap-2 mb-1">
                Origin Mix
                <Tooltip label={'Distribution of lanes by country of origin.'+ ' '+ORIGIN_TT} />
              </div>
              <ResponsiveContainer width="100%" height={60}>
                <PieChart>
                  <Pie
                    data={originAgg}
                    dataKey="count"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={18}
                    outerRadius={30}
                    isAnimationActive={false}
                    stroke="#13191A"
                    strokeWidth={3}
                  >
                    {originAgg.map((entry,ix) => (
                      <Cell key={ix} fill={COUNTRY_COLORS[entry.name] || "#4fd7de"} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-row flex-wrap justify-center gap-2 mt-1">
                {originAgg.map((entry,ix)=>(
                  <span key={ix} className="inline-flex items-center px-2 py-0.5 rounded-lg bg-[#222b] text-xs" style={{color:COUNTRY_COLORS[entry.name]}}>{entry.name} ({entry.code}):&nbsp;{entry.count}</span>
                ))}
              </div>
            </div>
            {/* Top Risks list */}
            <div className="rounded-2xl bg-[#181922] border border-[#222] min-h-[60px] px-6 pt-3 pb-2 flex flex-col">
              <div className="flex items-center text-xs font-mono text-neutral-300 gap-2 mb-1">
                Top Origin Exposures <Tooltip label="Count of highest tariff lanes by country." />
              </div>
              <ul className="flex flex-col gap-1">
                {originAgg
                  .slice()
                  .sort((a,b)=>b.count-a.count)
                  .slice(0,3)
                  .map((entry,ix)=>(
                  <li key={ix} className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full block" style={{background:COUNTRY_COLORS[entry.name]}} />
                    <span className="font-mono">{entry.name} ({entry.code})</span>
                    <span className="ml-2 text-cyan-200 font-mono">{entry.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* TOP 5 LANES */}
        <div className="mt-5">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-base font-mono text-white">Top 5 Lanes</span>
            <Tooltip label="Most exposed lanes by impact." />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {top5.map((lane,ix)=>(
              <div key={lane.id}
                className="bg-[#191a23] border border-[#2e2e3e] rounded-2xl px-4 py-3 flex flex-col shadow min-w-0"
              >
                <div className="flex items-center gap-2 mb-3">
                  <span className={`rounded-full bg-[#222] border border-neutral-500 px-[9px] font-bold text-cyan-200 mr-2 text-sm`}>{ix+1}</span>
                  <span className="font-mono text-white">{lane.id}</span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className="text-cyan-400 text-lg font-bold tracking-tight">{formatMoney(lane.impact)}</span>
                  <span className="text-xs text-neutral-400 ml-3 font-mono">{lane.origin} ({lane.originCode})</span>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs font-mono text-orange-200">Value: {formatMoney(lane.value)}</span>
                  <span className="text-xs font-mono text-pink-100">Tariff: {formatPct(lane.tariff)}</span>
                </div>
                <div className="mt-2">
                  <div className="w-full h-2 rounded bg-[#262833] relative overflow-hidden">
                    <div
                      className="h-2 rounded bg-cyan-400 transition-all"
                      style={{width: `${Math.min(100, 30+lane.impact/kpiTotalValue*90)}%`, opacity:0.7}}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* DETAILS / TABLES */}
        <div className="mt-7">
          <button
            onClick={()=>setShowDetails(v=>!v)}
            className="px-4 py-2 rounded-lg font-mono border border-cyan-800 bg-slate-900 hover:bg-cyan-800/20 text-cyan-200"
          >
            {showDetails?'Hide Details':'View Details'}
          </button>
          {showDetails && (
            <motion.div
              className="mt-4"
              initial={{ opacity:0, y:8 }}
              animate={{ opacity:1, y:0 }}
              exit={{ opacity:0, y:18 }}>
              {/* FULL LANES TABLE */}
              <div className="max-h-96 overflow-x-auto rounded-xl border border-[#202233] shadow mb-4 bg-[#181c23]">
              <table className="min-w-full text-sm font-mono border-collapse sticky-header">
                <thead className="sticky top-0 bg-[#232444] z-10">
                  <tr>
                    <th className="px-3 py-2 text-left">Lane ID</th>
                    <th className="px-3 py-2 text-left">Origin</th>
                    <th className="px-3 py-2 text-left">SKU</th>
                    <th className="px-3 py-2 text-left">Value</th>
                    <th className="px-3 py-2 text-left">Tariff %</th>
                    <th className="px-3 py-2 text-left">Impact</th>
                    <th className="px-3 py-2 text-left">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSorted.map(l=>(
                    <tr key={l.id} className="group hover:bg-[#34365866] transition-colors">
                      <td className="px-3 py-1">{l.id}</td>
                      <td className="px-3 py-1">{l.origin} ({l.originCode})</td>
                      <td className="px-3 py-1">{l.sku}</td>
                      <td className="px-3 py-1">{formatMoney(l.value)}</td>
                      <td className="px-3 py-1">{formatPct(l.tariff)}</td>
                      <td className="px-3 py-1 font-bold" style={{color:l.impact>80_000?'#ffe357':''}}>{formatMoney(l.impact)}</td>
                      <td className="px-3 py-1">{l.confidence}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>

              {/* Live LOG/Terminal (drawer) */}
              <button
                onClick={()=>setShowTerminal(v=>!v)}
                className="px-4 py-1 mt-2 rounded-md font-mono border border-pink-800 bg-[#1e1127] hover:bg-pink-800/20 text-pink-200"
              >
                {showTerminal?'Hide Log':'Show Live Log'}
              </button>
              <AnimatePresence>
                {showTerminal && (
                  <motion.div
                    initial={{ maxHeight:0, opacity:0 }}
                    animate={{ maxHeight:280, opacity:1 }}
                    exit={{ maxHeight:0, opacity:0 }}
                    className="overflow-auto transition-all duration-200 bg-black/90 border border-[#222] mt-3 rounded-lg shadow"
                  >
                    <pre className="text-xs p-4 font-mono text-green-400 leading-6">
{`[${lastUpdated}] Simulation seed: ${simSeed} – Lanes: ${filteredSorted.length}
Top China lane: ${filteredSorted.find(l=>l.origin==="China")?.id}
Potential savings (China minus nearshore): ${formatMoney(kpiSavings)}`}
                    </pre>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Decision Matrix Table */}
              <div className="mt-6">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono uppercase tracking-tight text-xs text-lime-300">Decision Matrix</span>
                  <Tooltip label={DELTA_TT} />
                </div>
                <div className="overflow-x-auto rounded-xl border border-[#19222e] shadow bg-[#161d1d]">
                  <table className="min-w-full text-xs font-mono">
                    <thead className="bg-[#222243]">
                      <tr>
                        <th className="px-2 py-2 text-left">From (China)</th>
                        <th className="px-2 py-2 text-left">To (Nearshore)</th>
                        <th className="px-2 py-2 text-left">ΔUSD</th>
                        <th className="px-2 py-2 text-left">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {decisionMatrix.map((row,ix)=>(
                        <tr key={ix} className="group hover:bg-[#283c3266]">
                          <td className="px-2 py-1">{row.from.id}&nbsp;<span className="text-neutral-400">{row.from.origin} ({row.from.originCode})</span></td>
                          <td className="px-2 py-1">{row.to.id}&nbsp;<span className="text-neutral-400">{row.to.origin} ({row.to.originCode})</span></td>
                          <td className="px-2 py-1" style={{
                            color: row.delta>0?'#40e1ff':'#fda69a',
                            fontWeight:600
                          }}>{formatMoney(row.delta)}</td>
                          <td className="px-2 py-1">
                            <span className={`px-2 py-0.5 rounded font-bold text-xs
                              ${row.confidence>=95?'bg-green-700 text-green-200':
                                row.confidence>=85?'bg-orange-700 text-orange-200':
                                'bg-red-700 text-red-200'
                              }`}>
                              {row.confidence}%
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>
      <style jsx global>{`
        html, body { font-family: "Geist Mono", Menlo, Consolas, Courier, monospace; }
        .range-thumb::-webkit-slider-thumb {
          background: #3be6b4; border-radius: 100px; box-shadow: 0 0 0 2px #232, 0 0 0 5px #131;
        }
        .sticky-header th { position: sticky; top: 0; z-index: 10; background: #232444; }
      `}</style>
    </main>
  );
}