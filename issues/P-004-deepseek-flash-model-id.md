---
schema: project-memory/v1
kind: issue
id: P-004
title: "更新 DeepSeek Flash 模型 ID"
status: closed
created: "2026-10-08"
updated: "2026-10-08"
changes: ["C-003"]
related: []
evidence: ["backend/app/services/ai_runtime.py", "backend/app/config.py", ".env.example", "backend/app/services/profile_agent.py"]
closed_reason: "配置与备用值已统一为 DeepSeek 当前 Flash 模型 ID"
closed_result: "默认值、可选项、环境变量示例和 Agent 备用值均使用 deepseek-flash"
---

# P-004：更新 DeepSeek Flash 模型 ID

## 目标与完成条件

将项目模型配置中的旧 Flash API ID `deepseek-v4-flash` 改为 `deepseek-flash`，保证配置页选项、环境变量默认值和代码备用值一致。

## 当前进度与结论

2026-10-08 已完成 C-003。代码内模型模板、环境默认值、Agent 备用值和 `.env.example` 已统一更新。数据库中此前保存的模型配置由用户在 AI 配置中心重新选择并保存；本次未迁移运行数据库。
