# API 接口约定

**最近更新：2026-10-26**

> 本文同时记录已实现接口与明确保留的 MVP 限制；各接口状态以对应条目为准。

## 通用约定

- 基础路径：`/api/v1`
- 响应格式：JSON
- 错误响应结构：
  ```json
  {
    "detail": "错误描述",
    "error_code": "ERROR_CODE"
  }
  ```
- FastAPI 对字段类型/长度等请求校验失败时还可能返回默认的 HTTP 422 `{"detail": [ ... ]}`；业务代码主动返回的 422 使用上面的 `detail + error_code` 结构。调用方需区分这两类错误。
- 时间格式：ISO 8601（`2026-10-21T12:00:00Z`）
- 分页参数：`page`（从 1 开始）、`page_size`（默认 20，最大 100）

---

## 健康检查

### GET /health

**状态**：已实现并通过本地 HTTP 验证（阶段 1）

**HTTP 状态码**：200

**响应**：
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

`/health` 仅表示 API 进程可响应，不检查数据库。

### GET /health/db

**状态**：已实现，并已通过真实 PostgreSQL 16 + pgvector 容器验证。

**HTTP 状态码**：200（数据库、pgvector 扩展、五张基础表和三张反馈相关表就绪）；503（未配置、无法连接或结构不完整）。

**200 响应**：`{"status":"ok"}`

**503 响应**：`{"detail":"Database is not ready","error_code":"DATABASE_UNAVAILABLE"}`

此接口不会向客户端暴露数据库连接信息或底层异常。

---

## 知识库接口

### POST /api/v1/knowledge/upload

**状态**：已实现，并通过真实 HTTP、智谱 Embedding 和 PostgreSQL 联调（阶段 2）

**请求**：`multipart/form-data`
- `file`: 文件（Markdown 或 TXT，最大 10MB）
- `tenant_id`: 租户标识，1-64 字符
- `owner_user_id`: 文档所有者标识，1-64 字符
- `visibility`: `private | tenant | public`，默认 `private`
- `allowed_roles`: 逗号分隔的角色名称，可为空，最多 20 个

**响应**：
```json
{
  "document_id": "uuid",
  "filename": "string",
  "chunk_count": 0,
  "status": "processed"
}
```

**错误码**：
- `UNSUPPORTED_FILE_TYPE`：不支持的文件类型
- `FILE_TOO_LARGE`：文件超过大小限制
- `INVALID_FILENAME`：文件名不合法
- `INVALID_ENCODING`：文件不是有效 UTF-8 文本
- `EMPTY_DOCUMENT`：空文档或无法产生分块
- `INVALID_ACL`：ACL 参数不合法
- `EMBEDDING_UNAVAILABLE`：Embedding 服务调用失败，HTTP 502

上传采用同步处理：校验、分块、批量 Embedding 全部成功后，在一个数据库事务中写入文档和 chunks。Embedding 失败时不写入半成品。

MVP 中 ACL 参数由请求表单提供，仅用于演示数据隔离，不能视为已经认证的用户身份。生产环境必须从 JWT、Session 或 API Gateway 提供的可信身份上下文生成 ACL，不能直接信任用户提交的 `tenant_id`、`owner_user_id` 和角色。

### GET /api/v1/knowledge/documents

**状态**：已实现。返回调用者按 RAG 相同 ACL 规则可见的文档。

**查询参数**：
- `tenant_id`：调用者租户
- `user_id`：调用者用户 ID
- `roles`：逗号分隔角色
- `page`：默认 1
- `page_size`：默认 20，最大 100

