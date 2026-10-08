import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Checkbox, Drawer, Empty, Input, Message, Pagination, Tag } from "@arco-design/web-react";
import { api, AIRuntimeConfig, DiaryCandidate, DiaryChatMessage, DiaryDiscussion, DiarySummary, DiarySummaryInput, InvestmentDiary, InvestmentTag, InvestmentTagInput } from "../api";
import { MarkdownReport, markdownPreviewText } from "./portfolioViews";

const blank = (): DiaryCandidate => ({ title: "", body: "", keywords: [], tag_ids: [], new_tags: [], accepted_new_tags: [] });
const words = (s: string) => [...new Set(s.split(/[,，、\n]/).map(v => v.trim()).filter(Boolean))];
const localDate = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const reason = (e: unknown) => e instanceof Error ? e.message : "操作未完成，请重试";

export function DiaryAnalysisPanel({ diary, refreshToken, onGuard }: {
  diary: InvestmentDiary | null; refreshToken: number; onGuard: (guard: (() => boolean) | null) => void;
}) {
  const [tags, setTags] = useState<InvestmentTag[]>([]);
  const [runtime, setRuntime] = useState<AIRuntimeConfig | null>(null);
  const [summaries, setSummaries] = useState<{ items: DiarySummary[]; count: number }>({ items: [], count: 0 });
  const [chats, setChats] = useState<{ items: DiaryDiscussion[]; count: number }>({ items: [], count: 0 });
  const [q, setQ] = useState("");
  const [filterTag, setFilterTag] = useState<number | undefined>();
  const [onlyDay, setOnlyDay] = useState(true);
  const [page, setPage] = useState(1);
  const [chatPage, setChatPage] = useState(1);
  const [tick, setTick] = useState(0);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"setup" | "chat" | "external" | "view">("setup");
  const [session, setSession] = useState<DiaryDiscussion | null>(null);
  const [draft, setDraft] = useState<DiaryCandidate>(blank);
  const [summaryPreview, setSummaryPreview] = useState(false);
  const [saved, setSaved] = useState(JSON.stringify(blank()));
  const [editing, setEditing] = useState<DiarySummary | null>(null);
  const [date, setDate] = useState(localDate());
  const [dayDiaries, setDayDiaries] = useState<InvestmentDiary[]>([]);
  const [diaryIds, setDiaryIds] = useState<number[]>([]);
  const [question, setQuestion] = useState("");
  const [background, setBackground] = useState("");
  const [input, setInput] = useState("");
  const [source, setSource] = useState<DiarySummaryInput["source_type"]>("external_discussion");
  const [sourceNote, setSourceNote] = useState("ChatGPT");
  const [keywordText, setKeywordText] = useState("");
  const [savedMeta, setSavedMeta] = useState("");
  const [sessionIds, setSessionIds] = useState<number[]>([]);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draftSaving, setDraftSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [tagOpen, setTagOpen] = useState(false);
  const [tagEdit, setTagEdit] = useState<number | undefined>();
  const [tagDraft, setTagDraft] = useState<InvestmentTagInput>({ name: "", definition: "", aliases: [] });
  const [mergeTarget, setMergeTarget] = useState<number | undefined>();
  const [tagDirty, setTagDirty] = useState(false);
  const [tagAliasText, setTagAliasText] = useState("");
  const flight = useRef<Promise<void> | null>(null);
  const busyRef = useRef(false);
  const mounted = useRef(true);
  const meta = JSON.stringify({ date, diaryIds, source, sourceNote, sessionIds });
  const live = useRef({ draft, session, open, busy, draftSaving, saved, input, mode, tagDirty, meta, savedMeta });
  live.current = { draft, session, open, busy, draftSaving, saved, input, mode, tagDirty, meta, savedMeta };
  const scopeDate = diary?.record_date;
  const dirty = open && mode !== "view" && JSON.stringify(draft) !== saved;

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const guard = () => {
      const v = live.current;
      if (v.busy || v.draftSaving) { Message.info("正在生成或保存，请稍候。"); return false; }
      const unsaved = (v.open && v.mode !== "view" && (JSON.stringify(v.draft) !== v.saved || !!v.input.trim() || (!v.session && v.meta !== v.savedMeta))) || v.tagDirty;
      return !unsaved || window.confirm("还有未保存的编辑或未发送的问题，确定离开吗？已保存的讨论可重新打开。");
    };
    onGuard(guard);
    const unload = (event: BeforeUnloadEvent) => {
      const v = live.current;
      if (v.busy || v.draftSaving || (v.open && v.mode !== "view" && (JSON.stringify(v.draft) !== v.saved || !!v.input.trim() || (!v.session && v.meta !== v.savedMeta))) || v.tagDirty) {
        event.preventDefault(); event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", unload);
    return () => { onGuard(null); window.removeEventListener("beforeunload", unload); };
  }, [onGuard]);

  useEffect(() => { setPage(1); setChatPage(1); }, [scopeDate, onlyDay, q, filterTag]);
  useEffect(() => {
    let active = true;
    setError("");
    Promise.all([api.investmentTags(), api.aiConfig(), api.diarySummaries({
      ...(onlyDay && scopeDate ? { start_date: scopeDate, end_date: scopeDate } : {}), q, tag_id: filterTag, offset: (page - 1) * 30,
    }), api.diaryDiscussions(onlyDay ? scopeDate : undefined, (chatPage - 1) * 30)])
      .then(([t, cfg, s, c]) => { if (active) { setTags(t.items); setRuntime(cfg.runtime); setSummaries(s); setChats(c); } })
      .catch(e => { if (active) setError(reason(e)); });
    return () => { active = false; };
  }, [scopeDate, onlyDay, page, chatPage, q, filterTag, tick, refreshToken]);

  async function loadDay(value: string, selected?: number[]) {
    let result = await api.diaries({ start_date: value, end_date: value, limit: 100 });
    const items = [...result.items];
    while (items.length < result.count) {
      result = await api.diaries({ start_date: value, end_date: value, limit: 100, offset: items.length });
      items.push(...result.items);
    }
    if (selected) {
      const extra = await Promise.all(selected.filter(id => !items.some(d => d.id === id)).map(id => api.diary(id)));
      items.push(...extra.map(r => r.item));
    }
    setDayDiaries(items);
    setDiaryIds(selected ?? items.map(d => d.id));
    return items;
  }

  function acceptSession(item: DiaryDiscussion) {
    const next = { ...blank(), ...item.candidate };
    setSession(item); setDraft(next); setSaved(JSON.stringify(next));
    setKeywordText(next.keywords.join("、"));
    setDate(item.record_date); setDiaryIds(item.diary_ids); setSessionIds([item.id]);
    setSource("in_app_ai"); setSourceNote(item.base_source ? (item.base_source.includes("本项目补充讨论") ? item.base_source : `${item.base_source}；本项目补充讨论`) : "本项目 AI 分析与讨论");
  }

  async function persistDraft() {
    if (flight.current) await flight.current;
    const v = live.current;
    if (!v.session || JSON.stringify(v.draft) === v.saved) return;
    const id = v.session.id, snapshot = v.draft, encoded = JSON.stringify(snapshot);
    setDraftSaving(true);
    const task = api.saveDiaryCandidate(id, snapshot).then(() => {
      if (mounted.current && live.current.session?.id === id) { setSaved(encoded); setSaveError(""); }
    }).catch(e => { if (mounted.current) setSaveError(reason(e)); throw e; })
      .finally(() => { if (mounted.current) setDraftSaving(false); flight.current = null; });
    flight.current = task;
    await task;
  }

  useEffect(() => {
    if (!open || mode !== "chat" || !session || !dirty || busy || draftSaving || saveError) return;
    const timer = window.setTimeout(() => { void persistDraft().catch(() => {}); }, 600);
    return () => window.clearTimeout(timer);
  }, [open, mode, session?.id, draft, dirty, busy, draftSaving, saveError]);

  useEffect(() => {
    if (!open || !session || session.generation_status !== "running" || busy) return;
    const timer = window.setInterval(() => {
      api.diaryDiscussion(session.id).then(({ item }) => {
        if (mounted.current && live.current.session?.id === item.id) acceptSession(item);
      }).catch(e => setSaveError(reason(e)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [open, session?.id, session?.generation_status, busy]);

  async function work(action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true); setSaveError("");
    try { await action(); } catch (e) { if (mounted.current) setSaveError(reason(e)); }
    finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  }

  async function start(modeValue: "setup" | "external", base?: DiarySummary) {
    await work(async () => {
      const value = base?.record_date ?? scopeDate ?? localDate();
      const existing = base ?? (await api.diarySummaries({ start_date: value, end_date: value })).items[0];
      setSession(null); setEditing(existing ?? null); setConsent(false); setInput(""); setQuestion(""); setBackground("");
      setDate(value); setMode(modeValue);
      setSummaryPreview(modeValue === "setup");
      const effective = modeValue === "external" ? existing : base;
      const next = effective ? { ...blank(), title: effective.title, body: effective.body, keywords: effective.keywords, tag_ids: effective.tags.map(t => t.id) } : blank();
      setDraft(next); setSaved(JSON.stringify(next));
      setKeywordText(next.keywords.join("、"));
      setSource(effective?.source_type ?? "external_discussion"); setSourceNote(effective?.source_note ?? "ChatGPT"); setSessionIds(effective?.session_ids ?? []);
      const originals = await loadDay(value, effective?.diary_ids);
      setSavedMeta(JSON.stringify({ date: value, diaryIds: effective?.diary_ids ?? originals.map(d => d.id), source: effective?.source_type ?? "external_discussion", sourceNote: effective?.source_note ?? "ChatGPT", sessionIds: effective?.session_ids ?? [] }));
      setOpen(true);
    });
  }

  async function openChat(id: number) {
    await work(async () => {
      const { item } = await api.diaryDiscussion(id);
      const found = await api.diarySummaries({ start_date: item.record_date, end_date: item.record_date });
      setEditing(found.items[0] ?? null); acceptSession(item); setMode("chat"); setConsent(false); setInput("");
      setSummaryPreview(true);
      await loadDay(item.record_date, item.diary_ids); setOpen(true);
    });
  }

  async function viewSummary(item: DiarySummary) {
    await start("external", item); setMode("view");
  }

  async function close() {
    if (busy || draftSaving) return;
    if (dirty && session) { try { await persistDraft(); } catch { return; } }
    if ((!session && (dirty || meta !== savedMeta)) || input.trim() || (mode === "setup" && (question.trim() || background.trim()))) {
      if (!window.confirm("编辑或未发送的问题尚未保存，确定关闭吗？已保存的讨论仍可恢复。")) return;
    }
    setOpen(false); setTick(v => v + 1);
  }

  async function generate(task: DiaryChatMessage["task"], retryMessage?: DiaryChatMessage, initial?: DiaryDiscussion) {
    const current = initial ?? session;
    if (!current) return;
    if (!consent) { setSaveError("请先勾选本次模型发送授权"); return; }
    if (task === "discuss" && !retryMessage && !input.trim()) return;
    if (task === "summarize" && dirty && !window.confirm("重新整理会替换当前候选编辑内容，是否继续？")) return;
    await work(async () => {
      await persistDraft();
      let messageId = retryMessage?.id;
      if (!messageId) {
        const body = task === "analyze" ? (question.trim() || "请分析选中的日记，解释核心问题并形成总结。") : task === "summarize" ? "请综合完整讨论和我的纠正，整理最终总结与标签。" : input;
        const result = await api.addDiaryMessage(current.id, task, body);
        messageId = result.message_id; setSession(result.item); setInput("");
      }
      try {
        const result = await api.generateDiaryReply(current.id, messageId, task, consent);
        if (mounted.current && live.current.session?.id === current.id) acceptSession(result.item);
      } catch (e) {
        const restored = await api.diaryDiscussion(current.id);
        if (mounted.current) setSession(restored.item);
        throw e;
      }
      setTick(v => v + 1);
    });
  }

  async function createChat() {
    if (!diaryIds.length) { setSaveError("请至少选择一条已保存原文"); return; }
    if (!consent) { setSaveError("请先勾选模型发送授权"); return; }
    let created: DiaryDiscussion | null = null;
    await work(async () => {
      const result = await api.createDiaryDiscussion({ record_date: date, diary_ids: diaryIds,
        title: draft.title || "投资日记讨论", question, background, base_summary_id: editing?.id });
      created = result.item; acceptSession(result.item); setMode("chat"); setTick(v => v + 1);
    });
    if (created) await generate("analyze", undefined, created);
  }

  async function confirmSummary() {
    if (session?.needs_summary || session?.generation_status === "running") { setSaveError("请先整理当前讨论的总结"); return; }
    if (!draft.body.trim()) { setSaveError("请填写总结正文"); return; }
    if (editing && !window.confirm("将更新当天的已确认总结，是否确认保存当前内容？")) return;
    await work(async () => {
      await persistDraft();
      const found = await api.diarySummaries({ start_date: date, end_date: date });
      const target = editing?.id ?? found.items[0]?.id;
      if (!editing && target && !window.confirm("该日期已有总结，是否确认用当前内容更新？")) return;
      const result = await api.saveDiarySummary({ ...draft, new_tags: draft.new_tags.filter((_, i) => draft.accepted_new_tags.includes(i)),
        record_date: date, diary_ids: diaryIds, session_ids: session ? [session.id] : sessionIds,
        source_type: source, source_note: sourceNote, confirmed: true }, target);
      setEditing(result.item); setSaved(JSON.stringify(draft)); setTick(v => v + 1);
      setSavedMeta(meta);
      if (session) {
        const names = draft.new_tags.filter((_, i) => draft.accepted_new_tags.includes(i)).map(t => t.name);
        const next = { ...draft, tag_ids: result.item.tags.map(t => t.id), new_tags: draft.new_tags.filter(t => !names.includes(t.name)), accepted_new_tags: [] };
        await api.saveDiaryCandidate(session.id, next);
        setDraft(next); setSaved(JSON.stringify(next));
      }
      if (result.markdown_saved) Message.success(result.message);
      else setSaveError(result.message + result.file_errors.join("；"));
    });
  }

  const readOnly = mode === "view";
  const blocked = busy || draftSaving || session?.generation_status === "running";
  const modelReady = runtime?.enabled && runtime.has_api_key;
  const latestUser = session?.messages?.filter(m => m.role === "user").slice(-1)[0];
  const pending = latestUser && latestUser.status !== "complete" ? latestUser : null;
  const update = (patch: Partial<DiaryCandidate>) => { setDraft(v => ({ ...v, ...patch })); setSaveError(""); };
  const choose = (ids: number[], id: number, checked: boolean) => checked ? [...new Set([...ids, id])] : ids.filter(v => v !== id);
  const selectedOriginals = dayDiaries.filter(d => diaryIds.includes(d.id));

  return <div className="stack diary-analysis-panel">
    <div className="diary-heading"><div><h3>分析与总结</h3><p>讨论自动保存；总结经你确认后保存，便于日后复盘。</p></div>
      <div className="diary-editor-actions"><Button disabled={busy} onClick={() => {
        const recent = chats.items.find(c => c.record_date === scopeDate);
        if (recent) void openChat(recent.id); else void start("setup");
      }}>AI 分析</Button><Button disabled={busy} onClick={() => void start("external")}>录入总结</Button><Button onClick={() => { setTagOpen(true); setTagDirty(false); }}>标签库</Button></div>
    </div>
    {error ? <Alert type="error" content={error} action={<Button onClick={() => setTick(v => v + 1)}>重试加载</Button>} /> : null}
    {!open && saveError ? <Alert type="error" content={saveError} /> : null}
    <div className="diary-filters"><Input aria-label="搜索总结" placeholder="搜索已确认总结、标题或关键词" value={q} onChange={setQ} />
      <select aria-label="按标签筛选" value={filterTag ?? ""} onChange={e => setFilterTag(e.target.value ? Number(e.target.value) : undefined)}><option value="">全部标签</option>{tags.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
      <Checkbox checked={onlyDay} disabled={!scopeDate} onChange={setOnlyDay}>仅查看所选日记当天</Checkbox>
    </div>
    <div className="diary-layout">
      <Card title={`已确认总结 · ${summaries.count}`}>
        {!summaries.items.length ? <Empty description="暂无已确认总结" /> : summaries.items.map(s => <button key={s.id} className="diary-list-item" onClick={() => void viewSummary(s)}>
          <small>{s.record_date} · {s.source_note || s.source_type}{!s.markdown_saved ? " · 文件待保存" : ""}</small><strong>{s.title || "日记总结"}</strong><span>{markdownPreviewText(s.body)}</span><span>{s.tags.map(t => t.name).join("、")}</span>
        </button>)}
        {summaries.count > 30 ? <Pagination total={summaries.count} pageSize={30} current={page} onChange={setPage} simple /> : null}
      </Card>
      <Card title={`讨论记录 · ${chats.count}`} extra={<Button disabled={busy} onClick={() => void start("setup")}>新建讨论</Button>}>
        {!chats.items.length ? <Empty description="暂无本项目讨论记录" /> : chats.items.map(c => <button className="diary-list-item" key={c.id} onClick={() => void openChat(c.id)}>
          <small>{c.record_date} · {c.generation_status === "running" ? "生成中" : c.generation_status === "failed" ? "本轮未完成" : "已保存"}</small><strong>{c.title}</strong><span>{c.question || "查看完整问答或继续讨论"}</span>
        </button>)}
        {chats.count > 30 ? <Pagination total={chats.count} pageSize={30} current={chatPage} onChange={setChatPage} simple /> : null}
      </Card>
    </div>
    <Drawer visible={open} width="min(1180px, 96vw)" title={mode === "setup" ? "AI 分析 · 新建讨论" : mode === "chat" ? "AI 分析 · 讨论与总结" : readOnly ? "已确认总结" : "录入总结"} maskClosable={false} onCancel={() => void close()} footer={<div className="diary-editor-actions">
      <Button disabled={busy || draftSaving} onClick={() => void close()}>关闭</Button>
      {mode === "setup" ? <Button type="primary" loading={busy} disabled={!modelReady || !diaryIds.length} onClick={() => void createChat()}>开始分析</Button> : readOnly ? <Button onClick={() => { setSummaryPreview(false); setMode("external"); }}>编辑总结</Button> : <Button type="primary" loading={busy} disabled={!!blocked || !!session?.needs_summary} onClick={() => void confirmSummary()}>{editing ? "确认更新" : "确认保存"}</Button>}
    </div>}>
      <div className="stack">
        {saveError ? <Alert type="error" content={saveError} action={session && dirty ? <Button onClick={() => void persistDraft().catch(() => {})}>重试保存进度</Button> : undefined} /> : null}
        {(mode === "setup" || mode === "external") ? <>
          <label>归属日期 <input aria-label="总结日期" type="date" value={date} disabled={!!blocked} onChange={e => { const v = e.target.value; setDate(v); void work(async () => { await loadDay(v, []); }); }} /></label>
          <div className="stack"><strong>{mode === "setup" ? "分析原文" : "总结来源原文"} · 已选 {diaryIds.length} 条日记</strong>
            {mode === "setup" ? <p>新建讨论默认选中当天全部日记，可取消不相关条目；从已有总结继续讨论时沿用其原文范围。只分析勾选内容，不自动读取其他日期日记。</p> : null}
            {dayDiaries.length ? dayDiaries.map(d => <Checkbox key={d.id} disabled={!!blocked} checked={diaryIds.includes(d.id)} onChange={checked => setDiaryIds(ids => choose(ids, d.id, checked))}>{d.record_date} · {d.title || "未命名日记"} · {d.body.slice(0, 80)}</Checkbox>) : <p>当天无规范日记。录入总结时可独立保存，请注明来源。</p>}</div>
        </> : <p className="diary-file">{mode === "chat" ? "分析日期" : "归属日期"}：{date} · {mode === "chat" ? `本次选中 ${diaryIds.length} 条日记` : `总结来源：${diaryIds.length} 条日记原文`}</p>}
        {mode === "setup" ? <><label>关注问题<Input.TextArea aria-label="关注问题" value={question} onChange={setQuestion} autoSize={{ minRows: 2, maxRows: 5 }} /></label><label>个人背景（可选，仅用于本次讨论）<Input.TextArea aria-label="讨论背景" value={background} onChange={setBackground} autoSize={{ minRows: 2, maxRows: 4 }} /></label>
          {editing ? <Alert content="将把当天已有总结作为讨论背景；新的总结确认前不会替换已保存内容。" /> : null}
        </> : null}
        {!readOnly ? <div className="diary-model-consent"><p>模型：{runtime ? `${runtime.display_name} / ${runtime.model}` : "未配置"}</p>{!modelReady ? <Alert type="warning" content="请在设置中配置并启用模型；仍可手工录入总结。" /> : null}
          <Checkbox checked={consent} disabled={!!blocked} onChange={setConsent}>{mode === "external" ? "授权将当前总结和标签定义发送给该模型以建议标签" : "授权将选中的原文、背景、该会话完整问答及标签定义发送给该模型"}</Checkbox>
        </div> : null}
        {mode === "chat" ? <>
          <details><summary>查看分析原文（{diaryIds.length} 条）、问题与背景</summary>{originalDetails()}<p>问题：{session?.question}</p><p>背景：{session?.background || "未填写"}</p></details>
          <div className="diary-discussion-layout"><div className="stack"><h3>完整讨论</h3>
            {(session?.messages ?? []).map(m => <article className={`diary-chat-message ${m.role}`} key={m.id}><small>{m.role === "user" ? "你" : "投资导师"} · {new Date(m.created_at).toLocaleString()}{m.model ? ` · ${m.model}` : ""}{m.status !== "complete" ? ` · ${m.status === "pending" ? "问题已保存，待生成" : m.status === "running" ? "生成中" : "本轮未完成"}` : ""}</small>{m.role === "assistant" ? <MarkdownReport text={m.body} presentation="text" /> : <div className="diary-message-text">{m.body}</div>}</article>)}
            {session?.last_error ? <Alert type="warning" content={session.last_error} /> : null}
            {pending ? <Button disabled={!!blocked || !modelReady} loading={busy} onClick={() => void generate(pending.task, pending)}>生成 / 重试本轮</Button> : null}
            <Input.TextArea aria-label="讨论问题" disabled={!!blocked || !!pending} value={input} onChange={setInput} autoSize={{ minRows: 3, maxRows: 7 }} placeholder="提出疑问、补充情况或纠正理解……" />
            <div className="diary-editor-actions"><Button disabled={!!blocked || !!pending || !modelReady} onClick={() => void generate("discuss")}>发送问题</Button><Button disabled={!!blocked || !!pending || !modelReady} onClick={() => void generate("summarize")}>整理总结</Button></div>
          </div><div className="stack">{summaryEditor()}</div></div>
        </> : mode !== "setup" ? summaryEditor() : null}
      </div>
    </Drawer>
    <Drawer visible={tagOpen} title="标签库" width={620} maskClosable={false} onCancel={() => { if (!busy && (!tagDirty || window.confirm("标签编辑未保存，确定关闭吗？"))) { setTagOpen(false); setTagDirty(false); } }} footer={null}>
      <div className="stack">{saveError ? <Alert type="error" content={saveError} /> : null}
        <p>名称简洁，定义说明使用边界。同义表达可设为别名；改名保留已有总结关联。</p>
        {tags.map(t => <button key={t.id} className="diary-list-item" onClick={() => { if (!tagDirty || window.confirm("放弃未保存的标签编辑吗？")) { setTagEdit(t.id); setTagDraft({ name: t.name, definition: t.definition, aliases: t.aliases }); setTagAliasText(t.aliases.join("、")); setTagDirty(false); } }}><strong>{t.name}</strong><span>{t.definition}</span><small>{t.aliases.join("、")}</small></button>)}
        <Button onClick={() => { if (!tagDirty || window.confirm("放弃未保存的标签编辑吗？")) { setTagEdit(undefined); setTagDraft({ name: "", definition: "", aliases: [] }); setTagAliasText(""); setTagDirty(false); } }}>新增标签</Button>
        <label>标签名称<Input aria-label="标签名称" value={tagDraft.name} maxLength={40} onChange={name => { setTagDraft(v => ({ ...v, name })); setTagDirty(true); }} /></label>
        <label>定义与使用边界<Input.TextArea aria-label="标签定义" value={tagDraft.definition} onChange={definition => { setTagDraft(v => ({ ...v, definition })); setTagDirty(true); }} /></label>
        <label>别名<Input aria-label="标签别名" value={tagAliasText} onChange={v => { setTagAliasText(v); setTagDraft(t => ({ ...t, aliases: words(v) })); setTagDirty(true); }} /></label>
        <Button type="primary" loading={busy} onClick={() => void work(async () => { const result = await api.saveInvestmentTag(tagDraft, tagEdit); setTagEdit(result.item.id); setTagDirty(false); setTags((await api.investmentTags()).items); setTick(v => v + 1); if (result.file_errors?.length) setSaveError("标签已保存，部分总结文件待重试。"); else Message.success("标签已保存"); })}>保存标签</Button>
        {tagEdit ? <div className="diary-filters"><select aria-label="合并目标标签" value={mergeTarget ?? ""} onChange={e => setMergeTarget(e.target.value ? Number(e.target.value) : undefined)}><option value="">选择合并到的标签</option>{tags.filter(t => t.id !== tagEdit).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select><Button disabled={!mergeTarget || busy} onClick={() => { if (mergeTarget && window.confirm("将迁移关联并保留旧名称为别名，确认合并吗？")) void work(async () => { const result = await api.mergeInvestmentTag(tagEdit, mergeTarget); setTags((await api.investmentTags()).items); setTagEdit(undefined); setTagDraft({ name: "", definition: "", aliases: [] }); setTagDirty(false); setTick(v => v + 1); if (result.file_errors.length) setSaveError("标签已合并，部分总结文件待重试。"); }); }}>合并标签</Button></div> : null}
      </div>
    </Drawer>
  </div>;

  function summaryEditor() {
    return <div className="stack diary-summary-editor"><h3>{readOnly ? "已确认总结" : "待保存总结"}</h3>
      {session?.needs_summary ? <Alert type="warning" content="讨论已更新，请先整理总结再确认。" /> : null}
      {session ? <small>{draftSaving ? "正在保存讨论进度…" : dirty ? "候选修改待保存" : "讨论与候选进度已保存；正式总结仍需确认"}</small> : null}
      <label>标题<Input aria-label="总结标题" value={draft.title} disabled={readOnly || !!blocked} maxLength={200} onChange={title => update({ title })} /></label>
      <div className="stack"><div className="diary-heading"><strong>总结正文</strong>{!readOnly ? <Button size="small" onClick={() => setSummaryPreview(v => !v)}>{summaryPreview ? "编辑正文" : "预览正文"}</Button> : null}</div>
        {readOnly || summaryPreview ? <div className="diary-summary-preview" aria-label="总结正文预览">{draft.body.trim() ? <MarkdownReport text={draft.body} presentation="text" /> : <p>暂无总结正文。</p>}</div> : <Input.TextArea aria-label="总结正文" value={draft.body} disabled={!!blocked} autoSize={{ minRows: 10, maxRows: 28 }} onChange={body => update({ body })} />}
      </div>
      <div className="diary-tags">{tags.map(t => <Checkbox key={t.id} title={t.definition} checked={draft.tag_ids.includes(t.id)} disabled={readOnly || !!blocked} onChange={checked => update({ tag_ids: choose(draft.tag_ids, t.id, checked) })}>{t.name}</Checkbox>)}</div>
      {!readOnly ? <Button disabled={!!blocked || !modelReady || !draft.body.trim()} onClick={() => void work(async () => { if (!consent) throw Error("请先勾选模型发送授权"); const result = await api.suggestDiaryTags(draft.body, consent); update({ ...result, accepted_new_tags: [] }); })}>建议标签</Button> : null}
      {draft.new_tags.map((t, i) => <div className="diary-new-tag" key={i}><Checkbox checked={draft.accepted_new_tags.includes(i)} disabled={readOnly || !!blocked} onChange={checked => update({ accepted_new_tags: choose(draft.accepted_new_tags, i, checked) })}>确认新增此标签</Checkbox>
        <Input aria-label={`新标签名称${i + 1}`} disabled={readOnly || !!blocked} value={t.name} onChange={name => update({ new_tags: draft.new_tags.map((v, j) => j === i ? { ...v, name } : v) })} />
        <Input.TextArea aria-label={`新标签定义${i + 1}`} disabled={readOnly || !!blocked} value={t.definition} onChange={definition => update({ new_tags: draft.new_tags.map((v, j) => j === i ? { ...v, definition } : v) })} />
        <Button disabled={readOnly || !!blocked} onClick={() => update({ new_tags: draft.new_tags.filter((_, j) => i !== j), accepted_new_tags: draft.accepted_new_tags.filter(j => j !== i).map(j => j > i ? j - 1 : j) })}>移除此建议</Button>
      </div>)}
      {!readOnly ? <Button disabled={!!blocked} onClick={() => update({ new_tags: [...draft.new_tags, { name: "", definition: "", aliases: [] }] })}>填写新标签</Button> : null}
      <label>关键词<Input aria-label="总结关键词" disabled={readOnly || !!blocked} value={keywordText} onChange={v => { setKeywordText(v); update({ keywords: words(v) }); }} /></label>
      <label>来源<select aria-label="总结来源" disabled={readOnly || !!blocked || !!session} value={source} onChange={e => setSource(e.target.value as DiarySummaryInput["source_type"])}><option value="external_discussion">外部讨论</option><option value="manual">手工整理</option><option value="in_app_ai">本项目分析</option></select></label>
      <label>来源说明<Input aria-label="总结来源说明" disabled={readOnly || !!blocked || !!session} value={sourceNote} onChange={setSourceNote} placeholder="例如 ChatGPT、DeepSeek 或其他来源" /></label>
      {editing ? <><p className="diary-file">阅读文件：{editing.markdown_path}</p>{!editing.markdown_saved ? <Button onClick={() => void work(async () => { const result = await api.retrySummaryMarkdown(editing.id); setEditing(result.item); setTick(v => v + 1); if (!result.markdown_saved) setSaveError(result.message); else Message.success("文件已保存"); })}>重试总结文件保存</Button> : null}</> : null}
      {readOnly ? <div className="stack"><strong>总结来源 · {diaryIds.length} 条日记原文</strong>{originalDetails()}<strong>关联讨论</strong>{sessionIds.length ? sessionIds.map(id => <Button key={id} onClick={() => void openChat(id)}>查看讨论 {id}</Button>) : <p>无本项目讨论记录</p>}<Button onClick={() => void start("setup", editing ?? undefined)}>从总结继续讨论</Button></div> : null}
    </div>;
  }

  function originalDetails() {
    return selectedOriginals.length ? selectedOriginals.map(d => <details className="diary-source" key={d.id}><summary>{d.record_date} · {d.title || "未命名日记"}</summary><div className="diary-original">{d.body}</div></details>) : <p>未关联原文，请查看来源说明。</p>;
  }
}
