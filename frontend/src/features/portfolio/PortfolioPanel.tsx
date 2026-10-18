import { assetUnit, priceUnit, quoteKindLabel, unitLabel } from "./assets";
import { useEffect, useRef, useState } from "react";
import { Alert, Drawer, Empty, Select, Table, Tag, Tooltip } from "@arco-design/web-react";
import { portfolioApi } from "./api";
import type { Asset, ChartPoint, Point, Portfolio } from "./types";
import "./portfolio.css";

export const numeric = (v: string | number | null | undefined) => v == null ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
export const percent = (v: string | null | undefined) => v == null ? "—" : `${(Number(v) * 100).toFixed(2)}%`;
export const timeLabel = (v: string) => new Date(v).toLocaleString("zh-CN", { hour12: false });
const observationLabel = (p: ChartPoint) => p.valuation_date ? `${p.valuation_date} 收盘` : timeLabel(p.observed_at);
export const accountLabel = (id: string, names: Record<string, string> = {}) => names[id] || "未命名账户";
export const labels: Record<string, string> = { opening: "建档", include: "纳入组合", exclude: "移出组合", trade: "买卖", valuation: "更新市值", deposit: "入金", withdrawal: "出金", transfer: "账户转账", dividend: "分红", interest: "利息", fee: "费用", fx: "换汇", subscription: "待确认申购", settle: "赎回到账", cancel_subscription: "申购撤回", split: "拆分", share_credit: "红股入账", position_transfer: "转托管" };

