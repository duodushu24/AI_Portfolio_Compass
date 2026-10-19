---
schema: project-memory/v1
kind: change
id: C-024
title: "恢复旧来源删除及累计盈亏主指标"
status: closed
created: "2026-10-19"
updated: "2026-10-19"
issues: ["P-010", "P-005"]
commits: ["9e6504a9ab3e56ebffec9813e804598d7f7aca22"]
evidence: ["frontend/src/features/portfolioViews.tsx", "frontend/src/features/portfolio/PortfolioPanel.tsx", "frontend/src/features/portfolio/PortfolioWorkbench.tsx", "backend/app/services/portfolio/profit.py", "backend/app/services/portfolio/service.py", "backend/app/services/portfolio/opening_import.py", "backend/tests/test_opening_profit.py", "backend/app/main.py", "issues/solutions/P-010/S-001-onboarding-profit-carry.md"]
closed_reason: "两个授权修复已实施并完成定向隔离验证，实际使用由 P-010 验收"
closed_result: "旧记录恢复删除，空白结转默认零，累计盈亏不再被统计期盈亏替换"
---

# C-024：恢复旧来源删除及累计盈亏主指标

## 实际修改与规则

- 修复 C-023 把旧来源表统一只读后隐藏删除按钮的问题。未建档旧持仓和成交恢复单条删除，保留原新增/编辑限制；沿用确认框和真实删除接口。派生持仓仍通过起点纠错或原账目作废维护，不通过删除模拟卖出。
- 按用户新要求，历史结转留空默认为 0，替代 C-023 的未知规则。手工起点、Excel 预览/确认、历史补录统一处理；旧数据字段缺失、null、空字符串在读取计算中按零，无迁移或真实数据补写。原非零值在纠错省略字段时保留，明确清空则归零。
- 组合主指标固定累计盈亏，包含历史结转、期初持仓盈亏和接入后盈亏；结转不改变现金、资产或成本。持仓成本、估值或汇率缺失仍保持未知，页面显示待补齐、缺失账户及完整核算账户合计，不自动换成统计期金额。
- 曲线和收益率仍使用统计区间；收益口径详情保留统计期金额及逐账户拆分。历史点详情原来把统计期金额称为累计组合盈亏，本批一并改正。模板、输入说明和项目入口同步默认零规则。

## 验证与边界

- `test_opening_profit.py` 18 项通过：空白/未提交结转、旧记录缺字段/null/空串的只读兼容、补填与清空不改现金成本、多账户缺成本隔离、转账/重置基准、Excel 负成本及空白结转、历史补录检查点等。使用内存 SQLite，未运行全套测试。
- 删除处理函数以虚构内存库直接调用实际后端实现：旧持仓删除成功、早期状态不自动复活、其他账户不受影响、重复删除 404、旧成交删除成功、已建档持仓删除受 409 保护。旧 TestClient 检查曾因本机请求阻塞而中止，未反复重试，改用以上直接处理函数核对；不宣称 HTTP 传输层验证通过。
- TypeScript/Vite 构建通过，仍有既有大包提示。无服务离线浏览器使用实际组件和虚构 props，共 12 项检查通过：旧记录删除入口与回调、建档后删除限制、累计金额展示、不回退统计期金额、缺失提示及部分合计、资产遮罩、无脚本错误。核对脚本修正了对 Arco 隐藏标签页的定位，不涉及业务代码额外修改。
- 临时检查保存在已忽略的 `.runtime/c024/`；未启动/重启前后端、未连接真实数据库或外部模型/行情。正式页面使用效果及真实账户数据完整性仍待用户验收。

## Git

代码/测试提交 `9e6504a9ab3e56ebffec9813e804598d7f7aca22`，7 个文件；公开记录另行本地提交，不推送。保留既有图片删除、CLAUDE.md、文档压缩包和路线文档等无关改动。
