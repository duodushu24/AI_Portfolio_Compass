import { useEffect, useRef, useState } from "react";
import { Alert, Button, Checkbox, Drawer, Modal, Select, Table, Tag } from "@arco-design/web-react";
import { portfolioApi } from "./api";
import { AssetTable, labels, numeric, timeLabel } from "./PortfolioPanel";
import { OpeningEditor } from "./PortfolioWorkbench";
import type { Opening, Portfolio, Reconciliation, SourceRecord } from "./types";
import { unitLabel } from "./assets";

export function SourceRecords({ accountId, onClose, onChanged }: {accountId: string; onClose: () => void; onChanged: () => void | Promise<void>}) {
  const [items, setItems] = useState<SourceRecord[]>([]), [enrolled, setEnrolled] = useState(false), [deleted, setDeleted] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [results, setResults] = useState<Reconciliation[] | null>(null);
  const [detail, setDetail] = useState<SourceRecord | null>(null), [book, setBook] = useState<{at: string; data: Portfolio} | null>(null);
  const [opening, setOpening] = useState<Opening | null>(null);
  const request = useRef(0);
  async function load() {
    const id = ++request.current;
    const result = await portfolioApi.sources(accountId);
    if (id === request.current) { setItems(result.items); setEnrolled(result.enrolled); }
  }
  useEffect(() => { load().catch(e => setError(String(e.message))); return () => { request.current++; }; }, [accountId]);
  const active = items.filter(i => !i.is_void && i.enabled);
  async function check(ids: number[]) {
    setBusy(true); setError("");
    try { setResults((await portfolioApi.reconcileSources(accountId, ids)).items); }
    catch (e) { setError(e instanceof Error ? e.message : "核对失败"); }
    finally { setBusy(false); }
  }
  async function update(id: number, changes: unknown) {
    setBusy(true); setError("");
    try {
      await portfolioApi.updateSource(accountId, id, changes);
      setResults(null); setDetail(null); await load(); await onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
    finally { setBusy(false); }
  }
  async function showBook(at: string) {
    setBusy(true); setError("");
    try {
      const data = await portfolioApi.overview(accountId, "", at, "records");
      setBook({at, data: {...data, records: data.records.filter(r => new Date(r.effective_at).getTime() <= new Date(at).getTime())}});
    }
    catch (e) { setError(e instanceof Error ? e.message : "当日账目读取失败"); }
    finally { setBusy(false); }
  }
  async function showOpening() {
    try { setOpening((await portfolioApi.opening(accountId)).opening); }
    catch (e) { setError(e instanceof Error ? e.message : "账户起点读取失败"); }
  }
  const title = {equal: "一致", mismatch: "存在差异", unmatched: "待确认标的", uncovered: "早于账户起点"};
  return <Drawer title="导入记录" visible width={1100} onCancel={onClose} footer={null}>
    <div className="stack">
      <p>这里保存持仓来源资料。账户起点及买卖记录在“账户记账”查看；原始文件未保存在此处。</p>
      {!enrolled && <Alert type="info" content="账户尚未建档。删除或恢复资料会影响待确认持仓；确认账户起点后才能核对账目。" />}
      {error && <Alert type="error" content={error} />}
      <div className="inline-actions"><Checkbox checked={deleted} onChange={setDeleted}>查看已删除</Checkbox><Button disabled={!enrolled || !active.length || active.length > 1000 || busy} loading={busy} onClick={() => check(active.map(r => r.id))}>核对全部有效资料</Button>{active.length > 1000 && <small>资料超过 1000 条，请逐条核对。</small>}</div>
      <Table rowKey="id" pagination={{pageSize: 8}} scroll={{x: 1000}} data={items.filter(i => i.is_void === deleted)} columns={[
        {title: "标的", width: 190, render: (_, r: SourceRecord) => <div className="portfolio-asset-cell"><strong>{r.name || r.code}</strong><small>{r.code}</small></div>},
        {title: "来源", dataIndex: "source", width: 100},
        {title: "资料日期", width: 165, render: (_, r: SourceRecord) => timeLabel(r.source_at)},
        {title: "数量", width: 105, render: (_, r: SourceRecord) => `${numeric(r.quantity)} ${r.unit ? unitLabel(r.unit) : ""}`},
        {title: "核对状态", width: 100, render: (_, r: SourceRecord) => r.enabled ? "用于核对" : "不用于核对"},
        {title: "操作", width: 310, render: (_, r: SourceRecord) => <div className="inline-actions">
          <Button size="mini" onClick={() => setDetail(r)}>详情</Button>
          {r.is_void ? <Button size="mini" disabled={busy} onClick={() => update(r.id, {is_void: false})}>恢复</Button> : <>
            <Button size="mini" disabled={busy || !enrolled || !r.enabled} onClick={() => check([r.id])}>核对</Button>
            <Button size="mini" disabled={busy} onClick={() => update(r.id, {enabled: !r.enabled})}>{r.enabled ? "停止核对" : "恢复核对"}</Button>
            <Button size="mini" status="danger" disabled={busy} onClick={() => Modal.confirm({title: "删除这条导入资料？", content: enrolled ? "仅移入已删除，可恢复；不会改变正式持仓、现金、成本或收益。" : "将影响尚未建档的待确认持仓，可在已删除中恢复。", onOk: () => update(r.id, {is_void: true})})}>删除</Button>
          </>}
        </div>},
      ]} />
      {results && <><h4>核对结果</h4>{!results.length && <p>没有可核对的有效资料。</p>}<Table rowKey={r => `${r.source_id ?? r.code}:${r.source_at}`} pagination={{pageSize: 8}} scroll={{x: 960}} data={results} columns={[
        {title: "标的／资料日期", width: 215, render: (_, r: Reconciliation) => <div className="portfolio-asset-cell"><strong>{r.name || r.code}</strong><small>{r.code}</small><small>{timeLabel(r.source_at)}</small></div>},
        {title: "导入数量", width: 100, render: (_, r: Reconciliation) => numeric(r.source_quantity)},
        {title: "当时账目数量", width: 110, render: (_, r: Reconciliation) => numeric(r.ledger_quantity)},
        {title: "结果", width: 250, render: (_, r: Reconciliation) => <div><Tag color={r.status === "equal" ? "green" : r.status === "mismatch" ? "orange" : "gray"}>{title[r.status]}</Tag><p>{r.reason}</p>{r.source_average_cost != null && r.ledger_average_cost != null && <small>成本价：导入 {numeric(r.source_average_cost)}／账目 {numeric(r.ledger_average_cost)} {r.currency}</small>}</div>},
        {title: "处理", width: 295, render: (_, r: Reconciliation) => <div className="stack">
          {r.status === "unmatched" && !!r.candidates?.length && <Select aria-label={`确认${r.name || r.code}对应标的`} placeholder="确认对应标的" options={r.candidates.map(p => ({value: JSON.stringify({code: p.code, currency: p.currency, unit: p.unit}), label: `${p.name} · ${p.code} · ${unitLabel(p.unit)}`}))} onChange={v => Modal.confirm({title: "确认用此标的核对？", content: "仅建立核对对应关系，数量按原值比较，不做单位换算，不修改正式账目。", onOk: () => r.source_id ? update(r.source_id, {match: JSON.parse(v)}) : undefined})} />}
          {r.status !== "equal" && <div className="inline-actions"><Button size="mini" disabled={busy} onClick={() => showBook(r.source_at)}>查看当日账目</Button><Button size="mini" onClick={showOpening}>账户起点</Button>{r.source_id != null && <Button size="mini" disabled={busy} onClick={() => update(r.source_id!, {enabled: false})}>不再用于核对</Button>}</div>}
        </div>},
      ]} /></>}
    </div>
    {detail && <Drawer title="导入资料详情" visible width={620} onCancel={() => setDetail(null)} footer={null}><div className="stack"><strong>{detail.name} · {detail.code}</strong><p>来源：{detail.source}</p><p>资料时间：{timeLabel(detail.source_at)}</p><p>导入时间：{detail.imported_at ? timeLabel(detail.imported_at) : "未记录"}</p><p>数量：{numeric(detail.quantity)} {detail.unit ? unitLabel(detail.unit) : "单位未记录"}</p><p>价格：{numeric(detail.price)} {detail.currency}</p><p>成本价：{numeric(detail.average_cost)}{detail.average_cost == null ? "（成本口径未确认）" : ` ${detail.currency}`}</p>{detail.match && <p>核对对应：{detail.match.code} · {detail.match.currency} · {unitLabel(detail.match.unit)} <Button size="mini" disabled={busy} onClick={() => update(detail.id, {match: null})}>清除对应关系</Button></p>}</div></Drawer>}
    {book && <Drawer title={`当日账目 · ${timeLabel(book.at)}`} visible width={1100} onCancel={() => setBook(null)} footer={null}><div className="stack"><AssetTable assets={book.data.current?.positions ?? []} asOf={book.at} showQuoteDate /><h4>截至此时的账目</h4><Table rowKey={r => `${r.category}:${r.id}`} pagination={{pageSize: 8}} data={book.data.records} columns={[{title: "发生时间", dataIndex: "effective_at", render: timeLabel}, {title: "事项", render: (_, r) => `${labels[r.kind] || r.kind}${r.is_void ? "（已作废）" : ""}`}, {title: "内容", render: (_, r) => `${r.data.name || r.data.code || ""} ${r.data.quantity || r.data.amount || ""}`}]} /></div></Drawer>}
    {opening && <OpeningEditor initial={opening} confirmed onClose={() => setOpening(null)} onSaved={async () => {setOpening(null); setBook(null); setResults(null); await load(); await onChanged();}} />}
  </Drawer>;
}
