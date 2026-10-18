---
schema: project-memory/v1
kind: change
id: C-021
title: "按实际时间取用历史汇率及人民币折算依据披露"
status: closed
created: "2026-10-18"
updated: "2026-10-18"
issues: ["P-005"]
commits: ["e276ade58c535e6cced1aaaa5f4c031ba9aaf7c2"]
evidence: ["backend/app/services/portfolio/performance.py", "backend/app/services/portfolio/ledger.py", "backend/app/services/portfolio/service.py", "backend/tests/test_historical_fx_usage.py", "backend/tests/test_portfolio_ledger.py", "frontend/src/features/portfolio/ClosedPositions.tsx", "frontend/src/features/portfolio/PortfolioPanel.tsx", "frontend/src/features/portfolio/types.ts", "issues/solutions/P-005/S-002-account-ledger-performance.md"]
closed_reason: "确认的汇率取用规则、针对性回归及正式只读核对完成"
closed_result: "未填汇率沿用最近有效历史记录；人民币成本与清仓折算可重算，保留来源并防止未来汇率倒填"
---

# C-021：按实际时间取用历史汇率及人民币折算依据披露

关联 [P-005](../issues/P-005-portfolio-return-history.md) 与 [S-002](../issues/solutions/P-005/S-002-account-ledger-performance.md)。用户已确认取消精确到秒相同的限制，未更新时使用此前最近的历史汇率，并授权实施。

## 实际变更

- 重放前从期初、有效成交和有效资金/估值事实建立按币种及实际时间排序的汇率索引；每个事件使用本笔有效填写，否则二分查找不晚于事件实际时间的最近记录。后来补录且实际时间较早的记录可修复之前事件，未来实际汇率不可回填。同一实际时点冲突使用确定顺序，修改/作废后重新计算；不从通用当前行情缓存读历史成本。
- 买卖成本、卖出结算、现金分红及资产/资金折算使用同一选用结果。去除成本和分红折算中的秒级一致校验，原币成本/盈亏和现金算法不变。旧持仓的未知历史人民币取得成本仍未知，不以期初汇率伪造。
- 外币成交和分红的派生明细保留实际取用汇率、时间、来源及沿用/估算信息；观察详情增加汇率依据。清仓摘要保留原币金额并提供人民币折算，沿用/估算明确提示，清仓成交表可查看汇率来源及日期。
- 不改数据库结构，不改写交易、期初、报价、汇率等原始事实；规则生效后从原记录自动重算，无需重新录入。

## 验证与结果

- 33 项相关后端检查通过：新增 8 项覆盖历史沿用、非同秒明确填写、补录/更正/作废、按实际时间而非录入时间、相同时点冲突、防未来及币种隔离、原始事实不变、分红和资金流不重复、旧取得成本未知；另覆盖周度基准、读取性能、摊薄成本与资金/范围变化。原有一项汇率测试曾断言新交易不得沿用历史汇率，按本轮确认规则更新该预期并单独通过；其他成功检查不重复运行。未运行完整测试集，前批已记录的旧分红测试不在本轮范围。
- TypeScript/Vite 构建通过。正式只读重放核对：当前组合总资产、现金、原币成本/浮盈/清仓盈亏、收益率和收益金额不变；人民币买入成本及清仓结果使用已存历史汇率补齐。较晚录入的较早实际汇率也能影响其后的历史交易。
- 正式重载及独立无界面浏览器通过：人民币清仓盈亏可见，缺失提示消失，原币仍正确，沿用标记及成交折算汇率可查，无 JS 异常。正式读检查后全部数据库表内容与实施前哈希一致，未写入账目或当前汇率缓存。
- 私有基线、结果和截图仅在忽略的本地运行目录。人民币折算采用沿用记录时不能称为成交瞬间市场精确汇率；继续保留实际时点与质量说明，用户真实业务验收由 P-005 跟踪。

## Git

实施提交 `e276ade58c535e6cced1aaaa5f4c031ba9aaf7c2` 已核对文件范围；未推送、未提交私有运行数据，保留无关既有改动。
