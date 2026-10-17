import { assetOptions, assetUnit, goldCode, priceUnit, unitLabel } from "./assets";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Alert, Button, Checkbox, Drawer, Modal, Select, Table } from "@arco-design/web-react";
import type { AccountSummary } from "../../api";
import { portfolioApi } from "./api";
import { accountLabel, labels, numeric, timeLabel } from "./PortfolioPanel";
import type { HistoryEntry, HistoryPreview, Opening, OpeningAsset, Portfolio, Reconciliation, RecordItem } from "./types";

const local = (v?: string | null) => { const d = v ? new Date(v) : new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19); };
const utc = (v: string) => new Date(v).toISOString();
const currencies = ["CNY", "HKD", "USD"];
const emptyAsset = (): OpeningAsset => ({ code: "", name: "", market: "CN", currency: "CNY", asset_type: "stock", unit: "share", quantity: "", average_cost: null, price: null });
type Fields = Record<string, string>;
function Field({ title, value, onChange, type = "text", options }: { title: string; value: string | null | undefined; onChange: (v: string) => void; type?: string; options?: Array<{ value: string; label: string }> }) {
  return <label>{title}{options ? <select aria-label={title} value={value ?? ""} onChange={e => onChange(e.target.value)}>{options.map(o => <option value={o.value} key={o.value}>{o.label}</option>)}</select> : <input aria-label={title} type={type} step={type === "datetime-local" ? "1" : "any"} value={value ?? ""} onChange={e => onChange(e.target.value)} />}</label>;
}
const options = (values: string[]) => values.map(value => ({ value, label: value }));
const marketOptions = [{ value: "CN", label: "境内市场" }, { value: "HK", label: "港股" }, { value: "US", label: "美股" }];
function FxFields({ values, setValues }: { values: Fields; setValues: (values: Fields) => void }) {
  return <details><summary>汇率（外币 → CNY；不填写则沿用历史有效值）</summary><div className="portfolio-fields">{["HKD", "USD"].map(c => <div key={c}><Field title={`${c}/CNY 汇率`} type="number" value={values[c]} onChange={v => setValues({ ...values, [c]: v })} /><Field title={`${c} 汇率实际时间（默认记录时间）`} type="datetime-local" value={values[`${c}_at`]} onChange={v => setValues({ ...values, [`${c}_at`]: v })} /></div>)}</div></details>;
}
function fxPayload(values: Fields, at: string) { return Object.fromEntries(Object.entries(values).filter(([c, v]) => currencies.includes(c) && v !== "").map(([c, rate]) => [c, { rate, at: utc(values[`${c}_at`] || at), source: "手工确认" }])); }

