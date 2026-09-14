# 智扫通智能客服 Agent 平台

## 任务交接与进度总结

更新时间：2026-09-14（Asia/Shanghai）
项目目录：`D:\agent智能体项目\扫地机器人智能客服-agent项目`
远程仓库：<https://github.com/Frashman520zyf/zst-cs-agent-platform.git>
当前分支：`main`，HEAD：`d01fccb`（`串联闭环1`）

本文用于在新会话中快速恢复项目背景、已完成工作、验证证据和后续执行顺序。文档只记录项目状态，不包含任何真实 API Key。

## 1. 用户目标与范围

目标是制作一个面向智能扫地机器人的客服与售后 Agent 演示平台：

- 前端迁移为 Next.js + React + TypeScript。
- 后端采用 FastAPI。
- 大模型通过系统环境变量 `DASHSCOPE_API_KEY` 调用 DashScope OpenAI-compatible API，默认模型为 `deepseek-v3`。
- 串联意图识别、分层记忆、知识检索/RAG、转人工工单、监控反馈和自动评测，形成可观察的闭环。
- 解析 TXT 与 PDF 知识资料；不要求接入真实设备数据。
- 不接入用户认证，不接入真实生产设备；所有记录和设备状态均为本地演示数据。
- 用户提供的客服机器人图标文件：
  `C:\Users\cola\Downloads\智能扫地机器人客服网页图标 (1).png`。
- 前端视觉方向：Modern E-commerce（现代电商风），以 `frontend-design` 的单一视觉 anchor 和 `ui-ux-pro-max` 的可访问性/响应式规则为设计基线。

## 2. 当前总体状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| Next.js/React 前端骨架 | 已完成 | `frontend/` 已可构建，包含六个工作区标签页。 |
| FastAPI 服务骨架 | 已完成 | `backend/app/main.py` 提供基础聊天、报告、知识库和健康接口。 |
| Agent 闭环 | 已完成（演示级） | 意图→记忆→RAG→回答→工单→评测→监控已串联。 |
| PDF/TXT 解析 | 已完成（文本层） | 解析器按 PyMuPDF→pypdf→PyPDF2 降级；扫描件仍需外部 OCR。 |
| 混合检索 | 已完成（本地演示级） | TF-IDF、关键词和 hash 向量可组合；DashScope embedding 可选。 |
| 用户图标资源 | 已完成 | `frontend/public/robot-assistant.png` 已接入品牌、客服头像、加载态和设备卡。 |
| Modern E-commerce 视觉改版 | 已完成 | `globals.css` 已切换为 Swiss Modern / electric blue 视觉系统，并保留既有页面结构。 |
| 机器人图片替换 Lucide Bot | 已完成 | `page.tsx` 使用 `next/image` 封装 `RobotAvatar`，带固定尺寸和描述性 `alt`。 |
| 浏览器端联调 | 已完成基础验证 | Next 首页与静态资源 HTTP 200；完整聊天链路需在本机同时启动双服务后验证。 |
| API 离线问题 | 已定位并提供修复 | 前后端需分别启动在 `8000/3000`，默认 CORS 与 API 地址已对齐。 |

最近一次只读健康检查得到的运行时快照：6 份知识文件、73 个索引片段、120 条演示使用记录；`pypdf` 可用，索引无解析错误。运行时数据会随本地操作变化，不应当视为固定产品数据。

## 3. 架构概览

```text
Next.js 15 / React 19 / TypeScript
        │  REST + SSE（当前 SSE 为兼容性伪流式）
        ▼
FastAPI（backend/app/main.py）
        ├── IntentRouter：规则优先、否定识别、复合意图、实体抽取
        ├── AgentLoopService：记忆 → SupportAgent/RAG → 回答 → 升级 → 评测 → 事件
        ├── KnowledgeBase / PersistentHybridIndex：TXT/PDF、TF-IDF、关键词、向量
        ├── DashScopeClient：DeepSeek OpenAI-compatible chat/completions
        ├── UsageRecords：data/external/records.csv 演示使用记录
        └── AgentLoopStore：SQLite（memory/tickets/events/evaluations）
```

