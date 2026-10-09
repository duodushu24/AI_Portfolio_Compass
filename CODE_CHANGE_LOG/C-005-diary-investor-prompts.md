---
schema: project-memory/v1
kind: change
id: C-005
title: "职业投资者定位与日记任务提示词去重"
status: closed
created: "2026-10-09"
updated: "2026-10-09"
issues: ["P-001"]
commits: ["d61a3a3799deeee568f10baba89b9ca5fda2f719"]
evidence: ["backend/app/skills/diary_investment_mentor.md", "backend/app/skills/diary_analysis.md", "backend/app/skills/diary_discussion.md", "backend/app/skills/diary_summary.md", "backend/app/services/diary_discussions.py", "backend/tests/test_diary_discussions.py"]
closed_reason: "四份提示词及必要加载调整已完成并通过最小相关验证"
closed_result: "共同身份、开放分析与三种任务职责分离，初次分析复用总结规则；实际模型效果继续由 P-001 试用验收"
---

# C-005：职业投资者定位与日记任务提示词去重

## 目标与范围

实施 P-001 S-003。用户要求职业投资者身份、深厚资产配置研究基础和行为金融/投资心理学研究能力，资产配置核心包括预期收益率、波动水平与资产相关性；删除具体话题清单，不给予不必要的分析限制。针对共同提示词覆盖其他文件的问题，分离身份原则与任务要求，不改存储、前端、确认流程或记忆策略。

## 实际修改

共同提示词保留身份、研究基础、专业解释与事实依据、Markdown 和确认边界；去掉固定话题枚举及一到三个问题限制，明确不强制套用配置三要素或行为偏误框架。具体分析方向、知识与深度由日记和当前问题决定。

分析提示词负责初次理解原文及同时产出分析/候选的关系；讨论提示词负责识别追问与前文的联系、回应补充、检验和修正判断，不生成候选或标签。总结提示词集中管理来源、结论结构、参考篇幅、凝练与标签，标签库不作为研究话题边界。

由于初次分析同时生成候选，`build_messages()` 在 analyze 时加载共同＋分析＋总结规范，discuss 时加载共同＋讨论，summarize 时加载共同＋总结规范；JSON 返回形状仍由代码指定。总结文件本身不再指定只输出总结，避免与初次分析冲突。每轮仍一次模型调用；不增加自动压缩、跨会话检索或对用户已保存内容的改写。

## 验证与结果

验证对应实施提交 `d61a3a3799deeee568f10baba89b9ca5fda2f719`。在隔离目录使用虚构记录与模型替代，从 backend 目录执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_diary_discussions.py::test_task_prompt_composition_keeps_summary_rules_out_of_discussion tests/test_diary_discussions.py::test_complete_discussion_context_correction_recovery_and_confirm_gate --basetemp=../.runtime/diary-prompt-tests-20261009 -q
```

结果 **2 passed**。新增组合测试使用临时标记文件核对实际系统消息：初次包含分析和总结要求、讨论只含讨论要求、整理只含总结要求，所有任务均加载共同身份；既有回归覆盖选定原文、上下文及纠正、生成重试、待整理确认限制和正式保存。

未调用真实外部模型；测试证明文件组合与流程契约，不证明投资判断或凝练质量。未修改前端或数据库，未运行前端构建及无关全套测试。项目记录单独收尾提交，保留无关既有改动，不推送。