function Chart({ points: records, metric, onSelect, assetCode = "" }: { points: ChartPoint[]; metric: string; onSelect: (p: ChartPoint) => void; assetCode?: string }) {
  const closingObservations = !assetCode && Boolean(records[0]?.valuation_date);
  const points = closingObservations ? records.filter(p => p.event_type === "valuation" && (p.valuation_date || p.total_assets != null)) : records;
  if (!points.length) return <Empty description="确认期初后，买卖、资金和市值更新会自动形成收益记录。" />;
  if (points.every(p => p.cumulative_return == null && p.profit == null)) return <Empty description="历史估值未补齐，暂不展示收益曲线。交易和资金记录已保留。" />;
  const value = (p: ChartPoint) => {
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
  return <div className="portfolio-chart"><svg viewBox="0 0 900 290" role="img" aria-label={assetCode ? "标的持仓收益率曲线" : "整体组合收益曲线"}>
    {[0, 1, 2, 3, 4].map(i => { const v = low - pad + (high - low + 2 * pad) * i / 4; return <g key={i}><line x1="75" x2="870" y1={y(v)} y2={y(v)} stroke="#d9dfe7" /><text x="65" y={y(v) + 4} textAnchor="end">{v.toFixed(1)}{assetCode || metric === "return" ? "%" : ""}</text></g>; })}
    <path d={path} fill="none" stroke="#165dff" strokeWidth="2.5" />
    {points.map((p, i) => <circle key={i} cx={x(times[i])} cy={values[i] == null ? 250 : y(values[i]!)} r="5" fill={p.event_type === "trade" ? "#ff7d00" : values[i] == null ? "#86909c" : "#165dff"} tabIndex={0} role="button" aria-label={`查看收益记录 ${observationLabel(p)} ${labels[p.event_type]}`} onClick={() => onSelect(p)} onKeyDown={e => { if (e.key === "Enter") onSelect(p); }}><title>{observationLabel(p)} · {labels[p.event_type]} · {values[i] == null ? "资料未齐/无持仓" : values[i]?.toFixed(2)}</title></circle>)}
    <text x="75" y="280">{observationLabel(points[0])}</text><text x="870" y="280" textAnchor="end">{observationLabel(points[points.length - 1])}</text>
  </svg><small>{closingObservations ? "按已记录的收盘估值连接，不生成每日收益。期间买卖、分红和现金变化已按账本计入；点击可查看估值依据。" : "橙色为实际买卖点，可点击查看数量、成本和利润变化。仅连接已保存时点；不同连续区间和缺失资料处断开。"}</small></div>;
}

export function AssetTable({ assets, onOpen, maskAssets = false, accountNames = {}, asOf }: { assets: Asset[]; onOpen?: (code: string) => void; maskAssets?: boolean; accountNames?: Record<string, string>; asOf?: string }) {
  const money = (v: string | null, digits = 2) => maskAssets ? "••••" : v == null ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: digits });
  const signed = (v: string | null) => <span className={!maskAssets && v != null ? Number(v) > 0 ? "gain" : Number(v) < 0 ? "loss" : "" : ""}>{money(v)}</span>;
  return <div className="portfolio-holdings-table">
    <Table className="portfolio-compact-table" tableLayoutFixed rowKey={a => `${a.account_id}:${a.code}:${a.currency}:${a.unit}`} data={assets} pagination={{ pageSize: 10 }} scroll={{ x: 1110 }}
      expandProps={{ rowExpandable: (a: Asset) => (a.account_positions?.length ?? 0) > 1 }}
      expandedRowRender={a => a.account_positions && <AssetTable assets={a.account_positions} onOpen={onOpen} maskAssets={maskAssets} accountNames={accountNames} asOf={asOf} />}
      columns={[
      { title: "标的", width: 190, render: (_, a: Asset) => <div className="portfolio-asset-cell"><button type="button" className="portfolio-name-button" onClick={() => onOpen?.(a.code)} disabled={!onOpen}>{a.name || a.code}</button><small>{a.code}</small><small>{a.account_id === "all" ? `${a.account_positions?.length ?? 1} 个账户` : accountLabel(a.account_id, accountNames)}</small></div> },
      { title: "币种", dataIndex: "currency", width: 65 },
      { title: "数量", align: "right", width: 85, render: (_, a: Asset) => <Tooltip content={`数量单位：${unitLabel(a.unit)}`}><span>{money(a.quantity, 6)}</span></Tooltip> },
      { title: "摊薄成本价", align: "right", width: 95, render: (_, a: Asset) => <Tooltip content={`本阶段买入支出减卖出净收入、净分红，再除以剩余数量。单位价格，${priceUnit(a.currency, a.unit)}`}><span>{money(a.average_cost, 4)}</span></Tooltip> },
      { title: "市值价", align: "right", width: 95, render: (_, a: Asset) => <Tooltip content={a.quote ? `${quoteKindLabel(a.quote.price_kind)} · ${a.quote.source} · ${timeLabel(a.quote.at)} · ${priceUnit(a.currency, a.unit)}` : "缺少报价"}><span>{money(a.price, 4)}<sup className="portfolio-quote-mark">{!a.quote ? "缺价" : a.quote.price_kind === "estimate" ? "估" : new Date(a.quote.at).toDateString() !== new Date(asOf || Date.now()).toDateString() ? "旧" : "·"}</sup></span></Tooltip> },
      { title: "持仓盈亏", align: "right", width: 105, render: (_, a: Asset) => signed(a.floating) },
      { title: "持仓收益率", align: "right", width: 100, render: (_, a: Asset) => <span className={a.holding_return == null ? "" : Number(a.holding_return) >= 0 ? "gain" : "loss"}>{percent(a.holding_return)}</span> },
      { title: "本阶段分红", align: "right", width: 110, render: (_, a: Asset) => signed(a.dividends) },
      { title: "持仓市值（CNY）", align: "right", width: 130, render: (_, a: Asset) => money(a.market_value_cny) },
      { title: "仓位", align: "right", width: 80, render: (_, a: Asset) => percent(a.position_weight) },
    ]} />
  </div>;
}

