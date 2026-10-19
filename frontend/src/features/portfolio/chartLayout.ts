import type { ChartPoint } from "./types";

export const profitMetrics = [
  { value: "total_return", label: "累计收益率" },
  { value: "total_profit", label: "累计盈亏" },
  { value: "return", label: "统计期收益率" },
  { value: "profit", label: "统计期盈亏" },
] as const;
export type ProfitMetric = typeof profitMetrics[number]["value"];
export const isTotalMetric = (metric: ProfitMetric) => metric === "total_return" || metric === "total_profit";
export const isRateMetric = (metric: ProfitMetric) => metric === "total_return" || metric === "return";

const dayFormatter = new Intl.DateTimeFormat("en", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" });
export function calendarDay(at: string): string {
  const parts = dayFormatter.formatToParts(new Date(at));
  const part = (type: string) => parts.find(p => p.type === type)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}
export const pointDay = (p: ChartPoint) => p.valuation_date || calendarDay(p.observed_at);
export const axisDay = (day: string, previous?: string) => !previous || day.slice(0, 4) !== previous.slice(0, 4) ? day : day.slice(5);

export function chartValue(p: ChartPoint, metric: ProfitMetric, assetCode = ""): number | null {
  const raw = assetCode ? p.asset_returns[assetCode] : metric === "total_return" ? p.cumulative_profit_rate
    : metric === "total_profit" ? p.cumulative_profit : metric === "return" ? p.cumulative_return : p.profit;
  if (raw == null) return null;
  const value = Number(raw) * (assetCode || isRateMetric(metric) ? 100 : 1);
  return Number.isFinite(value) ? value : null;
}

export function dailyObservations(records: ChartPoint[]) {
  const groups = new Map<string, ChartPoint[]>();
  // Stable sorting retains replay order for simultaneous records.
  for (const p of [...records].sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at))) {
    const day = pointDay(p);
    const group = groups.get(day) || [];
    group.push(p); groups.set(day, group);
  }
  return [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([day, records]) => {
    const valued = records.filter(p => p.total_assets != null);
    return { day, records, point: valued[valued.length - 1] || records[records.length - 1] };
  });
}

export function chartTicks(values: Array<number | null>, rate: boolean) {
  const valid = values.filter((v): v is number => v != null && Number.isFinite(v));
  const low = Math.min(0, ...valid), high = Math.max(0, ...valid);
  const rough = (high - low || (rate ? 1 : 100)) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const factor = [1, 2, 2.5, 5, 10].find(n => n * magnitude >= rough)!;
  const step = factor * magnitude;
  const min = Math.floor(low / step) * step, max = Math.ceil(high / step) * step || (low === 0 ? step * 4 : 0);
  const ticks = Array.from({ length: Math.round((max - min) / step) + 1 }, (_, i) => Number((min + i * step).toPrecision(12)));
  const digits = Math.min(10, Math.max(0, -Math.floor(Math.log10(step))) + (factor === 2.5 ? 1 : 0));
  const label = (v: number) => `${v.toLocaleString("zh-CN", { maximumFractionDigits: digits })}${rate ? "%" : ""}`;
  return { min, max, ticks, label };
}

export function dateLayout(days: string[], availableWidth: number) {
  const sorted = [...new Set(days)].sort();
  const times = sorted.map(d => Date.parse(`${d}T00:00:00Z`));
  const first = times[0] || 0, last = times[times.length - 1] || first;
  const gaps = times.slice(1).map((t, i) => t - times[i]);
  const required = gaps.length ? (last - first) / Math.min(...gaps) * 40 : 0;
  const width = Math.ceil(Math.max(availableWidth, 420, required + 164));
  const x = (day: string) => first === last ? (width + 44) / 2 : 110 + (Date.parse(`${day}T00:00:00Z`) - first) / (last - first) * (width - 164);
  return { width, x, days: sorted };
}