### 关键目录

```text
backend/app/
  main.py          FastAPI 入口、CORS、基础接口
  agent.py         原有客服回答器（RAG/报告/LLM/模板兜底）
  agent_loop.py    闭环编排、意图路由、SQLite 存储、工单/监控/评测路由
  retrieval.py     分页解析、分块、持久化混合索引、可选 embedding
  ingestion.py     文档提取和分块辅助函数
  knowledge.py     知识库门面和 RAG 检索结果转换
  rag_tools.py     可审计 RAG 工具封装
  llm.py           DashScope 客户端
  records.py       演示使用记录读取和报告生成
  schemas.py       基础聊天/知识库模型
  loop_schemas.py  闭环 API 的 Pydantic 模型

frontend/app/
  page.tsx         单页工作台（客服、报告、知识库、工单、监控、评测）
  globals.css      Swiss Modern / electric blue 现代电商工作台样式
  layout.tsx       页面 metadata 和全局布局
frontend/public/
  robot-assistant.png  用户提供的机器人图片（已由 next/image 接入）

data/
  *.txt、*.pdf      知识库源文件
  external/records.csv  本地演示使用记录
  agent_loop.db     运行时 SQLite（被 .gitignore 忽略）

.retrieval_index/、chroma_db/、logs/、frontend/.next/、frontend/node_modules/
  可重建或运行时目录，均不应提交到仓库。
```

顶层仍保留早期 `app.py`、`agent/`、`rag/`、`model/`、`utils/` 代码。当前推荐入口只有 FastAPI + Next.js；旧入口依赖未纳入 `backend/requirements.txt`，不要误用旧 Streamlit/Chroma 栈启动项目。

## 4. 后端已实现能力

### 4.1 意图识别

`IntentRouter` 在调用模型前进行确定性路由，当前覆盖：

- `safety_incident`：起火、冒烟、漏水、触电、电池鼓包等高风险信号。
- `human_handoff`：转人工、投诉、申诉、举报等。
- `after_sales`：维修、保修、退货、退款、换货、发票。
- `troubleshooting`：故障、报错、无法、漏扫、噪音、回充失败等。
- `maintenance`：清洁、保养、滤网、边刷、主刷、拖布、尘盒等。
- `usage_report`：报告、使用记录、月度数据等。
- `product_advice`：购买、选购、型号、价格、对比、推荐等。

实现了中文否定窗口和分句边界处理，例如“没有冒烟但漏水”不会因为前半句否定而丢掉后半句风险信号；复合问题会保留 `secondary_intents` 和 `chain`。可抽取的实体包括型号、序列号、月份、错误码和面积。

注意：这是启发式规则路由，不是经过训练和校准的生产分类器；复杂口语、Wi-Fi 等未覆盖词汇仍可能落到 `general_support`。

### 4.2 分层记忆与闭环

`AgentLoopStore` 使用 SQLite 保存：

- `short_term`：当前会话消息和最近回答，定期压缩保留窗口。
- `long_term`：用户型号、序列号等稳定事实，相同 key/value 去重。
- `episodic`：每轮意图、置信度和结果摘要。
- `tickets`：工单生命周期和上下文。
- `events`：运行、升级、反馈和工单审计事件。
- `evaluations`：自动评分、星级和反馈。

`AgentLoopService.handle()` 的实际顺序为：

```text
请求校验
  → 规则意图识别与实体抽取
  → 合并显式 history 和持久化记忆
  → SupportAgent（报告/RAG/DeepSeek/模板兜底）
  → 安全事故或人工意图升级（同会话/类别去重）
  → 自动相关性评分
  → 写入 agent_turn、错误/工单/评测事件
  → 返回 trace、引用、记忆、工单和延迟信息
```

### 4.3 知识库、RAG 与 PDF

