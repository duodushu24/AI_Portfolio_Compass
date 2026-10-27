import { assetUnit, priceUnit, quoteKindLabel, unitLabel } from "./assets";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Drawer, Select, Table, Tag, Tooltip } from "@arco-design/web-react";
import { portfolioApi } from "./api";
import type { Asset, ChartPoint, DataNeed, Point, Portfolio } from "./types";
import { PortfolioChart } from "./PortfolioChart";
import { RenameSecurity } from "./RenameSecurity";
import { calendarDay, pointDay, profitMetrics, isTotalMetric } from "./chartLayout";
import type { ProfitMetric } from "./chartLayout";
import "./portfolio.css";

export const numeric = (v: string | number | null | undefined) => v == null ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
export const percent = (v: string | null | undefined) => v == null ? "—" : `${(Number(v) * 100).toFixed(2)}%`;
export const timeLabel = (v: string) => new Date(v).toLocaleString("zh-CN", { hour12: false });
const observationLabel = pointDay;
export const accountLabel = (id: string, names: Record<string, string> = {}) => names[id] || "未命名账户";
export const labels: Record<string, string> = { opening: "建档", include: "纳入组合", exclude: "移出组合", trade: "买卖", valuation: "更新市值", deposit: "入金", withdrawal: "出金", transfer: "账户转账", dividend: "分红", interest: "利息", fee: "费用", fx: "换汇", subscription: "待确认申购", settle: "赎回到账", cancel_subscription: "申购撤回", split: "拆分", share_credit: "红股入账", position_transfer: "转托管" };

export function AssetTable({ assets, onOpen, maskAssets = false, accountNames = {}, asOf, showQuoteDate = false, onRenamed }: { assets: Asset[]; onOpen?: (code: string) => void; maskAssets?: boolean; accountNames?: Record<string, string>; asOf?: string; showQuoteDate?: boolean; onRenamed?: () => void | Promise<void> }) {
  const money = (v: string | null, digits = 2) => maskAssets ? "••••" : v == null ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: digits });
  const signed = (v: string | null) => <span className={!maskAssets && v != null ? Number(v) > 0 ? "gain" : Number(v) < 0 ? "loss" : "" : ""}>{money(v)}</span>;
  return <div className="portfolio-holdings-table">
    <Table className="portfolio-compact-table" tableLayoutFixed rowKey={a => `${a.account_id}:${a.code}:${a.currency}:${a.unit}`} data={assets} pagination={{ pageSize: 10 }} scroll={{ x: showQuoteDate ? 1230 : 1110 }}
      expandProps={{ rowExpandable: (a: Asset) => (a.account_positions?.length ?? 0) > 1 }}
      expandedRowRender={a => a.account_positions && <AssetTable assets={a.account_positions} onOpen={onOpen} maskAssets={maskAssets} accountNames={accountNames} asOf={asOf} showQuoteDate={showQuoteDate} onRenamed={onRenamed} />}
      columns={[
      { title: "标的", width: 190, render: (_, a: Asset) => <div className="portfolio-asset-cell"><div className="portfolio-name-row"><button type="button" className="portfolio-name-button" onClick={() => onOpen?.(a.code)} disabled={!onOpen}>{a.name || a.code}</button>{onRenamed && <RenameSecurity code={a.code} name={a.name} market={a.market} onSaved={onRenamed} />}</div><small>{a.code}</small><small>{a.account_id === "all" ? `${a.account_positions?.length ?? 1} 个账户` : accountLabel(a.account_id, accountNames)}</small></div> },
      { title: "币种", dataIndex: "currency", width: 65 },
      { title: "数量", align: "right", width: 85, render: (_, a: Asset) => <Tooltip content={`数量单位：${unitLabel(a.unit)}`}><span>{money(a.quantity, 6)}</span></Tooltip> },
      { title: "成本价", align: "right", width: 95, render: (_, a: Asset) => <Tooltip content={`本阶段买入支出减卖出净收入、净分红，再除以剩余数量。单位价格，${priceUnit(a.currency, a.unit)}`}><span>{money(a.average_cost, 4)}</span></Tooltip> },
      { title: "市值价", align: "right", width: 95, render: (_, a: Asset) => {
        const mark = !a.quote ? "缺价" : a.quote.price_kind === "reference" ? "参考" : a.quote.price_kind === "estimate" ? "估" : new Date(a.quote.at).toDateString() === new Date(asOf || Date.now()).toDateString() ? "·" : null;
        return <Tooltip content={a.quote ? `${quoteKindLabel(a.quote.price_kind)} · ${a.quote.source} · ${timeLabel(a.quote.at)} · ${priceUnit(a.currency, a.unit)}` : "缺少报价"}><span>{money(a.price, 4)}{mark && <sup className="portfolio-quote-mark">{mark}</sup>}</span></Tooltip>;
      } },
      ...(showQuoteDate ? [{ title: "市值更新日期", width: 120, render: (_: unknown, a: Asset) => {
        const rows = a.account_positions || [a];
        if (rows.some(p => !p.quote?.at)) return "—";
        const dates = [...new Set(rows.map(p => p.quote!.price_date || calendarDay(p.quote!.at)))].sort();
        return dates.length > 1 ? <Tooltip content="各账户价格日期不同，显示最早日期；展开可查看各账户。"><span>{dates[0]}</span></Tooltip> : dates[0];
      } }] : []),
      { title: "持仓盈亏", align: "right", width: 105, render: (_, a: Asset) => signed(a.floating) },
      { title: "持仓收益率", align: "right", width: 100, render: (_, a: Asset) => <span className={a.holding_return == null ? "" : Number(a.holding_return) >= 0 ? "gain" : "loss"}>{percent(a.holding_return)}</span> },
      { title: "本阶段分红", align: "right", width: 110, render: (_, a: Asset) => signed(a.dividends) },
      { title: "持仓市值（CNY）", align: "right", width: 130, render: (_, a: Asset) => money(a.market_value_cny) },
      { title: "仓位", align: "right", width: 80, render: (_, a: Asset) => percent(a.position_weight) },
    ]} />
  </div>;
}

