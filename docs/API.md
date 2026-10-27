# API Contract

2026-10-27 按当前源码核对。本页是主要接口与语义索引，不是所有响应字段的完整副本；字段以路由、Pydantic 请求模型及服务返回为准。已运行服务的 `/docs`、`/openapi.json` 可查看声明契约；对 `dict` 类型请求仍需查看相应服务校验。本次核对未启动服务或调用真实接口。

## 账户账本与组合收益

入口：[`routers/portfolio.py`](../backend/app/routers/portfolio.py)、[`services/portfolio/`](../backend/app/services/portfolio/)、[`前端请求与类型`](../frontend/src/features/portfolio/api.ts)。Agent 需要金额、成本与收益时优先复用这条计算链，不能自行从成交价生成市值报价。

| 接口 | 用途与边界 |
|---|---|
| `GET /api/portfolio/overview` | 当前资产、曲线、记录及账户范围；`account_id` 默认 `all`，可选 `at`、`code`、`view`。`view` 为 `current`、`chart`、`records`、`full`，后端默认 `full`，前端按用途选择精简视图。 |
| `GET /api/portfolio/point` | 精确读取历史节点；使用 `at`、`event_type`、`owner_id` 及可选 `record_id`、`account_id`、`code`，不能只凭显示日期混合当日多笔事件。 |
| `GET /api/portfolio/closed` | 阶段清仓明细；支持 `account_id`、`start`、`end`、`keyword`。 |
| `GET /api/portfolio/accounts/{account_id}/opening` | 返回 `confirmed`、起点资料和核对列表；未建档时是待确认来源，不代表已经写入期初。 |
| `POST /api/portfolio/accounts/{account_id}/opening/preview` | 起点试算；可选 `correction`，不持久化试算账目。 |
| `PUT /api/portfolio/accounts/{account_id}/opening` | 保存或通过 `correction=true` 纠正起点，需要明确的用户操作。 |
| `POST /api/portfolio/trades` | 保存买卖，维护数量、成本和现金；不写市值价。 |
| `PUT /api/portfolio/trades/{record_id}` | 纠正原买卖并校验重放结果。 |
| `POST /api/portfolio/events` | 保存估值、资金、分红等事项，`kind`、`effective_at`、`data` 由服务校验。 |
| `PUT /api/portfolio/events/{record_id}` | 纠正原事项；分红与资金不重复入账。 |
| `DELETE /api/portfolio/trades/{record_id}` | 作废买卖并重算，不等于真实卖出。 |
| `DELETE /api/portfolio/events/{record_id}` | 作废事项并重算，不是通用硬删除接口。 |
| `POST /api/portfolio/accounts/{account_id}/history/preview` | 更早历史补录试算与差异核对。 |
| `POST /api/portfolio/accounts/{account_id}/history` | 用户确认后的历史重建，不自动补造资金以抹平差异。 |
| `GET /api/portfolio/accounts/{account_id}/sources` | 查看旧导入资料及其状态，不把它作为第二套实时账本。 |
| `PATCH /api/portfolio/accounts/{account_id}/sources/{record_id}` | 旧来源资料的停止核对、删除或恢复；具体字段见 `source_records.py`。 |
| `POST /api/portfolio/accounts/{account_id}/sources/reconcile` | 主动核对 `source_ids` 选中的资料；未匹配不能解读为零持仓。 |
| `PUT /api/portfolio/securities/name` | 修改 `code`、`name`，可带 `market`；同步既有名称字段，不重算金额。 |

累计盈亏、累计净投入、累计收益率与统计期盈亏/净值收益率分别返回；历史结转不增加现金或持仓成本。未知值应保留为空及具体缺失项，不在 Agent 输入中补成零。旧页面兼容投影不保证保留所有未知语义，尚待 P-009 复核。

## 账户与公共行情/新闻

入口：[`main.py`](../backend/app/main.py)、[`routers/data_sources.py`](../backend/app/routers/data_sources.py)、[`services/data_sources.py`](../backend/app/services/data_sources.py)、[`services/sync.py`](../backend/app/services/sync.py)。

