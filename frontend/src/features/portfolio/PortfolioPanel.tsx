import { useEffect, useRef, useState } from "react";
import { Alert, Button, Drawer, Empty, Select, Table, Tag } from "@arco-design/web-react";
import { portfolioApi } from "./api";
import type { Asset, Point, Portfolio } from "./types";
import "./portfolio.css";

export const numeric = (v: string | number | null | undefined) => v == null ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
export const percent = (v: string | null | undefined) => v == null ? "—" : `${(Number(v) * 100).toFixed(2)}%`;
export const timeLabel = (v: string) => new Date(v).toLocaleString("zh-CN", { hour12: false });
export const accountLabel = (id: string, names: Record<string, string> = {}) => names[id] || "未命名账户";
export const labels: Record<string, string> = { opening: "建档", include: "纳入组合", exclude: "移出组合", trade: "买卖", valuation: "更新市值", deposit: "入金", withdrawal: "出金", transfer: "账户转账", dividend: "分红", interest: "利息", fee: "费用", fx: "换汇", subscription: "待确认申购", settle: "赎回到账", cancel_subscription: "申购撤回", split: "拆分", position_transfer: "转托管" };

function Chart({ points, metric, onSelect, assetCode = "" }: { points: Point[]; metric: string; onSelect: (p: Point) => void; assetCode?: string }) {
  if (!points.length) return <Empty description="确认期初后，买卖、资金和市值更新会自动形成收益记录。" />;
  const value = (p: Point) => {
    if (assetCode) {
      const result = p.asset_returns[assetCode];
      return result == null ? null : Number(result) * 100;
    }
    const v = metric === "return" ? p.cumulative_return : p.profit;
    return v == null ? null : Number(v) * (metric === "return" ? 100 : 1);
  };
  const times = points.map(p => new Date(p.observed_at).getTime()), values = points.map(value);
  const first = Math.min(...times), last = Math.max(...times), valid = values.filter((v): v is number => v != null);
  const low = Math.min(0, ...valid), high = Math.max(0, ...valid), pad = Math.max((high - low) * .12, 1);
  const x = (t: number) => first === last ? 460 : 75 + (t - first) / (last - first) * 795;
  const y = (v: number) => 235 - (v - low + pad) / (high - low + 2 * pad) * 210;
  let path = "", connected = false, interval = 0;
  points.forEach((p, i) => { const v = values[i]; if (v == null || interval !== p.interval) connected = false; if (v != null) { path += `${connected ? "L" : "M"}${x(times[i])},${y(v)} `; connected = true; } interval = p.interval; });
  return <div className="portfolio-chart"><svg viewBox="0 0 900 290" role="img" aria-label={assetCode ? "标的持仓收益率曲线" : "账户收益曲线"}>
    {[0, 1, 2, 3, 4].map(i => { const v = low - pad + (high - low + 2 * pad) * i / 4; return <g key={i}><line x1="75" x2="870" y1={y(v)} y2={y(v)} stroke="#d9dfe7" /><text x="65" y={y(v) + 4} textAnchor="end">{v.toFixed(1)}{assetCode || metric === "return" ? "%" : ""}</text></g>; })}
    <path d={path} fill="none" stroke="#165dff" strokeWidth="2.5" />
    {points.map((p, i) => <circle key={i} cx={x(times[i])} cy={values[i] == null ? 250 : y(values[i]!)} r="5" fill={p.event_type === "trade" ? "#ff7d00" : values[i] == null ? "#86909c" : "#165dff"} tabIndex={0} role="button" aria-label={`查看收益记录 ${timeLabel(p.observed_at)} ${labels[p.event_type]}`} onClick={() => onSelect(p)} onKeyDown={e => { if (e.key === "Enter") onSelect(p); }}><title>{timeLabel(p.observed_at)} · {labels[p.event_type]} · {values[i] == null ? "资料未齐/无持仓" : values[i]?.toFixed(2)}</title></circle>)}
    <text x="75" y="280">{timeLabel(points[0].observed_at)}</text><text x="870" y="280" textAnchor="end">{timeLabel(points[points.length - 1].observed_at)}</text>
  </svg><small>橙色为实际买卖点，可点击查看数量、成本和利润变化。仅连接已保存时点；不同连续区间和缺失资料处断开。</small></div>;
}

