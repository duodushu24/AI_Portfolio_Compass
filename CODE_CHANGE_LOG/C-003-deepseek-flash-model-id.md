---
schema: project-memory/v1
kind: change
id: C-003
title: "DeepSeek Flash 模型 ID 更新"
status: closed
created: "2026-10-08"
updated: "2026-10-08"
issues: ["P-004"]
commits: []
evidence: ["backend/app/services/ai_runtime.py", "backend/app/config.py", ".env.example", "backend/app/services/profile_agent.py"]
closed_reason: "请求范围内的模型配置更新已完成"
closed_result: "DeepSeek Flash 默认项、可选项、环境变量示例和备用值统一为 deepseek-flash"
---

# C-003：DeepSeek Flash 模型 ID 更新

## 目标与范围

将模型配置中 `deepseek-v4-flash` 替换为 `deepseek-flash`，不触碰用户已保存的运行数据库或无关工作区改动。

## 实际修改与进度

更新 `backend/app/services/ai_runtime.py` 的默认模型、下拉可选模型和说明；更新 `backend/app/config.py` 与 `.env.example` 的环境默认值；更新 `backend/app/services/profile_agent.py` 的备用默认值。

## 验证与结果

静态检索确认以上模型配置位置已统一。未运行测试或调用真实 DeepSeek API；用户数据库中已保存的模型值仍需在 AI 配置中心重新选择并保存。
