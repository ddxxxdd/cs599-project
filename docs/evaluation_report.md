# 测试与评估报告

本评估用于课程项目自测，覆盖阿里云 OSS 技术支持问答、权限配置、API 参考、故障排查和成本优化，检查意图识别、关键字段覆盖和引用覆盖。

- 样例数：10
- 意图识别准确率：1.0
- 关键字段覆盖率：1.0
- 引用覆盖率：1.0

| ID | 问题 | 期望意图 | 实际意图 | 关键字段通过 | 引用数 |
|---|---|---|---|---:|---:|
| q01 | OSS 403 AccessDenied 应该怎么排查？ | troubleshooting | troubleshooting | True | 7 |
| q02 | 如何用 STS 临时访问凭证让浏览器上传 OSS？ | permission | permission | True | 7 |
| q03 | RAM Policy 和 Bucket Policy 有什么区别？ | permission | permission | True | 7 |
| q04 | SignatureDoesNotMatch 常见原因有哪些？ | troubleshooting | troubleshooting | True | 7 |
| q05 | PutObject 需要什么权限，什么时候要用分片上传？ | api_reference | api_reference | True | 7 |
| q06 | OSS 生命周期规则如何降低日志存储成本？ | cost | cost | True | 7 |
| q07 | 浏览器直传 OSS 为什么会出现跨域失败？ | troubleshooting | troubleshooting | True | 7 |
| q08 | OSS 静态网站托管访问 404 或 403 怎么排查？ | troubleshooting | troubleshooting | True | 7 |
| q09 | 使用 SSE-KMS 加密上传 OSS 对象需要哪些权限？ | permission | permission | True | 7 |
| q10 | OSS 版本控制如何帮助误删恢复？ | doc_lookup | doc_lookup | True | 7 |