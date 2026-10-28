# SmartService

SmartService is a Python AI customer service demo built around two paths: evidence-based knowledge Q&A and an order/refund Agent. It connects FastAPI, PostgreSQL/pgvector, real Embedding calls, an OpenAI-compatible chat model, and smolagents. Refunds are simulated; no payment provider is called.

## What this project demonstrates

- **RAG:** upload Markdown/TXT documents, split and embed them, filter retrieval by document ACL in PostgreSQL, and return answers with source references or an explicit refusal when evidence is missing.
- **Tool-using Agent:** query orders, check refund eligibility, and search policy documents. In `refund_policy` mode, the server verifies required tool evidence, order consistency, and a policy citation before accepting a prepared action.
- **Controlled write:** the model can prepare a simulated refund, but only an explicit client confirmation causes the business service to create an application. The service applies business rules and an idempotency key.
- **Quality checks:** 30 curated RAG/Agent cases, retrieval and tool-call checks, human fact review, feedback capture, and a lightweight retrieval-threshold experiment. These checks expose failures; they do not establish production quality.

### Architecture

```text
Client -> FastAPI (app/api)
             |-- /chat -> RAG (app/ai/rag.py) -> Embedding API
             |                   |              -> PostgreSQL/pgvector (ai schema)
             |                   +-> chat model -> answer + sources
             |-- /agent/chat -> smolagents (app/ai/agent.py)
             |                      |-> knowledge search
             |                      |-> order/refund tools -> app/biz -> PostgreSQL (biz schema)
             |                      +-> evidence check -> pending action
             +-- explicit confirmation -> app/biz/refunds.py -> simulated application
```

The API, AI orchestration, business rules, and database access live in separate modules. The model can query data and prepare a pending action; the service binds caller-provided user context to business queries, enforces refund rules, and performs the final database write. The optional LangChain order demo (`app/ai/langchain_order_demo.py`) is a separate CLI exercise and does not replace the smolagents API.

### Current validation and limits

- With the optional LangChain demo dependencies installed, the local automated suite passes **97 tests** with **4 skipped**; the default run uses no external model or PostgreSQL. An earlier real run completed knowledge upload, Embedding, retrieval, Q&A, and a simulated refund prepare/confirm flow.
- A 20-case RAG subset passed a real-model run with project-level human review. The **full 30-case Agent quality gate has not passed**: multi-tool tasks have intermittently missed required calls or citations and encountered provider errors. A successful single run is not a stability claim.
- This is a local MVP. Request `user_id`/roles are not backed by login; conversation state is process-local. There is no production rate limiting, circuit breaker, persistent Agent trace, MCP server, or real payment refund.

