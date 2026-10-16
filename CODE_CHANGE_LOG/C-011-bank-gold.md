---
schema: project-memory/v1
kind: change
id: C-011
title: "银行黄金类型、克单位与手工估值闭环"
status: closed
created: "2026-10-16"
updated: "2026-10-16"
issues: ["P-006"]
commits: ["b55413ec8637faae2d0f00bd2df2d84046eddbe5"]
evidence: ["backend/app/database.py", "backend/app/models.py", "backend/app/schemas.py", "backend/app/main.py", "backend/app/services/imports.py", "backend/app/services/sync.py", "backend/app/services/portfolio/ledger.py", "backend/app/services/portfolio/service.py", "backend/app/services/profile_workflows.py", "backend/app/services/ai_engine.py", "backend/app/services/ai_decision_cards.py", "backend/tests/test_portfolio_ledger.py", "frontend/src/features/portfolio/assets.ts", "frontend/src/features/portfolio/PortfolioWorkbench.tsx", "frontend/src/features/portfolio/PortfolioPanel.tsx", "frontend/src/features/portfolioViews.tsx", "frontend/src/api.ts"]
closed_reason: "本批实现与直接相关验证结束，真实账户验收交由 P-006 跟踪"
closed_result: "支持人民币银行黄金按克记账和独立产品手工报价；相关测试通过，未操作正式服务和真实账目"
---

# C-011：银行黄金类型、克单位与手工估值闭环

关联 [P-006](../issues/P-006-bank-gold.md)，扩展 P-005 账目能力。

## 实际变更

- 新增 precious_metal → gram 类型与单位约束，限定境内人民币银行产品；名称必填，产品使用独立 CN.GOLD. 标识。期初、买卖、报价、更正和历史补录均复用现有账目及收益公式。
- PositionSnapshot 新增 unit 字段，SQLite 启动时仅增列、旧记录保持空值并按既有类型解释。来源、投影、API、Excel 模板/解析/确认及同日来源核对传递单位。成交导入可填写产品名称，已有产品可从账目或来源解析名称。
- 期初和买卖表单提供贵金属，自动生成内部标识；持仓、价格和交易记录显示克与元／克。估值支持银行赎回／回购价、银行展示市值及来源时间；初始成交价含义明确。旧持仓编辑与导入预览同步支持。
- 不同银行产品以独立代码区分；跨账户持仓合并同时按币种和单位分组。证券行情拉取过滤贵金属，适配器报价写入也排除贵金属；详情 K 线明确返回未支持，不请求外部证券数据。资产分类、主题及分析上下文带贵金属和单位。

## 验证与限制

账目测试首次可执行运行 35 通过、1 失败：新增来源往返用例未把确认起点设置为来源实际日期，因此被正确识别为起点前资料。修正用例起点后，只补跑该用例与新增黄金历史补录用例，2 项通过；当前该文件共 37 项均已覆盖通过，未重复运行已成功用例。包括分数克、费用、部分卖出及清仓、报价隔离、证券适配器阻断、Excel 来源及成交、历史重建/纠错和旧表增列兼容。

分析上下文相关的 test_profile_workflows.py、test_ai_engine.py、test_ai_decision_cards.py 共 11 项通过。前端 npm run build 通过，含 TypeScript 检查；保留既有大包提示。未运行全项目测试，也未调用外部模型或实际银行行情。

初次沙箱 TestClient 在既有 API 用例处停滞，已中止；同一份测试在获准执行环境正常完成。测试只使用临时或内存虚构 SQLite，不启动应用正式生命周期，不操作正式数据库。SQLite 增列已在旧结构的隔离测试验证，正式库升级将在下次后端启动发生。

未重启正式服务，未修改真实账户、持仓或成交；浏览器视觉核对和实际用户验收未进行。首期只支持银行黄金按克和人民币现金记账，不转换旧 commodity 数据，不支持自动银行行情、实物提取或保证金业务。P-006 保持 active。

实施提交 b55413ec8637faae2d0f00bd2df2d84046eddbe5 已核对包含上述 17 个代码和测试文件，未夹带用户原有删除图片、CLAUDE.md、压缩包或历史路线图。项目记录检查为 17 条记录、2 个方案、0 个错误，仅代表结构检查通过。文档收尾单独本地提交，未推送。
