---
schema: project-memory/v1
kind: change
id: C-013
title: "广发联合明细导入与明确报价限制"
status: closed
created: "2026-10-17"
updated: "2026-10-17"
issues: ["P-005"]
commits: ["adceb4436b347e33116b8a968c9b891381b0703d"]
evidence: ["backend/app/services/portfolio/gf_import.py", "backend/app/services/portfolio/ledger.py", "backend/app/services/portfolio/performance.py", "backend/app/services/portfolio/service.py", "scripts/import_gf_statement.py", "backend/tests/test_gf_import.py", "frontend/src/features/portfolio/PortfolioPanel.tsx", "frontend/src/features/portfolio/PortfolioWorkbench.tsx", "issues/solutions/P-005/S-002-account-ledger-performance.md"]
closed_reason: "授权导入已完成，正式接口及数据隔离检查通过"
closed_result: "联合明细重建指定账户，保留来源及恢复副本，不推算缺失历史市值与收益率"
---

# C-013：广发联合明细导入与明确报价限制

关联 [P-005](../issues/P-005-portfolio-return-history.md) 与唯一方案 [S-002](../issues/solutions/P-005/S-002-account-ledger-performance.md)。用户确认联合导入方案，并明确不补推算历史估值，随后授权处理数据并写入系统。

## 实际修改

- 增加本地命令 `scripts/import_gf_statement.py`：读两份导出，按账户、日期和流水联合核对，来源冲突、余额缺口、未适配业务直接拒绝。先通过 SQLite 在线备份建立恢复副本，再在另一副本中试写，最后在单次数据库事务中重建指定账户。原期初由真实首笔资金前的零现金起点替换；旧成交/资金作废留存，已有明确报价和只读来源快照保留。跨账户转移存在时拒绝单端替换。
- 证券费用合计只计一次；优先使用明确成交金额驱动现金和成本。银行出入金、利息、股息和份额增加分别映射；配号和零额存管事项只留来源。新增账户内 `share_credit`，增加数量而保留总成本，不复用会影响其他账户的全局拆分。
- 保存原时间与来源行顺序。来源按原顺序逐笔核对余额，正式账目按真实时间回放，另核对每天末端余额；不伪造时间来适配余额排列。
- 为导入账户设置 `explicit_only`：成交不更新共享报价，不沿用其他日期报价或估算价。缺少完整历史估值时不输出收益率、净值及完整期间利润；明确时点报价仍可计算当时资产。期初纠错保留该限制。前端展示缺估值空态和红股数量/调整表单。
- 同批次重复导入无变化；如果来源相同但现有账目已被修改，则报冲突。规范化明细、核对结果和数据库恢复副本只放被忽略的本地运行目录；公有记录不保存个人账户、流水、资产金额或原始文件内容。

## 验证与结果

- 新增 5 项隔离服务测试通过，覆盖联合映射、费用、份额成本、同代码其他账户隔离、幂等、编辑冲突、预览/失败回滚及明确报价日期限制。原有平均成本、缺价和拆分转托管 3 项检查完成；后续包含 TestClient 的用例在本机阻塞后中止，不声称完整旧测试集通过。
- 前端构建通过；本轮未做新增浏览器视觉验收。正式后端重载后，读取账户 overview 成功，持仓、现金、记录数和缺估值状态与隔离试写一致。
- 真实来源逐笔交叉核对、日终现金及末端数量/成本核对通过，完成正式写入。SQLite integrity_check 为 ok；按表对非目标账户及个人记录做前后摘要比较，无变化。详细私有结果在本地运行目录，不提交 Git。
- 正式 API 接受新账目不代表用户已验收全部页面；实际展示验收留在 P-005。不获取历史行情，不生成每日收益曲线，不接入券商 API，不调用外部模型。

## Git

实施提交 `adceb4436b347e33116b8a968c9b891381b0703d` 已完成，未推送。备份和正式 SQLite 均未加入 Git，代码提交不代表运行数据可通过 Git 恢复。
