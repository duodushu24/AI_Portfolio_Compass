---
schema: project-memory/v1
kind: change
id: C-006
title: "日记提示词结构化与目录迁移"
status: closed
created: "2026-10-09"
updated: "2026-10-09"
issues: ["P-001"]
commits: ["1bdd01b936e1f473fcca47c77359f9acbfb92e18"]
evidence: ["backend/app/prompts/diary/base.md", "backend/app/prompts/diary/analyze.md", "backend/app/prompts/diary/discuss.md", "backend/app/prompts/diary/summary.md", "backend/app/services/diary_discussions.py", "backend/tests/test_diary_discussions.py"]
closed_reason: "审核后的提示词重写、迁移与直接相关验证已完成"
closed_result: "共同身份精炼、判断与任务结构明确，四份文件仅在 prompts/diary 维护；加载及关键流程验证通过，实际模型效果待试用"
---

# C-006：日记提示词结构化与目录迁移

## 目标与范围

落实用户审核通过的 P-001 S-004：重新推敲身份措辞与逻辑顺序，采用简单 Markdown 结构，区分共同原则与任务产物，并将四份模型调用文本从 skills 迁至 prompts/diary。调整加载、测试和有效文档引用，不改变前端、数据库、调用次数、上下文或确认保存机制。

## 实际修改

`base.md` 的身份压缩为一句，按角色与目标、判断原则、事实边界、表达要求组织；资产预期收益率、波动及相关性移到涉及配置问题时的判断方法，不强制每篇日记套用。分析、讨论分别组织目标、材料或推进方式、产物要求；summary 明确为两处复用的规范，集中定义来源、正文取舍、标签和核对。

迁移后只有 `backend/app/prompts/diary/{base,analyze,discuss,summary}.md` 一套维护文本，移除四份旧 skills 文件。`PROMPT_DIR` 定位新目录，集中映射任务文件；初次加载 base＋analyze＋summary，讨论加载 base＋discuss，整理加载 base＋summary，JSON 对象仍由代码指定。

README 增加维护入口；S-001 只修复提示词链接，不改历史设计；C-004/C-005 的 evidence 指向迁移后现行文件并注明历史文本由各自实施提交追溯，不将新提示词冒充为旧批次验证内容。P 与状态入口同步最新进度。

## 验证与结果

业务验证对应实施提交 `1bdd01b936e1f473fcca47c77359f9acbfb92e18`。从 backend 目录运行：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_diary_discussions.py::test_task_prompt_composition_keeps_summary_rules_out_of_discussion tests/test_diary_discussions.py::test_complete_discussion_context_correction_recovery_and_confirm_gate --basetemp=../.runtime/diary-prompt-migration-tests-20261009 -q
```

结果 **2 passed**：组合专项使用隔离标记文件验证各任务实际系统消息；关键回归使用迁移后的真实提示词文件和虚构模型，覆盖选定原文、分析、连续问答及纠正、整理、确认限制和正式保存，证明新路径可加载且原流程保持正常。数据及测试运行目录隔离，没有发送真实日记或调用真实外部模型。

检查有效引用、迁移后的唯一文件集及 Git 差异；项目记录按本地规则检查并收尾。未修改前端，不运行前端构建或无关全套测试。测试不证明实际模型的投资判断和表达质量；后续由用户试用，不据此关闭 P-001。

代码实施已本地提交，项目记录及引用修复随本批次单独收尾提交；保留无关既有改动，不推送。
