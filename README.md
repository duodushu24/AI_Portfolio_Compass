# AI Portfolio Compass

> AI 持仓罗盘：一个把多个证券账户放到同一张地图里的投资组合工作台

> AI Portfolio Compass — AI portfolio copilot for investors with multiple brokerage accounts.

> 中文 | [English](#english)

AI Portfolio Compass 的起点很朴素：很多个人投资者并不只有一个账户。A 股基金、A 股股票、美股、港股、券商账户、手动导入资产，常常散落在不同 App 和不同市场里。你可能知道每个账户里有什么，却很难一眼看清“我到底完整持有什么、集中风险在哪里、哪些仓位真的需要处理”。

产品目标是帮助用户明确风险承受能力，建立适配的资产配置，改善持有体验并减少交易频率及对日常收益波动的注意力投入。账户管理支持标准 Excel 和手工建立起点，不要求使用同一家券商；历史结转盈亏与持仓成本、现金分别管理。首次使用请到账户与数据下载起点模板或手工填写，试算核对后确认；历史结转留空按 0 计入，可后续补填。收益支持累计/统计期金额与收益率四种视图，摘要与日曲线同步；累计收益率按净投入计算，统计期收益率按区间净值计算。成本或估值缺失时明确提示待补齐，不补画建档前走势。

收益曲线默认展示完整区间，可通过滚轮、按钮和底部范围选择缩放，放大后拖动平移。灰点表示当前指标无法计算，虚线只连接前后已知观察，不补填中间日期收益。

部分标的未更新时，使用该时点最近一次有效单位价格乘当时数量，不再因日期不同误判缺价；当前持仓的“市值更新日期”保留各价格原日期。真正缺失时列出账户、日期、标的及所需字段，可直接打开现有表单补录。统计期金额和收益率分别判断：金额可算而资金边界估值不足时，保留金额、提示补齐收益率依据。

买卖记录只更新数量、成本和现金，不更新市值价或市值更新日期，包括首次买入。没有有效报价的标的会提示缺价，请通过“更新市值”填写收盘价、净值或银行报价；已有报价继续用于交易后持仓估值。

历史收益基准缺少报价或汇率时，账户与持仓仍可读取，相关统计期收益显示待补齐，并提供具体补录入口；不会自动改用后来日期作为起点。新建或修改基准仍须有完整估值和正净资产。

这个项目首先要解决的是 **多账户、多市场、多币种资产的统一查看与分析**。在此基础上，它再把真实持仓、历史成交、仓位意图、行情新闻和复盘结果放进同一个本地系统，让 AI 在有上下文、有边界、有记录的前提下辅助你做投资组合管理。

它不是又一个“问 AI 今天买什么”的聊天壳子。AI 是能力层，不是项目本体；项目本体是一套属于个人投资者自己的资产总览、组合诊断和复盘系统。

它关注的不是单次答案，而是一个持续闭环：

```text
多账户资产汇总 -> 仓位分层 -> 组合诊断 -> 今日行动 -> 标的分析 -> 交易复盘 -> 用户画像更新
```

项目默认运行在你的电脑上。真实账户数据、API Key、本地数据库、日志和导入文件都应留在本地，不应提交到 Git，也不会被项目默认上传到云端。

> 本项目仅用于研究、记录和辅助决策，不构成投资建议；项目不实现下单、撤单、改单或交易解锁流程。


### 产品工作流

![从资产汇总到持续进化的投资工作流](docs/images/investment-workflow.jpg)

### 功能截图

| AI 模型与高级设置 | 账户与数据管理 |
| --- | --- |
| ![选择并配置外部大模型](docs/images/ai-model-settings.png) | ![持仓数据与投资账户管理](docs/images/account-data-management.png) |

| 持仓详情与 AI 辅助分析 | 投资组合全局总览 |
| --- | --- |
| ![持仓成本、K 线与 AI 辅助分析](docs/images/holding-analysis.png) | ![跨账户多市场的投资组合总览](docs/images/portfolio-overview.png) |

| 成交复盘与交易意图记录 | AI Agent 组合诊断报告 |
| --- | --- |
| ![成交复盘与交易意图记录](docs/images/trade-review.png) | ![AI Agent 自动生成组合诊断报告](docs/images/ai-diagnosis-report.jpg) |

## 为什么做这个项目

很多个人投资者的问题并不是“缺一个买卖点”，而是缺一个能把所有资产放在一起看、并长期跟踪自己投资行为的系统：

- A 股基金、A 股股票、美股、港股分散在不同账户里，没有统一资产总览。
- 不同账户、市场和币种的口径不一致，很难判断真实仓位、现金比例和集中度。
- 长期仓、波段仓、短线仓和期权仓混在一起，结果用同一套止盈止损逻辑处理。
- 买入时有理由，持有一段时间后理由丢了，只剩盈亏数字牵动情绪。
- AI 可以生成漂亮分析，但如果不知道你的仓位、成本、交易历史和风险偏好，答案很容易变成泛泛而谈。
- 盘中提醒太吵，真正该处理的风险反而被淹没。
- 交易结束后很少复盘，所以系统也无法知道哪些建议真的有用。

AI Portfolio Compass 想解决的是这个更长期的问题：让 AI 成为你的投资组合“副驾驶”，而不是一次性的荐股机器。

## 项目精髓

### 1. 真实账户驱动，而不是纯问卷画像

系统通过 Futu / moomoo OpenD 或本地导入读取不同账户、市场、持仓、成交和自选数据。它先把分散资产合并成一个组合视图，再基于真实交易行为动态推断用户画像，而不是只靠“你是稳健型还是进取型”这种问卷：

- 跨账户总资产、现金和持仓市值
- A 股、港股、美股等市场暴露
- 不同币种资产的归一化口径
- 资金分层和现金比例
- 持仓周期与加减仓行为
- 单票集中度和主题暴露
- 深度亏损仓、遗留仓和杠杆/期权风险
- 用户手动修正后的真实仓位意图

### 2. 仓位分层，让 AI 不再一刀切

同一只股票，作为长期核心仓、短期交易仓或遗留观察仓，应该对应完全不同的分析逻辑。系统会把持仓识别为：

- 核心长期仓：关注长期逻辑、组合权重、趋势是否被破坏。
- 中期配置仓：关注阶段趋势、成本区、目标位和失效条件。
- 短期交易仓：关注纪律、止损、成交量和交易理由是否仍成立。
- 期权仓：关注到期日、时间价值、波动率和最大亏损。
- 遗留观察仓：关注是否仍有持有理由，而不是机械止损。

用户可以手动修正仓位类型，后续分析会优先尊重人工标记。

### 3. 从“建议”走向“今日行动”

首页不是堆满行情，而是把最需要处理的事项提炼成行动清单：

- 哪些组合风险需要先看
- 哪些持仓已经接近失效条件
- 哪些标的只是观察，不值得被盘中噪音打断
- 哪些数据已经过期，因此不应该生成强提醒

系统强调克制提醒：数据不足就标记为信息不足，低置信度就降级为观察，不输出“立即买入”“必涨”“稳赚”这类强指令文案。

### 4. 复盘闭环，而不是只生成漂亮报告

每一次 AI 建议、用户查看、用户修正和后续交易都可以进入复盘链路。系统会把成交记录和后续行情结合起来，帮助你观察：

- 这笔交易是计划内执行，还是追高/卖飞/止损拖延
- AI 的提醒是否真的有帮助
- 哪些仓位需要重新定义持有理由
- 用户画像是否应该随着行为变化而更新

### 5. 本地优先和安全边界

这个项目从第一版就把安全边界放在核心位置：

- 只读同步，不执行交易动作。
- 不保存交易密码。
- 不调用交易解锁、下单、撤单、改单接口。
- API Key 只从环境变量读取。
- 外部 AI 调用需要显式授权，并且只发送单次分析所需的最小上下文。
- 本地数据库、日志、导入文件、导出文件和二维码默认不进入 Git。

## 当前能力

- 本地 Web 工作台：React + Vite + FastAPI。
- 多账户资产总览：把 A 股基金、A 股股票、美股、港股等分散资产放进统一视图。
- 多账户视角：支持账户选择、账户数据概览、跨账户合并分析和本地数据管理。
- 完整账户记账与收益：在“账户与数据”确认期初后，记录买卖、资金进出/转账、分红或更新市值，自动维护唯一摊薄成本、现金和阶段清仓收益；“资产组合”展示包含现金的整体净值收益率与盈亏金额曲线，账户筛选只影响持仓表，支持不规则时点、历史纠错及已清仓标的详情。
- 持仓与清仓分开查询：持仓表分别展示成本价（摊薄法）、市值价、含分红的持仓盈亏及本阶段分红，资产组合当前持仓另列市值更新日期；“账户与数据 → 数据管理 → 已清仓查询”按完整持有阶段查看历史退出，支持账户、关键词、清仓日期筛选及阶段成交明细。账户与数据保留分账户记账，不重复展示账户收益曲线。独立“记录分红”入口按记账时间视同到账，同步增加现金并抵扣成本，数量和市值价不变。
- 银行黄金手工记账：资产类型选择“贵金属（银行黄金）”，以克、元／克记录人民币积存金或账户黄金；不同银行产品分别维护，可按银行赎回／回购价或银行展示市值更新估值，并纳入账户收益。自动银行行情、实物提取和保证金业务暂未支持。
- 持仓诊断：仓位类型识别、组合集中度、盈亏状态、风险提示。
- 决策卡：建议类型、置信度、理由、风险、关键价位和数据状态。
- 标的详情：持仓、新闻、K 线摘要、AI 分析、仓位类型修正。
- 交易复盘：成交记录、后续表现、纪律标签和风险项聚焦。
- 投资日记：在“复盘 → 投资日记”独立录入原文，支持日期筛选、关键词搜索、同日多条记录和编辑；保存到 SQLite 与年月日 Markdown 文件。
- 日记分析与总结：提供“AI 分析”和“录入总结”；投资导师分析支持多轮追问，完整讨论自动保存，可关闭后恢复并在复盘时回看。总结须明确确认后保存，支持按标签/文字查询、编辑与文件重试。
- 日记提示词：在 [backend/app/prompts/diary](backend/app/prompts/diary/) 维护，`base.md` 为共同身份与判断原则，`analyze.md`、`discuss.md` 分别负责首次分析与连续讨论，`summary.md` 为首次分析和整理总结复用的总结规范。每轮仍只调用一次模型。
- 日记阅读与整理：AI 回复和总结支持常用 Markdown 排版，总结正文可编辑及预览。分析用于深入理解，总结保留核心结论、必要依据与边界；原文范围显示选中条数及日期、标题，不自动读取其他日期日记。总结的实际凝练质量仍需模型试用验证。
- 投资标签库：维护简短名称、使用定义和别名；AI 优先复用已有标签，新标签由用户确认，可手工新增、改名或合并并保留总结关联。
- 组合诊断工作流：客户画像、持仓诊断、资产配置建议等结构化报告。
- 数据源：免费默认 AKShare，支持沪深及美股股票/ETF 收盘价、基金正式净值、国际金价折算、日度汇率和境内个股新闻；免费/付费源统一管理，Futu OpenD 可选，Marketaux 保留免费额度 Key 配置。其他注册项尚未实现取数，不作为可用选项。
- 数据新鲜度矩阵：持仓、成交、行情、资讯、汇率、画像和决策卡都有过期处理。

成本计算唯一采用摊薄法：本持有阶段净成本＝买入清算支出－卖出净收入－净现金分红，除以剩余数量得到摊薄成本价；部分卖出和分红均会改变成本价，持仓盈亏已含二者，数量归零才结算清仓收益，再买入重新开阶段。分红按记账时间视同到账，不处理除息到到账的时间差，不自动调整市值价；清仓收益率以该阶段累计买入支出为分母，非正或未知分母不输出比例。详见 [P-007/S-001](issues/solutions/P-007/S-001-diluted-cost-dividend-accounting.md) 和 [C-017](CODE_CHANGE_LOG/C-017-manual-dividend-cost.md)。

组合收益从确认的期初市值及现金，或单独设置的完整估值基准开始；改收益基准不改历史账目与成本。盈亏金额＝当前总资产－基准总资产－期间净外部入金，收益率采用净值份额法；不把清仓利润或分红再加一次。每周等不规则观察均可，曲线连接已保存估值，期间买卖有独立交易标记，不推算缺价交易日收益。历史汇率优先本笔有效填写，否则沿用实际时间不晚于事件的最近保存记录，补录/纠错/作废后重算，禁止未来汇率倒填；来源、时间及沿用/估算信息可查。未知历史人民币取得成本不以当前汇率补造。相关实现见 [C-018](CODE_CHANGE_LOG/C-018-weekly-close-baseline.md)、[C-019](CODE_CHANGE_LOG/C-019-chart-transactions-and-closed-summary.md)、[C-021](CODE_CHANGE_LOG/C-021-historical-fx-selection.md)。

建档后持仓导入作为核对来源，不能覆盖账目；规范成交导入须填写币种、费用和资产/数量单位，成交号防重。旧快照与旧收益观察可只读查看。基础设计见 [S-002](issues/solutions/P-005/S-002-account-ledger-performance.md)，最新状态及有限验收项以 [current_state.md](current_state.md) 为准；稳定行情和 K 线不在这些批次修复范围内，不承诺精确每日收益曲线。

银行黄金 Excel 持仓及成交导入使用 `asset_type=precious_metal`、`unit=gram`、`market=CN`、`currency=CNY`，产品代码用稳定的 `CN.GOLD.产品标识`（不同银行产品分别命名），填写银行及产品名称；从界面建立过的产品应复用其代码，避免重复持仓。数量填克数，价格填元／克；成交表新增名称列，已有产品可复用账目或来源名称。升级后首次启动后端会给旧持仓表补充单位列，既有记录按原类型解释，不自动转换旧黄金记录。

日记的 Markdown 根目录可在 `.env` 中通过 `PERSONAL_KNOWLEDGE_DIR` 指向投资知识库；未设置时使用本地忽略目录 `data/personal_knowledge`。原文文件位于该根目录下的 `01_原始资料/复盘日记/YYYY/M月/MM.DD.md`，已确认总结位于 `02_分析与复盘/日记总结/YYYY/M月/MM.DD.md`。演示模式始终使用隔离的 `data/demo_personal_knowledge`。数据库保存原文、完整讨论与已确认总结；聊天和候选仅作为会话进度，不生成临时 Markdown，后续 Agent 的历史检索仍待开发。文件写入失败会提示并允许重试。

“AI 分析”使用设置中的模型，发送前须明确授权选中原文、会话背景、已保存问答及标签定义；本期不联网检索、不自动读取历史画像或其他日记。可先查看分析直接确认，也可追问后“整理总结”再确认。恢复和查看讨论不调用模型；生成中断保留问题，可主动重试。尚未发送的文字不属于已保存消息；候选编辑显示保存进度，失败时应先重试。外部总结可不调用模型直接手工保存，“建议标签”只发送当前总结与标签库。“一天一份已确认总结”与“可有多次讨论会话”分别管理。当前已完成流程及保存边界验证，真实模型分析质量仍需用户试用验收。

## 适合谁

这个项目更适合：

- 有多个证券账户，希望统一查看完整资产的人。
- 同时投资 A 股基金、A 股股票、美股、港股等不同市场的人。
- 有真实持仓，希望 AI 帮自己跟踪和复盘的人。
- 同时持有长期仓、阶段配置仓、短线仓或期权仓的人。
- 想把“买入理由、持有条件、失效条件、复盘结论”沉淀下来的人。
- 在意本地数据控制，不想把完整账户数据直接交给云端产品的人。
- 想研究 AI 投资助手、个人投顾工作台或 portfolio copilot 的开发者。

它不适合：

- 想要自动下单机器人的用户。
- 想要无脑荐股、收益承诺或短线信号群替代品的用户。
- 不愿意维护本地环境和 API 数据源配置的用户。

## 快速开始

给 Codex 或 Claude Code 的一句话安装指令：`请在当前目录安装并启动 AI Portfolio Compass：克隆仓库、复制 .env.example 为 .env、运行 ./scripts/start.sh，并告诉我本地访问地址。使用 Python 3.11 或以上安装后端依赖。启动后引导我建立手工账户，在“AI与高级设置 → 数据源”检测默认免费 AKShare；富途/OpenD 仅为可选来源，不是首次使用的必需项。`

克隆仓库后，创建本地环境变量文件：

```bash
cp .env.example .env
```

启动本地服务：

```bash
./scripts/start.sh
```

打开工作台：

```bash
http://127.0.0.1:4410/
```

查看服务状态：

```bash
./scripts/health.sh
```

### 演示模式（隔离的虚构数据）

应用启动后会同时准备正式工作区和演示工作区，可通过页面右上角的“正式模式 / 演示模式”按钮即时切换。演示后端会在启动时自动创建或升级完整的虚构数据，用户无需手动建库或执行数据初始化命令。演示数据写入单独的 `data/ai_trader_demo.db`，不会触碰默认的 `data/ai_trader.db`。

如需主动恢复演示工作区的初始状态，可选执行：

```bash
./scripts/start-demo.sh
```

演示工作区包含 A 股、港股和美股的虚构持仓与成交，成本价经过演示化处理以覆盖盈利和亏损场景；行情使用固定的 Futu OpenAPI 演示快照，资讯为明确标记的脱敏演示内容。演示服务不会同步真实账户，也不会把演示数据混入正式知识库。

停止服务：

```bash
./scripts/stop.sh
```

运行日志保存在 `.runtime/logs/`，该目录已被 Git 忽略。

## 手动启动

后端（Python 3.11 或以上；AKShare 已包含在依赖中）：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

前端：

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://127.0.0.1:4410`，正式后端健康检查地址为 `http://127.0.0.1:8010/api/health`，演示后端为 `http://127.0.0.1:8011/api/health`。端口 `4400/8000` 保留给非 public 版项目。

Windows PowerShell 可在项目根安装和启动正式后端，前端仍在 `frontend` 目录执行上面的 npm 命令：

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010
```

## 配置

复制 `.env.example` 为 `.env`。默认 AKShare 不需要 Key、证券账户或 OpenD；在“AI与高级设置 → 数据源 → 免费源”检测后，到“账户与数据”的行情/新闻页手动更新。沪深股票/ETF 使用已完成交易日的不复权收盘价，场外基金使用正式单位净值，保留原始价格日期；盘中运行不会把当日未完成日线当收盘价。美股股票/ETF 使用美元不复权收盘价，按纽约时区识别已完成交易日。黄金可按国际 XAU 参考价 × USD/CNY ÷ 31.1034768 折算人民币元/克，明确标为参考估值；新浪 XAU 为伦敦金现货参考/CFD，并非银行赎回报价。ETF/基金新闻、港股免费行情及银行专属自动报价仍未覆盖。

“更新行情”先获取并保存 USD/CNY 等所需汇率，再更新美股与金价；使用 AKShare 的 SAFE 日度人民币中间价。汇率失败沿用最近一次有效记录及原日期，较旧的上游数据不覆盖较新记录；缺少记录时提示补齐，不以固定汇率计算收益。美元现金同步折算，黄金已是人民币价格后不再重复换汇。实际成交与手续费继续记账，更新不改数量、成本或原币现金，也不把今日汇率套到更新前的成交。

付费源页按需启用 Futu，配置 OpenD 地址/端口并检测；Marketaux 为需 Key 的可选免费额度来源。前端保存的设置优先，旧环境变量仍兼容。普通沿用报价不视为估算，失败保留原有价格与日期。开源版本不包含商业 API Key。

开发者接入其他来源时，在 `backend/app/adapters/` 实现适配器，并在 `backend/app/services/providers.py` 登记分组、工厂、能力及配置字段。前端自动生成相应卡片和表单，不需要再维护服务商名单。AKShare 当前境内/美股股票及 ETF、伦敦金参考使用新浪接口，基金净值/个股新闻使用东方财富接口，日度中间价来自 SAFE；并非互相独立的稳定性保证。

```bash
FUTU_OPEND_HOST=127.0.0.1
FUTU_OPEND_PORT=11111
FUTU_TRD_ENV=REAL

MARKET_DATA_PROVIDER_PRIORITY=akshare
NEWS_PROVIDER_PRIORITY=akshare

MARKETAUX_API_TOKEN=

AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

如果没有配置 `DEEPSEEK_API_KEY`，单标的分析会使用本地结构化规则降级；需要外部模型参与的长报告工作流会明确提示未配置，不会伪装成 AI 报告。

## 可选：首次连接 Futu / moomoo OpenD

AI Portfolio Compass 通过你电脑上的 Futu / moomoo OpenD 以只读方式读取账户数据。系统不会执行下单、撤单、改单或解锁操作，也不会要求你在本系统中填写券商密码。

### 首次同步步骤

1. 安装并启动 Futu / moomoo OpenD。
2. 在 OpenD 中登录正确的 Futu 账号，并完成所需的手机验证和账户授权。
3. 确认 OpenD 的本地监听地址与项目配置一致：默认是 `127.0.0.1:11111`。
4. 在“AI与高级设置 → 数据源 → 付费源”启用 Futu 并保存连接配置，再回首页查看连接状态。
5. 点击“检查连接”。连接成功并读取到账户后，点击“首次同步”。
6. 系统会自动发现并创建 Futu 账户，然后读取账户资产、持仓和成交记录。

Futu 账户不需要在“账户管理”里手动创建。只有 Excel、PDF、截图等本地数据才需要通过“新增手动账户”导入。

### 账户来源如何区分

- `Futu · OpenD / 只读 API`：由 OpenD 首次同步自动创建，使用 API 刷新。
- `手动导入 / Excel / 文件`：由用户创建，使用 Excel、PDF 或截图导入，不依赖 OpenD。

第一版不允许同一个账户同时配置 Futu API 和手动导入，避免无法判断数据来源。需要补充本地文件时，请创建独立的手动账户。

### 常见问题

- **OpenD 未连接**：确认 OpenD 正在运行，并检查 host / port 是否为 `127.0.0.1:11111`。
- **OpenD 已连接但没有账户**：确认 OpenD 登录的是有交易账户的 Futu 账号，而不是只具备行情权限的账号。
- **账户授权不足**：在 OpenD 或券商端完成交易账户授权后，再回到工作台点击“重新检查”。
- **行情或市场数据不可用**：检查对应市场的行情权限；账户读取成功不代表所有市场行情权限都已开通。
- **修改 `.env` 后仍无法连接**：重启本地后端和前端服务，再重新检查。
- **首次同步失败**：查看工作台提示和 `./scripts/health.sh` 输出；不要把券商密码填入 `.env` 或 AI Portfolio Compass。

## 数据与隐私

默认忽略以下内容：

- `.env` 和所有本地密钥文件
- `data/` 本地数据库
- `.runtime/` 日志和运行状态
- 导入/导出的表格、PDF、截图、二维码
- Python、Node、测试和构建缓存

更多细节见 [SECURITY.md](SECURITY.md)。

## 文档

- [本地启动和数据源说明](#快速开始)
- [API Contract](docs/API.md)
- [安全边界](SECURITY.md)

## 测试

从仓库根目录运行后端测试：

```bash
pytest
```

构建前端：

```bash
cd frontend
npm install
npm run build
```

## 路线图方向

- 更完整的本地数据库加密方案。
- 更清晰的多账户、多币种和跨市场暴露分析。
- 更强的复盘评价体系，让 AI 建议能被长期验证。
- 更多本地模型或可替换模型 provider。
- 更完善的截图/PDF/Excel 导入体验。
- 更适合社区贡献的 provider 插件接口。

## 参与贡献

欢迎提交 issue 和 pull request。发起改动前请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

如果你要贡献数据源、AI provider 或交易相关能力，请优先保持项目的只读、安全和可复盘边界。

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。

---

## English

> AI Portfolio Compass: a local-first portfolio workbench that brings multiple brokerage accounts into one view

AI Portfolio Compass starts from a simple but painful problem: many individual investors do not have just one brokerage account. A-share funds, A-share stocks, US stocks, Hong Kong stocks, broker accounts, and manually imported assets often live in different apps and different markets. You may know what is inside each account, but it is hard to see the whole picture: what you truly own, where concentration risk sits, and which positions deserve attention.

The project first solves **unified viewing and analysis across multiple accounts, markets, and currencies**. On top of that, it brings holdings, trade history, position intent, market data, news, AI analysis, and post-trade review into one local workflow.

It is not another "ask AI what to buy today" wrapper. AI is a capability layer, not the product itself. The product is a personal asset overview, portfolio diagnosis, and review system for individual investors.

The core loop is:

```text
Multi-account asset aggregation -> Position layering -> Portfolio diagnosis -> Daily actions -> Position analysis -> Trade review -> Profile updates
```

The project is designed to run on your own machine. API keys, brokerage data, local databases, logs, and imported files should stay local and must not be committed to Git.

> This project is for research, record keeping, and decision support only. It is not investment advice and does not implement order placement, cancellation, order modification, or trading unlock flows.

## Interface Preview

Every screenshot below uses an isolated fictional dataset. No real account, holding, or trade data is included.

![Multi-account portfolio overview and diagnosis](docs/images/dashboard-demo.jpg)

| Unified holdings | Trade review |
| --- | --- |
| ![Unified multi-market holdings](docs/images/positions-demo.jpg) | ![Trade outcomes and discipline review](docs/images/review-demo.jpg) |

### Product Workflow

![Investment workflow from asset aggregation to continuous improvement](docs/images/investment-workflow.jpg)

### Feature Screenshots

| AI model settings | Account and data management |
| --- | --- |
| ![External AI model configuration](docs/images/ai-model-settings.png) | ![Holdings data and investment account management](docs/images/account-data-management.png) |

| Position detail and AI analysis | Portfolio overview |
| --- | --- |
| ![Cost basis, candlestick chart, and AI-assisted position analysis](docs/images/holding-analysis.png) | ![Multi-account and multi-market portfolio overview](docs/images/portfolio-overview.png) |

| Trade review | AI Agent portfolio diagnosis report |
| --- | --- |
| ![Trade review and investment-thesis capture](docs/images/trade-review.png) | ![AI Agent-generated portfolio diagnosis report](docs/images/ai-diagnosis-report.jpg) |

## Why This Exists

Many individual investors do not only need another buy/sell signal. They need a system that can put all assets in one place, then remember why they bought, what kind of position each holding is, when a thesis becomes invalid, and whether their own behavior is improving over time.

Common problems this project tries to address:

- A-share funds, A-share stocks, US stocks, and Hong Kong stocks are scattered across accounts, with no unified asset view.
- Accounts, markets, and currencies use different reporting bases, making true exposure, cash ratio, and concentration hard to judge.
- Long-term holdings, swing positions, short-term trades, and options are mixed together and judged with the same logic.
- The original buy thesis disappears after a few weeks, leaving only PnL-driven emotion.
- Generic AI analysis is often shallow because it does not know the investor's cost basis, position weight, history, or risk preference.
- Intraday alerts are noisy, while genuinely important portfolio risks are easy to miss.
- Suggestions are rarely reviewed later, so the system never learns what was actually useful.

AI Portfolio Compass aims to be a portfolio copilot, not a one-shot stock picker.

## What Makes It Different

### 1. Real account data over static questionnaires

The system reads accounts, holdings, trades, and watchlists through Futu / moomoo OpenD or local imports. It first consolidates scattered assets into one portfolio view, then infers the investor profile from actual behavior, not only from a risk questionnaire:

- Cross-account total assets, cash, and market value
- Exposure across A-shares, Hong Kong stocks, US stocks, and other markets
- Normalized views across currencies
- Cash ratio and position layers
- Holding period and add/reduce behavior
- Concentration and thematic exposure
- Deep-loss positions, legacy holdings, leveraged products, and options
- User-corrected position intent

### 2. Position layering instead of one-size-fits-all analysis

The same ticker should be analyzed differently depending on whether it is a long-term core holding, a medium-term allocation, a short-term trade, an option position, or a legacy position. The system classifies holdings into:

- Core long-term positions
- Medium-term allocation positions
- Short-term trading positions
- Options positions
- Legacy watch positions

Users can manually correct a position layer, and future analysis respects that correction.

### 3. From advice to daily action

The home view is designed around what deserves attention today:

- Which portfolio risks should be checked first
- Which holdings are close to invalidation conditions
- Which names are only worth observing
- Which data is stale and should not produce strong alerts

The system is intentionally restrained: insufficient data becomes "information insufficient", low confidence becomes observation, and prohibited language such as "buy immediately", "must go up", or "guaranteed profit" is avoided.

### 4. A review loop, not just polished reports

AI suggestions, user views, manual corrections, and later trades can all feed into the review loop. The system helps inspect:

- Whether a trade followed the original plan
- Whether the user chased, sold too early, delayed a stop, or protected gains
- Whether an AI alert was actually useful
- Whether a position needs a new holding thesis
- Whether the investor profile should change as behavior changes

### 5. Local-first with clear safety boundaries

Safety is a first-class design constraint:

- Read-only brokerage sync.
- No trading password storage.
- No trading unlock, order placement, cancellation, or modification calls.
- API keys are read from environment variables.
- External AI calls require explicit consent and send only the minimum context required for one analysis.
- Local databases, logs, imports, exports, screenshots, and QR codes are ignored by Git by default.

## Current Capabilities

- Local web workbench built with React, Vite, and FastAPI.
- Multi-account asset overview for scattered A-share funds, A-share stocks, US stocks, Hong Kong stocks, and manually imported assets.
- Account selection, account overview, cross-account analysis, and local data management.
- Account ledger with one diluted-cost method: net purchases less net sales and cash dividends determine the remaining cost. Partial sales and dividends stay in holding PnL until the position closes; a repurchase starts a new phase. Dividends are treated as received when recorded.
- Portfolio performance includes cash and external flows, with an optional complete valuation baseline, irregular valuation points, and separate trade markers. Historical FX uses an explicit valid rate or the most recent saved rate at or before the event; missing historical acquisition costs are not invented. See the Chinese capability notes and project state for validation limits.
- Manual RMB bank-gold accounting in grams, with independent product quotes and no automatic bank-price feed.
- Position diagnosis with position layers, concentration checks, PnL state, and risk notes.
- Decision cards with recommendation, confidence, reasons, risks, key prices, and data status.
- Position detail pages with holdings, news, K-line summaries, AI analysis, and layer correction.
- Trade review with execution outcome, later market movement, discipline labels, and risk focus.
- Independent investment diaries under Review: save original text to SQLite and dated Markdown files, browse/search entries, and edit them. AI distillation is planned for the next phase.
- Structured AI workflows for customer profiling, portfolio diagnosis, and allocation suggestions.
- Free AKShare data by default: mainland and US stock/ETF closes, published fund NAVs, XAU reference valuation, dated CNY FX and mainland stock news. Free/paid providers share one settings area; Futu is optional and Marketaux retains its key-based free quota. Unimplemented provider placeholders are not offered as working integrations.
- Freshness rules for holdings, trades, quotes, news, FX rates, profiles, and decision cards.

## Who It Is For

This project is a good fit for:

- Investors with multiple brokerage accounts who want one complete asset view.
- Users investing across A-share funds, A-share stocks, US stocks, Hong Kong stocks, or other markets.
- Investors with real holdings who want AI-assisted tracking and review.
- Users who mix long-term holdings, tactical allocations, short-term trades, and options.
- People who want to preserve buy thesis, hold conditions, invalidation rules, and review notes.
- Users who care about local control of sensitive account data.
- Developers exploring AI portfolio copilots or personal investment workbenches.

It is not a good fit for:

- Users looking for an auto-trading bot.
- Users looking for guaranteed returns, blind signals, or hype-driven stock picks.
- Users who do not want to manage a local environment or data provider configuration.

## Quick Start

One-line instruction for Codex or Claude Code: `Install and start AI Portfolio Compass in the current directory: clone the repository, copy .env.example to .env, run ./scripts/start.sh, and tell me the local URL. Use Python 3.11 or later for backend dependencies. Guide me to create a manual account and check free AKShare under AI & Advanced Settings → Data Sources. Futu/OpenD is optional.`

Create your local environment file:

```bash
cp .env.example .env
```

Start the local services:

```bash
./scripts/start.sh
```

Open the workbench:

```bash
http://127.0.0.1:4410/
```

Check status:

```bash
./scripts/health.sh
```

Stop services:

```bash
./scripts/stop.sh
```

Runtime logs are written to `.runtime/logs/`, which is ignored by Git.

## Manual Setup

Backend (Python 3.11 or later; requirements include AKShare):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://127.0.0.1:4410`; the formal backend health endpoint is `http://127.0.0.1:8010/api/health`, and the demo backend uses `http://127.0.0.1:8011/api/health`. Ports `4400/8000` remain reserved for the non-public project.

## Configuration

Copy `.env.example` to `.env`. Default AKShare needs no key, brokerage account, or OpenD. Check it under AI & Advanced Settings → Data Sources → Free, then manually update quotes/news in Accounts & Data. Mainland stocks/ETFs use completed-day unadjusted closes; OTC funds use published unit NAVs with their original dates. US stocks/ETFs use unadjusted USD closes with New York DST handling. Gold can use Sina London XAU spot-reference/CFD prices converted as USD per troy ounce × USD/CNY ÷ 31.1034768, explicitly marked as a reference, not a bank redemption quote. ETF/fund news, free HK quotes and bank-specific automatic quotes remain outside this batch. Updates fetch and save required FX first, then fetch prices. SAFE daily reference rates are shared across valuation; failed FX requests retain the latest valid saved rate and its original date, with no fixed-rate fallback in the financial ledger. Actual units, costs, original-currency cash and earlier trade FX costs remain unchanged. Enable optional Futu in Paid, or configure Marketaux with your own key for its free quota. Saved UI settings take priority over legacy environment values; failed updates preserve existing prices. No commercial API keys are included.

```bash
FUTU_OPEND_HOST=127.0.0.1
FUTU_OPEND_PORT=11111
FUTU_TRD_ENV=REAL

MARKET_DATA_PROVIDER_PRIORITY=akshare
NEWS_PROVIDER_PRIORITY=akshare

MARKETAUX_API_TOKEN=

AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Without `DEEPSEEK_API_KEY`, single-position analysis falls back to local structured rules. Long-form workflows that require an external model will explicitly report that the model is not configured instead of pretending to generate an AI report.

## Data and Privacy

The repository ignores:

- `.env` and local secret files
- `data/` local databases
- `.runtime/` logs and runtime state
- Imported/exported spreadsheets, PDFs, screenshots, and QR codes
- Python, Node, test, and build caches

See [SECURITY.md](SECURITY.md) for details.

## Documentation

- [Local setup and data providers](#quick-start)
- [API contract](docs/API.md)
- [Security boundary](SECURITY.md)

## Tests

Run backend tests from the repository root:

```bash
pytest
```

Build the frontend:

```bash
cd frontend
npm install
npm run build
```

## Roadmap

- Stronger local database encryption.
- Clearer multi-account, multi-currency, and cross-market exposure analysis.
- Better long-term evaluation of AI suggestions through trade review.
- More local model and model-provider options.
- Better screenshot, PDF, and Excel import experience.
- Cleaner provider plugin interfaces for community contributions.

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes.

If you contribute data providers, AI providers, or trading-related code, please preserve the project's read-only, privacy-conscious, and reviewable design boundaries.

## License

MIT License. See [LICENSE](LICENSE).
