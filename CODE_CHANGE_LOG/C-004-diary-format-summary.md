---
schema: project-memory/v1
kind: change
id: C-004
title: "日记 Markdown 展示、总结分工与原文范围说明"
status: closed
created: "2026-10-08"
updated: "2026-10-08"
issues: ["P-001"]
commits: ["04ea350c4e7de1f37278097ee62e488255a20abe"]
evidence: ["backend/app/services/diary_discussions.py", "backend/app/skills/diary_investment_mentor.md", "backend/app/skills/diary_analysis.md", "backend/app/skills/diary_discussion.md", "backend/app/skills/diary_summary.md", "frontend/src/features/DiaryAnalysisPanel.tsx", "frontend/src/features/portfolioViews.tsx", "frontend/src/styles.css"]
closed_reason: "本批次实施、直接相关回归与隔离页面检查完成"
closed_result: "Markdown 阅读与编辑预览、三种任务分工、原文数量及来源说明已实现；实际模型的凝练质量由 P-001 继续试用验收"
---

# C-004：日记 Markdown 展示、总结分工与原文范围说明

## 目标与范围

实施用户确认的 [P-001 / S-002](../issues/P-001-personal-records.md#s-002)。详细补充要求纳入 [S-001 设计](../issues/solutions/P-001/S-001-diary-workflow.md)第 3.1、3.3 节。解决正文格式不统一、分析与总结职责模糊，以及内部原文编号被误读为数量的问题；保留数据库结构、调用次数、讨论持久化、明确确认和正式总结保存边界。

## 实际修改与进度

共同教师提示词明确简洁 Markdown 及候选总结要求；分析、答疑、整理总结分别加载独立任务文件。分析保留机制和案例深度；答疑聚焦本轮；总结采用核心结论、依据与边界、有需要才写的待解决问题，普通日记参考 300—600 字，吸收纠正、去掉重复教学，不添加新观点或虚构共识。首次仍同次生成分析和候选，未增加自动模型调用或相似度拒绝。

现有 MarkdownReport 增加可选 text 展示模式，日记 AI 回复、总结阅读和预览复用同一解析能力；默认报告模式保留编号标题及原样式。日记模式使用普通标题与紧凑间距，不生成报告锚点或自动编号；用户消息与原文保持文字原样展示。总结编辑可切换预览，列表摘要清除常用 Markdown 标记，旧普通文本可读。不回写已有内容，不迁移数据库。

原文范围显示条数、日期和标题，可展开正文；新建讨论明确默认选择当天全部条目，用户可取消，不读取其他日期日记。从已确认总结继续时沿用其原文范围，总结详情明确列出来源原文。没有选择原文时“开始分析”不可用，服务端原有同日校验保留。

## 验证与结果

验证对应本批次提交前的上述源码，测试数据均为虚构记录，没有读取真实日记或调用外部模型。

- **后端关键回归**：`backend/.venv/Scripts/python.exe -m pytest tests/test_diary_discussions.py::test_complete_discussion_context_correction_recovery_and_confirm_gate --basetemp=../.runtime/diary-format-tests-approved -q`，1 passed。覆盖选中原文、初次调用、追问上下文及纠正、整理总结、确认前后边界和已完成请求重试不重复调用。未运行全套测试。
- **前端构建**：`npm run build` 通过 TypeScript 与 Vite；保留既有包体积提示。最初沙箱阻止 Vite 子进程和 pytest 临时目录访问，获自动批准后在隔离目录完成，未安装依赖。
- **隔离组件浏览器检查**：`.runtime/diary-format-check/check.cjs` 挂载实际 DiaryAnalysisPanel、MarkdownReport 与项目样式，接口由内存中的虚构数据替代。最终通过 Markdown 标题/无序与有序列表/加粗、普通文本兼容、HTML 作为文本显示、默认同日多条选择与取消、原文数量和原样正文、候选预览/编辑/确认/重开及关联回看、清洁列表摘要、默认报告编号展示检查，无未捕获页面异常。结果在忽略目录 `result.json`；测试服务器请求处理、断言选择范围、虚构响应时序及表达式换行曾作修正，最终通过。该检查不是完整工作台 HTTP 集成或真实模型质量验证。

总结凝练和投资判断仍需实际模型试用；300—600 字是提示目标，程序不保证字数、准确性或分析与总结语义差异。保留现有 Markdown 解析范围，本批次支持常用标题、列表、加粗等，并非完整 CommonMark 实现。

## Git 关联

实施提交：`04ea350`（完整哈希见 commits），消息关联 `[P-001][C-004]`。上述验证在该实施提交前针对本批次改动执行；2026-10-08 核对提交消息、改动文件和本记录归属后补录哈希，未重新执行业务测试。
