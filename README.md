# Aliyun OSS Support RAG：阿里云对象存储技术支持问答智能体

本项目是 CS599《企业级应用软件设计与开发》期末大作业，方向为 **方向一：Agentic AI 原生开发**。系统面向云服务开发者、运维工程师和企业应用团队，围绕阿里云 OSS 对象存储的权限配置、API 调用、错误排查、成本优化和安全实践进行 RAG 增强问答。

## 项目能力

- 15 份阿里云 OSS 技术支持文档条目，覆盖权限控制、STS、Bucket Policy、Object API、分片上传、签名错误、CORS、防盗链、生命周期、静态网站、服务端加密、版本控制和日志监控。
- 构建 60 个本地知识库 chunk，支持 Embedding 向量索引 + BM25 的混合检索，并保留官方来源 URL、文档分类、章节和相关度。
- 支持自然语言问答、文档查询、API 参考、权限配置、故障排查和成本优化意图。
- 回答会先检索本地 OSS 知识库；配置 Embedding 后使用向量相似度 + BM25 混合召回，未配置时自动回退到 BM25。每次回答最多引用 top-5 个相关片段，界面“知识库依据”按相关度从高到低排序。
- 网页端流式展示检索、模型连接、逐 token 生成、引用依据和工具调用状态。
- LLM 与 Embedding 均从 `.env` 读取配置，不硬编码密钥；Embedding 配置可以先留空。

## 技术栈

- 后端：Python 3.13、FastAPI、LangGraph、Pydantic、Uvicorn
- 前端：React 19、Vite 7、TypeScript、Ant Design、lucide-react
- 检索：Embedding 向量索引 + BM25 混合检索，未配置 Embedding 时自动回退
- 知识库：阿里云 OSS 支持文档摘要、官方来源 URL、benchmark
- 测试：pytest 与 benchmark 评估脚本

## 目录结构

```text
cs599-project/
├── data/
│   ├── raw/aliyun_oss_docs.json
│   ├── processed/chunks.jsonl
│   ├── processed/documents_index.json
│   ├── processed/retrieval_index.json
│   ├── processed/topics_manifest.json
│   ├── processed/vector_index.json
│   └── eval/benchmark.json
├── docs/
│   ├── product_spec.md
│   ├── architecture.md
│   └── api_spec.md
├── frontend/
│   ├── src/
│   └── dist/
├── scripts/
│   ├── build_kb.py
│   ├── check_models.py
│   └── evaluate.py
├── src/aliyun_oss_rag/
│   ├── agent.py
│   ├── api.py
│   ├── config.py
│   ├── embeddings.py
│   ├── llm.py
│   ├── model_checks.py
│   ├── retrieval.py
│   ├── schemas.py
│   └── tools.py
├── tests/
├── pyproject.toml
└── README.md
```

## 环境变量

复制 `.env.example` 为 `.env`，至少填写三项真实大模型配置：

```text
BASE_URL=https://你的-openai-compatible-host/v1
API_KEY=你的 key
MODEL=你的模型名
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
```

`BASE_URL` 可以填写基础地址、`/v1` 地址或完整 `/v1/chat/completions` 地址。Embedding 三项是可选配置，留空时系统会使用 BM25 检索回退；填好后重新运行 `uv run python scripts/build_kb.py`，会生成或刷新 `data/processed/vector_index.json` 中的真实向量。不要提交 `.env`。

## 运行网页

```powershell
cd C:\Users\dzp\project\cs599-project
uv sync --python 3.13
uv run uvicorn aliyun_oss_rag.api:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000` 即可使用网页。接口文档在 `http://127.0.0.1:8000/docs`。

仓库已经包含 `data/processed/` 知识库产物和 `frontend/dist/` 前端构建产物。如果修改了 `data/raw/aliyun_oss_docs.json`，或配置/更换了 Embedding 模型，请重新构建知识库：

```powershell
uv run python scripts/build_kb.py
```

如果修改了前端代码，或 `frontend/dist/` 不存在，再重新构建前端：

```powershell
cd C:\Users\dzp\project\cs599-project\frontend
npm install
npm run build
```

FastAPI 会托管 `frontend/dist`，因此后端启动后访问根路径就是网页应用。

## 模型连通性检查

填写 `.env` 后，可以先单独检查大模型和向量模型是否可用：

```powershell
uv run python scripts/check_models.py
```

脚本会返回 JSON，分别包含 `llm` 和 `embedding` 的 `configured`、`available`、`model`、`endpoint`、`latency_ms` 等信息；向量模型还会返回 `dimensions`。如果后端已经启动，也可以访问：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/models/status
```

## 主要接口

- `GET /health`：检查服务、知识库和检索模式状态。
- `GET /models/status`：检查 LLM 与 Embedding 连通性。
- `POST /ask`：普通问答接口。
- `POST /ask/stream`：流式问答接口，返回检索状态、模型 token、引用依据和最终回答。
- `GET /documents`、`GET /documents/{document_id}`：查看知识库文档索引和单篇文档详情。
- `GET /topics`：查看主题分类。
- `POST /lookup`：按主题或关键词查询知识库文档。

## 前端开发

如果只改前端，可以单独启动 Vite 开发服务：

```powershell
cd C:\Users\dzp\project\cs599-project\frontend
npm install
npm run dev
```

发布或让 FastAPI 托管静态页面前，再运行：

```powershell
npm run build
```

## 知识库范围

当前知识库围绕阿里云 OSS 对象存储构建，覆盖：

- 基础概念：Bucket、Object、Endpoint、地域、访问域名。
- 权限控制：RAM Policy、Bucket Policy、ACL、STS 临时凭证、最小权限。
- API 接入：PutObject、GetObject、DeleteObject、HeadObject、分片上传 API。
- 故障排查：AccessDenied、SignatureDoesNotMatch、NoSuchBucket、NoSuchKey、CORS 失败。
- 安全与运维：Referer 防盗链、服务端加密、版本控制、日志、监控。
- 成本优化：生命周期规则、低频、归档、冷归档和未完成分片清理。

注意：课程要求和项目说明不会写入 RAG 知识库；`chunks.jsonl` 只包含 OSS 技术支持知识和官方来源 URL。

## 测试与评估

```powershell
uv run pytest
uv run python scripts/evaluate.py
```

评估结果写入 `data/eval/results.json`。
