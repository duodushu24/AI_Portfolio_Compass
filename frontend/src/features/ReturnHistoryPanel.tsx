import { useEffect, useRef, useState } from "react";
import { Alert, Button, Checkbox, Drawer, Empty, Input, Modal, Select, Table, Tag } from "@arco-design/web-react";
import { api, AccountSummary, HoldingBatch, HoldingHistoryItem, ReturnDraftItem, ReturnEvent, ReturnPoint, ReturnSeries } from "../api";
import { PositionSnapshotModal } from "./portfolioViews";
import "./returnHistory.css";

const localTime = (value?: string) => {
  const date = value ? new Date(value) : new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const instant = (value: string) => new Date(value).toISOString();
const dateLabel = (value: string) => new Date(value).toLocaleString("zh-CN", { hour12: false });
const roiLabel = (value: string | number | null) => value == null ? "—" : `${(Number(value) * 100).toFixed(2)}%`;
const numberLabel = (value: string | number | null | undefined) => value == null ? "—" : Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 4 });

function ReturnChart({ points, events, onPoint, onEvent }: {
  points: Array<{ id: number; time: string; value: number | null }>;
  events: ReturnEvent[]; onPoint: (id: number) => void; onEvent: (event: ReturnEvent) => void;
}) {
  if (!points.length) return <Empty description="尚无收益观察点，点击“记录收益”开始积累。" />;
  const width = 900, height = 270, left = 68, right = 22, top = 24, bottom = 54;
  const times = points.map(p => new Date(p.time).getTime());
  const first = Math.min(...times), last = Math.max(...times);
  const values = points.flatMap(p => p.value == null ? [] : [p.value * 100]);
  const lower = Math.min(0, ...values), upper = Math.max(0, ...values);
  const pad = Math.max((upper - lower) * .15, 1), minY = lower - pad, maxY = upper + pad;
  const x = (time: number) => last === first ? (left + width - right) / 2 : left + (time - first) / (last - first) * (width - left - right);
  const y = (value: number) => top + (maxY - value) / (maxY - minY) * (height - top - bottom);
  let path = "", continued = false;
  for (const point of points) {
    if (point.value == null) { continued = false; continue; }
    path += `${continued ? "L" : "M"}${x(new Date(point.time).getTime())},${y(point.value * 100)} `;
    continued = true;
  }
  return <div className="return-chart-wrap">
    <svg viewBox={`0 0 ${width} ${height}`} className="return-chart" role="img" aria-label="持仓收益率曲线，按实际观察时间连接；橙色表示已记录成交">
      {[0, 1, 2, 3, 4].map(i => {
        const value = minY + (maxY - minY) * i / 4;
        return <g key={i}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="return-grid" /><text x={left - 10} y={y(value) + 4} textAnchor="end">{value.toFixed(1)}%</text></g>;
      })}
      <path d={path} fill="none" stroke="var(--primary-color, #165dff)" strokeWidth={2.5} />
      {points.map(p => {
        const day = new Date(p.time).toLocaleDateString();
        const traded = events.some(e => new Date(e.deal_time).toLocaleDateString() === day);
        return <circle key={p.id} cx={x(new Date(p.time).getTime())} cy={p.value == null ? height - bottom + 10 : y(p.value * 100)}
          r={5} fill={traded ? "#ff7d00" : p.value == null ? "#86909c" : "#165dff"} role="button" tabIndex={0}
          aria-label={`查看${dateLabel(p.time)}观察 ${roiLabel(p.value)}`} onClick={() => onPoint(p.id)} onKeyDown={e => { if (e.key === "Enter") onPoint(p.id); }}>
          <title>{dateLabel(p.time)} · {roiLabel(p.value)}{p.value == null ? "（数据未齐或无持仓）" : ""}</title>
        </circle>;
      })}
      {events.filter(e => new Date(e.deal_time).getTime() >= first && new Date(e.deal_time).getTime() <= last).map((e, index) => <rect
        key={e.id} x={x(new Date(e.deal_time).getTime()) - 4} y={height - bottom + 22 + index % 2 * 6} width={8} height={8}
        fill="#ff7d00" role="button" tabIndex={0} aria-label={`查看调仓 ${e.code} ${dateLabel(e.deal_time)}`}
        onClick={() => onEvent(e)} onKeyDown={ev => { if (ev.key === "Enter") onEvent(e); }}><title>{e.code} {dateLabel(e.deal_time)} · 已记录成交</title></rect>)}
      <text x={left} y={height - 6}>{new Date(first).toLocaleDateString()}</text>
      {last !== first && <text x={width - right} y={height - 6} textAnchor="end">{new Date(last).toLocaleDateString()}</text>}
    </svg>
    <p className="metadata-note">蓝色：收益观察 · 橙色：已记录成交 · 灰色：数据未齐/无持仓。仅连接观察点，空缺处断开；调仓标记可点击。</p>
  </div>;
}

