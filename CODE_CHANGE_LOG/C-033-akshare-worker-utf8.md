---
schema: project-memory/v1
kind: change
id: C-033
title: "修复 Windows 默认编码下 AKShare 基金取数失败"
status: closed
created: "2026-10-27"
updated: "2026-10-27"
issues: ["P-011"]
commits: ["ea874df4d0bbb0b5823f3f99c9f47a834d9516b0"]
evidence: ["backend/app/adapters/akshare_adapter.py", "backend/app/services/data_sources.py", "backend/tests/test_akshare_worker_encoding.py", "frontend/src/features/portfolioViews.tsx"]
closed_reason: "编码修复及最小定向验证结束，正式账户更新由 P-011 继续验收"
closed_result: "取数子进程固定 UTF-8，父进程按字节接收并明确解码；默认 GBK 环境下两只基金的隔离更新成功"
---

# C-033：AKShare 取数进程编码修复

## 原因与实际修改

Windows 默认 GBK 环境中，AKShare 子进程继承系统编码并输出含中文的 JSON，父进程却按 UTF-8 读取。已复现后台读取线程解码失败、随后空输出触发 JSON/TypeError 的链条，最终页面只显示“来源请求或解析失败”。同一公开基金请求在 UTF-8 环境成功，问题不需要通过修改基金类型或重新录入持仓解决；前批 UTF-8 验证未覆盖默认 GBK 启动条件。

`AKShareAdapter._call()` 仅为取数子进程设置 UTF-8 模式和标准流编码，以字节收发 JSON，再在调用线程明确解码；不依赖用户终端编码，不修改系统环境或 `.env`。保留原有超时、隐藏窗口和错误分类。异常编码单独返回 `encoding_error` 及保留原数据、更新后端后重试的提示，来源状态对应显示“编码异常”。

未修改来源选择、净值日期、汇率顺序、持仓成本或收益计算，也不借此扩大行情覆盖。本次不需要修改 S-001 的产品设计。

## 验证与限制

- 在父进程 `PYTHONUTF8=0`、`PYTHONIOENCODING=gbk` 条件下，新增进程边界测试及既有超时/依赖测试共 **6 项通过**：实际 Python 子进程的中文和非 GBK 字符往返、父环境保持、异常字节提示、依赖/进程失败/来源字段异常分类。新增测试不依赖网络或真实数据库，未运行全套回归。
- 在同样默认 GBK 条件下，用真实 AKShare 和实际应用更新服务处理虚构内存账本，两只公开基金分别走 `bond/share` 和 `fund/fund_unit` 路由，**2/2 成功**，取得的净值日期均为 **2026-10-26**。断言现金、数量和成本不变；结果留在忽略目录 `.runtime/c033/result.json`，未写正式账户。它验证 SDK、子进程和服务集成，未替代正式 HTTP 页面验收。
- 前端仅增加状态标签，`npm exec tsc -- --noEmit` 通过；未重跑前批页面交互或全量构建。
- 未启动或重启前后端，未改真实账目、报价、私人配置。用户需自行重新加载后端代码后，再在实际账户重试；公开来源持续可用性仍不作保证。

## Git

实施提交 `ea874df4d0bbb0b5823f3f99c9f47a834d9516b0`，仅含上述四个代码/测试文件；本记录、P-011 与索引另行本地提交，不推送，保留无关既有改动。
