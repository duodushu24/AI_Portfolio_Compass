import { useEffect, useRef, useState } from "react";
import { Alert, Button, Drawer, Input, Select, Table } from "@arco-design/web-react";
import { api, AccountSummary, ReturnPoint, HoldingHistoryItem } from "../api";
import { accountLabel, AssetTable, percent, PortfolioPanel, timeLabel } from "./portfolio/PortfolioPanel";

import { portfolioApi } from "./portfolio/api";
import type { DataNeed, Opening, Portfolio } from "./portfolio/types";
import { assetOptions } from "./portfolio/assets";
import { EntryEditor, OpeningEditor } from "./portfolio/PortfolioWorkbench";

// Old observations remain readable source material; the account ledger owns new writes.
export function ReturnHistoryPanel({ accounts, maskAssets, onChanged, onOpen }: { accounts: AccountSummary[]; maskAssets: boolean; onChanged: () => Promise<void>; onOpen?: (code: string) => void }) {
  const [legacy, setLegacy] = useState<{ points: ReturnPoint[]; holdings: HoldingHistoryItem[] } | null>(null), [error, setError] = useState("");
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null), [account, setAccount] = useState("all"), [keyword, setKeyword] = useState("");
  const [supplement, setSupplement] = useState<{ need: DataNeed; opening?: Opening } | null>(null);
  const [updating, setUpdating] = useState<{ index: number; total: number; name: string } | null>(null);
  const [updateResults, setUpdateResults] = useState<Array<{ account: string; status: string; message: string }> | null>(null);
  const updatingRef = useRef(false), mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { let cancelled = false; portfolioApi.overview("all").then(r => { if (!cancelled) { setPortfolio(r); setError(""); } }).catch(e => { if (!cancelled) setError(String(e.message)); }); return () => { cancelled = true; }; }, []);
  const holdings = account === "all" ? portfolio?.holdings ?? [] : (portfolio?.current?.positions ?? []).filter(p => p.account_id === account && Number(p.quantity) > 0);
  const filtered = holdings.filter(p => `${p.name} ${p.code}`.toLowerCase().includes(keyword.trim().toLowerCase()));
  const allocationLabels: Record<string, string> = { ...Object.fromEntries(assetOptions.map(o => [o.value, o.label])), cash: "现金", pending: "待确认 / 待到账", liabilities: "负债" };
  const accountNames = Object.fromEntries(accounts.map(a => [a.account_id, a.display_name || a.institution || "未命名账户"]));
  async function updateAllMarketData() {
    if (updatingRef.current || !accounts.length) return;
    updatingRef.current = true;
    setUpdateResults(null); setError("");
    const targets = [...accounts], results = [];
    try {
      // Reuse each account's configured source and FX-before-price workflow.
      // Sequential writes also avoid competing SQLite updates and source bursts.
      for (const [index, target] of targets.entries()) {
        // Leaving this page/workspace stops dispatching further account writes.
        if (!mounted.current) return;
        const name = accountNames[target.account_id];
        setUpdating({ index: index + 1, total: targets.length, name });
        try {
          const result = await api.pullAccountMarketData(target.account_id, { data_type: "quote" });
          results.push({ account: name, status: result.status, message: result.message });
        } catch (e) {
          results.push({ account: name, status: "failed", message: e instanceof Error ? e.message : "更新失败，请稍后重试" });
        }
      }
      if (!mounted.current) return;
      setUpdateResults(results);
      // Refresh after partial success too; successful writes must remain visible.
      try {
        await onChanged();
        if (!mounted.current) return;
        const latest = await portfolioApi.overview("all");
        if (mounted.current) setPortfolio(latest);
      } catch (e) {
        if (mounted.current) setError(`市值更新已结束，页面刷新失败，请重新进入资产组合。${e instanceof Error ? e.message : ""}`);
      }
    } finally {
      updatingRef.current = false;
      if (mounted.current) setUpdating(null);
    }
  }
  const completed = updateResults?.filter(r => ["success", "empty"].includes(r.status)).length ?? 0;
  const partial = updateResults?.filter(r => r.status === "partial").length ?? 0;
  const failed = (updateResults?.length ?? 0) - completed - partial;
  async function openSupplement(need: DataNeed) {
    try {
      const initial = need.action === "opening" ? await portfolioApi.opening(need.account_id) : null;
      setSupplement({ need, opening: initial?.opening }); setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "资料读取失败"); }
  }
  async function savedSupplement() {
    setSupplement(null);
    await onChanged();
    setPortfolio(await portfolioApi.overview("all"));
  }
  async function renamed() {
    await onChanged();
    setPortfolio(await portfolioApi.overview("all"));
  }
  async function readLegacy() {
    try { const [series, holdings] = await Promise.all([api.returnSeries("all", "CNY"), api.holdingHistory("all", "")]); setLegacy({ points: series.items, holdings: holdings.items }); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "读取失败"); }
  }
  return <div className="stack">
    {error && <Alert type="error" content={error} />}
    {updateResults && <Alert type={failed || partial ? completed || partial ? "warning" : "error" : "success"} content={<div>市值更新完成：{completed} 个账户完成，{partial} 个账户部分完成，{failed} 个账户失败。<details><summary>查看各账户结果</summary>{updateResults.map((r, i) => <p key={i}>{r.account}：{r.message}</p>)}</details></div>} />}
    {portfolio && <><PortfolioPanel accountId="all" portfolio={portfolio} maskAssets={maskAssets} showAssetTable={false} onSupplement={openSupplement} actions={<Button type="primary" loading={!!updating} disabled={!accounts.length || !!updating} title={updating ? `正在更新：${updating.name}` : "按各账户的数据源配置更新全部持仓市值和汇率"} onClick={updateAllMarketData}>{updating ? `更新中 ${updating.index}/${updating.total}` : "更新全部市值"}</Button>} />
      <section className="panel stack"><div className="portfolio-toolbar"><h3>组合配置</h3><small>纳入 {portfolio.coverage.included_accounts.length} 个账户 · {portfolio.coverage.unenrolled_accounts.length} 个账户未建档</small></div>
        {!!portfolio.coverage.unenrolled_accounts.length && <small>未建档账户尚未纳入组合收益，到账户与数据确认起点后参与统计。</small>}
        {!portfolio.allocation.length && <small>暂无可用配置比例；请补齐账户起点及估值。</small>}
        <div className="portfolio-allocation">{portfolio.allocation.map(a => <div key={a.type}><span>{allocationLabels[a.type] || a.type}</span><div className="allocation-track"><i style={{ width: `${Math.min(100, Math.max(0, Number(a.weight) * 100))}%` }} /></div><strong>{percent(a.weight)}</strong></div>)}</div>
      </section>
      <section className="panel stack"><div className="portfolio-toolbar"><div><h3>当前持仓</h3><small>账户筛选仅影响本表；仓位始终以整体组合总资产为分母。</small></div><div className="portfolio-holding-filters"><Input.Search aria-label="组合持仓搜索" placeholder="名称或代码" value={keyword} onChange={setKeyword} /><Select aria-label="持仓账户筛选" value={account} onChange={setAccount} options={[{ value: "all", label: "全部账户" }, ...accounts.map(a => ({ value: a.account_id, label: accountNames[a.account_id] }))]} /></div></div>
        <AssetTable assets={filtered} onOpen={onOpen} maskAssets={maskAssets} accountNames={accountNames} showQuoteDate onRenamed={renamed} />
      </section>
    </>}
    {supplement?.opening && <OpeningEditor initial={supplement.opening} confirmed focusNeed={supplement.need} onClose={() => setSupplement(null)} onSaved={savedSupplement} />}
    {supplement && !supplement.opening && <EntryEditor accountId={supplement.need.account_id} accounts={accounts} kind="valuation" portfolio={portfolio} initialAt={supplement.need.at} initialNeed={supplement.need} onClose={() => setSupplement(null)} onSaved={savedSupplement} />}
    <div><Button onClick={readLegacy}>查看建档前来源记录</Button></div>
    {legacy && <Drawer visible title="原持仓快照与旧收益观察（来源记录）" width={1000} footer={null} onCancel={() => setLegacy(null)}><p>这些资料继续保留，不是新账目的成交、清仓利润或完整账户净值。新增业务到账户与数据记账。</p>
      <Table rowKey="id" data={legacy.holdings} pagination={{ pageSize: 8 }} columns={[{ title: "实际时间", dataIndex: "snapshot_time", render: timeLabel }, { title: "账户 / 标的", render: (_, r) => `${accountLabel(r.account_id, accountNames)} · ${r.code}` }, { title: "原数量 / 均价", render: (_, r) => maskAssets ? "••••" : `${r.quantity} / ${r.average_cost} ${r.raw_currency}` }]} />
      <Table rowKey="id" data={legacy.points} pagination={{ pageSize: 8 }} columns={[{ title: "旧观察时间", dataIndex: "observed_at", render: timeLabel }, { title: "说明", render: () => "旧持仓收益观察，不含完整现金/资金流" }]} />
    </Drawer>}
  </div>;
}