- 支持 `.txt` 和 `.pdf`，保留 PDF 页码信息。
- PDF 解析顺序：PyMuPDF（若安装）→ `pypdf` → `PyPDF2`。
- 默认分块约 900 字符、重叠约 120 字符，生成稳定 `chunk_id` 和 citation。
- `PersistentHybridIndex` 持久化到 `.retrieval_index/index.json`，带文件、解析器、配置和 embedding 指纹，支持增量/强制重建。
- 检索分数组合词法/TF-IDF、关键词和可选 dense 向量；`/api/rag/search` 返回分数构成、引用、上下文和耗时，便于审计。
- 默认 embedding 是确定性的 384 维 `HashEmbeddingProvider`，无需外部服务即可演示。
- 设置 `DASHSCOPE_EMBEDDING_MODE=dashscope` 后可尝试 DashScope `text-embedding-v3`；远程失败会降级到本地检索。
- 扫描型 PDF 没有文本层时不会自动 OCR，会在索引状态的 `parse_errors` 中提示。

### 4.4 大模型与降级

`DashScopeClient` 调用：

```text
POST {DASHSCOPE_BASE_URL}/chat/completions
Authorization: Bearer $DASHSCOPE_API_KEY
model: $DASHSCOPE_MODEL（默认 deepseek-v3）
```

密钥只从后端进程环境读取，不发送到浏览器。未配置密钥、网络错误、模型错误或超时时，回答器使用本地 RAG/报告模板兜底并标记 `fallback`。当前客户端异常被统一吞并为 `None`，生产化时应补充结构化错误事件、重试策略和更细粒度的超时指标。

## 5. API 清单

所有路径均以 `/api` 开头。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 服务、模型配置、知识索引和演示记录健康状态。 |
| POST | `/chat` | 兼容旧客户端的客服问答，内部仍走闭环。 |
| POST | `/chat/stream` | SSE 兼容接口；当前先完成整轮回答，再拆行发送。 |
| GET | `/knowledge/search?query=` | 知识库搜索，返回片段、页码、引用和策略。 |
| GET | `/knowledge/index` | 索引文件数、片段数、解析器、embedding 和错误。 |
| POST | `/knowledge/rebuild?force=true` | 增量或强制重建知识索引。 |
| GET | `/rag/search?query=` | 可审计混合 RAG 检索，可限制 top-k、来源和上下文长度。 |
| GET | `/reports/{user_id}` | 读取用户最新演示使用报告。 |
| GET | `/reports/{user_id}/{month}` | 读取指定月份报告。 |
| POST | `/agent/intent` | 仅执行意图识别。 |
| POST | `/agent/loop` | 执行完整 Agent 闭环并返回 trace。 |
| GET | `/agent/memory/{user_id}` | 查询短期、长期或 episodic 记忆。 |
| POST | `/tickets` | 创建售后工单。 |
| GET | `/tickets`、`/tickets/{ticket_id}` | 查询工单列表或详情。 |
| PATCH | `/tickets/{ticket_id}` | 更新状态、优先级、负责人和 metadata。 |
| POST/GET | `/events` | 写入或查询运行事件。 |
| POST | `/evaluations` | 写入一条评测结果。 |
| GET | `/evaluations/metrics` | 汇总平均得分、星级和按意图指标。 |
| POST | `/evaluations/run` | 执行透明的内置评测集或自定义案例。 |
| POST | `/feedback` | 把用户星级/文字反馈写入同一评测表。 |
| GET | `/monitoring/overview` | 延迟、错误、警告、回退率、工单和意图分布。 |
| GET | `/monitoring/events` | 查询可审计事件流。 |

## 6. 前端现状

`frontend/app/page.tsx` 是一个客户端工作台，包含：

1. 智能客服：消息、快捷问题、RAG 引用、意图 trace、反馈和转人工提示。
2. 使用报告：覆盖率、清扫量、耗材和建议。
3. 知识库：关键词检索、引用、索引状态和常用主题。
4. 售后工单：状态、优先级、负责人和状态更新。
5. 运行监控：事件总数、延迟、回退率、错误/警告和意图分布。
6. 自动评测：运行默认测试集、平均分、星级和按意图得分。

默认后端地址：`http://localhost:8000/api`。可在 `frontend/.env.local` 中覆盖：

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