**响应**：
```json
{
  "items": [
    {
      "document_id": "uuid",
      "filename": "string",
      "chunk_count": 0,
      "visibility": "private | tenant | public",
      "created_at": "ISO8601"
    }
  ],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

### DELETE /api/v1/knowledge/documents/{document_id}

**状态**：已实现。只有同租户的文档所有者可以删除；角色可读权限不授予删除权限。删除文档时 chunks 通过外键级联删除。

**查询参数**：`tenant_id`、`user_id`

**响应**：
```json
{
  "deleted": true
}
```

**错误码**：
- `DOCUMENT_NOT_FOUND`：文档不存在或调用者不是所有者，HTTP 404
- `INVALID_ACL` / `INVALID_REQUEST`：调用上下文或分页参数不合法，HTTP 422
- `DATABASE_UNAVAILABLE`：数据库操作失败，HTTP 503

---

## 问答接口

### RAG 检索内部约定

- 用户问题使用与知识库一致的 `embedding-3` 和 1024 维配置生成查询向量。
- PostgreSQL 使用 pgvector `<=>` 计算余弦距离，接口层使用 `1 - distance` 表示相似度。
- 查询顺序为 ACL 过滤、相似度阈值、距离升序和 Top-K；禁止从全库取 Top-K 后再在 Python 中过滤权限。
- `top_k` 允许 1-20，当前默认 5；`min_score` 允许 0-1，当前默认 0.5，后续应以评测集校准。
- 检索结果包含 chunk/document ID、文件名、chunk 顺序、标题路径、原文和相似度。
- 当前 ACL 调用上下文仍是 MVP 参数；生产环境必须由可信认证上下文提供。

### POST /api/v1/chat

**状态**：RAG 问答已实现并通过真实 HTTP 验证；Swagger 已提供该接口的成功响应结构。Agent 工具调用由独立的 `/api/v1/agent/chat` 接口提供。

**请求**：
```json
{
  "question": "string",
  "tenant_id": "string",
  "user_id": "string",
  "roles": ["string"],
  "top_k": 5,
  "min_score": 0.5,
  "experiment": null
}
```

**响应**：
```json
{
  "request_id": "uuid",
  "experiment": null,
  "variant": null,
  "effective_min_score": 0.5,
  "answer": "string",
  "sources": [
    {
      "document_id": "uuid",
      "filename": "string",
      "chunk_index": 0,
      "heading": "string | null",
      "chunk_text": "string",
      "score": 0.0
    }
  ],
  "conversation_id": null,
  "tool_calls": [
    {
      "tool_name": "string",
      "arguments": {},
      "result": {}
    }
  ]
}
```

  当前不保存对话历史，因此 `conversation_id` 固定为 `null`。无满足阈值且有权限的证据时，返回固定答案 `现有知识库无法确认这个问题。` 和空 `sources`，并跳过对话模型调用。成功回答会写入 `ai.rag_requests` 并返回 `request_id`。不传 `experiment` 保持原有阈值；传 `threshold_v1` 时，按租户与用户稳定分为 A/B：A 使用请求阈值，B 使用 `min(1.0, min_score + 0.1)`。返回实际阈值和分组，便于后续按组比较。

### POST /api/v1/chat/feedback

提交一次成功 RAG 回答的反馈。请求示例：

```json
{
  "request_id": "uuid",
  "tenant_id": "demo",
  "user_id": "demo-user",
  "rating": "helpful",
  "question": "可选：用户明确同意回流的原问题",
  "comment": "可选备注"
}
```

`rating` 为 `helpful | unhelpful`；`question` 和 `comment` 可省略，只有显式提交后才写入数据库。相同 `request_id` 重复提交会更新原反馈。成功返回 `{ "saved": true, "request_id": "uuid" }`；请求 ID 不存在或租户/用户不匹配返回 404 `REQUEST_NOT_FOUND`，反馈存储不可用返回 503 `FEEDBACK_STORE_UNAVAILABLE`。本地 MVP 的 `tenant_id` / `user_id` 未经过身份认证，不可作为生产环境的反馈鉴权。

**错误码**：
- `INVALID_REQUEST`：ACL 或检索参数不合法，HTTP 422
- `EMBEDDING_UNAVAILABLE` / `INVALID_EMBEDDING`：问题向量化失败，HTTP 502
- `LLM_UNAVAILABLE`：对话模型调用失败，HTTP 502
- `DATABASE_UNAVAILABLE`：数据库检索失败，HTTP 503

---

## 订单接口

### GET /api/v1/orders/{order_id}

**状态**：已实现并通过真实 PostgreSQL 与 HTTP 验证（阶段 4）

**路径参数**：
- `order_id`: 订单 ID

**查询参数**：
- `user_id`: 用户 ID（待确认：MVP 阶段鉴权方式）

**响应**：
```json
{
  "order_id": "string",
  "user_id": "string",
  "status": "pending | paid | shipped | completed | cancelled",
  "items": [
    {
      "product_name": "string",
      "quantity": 1,
      "price": 0.0
    }
  ],
  "total_amount": 0.0,
  "created_at": "ISO8601",
  "delivered_at": "ISO8601 | null"
}
```

**错误码**：
- `ORDER_NOT_FOUND`：订单不存在

---

## 退款接口

### POST /api/v1/refunds/check-eligibility

**状态**：已实现（阶段 4）。资格窗口从 `delivered_at` 起算 7 个自然日，仅 `completed` 订单可申请。

**请求**：
```json
{
  "order_id": "string",
  "user_id": "string"
}
```

**响应**：
```json
{
  "eligible": true,
  "reason": "string (当 ineligible 时说明原因)",
  "deadline": "ISO8601 (可选, 退款截止时间)"
}
```

### POST /api/v1/refunds/apply

**状态**：已实现并验证确认边界、幂等重放和重复订单保护（阶段 4）

**请求**：
```json
{
  "order_id": "string",
  "user_id": "string",
  "reason": "string",
  "confirmed": true,
  "idempotency_key": "string，8-128 字符"
}
```

**响应**：
```json
{
  "refund_id": "uuid",
  "order_id": "string",
  "status": "pending | approved | rejected",
  "created_at": "ISO8601"
}
```

**错误码**：
- `NOT_ELIGIBLE`：不符合退款资格
- `NOT_CONFIRMED`：未确认退款申请
- `DUPLICATE_REFUND`：同一订单已经存在退款申请
- `IDEMPOTENCY_CONFLICT`：同一幂等键被用于不同参数

### GET /api/v1/refunds/{refund_id}

**状态**：已实现（阶段 4），查询参数 `user_id` 必填；其他用户查询时按不存在处理。

**响应**：
```json
{
  "refund_id": "uuid",
  "order_id": "string",
  "status": "pending | approved | rejected",
  "reason": "string",
  "created_at": "ISO8601"
}
```

---

## 数据库表约定

### 文档分块约定

- Markdown 按标题层级划分章节，并将完整标题路径写入每个分块文本。
- TXT 作为无标题正文处理，优先在段落、换行和句末标点处分割。
- 默认目标长度 800 字符、最大长度 1200 字符、相邻块重叠 120 字符。
- 完整 fenced code block 在长度允许时不拆分；超过最大长度时允许硬切分。
- `chunk_index` 在单个文档内从 0 开始连续递增。
- 空文档不生成分块；当前长度单位为 Python 字符数，不宣称等同于模型 token 数。
- chunk 保存 `document_id`、连续序号、标题路径、正文、正文 SHA-256 和 1024 维向量；文件名、原文件哈希、大小和 ACL 保存在文档表。

### 知识库 ACL 约定

- `public`：所有调用者可检索。
- `tenant`：仅同一 `tenant_id` 的调用者可检索。
- `private`：仅同租户的所有者，或命中 `allowed_roles` 的调用者可检索。
- 向量检索 SQL 必须在数据库查询中同时应用 ACL 条件，不能先取 Top-K 再在 Python 中过滤，否则可能泄露结果且造成召回不足。
- ACL 以 `ai.documents` 为唯一事实来源，chunk 通过 `document_id` 关联，不重复保存权限字段。

### ai schema

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `ai.documents` | 知识库文档与 ACL | `id`, `filename`, `file_type`, `chunk_count`, `content_sha256`, `size_bytes`, `tenant_id`, `owner_user_id`, `visibility`, `allowed_roles`, `created_at` |
| `ai.document_chunks` | 文档片段与向量 | `id`, `document_id`, `chunk_index`, `heading`, `chunk_text`, `content_sha256`, `embedding vector(1024)`, `UNIQUE(document_id, chunk_index)` |

### biz schema

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `biz.orders` | 模拟订单 | `id(VARCHAR PK)`, `user_id`, `status`, `total_amount`, `created_at`, `delivered_at` |
| `biz.order_items` | 订单明细 | `id(UUID PK)`, `order_id(FK)`, `product_name`, `quantity`, `price` |
| `biz.refund_applications` | 退款申请 | `id(UUID PK)`, `order_id(FK, UNIQUE)`, `user_id`, `status`, `reason`, `idempotency_key`, `created_at`, `UNIQUE(user_id, idempotency_key)` |

**Embedding 维度**：1024。使用 `embedding-3` 并在请求中显式指定 `dimensions=1024`；该维度已通过真实 API 响应确认。

`embedding` 列使用 `vector(1024)` 类型。阶段 2 写入前还必须在应用层校验响应向量维度；近似向量索引将在检索实现时根据实际数据量和距离算法建立。

基础表由 `db/init/001_schema.sql` 定义，首次初始化 PostgreSQL 数据卷时执行；后续迁移脚本补充 Embedding 维度、ACL 元数据和退款幂等约束。退款幂等键及订单唯一退款约束已实现并通过阶段 4 验证。

反馈审核队列由 `db/init/007_feedback_review_queue.sql` 增量创建：`ai.feedback_review_queue(request_id PK/FK, status, enqueued_at, reviewed_at)`。`status` 为 `pending | approved | rejected`。离线 `sync` 命令仅从“无用且已提交问题”的反馈中按 `request_id` 幂等入队；审批状态由本地人工审核命令更新，不通过公开 API 暴露。

---

## Agent 工具约定

工具中的 `user_id` 由服务端可信上下文绑定，不暴露给模型作为参数。当前 API 中的 `user_id` 仍是 MVP 请求字段，尚不代表已完成身份认证。

### order_query

**参数**：`{ "order_id": "string" }`
**返回**：订单信息（同 GET /api/v1/orders/{order_id} 响应）

### knowledge_search（`refund_policy` 任务模式）

**参数**：`{ "question": "string" }`
**返回**：`{ "ok": true, "sources": [{ "number": 1, "document_id": "uuid", "filename": "string", "chunk_index": 0, "text": "string", "score": 0.8 }] }`；无命中时 `sources=[]`。检索或向量化失败时返回 `ok=false` 和 `error_code`。
**约束**：使用本次请求的租户、用户和角色做与 RAG 相同的文档 ACL 过滤。当前这些身份字段仍由客户端提供，尚无真实登录态校验。

### refund_eligibility_check

**参数**：`{ "order_id": "string" }`
**返回**：退款资格信息（同 POST /api/v1/refunds/check-eligibility 响应）

### refund_prepare

**参数**：`{ "order_id": "string", "reason": "string" }`
**返回**：资格检查结果；符合资格时返回结构化 `pending_action`
**注意**：该工具只准备动作，不写入退款申请。服务端保存待确认状态后，必须由用户显式确认才能调用业务层 `apply_refund()`。

### refund_apply（不向 Agent 暴露）

**参数**：`{ "order_id": "string", "user_id": "string", "reason": "string" }`
**返回**：退款申请信息（同 POST /api/v1/refunds/apply 响应）
**注意**：此工具必须要求用户确认后才能执行。

### POST /api/v1/agent/chat

**状态**：已实现 Agent 查询、结构化退款待确认状态及确认执行；普通聊天历史仍不持久化。

新增可选 `task_mode="refund_policy"`：请求必须提供 `tenant_id`，可提供 `roles`；同一会话后续请求须使用相同租户。该模式为 Agent 增加 `knowledge_search`，最多执行 6 步，并把上一轮已查询的订单号作为结构化上下文传入下一轮。返回前服务端检查知识来源、订单查询、资格检查和订单号一致性；任一必需工具失败、无证据、缺少来源引用或待确认动作与订单不一致时，不保存新待确认动作，返回需要人工核实的说明。`task_mode` 默认为 `standard`，原有请求保持兼容。

该校验只证明必要工具调用和引用标记存在，**不能自动证明模型的每个政策事实都与文档一致，也不能可靠识别自然语言政策与业务结果的所有冲突**。会话上下文仍为单进程内存；真实 GLM 多步链路尚待外部接口恢复后验证。

**请求**：
```json
{
  "message": "查询订单 demo-refundable，并检查退款资格",
  "user_id": "demo-user",
  "conversation_id": null,
  "confirm_pending_action": false,
  "cancel_pending_action": false
}
```

**响应**：
```json
{
  "answer": "string",
  "tool_calls": [
    {
      "tool_name": "knowledge_search | order_query | refund_eligibility_check | refund_prepare",
      "arguments": {"order_id": "string"},
      "result": {}
    }
  ],
  "conversation_id": "uuid",
  "pending_action": null
}
```

当 `refund_prepare` 成功时，响应包含：

```json
{
  "pending_action": {
    "action_id": "string",
    "action": "apply_refund",
    "order_id": "demo-refundable",
    "reason": "商品损坏",
    "requires_confirmation": true
  }
}
```

准备成功且生成 `pending_action` 时，`answer` 由服务端给出固定的确认说明，不直接使用模型生成的执行指引。确认时提交同一 `conversation_id`，并设置 `confirm_pending_action=true`；仅发送“确认”等普通消息不会创建申请。服务端校验会话归属并使用稳定幂等键调用业务层；确认不再交给模型判断。当前会话存储是单进程内存实现，30 分钟过期、最多 1000 条，服务重启或多实例间不共享。

取消时提交同一 `conversation_id` 并设置 `cancel_pending_action=true`，服务端直接清除待确认动作。确认和取消不能同时为 `true`，两条路径均绕过模型。

**错误码**：
- `INVALID_REQUEST`：消息或用户参数无效，HTTP 422
- `AGENT_UNAVAILABLE`：模型或 Agent 执行失败，HTTP 502
- `AGENT_TIMEOUT`：Agent 端到端执行超过 45 秒，HTTP 504
- `CONVERSATION_NOT_FOUND`：会话不存在、已过期或不属于当前用户，HTTP 404
- `NO_PENDING_ACTION`：确认时没有待确认动作，HTTP 409
