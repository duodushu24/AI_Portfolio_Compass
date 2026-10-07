import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Alert, Button, Card, Drawer, Empty, Form, Input, Message, Pagination, Spin, Tabs, Tag } from "@arco-design/web-react";
import { api, DiaryInput, DiaryList, DiarySaveResult, InvestmentDiary } from "../api";
import { DiaryAnalysisPanel } from "./DiaryAnalysisPanel";

function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

type Draft = { record_date: string; title: string; body: string; topics: string; keywords: string };
const blankDraft = (): Draft => ({ record_date: today(), title: "", body: "", topics: "", keywords: "" });
const draftOf = (item: InvestmentDiary): Draft => ({ ...item, topics: item.topics.join("、"), keywords: item.keywords.join("、") });
const labels = (value: string) => [...new Set(value.split(/[,，、\n]/).map((item) => item.trim()).filter(Boolean))];

export type DiaryLeaveGuard = () => boolean;

export function ReviewWorkspace({ children, registerLeaveGuard, canLeaveCurrent }: {
  children: ReactNode;
  registerLeaveGuard: (guard: DiaryLeaveGuard | null) => void;
  canLeaveCurrent: () => boolean;
}) {
  const [tab, setTab] = useState("diary");
  return <Tabs activeTab={tab} onChange={(next) => { if (canLeaveCurrent()) setTab(next); }} destroyOnHide>
    <Tabs.TabPane key="diary" title="投资日记"><DiaryPage registerLeaveGuard={registerLeaveGuard} /></Tabs.TabPane>
    <Tabs.TabPane key="trades" title="成交复盘">{children}</Tabs.TabPane>
  </Tabs>;
}