export function AssetTable({ assets, onOpen, maskAssets = false, accountNames = {} }: { assets: Asset[]; onOpen?: (code: string) => void; maskAssets?: boolean; accountNames?: Record<string, string> }) {
  const money = (v: string | null) => maskAssets ? "••••" : numeric(v);
  return <Table tableLayoutFixed rowKey={a => `${a.account_id}:${a.code}:${a.currency}:${a.unit}`} data={assets} pagination={{ pageSize: 8 }} scroll={{ x: 1380 }} columns={[
    { title: "账户 / 标的", width: 220, render: (_, a: Asset) => <div className="portfolio-asset-cell"><small>{accountLabel(a.account_id, accountNames)}</small>{onOpen ? <Button className="portfolio-asset-link" type="text" onClick={() => onOpen(a.code)}>{a.name || a.code}</Button> : <strong>{a.name || a.code}</strong>}{a.name && a.name !== a.code && <small>{a.code}</small>}</div> },
    { title: "状态 / 数量", width: 160, render: (_, a: Asset) => Number(a.quantity) ? <div className="portfolio-asset-cell"><span>{money(a.quantity)}</span><small>第 {a.cycle} 次持有</small></div> : "已清仓" },
    { title: "平均成本 / 现价", width: 210, render: (_, a: Asset) => `${money(a.average_cost)} / ${money(a.price)} ${a.currency}` },
    { title: "持仓收益率", width: 130, render: (_, a: Asset) => percent(a.holding_return) },
    { title: "浮动 / 已实现盈亏", width: 220, render: (_, a: Asset) => `${money(a.floating)} / ${money(a.realized)} ${a.currency}` },
    { title: "市值 CNY", width: 150, render: (_, a: Asset) => money(a.market_value_cny) },
    { title: "报价依据", width: 290, render: (_, a: Asset) => a.quote ? `${timeLabel(a.quote.at)} · ${a.quote.price_kind === "nav" ? "正式净值" : a.quote.price_kind === "estimate" ? "估算" : "价格"} · ${a.quote.source}` : "缺价" },
  ]} />;
}

