# Product Spec

## 项目名称

Aliyun OSS Support RAG：阿里云对象存储技术支持问答智能体。

## 背景

企业应用接入对象存储时，经常遇到权限策略、STS 临时凭证、API 参数、签名错误、CORS、生命周期成本和静态网站访问等问题。普通搜索结果分散，通用大模型也容易忽略具体服务边界、错误码和权限条件。本项目构建一个面向阿里云 OSS 的垂直技术支持 RAG Agent。

## 目标用户

- 后端开发者：接入 OSS 上传、下载、分片上传和签名 URL。
- 运维工程师：排查 403、404、签名错误、跨域、日志和费用异常。
- 企业应用团队：设计 RAM、STS、Bucket Policy、加密和生命周期策略。

## 核心需求

1. 用户输入 OSS 技术问题后，系统识别知识问答、文档查询、API 参考、权限配置、故障排查或成本优化意图。
2. 系统通过向量相似度 + BM25 混合检索本地 OSS 支持知识库，并给出引用来源、chunk id、章节、分类和相关度。
3. 对权限类问题，调用权限工具聚合 RAM、STS、Bucket Policy、ACL、KMS 等文档。
4. 对错误类问题，调用故障排查工具返回错误码、优先检查项和相关文档。
5. 对 API 类问题，调用 API 查询工具返回相关接口、权限要求和注意事项。
6. Web 页面提交后先展示检索/模型连接状态，再流式追加大模型回答。
7. Web 页面保存浏览器本地问答历史，并区分成功回答和模型调用失败。
8. 回答下方展示知识库命中片段和官方来源链接，用于说明 RAG 依据。
9. LLM 通过 `.env` 的 `BASE_URL`、`API_KEY`、`MODEL` 三项配置；Embedding 通过 `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL` 配置，三项可先留空。

## 成功标准

- 覆盖不少于 10 份 OSS 支持文档条目。
- 知识库构建后不少于 50 个 chunk。
- RAG 检索数据只包含 OSS 技术支持知识和官方来源 URL，不包含课程要求或报告文本。
- benchmark 覆盖权限、API、故障排查、成本优化和访问配置。
- API 支持 `/ask/stream`、`/documents`、`/documents/{id}`、`/topics` 和 `/lookup`。
- FastAPI 托管 React/Vite 构建后的网页，正式演示只需访问根地址。
