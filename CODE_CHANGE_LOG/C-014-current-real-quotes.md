---
schema: project-memory/v1
kind: change
id: C-014
title: "当前持仓沿用明确报价与历史估值分离"
status: closed
created: "2026-10-17"
updated: "2026-10-17"
issues: ["P-005"]
commits: ["02ac710a3d4c84a29a516dc991a6627e52f89540"]
evidence: ["backend/app/services/portfolio/performance.py", "backend/app/services/portfolio/service.py", "backend/tests/test_gf_import.py", "issues/solutions/P-005/S-002-account-ledger-performance.md"]
closed_reason: "相关隔离检查及正式服务读接口核对通过"
closed_result: "当前展示最新已知真实报价及日期，历史缺价保留缺失，重复提示合并"
---

# C-014：当前持仓沿用明确报价与历史估值分离

关联 [P-005](../issues/P-005-portfolio-return-history.md) 与唯一方案 [S-002](../issues/solutions/P-005/S-002-account-ledger-performance.md)。用户授权修正 C-013 中过严的价格读取规则，同时询问最新报价是否必须手填。

## 修改

- Prices 分别保存最新普通观察和最新真实报价。真实报价不被更晚的估算/成交价覆盖；份额入账或拆分后清除变更前单位的真实报价，需要新的实际报价，不能沿用未调整的旧单位价格。
- 明确报价模式的历史重放仍要求该时点报价；当前视图另行覆盖为最近已知真实报价计算的参考市值，保留原日期和沿用提示。当前视图不写入价格、收益点或交易事实，不回填历史。
- overview 的当前指标、持仓汇总和兼容投影读取同一当前估值。历史点、按明确历史时点查询的结果仍保留缺失，期间收益率仍不推算。
- 明确报价模式的资金边界历史提示合并为单条说明，当前缺价/旧价/汇率提示保留。
- 行情路径核对结果：实际账户拉取仍调用 Futu 适配器；注册表内的其他行情名称不代表已实现获取逻辑。本轮不新增行情连接，不抓取市场价格，不把手工旧报价改成最新行情。

## 验证

- `test_gf_import.py` 6 项通过。覆盖当前旧报价可显示且保留日期、历史未回填、后续资金记录不隐藏真实报价、估算/成交价不覆盖真实报价、份额变化后旧价失效，以及导入/隔离/幂等/回滚。
- 正式后端重载后，overview 读取已存真实报价及其日期成功；历史末端估值和累计收益率仍为空，历史提示为单条。health 正常，本地 OpenD 未连接。未改变正式交易、资金或报价记录。
- 本轮无前端文件变更，不重复前端构建；未新增浏览器视觉验收，不声称市场数据接入或自动更新已完成。

## Git

实施提交 `02ac710a3d4c84a29a516dc991a6627e52f89540` 已完成，未推送；不提交私有运行数据。