Start with [Local setup](#local-setup), then use the [API examples](#api-development-workflow) and [test commands](#tests). The public repository keeps implementation notes in this README; local development notes under `docs/` are intentionally excluded from Git.

## Local setup

Requirements: Python 3.14, Docker Desktop with a working WSL 2 backend, and Docker Compose. The Python service runs on Windows; PostgreSQL runs in Docker. Run the PowerShell commands below from the project root.

After installing Docker Desktop, restart VS Code (or open a fresh PowerShell from the Start menu) and verify `docker version` and `docker compose version`. This machine uses a per-user Docker Desktop installation, so its `resources\bin` directory must be present in the user `PATH`.

1. Create the project virtual environment if it does not already exist:

   ```powershell
   py -3.14 -m venv .venv
   ```

2. Copy `.env.example` to `.env`, replace the local PostgreSQL password placeholder in both `POSTGRES_PASSWORD` and `DATABASE_URL`, and set `LLM_PROVIDER=qianwen` with a valid `QIANWEN_API_KEY`. The demo chat model is `qwen3.7-flash`. Set a valid `EMBEDDING_API_KEY` for Zhipu `embedding-3`; existing pgvector data remains compatible because this does not change the embedding model. To switch chat back to Zhipu, set `LLM_PROVIDER=zhipu` and configure `ZHIPU_API_KEY`. Keep `.env` out of Git.
3. Install dependencies in the project virtual environment:

   ```powershell
   & ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
   ```

4. Start PostgreSQL:

   ```powershell
   docker compose up -d
   docker compose ps
   ```

5. Start the API in another terminal:

   ```powershell
   & ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

6. Open `http://127.0.0.1:8000/docs`. `GET /health` checks the API process; `GET /health/db` checks the PostgreSQL connection, pgvector extension, and required tables.

The SQL in `db/init/` runs only when the PostgreSQL data volume is created for the first time. `docker compose down` stops the database without deleting its data.

## Optional LangChain order demo

Install the small LangChain exercise in the project virtual environment:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -e ".[langchain-demo]"
```

With the existing database and configured chat model available, run:

```powershell
& ".\.venv\Scripts\python.exe" -m app.ai.langchain_order_demo --user-id demo-user --order-id demo-refundable
```

The command uses LangChain `create_agent` and one `order_query` tool backed by `app.biz.orders.get_order`. It prints the answer and tool result for inspection. It only reads orders and does not create refund applications. `--user-id` is a local demo input, not a verified login identity. The normal `/api/v1/agent/chat` API continues to use smolagents. No new API route is registered.

For an existing database volume, apply the feedback migrations from the project root (they are safe to rerun):

```powershell
Get-Content -Raw db/init/006_rag_feedback.sql | docker compose exec -T db psql -U smartservice -d smartservice
Get-Content -Raw db/init/007_feedback_review_queue.sql | docker compose exec -T db psql -U smartservice -d smartservice
```

Use `docker compose stop` to stop PostgreSQL and `docker compose start` to start the existing container again. `docker compose down` removes the container and network but preserves the named data volume unless `--volumes` is explicitly supplied.

## API development workflow

From PowerShell, call the running API with:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
```

The route is `/health` (not `/heath`). You can start the API without Docker and call `/health`; `/health/db` returns 503 until PostgreSQL and its schema are ready.

Upload a knowledge document with:

```powershell
curl.exe -X POST `
  -F "file=@tests/fixtures/knowledge/refund_policy.md;type=text/markdown" `
  -F "tenant_id=demo" `
  -F "owner_user_id=demo-user" `
  -F "visibility=private" `
  -F "allowed_roles=support" `
  http://127.0.0.1:8000/api/v1/knowledge/upload
```

The ACL fields are demonstration inputs, not authentication. A production API must derive tenant, user, and roles from trusted authentication context.

List ACL-visible documents or delete a document as its owner:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/v1/knowledge/documents?tenant_id=demo&user_id=demo-user&roles=support"

Invoke-RestMethod `
  -Method Delete `
  "http://127.0.0.1:8000/api/v1/knowledge/documents/<document-id>?tenant_id=demo&user_id=demo-user"
```

Role-based access can make a private document readable, but only its owner can delete it. Deleting the document also deletes its chunks through the database foreign key.

Ask a RAG question with:

```powershell
$body = @{
  question = "商品签收后多少天内可以申请退款？"
  tenant_id = "demo"
  user_id = "demo-user"
  roles = @("support")
  top_k = 3
  min_score = 0.5
} | ConvertTo-Json

$chat = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))

