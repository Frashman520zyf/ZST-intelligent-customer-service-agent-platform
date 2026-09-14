# 智扫通智能客服 Agent 平台

面向智能扫地机器人客服与售后的 Agent 演示平台：`frontend/` 使用 Next.js + React，`backend/` 使用 FastAPI。项目使用本地演示用户和模拟设备记录，不包含用户认证，也不连接真实设备。

## 架构

```text
Next.js / React 工作台
        │ REST + SSE
FastAPI（聊天、报告、检索、健康检查）
        ├── DashScope OpenAI-compatible API → DeepSeek
        ├── data/*.txt + data/*.pdf → 本地混合检索（词法 / 关键词 / 可选向量）
        └── data/external/records.csv → 个性化使用报告
```

## 启动

### 后端

```powershell
cd backend
python -m pip install -r requirements.txt
cd ..
python -m uvicorn backend.app.main:app --reload --port 8000
```

后端从系统环境变量读取 `DASHSCOPE_API_KEY`，不会把密钥发送到前端。默认模型为 `deepseek-v3`，可通过 `DASHSCOPE_MODEL` 覆盖。

### 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 <http://localhost:3000>。如后端地址不同，复制 `.env.example` 为 `.env.local` 并设置 `NEXT_PUBLIC_API_BASE_URL`。

## API

- `GET /api/health`：服务、模型、知识库和记录数量
- `POST /api/chat`：客服问答，自动判断普通咨询/使用报告
- `POST /api/chat/stream`：SSE 格式客服响应
- `GET /api/knowledge/search?query=...`：知识库检索
- `GET /api/reports/{user_id}`：用户最新报告
- `GET /api/reports/{user_id}/{month}`：用户指定月份报告

### PDF 知识库解析

知识库索引会按以下顺序尝试提取 PDF 文本：`PyMuPDF (fitz)` → `pypdf` → `PyPDF2`。`pypdf` 是基础依赖，PyMuPDF 和 PyPDF2 为可选增强依赖；即使解析器不可用，TXT 检索和客服仍可正常启动，PDF 会在 `GET /api/knowledge/index` 的 `parse_errors` 中提示。扫描型（无文本层）PDF 需要先做 OCR。

如需更高的 PDF 解析兼容性，可额外安装：

```powershell
python -m pip install pymupdf
# 或者使用旧版兼容解析器
python -m pip install PyPDF2
```

### Agent 闭环 API

除基础聊天接口外，演示工作台还提供一组可独立调用的 Agent 闭环接口：

- `POST /api/agent/intent`：规则优先的意图识别，返回置信度、实体、复合意图链
- `POST /api/agent/loop`：串联意图、分层记忆、RAG、回答、自动升级工单和评测事件
- `GET /api/agent/memory/{user_id}`：按用户/会话查看短期、长期和 episodic 记忆
- `GET /api/knowledge/index`：查看索引状态、来源、解析错误和配置指纹
- `POST /api/knowledge/rebuild`：增量或强制重建知识索引
- `GET /api/rag/search?query=...`：带策略、分数和引用信息的 RAG 检索
- `POST /api/tickets`、`GET /api/tickets`、`GET/PATCH /api/tickets/{ticket_id}`：售后工单生命周期
- `POST /api/events`、`GET /api/events`：写入/查询运行事件
- `POST /api/evaluations`、`GET /api/evaluations/metrics`、`POST /api/evaluations/run`：自动评测和指标
- `POST /api/feedback`：记录用户评分与反馈
- `GET /api/monitoring/overview`、`GET /api/monitoring/events`：延迟、fallback、意图分布、错误和工单监控

这里以阿里云百炼平台为例，不同运营商对应的名字不同，配置 API key 环境变量方法为：打开本地 powershell 或 cmd ，输入命令：
```powershell
setx DASHSCOPE_API_KEY "sk-你的API_KEY"
```
如果未配置 API key，后端仍可启动，并使用本地检索与报告模板兜底；配置 key 后会调用 DashScope 的 DeepSeek 模型生成回答。当前依赖无数据库/向量服务即可运行，TXT 和有文本层的 PDF 会直接索引；原有 Chroma 数据保留，可按需替换 `KnowledgeBase` 的检索实现。

向量层默认使用离线、确定性的 hash embedding，便于直接演示。要使用 DashScope 的真实向量模型，可设置 `DASHSCOPE_EMBEDDING_MODE=dashscope`；模型默认是 `text-embedding-v3`，也可通过 `DASHSCOPE_EMBEDDING_MODEL` 覆盖。远程 embedding 不可用时会自动降级到 TF-IDF 与关键词检索，索引、SQLite 记忆和监控数据均为本地运行时文件，不会提交到 Git。
