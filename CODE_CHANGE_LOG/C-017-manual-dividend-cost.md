---
schema: project-memory/v1
kind: change
id: C-017
title: "手工分红入口及现金成本同步调整"
status: closed
created: "2026-10-18"
updated: "2026-10-18"
issues: ["P-007"]
commits: ["f18282245342eb2bf90a3c2195d57791c550bad3"]
evidence: ["backend/app/services/portfolio/ledger.py", "backend/app/services/portfolio/service.py", "backend/tests/test_diluted_cost.py", "frontend/src/features/portfolio/PortfolioWorkbench.tsx", "frontend/src/features/portfolio/PortfolioPanel.tsx", "issues/solutions/P-007/S-001-diluted-cost-dividend-accounting.md"]
closed_reason: "授权的分红功能调整及针对性验证完成"
closed_result: "分红视同到账并扣减成本，持仓盈亏含分红，清仓不重复结算；提供独立入口与预览"
---

# C-017：手工分红入口及现金成本同步调整

关联 [P-007](../issues/P-007-diluted-cost-dividends.md) 与更新后的 [S-001](../issues/solutions/P-007/S-001-diluted-cost-dividend-accounting.md)。按用户确认以手工录入为主，不处理后续账单导入去重，不改变收益统计起点。

## 实际变更

- 当前阶段分红增加现金并扣减原币/明确历史汇率下人民币净成本；清仓按已扣分红的成本结算一次，买卖盈亏拆分扣除披露的分红，历史阶段补录不影响新阶段成本。
- 独立“记录分红”复用 dividend 事件，默认选择该记账时间的当前阶段，币种随标的，预览现金/成本变化或历史阶段收益；记账时间视同到账。纠错和作废复用原记录，净分红不为正时拒绝。
- 持仓表改称“持仓盈亏”，明确包含分红及部分卖出；成本提示、相关规则及 README 同步。报价更新、兼容字段及清仓拆分保留。
- 既有分红使用原事件重放，无数据库迁移或重复入账；新样本仅在副本试录，正式不自动新增资金记录。

## 验证

- 14 项相关后端用例通过，覆盖持有期分红、清仓重置、历史阶段分红、外币汇率、负成本、转托管及周度总收益；新增纠错/作废与报价不改成本检查，含 3 项读取性能回归。未跑完整测试集。
- 前端构建通过。隔离浏览器虚构账户验证独立入口、默认阶段、预览、保存、纠错和作废；现金/成本各调整一次，数量/报价不变，无 JS 异常。
- 正式只读基准与隔离副本比较：既有事实下当前结果和清仓查询一致；副本新增用户样本后成本与目标一致、现金只增加一次，清仓查询不变。
- 正式服务重载并只读核对，正式账目与恢复副本各表一致。私有恢复副本、金额、试录结果和浏览器脚本仅留已忽略本地运行目录。

## 限制与 Git

按用户要求视同到账，未处理券商实时可用资金与分红发放日期的差异。新分红由用户手工录入；实际体验仍在 P-007 验收。首次测试前端启动时 Node 路径不符，改用已安装路径后完成验证。

实施提交 f18282245342eb2bf90a3c2195d57791c550bad3 已核对文件范围；未推送，未提交私有数据，保留无关既有改动。