$chat | Select-Object request_id, answer, sources
```

Use the returned `request_id` to submit a rating. Include `question` only when the user agrees to store the original text for review:

```powershell
$feedbackBody = @{
  request_id = $chat.request_id
  tenant_id = "demo"
  user_id = "demo-user"
  rating = "helpful"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/chat/feedback" `
  -Method Post -ContentType "application/json" -Body $feedbackBody
```

Query the refundable demo order and check its refund eligibility:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/orders/demo-refundable?user_id=demo-user"

$body = @{ order_id = "demo-refundable"; user_id = "demo-user" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/refunds/check-eligibility" `
  -Method Post -ContentType "application/json" -Body $body
```

For a combined policy and order task, call the Agent with `task_mode="refund_policy"`. Use the returned `conversation_id` on a later turn; the service retains the last queried order ID in its process-local conversation state:

```powershell
$body = @{
  message = "查询订单 demo-refundable 的退款资格，并说明知识库中的退款政策"
  user_id = "demo-user"
  tenant_id = "demo"
  roles = @("support")
  task_mode = "refund_policy"
} | ConvertTo-Json
$agentResult = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/agent/chat" `
  -Method Post -ContentType "application/json" -Body $body

$agentResult | Select-Object answer, conversation_id, pending_action
$agentResult.tool_calls | Select-Object tool_name, arguments, result
```

Inspect the returned `answer`, `conversation_id`, `tool_calls`, and `pending_action`; the exact answer and tool sequence depend on the model and available evidence. This mode checks for successful policy search, order lookup, eligibility lookup, matching order IDs, and a policy citation before accepting a prepared refund action. Missing evidence or failed tools return a human-review message with no new pending action. This is a structural guard, not a guarantee that every generated policy claim is factually correct. The MVP still trusts caller-provided identity fields and stores conversation context only in one process.

Creating a simulated refund requires `confirmed=true` and a stable, client-generated idempotency key. Repeating the same request returns the same refund application:

```powershell
$body = @{
  order_id = "demo-refundable"
  user_id = "demo-user"
  reason = "No longer needed"
  confirmed = $true
  idempotency_key = "demo-refund-request-001"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/refunds/apply" `
  -Method Post -ContentType "application/json" -Body $body
```

Before using `demo-refundable` for the Agent confirmation walkthrough below, reset the demo orders with the reset command near the end of this section. The direct API and Agent examples both create a refund application for the same order; the database allows only one.

Run the business Agent:

```powershell
$body = @{
  message = "查询订单 demo-refundable，并检查它是否符合模拟退款资格。"
  user_id = "demo-user"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/agent/chat" `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

To prepare a simulated refund, ask the Agent with an explicit reason. The response contains a `conversation_id` and `pending_action`; preparation does not write a refund application:

```powershell
$prepareBody = @{
  message = "请为订单 demo-refundable 准备模拟退款，原因是商品损坏。"
  user_id = "demo-user"
} | ConvertTo-Json

$prepared = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/agent/chat" `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($prepareBody))

$confirmBody = @{
  message = "确认提交模拟退款申请"
  user_id = "demo-user"
  conversation_id = $prepared.conversation_id
  confirm_pending_action = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/agent/chat" `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($confirmBody))
```

Use `cancel_pending_action=true` instead of `confirm_pending_action=true` to discard the pending action. Confirmation and cancellation bypass the model and are mutually exclusive.

Reset only the three demo orders and their simulated refund applications before repeating a demo:

```powershell
Get-Content -Raw ".\db\demo\reset_demo_data.sql" |
  docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

The Uvicorn startup command above controls the listening address: `--host 127.0.0.1` is local-only, and `--port 8000` makes the URL `http://127.0.0.1:8000/health`. To use port 8080, start it with `--port 8080` and call `http://127.0.0.1:8080/health`. Restart the server after changing host or port. `POSTGRES_PORT` in the Compose configuration is a separate database port. The `FASTAPI_HOST` and `FASTAPI_PORT` entries in `.env.example` are **not read by the current Uvicorn command**; editing them alone has no effect.

Python does not require a manual compile step here. Uvicorn loads `app.main:app` when started, while `app/main.py` defines the `/health` route. In development, `--reload` restarts the worker after Python source changes; editing this README does not change a running process or its startup arguments.

Stop a server running in your terminal with **Ctrl+C**. Uvicorn has no separate `stop` command. If the terminal is gone, the following PowerShell fallback finds the project's virtual-environment Python process and force-stops it and its children; use it only when no other Python task is running from this `.venv`:

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -eq (Resolve-Path '.\.venv\Scripts\python.exe').Path } |
  ForEach-Object { taskkill /PID $_.Id /T /F }
```

Process IDs change between runs, so do not save a PID as a permanent stop command. Check `/health` again at the start of a new session instead of assuming the server is still running.

## Tests

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q
& ".\.venv\Scripts\python.exe" -m ruff check app tests
& ".\.venv\Scripts\python.exe" -m pip check
```

The default suite does not call external models or require PostgreSQL.

For the local PostgreSQL workflow without calling external AI services:

```powershell
$env:RUN_DB_INTEGRATION = "1"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_db_workflow.py -q -m integration
Remove-Item Env:RUN_DB_INTEGRATION
```

This test creates temporary documents, feedback, and orders, then removes them. It verifies database and API wiring while using fixed embedding/chat outputs.

With PostgreSQL and the API credentials ready, run the opt-in real workflow tests with:

```powershell
$env:RUN_LIVE_TESTS = "1"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_live_end_to_end.py -q -m live
Remove-Item Env:RUN_LIVE_TESTS
```

These tests upload and delete a temporary knowledge document and temporarily clear/recreate the simulated refund for `demo-refundable`.

## Inspect local data

Enter PostgreSQL from the project root:

```powershell
docker compose exec db psql -U smartservice -d smartservice
```

Inside `psql`, inspect tables and a small sample of rows:

```sql
\dt ai.*
\dt biz.*
SELECT id, filename, tenant_id, visibility, chunk_count FROM ai.documents;
SELECT document_id, chunk_index, left(chunk_text, 100) FROM ai.document_chunks LIMIT 10;
SELECT id, user_id, status FROM biz.orders ORDER BY id;
SELECT id, order_id, status FROM biz.refund_applications;
```

Use `\q` to leave `psql`. The vector column is intentionally omitted from the sample query because each vector has 1024 numbers.

## Offline evaluation

Successful RAG responses include `request_id`. To opt into the retrieval threshold experiment, send `"experiment": "threshold_v1"` in the chat request; the response includes variant A/B and its effective threshold. Variant assignment is stable per tenant and user, so this is a small demonstration experiment rather than a production A/B platform. Submit explicit feedback with `POST /api/v1/chat/feedback` using that `request_id`, `tenant_id`, `user_id`, and `rating` (`helpful` or `unhelpful`). Include `question` only when the user agrees to store the original text for later labeling. The request and response schemas are defined in [the API modules](app/api). The MVP user ID is not authenticated.

The 30 curated cases are in [evals/cases/smartservice.jsonl](evals/cases/smartservice.jsonl). The [evaluation runner](app/evals/runner.py) checks source recall, citations, refusals, tool names and arguments, and pending actions. Answer factuality still needs human review using each case's `review_notes`; [gate.py](app/evals/gate.py) combines structural checks and human decisions.

Before a live RAG run, upload the three fixture documents once as private documents for `demo/demo-user` with role `support`. The current demo database may already contain `refund_policy.md`; list documents before uploading to avoid duplicate copies.

For the current database, `refund_policy.md` is already present. Upload the other two fixtures:

```powershell
curl.exe -X POST `
  -F "file=@tests/fixtures/knowledge/shipping_policy.md;type=text/markdown" `
  -F "tenant_id=demo" -F "owner_user_id=demo-user" `
  -F "visibility=private" -F "allowed_roles=support" `
  http://127.0.0.1:8000/api/v1/knowledge/upload

curl.exe -X POST `
  -F "file=@tests/fixtures/knowledge/product_faq.txt;type=text/plain" `
  -F "tenant_id=demo" -F "owner_user_id=demo-user" `
  -F "visibility=private" -F "allowed_roles=support" `
  http://127.0.0.1:8000/api/v1/knowledge/upload
```

```powershell
& ".\.venv\Scripts\python.exe" -m app.evals.runner --live --kind rag `
  --observations-out evals/reports/rag-observations.jsonl `
  --report evals/reports/rag-report.json
```

To score previously collected observations without calling external services:

```powershell
& ".\.venv\Scripts\python.exe" -m app.evals.runner --kind rag `
  --observations evals/reports/rag-observations.jsonl `
  --report evals/reports/rag-replay.json
```

Use `--kind agent` for the Agent cases after the provider's 429 limit clears. The runner uses FastAPI's in-process test client, so it needs the database and API credentials but no Uvicorn process. Reports and raw observations are ignored by Git.

`user_id` values in the API are demonstration inputs, not authentication. Refunds are simulated; no payment provider is connected.