| 接口 | 用途与边界 |
|---|---|
| `GET /api/accounts` | 账户列表与摘要，返回 `items`、`count`。 |
| `POST /api/accounts` | 新建手工账户。 |
| `PATCH /api/accounts/{account_id}` | 修改账户配置；来源平台和公共行情提供方分开。 |
| `DELETE /api/accounts/{account_id}` | 删除账户，属于数据管理操作，不能作为分析工具默认开放。 |
| `GET /api/data/accounts/{account_id}/overview` | 账户持仓、成交、来源状态及账本投影等页面资料。 |
| `GET /api/data-sources` | 免费/付费目录、已实现能力、配置字段和脱敏配置状态。 |
| `PUT /api/data-sources/{provider_id}` | 保存来源配置；敏感字段空字符串保留原值，显式 `null` 清除。 |
| `POST /api/data-sources/{provider_id}/check` | 用 `data_type` 和可选 `sample` 检测实际来源，检查结果会更新配置状态，但不写账户估值或报价。 |
| `POST /api/data/accounts/{account_id}/providers/check` | 检测指定账户的来源能力与连接状态。 |
| `POST /api/data/accounts/{account_id}/market-data/pull` | 请求体 `{"data_type":"quote"}` 或 `{"data_type":"news"}`；手动取数并保存成功部分。 |

行情更新先请求并保存所需 FX，再取价格；FX 失败沿用最近有效记录及原日期，无有效记录时明确缺失。基金使用正式单位净值，美股使用已结束交易日价格，XAU 换算为参考估值；具体来源覆盖以目录和 P-011 为准。

拉取结果包含 `status`、`message`、新增/更新/日线数量、`failures`、`fx_updates` 和账户 `provider_states`。批次状态包括 `success`、`partial`、`failed`、`empty`；来源级错误另外区分缺依赖、编码、超时、授权、不支持等原因，不能仅凭 HTTP 200 判断全部成功。

“更新全部市值”由前端依次调用上述单账户拉取接口，不存在另一个后端全账户批量接口，也不是富途全量账户同步。更新结束重新读取组合，新闻不随该按钮更新；离开页面后不派发后续账户。

## 日记、讨论、总结与标签

入口：[`diary_routes.py`](../backend/app/diary_routes.py)、[`diary_analysis_routes.py`](../backend/app/diary_analysis_routes.py)、[`diary_schemas.py`](../backend/app/diary_schemas.py)。

| 接口 | 用途 |
|---|---|
| `GET /api/diaries` | 原文列表，支持日期、关键词及分页。 |
| `POST /api/diaries` | 保存新原文及约定 Markdown 文件。 |
| `GET /api/diaries/{diary_id}` | 读取原文。 |
| `PUT /api/diaries/{diary_id}` | 修改原文；分析结果不自动覆盖原文。 |
| `POST /api/diaries/{diary_id}/retry-markdown` | 重试原文文件写入。 |
| `GET /api/diary-discussions` | 查询已保存讨论，可按日期或日记筛选。 |
| `POST /api/diary-discussions` | 创建选定日记范围的讨论。 |
| `GET /api/diary-discussions/{session_id}` | 恢复讨论及候选，不调用模型。 |
| `PUT /api/diary-discussions/{session_id}` | 保存候选编辑，不等于确认有效总结。 |
| `POST /api/diary-discussions/{session_id}/messages` | 保存用户问题。 |
| `POST /api/diary-analysis/analyze` | 首次分析；参数含 `session_id`、`message_id`、`consent_external_ai`。 |
| `POST /api/diary-analysis/discuss` | 后续讨论，沿用同一会话与显式授权。 |
| `POST /api/diary-analysis/summarize` | 整理候选总结，不自动升级为已确认规则。 |
| `POST /api/diary-analysis/suggest-tags` | 对当前总结建议标签，需要单独的外部传输授权。 |
| `GET /api/diary-summaries` | 按日期、关键词、标签查询确认总结。 |
| `GET /api/diary-summaries/{summary_id}` | 读取确认总结与来源。 |
| `POST /api/diary-summaries` | 用户确认后保存总结。 |
| `PUT /api/diary-summaries/{summary_id}` | 修改已保存总结。 |
| `POST /api/diary-summaries/{summary_id}/retry-markdown` | 重试总结文件写入。 |
| `GET /api/investment-tags` | 读取标签库。 |
| `POST /api/investment-tags` | 新增用户确认的标签。 |
| `PUT /api/investment-tags/{tag_id}` | 修改标签名称、定义及别名。 |
| `POST /api/investment-tags/{tag_id}/merge` | 合并标签并保留关联。 |