export function PortfolioWorkbench({ accountId, accounts, onChanged, onSelectAccount, revision = 0 }: { accountId: string; accounts: AccountSummary[]; onChanged: () => Promise<void>; onSelectAccount: (id: string) => void; revision?: number }) {
  const [data, setData] = useState<Portfolio | null>(null), [error, setError] = useState("");
  const [opening, setOpening] = useState<{ confirmed: boolean; opening: Opening } | null>(null), [reconciliation, setReconciliation] = useState<Reconciliation[]>([]);
  const [editor, setEditor] = useState<{ kind: string; record?: RecordItem } | null>(null);
  const request = useRef(0);
  async function reload() {
    const id = ++request.current;
    try {
      const [result, initial] = await Promise.all([portfolioApi.overview(accountId), portfolioApi.opening(accountId)]);
      if (id === request.current) { setData(result); setOpening(initial); setReconciliation(initial.reconciliation); setError(""); }
    } catch (e) { if (id === request.current) setError(e instanceof Error ? e.message : "读取失败"); }
  }
  useEffect(() => { setEditor(null); }, [accountId]);
  useEffect(() => { setData(null); setOpening(null); void reload(); return () => { request.current++; }; }, [accountId, revision]);
  async function saved() { setEditor(null); await onChanged(); }
  const confirmed = !!opening?.confirmed;
  const accountNames = Object.fromEntries(accounts.map(a => [a.account_id, a.display_name || a.institution || "未命名账户"]));
  return <div className="stack">
    <section className="panel stack"><div className="portfolio-toolbar"><div><h3>账户记账</h3><small>{confirmed ? "买卖自动维护成本和现金；更新市值自动保存收益点。" : "从首笔交易前的现金开始，或确认已有持仓作为统计起点。"}</small></div><Select aria-label="记账账户" value={accountId} options={accounts.map(a => ({ value: a.account_id, label: accountLabel(a.account_id, accountNames) }))} onChange={onSelectAccount} /><div className="inline-actions"><Button onClick={() => setEditor({ kind: "opening" })} disabled={!opening}>{confirmed ? "期初资料 / 纠错" : "设置账户起点"}</Button><Button type="primary" disabled={!confirmed} onClick={() => setEditor({ kind: "trade" })}>记录买卖</Button><Button disabled={!confirmed} onClick={() => setEditor({ kind: "funds" })}>记录资金</Button><Button disabled={!confirmed} onClick={() => setEditor({ kind: "valuation" })}>更新市值</Button>{confirmed && <Button onClick={() => setEditor({ kind: "history" })}>补录更早历史</Button>}</div></div>
      {error && <Alert type="error" content={error} />}
      {!!reconciliation.length && <Alert type={reconciliation.some(d => d.status === "mismatch") ? "warning" : "info"} content={<details><summary>{reconciliation.some(d => d.status === "mismatch") ? "来源资料与同一时点账目存在差异" : "部分来源日期尚未纳入统计范围"}</summary>{reconciliation.map(d => <p key={`${d.code}:${d.currency}:${d.source_at}`}>{d.code} · {timeLabel(d.source_at)} · {d.reason}{d.status === "mismatch" && <>；数量 {d.source_quantity} / {d.ledger_quantity}；平均成本 {numeric(d.source_average_cost)} / {numeric(d.ledger_average_cost)} {d.currency}（来源 / 同时点账目）</>}</p>)}<p>核对只比较相同日期；旧来源资料保留，不覆盖自动账目。</p></details>} />}
      {confirmed && <Table rowKey={r => `${r.category}:${r.id}`} data={data?.records ?? []} pagination={{ pageSize: 8 }} scroll={{ x: 900 }} columns={[
        { title: "实际时间", dataIndex: "effective_at", render: timeLabel }, { title: "事项", render: (_, r: RecordItem) => `${labels[r.kind]}${r.is_void ? "（已作废）" : ""}` },
        { title: "内容", render: (_, r: RecordItem) => r.kind === "trade" ? `${r.data.code} · ${r.data.side === "BUY" ? "买入" : "卖出"} ${r.data.quantity} × ${r.data.price} · 费用 ${r.data.fees} ${r.data.currency}` : r.kind === "valuation" ? "价格 / 净值 / 汇率更新" : `${r.data.amount ?? ""} ${r.data.currency ?? ""}${r.data.to_account_id ? ` → ${accountLabel(String(r.data.to_account_id), accountNames)}` : ""} · ${r.data.note ?? ""}` },
        { title: "操作", render: (_, r: RecordItem) => <div className="inline-actions"><Button size="small" onClick={() => setEditor({ kind: r.kind === "trade" ? "trade" : r.kind === "valuation" ? "valuation" : "funds", record: r })}>纠错{r.is_void ? " / 恢复" : ""}</Button>{!r.is_void && <Button size="small" status="danger" onClick={() => Modal.confirm({ title: "作废错误账目？", content: "此操作会重算后续账目，不能替代实际卖出。有关联或导致现金、数量不足时会拒绝并保留原记录。", onOk: async () => { try { await portfolioApi.void(r.category, r.id); await saved(); } catch (e) { setError(e instanceof Error ? e.message : "作废失败"); throw e; } } })}>作废</Button>}</div> },
      ]} />}
    </section>
    {editor?.kind === "opening" && opening && <OpeningEditor initial={opening.opening} confirmed={confirmed} onClose={() => setEditor(null)} onSaved={saved} />}
    {editor?.kind === "history" && opening && <HistoryEditor initial={opening.opening} accounts={accounts} portfolio={data} onClose={() => setEditor(null)} onSaved={saved} />}
    {editor && !["opening", "history"].includes(editor.kind) && <EntryEditor key={`${accountId}:${editor.kind}:${editor.record?.id || "new"}`} accountId={accountId} accounts={accounts} kind={editor.kind} record={editor.record} portfolio={data} onClose={() => setEditor(null)} onSaved={saved} />}
  </div>;
}

