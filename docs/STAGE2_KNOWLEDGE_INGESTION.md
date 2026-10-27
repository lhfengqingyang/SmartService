# 阶段 2 技术记录：知识库导入、Embedding 与 ACL

**记录日期：2026-10-23**  
**当前结论：RAG 摄取链路已经通过真实 HTTP、智谱 Embedding 和 PostgreSQL + pgvector 端到端验证；检索与答案生成属于下一阶段。**

## 今天完成了什么

当前实现的是 RAG 的 ingestion（摄取）部分：

```text
Markdown/TXT 上传
    -> 文件安全校验与 UTF-8 解码
    -> 结构感知分块
    -> embedding-3 批量生成 1024 维向量
    -> PostgreSQL 事务写入 documents 和 document_chunks
```

实际上传 `refund_policy.md` 已成功生成 3 个 chunk。数据库确认文档 ACL 正确保存，3 个向量的维度均为 1024。第一次在受限网络进程中调用 Embedding 返回 502，事务没有留下半成品；允许联网后端到端调用成功。

| 文件 | 职责 |
|------|------|
| `app/api/knowledge.py` | 暴露 `POST /api/v1/knowledge/upload`，读取 multipart 表单并返回统一错误 |
| `app/ai/knowledge.py` | 校验文件与 ACL、调用分块和 Embedding、控制数据库事务 |
| `app/ai/chunking.py` | Markdown 标题感知和 TXT 自然边界分块 |
| `app/ai/embedding.py` | 调用智谱 `/embeddings`，校验数量、数值类型和向量维度 |
| `app/config.py` | 管理上传、分块和 Embedding 配置 |
| `db/init/002_embedding_dimension.sql` | 将向量列固定为 `vector(1024)` |
| `db/init/003_knowledge_metadata_acl.sql` | 增加来源元数据、chunk 元数据和文档 ACL |
| `tests/test_knowledge.py` | 覆盖上传响应、文件校验、路径穿越、编码、大小和 ACL 格式 |

## RAG 技术流程与选型

完整 RAG 分为三段，目前只完成第一段：

1. 摄取：文档解析、分块、Embedding、存储。当前已完成。
2. 检索：问题生成 Embedding，在 pgvector 中执行带 ACL 的 Top-K 相似度查询。尚未实现。
3. 生成：把可靠片段和来源交给对话模型生成答案；证据不足时拒绝猜测。尚未实现。

本项目的选型：

- FastAPI：上传 API、Swagger 和参数校验。
- 自研轻量分块：第一版不引入复杂语义分块框架，逻辑可解释且方便测试。
- `embedding-3`：负责把文档块和用户问题转换为同一向量空间中的 1024 维向量。
- PostgreSQL 16 + pgvector：同时保存业务元数据和向量，减少 MVP 的基础设施数量。
- SQLAlchemy + psycopg：连接池、事务和参数化 SQL；当前没有使用 ORM。
- Docker Compose：提供可复现的本地 PostgreSQL + pgvector 环境。

对话模型不负责生成 Embedding。后续 GLM 对话模型只读取检索片段并组织答案；`embedding-3` 负责向量化；pgvector 负责向量存储和距离计算。

## 分块数据与来源追踪

文档表 `ai.documents` 保存：

- 文件名、类型、原文件 SHA-256、字节数、chunk 数量和创建时间。
- `tenant_id`、`owner_user_id`、`visibility`、`allowed_roles`。

分块表 `ai.document_chunks` 保存：

- `document_id`：关联来源文档。
- `chunk_index`：文档内连续顺序。
- `heading`：Markdown 完整标题路径。
- `chunk_text`：用于检索和引用的实际文本。
- `content_sha256`：分块内容哈希。
- `embedding vector(1024)`：真实模型生成的向量。

当前分块参数为目标 800 字符、最大 1200 字符、重叠 120 字符。Markdown 优先按标题层级分区，再在段落、换行或句末标点处切分；TXT 按自然文本边界处理。这里使用的是字符数，不宣称等同于 token 数。

## ACL 为什么在生成向量时一起保存