export function ReturnHistoryPanel({ selectedAccount, accounts, maskAssets, onChanged }: { selectedAccount: string; accounts: AccountSummary[]; maskAssets: boolean; onChanged: () => Promise<void> }) {
  const [currency, setCurrency] = useState("CNY");
  const [scope, setScope] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [data, setData] = useState<ReturnSeries | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<ReturnPoint | null | undefined>(undefined);
  const [selected, setSelected] = useState<ReturnPoint | null>(null);
  const [event, setEvent] = useState<ReturnEvent | null>(null);
  const [asset, setAsset] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const latestRequest = useRef(0);
  async function reload() {
    const request = ++latestRequest.current;
    setLoading(true); setError("");
    try {
      const result = await api.returnSeries(selectedAccount, currency, start ? instant(start) : "", end ? instant(end) : "", scope && selectedAccount === "all" ? JSON.parse(scope) : undefined);
      if (request === latestRequest.current) setData(result);
    } catch (e) { if (request === latestRequest.current) setError(e instanceof Error ? e.message : "读取失败"); }
    finally { if (request === latestRequest.current) setLoading(false); }
  }
  useEffect(() => { setScope(""); }, [selectedAccount]);
  useEffect(() => { setSelected(null); setAsset(""); setData(null); void reload(); return () => { latestRequest.current++; }; }, [selectedAccount, currency, start, end, scope]);
  const points = (data?.items ?? []).map(p => {
    if (!asset) return { id: p.id, time: p.observed_at, value: p.return_ratio == null ? null : Number(p.return_ratio) };
    const value = p.asset_returns[asset];
    return { id: p.id, time: p.observed_at, value: value == null ? null : Number(value) };
  });
  const assetOptions = Array.from(new Set(data?.items.flatMap(p => p.items.map(i => i.code)) ?? []));
  const filteredEvents = (data?.events ?? []).filter(e => !asset || e.code === asset);
  const scopeNames = data?.account_ids.map(id => accounts.find(a => a.account_id === id)?.display_name || id).join("、");
  return <section className="return-history-panel stack">
    <div className="return-toolbar"><div><h3>持仓收益</h3><p className="metadata-note">按剩余平均成本加权 · {currency} · {scopeNames || "尚未选择账户"}</p></div>
      <div className="return-actions"><Button onClick={() => setShowHistory(true)}>持仓历史</Button><Button type="primary" onClick={() => setEditing(null)} disabled={!data?.account_ids.length}>记录收益</Button></div>
    </div>
    <div className="return-filters">
      <Select aria-label="收益币种" value={currency} onChange={setCurrency} options={["CNY", "HKD", "USD"]} />
      {selectedAccount === "all" && <Select aria-label="组合账户范围" value={scope} onChange={setScope} options={[{ value: "", label: "当前启用账户" }, ...(data?.available_scopes ?? []).map(ids => ({ value: JSON.stringify(ids), label: ids.map(id => accounts.find(a => a.account_id === id)?.display_name || id).join("、") }))]} />}
      <Select aria-label="收益曲线范围" value={asset} onChange={setAsset} options={[{ value: "", label: "组合持仓收益率" }, ...assetOptions.map(code => ({ value: code, label: code }))]} />
      <label>开始 <Input type="datetime-local" value={start} onChange={setStart} /></label>
      <label>结束 <Input type="datetime-local" value={end} onChange={setEnd} /></label>
    </div>
    {error && <Alert type="error" content={error} />}
    {loading ? <p>正在读取收益记录…</p> : <ReturnChart points={points} events={filteredEvents} onPoint={id => setSelected(data?.items.find(p => p.id === id) ?? null)} onEvent={setEvent} />}
    {!!data?.other_scope_count && <Alert type="info" content={`另有 ${data.other_scope_count} 条记录采用不同账户范围，已分开保存；切换回对应账户范围查看。`} />}
    <p className="metadata-note">持仓收益不含已卖出部分和现金。{data?.cumulative_reason} 全部账户仅包含启用账户；不同币种/账户范围分别形成曲线。</p>
    <details><summary>观察记录与成交明细（含未落在曲线时间内的成交）</summary>
      <Table rowKey="id" data={data?.items ?? []} pagination={{ pageSize: 6 }} columns={[
        { title: "观察时间", dataIndex: "observed_at", render: value => dateLabel(value) },
        { title: "持仓收益率", dataIndex: "return_ratio", render: value => roiLabel(value) },
        { title: "数据覆盖", render: (_, p: ReturnPoint) => `${p.covered_count}/${p.holding_count}${p.status === "empty" ? "（无持仓）" : ""}${p.price_warning ? " · 旧价/估算" : ""}${p.scope_warning ? " · 范围待核对" : ""}` },
        { title: "操作", render: (_, p: ReturnPoint) => <Button size="small" onClick={() => setSelected(p)}>查看</Button> },
      ]} />
      <EventList events={filteredEvents} onSelect={setEvent} />
    </details>
    {editing !== undefined && <ReturnRecorder accountId={selectedAccount} accountIds={editing?.account_ids ?? data?.account_ids} currency={currency} existing={editing} accounts={accounts} onClose={() => setEditing(undefined)} onSaved={async () => { setEditing(undefined); setSelected(null); await reload(); }} />}
    {selected && <Drawer title={`收益观察 · ${dateLabel(selected.observed_at)}`} width={1000} visible footer={null} onCancel={() => setSelected(null)}>
      <div className="stack"><h3>{roiLabel(selected.return_ratio)} · {selected.currency}</h3>
        <p>覆盖 {selected.covered_count}/{selected.holding_count} 个账户标的。{selected.status === "empty" && "此时无持仓。"} {selected.note}</p>
        {selected.scope_warning && <Alert type="warning" content="账户尚无完整持仓基线，本次收益仅反映已记录持仓。请通过完整持仓导入或空仓确认核对范围。" />}
        {selected.holdings_changed && <Alert type="warning" content="历史持仓经补录或纠错后已重新计算；新增/替换持仓的成本和价格需重新核对。" />}
        <Table rowKey={i => `${i.account_id}:${i.code}`} data={selected.items} pagination={false} scroll={{ x: 1100 }} columns={[
          { title: "账户/标的", render: (_, i) => <Button type="text" onClick={() => { setAsset(i.code); setSelected(null); }}>{i.account_id} · {i.name || i.code}</Button> },
          { title: "数量/均价", render: (_, i) => `${numberLabel(i.quantity)} / ${numberLabel(i.average_cost)} ${i.raw_currency}` },
          { title: "价格时间", render: (_, i) => `${numberLabel(i.price)} · ${i.price_at ? dateLabel(i.price_at) : "缺失"} · ${i.source} · ${i.price_kind === "nav" ? "正式净值" : i.price_kind === "estimate" ? "估算" : "价格"}` },
          { title: "汇率", dataIndex: "fx_rate", render: numberLabel },
          { title: "成本/市值", render: (_, i) => maskAssets ? "****" : `${numberLabel(i.cost)} / ${numberLabel(i.market_value)} ${selected.currency}` },
          { title: "收益率/状态", render: (_, i) => `${roiLabel(i.return_ratio)} ${i.problems.join("；")}${i.stale ? " · 旧价" : ""}` },
        ]} />
        <EventList events={(data?.events ?? []).filter(e => new Date(e.deal_time).toLocaleDateString() === new Date(selected.observed_at).toLocaleDateString())} onSelect={setEvent} />
        <div className="return-actions"><Button onClick={() => setEditing(selected)}>修改观察</Button><Button status="danger" onClick={() => Modal.confirm({ title: "删除错误收益观察？", content: "持仓和成交记录仍保留。", onOk: async () => { await api.deleteReturn(selected.id); setSelected(null); await reload(); } })}>删除观察</Button></div>
      </div>
    </Drawer>}
    {event && <Drawer title="已记录调仓" width={620} visible footer={null} onCancel={() => setEvent(null)}><div className="stack">
      <h3>{event.account_id} · {event.code} · {event.side === "BUY" ? "买入" : event.side === "SELL" ? "卖出" : event.side}</h3>
      <p>{dateLabel(event.deal_time)} · 数量 {numberLabel(event.quantity)} · 成交价 {numberLabel(event.price)}</p>
      <p>费用：{Object.entries(event.fees).map(([key, value]) => `${({ fee: "手续费", commission: "佣金", tax: "税费" } as Record<string, string>)[key]} ${numberLabel(value)}`).join(" / ")}</p>
      {[{ title: "之前最近观察", fact: event.before }, { title: "之后最近观察", fact: event.after }].map(({ title, fact }) => <p key={title}>{title}：{fact ? `${dateLabel(fact.observed_at)} · 数量 ${numberLabel(fact.quantity)} · 均价 ${numberLabel(fact.average_cost)}` : "缺少记录"}</p>)}
      <Alert type="info" content={event.detail_note} />
    </div></Drawer>}
    {showHistory && <HoldingHistory accountId={selectedAccount} accounts={accounts} onClose={() => setShowHistory(false)} onChanged={async () => { await onChanged(); await reload(); }} onAsset={code => { setAsset(code); setShowHistory(false); }} />}
  </section>;
}