已有列表查询不等于已实现跨历史日记的 Agent 检索或 RAG。未来接入要保持原文、AI 分析、候选、已确认总结及用户反馈的语义区别，并确认版本、来源范围与外部模型传输权限。

## 分析工作流与模型配置

入口：[`main.py`](../backend/app/main.py)、[`profile_agent.py`](../backend/app/services/profile_agent.py)、[`profile_agent_tools.py`](../backend/app/services/profile_agent_tools.py)、[`profile_workflows.py`](../backend/app/services/profile_workflows.py)。

| 接口 | 用途与边界 |
|---|---|
| `GET /api/ai/providers` | 模型服务商目录。 |
| `GET /api/ai/config` | 当前运行配置的脱敏状态。 |
| `PUT /api/ai/config` | 保存用户选择的模型配置。 |
| `POST /api/ai/config/test` | 显式检测模型服务。 |
| `GET /api/profile/preferences` | 读取投资偏好。 |
| `PATCH /api/profile/preferences` | 用户确认后更新偏好，不默认授权 Agent 写入。 |
| `POST /api/profile/ai-workflows/{workflow_type}` | 创建 `customer_profile`、`portfolio_diagnosis` 或 `asset_allocation` 任务；可指定 `account_id`，请求可含问题和外部模型授权。 |
| `GET /api/profile/ai-workflows` | 查询任务列表。 |
| `GET /api/profile/ai-workflows/{run_id}` | 读取已有任务状态、输出及记录。 |
| `GET /api/profile/ai-workflows/{run_id}/stream` | SSE 执行与报告流；会推进工作流，不能当作普通历史查询。 |
| `POST /api/profile/ai-workflows/{run_id}/cancel` | 取消任务。 |
| `DELETE /api/profile/ai-workflows/{run_id}` | 删除已有任务记录。 |
| `GET /api/profile/ai-workflows/{run_id}/download` | 下载已有 Markdown 报告。 |

当前三类分析仍采用固定工具序列。工具注册、执行轨迹与报告校验不等于动态规划或模型效果已验收；下一阶段先使用 [需求讨论提示词](agent-next-stage-kickoff.md) 明确任务与框架取舍。

## 工作台基础接口

## `GET /api/health`

返回服务、数据库、OpenD 连接和 SQLite 加密准备状态。

## `POST /api/sync/manual`

触发可选富途账户的手动全量同步；未启用富途会跳过。它不等于“更新全部市值”，不会在免费来源失败时自动启用付费源。同步失败会记录原因。

## `GET /api/sync/status`

返回最近一次同步任务状态、时间、失败原因和新增/更新数量。

## `GET /api/dashboard`

返回首页需要的组合摘要、今日行动清单和同步状态。

## `GET /api/positions`

返回持仓或兼容投影。金额与未知值的完整语义优先查组合账本接口。可选 query 参数：

- `layer`：按仓位类型筛选。
- `account_id`：账户范围，默认 `all`。

## `GET /api/positions/{code}`

返回单个标的的持仓详情、关联决策卡和最近一次 AI 分析。

## `POST /api/positions/{code}/ai-analysis`

使用当前有效模型配置为单个标的生成分析；配置可来自本地设置或环境变量，不固定为 DeepSeek。发送外部上下文前请求体须包含 `consent_external_ai: true`；本地规则降级须如实标识，不能冒充外部模型输出。以下 DeepSeek 返回仅为示例，不保证当前配置的服务商和模型与它相同。

返回：

```json
{
  "ai_analysis": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "status": "success",
    "output": {
      "recommendation": "观察",
      "conclusion": "当前只适合复核和跟踪。",
      "reasons": [],
      "risks": [],
      "invalid_conditions": [],
      "missing_data": []
    }
  }
}
```

## `PATCH /api/positions/{code}/layer`

保存用户手动仓位类型修正。

请求：

```json
{
  "position_layer": "核心长期仓",
  "reason": "用户在工作台手动修正"
}
```

## `GET /api/review`

返回最近一次盘后复盘，包括组合摘要、建议回顾、用户行为摘要、后续表现评估和明日关注。

## `GET /api/profile`

返回最近一次用户交易画像，包括仓位分层比例、置信度和偏好标签。

## `GET /api/data/status`

返回同步任务和各数据源新鲜度状态。

## `POST /api/data/delete-local`

删除本地账户、持仓、成交、建议、提醒、复盘和同步记录。请求必须包含：

```json
{
  "confirmation": "DELETE_LOCAL_DATA"
}
```