Embedding 本身不携带权限，它只是数值向量。上传时同时保存 ACL，是为了让检索 SQL 在计算和排序候选片段时就排除无权访问的文档。

ACL 以文档表为唯一事实来源，chunk 通过 `document_id` 关联，不在每个 chunk 中复制权限，避免权限修改后出现数据不一致。计划中的检索语义是：

- `public`：所有调用者可检索。
- `tenant`：仅同租户调用者可检索。
- `private`：仅同租户所有者或命中允许角色的调用者可检索。

必须在数据库 Top-K 查询中应用 ACL，不能先检索全库再在 Python 中删除无权结果。后过滤既可能暴露数据，也会导致返回不足 K 条。

当前接口中的租户、用户和角色由表单传入，只用于 MVP 演示，不等于身份认证。生产环境必须从可信 JWT、Session、API Gateway 或服务间身份中取得这些值。

## 当前一致性和失败处理

- 文件先完成校验、分块和 Embedding，再开启数据库事务，避免长时间占用数据库连接。
- 文档行和所有 chunk 在同一事务中写入；任意 SQL 失败会整体回滚。
- Embedding 失败返回 `502 EMBEDDING_UNAVAILABLE`，不会写入半成品。
- 数据库失败返回 `503 DATABASE_UNAVAILABLE`，API 不返回底层 SQL 和连接信息。
- Embedding 按最多 64 个文本一批调用，避免逐 chunk 请求造成延迟和费用浪费。
- `.env` 保存真实密钥并被 Git 忽略，`.env.example` 只保留占位值。

## 关键问题与设计取舍

### `await run_in_threadpool()` 在上传接口中的作用

FastAPI 上传路由是 `async def`，但当前 `import_document()` 内部使用同步 `httpx.Client`、同步 SQLAlchemy Engine，并包含文本处理。这些操作如果直接在异步路由中执行，会占用主事件循环，导致同一进程中的其他请求等待。

```python
result = await run_in_threadpool(import_document, ...)
```

`run_in_threadpool()` 把同步导入函数交给工作线程；`await` 只暂停当前请求对应的协程，主事件循环可以继续调度其他请求。工作线程完成后，当前请求恢复并取得 `ImportedDocument`。这不是让整个服务停止，也不是 AI 调用语法。

该方案适合当前低并发 MVP，可以复用简单的同步 HTTP 和数据库代码。线程池容量有限，大量长时间导入任务仍会排队；生产环境应改为上传后创建任务，由独立 Worker 异步处理。

### 文件是二进制，不代表模型可以理解任意模态

HTTP 上传后的 Markdown、TXT、PDF、图片和音频在程序中都可以表现为 `bytes`，但 bytes 只是传输形式，不代表模型理解了内容。

当前系统仅支持：

```text
Markdown/TXT bytes -> UTF-8 解码 -> Python 字符串 -> 分块 -> 文本 Embedding
```

图片需要图片格式校验和 OCR/视觉模型；PDF 需要版面与文本解析器；音频需要 ASR；视频通常需要抽帧和音频转录。解析后得到的文本或多模态表示，才可以送入对应模型。当前项目是文本 RAG，不是多模态 RAG。

### `chunk_document()` 为什么没有调用 AI

`chunk_document()` 是确定性的规则分块函数，不负责模型推理。它执行：

1. Markdown 按标题层级划分章节，TXT 作为无标题正文处理。
2. 优先在段落、换行和句末标点处分割。
3. 使用目标 800、最大 1200、重叠 120 个字符的长度约束。
4. 找不到自然边界时按长度硬切。
5. 输出带连续索引和标题路径的 `TextChunk`。

真正的 AI 调用发生在分块之后：`_embed_chunks()` 收集 chunk 文本并调用 `embed_texts()`，后者请求智谱 `/embeddings`。规则分块速度快、无额外模型费用、结果稳定且容易测试；只有评测证明有必要时，才考虑语义分块。

### 当前是否需要断点续传

需要区分文件上传断点续传与知识导入任务恢复：