export function PortfolioPanel({ accountId = "all", code = "", maskAssets = false, revision = 0, onOpen, showAssetTable = true, portfolio }: { accountId?: string; code?: string; maskAssets?: boolean; revision?: number; onOpen?: (code: string) => void; showAssetTable?: boolean; portfolio?: Portfolio }) {
  const [data, setData] = useState<Portfolio | null>(null), [error, setError] = useState("");
  const [metric, setMetric] = useState("return"), [selected, setSelected] = useState<Point | null>(null);
  const request = useRef(0);
  const pointRequest = useRef(0);
  const [pointLoading, setPointLoading] = useState(false);
  async function selectPoint(point: ChartPoint) {
    const id = ++pointRequest.current, parentId = request.current;
    setPointLoading(true);
    try {
      const detail = await portfolioApi.point(accountId, point, code);
      if (id === pointRequest.current && parentId === request.current) setSelected(detail);
    } catch (e) { if (id === pointRequest.current && parentId === request.current) setError(e instanceof Error ? e.message : "记录读取失败"); }
    finally { if (id === pointRequest.current && parentId === request.current) setPointLoading(false); }
  }
  useEffect(() => { const id = ++request.current; if (portfolio) { setData(portfolio); setError(""); return () => { request.current++; }; } setData(null); setSelected(null); portfolioApi.overview(accountId, code).then(result => { if (id === request.current) { setData(result); setError(""); } }).catch(e => { if (id === request.current) setError(String(e.message)); }); return () => { request.current++; }; }, [accountId, code, revision, portfolio]);
  const current = data?.current, money = (v: string | null | undefined) => maskAssets ? "••••" : v == null ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  const accountName = (id: string) => accountLabel(id, data?.account_names);
  const beginning = data?.points.find(p => p.interval === current?.interval && p.opening_assets != null);
  return <section className="panel portfolio-panel stack">
    <div className="portfolio-toolbar"><div><h3>{code ? "标的收益与成交历史" : "整体组合收益"}</h3><small>{code ? "唯一摊薄成本口径；现金分红抵扣成本，清仓后再买入重新计算" : "统计区间内的净值收益 · 包含现金、资金进出与汇率 · CNY"}</small></div>{!code && <Select value={metric} onChange={setMetric} options={[{ value: "return", label: "累计组合收益率" }, { value: "profit", label: "累计组合盈亏金额" }]} />}</div>
    {error && <Alert type="error" content={error} />}
    {pointLoading && <small>正在读取当时账目…</small>}
    {!code && current && <div className="portfolio-metrics"><div>组合总资产<strong>{money(current.total_assets)} CNY</strong></div><div>累计组合收益率<strong>{percent(current.cumulative_return)}</strong></div><div>累计组合盈亏<strong>{money(current.profit)} CNY</strong></div><div>现金<strong>{money(current.cash_value)} CNY</strong></div></div>}
    {!code && current && <div className="portfolio-profit-basis"><p>组合盈亏从期初市值和现金开始统计；持仓盈亏已包含当前阶段的部分卖出盈亏和分红，不能再额外加分红；清仓收益在已清仓查询中展示，包含该阶段已收分红。</p><details><summary>查看组合盈亏计算依据</summary><p>收益起点：{beginning ? observationLabel(beginning) : "期初估值待补齐"} · 期初总资产 {money(current.opening_assets)} CNY · 当前总资产 {money(current.total_assets)} CNY · 净外部入金 {money(current.net_flows)} CNY</p><p>组合盈亏＝当前总资产－期初总资产－期间净外部入金。买卖产生的现金已计入总资产，不另加一遍卖出利润。</p></details></div>}
    {current && (current.issues.length > 0 || current.performance_issues.length > 0) && <Alert type="warning" content={<details><summary>{current.quality === "missing" ? "资料缺失，完整资产及收益不可用" : "部分报价沿用旧值或使用估算；查看依据"}</summary>{[...current.issues, ...current.performance_issues].map(i => <p key={i}>{i}</p>)}</details>} />}
    {current?.ended && <Alert type="info" content="本连续区间已结束，保留最后有效收益；重新入金会开始新连续区间。" />}
    <Chart points={data?.points ?? []} metric={metric} assetCode={code} onSelect={selectPoint} />
    {!current && <p>到账户与数据确认期初资料。未建档账户的旧快照保留为来源，不参与这条净值曲线。</p>}
    {current && showAssetTable && <><h4>{code ? "成本盈亏" : "当前持仓"}</h4><AssetTable assets={current.positions.filter(a => Number(a.quantity) > 0)} onOpen={onOpen} maskAssets={maskAssets} accountNames={data?.account_names} /></>}
    {code && current && <><h4>历次清仓</h4><Table rowKey={r => `${r.account_id}:${r.cycle}`} pagination={false} data={current.positions.flatMap(a => (a.closed_cycles ?? []).map(c => ({ ...c, account_id: a.account_id, currency: a.currency })))} columns={[
      { title: "账户 / 阶段", render: (_, r) => `${accountName(r.account_id)} · 第 ${r.cycle} 次持有` },
      { title: "开始 / 清仓时间", render: (_, r) => `${timeLabel(r.opened_at)} / ${timeLabel(r.closed_at)}` },
      { title: "结转成本", render: (_, r) => `${money(r.disposed_cost)} ${r.currency}` },
      { title: "清仓收益额", render: (_, r) => `${money(r.realized)} ${r.currency}` },
      { title: "清仓收益率", render: (_, r) => percent(r.return) },
    ]} /><small>清仓收益率＝该持有阶段已实现盈亏合计 ÷ 卖出结转成本合计，包含分批卖出；不是年化收益。未知或零成本不计算收益率。</small></>}
    {code && <Table rowKey={r => `${r.category}:${r.id}`} data={data?.records ?? []} pagination={{ pageSize: 8 }} columns={[{ title: "时间", dataIndex: "effective_at", render: timeLabel }, { title: "事项", render: (_, r) => `${accountName(r.account_id)} · ${labels[r.kind]}${r.is_void ? "（已作废）" : ""}` }, { title: "数量 / 价格 / 费用", render: (_, r) => maskAssets ? "••••" : `${r.data.side === "BUY" ? "买入" : r.data.side === "SELL" ? "卖出" : ""} ${r.data.quantity ?? ""} ${r.data.quantity != null ? unitLabel(String(r.data.unit || assetUnit(String(r.data.asset_type || "stock")))) : ""} / ${r.data.price ?? ""} ${r.data.price != null ? priceUnit(String(r.data.currency), String(r.data.unit || assetUnit(String(r.data.asset_type || "stock")))) : ""} / ${r.data.fees ?? ""}` }]} />}
    {!code && <p className="metadata-note">未知历史人民币成本不以当前汇率补算。报价沿用情况与资金边界估算可查看每个点。</p>}
    {selected && <Drawer title={`${labels[selected.event_type]} · ${observationLabel(selected)}`} visible width={1000} footer={null} onCancel={() => setSelected(null)}><div className="stack">
      <p>总资产 {money(selected.total_assets)} CNY · 净值 {numeric(selected.nav)} · 份额 {money(selected.units)} · 收益率 {percent(selected.cumulative_return)} · 累计组合盈亏 {money(selected.profit)} CNY</p>
      <Tag color={selected.quality === "complete" ? "green" : "orange"}>{selected.quality === "complete" ? "当时报价完整" : "估算 / 资料缺失"}</Tag>
      {selected.changes && <p>数量 {money(selected.changes.before_quantity)} → {money(selected.changes.after_quantity)}；剩余成本 {money(selected.changes.before_cost)} → {money(selected.changes.after_cost)}；本次已实现盈亏 {money(selected.changes.realized)}（原币）</p>}
      <AssetTable assets={selected.positions} asOf={selected.observed_at} maskAssets={maskAssets} accountNames={data?.account_names} /><p>现金：{selected.cash.map(c => `${accountName(c.account_id)} ${money(c.amount)} ${c.currency}`).join("；")}</p><p>待确认 / 待到账：{selected.pending.map(p => `${accountName(p.account_id)} · ${p.pending_id} ${money(p.amount)} ${p.currency}`).join("；") || "无"}</p>
      {[...selected.issues, ...selected.performance_issues].map(i => <p key={i}>{i}</p>)}
      {!maskAssets && <details><summary>此项操作记录</summary><pre>{JSON.stringify(selected.data, null, 2)}</pre></details>}
    </div></Drawer>}
  </section>;
}
