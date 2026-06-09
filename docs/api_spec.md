# API Spec

## GET /health

返回服务状态、知识库 chunk 数、文档数、模型名和产品名。

## POST /ask

提交非流式 OSS 技术支持问题。

请求：

```json
{
  "question": "OSS 403 AccessDenied 应该怎么排查？",
  "conversation_id": "web"
}
```

响应包含 `answer`、`intent`、`citations`、`tool_calls` 和 `suggestions`。

## POST /ask/stream

提交流式 OSS 技术支持问题，以 SSE 返回：

```text
data: {"type":"status","content":"正在检索阿里云 OSS 技术支持知识库"}
data: {"type":"meta","state":{"intent":"troubleshooting", "...":"..."}}
data: {"type":"token","content":"答案","delta":"答案"}
data: {"type":"final","content":"完整回答","state":{"citations":[...]}}
data: {"type":"done"}
```

## GET /sources

返回知识库引用来源，包含 `source_title`、`url`、`source_type`、`product` 和 `category`。

## GET /documents

返回 OSS 支持文档清单，包含标题、分类、文档类型、标签、相关 API、常见错误和摘要。

## GET /documents/{document_id}

返回指定 OSS 支持文档详情，包含章节内容。

## GET /topics

返回知识库主题清单，用于前端展示文档分类。

## POST /lookup

按主题查询相关 OSS 支持文档。

请求：

```json
{
  "query": "Bucket Policy 权限"
}
```
