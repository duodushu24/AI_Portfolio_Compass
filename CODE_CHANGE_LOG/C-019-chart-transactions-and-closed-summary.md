---
schema: project-memory/v1
kind: change
id: C-019
title: "历史持仓过滤、交易标记恢复与原币清仓摘要"
status: closed
created: "2026-10-18"
updated: "2026-10-18"
issues: ["P-005"]
commits: ["d0d5f04b7c56c537ef04fb5617d3da55971b7783"]
evidence: ["backend/app/services/portfolio/service.py", "backend/tests/test_read_performance.py", "backend/tests/test_weekly_baseline.py", "frontend/src/features/portfolio/ClosedPositions.tsx", "frontend/src/features/portfolio/PortfolioPanel.tsx", "frontend/src/features/portfolio/types.ts", "issues/solutions/P-005/S-002-account-ledger-performance.md"]
closed_reason: "针对性检查、正式重载及三处浏览器验收通过"
closed_result: "历史节点只展示当时非零持仓，周度曲线保留逐笔交易入口，单币种摘要直接展示原币盈亏"
---

# C-019：历史持仓过滤、交易标记恢复与原币清仓摘要

关联 [P-005](../issues/P-005-portfolio-return-history.md) 与 [S-002](../issues/solutions/P-005/S-002-account-ledger-performance.md)。处理用户在 C-018 页面验收中发现的三处问题，不调整账本、收益基准或成本/收益算法。

## 原因与修正

- 历史节点直接将完整账本 positions 交给表格，显示已清仓的零数量行。改为仅在展示时过滤非正数量，标记“当时持仓”；完整历史和清仓阶段继续保留。本次买卖另显示标的、方向、数量、价格和费用，全部卖出后也可查看该成交。
- 清仓主摘要固定采用 CNY，外币历史人民币成本或卖出时汇率未知时显示空值，虽原币结果完整也难以辨认。单币种查询按原币显示完整盈亏并明确币种；原币成本未知仍不输出完整合计，混合币种不直接相加。人民币缺失说明保留，不改成本或补造历史汇率。
- C-018 为连接周度观察线在前端过滤交易，造成交易标记遗漏。估值线仍仅用原估值点；独立交易行恢复真实成交，以北京时间同日分组，多笔可展开选择。API 精简视图增加少量成交描述，完整结果及详情不变；交易当时缺价仍无收益值，不以插值或成交价伪造整体收益。

## 验证与限制

- 8 项相关后端用例通过，覆盖精简/完整结果、逐历史点详情及请求内重放兼容；新增同日买卖保留描述与空盘中收益检查。不运行完整测试集；本轮未重新验证前一批已记录的旧分红测试问题。
- TypeScript/Vite 构建通过。正式只读财务对比：当前指标、所有完整历史收益点、账本及清仓查询完全一致。
- 正式后端重载、独立无界面浏览器通过：历史节点仅当时非零持仓；同日多笔交易可展开逐笔点击，清仓成交详情可见且不混入持仓行；原币摘要及人民币资料缺失说明可见，无 JS 异常。最初检查使用了错误的抽屉关闭选择器，按实际控件修正后通过。
- 浏览器核对前后原账本和业务表内容未变；只有应用既有自动汇率缓存刷新。该缓存不作为本轮历史估值/成本依据，业务财务结果再次比对一致。私有基线、核对结果和截图只留在已忽略运行目录。
- 本轮恢复的是交易事件展示；缺少完整组合估值的交易日期仍不计算精确盘中收益，用户实际使用验收继续由 P-005 跟踪。

## Git

实施提交 `d0d5f04b7c56c537ef04fb5617d3da55971b7783` 已核对文件范围；未推送，未提交私有运行资料，保留无关改动。
