import { useEffect, useId, useRef, useState } from "react";
import { Drawer, Empty, Table } from "@arco-design/web-react";
import type { ChartPoint } from "./types";
import { calendarDay, chartTicks, chartValue, clampWindow, dailyObservations, dateLayout, fullWindow, isRateMetric, isTotalMetric, observationSegments, pointDay, resizeWindow, zoomWindow } from "./chartLayout";
import type { ChartWindow, ProfitMetric } from "./chartLayout";

export function PortfolioChart({ points: records, metric, onSelect, assetCode = "", eventLabels, maskAssets = false }: {
  points: ChartPoint[]; metric: ProfitMetric; onSelect: (p: ChartPoint) => void; assetCode?: string;
  eventLabels: Record<string, string>; maskAssets?: boolean;
}) {
  const [recordGroup, setRecordGroup] = useState<ChartPoint[]>([]);
  const [availableWidth, setAvailableWidth] = useState(900);
  const [view, setView] = useState<ChartWindow>(fullWindow);
  const [hover, setHover] = useState<number | null>(null), [panning, setPanning] = useState(false);
  const drag = useRef<{ x: number; view: ChartWindow } | null>(null);
  const clipId = useId().replace(/:/g, "");
  const viewport = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = viewport.current;
    if (!node) return;
    const measure = () => setAvailableWidth(node.clientWidth || 900);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [records]);
  useEffect(() => { setRecordGroup([]); }, [records]);

  const closingObservations = !assetCode && Boolean(records[0]?.valuation_date);
  const observations = closingObservations ? records.filter(p => p.event_type === "valuation") : records;
  const daily = dailyObservations(observations);
  const trades = new Map<string, ChartPoint[]>();
  if (closingObservations) for (const p of records.filter(p => p.event_type === "trade")) {
    const day = calendarDay(p.observed_at);
    trades.set(day, [...(trades.get(day) || []), p]);
  }
  const tradeDays = [...trades.keys()].sort();
  const axisDays = [...daily.map(d => d.day), ...(tradeDays.length ? [tradeDays[0], tradeDays[tradeDays.length - 1]] : [])];
  const overview = dateLayout(axisDays, availableWidth);
  const layout = dateLayout(axisDays, availableWidth, view);
  const plotWidth = layout.width - 164;
  const span = layout.range.end - layout.range.start;
  const rate = Boolean(assetCode) || isRateMetric(metric);
  const values = daily.map(d => chartValue(d.point, metric, assetCode));
  const hovered = hover != null && daily[hover] ? hover : null;
  const visible = daily.map((d, i) => i).filter(i => layout.x(daily[i].day) >= 110 - 0.01 && layout.x(daily[i].day) <= layout.width - 54 + 0.01);
  const preceding = daily.map((d, i) => i).filter(i => values[i] != null && layout.x(daily[i].day) < 110);
  const following = daily.findIndex((d, i) => values[i] != null && layout.x(d.day) > layout.width - 54);
  const rangeValues = [...visible, ...(preceding.length ? [preceding[preceding.length - 1]] : []), ...(following >= 0 ? [following] : [])].map(i => values[i]);
  const ticks = chartTicks(rangeValues, rate), overviewTicks = chartTicks(values, rate);
  const y = (v: number) => 238 - (v - ticks.min) / (ticks.max - ticks.min) * 210;
  const overviewY = (v: number) => 37 - (v - overviewTicks.min) / (overviewTicks.max - overviewTicks.min) * 32;
  const segments = observationSegments(daily.map(d => d.point), values, isTotalMetric(metric) && !assetCode);
  const segmentPath = (from: number, to: number) => `M${layout.x(daily[from].day)},${y(values[from]!)} L${layout.x(daily[to].day)},${y(values[to]!)}`;
  const path = segments.filter(s => !s.missing).map(s => segmentPath(s.from, s.to)).join(" ");
  const hasGaps = values.some(v => v == null);
  const rangeDay = (time: number) => new Date(time).toISOString().slice(0, 10);
  useEffect(() => { setView(fullWindow); setHover(null); }, [overview.days[0], overview.days[overview.days.length - 1]]);
  useEffect(() => { setHover(null); }, [metric, records, view]);
  useEffect(() => {
    const node = viewport.current;
    if (!node) return;
    const wheel = (event: WheelEvent) => {
      const box = node.getBoundingClientRect(), cursor = event.clientX - box.left;
      if (cursor < 110 || cursor > layout.width - 54 || event.clientY - box.top > 250 || overview.minSpan === 1) return;
      event.preventDefault();
      if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
        setView(prev => clampWindow(prev.start + event.deltaX / plotWidth * (prev.end - prev.start), prev.end + event.deltaX / plotWidth * (prev.end - prev.start), overview.minSpan));
      } else {
        const anchor = Math.max(0, Math.min(1, (cursor - 110) / plotWidth));
        setView(prev => zoomWindow(prev, Math.exp(Math.max(-120, Math.min(120, event.deltaY)) * 0.006), anchor, overview.minSpan));
      }
    };
    node.addEventListener("wheel", wheel, { passive: false });
    return () => node.removeEventListener("wheel", wheel);
  }, [records, layout.width, plotWidth, overview.minSpan]);
  const valueLabel = (p: ChartPoint) => {
    const v = chartValue(p, metric, assetCode);
    return v == null ? "无法计算" : !rate && maskAssets ? "••••" : `${v.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${rate ? "%" : " CNY"}`;
  };
  const openGroup = (group: ChartPoint[]) => group.length === 1 ? onSelect(group[0]) : setRecordGroup(group);
  const onlyTrades = recordGroup.every(p => p.event_type === "trade");
  if (!daily.length) return <Empty description="确认期初后，买卖、资金和市值更新会自动形成收益记录。" />;
  return <div className="portfolio-chart">
    <div className="portfolio-chart-controls"><span>{rangeDay(layout.startTime)} ～ {rangeDay(layout.endTime)}</span><div>
      <button type="button" aria-label="放大收益曲线" disabled={span <= overview.minSpan + 0.000001} onClick={() => setView(prev => zoomWindow(prev, 0.65, 0.5, overview.minSpan))}>放大</button>
      <button type="button" aria-label="缩小收益曲线" disabled={span >= 0.999999} onClick={() => setView(prev => zoomWindow(prev, 1.6, 0.5, overview.minSpan))}>缩小</button>
      <button type="button" aria-label="显示全部日期" onClick={() => setView(fullWindow)}>全部</button>
    </div></div>
    {hasGaps && <p className="portfolio-chart-gap-note">灰点：当前指标无法计算。虚线：仅连接前后已知值，中间日期无收益数值；统计期切换仍断开。</p>}
    <div className="portfolio-chart-viewport" ref={viewport}>
      <svg width={layout.width} height="340" viewBox={`0 0 ${layout.width} 340`} role="img" aria-label={assetCode ? "标的持仓收益率曲线" : "整体组合收益曲线"} className={panning ? "portfolio-chart-panning" : undefined}
        onPointerDown={event => {
          if (event.button !== 0 || span >= 0.999999 || (event.target as Element).closest('[role="button"]')) return;
          drag.current = { x: event.clientX, view: layout.range }; setPanning(true); setHover(null);
          event.currentTarget.setPointerCapture(event.pointerId);
        }} onPointerMove={event => {
          if (drag.current) {
            const delta = (drag.current.x - event.clientX) / plotWidth * (drag.current.view.end - drag.current.view.start);
            setView(clampWindow(drag.current.view.start + delta, drag.current.view.end + delta, overview.minSpan)); return;
          }
          const box = event.currentTarget.getBoundingClientRect(), cursor = event.clientX - box.left;
          if (!visible.length || cursor < 110 || cursor > layout.width - 54 || event.clientY - box.top > 250) { setHover(null); return; }
          setHover(visible.reduce((a, b) => Math.abs(layout.x(daily[a].day) - cursor) <= Math.abs(layout.x(daily[b].day) - cursor) ? a : b));
        }} onPointerUp={event => { drag.current = null; setPanning(false); if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        onPointerCancel={() => { drag.current = null; setPanning(false); }} onPointerLeave={() => { if (!drag.current) setHover(null); }}>
        <defs><clipPath id={clipId}><rect x="104" y="20" width={plotWidth + 12} height="255" /></clipPath></defs>
        {ticks.ticks.map(v => <g key={v} className={v === 0 ? "portfolio-zero-tick" : undefined}>
          <line x1="110" x2={layout.width - 54} y1={y(v)} y2={y(v)} stroke={v === 0 ? "#86909c" : "#d9dfe7"} strokeWidth={v === 0 ? 1.5 : 1} />
          <text x="98" y={y(v) + 4} textAnchor="end">{!rate && maskAssets ? "••••" : ticks.label(v)}</text>
        </g>)}
        <g clipPath={`url(#${clipId})`}>
        <path className="portfolio-return-path" d={path} fill="none" stroke="#165dff" strokeWidth="2.5" />
        {segments.filter(s => s.missing).map(s => <path key={s.to} className="portfolio-gap-bridge" d={segmentPath(s.from, s.to)} fill="none" stroke="#86909c" strokeWidth="1.5" strokeDasharray="5 5"><title>{daily[s.from].day} ～ {daily[s.to].day}：中间记录的当前指标无法计算；虚线只连接两次已知观察值。</title></path>)}
        {!!tradeDays.length && <><line x1="110" x2={layout.width - 54} y1="263" y2="263" stroke="#e5e6eb" /><text x="98" y="267" textAnchor="end">交易</text>
          {tradeDays.filter(day => layout.x(day) >= 110 && layout.x(day) <= layout.width - 54).map(day => {
            const group = trades.get(day)!;
            const title = `${day} · ${group.length} 笔交易`;
            return <g key={day} className="portfolio-trade-marker" role="button" tabIndex={0} aria-label={`查看交易 ${title}`} onClick={() => openGroup(group)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openGroup(group); } }}>
              <title>{title}；点击查看成交及数量、成本变化，不代表该时点的组合收益。</title><circle cx={layout.x(day)} cy="263" r="8" fill="#ff7d00" />
              {group.length > 1 && <text x={layout.x(day)} y="267" textAnchor="middle" style={{ fill: "white", fontSize: 10 }}>{group.length}</text>}
            </g>;
          })}</>}
        {visible.map(i => { const { day, records: group } = daily[i]; return <circle className="portfolio-observation-point" key={day} cx={layout.x(day)} cy={values[i] == null ? 246 : y(values[i]!)} r={hover === i ? 6 : 5} fill={values[i] == null ? "#86909c" : "#165dff"} tabIndex={0} role="button" onFocus={() => setHover(i)} onBlur={() => setHover(null)}
          aria-label={`查看收益记录 ${day} · ${valueLabel(daily[i].point)}`} onClick={() => openGroup(group)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openGroup(group); } }}>
          <title>{day} · {valueLabel(daily[i].point)}{group.length > 1 ? ` · 当天 ${group.length} 条记录，显示最后一次有效估值` : ""}</title>
        </circle>; })}
        {hovered != null && <line className="portfolio-crosshair" x1={layout.x(daily[hovered].day)} x2={layout.x(daily[hovered].day)} y1="22" y2="250" stroke="#86909c" strokeDasharray="3 3" pointerEvents="none" />}
        </g>
        {layout.ticks.map(({ day, label, row }) => <g key={day} className="portfolio-date-tick">
          <line x1={layout.x(day)} x2={layout.x(day)} y1="278" y2={row ? 308 : 290} stroke="#d9dfe7" />
          <text x={layout.x(day)} y={row ? 323 : 305} textAnchor="middle" className="portfolio-date-label">{label}</text>
        </g>)}
      </svg>
      {hovered != null && <div className="portfolio-chart-tooltip" role="status" style={{ left: Math.max(4, Math.min(layout.width - 230, layout.x(daily[hovered].day) - 110)) }}>{daily[hovered].day} · {valueLabel(daily[hovered].point)}{values[hovered] == null && <span>灰点是缺失标记，不是零收益；点击查看记录。</span>}</div>}
    </div>
    <div className="portfolio-chart-navigator" aria-label="收益曲线查看范围">
      <svg width={plotWidth} height="42" viewBox={`0 0 ${plotWidth} 42`} aria-hidden="true">
        <rect x={layout.range.start * plotWidth} y="1" width={span * plotWidth} height="40" fill="rgba(22,93,255,0.1)" stroke="#165dff" />
        {segments.map(s => <path key={s.to} d={`M${overview.x(daily[s.from].day) - 110},${overviewY(values[s.from]!)} L${overview.x(daily[s.to].day) - 110},${overviewY(values[s.to]!)}`} fill="none" stroke={s.missing ? "#86909c" : "#165dff"} strokeDasharray={s.missing ? "3 3" : undefined} />)}
      </svg>
      <input type="range" min="0" max="1" step="0.001" aria-label="图表起点" value={layout.range.start} onChange={e => setView(resizeWindow(layout.range, "start", Number(e.target.value), overview.minSpan))} />
      <input type="range" min="0" max="1" step="0.001" aria-label="图表终点" value={layout.range.end} onChange={e => setView(resizeWindow(layout.range, "end", Number(e.target.value), overview.minSpan))} />
    </div>
    {values.every(v => v == null) && <p className="metadata-note">当前选项暂无可计算的收益点；可切换盈亏金额或查看资料缺失提示。</p>}
    <small>滚轮或按钮缩放，放大后拖动曲线平移；底部两端可调整查看范围。日期标签随缩放调整，悬停每个点可查看完整日期。缩放只改变查看范围，不改变上方收益统计。每天显示最后一次有效估值，点击可查看当天全部记录。{closingObservations ? "橙色为真实交易，灰点只标记无法计算的记录。" : "只展示已保存的观察日期。"}</small>
    {!!recordGroup.length && <Drawer visible title={`${pointDay(recordGroup[0])} · ${recordGroup.length} ${onlyTrades ? "笔交易" : "条收益记录"}`} width={850} footer={null} onCancel={() => setRecordGroup([])}>
      <Table rowKey={p => `${p.observed_at}:${p.account_id}:${p.event_type}:${p.record_id}`} data={recordGroup} pagination={false} columns={[
        { title: "日期", render: (_, p: ChartPoint) => pointDay(p) },
        { title: "事项", render: (_, p: ChartPoint, i: number) => onlyTrades ? p.transaction?.name || p.transaction?.code || "已记录交易" : `第 ${i + 1} 次 · ${eventLabels[p.event_type]}` },
        onlyTrades ? { title: "方向", render: (_, p: ChartPoint) => p.transaction?.side === "BUY" ? "买入" : "卖出" } : { title: "收益", render: (_, p: ChartPoint) => valueLabel(p) },
        { title: "查看", render: (_, p: ChartPoint) => <button className="portfolio-name-button" onClick={() => { setRecordGroup([]); onSelect(p); }}>查看详情</button> },
      ]} />
    </Drawer>}
  </div>;
}