function EditorShell({ title, onClose, error, saving, onSave, children, saveText = "确认保存" }: { title: string; onClose: () => void; error: string; saving: boolean; onSave: () => Promise<void>; children: ReactNode; saveText?: string }) {
  return <Drawer title={title} visible width={1050} onCancel={onClose} footer={<div className="inline-actions"><Button onClick={onClose}>取消</Button><Button type="primary" loading={saving} onClick={onSave}>{saveText}</Button></div>}><div className="portfolio-form">{error && <Alert type="error" content={error} />}{children}</div></Drawer>;
}

function OpeningEditor({ initial, confirmed, onClose, onSaved }: { initial: Opening; confirmed: boolean; onClose: () => void; onSaved: () => Promise<void> }) {
  const [mode, setMode] = useState(confirmed ? "snapshot" : "transactions");
  const [at, setAt] = useState(local(initial.effective_at)), [included, setIncluded] = useState(initial.included), [includedAt, setIncludedAt] = useState(initial.included_at ? local(initial.included_at) : ""), [excludedAt, setExcludedAt] = useState(initial.excluded_at ? local(initial.excluded_at) : "");
  const [positions, setPositions] = useState(confirmed ? initial.positions : []), [cash, setCash] = useState<Record<string, string>>(confirmed ? initial.cash : {}), [fx, setFx] = useState<Fields>(confirmed ? Object.fromEntries(Object.entries(initial.fx).flatMap(([c, v]) => [[c, v.rate], [`${c}_at`, local(v.at)]])) : {});
  const [error, setError] = useState(""), [saving, setSaving] = useState(false);
  const update = (index: number, change: Partial<OpeningAsset>) => setPositions(rows => rows.map((r, i) => i === index ? { ...r, ...change } : r));
  async function save() {
    setSaving(true); setError("");
    try { await portfolioApi.saveOpening(initial.account_id, { effective_at: utc(at), included, included_at: includedAt ? utc(includedAt) : null, excluded_at: excludedAt ? utc(excludedAt) : null, positions: positions.map(p => ({ ...p, price_at: p.price_at || utc(at) })), cash: Object.fromEntries(Object.entries(cash).filter(([, v]) => v !== "")), liabilities: mode === "snapshot" ? initial.liabilities || {} : {}, fx: fxPayload(fx, at), source: mode === "transactions" ? "首笔交易前的账户起点" : initial.source || "用户确认" }, confirmed); await onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : "保存失败"); } finally { setSaving(false); }
  }
  return <EditorShell title={confirmed ? "期初资料与组合范围纠错" : "确认账户期初"} onClose={onClose} error={error} saving={saving} onSave={save}>
    {!confirmed && <Field title="录入方式" value={mode} options={[{ value: "transactions", label: "从首笔交易开始（推荐）" }, { value: "snapshot", label: "从已有持仓开始" }]} onChange={value => { setMode(value); setPositions(value === "snapshot" ? initial.positions : []); setCash(value === "snapshot" ? initial.cash : {}); setFx(value === "snapshot" ? Object.fromEntries(Object.entries(initial.fx).map(([c, v]) => [c, v.rate])) : {}); }} />}
    <p>{mode === "transactions" ? "起点设在首笔交易之前，填写当时真实现金；也可从零现金开始，再记录首笔入金。保存后逐笔记录买卖，首次成交价自动作为初始报价，手续费进入平均成本。不要重复填写同一笔买入的期初持仓。" : "期初资产作为统计区间起点；原币平均成本用于持仓和卖出盈亏。已有持仓的价格填写当时报价，不以成本伪造市场价格。成本未知可以留空。"}</p>
    <div className="portfolio-fields"><Field title="期初实际时间" type="datetime-local" value={at} onChange={setAt} /><Field title="纳入组合时间（默认期初）" type="datetime-local" value={includedAt} onChange={setIncludedAt} /><Field title="移出组合时间（可留空）" type="datetime-local" value={excludedAt} onChange={setExcludedAt} /></div>
    <Checkbox checked={included} onChange={setIncluded}>纳入全账户收益范围（与账户同步启用开关无关）</Checkbox>
    <fieldset><legend>期初各币种现金（实际可用余额）</legend><div className="portfolio-fields">{currencies.map(c => <Field key={c} title={`${c} 现金`} type="number" value={cash[c] ?? ""} onChange={v => setCash({ ...cash, [c]: v })} />)}</div></fieldset>
    <small>银行黄金请在名称中写明银行及产品，按克和元／克填写；不同产品分别添加，已有产品后续通过买卖维护。</small>
    {positions.map((p, i) => <fieldset key={i}><legend>期初持仓 {i + 1}</legend><div className="portfolio-fields portfolio-opening-row">
      {p.asset_type !== "precious_metal" && <Field title="标的代码" value={p.code} onChange={code => update(i, { code })} />}<Field title="标的名称" value={p.name} onChange={name => update(i, { name })} />
      <Field title="市场" value={p.market} options={marketOptions} onChange={market => update(i, { market })} /><Field title="币种" value={p.currency} options={options(currencies)} onChange={currency => update(i, { currency })} />
      <Field title="资产类型" value={p.asset_type} options={assetOptions} onChange={asset_type => update(i, { asset_type, unit: assetUnit(asset_type), ...(asset_type === "precious_metal" ? { code: goldCode(), market: "CN", currency: "CNY" } : {}) })} />
      <Field title={`期初数量（${unitLabel(p.unit)}）`} type="number" value={p.quantity} onChange={quantity => update(i, { quantity })} /><Field title={`平均成本（${priceUnit(p.currency, p.unit)}，未知留空）`} type="number" value={p.average_cost} onChange={v => update(i, { average_cost: v || null })} /><Field title={`期初价格（${priceUnit(p.currency, p.unit)}）`} type="number" value={p.price} onChange={v => update(i, { price: v || null })} />
      <Field title="实际报价时间" type="datetime-local" value={p.price_at ? local(p.price_at) : at} onChange={v => update(i, { price_at: v ? utc(v) : undefined })} />
      {p.currency !== "CNY" && <Field title="历史人民币剩余成本（有依据才填）" type="number" value={p.cost_cny_amount} onChange={v => update(i, { cost_cny_amount: v || null })} />}
    </div><Button status="danger" size="small" onClick={() => setPositions(rows => rows.filter((_, j) => i !== j))}>移除此期初行</Button></fieldset>)}
    {mode === "snapshot" && <Button onClick={() => setPositions(rows => [...rows, emptyAsset()])}>添加期初持仓</Button>}<FxFields values={fx} setValues={setFx} />
    {confirmed && <Alert type="warning" content="纠错会重算建档后的成本、现金和收益。日常买卖请返回记录买卖；增减本金请记录资金。" />}
  </EditorShell>;
}