export function PortfolioPanel({ accountId = "all", code = "", maskAssets = false, revision = 0, onOpen, showAssetTable = true, portfolio, onSupplement }: { accountId?: string; code?: string; maskAssets?: boolean; revision?: number; onOpen?: (code: string) => void; showAssetTable?: boolean; portfolio?: Portfolio; onSupplement?: (need: DataNeed) => void }) {
  const [data, setData] = useState<Portfolio | null>(null), [error, setError] = useState("");
  const [metric, setMetric] = useState<ProfitMetric>("total_return"), [selected, setSelected] = useState<Point | null>(null);
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
  const total = !code && isTotalMetric(metric);
  const profit = total ? current?.cumulative_profit : current?.profit;
  const rate = total ? current?.cumulative_profit_rate : current?.cumulative_return;
  const scopeLabel = total ? "累计" : "统计期";
  const needs = [...(current?.data_needs || []), ...(total ? current?.cumulative_needs || [] : current?.performance_needs || [])];
  // One actionable row per missing input, even when it affects several metrics.
  const uniqueNeeds = [...new Map(needs.map(n => [`${n.account_id}:${n.at}:${n.kind}:${n.code || ""}:${n.currency}:${n.unit || ""}`, n])).values()];
  const notes = [...new Set([...(current?.issues || []), ...(current?.performance_issues || [])])];
  return <section className="panel portfolio-panel stack">
    <div className="portfolio-toolbar"><div><h3>{code ? "标的收益与成交历史" : "整体组合收益"}</h3><small>{code ? "唯一摊薄成本口径；现金分红抵扣成本，清仓后再买入重新计算" : total ? "累计口径含历史结转 · 收益率按净投入计算 · CNY" : "统计期口径 · 收益率按区间净值计算 · CNY"}</small></div>{!code && <Select aria-label="收益曲线指标" value={metric} onChange={value => setMetric(value as ProfitMetric)} options={profitMetrics.map(o => ({ ...o }))} />}</div>
    {error && <Alert type="error" content={error} />}
    {pointLoading && <small>正在读取当时账目…</small>}
    {!code && current && <div className="portfolio-metrics"><div>组合总资产<strong>{money(current.total_assets)} CNY</strong></div><div>{scopeLabel}盈亏<strong>{profit != null ? `${money(profit)} CNY` : "待补齐"}</strong></div><div>{scopeLabel}收益率<strong>{percent(rate ?? null)}</strong></div><div>现金<strong>{money(current.cash_value)} CNY</strong></div></div>}
    {!code && current?.fx_rates && <small className="metadata-note">{Object.entries(current.fx_rates).filter(([c]) => c !== "CNY").map(([c,r]) => `${c}/CNY ${Number(r.rate).toFixed(4)} · ${r.rate_date || calendarDay(r.at)}`).join("　")}</small>}
    {!!uniqueNeeds.length && <Alert type="warning" content={<div><strong>{scopeLabel}收益资料待补齐</strong>{!total && profit != null && rate == null && <p>盈亏金额可计算；收益率还需要资金进出时的估值。</p>}<ul>{uniqueNeeds.map((n, i) => <li key={i}>{accountName(n.account_id)} · {n.valuation_date || calendarDay(n.at)}{n.context === "opening" ? " 期初" : n.context === "cash_flow" ? " 资金进出时" : n.context === "baseline" ? " 收益基准" : ""} · {n.kind === "fx" ? `${n.currency}/CNY 汇率` : `${n.name || n.code}：${n.kind === "price" ? "市值价" : n.kind === "cost_cny" ? "历史人民币剩余成本" : "成本价"}`}缺失。{onSupplement ? <Button size="mini" type="text" onClick={() => onSupplement(n)}>{n.action === "opening" ? "补齐期初" : n.kind === "fx" ? "补录汇率" : "补录市值"}</Button> : "请到账户与数据补录。"}</li>)}</ul></div>} />}
    {!code && total && current && !!current.missing_cumulative_accounts?.length && !uniqueNeeds.length && <Alert type="warning" content={`累计盈亏待补齐：${current.missing_cumulative_accounts.map(accountName).join("、")}。请到账户与数据核对期初与资金记录。`} />}
    {!code && total && current?.cumulative_profit != null && current.cumulative_profit_rate == null && <p className="metadata-note">累计净投入为零或负数，不展示累计收益率；累计盈亏金额仍可查看。</p>}
    {!code && current && <div className="portfolio-profit-basis"><details><summary>收益口径</summary><p>累计盈亏包含历史结转、期初持仓盈亏及接入后的账户盈亏；历史结转不增加现金、不改变持仓成本。曲线从已有记录开始，不补画建档前走势。</p>
      <p>累计收益率＝累计盈亏 ÷ 累计净投入；累计净投入＝当前净资产－累计盈亏，目前为 {money(current.cumulative_net_investment)} CNY。净投入不为正时收益率不适用；提取本金可能放大该比例。统计期收益率依据区间净值计算，与累计口径分开。</p>
      <p>历史结转留空按 0 计入，可到账户起点补填。统计期盈亏：{money(current.profit)} CNY。</p>
      {current.account_profits?.map(p => <p key={p.account_id}>{accountName(p.account_id)}：历史结转 {money(p.historical_profit_cny)} · 期初持仓盈亏 {money(p.opening_holding_profit)} · 接入后盈亏 {money(p.profit_since_opening)} · 累计盈亏 {money(p.cumulative_profit)} CNY</p>)}<p>收益起点：{current.performance_baseline ? current.performance_baseline.valuation_date || calendarDay(current.performance_baseline.at) : beginning ? observationLabel(beginning) : "期初估值待补齐"} · 期初总资产 {money(current.opening_assets)} CNY · 当前总资产 {money(current.total_assets)} CNY · 净外部入金 {money(current.net_flows)} CNY</p><p>组合盈亏＝当前总资产－期初总资产－期间净外部入金。买卖产生的现金已计入总资产，不另加一遍卖出利润。</p></details></div>}
    {!!notes.length && <details className="metadata-note"><summary>计算说明</summary>{notes.map(i => <p key={i}>{i}</p>)}</details>}
    {current?.ended && <Alert type="info" content="本连续区间已结束，保留最后有效收益；重新入金会开始新连续区间。" />}
    <PortfolioChart points={data?.points ?? []} metric={code ? "return" : metric} assetCode={code} onSelect={selectPoint} eventLabels={labels} maskAssets={maskAssets} />
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
    {!code && <p className="metadata-note">未更新标的按该时点最近一次有效价格和当时数量计算；价格日期见当前持仓。未知历史人民币成本不以当前汇率补算。</p>}
    {selected && <Drawer title={`${labels[selected.event_type]} · ${observationLabel(selected)}`} visible width={1000} footer={null} onCancel={() => setSelected(null)}><div className="stack">
      <p>总资产 {money(selected.total_assets)} CNY · 净值 {numeric(selected.nav)} · 份额 {money(selected.units)} · {scopeLabel}收益率 {percent(total && !code ? selected.cumulative_profit_rate : selected.cumulative_return)} · {scopeLabel}盈亏 {money(total && !code ? selected.cumulative_profit : selected.profit)} CNY</p>
      <Tag color={selected.quality === "complete" ? "green" : "orange"}>{selected.quality === "complete" ? "按最近已记录价格计算" : selected.quality === "missing" ? "计算资料待补齐" : "含明确标记的估算值"}</Tag>
      {!!Object.keys(selected.fx_basis || {}).length && <p>折算汇率：{Object.entries(selected.fx_basis || {}).map(([curr, fx]) => `${curr}/CNY ${numeric(fx.rate)} · ${timeLabel(fx.at)} · ${fx.source}${fx.carried ? "（沿用）" : ""}${fx.is_estimate ? "（估算）" : ""}`).join("；")}</p>}
      {selected.event_type === "trade" && <><h4>本次交易</h4><p>{accountName(selected.account_id)} · {String(selected.data.name || selected.data.code)} · {selected.data.side === "BUY" ? "买入" : "卖出"} · 数量 {maskAssets ? "••••" : numeric(String(selected.data.quantity))} · 成交价 {maskAssets ? "••••" : numeric(String(selected.data.price))} {String(selected.data.currency)} · 费用 {maskAssets ? "••••" : numeric(String(selected.data.fees))}</p>{selected.total_assets == null && <small>此时缺少完整组合报价，不计算该时点收益；成交和数量、成本、现金变化已记录。</small>}</>}
      {selected.changes && <p>数量 {money(selected.changes.before_quantity)} → {money(selected.changes.after_quantity)}；剩余成本 {money(selected.changes.before_cost)} → {money(selected.changes.after_cost)}；本次已实现盈亏 {money(selected.changes.realized)}（原币）</p>}
      <h4>当时持仓</h4><AssetTable assets={selected.positions.filter(a => Number(a.quantity) > 0)} asOf={selected.observed_at} maskAssets={maskAssets} accountNames={data?.account_names} /><p>现金：{selected.cash.map(c => `${accountName(c.account_id)} ${money(c.amount)} ${c.currency}`).join("；")}</p><p>待确认 / 待到账：{selected.pending.map(p => `${accountName(p.account_id)} · ${p.pending_id} ${money(p.amount)} ${p.currency}`).join("；") || "无"}</p>
      {[...selected.issues, ...selected.performance_issues].map(i => <p key={i}>{i}</p>)}
      {!maskAssets && <details><summary>此项操作记录</summary><pre>{JSON.stringify(selected.data, null, 2)}</pre></details>}
    </div></Drawer>}
  </section>;
}