- 文件上传断点续传解决大文件网络中断后从已上传字节继续。当前只允许 10MB Markdown/TXT，失败后重新上传即可，暂不值得增加分片会话、合并和过期清理。
- 导入任务恢复解决大量 chunks 已处理一部分后，从未完成批次继续。这对生产 RAG 更有价值，但当前小文档同步流程暂不实现。

生产方案应先保存原文并创建 `ingestion_job`，由 Worker 按批生成向量，每批提交进度。任务记录 `pending/processing/completed/failed`、总 chunk 数、已完成数量、重试次数和错误信息；chunk 使用文档 ID、顺序、内容哈希、Embedding 模型和版本构成幂等约束。重试只处理未完成批次。

如果以后支持大型 PDF、音频或视频，文件本体应使用 S3、OSS、MinIO Multipart Upload 或 tus 协议完成可恢复上传。Agent 只调用上传或查询任务状态工具，不能负责分片、幂等和断点判断，这些必须由确定性的导入服务实现。

## 线上化重点

### 1. 异步任务与状态机

当前小文件采用同步上传，便于演示。生产环境通常先保存原文和任务，立即返回任务 ID，再由队列和 Worker 执行解析、分块和 Embedding。文档状态应包含 `pending/processing/processed/failed`，并记录可重试错误，不要让大文件长期占用 HTTP 请求。

### 2. 增量更新与幂等

使用来源 ID、文档版本和内容哈希判断新增、修改与重复上传。更新时先构建新版本，完整成功后原子切换为可检索版本，再删除旧 chunks，避免用户检索到一半新一半旧的数据。

### 3. 限流、重试与成本

Embedding 调用需要批处理、并发上限、超时、指数退避和随机抖动。只对超时、限流和部分服务端错误重试，认证失败和参数错误不应盲目重试。记录 token、请求次数、延迟和失败率，但不要记录 Key 或完整向量。

### 4. 权限与删除传播

检索、列表、引用详情和删除接口必须采用相同 ACL 规则。用户失去权限或原文被删除时，向量和缓存也必须同步失效。对于严格隔离场景，可以按租户分区或独立数据库，不能只依赖前端隐藏结果。

### 5. 检索质量

需要用真实问题集评估 chunk 大小、重叠、Top-K、距离阈值和召回率，不能只凭主观选择参数。数据量较小时精确检索更简单；规模扩大后再评估 HNSW 索引、召回率和写入成本。必要时增加关键词混合检索与 Rerank。

### 6. 模型与数据版本

文档向量和查询向量必须由兼容的 Embedding 模型及相同维度生成。更换模型时应记录 `embedding_model`、维度和版本，建立新向量版本并逐步切换，不能把不同模型向量混在同一索引中比较。

### 7. 安全与可观测性

除扩展名外，生产环境还要检查 MIME、恶意文件、压缩炸弹和解析器资源限制。知识文档属于不可信输入，后续生成阶段要防止文档中的提示注入改变系统规则。日志应包含任务 ID、文档 ID、阶段耗时、chunk 数和错误码，但不记录密钥、敏感原文或完整向量。

## 面试讲解口径

可以这样概括：

> 项目先完成可验证的 RAG 摄取链路。FastAPI 接收 Markdown/TXT，做安全校验和结构化分块；使用真实 Embedding API 批量生成 1024 维向量；再通过 SQLAlchemy 事务写入 Docker 中的 PostgreSQL + pgvector。ACL 保存在文档元数据中，下一阶段的向量检索会在 SQL 内先做权限约束再做 Top-K 排序。MVP 使用同步处理，生产环境会演进为带状态机、幂等版本和失败重试的异步任务。

不要说“完整 RAG 已完成”。准确说法是“RAG 摄取链路已完成并真实验收，检索和生成阶段待实现”。

## 验证记录

```text
pytest -q                 16 passed
ruff check app tests      All checks passed
pip check                 No broken requirements found
真实上传                   HTTP 200，3 chunks
数据库向量维度             3 个均为 1024
失败请求事务检查           0 条残留失败数据
```

当前本地 API 运行地址为 `http://127.0.0.1:8000`，Swagger 为 `http://127.0.0.1:8000/docs`。