当前页面的主要实现已完成：

- 已引入 `next/image` 和 `RobotAvatar`，将用户图片用于品牌 mark、客服头像、加载态和设备服务卡。
- `globals.css` 已切换为 Swiss Modern E-commerce：白/浅灰表面、electric blue、深色高对比文字、1px 网格线、左对齐和清晰 focus ring。
- 已保留六个标签和现有 API 合约，未重写后端业务布局。
- 已将 FastAPI 422 的 `detail` 数组格式化为可读中文，避免直接显示 `[object Object]`。
- 已为聊天输入（4000）和知识查询（200）增加前端长度限制；空输入、发送中和检索中按钮会禁用。
- 已加入 375/768/1024/1440 断点及 `prefers-reduced-motion` 样式，避免移动端横向滚动。

设计基线：

- 视觉 anchor 只采用 Swiss，不混合暖纸色、颗粒纹理、过度玻璃拟态或大面积渐变。
- 图标继续使用 `lucide-react`，不使用 emoji 代替图标。
- 有意义的机器人图片必须有描述性 `alt`；纯装饰图片使用空 alt。
- 交互控件保留键盘 focus、禁用态、pressed/hover 反馈和至少约 44px 的触控区域。

## 7. Git 与文件安全状态

最近提交历史：

```text
d01fccb 串联闭环1
466bb53 readme更改
917617f readme增加api_key配置方法
86d888f feat: scaffold Next.js frontend and FastAPI backend
```

当前工作树（已核对，待本次提交）：

```text
 M .gitignore
 M README.md
 M frontend/app/globals.css
 M frontend/app/page.tsx
?? PROJECT_STATUS_SUMMARY.md
?? frontend/public/robot-assistant.png
```

`README.md` 的本地修改必须保留；该修改将运行时文件不提交的说明移出 README，但实际排除规则仍由 `.gitignore` 保证。机器人图片是用户提供的资源，随本次前端改版提交。当前总结文档本身为本次新增文件，提交前应一并审阅。

以下内容已在 `.gitignore` 排除，不应上传：

- `.env`、`.env.*`（保留各目录的 `.env.example`）。
- `frontend/node_modules/`、`frontend/.next/`、构建输出。
- `*.db`、`*.sqlite3`、`chroma_db/`、`.retrieval_index/`、`*.bin`。
- `logs/`、Python 缓存、IDE 配置和系统文件。
- 任何真实 `DASHSCOPE_API_KEY` 或本地密钥。

## 8. 已完成验证

以下命令均在项目目录执行过：

```powershell
Set-Location 'D:\agent智能体项目\扫地机器人智能客服-agent项目'

py -3.14 -m unittest discover -s tests -p 'test*.py' -v
# 6 tests OK（其中无效 PDF 用例会输出预期的 EOF marker 警告）

py -3.14 -m unittest discover -s backend/tests -p 'test*.py' -v
# 20 tests OK

py -3.14 -m compileall -q backend agent rag model utils app.py
# PASS

Set-Location frontend
npm run build
# PASS；Next.js 15.5.25，TypeScript/lint 检查通过，/ 和 /_not-found 生成成功
```

FastAPI `TestClient` 只读冒烟结果：

- `/api/health`：200；返回 `model=deepseek-v3`、知识库 6 files/73 chunks、records=120，未打印密钥。
- `/api/agent/intent`：200；“机器冒烟了，请转人工”正确得到 `safety_incident`，并保留 `human_handoff` 链路。
- `/api/knowledge/index`、`/api/knowledge/search`、`/api/rag/search`：200。
- `/api/monitoring/overview`、`/api/monitoring/events`：200。

环境提示：当前 Python 3.14 环境的 FastAPI/Pydantic/httpx 可用；直接执行默认 `python -m pytest` 曾因当前解释器未安装 pytest 而失败，项目测试使用标准库 `unittest`，不应把该环境提示误判为业务测试失败。TestClient 还会输出 Starlette 关于 `httpx` 兼容性的弃用提示，不影响当前请求结果。

## 9. 已知限制与风险（演示范围内可接受）