function HistoryEditor({ initial, accounts, portfolio, onClose, onSaved }: { initial: Opening; accounts: AccountSummary[]; portfolio: Portfolio | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const [at, setAt] = useState(""), [cash, setCash] = useState<Fields>({}), [fx, setFx] = useState<Fields>({});
  const [entries, setEntries] = useState<HistoryEntry[]>([]), [editing, setEditing] = useState<{ kind: string; index?: number } | null>(null);
  const [preview, setPreview] = useState<HistoryPreview | null>(null), [acknowledged, setAcknowledged] = useState(false), [error, setError] = useState(""), [saving, setSaving] = useState(false);
  useEffect(() => { setPreview(null); setAcknowledged(false); }, [at, cash, fx, entries]);
  const payload = () => ({ opening: { effective_at: utc(at), cash: Object.fromEntries(Object.entries(cash).filter(([, v]) => v !== "")), fx: fxPayload(fx, at) }, records: entries, confirm_differences: acknowledged });
  async function calculate() {
    setSaving(true); setError("");
    try { setPreview(await portfolioApi.previewHistory(initial.account_id, payload())); }
    catch (e) { setPreview(null); setError(e instanceof Error ? e.message : "试算失败"); }
    finally { setSaving(false); }
  }
  async function save() {
    if (!preview || preview.differences.length && !acknowledged) { setError("请先完成试算，核对原起点差异后再保存"); return; }
    setSaving(true); setError("");
    try { await portfolioApi.saveHistory(initial.account_id, payload()); await onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
    finally { setSaving(false); }
  }
  const selected = editing?.index == null ? undefined : entries[editing.index];
  const record: RecordItem | undefined = selected ? { id: editing!.index!, account_id: initial.account_id, category: selected.kind === "trade" ? "trade" : "event", is_void: false, ...selected } : undefined;
  return <EditorShell title="补录更早历史" onClose={onClose} error={error} saving={saving} onSave={save}>
    <p>原统计起点：{timeLabel(initial.effective_at)}。从更早的首笔交易前开始，填写当时现金并添加截至原起点的历史记录。试算不会保存；确认后统一替换起点并补录交易，原起点资料保留用于核对，不重复计入持仓。</p>
    <Field title="新起点实际时间" type="datetime-local" value={at} onChange={setAt} />
    <fieldset><legend>新起点现金（可全为零，再添加入金记录）</legend><div className="portfolio-fields">{currencies.map(c => <Field key={c} title={`${c} 现金`} type="number" value={cash[c]} onChange={v => setCash({ ...cash, [c]: v })} />)}</div></fieldset>
    <FxFields values={fx} setValues={setFx} />
    <div className="inline-actions"><Button disabled={!at || saving} onClick={() => setEditing({ kind: "trade" })}>添加历史买卖</Button><Button disabled={!at || saving} onClick={() => setEditing({ kind: "funds" })}>添加历史资金</Button></div>
    <Table rowKey="index" pagination={false} data={entries.map((e, index) => ({ ...e, index }))} columns={[
      { title: "实际时间", dataIndex: "effective_at", render: timeLabel }, { title: "事项", render: (_, r) => labels[r.kind] },
      { title: "内容", render: (_, r) => r.kind === "trade" ? `${r.data.code} · ${r.data.side === "BUY" ? "买入" : "卖出"} ${r.data.quantity} × ${r.data.price} · 费用 ${r.data.fees} ${r.data.currency}` : `${r.data.amount ?? ""} ${r.data.currency ?? ""}` },
      { title: "操作", render: (_, r) => <div className="inline-actions"><Button disabled={saving} onClick={() => setEditing({ kind: r.kind === "trade" ? "trade" : "funds", index: r.index })}>修改</Button><Button disabled={saving} status="danger" onClick={() => setEntries(rows => rows.filter((_, i) => i !== r.index))}>移除</Button></div> },
    ]} />
    <Button type="primary" loading={saving} disabled={!at || !entries.length} onClick={calculate}>试算并核对原起点</Button>
    {preview && <><Alert type={preview.differences.length ? "warning" : "success"} content={preview.differences.length ? "补录后的原起点数量、成本或现金存在差异，请核对记录。" : "原起点数量、已知成本及现金核对一致，可以确认保存。"} />
      <p>补录 {preview.record_count} 条 · 当前总资产 {numeric(preview.current.total_assets)} CNY · 累计账户盈亏 {numeric(preview.current.profit)} CNY</p>
      {preview.differences.length > 0 && <><Table rowKey="item" pagination={false} data={preview.differences} columns={[{ title: "核对项目", dataIndex: "item" }, { title: "原资料", dataIndex: "before" }, { title: "补录结果", dataIndex: "after" }]} /><Checkbox checked={acknowledged} onChange={setAcknowledged}>已核对差异，确认以本次历史记录重建账目（不会自动补造现金或交易）</Checkbox></>}
      {!!(preview.current.issues.length + preview.current.performance_issues.length) && <Alert type="warning" content={[...preview.current.issues, ...preview.current.performance_issues].join("；")} />}
    </>}
    {editing && <EntryEditor accountId={initial.account_id} accounts={accounts.filter(a => a.account_id === initial.account_id)} kind={editing.kind} record={record} portfolio={portfolio} initialAt={at ? utc(at) : undefined} onClose={() => setEditing(null)} onSaved={async () => {}} onStage={entry => { setEntries(rows => editing.index == null ? [...rows, entry] : rows.map((r, i) => i === editing.index ? entry : r)); setEditing(null); }} />}
  </EditorShell>;
}

function EntryEditor({ accountId, accounts, kind, record, portfolio, onClose, onSaved, onStage, initialAt }: { accountId: string; accounts: AccountSummary[]; kind: string; record?: RecordItem; portfolio: Portfolio | null; onClose: () => void; onSaved: () => Promise<void>; onStage?: (entry: HistoryEntry) => void; initialAt?: string }) {
  const d = record?.data || {}, [at, setAt] = useState(local(record?.effective_at || initialAt));
  const [aid, setAid] = useState(record?.account_id || accountId), [fields, setFields] = useState<Fields>({ ...Object.fromEntries(Object.entries(d).filter(([, v]) => typeof v !== "object").map(([k, v]) => [k, String(v ?? "")])), code: String(d.code || ""), market: String(d.market || "CN"), currency: String(d.currency || "CNY"), asset_type: String(d.asset_type || "stock"), unit: String(d.unit || assetUnit(String(d.asset_type || "stock"))), side: String(d.side || "BUY"), fees: String(d.fees || "0"), settlement: String(d.settlement || "cash"), amount: String(d.amount || ""), to_currency: String(d.to_currency || "USD") });
  const rates = (d.fx || {}) as Record<string, { rate: string; at: string }>;
  const [fundKind, setFundKind] = useState(record?.kind || "deposit"), [fx, setFx] = useState<Fields>(Object.fromEntries(Object.entries(rates).flatMap(([c, v]) => [[c, v.rate], [`${c}_at`, local(v.at)]]))), [error, setError] = useState(""), [saving, setSaving] = useState(false);
  type PriceRow = OpeningAsset & { at: string; source: string; price_kind: string; input_mode: string; input_value: string };
  const [prices, setPrices] = useState<PriceRow[]>([]), [loadedAt, setLoadedAt] = useState("");
  const [context, setContext] = useState(portfolio);
  useEffect(() => { let cancelled = false; portfolioApi.overview(aid).then(result => { if (!cancelled) setContext(result); }).catch(e => { if (!cancelled) setError(String(e.message)); }); return () => { cancelled = true; }; }, [aid]);
  const request = useRef(0);
  const set = (name: string, value: string) => setFields(f => ({ ...f, [name]: value }));
  const assets = context?.current?.positions ?? [];
  useEffect(() => {
    if (kind !== "valuation") return;
    if (record) {
      const rows = (d.prices || []) as Array<OpeningAsset & { at: string; source: string; price_kind: string }>;
      setPrices(rows.map(p => ({ ...p, input_mode: "price", input_value: String(p.price ?? "") })));
      const rates = (d.fx || {}) as Record<string, { rate: string }>;
      setLoadedAt(at); return;
    }
    const id = ++request.current;
    portfolioApi.overview(aid, "", utc(at)).then(result => {
      if (id !== request.current) return;
      setPrices((result.current?.positions ?? []).filter(p => Number(p.quantity) > 0).map(p => ({ ...p, average_cost: p.average_cost, price: p.price, quantity: p.quantity, at: utc(at), source: p.asset_type === "precious_metal" ? "手工银行报价" : "手工", price_kind: p.asset_type === "precious_metal" ? "redemption" : p.asset_type === "fund" ? "nav" : "price", input_mode: "price", input_value: "" })));
      setLoadedAt(at); setError("");
    }).catch(e => { if (id === request.current) setError(String(e.message)); });
    return () => { request.current++; };
  }, [aid, at, kind]);
  const changePrice = (i: number, change: Partial<PriceRow>) => setPrices(rows => rows.map((r, j) => i === j ? { ...r, ...change } : r));
  async function save() {
    setSaving(true); setError("");
    try {
      const effective_at = utc(at), rates = fxPayload(fx, at);
      if (kind === "trade") {
        if (onStage) onStage({ kind: "trade", effective_at, data: { ...fields, fx: rates } });
        else await portfolioApi.saveTrade({ ...fields, account_id: aid, effective_at, fx: rates }, record?.id);
      }
      else if (kind === "valuation") {
        if (!record && loadedAt !== at) throw new Error("正在读取该实际时点持仓，请稍后保存");
        await portfolioApi.saveEvent({ kind: "valuation", account_id: aid, effective_at, data: { prices: prices.filter(p => p.input_value !== "").map(p => ({ ...p, price: p.input_mode === "price" ? p.input_value : undefined, market_value: p.input_mode === "market_value" ? p.input_value : undefined })), fx: rates, note: fields.note || "" } }, record?.id);
      } else if (onStage) onStage({ kind: fundKind, effective_at, data: { ...fields, fx: rates } });
      else await portfolioApi.saveEvent({ kind: fundKind, account_id: aid, effective_at, data: { ...fields, fx: rates } }, record?.id);
      await onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); } finally { setSaving(false); }
  }
  return <EditorShell title={`${record ? "纠错 / 恢复 · " : ""}${kind === "trade" ? "记录买卖" : kind === "valuation" ? "更新市值" : "记录资金"}`} onClose={onClose} error={error} saving={saving} onSave={save} saveText={onStage ? "加入本批" : "确认保存"}>
    <div className="portfolio-fields"><Field title="账户" value={aid} options={accounts.map(a => ({ value: a.account_id, label: a.display_name || a.institution || "未命名账户" }))} onChange={setAid} /><Field title="实际发生时间" type="datetime-local" value={at} onChange={setAt} /></div>
    {kind === "trade" ? <>
      <Field title="选择现有标的（新标的直接填写下方）" value="" options={[{ value: "", label: "选择标的 / 新标的" }, ...assets.filter(a => a.account_id === aid).map(a => ({ value: `${a.code}:${a.currency}:${a.unit}`, label: `${a.name} · ${a.code} · ${a.quantity} ${unitLabel(a.unit)} · ${a.currency}` }))]} onChange={v => { const a = assets.find(p => `${p.code}:${p.currency}:${p.unit}` === v); if (a) setFields(f => ({ ...f, code: a.code, name: a.name, market: a.market, currency: a.currency, asset_type: a.asset_type, unit: a.unit })); }} />
      <div className="portfolio-fields"><Field title="买卖方向" value={fields.side} options={[{ value: "BUY", label: "买入" }, { value: "SELL", label: "卖出" }]} onChange={v => set("side", v)} />
      {[ ...(fields.asset_type === "precious_metal" ? [] : [["code", "标的代码"]]), ["name", "标的名称"] ].map(([key, title]) => <Field key={key} title={title} value={fields[key]} onChange={v => set(key, v)} />)}
      <Field title="市场" value={fields.market} options={marketOptions} onChange={v => set("market", v)} /><Field title="币种" value={fields.currency} options={options(currencies)} onChange={v => set("currency", v)} /><Field title="资产类型" value={fields.asset_type} options={assetOptions} onChange={v => setFields(f => ({ ...f, asset_type: v, unit: assetUnit(v), ...(v === "precious_metal" ? { code: goldCode(), market: "CN", currency: "CNY" } : {}) }))} />
      {[ ["quantity", `成交数量（${unitLabel(fields.unit)}）`], ["price", `成交价格（${priceUnit(fields.currency, fields.unit)}）`], ["fees", "总费用（含佣金税费）"] ].map(([key, title]) => <Field key={key} title={title} type="number" value={fields[key]} onChange={v => set(key, v)} />)}</div>
      {fields.side === "SELL" && <>{!onStage && <Button onClick={() => { const a = assets.find(p => p.code === fields.code && p.currency === fields.currency && p.unit === fields.unit); if (a) set("quantity", a.quantity); }}>卖出全部当前持仓</Button>}<Field title="资金结算" value={fields.settlement} options={[{ value: "cash", label: "现金已到账" }, { value: "pending", label: "已确认赎回，资金待到账" }]} onChange={v => set("settlement", v)} /></>}
      {fields.side === "BUY" && <Field title="关联待确认申购（普通买入留空）" value={fields.pending_id || ""} options={[{ value: "", label: "普通现金买入" }, ...(context?.current?.pending ?? []).filter(p => p.kind === "subscription").map(p => ({ value: p.pending_id, label: `${p.pending_id} · ${p.amount} ${p.currency}` }))]} onChange={v => set("pending_id", v)} />}
      {fields.asset_type === "precious_metal" && <p>请填写银行及产品名称；每个新产品自动分配独立标识。再次买卖请选择已有产品。资金按真实入金或转账记录，买入扣减账户现金。初始成交价不代表银行可赎回价，之后请更新银行报价。</p>}
      <small>首次买入的成交价自动作为初始报价，费用进入平均成本；成交同时更新数量、成本和现金。分红再投资先记分红收入，再记录买入。</small>
    </> : kind === "valuation" ? <>
      <p>银行黄金优先填银行赎回 / 回购价，或银行展示市值，并核对报价来源与时间。只填本次更新的标的；其余沿用最近有效报价并标注日期。价格和市值任选一种。此报价也用于其他账户的同一标的、币种和单位。</p>
      {!prices.length && <p>此时点没有持仓；仍可单独更新外币现金的汇率。</p>}
      {prices.map((p, i) => <fieldset key={`${p.code}:${p.currency}:${p.unit}`}><legend>{p.name || p.code} · {p.code} · 数量 {numeric(p.quantity)} {unitLabel(p.unit)} · {p.currency}</legend><div className="portfolio-fields">
        <Field title="输入方式" value={p.input_mode} options={[{ value: "price", label: `单位价格（${priceUnit(p.currency, p.unit)}）` }, { value: "market_value", label: "此标的总市值" }]} onChange={input_mode => changePrice(i, { input_mode, ...(p.asset_type === "precious_metal" ? { price_kind: input_mode === "market_value" ? "bank_value" : "redemption" } : {}) })} /><Field title="本次更新值" type="number" value={p.input_value} onChange={input_value => changePrice(i, { input_value })} /><Field title="实际价格时间" type="datetime-local" value={local(p.at)} onChange={v => changePrice(i, { at: utc(v) })} />
        <Field title="报价类型" value={p.price_kind} options={[...(p.asset_type === "precious_metal" ? [{ value: "redemption", label: "银行赎回 / 回购价" }, { value: "bank_value", label: "银行展示市值" }] : []), { value: "price", label: "市场价格" }, { value: "nav", label: "正式单位净值" }, { value: "estimate", label: "估算价格 / 净值" }]} onChange={price_kind => changePrice(i, { price_kind })} /><Field title="报价来源" value={p.source} onChange={source => changePrice(i, { source })} />
      </div><small>上次价格 {numeric(p.price)} {priceUnit(p.currency, p.unit)}；留空表示本次不更新。</small></fieldset>)}
    </> : <>
      <Field title="资金 / 调整类型" value={fundKind} options={Object.entries(labels).filter(([k]) => !["opening", "include", "exclude", "trade", "valuation"].includes(k)).map(([value, label]) => ({ value, label }))} onChange={setFundKind} />
      <div className="portfolio-fields"><Field title="币种" value={fields.currency} options={options(currencies)} onChange={v => set("currency", v)} />
      {!["settle", "cancel_subscription", "split", "position_transfer"].includes(fundKind) && <><Field title="金额（正数）" type="number" value={fields.amount} onChange={v => set("amount", v)} /><Field title="独立手续费" type="number" value={fields.fees} onChange={v => set("fees", v)} /></>}
      {["transfer", "position_transfer"].includes(fundKind) && <Field title="转入账户" value={fields.to_account_id || ""} options={[{ value: "", label: "请选择" }, ...accounts.filter(a => a.account_id !== aid).map(a => ({ value: a.account_id, label: a.display_name || a.institution || "未命名账户" }))]} onChange={v => set("to_account_id", v)} />}
      {fundKind === "fx" && <><Field title="换入币种" value={fields.to_currency} options={options(currencies)} onChange={v => set("to_currency", v)} /><Field title="实际换入金额" type="number" value={fields.to_amount} onChange={v => set("to_amount", v)} /></>}
      {["settle", "cancel_subscription"].includes(fundKind) && <Field title="关联款项" value={fields.pending_id || ""} options={[{ value: "", label: "请选择待确认 / 待到账事项" }, ...(context?.current?.pending ?? []).map(p => ({ value: p.pending_id, label: `${p.pending_id} · ${p.amount} ${p.currency}` }))]} onChange={v => set("pending_id", v)} />}
      {["split", "position_transfer"].includes(fundKind) && <><Field title="标的代码" value={fields.code} onChange={v => { const a = assets.find(p => p.code === v); setFields(f => ({ ...f, code: v, market: a?.market || f.market, currency: a?.currency || f.currency, unit: a?.unit || f.unit, asset_type: a?.asset_type || f.asset_type })); }} /><Field title={fundKind === "split" ? "数量倍数（如一拆二填 2）" : "转出数量"} type="number" value={fields[fundKind === "split" ? "factor" : "quantity"]} onChange={v => set(fundKind === "split" ? "factor" : "quantity", v)} /></>}
      </div><small>转账保存两端，不要另录对方入金；换汇填写实际两币种金额。待确认/到账保留资产，确认只转换形态。费用类型的金额就是费用本身。拆分应用于所有已建档账户的同一标的、币种与单位，只记录一次。</small>
    </>}
    <FxFields values={fx} setValues={setFx} /><Field title="备注" value={fields.note || ""} onChange={v => set("note", v)} />
  </EditorShell>;
}
