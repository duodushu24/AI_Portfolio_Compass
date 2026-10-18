---
schema: project-memory/v1
kind: issue
id: P-009
title: "功能设计与代码架构评审"
status: active
created: "2026-10-18"
updated: "2026-10-18"
changes: []
related: ["P-005", "P-006", "P-007", "P-008"]
evidence: ["README.md", "issues/solutions/P-005/S-002-account-ledger-performance.md", "issues/solutions/P-007/S-001-diluted-cost-dividend-accounting.md", "backend/app/services/portfolio/ledger.py", "backend/app/services/portfolio/performance.py", "backend/app/services/portfolio/service.py", "backend/tests/test_gf_import.py"]
next: "依据 P-010/C-023 实现和用户试用结果复核剩余问题，不自动扩展开发范围"
priority: high
tags: ["review", "architecture", "portfolio", "returns"]
---

# P-009：功能设计与代码架构评审

## 当前进度与授权

已按指定 architecture-design-review skill 完成基于 `400fc3ad327bab1eb6c02f57af338146173e4d75` 和全部相关未提交差异的评审；当时业务代码相对 71a00fb 未变。发现与建议已向用户交付。用户随后明确产品面向通用部署、低频资产配置管理，并授权实施账户起点与历史收益衔接，另见 [P-010](P-010-account-onboarding-profit-carry.md) / [C-023](../CODE_CHANGE_LOG/C-023-onboarding-profit-carry.md)。

本问题当前跟踪实施后的复核，不将新授权扩大到未确认的券商适配、Agent 工作流或正式账目改写。保留所有无关既有改动；公开记录仅用设计和虚构验证结果。

### 评审发现与本批处理

- P1：估值纠错丢失整体基准/交易日期；汇率来源与估算信息往返丢失。C-023 已修复表单保留及试算刷新问题。
- P2：明确成交金额在纠错中丢失、历史补录漏比人民币成本、旧详情不认可摊薄成本、申购独立费用漏扣。C-023 已处理；旧详情的全部特殊成本汇总和诊断输入未知值仍须复核，不能据此宣称整条兼容链一致。
- P2：同秒成交固定排在资金事件前，可能拒绝先入金后买入；本批未改事项顺序。
- 能力缺口：全部转托管后原阶段分红归属不可用，需先确认归属规则，未直接认定某种跨账户分配算法正确。
- 验证缺口：评审完成的定向检查为 33 通过、3 项旧预期失败；C-023 后续修正这些预期并定向通过，未运行完整测试集。

## 评审目标与有效边界

1. **功能设计和计算：** 以账户资产管理及收益计算为重点，检查建档/现金/持仓/成交事实、费用和资金流、唯一摊薄成本、分红抵扣、清仓再买入、原币与人民币收益、历史汇率沿用/补录/更正、整体基准和净值份额、周度观察/交易节点、账户纳入/移出、查询及纠错流程是否一致。区分实际缺陷、尚未支持的能力、数据不足和非阻塞优化，不以券商显示不同直接判定算法错误。
2. **代码架构及增量开发：** 使用 `D:/duodushu/ai_harness/skills/architecture-design-review/SKILL.md`，按其 `references/design-and-review.md` 检查职责、依赖方向、权威事实/派生状态、事务及缓存生命周期、接口契约、错误和回滚、测试证据，以及后续新功能应放置的模块和扩展路径。先核对账户/收益主链，再有依据地涉及导入、行情、复盘和诊断调用方；不以文件行数或模式偏好机械要求重构。

已确认约束：保留 React/Vite、FastAPI、SQLite；整体资产配置为主要视角，分账户继续记账但不恢复单账户主曲线；现金分红记账即视同到账并扣减成本，不建应收分红或区分除息归因；每周等不规则记录即可，不恢复精确每日历史；汇率优先本笔有效填写，否则沿用实际时间不晚于事件的最近保存记录，不造历史成本；日常以手工录入为主，不要求新的券商 API 或后续账单导入去重。

## 建议阅读与代码入口

先读 AGENTS.md 和 current_state.md，再读本页、P-005/P-007 的当前进度及两份现行 S；P-006/P-008 按涉及范围补充。C-017/C-018/C-019/C-021/C-022 提供最新规则与有限验证依据；性能细节查 C-016，只有追溯旧行为才读早期 C。S-001（P-005 的归档方案）不作为现行要求。

主链：`backend/app/routers/portfolio.py` → `services/portfolio/service.py` → `ledger.py` / `performance.py`，以及 `models.py`、`schemas.py`、`database.py` 的持久化契约；前端从 `App.tsx`、`features/portfolioViews.tsx`、`features/portfolio/`、`api.ts` 和 `requestCache.ts` 核对输入、刷新和展示。导入适配为 `services/portfolio/gf_import.py`，行情和复盘检查 `sync.py` / `trade_review.py` 的投影调用；不假定其他页面没有重复算法。

已有针对性测试位于 `test_portfolio_ledger.py`、`test_diluted_cost.py`、`test_historical_fx_usage.py`、`test_weekly_baseline.py`、`test_read_performance.py`、`test_gf_import.py`，前端有 `frontend/tests/requestCache.test.cjs`。源码和测试断言都要核对当前语义，不能用历史通过记录替代本次证据。

## 已知缺口与验收状态

原联合导入分红成本旧断言已由 C-023 修正并验证；本页保留初始失败作为评审证据，不再将其列为待修。完整测试、正式账户验收与剩余问题仍独立。

P-005/P-006/P-007/P-008 均有实施与有限验证记录，仍缺各自明确的实际用户验收，P-006 还缺黄金专用浏览器视觉检查；评审通过不自动关闭这些问题。P-001/P-003/P-004 已关闭，P-002 继续暂停。

## 有限交付条件

- 先形成当前实际功能与计算口径的一致认识，指出设计、源码、测试或文档之间的差异及影响；区分已确认事实和推断。
- 发现给出需求/约定、具体代码位置、触发例子、后果、严重性、建议处理与最小验证办法；按正确性风险和用户影响排序。
- 对后续增量开发给出有证据的模块边界与改动建议，区分必须调整和可选优化；不预设必须引入框架或重写。
- 标明审阅提交/diff 范围及静态检查、实际测试、未验证项；同一上下文自查不得称为独立审核。默认按风险选择检查，不跑无关全套测试。

评审结果优先更新本 P；复杂细化设计才新增所属 S。没有实施时不创建已实施 C，不把设计认可当成功能验收。