1. **尚非真正生产级向量检索**：默认是 JSON 持久化和 O(N) 本地扫描的 TF-IDF/关键词/hash 向量，没有 ANN、向量数据库、rerank 或召回阈值评测。DashScope embedding 只是可选适配器。
2. **PDF 无 OCR**：扫描件无文本层时需外部 OCR 后再索引。
3. **SSE 不是真流式**：`/chat/stream` 当前先等待完整 `chat()`，再按行发送；尚未接入 `DashScopeClient.stream()` 的增量 token。
4. **意图识别为启发式**：没有 LLM 二次分类或标注集校准，复杂/隐含意图可能误路由。
5. **模型错误可见性不足**：LLM 异常会降级为模板，当前未完整记录错误类型、重试次数和上游状态码；配置无效 key 时可能等待超时后才看到 fallback。
6. **SQLite 为单机演示实现**：未配置 WAL、迁移、保留策略或多进程锁；事件、评测和 episodic 记忆会持续增长。
7. **索引/CSV 在启动或手工 rebuild 时载入**：外部文件修改后需重启或调用 rebuild；重建与查询尚无专门锁。
8. **CORS/绑定限制**：默认只允许 `localhost:3000` 和 `127.0.0.1:3000`；`run_backend.ps1` 绑定 `127.0.0.1`。局域网访问需使用 `--host 0.0.0.0` 并设置匹配的 `ALLOWED_ORIGINS`。
9. **无认证和真实设备数据**：这是用户明确要求的演示边界，不代表可直接用于生产。
10. **旧栈并存**：顶层旧 `app.py`/LangChain/Chroma 代码可能造成入口混淆，后续应在 README 中进一步强调 uvicorn 入口。

## 10. 后续可选增强

1. **双服务端到端浏览器回归**：后端 `8000`、前端 `3000` 同时启动后，手动检查聊天、转人工、知识检索、报告和移动端布局。
2. **按需提升检索生产性**：引入真正的向量数据库/ANN、DashScope embedding 缓存与重试、rerank、召回评测和异步索引；这超出当前演示骨架的最低交付范围。
3. **按需完善可观测性**：将上游 LLM 错误、超时、fallback 原因和 SSE 连接状态写入事件流。
4. **持续维护 Git 忽略规则**：已核对没有 `.env`、数据库、索引、日志或 `node_modules` 被误加入当前提交范围；后续新增运行时目录仍需沿用现有规则。

## 11. 常用启动命令

### 后端

```powershell
Set-Location 'D:\agent智能体项目\扫地机器人智能客服-agent项目'
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

如需局域网访问：

```powershell
$env:ALLOWED_ORIGINS='http://localhost:3000,http://127.0.0.1:3000,http://<前端主机>:3000'
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

另开终端：

```powershell
Set-Location 'D:\agent智能体项目\扫地机器人智能客服-agent项目\frontend'
npm install
npm run dev
```

浏览器访问 <http://localhost:3000>；后端健康地址为 <http://localhost:8000/api/health>。

若页面提示“客服 API 离线”，按以下顺序检查：

1. 后端是否在 `8000` 端口运行，并能打开 `/api/health`。
2. `frontend/.env.local` 的 `NEXT_PUBLIC_API_BASE_URL` 是否包含 `/api` 且主机/端口正确。
3. 跨主机访问时，`ALLOWED_ORIGINS` 是否包含浏览器的完整 origin。
4. 修改 `.env.local` 后是否重启了 Next.js 开发服务器。

## 12. 会话恢复提示

新会话开始时，先阅读本文件和 `README.md`，再执行：

```powershell
Set-Location 'D:\agent智能体项目\扫地机器人智能客服-agent项目'
git status --short
git diff -- README.md frontend/app/page.tsx frontend/app/globals.css
```

不要回滚 `README.md` 的已有修改；不要删除用户图片、SQLite 数据、索引或知识源文件。前端视觉、图片接入、输入边界和基础构建验证已完成；后续优先执行第 10 节的双服务浏览器回归，再按需处理生产化增强。
