---
schema: project-memory/v1
kind: issue
id: P-009
title: "功能设计与代码架构评审"
status: open
created: "2026-10-18"
updated: "2026-10-18"
changes: []
related: ["P-005", "P-006", "P-007", "P-008"]
evidence: ["README.md", "issues/solutions/P-005/S-002-account-ledger-performance.md", "issues/solutions/P-007/S-001-diluted-cost-dividend-accounting.md", "backend/app/services/portfolio/ledger.py", "backend/app/services/portfolio/performance.py", "backend/app/services/portfolio/service.py", "backend/tests/test_gf_import.py"]
next: "在新对话只读评审账户资产/收益设计及代码架构，使用指定 architecture-design-review skill"
priority: high
tags: ["review", "architecture", "portfolio", "returns"]
---

# P-009：功能设计与代码架构评审

## 当前进度与授权

用户准备在新对话开展两部分评审，本轮仅整理开发记录和此入口，**尚未开始全面评审**。最近应用代码核对基线为 `71a00fb7a5f115199be5dd1aa5619c81ce53e6cd`（含 C-022）；新对话应重新核对 HEAD 与完整未提交 diff，不只看最后一次修补。既有无关未提交文件不得纳入评审结论或自动删除。

评审先只读，不自动重构、安装依赖、变更规则或改动真实账目。不因发现问题而扩展实施授权，不启动已暂停的 P-002。私有金额、持仓、来源原表和运行库不写入公开记录；如需要具体例子，优先虚构数据及隔离环境。

## 评审目标与有效边界

1. **功能设计和计算：** 以账户资产管理及收益计算为重点，检查建档/现金/持仓/成交事实、费用和资金流、唯一摊薄成本、分红抵扣、清仓再买入、原币与人民币收益、历史汇率沿用/补录/更正、整体基准和净值份额、周度观察/交易节点、账户纳入/移出、查询及纠错流程是否一致。区分实际缺陷、尚未支持的能力、数据不足和非阻塞优化，不以券商显示不同直接判定算法错误。
2. **代码架构及增量开发：** 使用 `D:/duodushu/ai_harness/skills/architecture-design-review/SKILL.md`，按其 `references/design-and-review.md` 检查职责、依赖方向、权威事实/派生状态、事务及缓存生命周期、接口契约、错误和回滚、测试证据，以及后续新功能应放置的模块和扩展路径。先核对账户/收益主链，再有依据地涉及导入、行情、复盘和诊断调用方；不以文件行数或模式偏好机械要求重构。

已确认约束：保留 React/Vite、FastAPI、SQLite；整体资产配置为主要视角，分账户继续记账但不恢复单账户主曲线；现金分红记账即视同到账并扣减成本，不建应收分红或区分除息归因；每周等不规则记录即可，不恢复精确每日历史；汇率优先本笔有效填写，否则沿用实际时间不晚于事件的最近保存记录，不造历史成本；日常以手工录入为主，不要求新的券商 API 或后续账单导入去重。

## 建议阅读与代码入口

先读 AGENTS.md 和 current_state.md，再读本页、P-005/P-007 的当前进度及两份现行 S；P-006/P-008 按涉及范围补充。C-017/C-018/C-019/C-021/C-022 提供最新规则与有限验证依据；性能细节查 C-016，只有追溯旧行为才读早期 C。S-001（P-005 的归档方案）不作为现行要求。

主链：`backend/app/routers/portfolio.py` → `services/portfolio/service.py` → `ledger.py` / `performance.py`，以及 `models.py`、`schemas.py`、`database.py` 的持久化契约；前端从 `App.tsx`、`features/portfolioViews.tsx`、`features/portfolio/`、`api.ts` 和 `requestCache.ts` 核对输入、刷新和展示。导入适配为 `services/portfolio/gf_import.py`，行情和复盘检查 `sync.py` / `trade_review.py` 的投影调用；不假定其他页面没有重复算法。

已有针对性测试位于 `test_portfolio_ledger.py`、`test_diluted_cost.py`、`test_historical_fx_usage.py`、`test_weekly_baseline.py`、`test_read_performance.py`、`test_gf_import.py`，前端有 `frontend/tests/requestCache.test.cjs`。源码和测试断言都要核对当前语义，不能用历史通过记录替代本次证据。

## 已知缺口与验收状态

`backend/tests/test_gf_import.py::test_joint_import_cash_cost_scope_and_idempotency` 的虚构样本净分红为 5，当前仍断言剩余成本 41；C-018 已复现其与 C-017 分红扣成本口径冲突。按现行公式应核对为 36，本轮没有修复或重跑，P-007 继续跟踪。评审应验证影响，不能以此推断产品账目错误，也不能忽略后宣称全套通过。

P-005/P-006/P-007/P-008 均有实施与有限验证记录，仍缺各自明确的实际用户验收，P-006 还缺黄金专用浏览器视觉检查；评审通过不自动关闭这些问题。P-001/P-003/P-004 已关闭，P-002 继续暂停。

## 有限交付条件

- 先形成当前实际功能与计算口径的一致认识，指出设计、源码、测试或文档之间的差异及影响；区分已确认事实和推断。
- 发现给出需求/约定、具体代码位置、触发例子、后果、严重性、建议处理与最小验证办法；按正确性风险和用户影响排序。
- 对后续增量开发给出有证据的模块边界与改动建议，区分必须调整和可选优化；不预设必须引入框架或重写。
- 标明审阅提交/diff 范围及静态检查、实际测试、未验证项；同一上下文自查不得称为独立审核。默认按风险选择检查，不跑无关全套测试。

评审结果优先更新本 P；复杂细化设计才新增所属 S。没有实施时不创建已实施 C，不把设计认可当成功能验收。
