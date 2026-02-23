'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartTooltip,
  ResponsiveContainer,
  LabelList,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
  PieChart,
  Pie,
  ReferenceLine,
} from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';

// --- CONSTANTS ---
const CONTAINER_CLASS = 'max-w-7xl mx-auto px-6';
const DARK_BG = 'bg-[#14171a]';
const SOFT_NEON = 'text-[#5fffe8]';
const NEON_BG = 'bg-[#192b2a]';
const BORDER = 'border border-[#23272a]';
const CARD = `${NEON_BG} ${BORDER} rounded-2xl shadow-sm`;
const CHIP = `inline-flex items-center px-3 py-1 mr-2 mb-2 rounded-full font-mono text-xs font-semibold ${BORDER} bg-[#222d2d] transition hover:bg-[#263938] cursor-pointer`;

const LANES_COUNT = 32;
const SPARK_POINTS = 12;

// --- TYPES ---
type LaneType = {
  id: string;
  origin: string;
  originCode: string;
  nearshore: string;
  nearshoreCode: string;
  sku: string;
  skuId: string;
  value: number;
  tariff: number;
  impact: number;
  nearshoreTariff: number;
  nearshoreValue: number;
  nearshoreImpact: number;
  savings: number;
};

// -- Countries --
const COUNTRIES = [
  { code: 'CN', name: 'China', full: 'China (CN)', color: '#FFD55F' },
  { code: 'VN', name: 'Vietnam', full: 'Vietnam (VN)', color: '#42F99E' },
  { code: 'MX', name: 'Mexico', full: 'Mexico (MX)', color: '#5AC8FA' },
  { code: 'US', name: 'United States', full: 'United States (US)', color: '#FFD5A5' },
  { code: 'CA', name: 'Canada', full: 'Canada (CA)', color: '#91AFFF' },
];

const SKU_LIST = [
  { id: 'A100', label: 'Bolt XL' },
  { id: 'B200', label: 'Precision Coil' },
  { id: 'C300', label: 'Steel Dowel' },
  { id: 'D400', label: 'Mini Fuse' },
  { id: 'E500', label: 'Insulator' },
  { id: 'F600', label: 'Magneto' },
];

