import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Input, Tabs, Tag } from "@arco-design/web-react";
import { sourceApi } from "./api";
import type { ProviderItem, SourceCheck } from "./api";

const capabilityLabel: Record<string, string> = {quote: "行情／净值", news: "新闻", kline: "日线", fx: "汇率", account: "账户同步", technical: "技术数据"};
export function DataSourcesPanel() {
  const [items, setItems] = useState<ProviderItem[]>([]), [error, setError] = useState("");
  useEffect(() => {let cancelled = false; sourceApi.list().then(r => {if (!cancelled) setItems(r.items);}).catch(e => {if (!cancelled) setError(String(e.message));}); return () => {cancelled = true;};}, []);
  return <section className="panel stack" id="data-sources"><div><h2>数据源</h2><small>默认使用 AKShare 免费来源。行情和新闻按需手动更新，与账户所属平台无关。</small></div>
    {error && <Alert type="error" content={error} />}
    <Tabs defaultActiveTab="free">{([{id: "free", name: "免费源"}, {id: "paid", name: "付费源"}] as const).map(group => <Tabs.TabPane key={group.id} title={group.name}>
      <div className="stack">{items.filter(p => p.group === group.id).map(p => <SourceCard key={p.id} provider={p} onSaved={setItems} />)}</div>
    </Tabs.TabPane>)}</Tabs>
  </section>;
}

function SourceCard({provider: p, onSaved}: {provider: ProviderItem; onSaved: (items: ProviderItem[]) => void}) {
  const [values, setValues] = useState<Record<string, unknown>>(p.config), [error, setError] = useState(""), [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(""), [result, setResult] = useState<SourceCheck | null>(p.last_check), [note, setNote] = useState("");
  useEffect(() => {setValues(p.config); setResult(p.last_check);}, [p]);
  const set = (key: string, value: unknown) => {setValues(v => ({...v, [key]: value})); setResult(null); setNote("");};
  async function save() {
    setSaving(true); setError(""); setNote("");
    try {onSaved((await sourceApi.save(p.id, values)).items); setNote("配置已保存");}
    catch (e) {setError(e instanceof Error ? e.message : "配置保存失败");}
    finally {setSaving(false);}
  }
  async function check(kind: string, sample?: string) {
    setChecking(`${kind}:${sample || ""}`); setError("");
    try {setResult(await sourceApi.check(p.id, kind, sample));}
    catch (e) {setError(e instanceof Error ? e.message : "连接检测失败");}
    finally {setChecking("");}
  }
  const dirty = JSON.stringify(values) !== JSON.stringify(p.config);
  return <div className="stack source-provider-card"><div className="portfolio-toolbar"><h3>{p.label}</h3><Tag color={p.id === "akshare" ? "green" : "gray"}>{p.id === "akshare" ? "默认免费" : p.group === "free" ? p.fields.some(f => f.type === "secret") ? "免费额度／需 Key" : "免费来源" : "可选授权来源"}</Tag></div>
    <p>{p.description}</p><small>支持市场：{p.markets.join("、")} · 能力：{p.capabilities.map(c => capabilityLabel[c] || c).join("、")}</small>
    {error && <Alert type="error" content={error} />}{note && <Alert type="success" content={note} />}
    <Checkbox checked={!!values.enabled} onChange={v => set("enabled", v)}>启用 {p.label}</Checkbox>
    <div className="portfolio-fields">{p.fields.map(f => <label key={f.key}>{f.label}{f.type === "secret" ? <><Input.Password aria-label={`${p.id}-${f.key}`} value={String(values[f.key] ?? "")} placeholder={p.secrets[f.key] ? "已保存；留空保留" : "填写自己的 API Key"} onChange={v => set(f.key, v)} />{p.secrets[f.key] && <Button size="mini" onClick={() => set(f.key, null)}>清除已保存密钥</Button>}</> : <Input aria-label={`${p.id}-${f.key}`} type={f.type === "number" ? "number" : "text"} value={String(values[f.key] ?? "")} onChange={v => set(f.key, v)} />}</label>)}</div>
    <div className="inline-actions">{["quote", "news", "fx"].filter(k => p.capabilities.includes(k)).map(k => <Checkbox key={k} checked={!!values[`preferred_${k}`]} onChange={v => set(`preferred_${k}`, v)}>优先使用此来源获取{capabilityLabel[k]}</Checkbox>)}</div>
    <div className="inline-actions"><Button type="primary" loading={saving} onClick={save}>保存 {p.label} 配置</Button>{(p.checks || ["quote", "news", "fx"].filter(k => p.capabilities.includes(k)).map(k => ({data_type:k,label:capabilityLabel[k],sample:undefined}))).map(c => <Button key={`${c.data_type}:${c.sample || ""}`} disabled={!values.enabled || dirty || saving || !!checking} loading={checking === `${c.data_type}:${c.sample || ""}`} onClick={() => check(c.data_type, c.sample)}>检测{c.label}</Button>)}{dirty && <small>请先保存，再检测实际连接。</small>}</div>
    {result ? <Alert type={result.status === "available" ? "success" : result.status === "empty" ? "info" : "warning"} content={`${result.message}${result.checked_at ? ` · ${new Date(result.checked_at).toLocaleString("zh-CN")}` : ""}`} /> : <small>{p.message}</small>}
  </div>;
}