export function PortfolioPanel({ accountId = "all", code = "", maskAssets = false, revision = 0, onOpen, showPositions = true }: { accountId?: string; code?: string; maskAssets?: boolean; revision?: number; onOpen?: (code: string) => void; showPositions?: boolean }) {
  const [data, setData] = useState<Portfolio | null>(null), [error, setError] = useState("");
  const [metric, setMetric] = useState("return"), [selected, setSelected] = useState<Point | null>(null), [closed, setClosed] = useState(false);
  const request = useRef(0);
  useEffect(() => { const id = ++request.current; setData(null); setSelected(null); portfolioApi.overview(accountId, code).then(result => { if (id === request.current) { setData(result); setError(""); } }).catch(e => { if (id === request.current) setError(String(e.message)); }); return () => { request.current++; }; }, [accountId, code, revision]);
  const current = data?.current, money = (v: string | null | undefined) => maskAssets ? "••••" : numeric(v);
  const accountName = (id: string) => accountLabel(id, data?.account_names);
  const beginning = data?.points.find(p => p.interval === current?.interval && p.opening_assets != null);
  return <section className="panel portfolio-panel stack">
    <div className="portfolio-toolbar"><div><h3>{code ? "标的收益与成交历史" : "账户收益"}</h3><small>{code ? "平均成本口径；清仓利润保留，重新买入开启新持有阶段" : "自建档净值收益 · 包含现金、资金进出与汇率 · CNY"}</small></div>{!code && <Select value={metric} onChange={setMetric} options={[{ value: "return", label: "累计账户收益率" }, { value: "profit", label: "自建档盈亏金额" }]} />}</div>
    {error && <Alert type="error" content={error} />}
    {!code && current && <div className="portfolio-metrics"><div>账户总资产<strong>{money(current.total_assets)} CNY</strong></div><div>累计账户收益率<strong>{percent(current.cumulative_return)}</strong></div><div>自建档盈亏<strong>{money(current.profit)} CNY</strong></div><div>现金<strong>{money(current.cash_value)} CNY</strong></div></div>}
    {!code && current && <div className="portfolio-profit-basis"><p>账户盈亏从期初市值和现金开始统计；持仓的浮动／已实现盈亏按平均成本计算，可能包含期初已有浮盈或浮亏。</p><details><summary>查看账户盈亏计算依据</summary><p>收益起点：{beginning ? timeLabel(beginning.observed_at) : "期初估值待补齐"} · 期初总资产 {money(current.opening_assets)} CNY · 当前总资产 {money(current.total_assets)} CNY · 净外部入金 {money(current.net_flows)} CNY</p><p>账户盈亏＝当前总资产－期初总资产－期间净外部入金。买卖产生的现金已计入总资产，不另加一遍卖出利润。</p></details></div>}
    {current && (current.issues.length > 0 || current.performance_issues.length > 0) && <Alert type="warning" content={<details><summary>{current.quality === "missing" ? "资料缺失，完整资产及收益不可用" : "部分报价沿用旧值或使用估算；查看依据"}</summary>{[...current.issues, ...current.performance_issues].map(i => <p key={i}>{i}</p>)}</details>} />}
    {current?.ended && <Alert type="info" content="本连续区间已结束，保留最后有效收益；重新入金会开始新连续区间。" />}
    <Chart points={data?.points ?? []} metric={metric} assetCode={code} onSelect={setSelected} />
    {!current && <p>到账户与数据确认期初资料。未建档账户的旧快照保留为来源，不参与这条净值曲线。</p>}
    {current && <><div className="portfolio-toolbar"><h4>{code ? "成本盈亏" : showPositions ? "持仓与已清仓标的" : "已清仓历史"}</h4>{!code && <Button onClick={() => setClosed(!closed)}>{closed ? "收起已清仓" : "包含已清仓"}</Button>}</div>{(showPositions || code || closed) && <AssetTable assets={current.positions.filter(a => code || (showPositions ? closed || Number(a.quantity) > 0 : !Number(a.quantity)))} onOpen={onOpen} maskAssets={maskAssets} accountNames={data?.account_names} />}</>}
    {code && <Table rowKey={r => `${r.category}:${r.id}`} data={data?.records ?? []} pagination={{ pageSize: 8 }} columns={[{ title: "时间", dataIndex: "effective_at", render: timeLabel }, { title: "事项", render: (_, r) => `${accountName(r.account_id)} · ${labels[r.kind]}${r.is_void ? "（已作废）" : ""}` }, { title: "数量 / 价格 / 费用", render: (_, r) => maskAssets ? "••••" : `${r.data.side === "BUY" ? "买入" : r.data.side === "SELL" ? "卖出" : ""} ${r.data.quantity ?? ""} / ${r.data.price ?? ""} / ${r.data.fees ?? ""}` }]} />}
    {!code && <p className="metadata-note">未知历史人民币成本不以当前汇率补算。报价沿用情况与资金边界估算可查看每个点。</p>}
    {selected && <Drawer title={`${labels[selected.event_type]} · ${timeLabel(selected.observed_at)}`} visible width={1000} footer={null} onCancel={() => setSelected(null)}><div className="stack">
      <p>总资产 {money(selected.total_assets)} CNY · 净值 {numeric(selected.nav)} · 份额 {money(selected.units)} · 收益率 {percent(selected.cumulative_return)} · 自建档盈亏 {money(selected.profit)} CNY</p>
      <Tag color={selected.quality === "complete" ? "green" : "orange"}>{selected.quality === "complete" ? "当时报价完整" : "估算 / 资料缺失"}</Tag>
      {selected.changes && <p>数量 {money(selected.changes.before_quantity)} → {money(selected.changes.after_quantity)}；剩余成本 {money(selected.changes.before_cost)} → {money(selected.changes.after_cost)}；本次已实现盈亏 {money(selected.changes.realized)}（原币）</p>}
      <AssetTable assets={selected.positions} maskAssets={maskAssets} accountNames={data?.account_names} /><p>现金：{selected.cash.map(c => `${accountName(c.account_id)} ${money(c.amount)} ${c.currency}`).join("；")}</p><p>待确认 / 待到账：{selected.pending.map(p => `${accountName(p.account_id)} · ${p.pending_id} ${money(p.amount)} ${p.currency}`).join("；") || "无"}</p>
      {[...selected.issues, ...selected.performance_issues].map(i => <p key={i}>{i}</p>)}
      {!maskAssets && <details><summary>此项操作记录</summary><pre>{JSON.stringify(selected.data, null, 2)}</pre></details>}
    </div></Drawer>}
  </section>;
}