function EventList({ events, onSelect }: { events: ReturnEvent[]; onSelect: (e: ReturnEvent) => void }) {
  return <div className="return-event-list">{events.length ? events.map(e => <Button key={e.id} size="small" onClick={() => onSelect(e)}>{dateLabel(e.deal_time)} · {e.code} · {e.side === "BUY" ? "买入" : e.side === "SELL" ? "卖出" : e.side}</Button>) : <p className="metadata-note">该范围暂无已记录成交；数量变化不会自动生成买卖记录。</p>}</div>;
}

function ReturnRecorder({ accountId, accountIds, currency, existing, accounts, onClose, onSaved }: {
  accountId: string; accountIds?: string[]; currency: string; existing: ReturnPoint | null; accounts: AccountSummary[]; onClose: () => void; onSaved: () => Promise<void>;
}) {
  const [time, setTime] = useState(localTime(existing?.observed_at));
  const [rows, setRows] = useState<ReturnDraftItem[]>([]);
  const [ids, setIds] = useState<string[]>([]);
  const [loadedTime, setLoadedTime] = useState("");
  const [note, setNote] = useState(existing?.note ?? "");
  const [checkedScope, setCheckedScope] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const requestCounter = useRef(0);
  async function load() {
    if (!time) return;
    const request = ++requestCounter.current;
    setBusy(true); setError("");
    try {
      const result = await api.returnDraft(accountId, instant(time), currency, accountIds);
      if (request !== requestCounter.current) return;
      setIds(result.account_ids); setLoadedTime(time);
      setRows(result.items.map(row => {
        const old = existing?.inputs.find(i => i.position_id === row.position_id);
        if (!old) return row;
        const sameCurrency = (old.price_currency ?? old.holding_currency) === row.raw_currency;
        const sameCost = sameCurrency && Number(old.holding_quantity) === row.quantity && Number(old.holding_average_cost) === row.average_cost;
        return { ...row, ...old, price: sameCurrency ? old.price : null,
          fx_rate: sameCurrency ? old.fx_rate : row.fx_rate,
          confirm_average_cost: sameCost ? old.confirm_average_cost : row.confirm_average_cost,
          cost_cny_amount: sameCost ? old.cost_cny_amount : row.cost_cny_amount };
      }));
    } catch (e) { setError(e instanceof Error ? e.message : "读取持仓失败"); }
    finally { if (request === requestCounter.current) setBusy(false); }
  }
  useEffect(() => { void load(); return () => { requestCounter.current++; }; }, []);
  function update(index: number, patch: Partial<ReturnDraftItem>) { setRows(old => old.map((row, i) => i === index ? { ...row, ...patch } : row)); }
  async function save() {
    setBusy(true); setError("");
    try {
      await api.saveReturn({ observed_at: instant(time), account_ids: ids, currency, note,
        inputs: rows.map(({ position_id, account_id, code, price, price_at, fx_rate, source, price_kind, confirm_average_cost, cost_cny_amount }) => ({
          position_id, account_id, code, price: price === "" ? null : price, price_at, fx_rate: fx_rate || null,
          source, price_kind, confirm_average_cost, cost_cny_amount: cost_cny_amount || null,
        })) }, existing?.id);
      await onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
    finally { setBusy(false); }
  }
  return <Drawer title={existing ? "修改收益观察" : "记录收益"} width={1120} visible onCancel={onClose} footer={<div className="return-actions"><Button onClick={onClose}>取消</Button><Button type="primary" onClick={save} loading={busy} disabled={busy || time !== loadedTime || !checkedScope || !ids.length}>保存观察</Button></div>}>
    <div className="stack">
      <div className="return-actions"><label>实际观察时间 <Input type="datetime-local" value={time} onChange={setTime} /></label><Button onClick={load} loading={busy}>读取该时点持仓</Button></div>
      <Checkbox checked={checkedScope} onChange={setCheckedScope}>确认纳入 {ids.map(id => accounts.find(a => a.account_id === id)?.display_name || id).join("、")}，以 {currency} 记录</Checkbox>
      <Alert type="info" content="数量和平均成本取自该时点的持仓。填新价格时自动使用观察时间，请核对实际价格日期；未填写的价格保持缺失。人民币成本填写剩余持仓的取得/期初确认成本，不能用今天汇率倒推。" />
      {error && <Alert type="error" content={error} />}
      {time !== loadedTime && <Alert type="warning" content="时间已修改，请重新读取该时点持仓后核对。" />}
      {!rows.length && <Empty description="该时点没有可用持仓。可保存观察；已作废记录会标为待核对，不视为清仓。" />}
      {rows.map((row, index) => <section className="return-record-row" key={`${row.account_id}:${row.code}`}>
        <div className="return-toolbar"><strong>{row.name || row.code} · {row.code}</strong><span>{row.account_id} · 数量 {numberLabel(row.quantity)} · 均价 {numberLabel(row.average_cost)} {row.raw_currency}</span></div>
        <div className="return-inputs">
          <label>价格 / 单位净值<Input type="number" min={0} value={row.price ?? ""} placeholder="留空表示缺失" onChange={price => update(index, { price: price || null, price_at: instant(time), source: "手工" })} /></label>
          <label>实际价格时间<Input type="datetime-local" value={localTime(row.price_at)} onChange={value => { if (value) update(index, { price_at: instant(value) }); }} /></label>
          <label>来源<Input value={row.source} onChange={source => update(index, { source })} /></label>
          <label>价格类型<Select value={row.price_kind} onChange={price_kind => update(index, { price_kind })} options={[{ value: "price", label: "市场价格" }, { value: "nav", label: "正式单位净值" }, { value: "estimate", label: "估算价格/净值" }]} /></label>
          {row.raw_currency !== currency && currency === "CNY" && <>
            <label>{row.raw_currency} → CNY 汇率<Input type="number" min={0} value={row.fx_rate ?? ""} onChange={fx_rate => update(index, { fx_rate })} /></label>
            <label>剩余持仓人民币成本<Input type="number" min={0} value={row.cost_cny_amount ?? ""} onChange={cost_cny_amount => update(index, { cost_cny_amount })} /></label>
          </>}
        </div>
        <Checkbox checked={row.confirm_average_cost} onChange={confirm_average_cost => update(index, { confirm_average_cost })}>已核对上述均价为平均成本</Checkbox>
        {row.raw_currency !== currency && currency !== "CNY" && <p>此持仓币种不同，无法合并到所选原币收益；请选择 CNY 并确认折算成本。</p>}
        {row.price_at && new Date(row.price_at) < new Date(instant(time)) && <Tag color="orange">沿用旧价 · {dateLabel(row.price_at)}</Tag>}
      </section>)}
      <label>备注<Input.TextArea value={note} onChange={setNote} placeholder="可记录本次复盘或数据缺失说明" /></label>
      <p className="metadata-note">可保存资料未齐的观察，但不会输出完整组合收益率。新增持仓或成交后，请单独保存相应时点的观察。</p>
    </div>
  </Drawer>;
}

function HoldingHistory({ accountId, accounts, onClose, onChanged, onAsset }: { accountId: string; accounts: AccountSummary[]; onClose: () => void; onChanged: () => Promise<void>; onAsset: (code: string) => void }) {
  const [items, setItems] = useState<HoldingHistoryItem[]>([]);
  const [batches, setBatches] = useState<HoldingBatch[]>([]);
  const [at, setAt] = useState("");
  const [error, setError] = useState("");
  const [edit, setEdit] = useState<HoldingHistoryItem | null>(null);
  const [empty, setEmpty] = useState(false);
  const [emptyAccount, setEmptyAccount] = useState(accountId === "all" ? accounts[0]?.account_id ?? "" : accountId);
  const [emptyTime, setEmptyTime] = useState(localTime());
  const [emptyMarket, setEmptyMarket] = useState("");
  const [confirm, setConfirm] = useState(false);
  const requestCounter = useRef(0);
  async function load() {
    const request = ++requestCounter.current;
    try { const result = await api.holdingHistory(accountId, at ? instant(at) : ""); if (request === requestCounter.current) { setItems(result.items); setBatches(result.batches); setError(""); } }
    catch (e) { setError(e instanceof Error ? e.message : "读取失败"); }
  }
  useEffect(() => { void load(); return () => { requestCounter.current++; }; }, [at]);
  return <Drawer title="持仓历史" width={1080} visible footer={null} onCancel={onClose}>
    <div className="stack">
      <div className="return-actions"><label>截至时点（留空查看全部）<Input type="datetime-local" value={at} onChange={setAt} /></label><Button onClick={() => setEmpty(true)} disabled={!accounts.length}>确认空仓状态</Button></div>
      <p className="metadata-note">“截至时点持有”按完整/局部批次还原；旧记录完整性未知。关闭的标的仍保留历史，收益曲线只包含已保存观察点。</p>
      {error && <Alert type="error" content={error} />}
      <Table rowKey="id" data={items} pagination={{ pageSize: 10 }} scroll={{ x: 1000 }} columns={[
        { title: "账户/标的", render: (_, row: HoldingHistoryItem) => `${row.account_id} · ${row.name || row.code}` },
        { title: "实际时间", dataIndex: "snapshot_time", render: dateLabel },
        { title: "数量/均价", render: (_, row: HoldingHistoryItem) => `${numberLabel(row.quantity)} / ${numberLabel(row.average_cost)} ${row.raw_currency}` },
        { title: "状态", render: (_, row: HoldingHistoryItem) => row.is_void ? "错误记录已作废" : row.is_current ? "截至时点持有" : row.quantity === 0 ? "零持仓观察" : "历史观察" },
        { title: "范围", dataIndex: "completeness", render: value => value === "full" ? "完整" : value === "partial" ? "局部" : "未知（旧记录）" },
        { title: "操作", render: (_, row: HoldingHistoryItem) => <div className="return-actions"><Button size="small" onClick={() => onAsset(row.code)}>收益曲线</Button><Button size="small" onClick={() => setEdit(row)}>维护</Button>
          {!row.is_void && <Button size="small" status="danger" onClick={() => Modal.confirm({ title: "作废错误持仓记录？", content: "此操作处理错误记录，不表示卖出；更早的持仓不会自动恢复。", onOk: async () => {
            await api.deleteAccountPosition(row.account_id, row.code, row.snapshot_time); await load(); await onChanged();
          } })}>作废</Button>}</div> },
      ]} />
      <details><summary>观察批次（包括完整空仓）</summary><Table rowKey="id" data={batches} pagination={{ pageSize: 6 }} columns={[
        { title: "账户", dataIndex: "account_id" }, { title: "范围", render: (_, b: HoldingBatch) => `${b.market || "整个账户"} · ${b.completeness === "full" ? "完整" : "局部"}` },
        { title: "实际时间", dataIndex: "observed_at", render: dateLabel }, { title: "来源", dataIndex: "source" },
      ]} /></details>
    </div>
    {edit && accounts.find(a => a.account_id === edit.account_id) && <PositionSnapshotModal account={accounts.find(a => a.account_id === edit.account_id)!} position={edit} onClose={() => setEdit(null)} setNotice={setError} onSaved={async () => { setEdit(null); await load(); await onChanged(); }} />}
    {empty && <Modal title="确认完整空仓状态" visible onCancel={() => setEmpty(false)} okButtonProps={{ disabled: !confirm || !emptyAccount || !emptyTime }} onOk={async () => {
      try { await api.confirmEmptyHoldings(emptyAccount, instant(emptyTime), emptyMarket); setEmpty(false); setConfirm(false); await load(); await onChanged(); }
      catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
    }}>
      <div className="stack"><Select value={emptyAccount} onChange={setEmptyAccount} options={accounts.map(a => ({ value: a.account_id, label: a.display_name || a.account_id }))} />
        <Select value={emptyMarket} onChange={setEmptyMarket} options={[{ value: "", label: "整个账户" }, { value: "CN", label: "仅境内市场" }, { value: "HK", label: "仅港股" }, { value: "US", label: "仅美股" }]} />
        <Input type="datetime-local" value={emptyTime} onChange={setEmptyTime} />
        <Checkbox checked={confirm} onChange={setConfirm}>确认该范围在此实际时点没有持仓。历史保留，不自动生成卖出成交。</Checkbox>
      </div>
    </Modal>}
  </Drawer>;
}
