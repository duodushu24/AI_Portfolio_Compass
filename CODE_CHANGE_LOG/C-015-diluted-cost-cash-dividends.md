---
schema: project-memory/v1
kind: change
id: C-015
title: "唯一摊薄成本与到账分红阶段结算"
status: closed
created: "2026-10-17"
updated: "2026-10-18"
issues: ["P-007"]
commits: ["e4afef97400ed28caa78ed9a72fd5f8ac0f1b795"]
evidence: ["backend/app/services/portfolio/ledger.py", "backend/app/services/portfolio/performance.py", "backend/app/services/portfolio/service.py", "backend/app/services/portfolio/gf_import.py", "backend/tests/test_diluted_cost.py", "backend/tests/test_gf_import.py", "backend/tests/test_portfolio_ledger.py", "frontend/src/features/portfolio/PortfolioPanel.tsx", "frontend/src/features/portfolio/PortfolioWorkbench.tsx", "frontend/src/features/portfolio/ClosedPositions.tsx", "frontend/src/features/portfolio/types.ts", "issues/solutions/P-007/S-001-diluted-cost-dividend-accounting.md"]
closed_reason: "授权实现、隔离重算和正式接口核对完成"
closed_result: "全账本使用摊薄净投入，部分卖出不单列收益，现金分红关联阶段并于清仓结算"
---

# C-015：唯一摊薄成本与到账分红阶段结算

关联 [P-007](../issues/P-007-diluted-cost-dividends.md) 与更新后的唯一方案 [S-001](../issues/solutions/P-007/S-001-diluted-cost-dividend-accounting.md)。用户明确排除精确每日曲线、除息时间差、应收分红及价格归因，并授权按简化范围修改系统。

后续替代（2026-10-18）：本记录的“分红不改成本”已被用户新要求及 C-017 替代。当前分红视同到账、增加现金并扣减阶段净成本，持仓盈亏含分红，清仓只结算一次；下文保留本批实际实施与验证历史，不作为现行分红公式。

## 实际变更

- 替换平均成本结转为单一净投入计算：买入增加实际清算支出，卖出扣减净清算收入；持有期间部分卖出盈亏留在浮动盈亏中，数量归零才结算阶段收益。同日清仓回补也新开阶段；费用只计算一次，合法负/零成本不截断，非正成本不输出误导百分比。
- 现金分红不改成本；真实到账增加现金并关联标的和阶段，清仓收益为净卖出收入减买入支出加阶段现金分红。迟到分红更新原关闭阶段，不污染新持仓。唯一阶段可自动匹配，多阶段必须明确选择；旧未归属分红保留现金事实并提示核对。
- 为已有券商旧导入增加来源校验的分红元数据补全函数，不新增现金流水。正式切换只补充一条来源明确的旧分红归属字段；没有重新导入、作废或更改其他事实。
- 兼容接口的 average_cost 是摊薄成本的同源别名，明确输出 diluted_cost/cost_method。旧平均成本来源不冒充新摊薄期初，不做跨类型成本比较。黄金、基金的单位及银行独立报价规则保留，转托管携带净投入不制造清仓收益。
- 持仓表移除部分卖出已实现盈亏列，显示阶段现金分红；清仓查询拆出交易盈亏和分红，详情列净清算额与分红到账记录。资金录入提供标的/阶段选择，期初提示明确摊薄成本并允许确认负数。
- 账户现金、资产及净值/份额算法不改变；缺失历史估值不推算。没有增加应收分红、除息归因、每日曲线或自动行情获取。

## 验证与正式切换

- 两个直接相关隔离测试模块共 15 项通过，既有直接账目/净值/拆分缺价回归 4 项通过；未跑完整测试集。覆盖部分卖出、费用、负/零成本、阶段重置、分红不改成本、迟到归属、编辑回滚、实际汇率、转托管、周度资产核对、导入及旧分红元数据补全不重记现金。
- 前端构建通过。未进行新增浏览器视觉验收；正式后端重载后，overview 和 closed 接口的成本、分红拆分、清仓合计与用户已核对样本一致。
- 正式数据库已先保存本地恢复副本，再在副本中重放及核对日终现金和样本，通过后事务补充分红关联并重载。真实现金、数量、相同报价下的总资产及账户收益字段前后保持一致；全部来源日终现金核对通过。
- 逐表比较恢复副本与正式数据库，只存在原分红事件 data 的非金额归属字段变化；原 amount/fees/currency/import_ref 不变。其他表逐行一致，SQLite integrity_check 为 ok。详细私有基准、恢复副本和核对结果保存在已忽略的本地运行目录，不写入公有记录或 Git。

## 限制

现金按实际到账日计入，不处理除息与到账之间的资产时间差；这是用户确认的范围。缺少收益边界估值的累计收益率仍不可用，不能由成本切换变成精确历史业绩。清仓百分比以累计买入支出为基数并明确说明，未对券商该百分比逐项验收。运行检查不等于用户已经验收全部页面，后续在 P-007 跟踪有限验收。

## Git

实施提交 `e4afef97400ed28caa78ed9a72fd5f8ac0f1b795` 已完成；无推送，不提交私有账目。
