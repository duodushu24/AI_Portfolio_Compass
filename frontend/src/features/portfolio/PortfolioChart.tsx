import { useEffect, useRef, useState } from "react";
import { Drawer, Empty, Table } from "@arco-design/web-react";
import type { ChartPoint } from "./types";
import { axisDay, calendarDay, chartTicks, chartValue, dailyObservations, dateLayout, isRateMetric, isTotalMetric, pointDay } from "./chartLayout";
import type { ProfitMetric } from "./chartLayout";

export function PortfolioChart({ points: records, metric, onSelect, assetCode = "", eventLabels, maskAssets = false }: {
  points: ChartPoint[]; metric: ProfitMetric; onSelect: (p: ChartPoint) => void; assetCode?: string;
  eventLabels: Record<string, string>; maskAssets?: boolean;
}) {
  const [recordGroup, setRecordGroup] = useState<ChartPoint[]>([]);
  const [availableWidth, setAvailableWidth] = useState(900);
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
  const layout = dateLayout(axisDays, availableWidth);
  const rate = Boolean(assetCode) || isRateMetric(metric);
  const values = daily.map(d => chartValue(d.point, metric, assetCode));
  const ticks = chartTicks(values, rate);
  const y = (v: number) => 238 - (v - ticks.min) / (ticks.max - ticks.min) * 210;
  const valueLabel = (p: ChartPoint) => {
    const v = chartValue(p, metric, assetCode);
    return v == null ? "无法计算" : !rate && maskAssets ? "••••" : `${v.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${rate ? "%" : " CNY"}`;
  };
  let path = "", connected = false, interval = 0;
  daily.forEach(({ day, point }, i) => {
    const v = values[i];
    if (v == null || (!(isTotalMetric(metric) && !assetCode) && interval !== point.interval)) connected = false;
    if (v != null) { path += `${connected ? "L" : "M"}${layout.x(day)},${y(v)} `; connected = true; }
    interval = point.interval;
  });
  const openGroup = (group: ChartPoint[]) => group.length === 1 ? onSelect(group[0]) : setRecordGroup(group);
  const onlyTrades = recordGroup.every(p => p.event_type === "trade");
  if (!daily.length) return <Empty description="确认期初后，买卖、资金和市值更新会自动形成收益记录。" />;
  return <div className="portfolio-chart">
    <div className="portfolio-chart-viewport" ref={viewport}>
      <svg width={layout.width} height="340" viewBox={`0 0 ${layout.width} 340`} role="img" aria-label={assetCode ? "标的持仓收益率曲线" : "整体组合收益曲线"}>
        {ticks.ticks.map(v => <g key={v} className={v === 0 ? "portfolio-zero-tick" : undefined}>
          <line x1="110" x2={layout.width - 54} y1={y(v)} y2={y(v)} stroke={v === 0 ? "#86909c" : "#d9dfe7"} strokeWidth={v === 0 ? 1.5 : 1} />
          <text x="98" y={y(v) + 4} textAnchor="end">{!rate && maskAssets ? "••••" : ticks.label(v)}</text>
        </g>)}
        <path className="portfolio-return-path" d={path} fill="none" stroke="#165dff" strokeWidth="2.5" />
        {!!tradeDays.length && <><line x1="110" x2={layout.width - 54} y1="263" y2="263" stroke="#e5e6eb" /><text x="98" y="267" textAnchor="end">交易</text>
          {tradeDays.map(day => {
            const group = trades.get(day)!;
            const title = `${day} · ${group.length} 笔交易`;
            return <g key={day} className="portfolio-trade-marker" role="button" tabIndex={0} aria-label={`查看交易 ${title}`} onClick={() => openGroup(group)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openGroup(group); } }}>
              <title>{title}；点击查看成交及数量、成本变化，不代表该时点的组合收益。</title><circle cx={layout.x(day)} cy="263" r="8" fill="#ff7d00" />
              {group.length > 1 && <text x={layout.x(day)} y="267" textAnchor="middle" style={{ fill: "white", fontSize: 10 }}>{group.length}</text>}
            </g>;
          })}</>}
        {daily.map(({ day, records: group }, i) => <circle className="portfolio-observation-point" key={day} cx={layout.x(day)} cy={values[i] == null ? 246 : y(values[i]!)} r="5" fill={values[i] == null ? "#86909c" : "#165dff"} tabIndex={0} role="button"
          aria-label={`查看收益记录 ${day} · ${valueLabel(daily[i].point)}`} onClick={() => openGroup(group)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openGroup(group); } }}>
          <title>{day} · {valueLabel(daily[i].point)}{group.length > 1 ? ` · 当天 ${group.length} 条记录，显示最后一次有效估值` : ""}</title>
        </circle>)}
        {layout.days.map((day, i) => <g key={day} className="portfolio-date-tick">
          <line x1={layout.x(day)} x2={layout.x(day)} y1="278" y2={i % 2 ? 308 : 290} stroke="#d9dfe7" />
          <text x={layout.x(day)} y={i % 2 ? 323 : 305} textAnchor="middle" className="portfolio-date-label">{axisDay(day, layout.days[i - 1])}</text>
        </g>)}
      </svg>
    </div>
    {values.every(v => v == null) && <p className="metadata-note">当前选项暂无可计算的收益点；可切换盈亏金额或查看资料缺失提示。</p>}
    <small>每天显示最后一次有效估值，点击节点可查看当天全部记录。{closingObservations ? "橙色标记为真实交易，同日多笔合并显示数量；缺少估值的交易日不生成收益点。" : "只展示已保存的观察日期，不补画每日行情。"}{isTotalMetric(metric) && !assetCode ? "累计口径包含历史结转，从已有记录开始展示。" : "统计期在基准重置、连续区间切换或资料缺失处断开。"}日期较密时可横向滚动。</small>
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
