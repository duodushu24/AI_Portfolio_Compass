---
schema: project-memory/v1
kind: change
id: C-022
title: "移除市值价旧报价上标"
status: closed
created: "2026-10-18"
updated: "2026-10-18"
issues: ["P-005"]
commits: ["40d502310279d23aaaf318cefef4d678d9facc81"]
evidence: ["frontend/src/features/portfolio/PortfolioPanel.tsx"]
closed_reason: "限定的前端展示调整及最小相关验证完成"
closed_result: "旧报价不再显示旧字上标，报价时间与来源继续通过悬停查看"
---

# C-022：移除市值价旧报价上标

关联 [P-005](../issues/P-005-portfolio-return-history.md)。用户明确只去掉“旧”字，不在表格上方增加日期说明行。

## 实际变更及验证

共用持仓表移除旧报价的上标元素，悬停中的报价类型、来源、实际时间及单位保留；缺价、估算和当日既有标记保留。资产组合、账户持仓及历史详情使用同一组件。

`npm run build`（TypeScript + Vite）及差异空白检查通过。仅前端展示调整，不操作数据库或修改计算规则；未运行后端测试和浏览器验收，页面实际效果待用户确认。实施提交为 `40d502310279d23aaaf318cefef4d678d9facc81`；保留无关既有改动，未推送。
