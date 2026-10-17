import { useEffect, useRef, useState } from "react";
import { Alert, Button, Drawer, Input, Select, Table } from "@arco-design/web-react";
import type { AccountSummary } from "../../api";
import { portfolioApi } from "./api";
import { numeric, percent, timeLabel } from "./PortfolioPanel";
import type { ClosedPosition, ClosedQuery, ClosedTrade, Portfolio } from "./types";
import { unitLabel } from "./assets";

const amount = (v: string | null, masked: boolean) => masked ? "••••" : v == null ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
const day = (v: string) => new Date(v).toLocaleDateString("zh-CN");

export function ClosedPositions({ accountId, accounts, revision, maskAssets = false }: { accountId: string; accounts: AccountSummary[]; revision?: unknown; maskAssets?: boolean }) {
  const [account, setAccount] = useState(accountId), [keyword, setKeyword] = useState(""), [start, setStart] = useState(""), [end, setEnd] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({ account_id: accountId });
  const [data, setData] = useState<ClosedQuery | null>(null), [error, setError] = useState(""), [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<ClosedPosition | null>(null);
  const request = useRef(0);
  useEffect(() => { setAccount(accountId); setKeyword(""); setStart(""); setEnd(""); setFilters({ account_id: accountId }); }, [accountId]);
  useEffect(() => {
    const id = ++request.current; setLoading(true); setData(null); setDetail(null); setError("");
    portfolioApi.closed(filters).then(r => { if (id === request.current) setData(r); }).catch(e => { if (id === request.current) setError(String(e.message)); }).finally(() => { if (id === request.current) setLoading(false); });
    return () => { request.current++; };
  }, [filters, revision]);
  const query = () => setFilters({ account_id: account, keyword: keyword.trim(), ...(start ? { start: new Date(`${start}T00:00:00`).toISOString() } : {}), ...(end ? { end: new Date(`${end}T23:59:59.999`).toISOString() } : {}) });
  const summary = data?.summary;
  return <div className="stack closed-positions">
    <div className="closed-query-toolbar">
      <Select aria-label="清仓查询账户" value={account} onChange={setAccount} options={[{ value: "all", label: "全部账户" }, ...accounts.map(a => ({ value: a.account_id, label: a.display_name || a.institution || "未命名账户" }))]} />
      <Input.Search aria-label="清仓标的搜索" placeholder="标的名称或代码" value={keyword} onChange={setKeyword} onSearch={query} />
      <label>清仓日期<input aria-label="清仓开始日期" type="date" value={start} onChange={e => setStart(e.target.value)} /></label><span>至</span><input aria-label="清仓结束日期" type="date" value={end} onChange={e => setEnd(e.target.value)} />
      <Button type="primary" onClick={query}>查询</Button>
    </div>
    {error && <Alert type="error" content={error} />}
    <div className="portfolio-metrics closed-summary">
      <div>清仓盈亏（CNY）<strong>{summary ? amount(summary.realized_cny, maskAssets) : "—"}</strong></div>
      <div>清仓胜率<strong>{summary ? percent(summary.win_rate) : "—"}</strong></div>
      <div>清仓次数<strong>{summary?.count ?? "—"}</strong></div>
      <div>涉及标的数<strong>{summary?.symbol_count ?? "—"}</strong></div>
    </div>
    {!!summary?.missing_cny_count && <Alert type="warning" content={`有 ${summary.missing_cny_count} 次清仓缺少历史人民币成本或卖出时汇率，未输出完整人民币合计。已知人民币盈亏：${amount(summary.known_realized_cny, maskAssets)}；按原币已知盈亏：${Object.entries(summary.by_currency).map(([c, v]) => `${amount(v, maskAssets)} ${c}`).join("；") || "无"}`} />}
    {!!summary?.unknown_count && <small>有 {summary.unknown_count} 次清仓成本未知，不计入胜率；胜率＝盈利次数 ÷ 盈亏已知次数，持平计入分母。</small>}
    <Table className="portfolio-compact-table" tableLayoutFixed rowKey={r => `${r.account_id}:${r.code}:${r.currency}:${r.unit}:${r.cycle}`} data={data?.items ?? []} loading={loading} pagination={{ pageSize: 10 }} scroll={{ x: 1250 }} onRow={r => ({ onClick: () => setDetail(r) })} columns={[
      { title: "标的", width: 180, render: (_, r: ClosedPosition) => <div className="portfolio-asset-cell"><button type="button" className="portfolio-name-button" onClick={() => setDetail(r)}>{r.name || r.code}</button><small>{r.code}</small></div> },
      { title: "账户", dataIndex: "account_name", width: 120 }, { title: "币种", dataIndex: "currency", width: 65 },
      { title: "建仓日期", width: 120, render: (_, r: ClosedPosition) => r.opening_kind === "buy" ? day(r.opened_at) : "起点前 / 转入" },
      { title: "清仓日期", width: 120, sorter: (a, b) => a.closed_at.localeCompare(b.closed_at), render: (_, r: ClosedPosition) => day(r.closed_at) },
      { title: "持有天数", align: "right", width: 90, render: (_, r: ClosedPosition) => r.holding_days ?? "—" },
      { title: "买卖盈亏", align: "right", width: 110, render: (_, r: ClosedPosition) => amount(r.trading_profit, maskAssets) },
      { title: "现金分红", align: "right", width: 100, render: (_, r: ClosedPosition) => amount(r.dividends, maskAssets) },
      { title: "清仓盈亏", align: "right", width: 115, sorter: (a, b) => Number(a.realized) - Number(b.realized), render: (_, r: ClosedPosition) => amount(r.realized, maskAssets) },
      { title: "清仓收益率", align: "right", width: 115, render: (_, r: ClosedPosition) => percent(r.return) },
    ]} />
    <small>每行是一个账户中一次完整持有阶段，包含分批买卖、费用和已收现金分红；再买回重新计算，此前记录保留。仅转出持仓不计清仓。日期筛选按清仓日期，胜率按原币盈亏统计；仅覆盖已录入账目。</small>
    {detail && <Drawer visible title={`${detail.name} · 第 ${detail.cycle} 次持有`} width={1000} footer={null} onCancel={() => setDetail(null)}>
      <div className="stack"><p>{detail.account_name} · {timeLabel(detail.opened_at)} — {timeLabel(detail.closed_at)}</p>
        <p>清仓盈亏 {amount(detail.realized, maskAssets)} {detail.currency} · 清仓收益率 {percent(detail.return)} · 累计买入支出 {amount(detail.buy_total, maskAssets)} {detail.currency}</p>
        <p>买卖盈亏 {amount(detail.trading_profit, maskAssets)} · 现金分红 {amount(detail.dividends, maskAssets)}；清仓收益率以累计买入支出为基数。</p>
        {detail.opening_kind !== "buy" && <Alert type="info" content="本阶段从已有持仓或转入开始，真实首次买入日期未确认；不计算完整持有天数。" />}
        <p>以下数量按{unitLabel(detail.unit)}、单价按 {detail.currency}／{unitLabel(detail.unit)}、费用与盈亏按 {detail.currency} 展示。</p>
        <Table className="portfolio-compact-table" rowKey="record_id" data={detail.trades} pagination={false} columns={[
          { title: "成交时间", dataIndex: "at", render: timeLabel }, { title: "方向", render: (_, r: ClosedTrade) => r.side === "BUY" ? "买入" : "卖出" },
          { title: "数量", align: "right", render: (_, r: ClosedTrade) => maskAssets ? "••••" : numeric(r.quantity) },
          { title: "成交价", align: "right", render: (_, r: ClosedTrade) => maskAssets ? "••••" : numeric(r.price) },
          { title: "费用", align: "right", render: (_, r: ClosedTrade) => amount(r.fees, maskAssets) },
          { title: "净清算金额", align: "right", render: (_, r: ClosedTrade) => amount(r.cash_amount, maskAssets) },
        ]} />
        {!!detail.dividend_records?.length && <><h4>本阶段现金分红</h4><Table rowKey="record_id" pagination={false} data={detail.dividend_records} columns={[{ title: "到账时间", dataIndex: "at", render: timeLabel }, { title: "净到账金额", render: (_, r) => amount(r.amount, maskAssets) }, { title: "币种", dataIndex: "currency" }]} /></>}
      </div>
    </Drawer>}
  </div>;
}

// Data management shows the facts for this symbol, without another account performance chart.
export function AssetHistory({ accountId, code, maskAssets }: { accountId: string; code: string; maskAssets: boolean }) {
  const [data, setData] = useState<Portfolio | null>(null), [error, setError] = useState("");
  useEffect(() => { let cancelled = false; portfolioApi.overview(accountId, code).then(r => { if (!cancelled) setData(r); }).catch(e => { if (!cancelled) setError(String(e.message)); }); return () => { cancelled = true; }; }, [accountId, code]);
  return <div className="stack">{error && <Alert type="error" content={error} />}<Table rowKey="id" data={(data?.records ?? []).filter(r => r.kind === "trade")} columns={[
    { title: "成交时间", dataIndex: "effective_at", render: timeLabel }, { title: "方向", render: (_, r) => r.data.side === "BUY" ? "买入" : "卖出" },
    { title: "数量", render: (_, r) => maskAssets ? "••••" : numeric(String(r.data.quantity)) },
    { title: "成交价", render: (_, r) => maskAssets ? "••••" : numeric(String(r.data.price)) },
    { title: "币种", render: (_, r) => String(r.data.currency) }, { title: "费用", render: (_, r) => amount(String(r.data.fees), maskAssets) },
    { title: "状态", render: (_, r) => r.is_void ? "已作废" : "有效" },
  ]} /><small>交易纠错和作废到账户记账操作；历次完整退出请到“已清仓查询”查看。</small></div>;
}
