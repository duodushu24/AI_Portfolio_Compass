import { useState } from "react";
import { Alert, Button, Input, Modal } from "@arco-design/web-react";
import { IconEdit } from "@arco-design/web-react/icon";
import { portfolioApi } from "./api";

export function RenameSecurity({ code, name, market, onSaved }: {code: string; name: string; market?: string; onSaved: () => void | Promise<void>}) {
  const [open, setOpen] = useState(false), [value, setValue] = useState(name), [error, setError] = useState(""), [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true); setError("");
    try { await portfolioApi.rename(code, value, market); await onSaved(); setOpen(false); }
    catch (e) { setError(e instanceof Error ? e.message : "名称保存失败"); }
    finally { setSaving(false); }
  }
  return <>
    <button type="button" className="portfolio-name-edit" aria-label={`修改${name || code}名称`} title="修改名称" onClick={() => { setValue(name); setError(""); setOpen(true); }}><IconEdit /></button>
    <Modal title="修改标的名称" visible={open} onCancel={() => !saving && setOpen(false)} footer={<><Button disabled={saving} onClick={() => setOpen(false)}>取消</Button><Button type="primary" loading={saving} disabled={!value.trim()} onClick={save}>保存</Button></>}>
      {error && <Alert type="error" content={error} />}
      <p>{code} · 同一标的在各账户中使用相同名称。</p>
      <label>标的名称<Input aria-label="标的新名称" value={value} maxLength={120} onChange={setValue} /></label>
    </Modal>
  </>;
}
