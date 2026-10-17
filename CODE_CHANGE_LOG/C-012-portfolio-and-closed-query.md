---
schema: project-memory/v1
kind: change
id: C-012
title: "资产组合展示与独立清仓查询"
status: closed
created: "2026-10-17"
updated: "2026-10-17"
issues: ["P-005"]
commits: ["e89ebe0d72229f49ff21df91b58286d88e7177ff"]
evidence: ["backend/app/routers/portfolio.py", "backend/app/services/portfolio/ledger.py", "backend/app/services/portfolio/service.py", "backend/tests/test_portfolio_ledger.py", "frontend/src/App.tsx", "frontend/src/layout/ProShell.tsx", "frontend/src/features/ReturnHistoryPanel.tsx", "frontend/src/features/portfolio/PortfolioPanel.tsx", "frontend/src/features/portfolio/ClosedPositions.tsx", "frontend/src/features/portfolio/PortfolioWorkbench.tsx", "frontend/src/features/portfolio/portfolio.css", "frontend/src/features/portfolio/api.ts", "frontend/src/features/portfolio/types.ts", "frontend/src/features/portfolioViews.tsx", "issues/solutions/P-005/S-002-account-ledger-performance.md"]
closed_reason: "本批实现、直接相关验证与隔离页面核对完成"
closed_result: "资产组合固定整体曲线，记账与收益展示分离，持仓表拆列并独立查询历史清仓阶段；实际用户验收留在 P-005"
---

# C-012：资产组合展示与独立清仓查询

关联 [P-005](../issues/P-005-portfolio-return-history.md) 与更新后的唯一方案 [S-002](../issues/solutions/P-005/S-002-account-ledger-performance.md)。用户批准问题分析和方案后实施。

## 实际修改

- 导航“持仓”更名“资产组合”，整体曲线固定请求全组合，配置展示纳入账户与未建档覆盖提示。持仓表账户筛选为局部状态，金额/收益不受其影响；隐藏本页全局账户和展示币种切换。分账户账目、收益校验和净值公式保留。
- 复用持仓表去掉状态/持有阶段及数量后单位，拆分成本价、市值价、浮动盈亏和已实现盈亏，币种独立，金额两位、单价保留必要小数，数值右对齐且不换行。报价及数量单位在提示/详情中，已实现列可隐藏。组合兼容资产由后端按代码、币种、单位合并，账户分布可展开；旧来源持仓表也拆分价格与数量显示。
- 账户与数据移除单账户收益组件，保留分账户数据查询与记账。移除包含已清仓切换，新建同级“已清仓查询”，可按清仓日期、关键词和账户筛选，包括独立选择全部账户。持仓点击只看成交记录，清仓阶段点击查看其买卖、费用及成本结转，没有账户曲线。
- 新增 GET /api/portfolio/closed，从账目重放生成阶段记录，清仓再买回不丢过去阶段，转托管本身不生成清仓。每阶段带成交事实及人民币盈亏；只使用历史人民币成本和卖出时实际汇率，不用今天汇率凑合计。未知成本不计胜率，平手计入分母；跨币种缺失显示已知部分和缺失次数。起点快照及转入不冒充实际建仓日，真实买入阶段按北京时间自然日计算持有天数。
- 不新增持仓/收益事实表，不迁移或改写真实账目，不增加指数比较、平均持仓天数、交易执行或外部模型流程。

## 验证与限制

直接相关账目文件首次运行 38 通过、2 失败；新增断言分别把 Decimal 文本 23.0 当成必须等于 23，以及未容忍比例累加最后一位舍入。按数值与微小舍入容差修正断言后，只补跑两项，均通过；补充北京时间跨日持有天数用例 1 项通过。当前相关文件累计 41 项已覆盖通过，未反复运行成功用例，未运行全项目测试。

最终 npm run build 通过（含 TypeScript）；保留既有包体积提示。隔离本机 FastAPI/Vite/隐藏 Edge 使用新建虚构 SQLite 验证：更名导航、唯一整体曲线、局部持仓账户筛选不改变曲线、账户数据没有曲线、无包含已清仓按钮、已再买回标的仍有清仓阶段、点击阶段查看买卖明细及费用，无 JS 运行异常。截图核对组合表与清仓页的数字对齐、拆列和无长单位换行；没有把截图作为真实账户验收。自动化最初未正确触发 Arco 下拉菜单，改用真实鼠标事件后完成检查，未因此修改业务行为。

结构检查为 18 条记录、2 个方案、0 个错误，仅代表项目记录结构通过。实施提交 e89ebe0d72229f49ff21df91b58286d88e7177ff 已核对包含本批 14 个代码和测试文件。文档收尾单独提交，不循环追记自身哈希，未推送。用户原有图片删除及未跟踪文件保留。

专用隔离后端、前端和无头浏览器已关闭。尚未在用户正式账户验收，正式服务不自动重启，真实数据库、持仓、成交和日记均未操作。P-005 保持 active；历史缺失、未知成本和缺汇率保持可见。最后的源码收尾只统一旧来源表、账目行和金额格式，以及空值中性显示，不改变已验证的账目公式；TypeScript 与构建按最终源码通过。