// --- PRNG ---
function mulberry32(a: number) {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// --- Format Helpers ---
function formatMoney(val: number) {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(val < 10_000_000 ? 1 : 0)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(val < 10_000 ? 1 : 0)}K`;
  return `$${Math.round(val)}`;
}
function formatPct(val: number) {
  return `${val.toFixed(1)}%`;
}
function formatCount(val: number) {
  return Math.round(val).toLocaleString();
}
function formatDate(date: Date) {
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

// --- SVG ICONS ---
const InfoIcon = ({ className = '', size = 18 }: { className?: string; size?: number }) => (
  <svg className={className} width={size} height={size} style={{ flexShrink: 0, display: 'inline' }} viewBox="0 0 20 20" fill="none">
    <circle cx="10" cy="10" r="10" fill="#292B40" />
    <text x="10" y="14" textAnchor="middle" fontSize="12" fill="#5fffe8" fontFamily="monospace" fontWeight="bold">
      i
    </text>
  </svg>
);

const ResetIcon = ({ className = '', size = 16 }: { className?: string; size?: number }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 20 20" fill="none">
    <circle cx="10" cy="10" r="9" stroke="#8AECB6" strokeWidth="2" />
    <path d="M10 5V10L13.5 12" stroke="#8AECB6" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const ChevronDown = ({ className = '', size = 20, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 24 24" style={style}>
    <path d="M6 9l6 6 6-6" stroke="#7cfffc" strokeWidth="2" fill="none" strokeLinecap="round" />
  </svg>
);

// --- POPOVER TOOLTIP ---
function Tooltip({ label }: { label: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative ml-1 inline-block">
      <button
        tabIndex={0}
        type="button"
        aria-label="Info"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        className="align-middle"
      >
        <InfoIcon size={15} />
      </button>
      {show && (
        <div className="z-30 absolute left-1/2 -translate-x-1/2 top-[150%] bg-[#292B40] text-white text-xs px-3 py-1 rounded shadow-md whitespace-nowrap opacity-95 pointer-events-none border border-[#1AE3DA]">
          {label}
        </div>
      )}
    </span>
  );
}

// --- SEEDABLE DATA ---
function useDemoData(simSeed: number) {
  const rand = useMemo(() => mulberry32(simSeed), [simSeed]);

  const lanes = useMemo(() => {
    const result: LaneType[] = [];
    for (let i = 0; i < LANES_COUNT; ++i) {
      // pick origin among CN/VN/MX
      const originIdx = Math.floor(rand() * 3);
      const origin = COUNTRIES[originIdx];

      // nearshore logic (simple, deterministic)
      const nearshoreIdx = origin.code === 'CN' ? 2 : origin.code === 'VN' ? 3 : 3; // CN->MX, VN->US, MX->US
      const nearshore = COUNTRIES[nearshoreIdx];

      const sku = SKU_LIST[Math.floor(rand() * SKU_LIST.length)];
      const laneId = `${origin.code}-${nearshore.code}-${sku.id}`;

      let tariff =
        origin.code === 'CN' ? 10 + Math.round(rand() * 15) : origin.code === 'VN' ? 5 + Math.round(rand() * 7) : 0 + Math.round(rand() * 3);
      tariff = Math.round(tariff * 10) / 10;

      let value = (rand() * 2.4 + 0.1) * 1_000_000;
      value = Math.round(value / 1000) * 1000;

      const impact = Math.round(value * (tariff / 100));

      const nearshoreTariff = nearshore.code === 'MX' ? 3 + Math.round(rand() * 3) : nearshore.code === 'US' ? 0 : 7 + Math.round(rand() * 3);
      const nearshoreValue = Math.round((value * (0.93 + (rand() - 0.5) / 50)) / 1000) * 1000;
      const nearshoreImpact = Math.round(nearshoreValue * (nearshoreTariff / 100));

      result.push({
        id: laneId,
        origin: origin.name,
        originCode: origin.code,
        nearshore: nearshore.name,
        nearshoreCode: nearshore.code,
        sku: sku.label,
        skuId: sku.id,
        value,
        tariff,
        impact,
        nearshoreTariff,
        nearshoreValue,
        nearshoreImpact,
        savings: impact - nearshoreImpact,
      });
    }
    return result;
  }, [simSeed, rand]);

  const sparkHistory = useMemo(() => {
    const arr: number[][] = [[], [], [], []];
    const base = (simSeed % 101) + 45;
    for (let s = 0; s < 4; ++s) {
      let v = base + s * 11;
      for (let i = 0; i < SPARK_POINTS; ++i) {
        const bump = Math.sin(0.7 * i + s) * 4.9 + rand() * 7;
        arr[s][i] = Math.round((v + bump) * 1000) / 1000;
        v *= 1.02 + s * 0.0006;
      }
    }
    return arr;
  }, [simSeed, rand]);

  const dmRows = useMemo(() => {
    return lanes.slice(0, 6).map((lane, idx) => {
      const deltaUSD = Math.round(lane.value + lane.impact - (lane.nearshoreValue + lane.nearshoreImpact));
      return {
        key: `dm${idx}`,
        lane: lane.id,
        from: `${lane.origin} (${lane.originCode})`,
        to: `${lane.nearshore} (${lane.nearshoreCode})`,
        originValue: lane.value,
        originTariff: lane.tariff,
        originImpact: lane.impact,
        nearValue: lane.nearshoreValue,
        nearTariff: lane.nearshoreTariff,
        nearImpact: lane.nearshoreImpact,
        deltaUSD,
        confidence: [85, 70, 92, 78, 97, 60][idx] ?? 80,
      };
    });
  }, [lanes]);

  return { lanes, sparkHistory, dmRows };
}

// -- FILTERS / STATE --
const MIN_TARIFF = 0;
const MAX_TARIFF = 25;

const SORT_FIELDS = [
  { value: 'impact', label: 'Impact ($)' },
  { value: 'value', label: 'Lane Value ($)' },
  { value: 'tariff', label: 'Tariff (%)' },
];
const SORT_ORDERS = [
  { value: 'desc', label: 'High → Low' },
  { value: 'asc', label: 'Low → High' },
];

// --- COMPONENT ---
export default function CommandDashboard() {
  const [simSeed, setSimSeed] = useState(1234);
  const demo = useDemoData(simSeed);

  const [originCodes, setOriginCodes] = useState<string[]>([COUNTRIES[0].code, COUNTRIES[1].code, COUNTRIES[2].code]);
  const [skuIds, setSkuIds] = useState<string[]>([]);
  const [tariffRange, setTariffRange] = useState<[number, number]>([MIN_TARIFF, MAX_TARIFF]);
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState('impact');
  const [sortOrder, setSortOrder] = useState('desc');
  const [showTable, setShowTable] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const [showMatrix, setShowMatrix] = useState(false);

  const [lastUpdate, setLastUpdate] = useState<string>('—');
  useEffect(() => {
    setLastUpdate(formatDate(new Date()));
  }, [simSeed]);

  const filteredLanes = useMemo(() => {
    return demo.lanes.filter((lane) => {
      const matchesOrigin = originCodes.length ? originCodes.includes(lane.originCode) : true;
      const matchesSku = skuIds.length ? skuIds.includes(lane.skuId) : true;
      const matchesTariff = lane.tariff >= tariffRange[0] && lane.tariff <= tariffRange[1];
      const q = search.trim().toLowerCase();
      const matchesSearch =
        !q ||
        lane.id.toLowerCase().includes(q) ||
        lane.sku.toLowerCase().includes(q) ||
        lane.origin.toLowerCase().includes(q) ||
        lane.originCode.toLowerCase().includes(q);
      return matchesOrigin && matchesSku && matchesTariff && matchesSearch;
    });
  }, [demo.lanes, originCodes, skuIds, tariffRange, search]);

  const sortedLanes = useMemo(() => {
    const dir = sortOrder === 'desc' ? -1 : 1;
    const laneSorter = (a: LaneType, b: LaneType) => {
      if (sortField === 'impact') return dir * (a.impact - b.impact);
      if (sortField === 'value') return dir * (a.value - b.value);
      if (sortField === 'tariff') return dir * (a.tariff - b.tariff);
      return 0;
    };
    return [...filteredLanes].sort(laneSorter);
  }, [filteredLanes, sortField, sortOrder]);

  const kpi = useMemo(() => {
    const totalLanes = filteredLanes.length;
    const totalValue = filteredLanes.reduce((a, v) => a + v.value, 0);
    const avgTariff = filteredLanes.length ? filteredLanes.reduce((a, v) => a + v.tariff, 0) / filteredLanes.length : 0;
    const potentialSavings = filteredLanes.reduce((a, v) => a + Math.max(0, v.savings), 0);
    return { totalLanes, totalValue, avgTariff, potentialSavings };
  }, [filteredLanes]);

  const impactCompareData = useMemo(() => {
    let origImpact = 0;
    let nearImpact = 0;
    let savings = 0;
    for (const lane of filteredLanes) {
      origImpact += lane.impact;
      nearImpact += lane.nearshoreImpact;
      savings += Math.max(0, lane.savings);
    }
    return [
      { category: 'China', value: origImpact, fill: COUNTRIES.find((c) => c.code === 'CN')?.color ?? '#FFD55F' },
      { category: 'Nearshore', value: nearImpact, fill: COUNTRIES.find((c) => c.code === 'MX')?.color ?? '#5AC8FA' },
      { category: 'Net Savings', value: savings, fill: '#35FFD3' },
    ];
  }, [filteredLanes]);

  const scatterData = useMemo(() => {
    return filteredLanes.slice(0, 20).map((lane) => ({
      id: lane.id,
      x: lane.tariff,
      y: lane.value,
      z: lane.impact,
      originCode: lane.originCode,
      color: COUNTRIES.find((c) => c.code === lane.originCode)?.color || '#34DFFF',
      sku: lane.sku,
    }));
  }, [filteredLanes]);

  const tariffHist = useMemo(() => {
    const bins: Record<string, number> = {};
    for (const lane of filteredLanes) {
      const b = (Math.floor(lane.tariff / 2.5) * 2.5).toFixed(1);
      bins[b] = (bins[b] || 0) + 1;
    }
    const values = Object.entries(bins)
      .map(([range, count]) => ({ range, count }))
      .sort((a, b) => parseFloat(a.range) - parseFloat(b.range));

    const sortedTariffs = filteredLanes.map((l) => l.tariff).sort((a, b) => a - b);
    const mid = Math.floor(sortedTariffs.length / 2);
    let median = sortedTariffs.length
      ? sortedTariffs.length % 2
        ? sortedTariffs[mid]
        : (sortedTariffs[mid - 1] + sortedTariffs[mid]) / 2
      : 0;
    median = Math.round(median * 10) / 10;
    return { values, median };
  }, [filteredLanes]);

  const originCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const lane of filteredLanes) counts[lane.origin] = (counts[lane.origin] || 0) + 1;
    return COUNTRIES.map(({ name, color }) => ({ name, count: counts[name] || 0, color })).filter((o) => o.count);
  }, [filteredLanes]);

  const top5 = useMemo(() => sortedLanes.slice(0, 5), [sortedLanes]);

  function FilterChip({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
    return (
      <button className={`${CHIP} ${active ? SOFT_NEON + ' border-[#19E4D3] bg-[#1B2424]' : ''}`} type="button" onClick={onClick}>
        {children}
      </button>
    );
  }

  function Sparkline({ data }: { data: number[] }) {
    const min = Math.min(...data);
    const max = Math.max(...data);
    const points = data.map((v, i) => [
      Math.round((i / (data.length - 1)) * 62 * 1000) / 1000,
      Math.round(((max - v) / (max - min + 0.001)) * 18 * 1000) / 1000 + 2,
    ]);
    return (
      <svg viewBox="0 0 64 24" width={64} height={24}>
        <polyline points={points.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="#5fffe8" strokeWidth="2.5" opacity={0.82} />
        <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r="2" fill="#63ffd3" />
      </svg>
    );
  }

  function KpiCard({ label, val, spark, infoTip }: { label: string; val: string; spark: number[]; infoTip?: string }) {
    return (
      <div className={`${CARD} flex flex-1 min-w-0 p-4 items-center group`}>
        <span className="font-mono text-[#5fffe8] text-xs mr-2">
          {label}
          {infoTip && <Tooltip label={infoTip} />}
        </span>
        <span className="ml-auto font-bold text-lg text-white mr-3">{val}</span>
        <div className="h-8 w-16 shrink-0 flex items-center">
          <Sparkline data={spark} />
        </div>
      </div>
    );
  }

  return (
    <div className={`${DARK_BG} min-h-screen font-mono text-[#E3FDFC]`}>
      <main className={CONTAINER_CLASS}>
        {/* Sticky Filter Bar */}
        <section
          className={`sticky top-0 z-40 ${CARD} flex items-center justify-between overflow-x-auto gap-6 px-4 py-3 mt-6 mb-0 shadow-md`}
          style={{ backdropFilter: 'blur(6px)' }}
        >
          <div className="flex flex-wrap items-center gap-3 min-w-0">
            <input
              placeholder="Search Lane ID/SKU/Origin"
              className="bg-[#212d2a] border border-[#25363a] rounded-lg px-3 py-1 mr-2 w-40 font-mono text-[#BAFFE6] text-xs focus:outline-none focus:border-[#5FFFE8] transition"
              autoComplete="off"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

            <span className="ml-1 text-xs inline-flex items-center">
              <span className="pr-1">Origin:</span>
              <Tooltip label="Country of origin (ISO): China=CN, Canada=CA, Mexico=MX, Vietnam=VN, United States=US." />
            </span>

            <div className="flex flex-shrink gap-1.5 overflow-x-auto">
              {COUNTRIES.map(({ full, code }) => (
                <FilterChip
                  key={code}
                  active={originCodes.includes(code)}
                  onClick={() =>
                    setOriginCodes(originCodes.includes(code) ? originCodes.filter((c) => c !== code) : [...originCodes, code])
                  }
                >
                  {full}
                </FilterChip>
              ))}
            </div>

            <span className="ml-2 text-xs">SKU:</span>
            <div className="flex gap-1.5 overflow-x-auto">
              {SKU_LIST.map((sku) => (
                <FilterChip
                  key={sku.id}
                  active={skuIds.includes(sku.id)}
                  onClick={() => setSkuIds(skuIds.includes(sku.id) ? skuIds.filter((s) => s !== sku.id) : [...skuIds, sku.id])}
                >
                  {sku.label}
                </FilterChip>
              ))}
            </div>

            <div className="ml-2 flex items-center">
              <span className="mr-1 text-xs">Tariff:</span>
              <input
                type="range"
                min={MIN_TARIFF}
                max={MAX_TARIFF}
                value={tariffRange[0]}
                step={1}
                onChange={(e) => setTariffRange([+e.target.value, Math.max(tariffRange[1], +e.target.value)])}
                style={{ width: 50 }}
                className="accent-[#5fffe8] mx-1"
                aria-label="Tariff min"
              />
              <input
                type="range"
                min={MIN_TARIFF}
                max={MAX_TARIFF}
                value={tariffRange[1]}
                step={1}
                onChange={(e) => setTariffRange([Math.min(+e.target.value, tariffRange[0]), +e.target.value])}
                style={{ width: 50 }}
                className="accent-[#5fffe8] mx-1"
                aria-label="Tariff max"
              />
              <span className="ml-1 text-xs">
                {tariffRange[0]}–{tariffRange[1]}%
              </span>
            </div>

            <span className="ml-5 flex items-center text-xs">Sort:</span>

            <div className="relative">
              <select
                className="appearance-none font-mono border border-[#293E39] text-xs rounded px-2 py-1 bg-[#1b2224] pr-8 text-[#53ffd3] focus:outline-none"
                value={sortField}
                onChange={(e) => setSortField(e.target.value)}
              >
                {SORT_FIELDS.map((sf) => (
                  <option value={sf.value} key={sf.value}>
                    {sf.label}
                  </option>
                ))}
              </select>
              <span className="absolute right-2 top-2">
                <ChevronDown size={12} />
              </span>
            </div>

            <div className="relative ml-1">
              <select
                className="appearance-none font-mono border border-[#293E39] text-xs rounded px-2 py-1 bg-[#1b2224] pr-8 text-[#5FFFE8] focus:outline-none"
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
              >
                {SORT_ORDERS.map((o) => (
                  <option value={o.value} key={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <span className="absolute right-2 top-2">
                <ChevronDown size={12} />
              </span>
            </div>

            <button
              className={`${CHIP} border-[#363B3A] ml-4`}
              type="button"
              title="Reset filters"
              onClick={() => {
                setSimSeed(1234 + Math.floor(Math.random() * 1000));
                setOriginCodes([COUNTRIES[0].code, COUNTRIES[1].code, COUNTRIES[2].code]);
                setSkuIds([]);
                setTariffRange([MIN_TARIFF, MAX_TARIFF]);
                setSearch('');
                setSortField('impact');
                setSortOrder('desc');
              }}
            >
              <ResetIcon size={14} className="mr-1" /> Reset
            </button>

            <button
              className={`${CHIP} border-[#14FFE8] ml-2 bg-[#153e33]`}
              type="button"
              title="Simulate new scenario"
              onClick={() => setSimSeed((s) => s + 1)}
            >
              <span className="mr-1">∼</span> Simulate
            </button>
          </div>

          <span className="text-xs text-[#91a6ad] flex-0 shrink-0">
            Last updated: <span className="font-mono text-[#41FFD7]">{lastUpdate}</span>
          </span>
        </section>

        {/* KPI Strip */}
        <section className="mt-4 flex gap-5">
          <KpiCard label="Total Lanes" val={formatCount(kpi.totalLanes)} spark={demo.sparkHistory[0]} infoTip="Filtered lane count across origins and SKUs." />
          <KpiCard label="Total Value" val={formatMoney(kpi.totalValue)} spark={demo.sparkHistory[1]} infoTip="Sum of annualized lane values for selection." />
          <KpiCard label="Avg Tariff" val={formatPct(kpi.avgTariff)} spark={demo.sparkHistory[2]} infoTip="Average applied tariff rate (unweighted across lanes)." />
          <KpiCard label="Potential Savings" val={formatMoney(kpi.potentialSavings)} spark={demo.sparkHistory[3]} infoTip="Sum of (Origin impact − Nearshore impact) where positive." />
        </section>

        {/* Exec Visuals */}
        <section className="mt-4 grid grid-cols-1 lg:grid-cols-7 gap-6" style={{ minHeight: 460 }}>
          {/* Left */}
          <div className="lg:col-span-4 flex flex-col gap-6 h-full">
            <div className={`${CARD} flex flex-col flex-1 min-h-0 p-4`}>
              <div className="flex items-center mb-2">
                <span className="font-semibold text-white mr-1">Impact Comparison</span>
                <Tooltip label="Breakdown: origin vs. nearshore vs. net savings. Impact = annualized lane value × tariff rate." />
              </div>
              <div className="flex-1 min-h-0">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={impactCompareData}>
                    <CartesianGrid stroke="#29303d" vertical={false} />
                    <XAxis dataKey="category" tick={{ fill: '#E3FDFC', fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={formatMoney} tick={{ fill: '#7fffe1', fontSize: 12 }} axisLine={false} tickLine={false} width={76} />
                    <RechartTooltip
                      content={({ active, payload }) =>
                        active && payload?.[0]?.payload ? (
                          <div className="bg-[#212134] border border-[#53ffd3] rounded px-3 py-1 text-xs">
                            <b>{payload[0].payload.category}</b>: {formatMoney(payload[0].payload.value)}
                          </div>
                        ) : null
                      }
                    />
                    <Bar dataKey="value">
                      {impactCompareData.map((entry) => (
                        <Cell key={entry.category} fill={entry.fill} />
                      ))}
                      <LabelList dataKey="value" formatter={formatMoney} position="top" fill="#5fffe8" fontSize={12} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className={`${CARD} flex flex-col flex-1 min-h-0 p-4`}>
              <div className="flex items-center mb-2">
                <span className="font-semibold text-white mr-1">Lane Impact Map</span>
                <Tooltip label="Scatter: tariff (X), value (Y), bubble size = impact. Hover for details." />
              </div>
              <div className="flex-1 min-h-0">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 12 }}>
                    <XAxis type="number" dataKey="x" name="Tariff" unit="%" tick={{ fill: '#E3FDFC', fontSize: 11 }} axisLine={false} tickLine={false} domain={[MIN_TARIFF, MAX_TARIFF]} />
                    <YAxis type="number" dataKey="y" name="Value" tickFormatter={formatMoney} tick={{ fill: '#E3FDFC', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <ZAxis dataKey="z" />
                    <CartesianGrid stroke="#232b31" vertical={false} />
                    <RechartTooltip
                      content={({ active, payload }) =>
                        active && payload?.[0]?.payload ? (
                          <div className="bg-[#162933] border border-[#19ffd3] px-3 py-1 rounded text-xs">
                            <div>
                              <b>{payload[0].payload.id}</b>
                            </div>
                            <div>
                              Origin: <span className="font-semibold">{COUNTRIES.find((c) => c.code === payload[0].payload.originCode)?.full}</span>
                            </div>
                            <div>
                              SKU: <span className="font-semibold">{payload[0].payload.sku}</span>
                            </div>
                            <div>Tariff: {formatPct(payload[0].payload.x)}</div>
                            <div>Value: {formatMoney(payload[0].payload.y)}</div>
                            <div>Impact: {formatMoney(payload[0].payload.z)}</div>
                          </div>
                        ) : null
                      }
                    />
                    <Scatter name="Lanes" data={scatterData} fill="#5fffe8">
                      {scatterData.map((d) => (
                        <Cell key={d.id} fill={d.color} />
                      ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Right */}
          <div className="lg:col-span-3 flex flex-col gap-6 h-full">
            <div className={`${CARD} flex flex-col h-full p-4`}>
              <div className="flex items-center mb-2">
                <span className="font-semibold text-white">Risk &amp; Exposure</span>
                <Tooltip label="Tariff distribution, origin concentration, and top sources of exposure by impact." />
              </div>

              <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-3 min-h-0">
                {/* Histogram */}
                <div className="flex flex-col min-h-0">
                  <div className="flex items-center text-xs mb-1">
                    Tariff Histogram
                    <Tooltip label="Count of lanes by tariff bins. Median marker included." />
                  </div>

                  <div className="flex-1 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={tariffHist.values} margin={{ top: 6, right: 6, left: -8, bottom: 0 }} barGap={2}>
                        <CartesianGrid stroke="#23323a" vertical={false} />
                        <XAxis dataKey="range" axisLine={false} tickLine={false} tick={{ fill: '#bfffdc', fontSize: 10 }} />
                        <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: '#91a6ad', fontSize: 10 }} width={28} />
                        <RechartTooltip
                          content={({ active, payload }) =>
                            active && payload?.[0]?.payload ? (
                              <div className="bg-[#162933] border border-[#19ffd3] px-3 py-1 rounded text-xs">
                                <div>
                                  <b>Bin:</b> {payload[0].payload.range}%
                                </div>
                                <div>
                                  <b>Lanes:</b> {payload[0].payload.count}
                                </div>
                              </div>
                            ) : null
                          }
                        />
                        <Bar dataKey="count" fill="#35FFD3" radius={[6, 6, 0, 0]}>
                          <LabelList dataKey="count" position="top" fill="#6cd3e6" fontSize={10} />
                        </Bar>

                        <ReferenceLine
                          x={(Math.floor(tariffHist.median / 2.5) * 2.5).toFixed(1)}
                          stroke="#FFD580"
                          strokeWidth={2}
                          strokeDasharray="4 4"
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="mt-2 text-[11px] text-[#91a6ad]">
                    Median: <span className="text-[#FFD580] font-semibold">{tariffHist.median.toFixed(1)}%</span>
                  </div>
                </div>

                {/* Donut */}
                <div className="flex flex-col min-h-0">
                  <div className="flex items-center text-xs mb-1">
                    Origin Mix
                    <Tooltip label="Lane count share by origin (concentration risk)." />
                  </div>

                  <div className="flex-1 min-h-0 flex items-center justify-center">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={originCounts}
                          dataKey="count"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius="55%"
                          outerRadius="85%"
                          paddingAngle={originCounts.length > 1 ? 2 : 0}
                        >
                          {originCounts.map((x) => (
                            <Cell key={x.name} fill={x.color} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1">
                    {originCounts.map((o) => (
                      <div key={o.name} className="flex items-center text-[11px]">
                        <span className="inline-flex items-center justify-center w-2.5 h-2.5 mr-2">
                          <svg width={10} height={10}>
                            <circle cx={5} cy={5} r={4} fill={o.color} />
                          </svg>
                        </span>
                        <span className="truncate" style={{ color: o.color }}>
                          {o.name}
                        </span>
                        <span className="ml-auto text-[#b8ecdc]">{o.count}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Top origins by impact */}
                <div className="flex flex-col min-h-0">
                  <div className="flex items-center text-xs mb-1">
                    Top Origins by Impact
                    <Tooltip label="Where $ exposure is concentrated. Impact = value × tariff." />
                  </div>

                  <div className="flex-1 min-h-0 flex flex-col gap-2">
                    {COUNTRIES
                      .map((c) => {
                        const t = filteredLanes.filter((l) => l.originCode === c.code);
                        return { ...c, impact: t.reduce((a, v) => a + v.impact, 0), lanes: t.length };
                      })
                      .filter((x) => x.impact > 0)
                      .sort((a, b) => b.impact - a.impact)
                      .slice(0, 5)
                      .map((oc) => {
                        const maxImpact = Math.max(
                          1,
                          ...COUNTRIES.map((c) =>
                            filteredLanes.filter((l) => l.originCode === c.code).reduce((a, v) => a + v.impact, 0)
                          )
                        );
                        const pct = oc.impact / maxImpact;

                        return (
                          <div key={oc.code} className="rounded-xl border border-[#25363a] bg-[#162125] px-3 py-2">
                            <div className="flex items-center gap-2 text-xs">
                              <span className="w-2.5 h-2.5 rounded-full" style={{ background: oc.color, opacity: 0.9 }} />
                              <span className="truncate">{oc.full}</span>
                              <span className="ml-auto font-bold text-[#FFD580]">{formatMoney(oc.impact)}</span>
                            </div>

                            <div className="mt-1 flex items-center gap-2">
                              <div className="flex-1 h-2 rounded bg-[#0f1417] border border-[#1e2a2f] overflow-hidden">
                                <div
                                  className="h-full rounded"
                                  style={{
                                    width: `${Math.max(3, Math.round(pct * 100))}%`,
                                    background: `linear-gradient(90deg, ${oc.color}, #35FFD3)`,
                                    opacity: 0.9,
                                  }}
                                />
                              </div>
                              <div className="text-[11px] text-[#91a6ad] w-[52px] text-right">{(pct * 100).toFixed(0)}%</div>
                            </div>

                            <div className="mt-1 text-[11px] text-[#91a6ad]">
                              Lanes: <span className="text-[#E3FDFC] font-semibold">{oc.lanes}</span>
                            </div>
                          </div>
                        );
                      })}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Top 5 Lanes Preview */}
        <section className="mt-5 grid md:grid-cols-5 gap-5">
          {top5.map((lane, idx) => (
            <div key={lane.id} className={`${CARD} flex flex-col items-start px-4 py-3`}>
              <div className="flex items-center mb-2">
                <span className="rounded-full bg-[#1A1B20] border-2 font-mono w-7 h-7 flex items-center justify-center text-[#5fffe8] border-[#4fffd7] mr-2">
                  {idx + 1}
                </span>
                <span className="font-bold text-md truncate" title={lane.id}>
                  {lane.id}
                </span>
              </div>
              <div className="text-base text-[#F7FFF3] font-extrabold mb-1">{formatMoney(lane.impact)}</div>
              <div className="mb-2 flex text-xs">
                <span className="mr-3 text-[#aafffe]">Value: {formatMoney(lane.value)}</span>
                <span className="text-[#FFD580]">Tariff: {formatPct(lane.tariff)}</span>
              </div>
              <div className="w-full bg-[#262a2c] rounded h-2 mb-1">
                <div
                  style={{
                    width: `${(lane.impact / Math.max(...top5.map((l) => l.impact), 1)) * 100}%`,
                    background: `linear-gradient(90deg, #5FFFE8, #FFD580 98%)`,
                    borderRadius: '0.5rem',
                    height: '100%',
                  }}
                />
              </div>
              <div className="flex items-center text-xs mt-1">
                <span className="text-[#bfffdc] pr-2">Origin:</span>
                <span className="font-semibold">{COUNTRIES.find((c) => c.code === lane.originCode)?.full}</span>
              </div>
            </div>
          ))}
        </section>

        {/* Details Section */}
        <section className="mt-10 mb-16 flex flex-col gap-5">
          <div className="flex gap-4">
            <button className={`${CARD} px-6 py-2 text-[#1ae4d3] font-semibold mr-2 hover:bg-[#23353a] transition`} onClick={() => setShowTable((v) => !v)}>
              {showTable ? 'Hide details' : 'View details'}
            </button>
            <button className={`${CARD} px-6 py-2 text-[#5fffe8] font-semibold mr-2 hover:bg-[#23353a]`} onClick={() => setShowLog((v) => !v)}>
              {showLog ? 'Hide log' : 'Show live log'}
            </button>
            <button className={`${CARD} px-6 py-2 text-[#FFD580] font-semibold hover:bg-[#1f262c]`} onClick={() => setShowMatrix((v) => !v)}>
              {showMatrix ? 'Hide Decision Matrix' : 'Show Decision Matrix'}
            </button>
          </div>

          <AnimatePresence>
            {showTable && (
              <motion.div
                key="details"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 30 }}
                transition={{ duration: 0.23 }}
                className={`${CARD} p-4`}
              >
                <div className="mb-2 text-[#5fffe8] flex items-center font-bold">
                  Lanes Table
                  <Tooltip label="Full detail of filtered lanes." />
                </div>
                <div style={{ overflowX: 'auto', maxHeight: 388 }}>
                  <table className="min-w-full text-xs">
                    <thead className="sticky top-0 bg-[#14171a] z-10">
                      <tr>
                        <th className="px-3 py-2 font-semibold text-[#85FFF9]">Lane</th>
                        <th className="px-2">Origin</th>
                        <th className="px-2">SKU</th>
                        <th className="px-2 text-right">Value</th>
                        <th className="px-2 text-right">Tariff</th>
                        <th className="px-2 text-right">Impact</th>
                        <th className="px-2 text-right">Nearshore</th>
                        <th className="px-2 text-right">Near Tariff</th>
                        <th className="px-2 text-right">Near Impact</th>
                        <th className="px-2 text-right">Savings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedLanes.map((lane) => (
                        <tr key={lane.id} className="border-b border-[#282e34] hover:bg-[#1b2227] transition">
                          <td className="px-3 py-2">{lane.id}</td>
                          <td className="px-2">{COUNTRIES.find((c) => c.code === lane.originCode)?.full}</td>
                          <td className="px-2">{lane.sku}</td>
                          <td className="px-2 text-right">{formatMoney(lane.value)}</td>
                          <td className="px-2 text-right">{formatPct(lane.tariff)}</td>
                          <td className="px-2 text-right text-[#FFD580]">{formatMoney(lane.impact)}</td>
                          <td className="px-2 text-right">{COUNTRIES.find((c) => c.code === lane.nearshoreCode)?.full}</td>
                          <td className="px-2 text-right">{formatPct(lane.nearshoreTariff)}</td>
                          <td className="px-2 text-right">{formatMoney(lane.nearshoreImpact)}</td>
                          <td className="px-2 text-right">
                            <span className={lane.savings > 0 ? 'text-[#35FFD3]' : 'text-[#FFD5A5]'}>{formatMoney(lane.savings)}</span>
                          </td>
                        </tr>
                      ))}
                      {!sortedLanes.length && (
                        <tr>
                          <td className="px-3 py-3 text-[#91a6ad]" colSpan={10}>
                            No lanes match your filters.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {showLog && (
              <motion.div
                key="logdrawer"
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 30 }}
                transition={{ duration: 0.26 }}
                className={`${CARD} p-4`}
              >
                <div className="text-[#5fffe8] font-bold mb-2 flex items-center">
                  Live Log
                  <Tooltip label="Simulated latest scenario import/transform events. (Demo only)" />
                </div>
                <pre className="text-xs bg-[#111416] rounded p-3 overflow-auto h-44 text-[#AAF6E8]">
{[
  '2024-06-07 14:05:34.224  [IMPORT]  Scenario ingested. Filters applied.',
  '2024-06-07 14:05:34.344  [SIM]     Impact/savings model run on new scenario.',
  '2024-06-07 14:05:34.418  [REFRESH] Lanes list filtered: ' + formatCount(sortedLanes.length),
  '2024-06-07 14:05:34.597  [REFRESH] Metrics, charts updated.',
].join('\n')}
                </pre>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {showMatrix && (
              <motion.div
                key="matrix"
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 30 }}
                transition={{ duration: 0.21 }}
                className={`${CARD} p-4`}
              >
                <div className="text-[#FFD580] font-bold mb-2 flex items-center">
                  Decision Matrix
                  <Tooltip label="ΔUSD = (Origin landed cost + tariffs) − (Nearshore landed cost)." />
                </div>
                <table className="min-w-full text-xs">
                  <thead>
                    <tr>
                      <th className="px-2 py-2">Lane</th>
                      <th className="px-2">From</th>
                      <th className="px-2">To</th>
                      <th className="px-2 text-right">Origin Value</th>
                      <th className="px-2 text-right">Tariff</th>
                      <th className="px-2 text-right">Impact</th>
                      <th className="px-2 text-right">Near Value</th>
                      <th className="px-2 text-right">Near Tariff</th>
                      <th className="px-2 text-right">Near Impact</th>
                      <th className="px-2 text-right">ΔUSD</th>
                      <th className="px-2">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {demo.dmRows.map((row) => (
                      <tr key={row.key} className="border-b border-[#24303c]">
                        <td className="px-2 py-2">{row.lane}</td>
                        <td className="px-2">{row.from}</td>
                        <td className="px-2">{row.to}</td>
                        <td className="px-2 text-right">{formatMoney(row.originValue)}</td>
                        <td className="px-2 text-right">{formatPct(row.originTariff)}</td>
                        <td className="px-2 text-right">{formatMoney(row.originImpact)}</td>
                        <td className="px-2 text-right">{formatMoney(row.nearValue)}</td>
                        <td className="px-2 text-right">{formatPct(row.nearTariff)}</td>
                        <td className="px-2 text-right">{formatMoney(row.nearImpact)}</td>
                        <td className="px-2 text-right">{formatMoney(row.deltaUSD)}</td>
                        <td className="px-2">
                          <span
                            className={`inline-block px-2 rounded ${
                              row.confidence >= 90 ? 'bg-[#102d15] text-[#83ff54]' : row.confidence > 75 ? 'bg-[#29293e] text-[#52fff0]' : 'bg-[#3d231f] text-[#FFECDC]'
                            }`}
                          >
                            {row.confidence}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </motion.div>
            )}
          </AnimatePresence>
        </section>
      </main>

      <style jsx global>{`
        html,
        body {
          background-color: #14171a !important;
          font-family: 'Geist Mono', 'Fira Mono', 'IBM Plex Mono', ui-monospace, monospace;
        }
        ::selection {
          background: #073c34;
        }
        input:focus {
          outline: none;
        }
        .sticky {
          box-shadow: 0 2px 16px 0 rgba(30, 255, 216, 0.06);
        }
        .overflow-x-auto::-webkit-scrollbar {
          height: 0 !important;
        }
      `}</style>
    </div>
  );
}