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

export type ChartWindow = { start: number; end: number };
export const fullWindow: ChartWindow = { start: 0, end: 1 };

export function clampWindow(start: number, end: number, minSpan = 0.01): ChartWindow {
  const span = Math.max(minSpan, Math.min(1, end - start));
  const left = Math.max(0, Math.min(1 - span, start));
  return { start: left, end: left + span };
}
export function zoomWindow(view: ChartWindow, factor: number, anchor = 0.5, minSpan = 0.01): ChartWindow {
  const span = Math.max(minSpan, Math.min(1, (view.end - view.start) * factor));
  const pivot = view.start + (view.end - view.start) * anchor;
  return clampWindow(pivot - span * anchor, pivot + span * (1 - anchor), minSpan);
}
export function resizeWindow(view: ChartWindow, edge: "start" | "end", value: number, minSpan: number): ChartWindow {
  return edge === "start" ? { start: Math.max(0, Math.min(view.end - minSpan, value)), end: view.end }
    : { start: view.start, end: Math.min(1, Math.max(view.start + minSpan, value)) };
}

export function observationSegments(points: ChartPoint[], values: Array<number | null>, cumulative: boolean) {
  const segments: Array<{ from: number; to: number; missing: boolean }> = [];
  let previous = -1;
  for (let i = 0; i < points.length; i++) {
    if (values[i] == null) continue;
    if (previous >= 0 && (cumulative || points.slice(previous, i + 1).every(p => p.interval === points[previous].interval))) {
      segments.push({ from: previous, to: i, missing: i > previous + 1 });
    }
    previous = i;
  }
  return segments;
}

export function dateLayout(days: string[], availableWidth: number, view: ChartWindow = fullWindow) {
  const sorted = [...new Set(days)].sort();
  const times = sorted.map(d => Date.parse(`${d}T00:00:00Z`));
  const first = times[0] || 0, last = times[times.length - 1] || first;
  const minSpan = Math.min(1, 86400000 / (last - first || 86400000));
  const range = clampWindow(view.start, view.end, minSpan);
  const startTime = first + (last - first) * range.start, endTime = first + (last - first) * range.end;
  const width = Math.max(220, Math.floor(availableWidth));
  const x = (day: string) => first === last ? (width + 44) / 2 : 110 + (Date.parse(`${day}T00:00:00Z`) - startTime) / (endTime - startTime) * (width - 164);
  const visible = sorted.filter((_, i) => times[i] >= startTime - 1 && times[i] <= endTime + 1);
  const ticks: Array<{ day: string; label: string; row: number }> = [];
  const edges = [-Infinity, -Infinity];
  const lastDay = visible[visible.length - 1];
  // Two rows retain useful date detail without widening the actual chart.
  for (const day of visible) {
    const label = axisDay(day, ticks[ticks.length - 1]?.day), half = label.length * 3.5 + 6;
    const endSpace = day === lastDay ? Infinity : x(lastDay) - lastDay.length * 3.5 - 6;
    const row = [0, 1].find(row => x(day) - half >= edges[row] && (row === 1 || x(day) + half < endSpace));
    if (row == null) continue;
    ticks.push({ day, label, row }); edges[row] = x(day) + half;
  }
  return { width, x, days: sorted, ticks, startTime, endTime, minSpan, range };
}