export function DiaryPage({ registerLeaveGuard }: { registerLeaveGuard: (guard: DiaryLeaveGuard | null) => void }) {
  const [list, setList] = useState<DiaryList | null>(null);
  const [selected, setSelected] = useState<InvestmentDiary | null>(null);
  const [filters, setFilters] = useState({ q: "", start_date: "", end_date: "" });
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | undefined>();
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [baseline, setBaseline] = useState<Draft>(draft);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<DiarySaveResult | null>(null);
  const [saveError, setSaveError] = useState("");
  const dirty = editorOpen && JSON.stringify(draft) !== JSON.stringify(baseline);
  const guardState = useRef({ dirty, saving });
  const analysisGuard = useRef<(() => boolean) | null>(null);
  const registerAnalysisGuard = useCallback((guard: (() => boolean) | null) => { analysisGuard.current = guard; }, []);
  guardState.current = { dirty, saving };

  useEffect(() => {
    registerLeaveGuard(() => {
      if (guardState.current.saving) { Message.info("正在保存，请稍候。"); return false; }
      if (guardState.current.dirty && !window.confirm("原文修改尚未保存，确定离开并放弃修改吗？")) return false;
      return analysisGuard.current?.() ?? true;
    });
    return () => registerLeaveGuard(null);
  }, [registerLeaveGuard]);

  useEffect(() => {
    function preventUnload(event: BeforeUnloadEvent) {
      if (dirty || saving) { event.preventDefault(); event.returnValue = ""; }
    }
    window.addEventListener("beforeunload", preventUnload);
    return () => window.removeEventListener("beforeunload", preventUnload);
  }, [dirty, saving]);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    api.diaries({ ...filters, offset: (page - 1) * 30 }).then((result) => {
      if (current) setList(result);
    }).catch((reason) => {
      if (current) setError(reason instanceof Error ? reason.message : "日记加载失败");
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [filters, page, refresh]);

  function edit(item?: InvestmentDiary) {
    const next = item ? draftOf(item) : blankDraft();
    setDraft(next);
    setBaseline(next);
    setEditingId(item?.id);
    setSaveResult(null);
    setSaveError("");
    setEditorOpen(true);
  }

  function closeEditor() {
    if (saving) return;
    if (dirty && !window.confirm("原文修改尚未保存，确定放弃修改吗？")) return;
    setEditorOpen(false);
  }

  function acceptSaved(result: DiarySaveResult) {
    setSelected(result.item);
    setEditingId(result.item.id); // Retry/edit always targets the saved row.
    const savedDraft = draftOf(result.item);
    setDraft(savedDraft);
    setBaseline(savedDraft);
    setSaveResult(result);
    setRefresh((value) => value + 1);
    if (result.markdown_saved) {
      Message.success(result.message);
      setEditorOpen(false);
    }
  }

  async function save() {
    if (saving) return;
    if (!draft.record_date || !draft.body.trim()) { setSaveError("请填写日期和日记正文。"); return; }
    setSaving(true);
    setSaveError("");
    try {
      const input: DiaryInput = { ...draft, topics: labels(draft.topics), keywords: labels(draft.keywords) };
      acceptSaved(await api.saveDiary(input, editingId));
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : "原文保存失败");
    } finally { setSaving(false); }
  }

  async function retry(item: InvestmentDiary) {
    if (saving) return;
    setSaving(true);
    setSaveError("");
    try {
      const result = await api.retryDiaryMarkdown(item.id);
      setSelected(result.item);
      setSaveResult(result);
      setRefresh((value) => value + 1);
      if (result.markdown_saved) { Message.success("文件已保存"); setEditorOpen(false); }
    } catch (reason) { setSaveError(reason instanceof Error ? reason.message : "文件保存失败"); }
    finally { setSaving(false); }
  }

  function changeFilter(key: keyof typeof filters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }

  return (
    <div className="stack diary-page">
      <div className="diary-heading">
        <div><h2>投资日记</h2><p>记录当时的思考、计划与经历。日记独立于证券账户，按日期保存。</p></div>
        <Button type="primary" onClick={() => edit()}>写日记</Button>
      </div>
      <div className="diary-filters">
        <Input aria-label="搜索日记" allowClear placeholder="搜索正文、标题、主题或关键词" value={filters.q} onChange={(value) => changeFilter("q", value)} />
        <label>从 <input aria-label="开始日期" type="date" value={filters.start_date} onChange={(event) => changeFilter("start_date", event.target.value)} /></label>
        <label>至 <input aria-label="结束日期" type="date" value={filters.end_date} onChange={(event) => changeFilter("end_date", event.target.value)} /></label>
        <Button onClick={() => { setFilters({ q: "", start_date: "", end_date: "" }); setPage(1); }}>重置</Button>
      </div>
      {error ? <Alert type="error" content={error} action={<Button onClick={() => setRefresh((value) => value + 1)}>重新加载</Button>} /> : null}
      <div className="diary-layout">
        <Card title={`日记记录${list ? ` · ${list.count}` : ""}`} className="diary-list">
          <Spin loading={loading} style={{ width: "100%" }}>
            {!list?.items.length ? <Empty description={loading ? "正在加载日记" : "暂无日记，可点击“写日记”开始记录"} /> : list.items.map((item) => (
              <button key={item.id} className={`diary-list-item ${selected?.id === item.id ? "is-selected" : ""}`} onClick={() => { setSelected(item); setSaveResult(null); setSaveError(""); }}>
                <small>{item.record_date}{!item.markdown_saved ? " · 文件待保存" : ""}</small>
                <strong>{item.title || "未命名日记"}</strong>
                <span>{item.body.slice(0, 100)}</span>
              </button>
            ))}
          </Spin>
          {list && list.count > 30 ? <Pagination total={list.count} pageSize={30} current={page} onChange={setPage} size="small" simple /> : null}
        </Card>
        <Card className="diary-detail" title={selected ? `${selected.record_date} · ${selected.title || "日记原文"}` : "日记原文"} extra={selected ? <Button onClick={() => edit(selected)}>编辑原文</Button> : null}>
          {selected ? <>
            {selected.topics.length || selected.keywords.length ? <div className="diary-tags">{selected.topics.map((value) => <Tag key={`topic-${value}`} color="arcoblue">{value}</Tag>)}{selected.keywords.map((value) => <Tag key={`keyword-${value}`}>{value}</Tag>)}</div> : null}
            <div className="diary-original">{selected.body}</div>
            <p className="diary-file">阅读文件：{selected.markdown_path}</p>
            {!selected.markdown_saved ? <Alert type="warning" content="记录已入库，文件保存失败。" action={<Button loading={saving} onClick={() => retry(selected)}>重试文件保存</Button>} /> : null}
            {saveError && !editorOpen ? <Alert type="error" content={saveError} /> : null}
            {saveResult && !editorOpen && !saveResult.markdown_saved ? <p className="diary-file">{saveResult.file_errors.join("；")}</p> : null}
          </> : <Empty description="选择一条日记查阅原文，或写下新的记录" />}
        </Card>
      </div>
      <DiaryAnalysisPanel diary={selected} refreshToken={refresh} onGuard={registerAnalysisGuard} />
      <Drawer visible={editorOpen} title={editingId ? "编辑日记原文" : "写投资日记"} width={640} maskClosable={false} onCancel={closeEditor} footer={<div className="diary-editor-actions"><Button disabled={saving} onClick={closeEditor}>关闭</Button><Button type="primary" loading={saving} onClick={save}>{editingId ? "保存修改" : "保存原文"}</Button></div>}>
        <Form layout="vertical">
          <Form.Item label="记录日期" required><input className="diary-date-input" aria-label="记录日期" type="date" value={draft.record_date} disabled={saving} onChange={(event) => setDraft({ ...draft, record_date: event.target.value })} /></Form.Item>
          <Form.Item label="标题（可选）"><Input aria-label="日记标题" value={draft.title} maxLength={200} disabled={saving} onChange={(title) => setDraft({ ...draft, title })} placeholder="为这次记录起一个简短标题" /></Form.Item>
          <Form.Item label="日记正文" required><Input.TextArea aria-label="日记正文" value={draft.body} disabled={saving} onChange={(body) => setDraft({ ...draft, body })} autoSize={{ minRows: 12, maxRows: 24 }} placeholder="自由记录你的思考、计划和经历……" /></Form.Item>
          <Form.Item label="主题（可选）"><Input aria-label="日记主题" value={draft.topics} disabled={saving} onChange={(topics) => setDraft({ ...draft, topics })} placeholder="例如：仓位管理、长期持有；用逗号或顿号分隔" /></Form.Item>
          <Form.Item label="关键词（可选）"><Input aria-label="日记关键词" value={draft.keywords} disabled={saving} onChange={(keywords) => setDraft({ ...draft, keywords })} placeholder="具体标的、事件或表达；用逗号或顿号分隔" /></Form.Item>
        </Form>
        {saveError ? <Alert type="error" content={saveError} /> : null}
        {saveResult && !saveResult.markdown_saved ? <Alert type="warning" content={<span>{saveResult.message}<small className="diary-file">{saveResult.file_errors.join("；")}</small></span>} action={<Button disabled={dirty} loading={saving} onClick={() => retry(saveResult.item)}>重试文件保存</Button>} /> : null}
      </Drawer>
    </div>
  );
}
