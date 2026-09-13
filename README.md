# 智扫通智能客服 Agent 平台

面向智能扫地机器人客服与售后的全栈骨架：`frontend/` 使用 Next.js + React，`backend/` 使用 FastAPI。原有 `agent/`、`rag/`、`data/` 和 `prompts/` 目录保留，作为迁移参考与知识数据源。

## 架构

```text
Next.js / React 工作台
        │ REST + SSE
FastAPI（聊天、报告、检索、健康检查）
        ├── DashScope OpenAI-compatible API → DeepSeek
        ├── data/*.txt → 轻量本地知识检索（PDF 保留，待接入解析器）
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

如果未配置 API key，后端仍可启动，并使用本地检索与报告模板兜底；配置 key 后会调用 DashScope 的 DeepSeek 模型生成回答。当前依赖无数据库/向量服务即可运行，TXT 已直接索引；原有 Chroma 与 PDF 文件保留，后续可替换 `KnowledgeBase` 接入生产级解析和向量检索。
