# 项目状态

**最近更新：2026-10-27**

## 2026-10-27 千问 3.7 Flash 接入与真实端到端验收

- 增加 `LLM_PROVIDER=qianwen|zhipu` 配置选择；本机 `.env` 已设为 `qianwen`、`QIANWEN_MODEL=qwen3.7-flash`，保留原智谱 Key 和 `embedding-3`/1024 维向量设置。`.env.example` 与 README 已更新，密钥未写入文档或示例；没有改动向量模型与数据库结构。
- Docker Desktop Linux Engine 和 Compose `db` 容器已启动；`GET /health` 与 `/health/db` 均返回 200。`RUN_LIVE_TESTS=1` 执行 `tests/test_live_end_to_end.py -s`：2 passed、1 条 pytest 缓存目录警告。真实知识文档上传→Embedding→pgvector 检索→千问 RAG 回答→删除测试文档，以及 Agent 准备模拟退款→用户显式确认→清理演示申请均通过。随后只读数据库确认 `live_refund_policy.md` 和 `demo-refundable` 的退款申请均为 0 条。
- 单独复测 `task_mode="refund_policy"`：一次 HTTP 200 执行 `order_query`、`refund_eligibility_check`、`knowledge_search` 后模型漏引来源编号，服务端门禁返回人工核实且无待确认动作；两次 HTTP 502 / `AGENT_UNAVAILABLE`（日志为 `AgentGenerationError`）。随后原提示词下直接调用又成功执行这三个工具且答案含来源编号。路径可成功但本轮稳定性未通过；尝试加强引用提示未改善，已撤回该提示改动，保留原门禁和失败兜底。
- 本轮最终执行 `pytest -q`：81 passed、4 skipped；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。未运行完整固定评测集，不能据此宣称整体回答质量达标。
- 收尾密钥检查发现 `.env.example` 的 `DEEPSEEK_API_KEY` 曾与本地 `.env` 同值；已立即替换为占位值，复查示例文件及项目文本未再发现与本地敏感值一致的内容。当前 Git 状态显示项目文件尚未跟踪，未见该值已提交的证据；若此示例文件曾被发送或推送到外部，应轮换 DeepSeek Key。

## 2026-10-27 千问 3.8 系列临时验收

- 阿里云官方模型列表当前提供 `qwen3.8-flash` 和 `qwen3.8-max`。使用现有 `QIANWEN_API_KEY` 与北京地域兼容接口旧域名，两个模型的最小聊天请求均返回 HTTP 200、内容 `OK`；未输出密钥，也未修改默认配置。
- 临时以 `qwen3.8-flash` 运行 `task_mode="refund_policy"` 只读样例：接口 HTTP 200，模型发起 `knowledge_search`、`order_query`、`refund_eligibility_check` 等工具调用，但服务端证据门禁返回“知识或业务工具执行失败，需人工处理”，`pending_action=null`；不能算多工具任务通过。
- 临时以 `qwen3.8-max` 运行只读订单样例：接口 HTTP 200，发起 `order_query`，工具报告 `DATABASE_UNAVAILABLE`，回答也明确数据库不可用；没有退款动作。
- 随后本地 `GET /health` 为 200、`GET /health/db` 为 503 / `DATABASE_UNAVAILABLE`。本轮可确认两个新模型的聊天接口可用且会发起工具调用，不能判断其数据库依赖的完整业务效果。恢复 PostgreSQL 后应复验。

**10 月 26–27 日项目讨论与验收汇总：** [WORK_LOG_2026_10_26_27.md](WORK_LOG_2026_10_26_27.md)。下方为逐次记录；同日较早结论须结合后续测试阅读。

## 2026-10-27 千问 3.7 Flash 临时联调

- `.env` 中 `QIANWEN_API_KEY` 已配置；使用北京地域兼容接口旧域名和 `qwen3.7-flash`，最小 `/chat/completions` 请求返回 HTTP 200，`choices[0].message.content="OK"`。未输出密钥。
- 两工具只读请求（`order_query`、`knowledge_search`）返回 HTTP 200、`finish_reason=tool_calls`，模型选择 `order_query(order_id="demo-refundable")`。这是模型工具调用输出，不代表业务工具已在该请求中执行。
- 在测试进程内临时将项目 LLM 配置指向千问，`POST /api/v1/agent/chat` 标准只读订单问题返回 HTTP 200，实际调用 `order_query`，回答订单状态 `completed`。
- 同样临时配置下，`task_mode="refund_policy"` 对 `demo-refundable` 的只读联调返回 HTTP 200，执行 `order_query`、`refund_eligibility_check`、`knowledge_search`，回答包含 `[1]`、`[3]` 来源编号；`pending_action=null`。未提交退款，也未修改 `.env` 或默认模型配置。
- 这验证了一个样例的真实多工具流程；其余任务质量、并发和稳定性仍需独立评测，不能据此宣称全面验收通过。

## 2026-10-27 DeepSeek API 连通性检查

- 检测到 `.env` 中已配置 `DEEPSEEK_API_KEY`（未输出密钥）。以 `deepseek-flash` 调用官方 `/chat/completions` 最小只读请求，服务端返回 HTTP 402、`insufficient_balance_error` / `Insufficient Balance`，无模型生成内容。仅能确认请求到达服务端，不能据此认定模型和项目 Agent 链路可用。
- 因账户余额不足，未执行 DeepSeek RAG 或 Agent 联调；未更改 `.env` 或模型默认配置。待账户有可用余额后重试最小请求，再验收工具调用和引用质量。

## 2026-10-27 GLM-4.7-Flash 再次连通性检查

- 使用项目 `.env` 中的智谱配置，按 `app/ai/llm.py` 的请求结构对 `/chat/completions` 发起一次最小真实请求（`model=glm-4.7-flash`、`temperature=0.1`、`max_tokens=800`）。结果：HTTP 429，响应 `error.code=1305`，没有生成 `choices`。
- 当前 `.env` 未配置 `DEEPSEEK_API_KEY`，因此未执行 DeepSeek 真实请求，也未宣称 DeepSeek 可用。未修改模型配置或业务代码。

## 2026-10-27 真实模型与备选免费模型验收

- 现有 `.env` 的 `glm-4.7-flash` 最小聊天请求返回 HTTP 429 / 上游代码 `1305`；`task_mode="refund_policy"` 的只读真实 Agent 请求返回 HTTP 502 / `AGENT_UNAVAILABLE`，日志确认底层为 429。尚未通过真实多步 Agent 验收。
- 核对智谱官方模型文档：`glm-4.5-flash` 已下线，旧 ID 会自动转到 `glm-4.7-flash`，无法作为独立回退。较早的免费文本模型 `glm-4-flash-250414` 普通聊天返回 200，单工具强制调用返回 1 个工具调用；但五工具列表的强制调用返回 200、0 个 `tool_calls`。实际 smolagents 只读请求连续出现 `AgentParsingError`，无工具执行。`glm-4.6v-flash` 多工具请求返回 429 / 1305。
- 临时把本进程模型设为 `glm-4-flash-250414` 后，RAG 接口返回 HTTP 200、命中 2 个来源；另一次同题请求虽返回 200，但答案没有按提示包含来源编号。该模型可用于临时普通问答排障，未通过本项目的多工具 Agent 和引用质量要求。
- 因回退模型未通过关键能力验收，**没有修改 `.env`、默认模型、`AGENTS.md` 或 `.env.example`**。本轮没有执行真实退款确认或写操作。后续需等待 4.7 恢复，或另行选定并验证兼容多工具调用的模型；不能将 HTTP 200 当作 Agent 任务成功。

## 2026-10-27 跨知识与订单的 Agent 任务模式

- 新增 `knowledge_search` 只读工具，复用 RAG 的 Embedding/pgvector ACL 检索；`POST /api/v1/agent/chat` 可选 `task_mode="refund_policy"`，需要租户上下文。该模式让 smolagents 在同一任务内调用知识与订单工具，跨轮保存上一笔订单号，并把步骤上限设为 6。
- 工具执行时保留逐次结构化结果，避免 smolagents 并行调用时合并观察文本导致证据错配。服务端在该模式返回前检查政策来源、订单及资格工具结果、订单号一致性、来源编号；失败时返回人工核实说明且不生成新的待确认动作。已有确认分支仍绕过模型。
- 边界：目前只是结构化证据门禁，尚不能验证每个生成事实是否与知识片段一致，也不能可靠判定自然语言政策与业务规则冲突；请求身份仍未认证，会话仍是单进程内存。真实 GLM 多步联调受提供方 429 影响，未标记为通过。简历不可写“完整事实校验/冲突自动仲裁/线上企业级”。
- 本轮实际执行 `& .\.venv\Scripts\python.exe -m pytest -q`：78 passed、4 skipped；`& .\.venv\Scripts\python.exe -m ruff check app tests`：All checks passed；`& .\.venv\Scripts\python.exe -m pip check`：No broken requirements found；设置 `RUN_DB_INTEGRATION=1` 后运行 `tests/test_db_workflow.py`：2 passed。未执行真实 GLM 多步调用。
- 新 `KnowledgeSearchTool` 以 `demo/demo-user/support` 对真实 Embedding 与 PostgreSQL 做只读联调：`ok=True`，命中 2 个来源；未输出来源正文或密钥。

## 2026-10-26 企业化目标核对

- 根据新的求职展示目标，新增 [ENTERPRISE_AGENT_PLAN.md](ENTERPRISE_AGENT_PLAN.md) 和路线图阶段 7。核对代码确认：现有 API 信任客户端提供的用户、租户和角色；会话存在单进程内存中；真实 GLM Agent 端到端验收仍受 429 阻塞。因此企业化能力目前仅为规划，不能写作已完成。
- 阶段 6 的真实模型验收仍优先；阶段 7 的方向和验收条件见企业化方案。此次仅修改文档，未改接口、数据库或执行测试。
- 根据用户侧重点调整阶段 7：优先深挖 Agent 质量评判、MCP 只读工具适配、模型及工具的限流熔断和请求追踪；真实登录态由现有网关/认证系统集成，持久会话属于多实例上线前提。当前代码尚无 MCP、熔断或可信身份集成，这些均未计为已完成。

## 2026-10-26 Swagger 契约补全

- 新增 `app/api/schemas.py`，为当前 12 条 MVP 路由声明成功响应模型；知识上传/列表/删除、RAG/反馈、订单/退款、Agent 确认与健康接口在 OpenAPI 中均有结构化 200 响应。常见非 422 业务错误也关联统一 `detail + error_code` 结构；FastAPI 自动参数校验 422 与自定义业务 422 的两种实际格式已在 API 契约说明。
- 现有测试中两个 `doc-1` 伪造文档 ID 与真实 UUID 契约不一致，已修正测试夹具；未改业务响应内容。
- `/openapi.json` 回归测试覆盖全部 12 条路径的 200 响应 `$ref`；默认 `pytest -q`：73 passed、4 skipped；本地 PostgreSQL 集成测试：2 passed；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。真实外部模型全链路仍未复测，最终演示验收尚未完成。
- 再次只读检查 `/openapi.json`：12 条路径；RAG、反馈与 Agent 接口列出 200、422 和各自常见业务错误响应；`/health/db` 返回 200。README 已补 RAG 回答的 `request_id` 反馈命令，并明确直接退款 API 与 Agent 确认示例复用同一演示订单，二者之间需要重置演示数据，否则会触发订单唯一退款约束。

## 2026-10-26 收尾验收进展

- 按求职演示 MVP 的原始目标粗估完成约 85%；这是主观里程碑估计，不表示生产可用。知识入库、RAG、业务工具、确认边界、反馈/评测已实现；真实模型完整复测、Swagger 响应模型完善与最终演示仍待完成。真实鉴权、持久聊天历史和运营前端也尚未实现。
- 新增 `tests/test_db_workflow.py`（显式 `RUN_DB_INTEGRATION=1`）：真实 PostgreSQL，固定 Embedding/Chat 输出。第一条链路走通文档上传、ACL 检索回答、反馈、幂等入队、驳回；第二条走通临时订单、资格检查、工具准备、确认前无申请、显式确认后仅一条模拟退款申请。临时数据在 `finally` 清理。
- 初次集成测试暴露 `sync_queue` SQL 中未定型的 UUID 参数，PostgreSQL 报 `AmbiguousParameter`；已对参数显式 CAST，重跑 2 passed。失败测试的临时记录已检查并清理。
- 运行态读接口：`/health` 200、`/health/db` 200、`/openapi.json` 200（12 条路径）；Swagger 路由及反馈请求模型存在，但各成功响应模型和错误响应的完整说明仍需补齐，阶段 6 的 Swagger 验收继续未勾选。
- 本轮默认 `pytest -q`：73 passed、4 skipped（2 条真实模型测试、2 条需显式启用的本地数据库集成测试）；显式启用本地数据库集成测试：2 passed；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。未运行真实模型全链路。

## 2026-10-26 待标注任务队列

- 新增 `db/init/007_feedback_review_queue.sql`，当前 PostgreSQL 已执行迁移；`/health/db` 增加队列表就绪检查。
- `app.evals.feedback_review sync` 扫描“无用且主动提交原问题”的反馈，按 `request_id` 幂等入 `ai.feedback_review_queue`；`export` 只导出待审任务；`promote` 把批准/驳回决定写回队列。当前没有用户负反馈，实际 `sync` 返回 0。
- 用临时模拟反馈验证：首次入队 1、再次入队 0、待审导出 1、驳回后待审导出 0；临时数据库记录已清理。这是定时扫描模式，不是实时字段监听或运营前端。
- 执行 `pytest -q`：72 passed、2 skipped；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。补充审核 case ID 的 UUID 校验；线上运营平台、真实身份认证、双人标注与审计字段尚未实现。

## 2026-10-26 智谱接口复查

- 使用项目现有配置各发送一次最小上游请求：`glm-4.7-flash` 聊天端点返回 HTTP 429 / 提供方代码 `1305`（约 0.55 秒）；`embedding-3` 端点返回 HTTP 200，实际向量长度为 1024（约 0.27 秒）。两种 Key 均已配置；未记录 Key 或响应正文。
- FastAPI TestClient 检查 `/health` 和 `/health/db` 均返回 200。以数据库实际的 `tenant_id=demo`、`user_id=demo-user` 调用 `/api/v1/chat`，检索到证据后上游聊天请求返回 429，应用返回 HTTP 502 / `LLM_UNAVAILABLE`；可确认当前阻塞在聊天模型端点。若传入不同 tenant，ACL 会使检索结果为空并直接返回无证据回答，此时不会请求聊天模型。
- 执行 `& .\.venv\Scripts\python.exe -m pytest -q tests/test_llm.py tests/test_embedding.py tests/test_chat.py tests/test_agent_api.py tests/test_rag.py`：25 passed。首次误用不存在的 `tests/test_chat_api.py` 路径，pytest 未运行任何测试；随后使用实际的 `tests/test_chat.py` 重跑通过。
- 本轮未执行真实 Agent 退款链路或写操作；上游聊天模型恢复前，Agent 的 live 验收仍待完成。另观察到 RAG 在 LLM 失败时日志中的 `retrieved_count` 仍为 0，可能低估已成功检索的请求，待单独修复观测逻辑。

## 2026-10-26 演示样本人工复核

- 已逐条阅读三份知识 fixture、演示订单与退款规则，复核 20 条 RAG、10 条 Agent 种子标签；具体人工预期、来源片段与已保存回答判定见 [EVALUATION_MANUAL_REVIEW.md](EVALUATION_MANUAL_REVIEW.md)。这属于项目内部复核，不是独立标注员或用户反馈。
- 修正 `rag-refund-08` 的含混提问：原“退货”不等于知识库定义的“模拟退款申请”；新题目明确询问模拟退款申请时限，旧观测不对应新题目，需重测。16 条可回答 RAG 样本已加 `expected_chunks`，评分器新增 `chunk_recall_at_k`。
- 使用旧观测离线重评分：20 条中 12 条 HTTP 200、8 条上游错误；可用样本上片段命中 8/8、文件命中 8/8、引用格式 8/8、正确拒答 4/4。人工逐条核对的 8 条可回答样本核心事实与所标来源相符；Agent 唯一旧成功回答工具正确但确认文案误导，服务端固定文案修复后尚未重新真实验证。
- 数据库只读核对：`demo-refundable` 已签收约 2 天、`demo-expired` 约 10 天、`demo-shipped` 未签收；3 条演示订单关联退款申请为 0。用户真实“无用”反馈仍为 0，不应称已完成人工标注用户反馈。
- 本轮执行 `& .\.venv\Scripts\python.exe -m pytest -q`：70 passed、2 skipped；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。未重新调用上游模型；下一步先确保可用率，再用修正后的固定集跑新基线与人工事实复核。

## 2026-10-26 固定样本的前后对比

- 新增 `app/evals/compare.py`：要求前后报告包含相同 case ID，分开统计可用性转换与两次都成功的同一案例上的结构检查得失；新失败和已成功案例的自动检查回退可直接识别。结果始终带 `manual_review_required=true`，不把结构指标当作事实正确性。
- 用已有 `evals/reports/rag-report.json` 自对比验证命令：20 条样本、12 条两次可用、8 条两次错误，自动信号 `no_automated_change`。这是工具烟测，没有实施新检索改动或证明效果改善。
- 新评测报告增加样本内容 SHA-256 指纹；对比时若两份新报告指纹不一致则拒绝比较，旧报告缺少指纹时输出 `case_content_verified=false`。执行 `pytest -q`：69 passed、2 skipped；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。下一步需要真实人工标注样本和实际改动前后两轮评测，才可判断质量是否提升。

## 2026-10-26 反馈人工标注闭环

- 新增 `app/evals/feedback_review.py`：只导出含用户主动提交问题的“无用”反馈，候选与批准后的固定评测集均写入被 Git 忽略的 `evals/private_cases/`。未批准样本不入集；批准样本必须填写可回答性、预期文件、事实核对说明和失败类型。
- 失败类型用于决定改进点：检索漏召回、召回不相关、回答无证据、错误拒答及其他。固定集通过现有 `app.evals.runner --cases` 回归；这不会更新 GLM 权重，改善来自知识、分块、检索、提示词或规则调整。
- 当前真实 PostgreSQL 查询和导出均为 0 条可用负反馈；没有伪造真实人工标注样本。新增模拟样本测试覆盖未批准过滤、标签校验及与现有评分器兼容。
- 执行 `& .\.venv\Scripts\python.exe -m app.evals.feedback_review export --out evals/private_cases/pending_review.jsonl`：0 cases；`pytest -q`：64 passed、2 skipped；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。真实反馈入集与上线后质量提升尚未发生。

## 2026-10-26 反馈回流与检索阈值实验

- 新增 `db/init/006_rag_feedback.sql` 中的 `ai.rag_requests` 和 `ai.rag_feedback`，在当前已有数据卷手动应用并核对两表。成功 RAG 回答生成 `request_id`，只存租户、用户、片段数、Top-1 分数及实验元数据；不自动保存问题或答案。用户显式提交 `POST /api/v1/chat/feedback` 后才保存可选问题/备注。相同请求 ID 反馈采用更新语义。
- 可选 `experiment=threshold_v1`：按租户和用户稳定分 A/B，A 保持请求 `min_score`，B 使用 `min(1.0, min_score + 0.1)`；响应及请求元数据均含分组和实际阈值。默认不参与实验，原阈值保持不变。
- 已用临时请求 ID 在真实 PostgreSQL 验证请求记录、实验分组、反馈写入及级联清理。此处仍是演示级闭环：没有真实鉴权、样本平衡分析、显著性检验或人工标注平台；不能凭点赞率直接断言 B 更好。
- 新迁移需要在旧数据卷显式执行，README 已给 PowerShell 命令；`/health/db` 现在检查反馈表。下一步可按分组汇总反馈与无证据率，建立人工标注流程。
- 执行 `& .\.venv\Scripts\python.exe -m pytest -q`：61 passed、2 skipped；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。本轮未调用外部模型，线上实验效果尚无数据。

## 2026-10-26 RAG 运行指标

- 为 `/api/v1/chat` 新增逐请求 JSON 指标日志：UTC 时间、HTTP 状态、耗时、返回片段数、Top-1 分数、Top-2 分差、无证据标记及应用错误码；不记录请求正文、答案、用户或租户标识。
- 当前仅写标准输出，尚无长期存储、看板、回流标注或 A/B 实验。检索后若 LLM 失败，来源数在此事件中为 0，不能误判为真正的无检索结果。
- 测试覆盖成功响应的分数分布、无证据与失败区分、敏感内容不进入事件。执行 `& .\.venv\Scripts\python.exe -m pytest -q`：58 passed、2 skipped；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。未调用外部模型验证实时生产日志。

## 2026-10-26 评测问题修复与上游诊断

- 对 GLM 聊天接口做了一次最小真实请求：上游返回 HTTP 429、业务码 `1305`。这解释了本次复核时模型不可用；上一轮 17 条评测失败只保存了应用层错误码，不能逐条反推全部都是 429。当前保持关闭 SDK 与 smolagents 的自动重试，避免免费额度拥堵时长时间占用请求。
- 生成 `pending_action` 时，Agent API 现在使用服务端固定确认说明覆盖模型的退款执行文案，明确要求同一 `conversation_id` 和 `confirm_pending_action=true`；普通文字“确认”不会创建申请。普通非待确认回答仍使用模型输出。
- LLM 和 Agent 失败时，服务端日志只记录 HTTP 状态码（如有）或异常类型，不记录上游响应正文、请求内容或密钥；对外错误码保持原样。
- 执行 `& .\.venv\Scripts\python.exe -m pytest -q`：56 passed、2 skipped；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。本轮未重复运行真实 30 条基线，需待上游可用后复测成功率和人工事实判断。

## 2026-10-26 真实评测基线尝试

- 为继续执行离线评测计划中的真实基线，先核对 `app/evals/runner.py`、评测样本、fixture 和数据库；数据库当时仍只有 `refund_policy.md`（3 个 chunk）。
- 初次在受限执行环境上传 `shipping_policy.md`、`product_faq.txt` 均返回 HTTP 502、`EMBEDDING_UNAVAILABLE`，直接连接抛出 `httpx.ConnectError`；放开本次外部网络请求后 Embedding 接口返回 HTTP 200，两份样例分别成功导入 3、1 个 chunk。初次失败后核对过数据库，没有部分导入。
- 实际运行 20 条 RAG live 样本，观测文件 `evals/reports/rag-observations.jsonl`、报告 `evals/reports/rag-report.json`（均被 Git 忽略）：12 条 HTTP 200、8 条 `LLM_UNAVAILABLE`。在 12 条可用结果中，`source_recall_at_k` 8/8、`valid_citation` 8/8、`no_evidence` 4/4；这些仅为文件级来源、引用格式及固定拒答检查，不代表答案事实正确率，也不能忽略 8 条失败。
- 实际运行 10 条 Agent live 样本，观测文件 `evals/reports/agent-observations.jsonl`、报告 `evals/reports/agent-report.json`：1 条 HTTP 200、9 条 `AGENT_UNAVAILABLE`。可用的 `agent-prepare-01` 在工具选择、参数、待确认动作和订单号四项结构检查各为 1/1；样本量太小，不能据此判断 Agent 整体效果。当前报告只记录应用层错误码，未确认这 17 次失败各自对应的上游 HTTP 原因。
- 人工查看 `agent-prepare-01` 回答发现其文字提示用户“回复确认”即可执行退款；实际 API 仅以 `confirm_pending_action=true` 作为授权，普通文字回复不会创建申请。这是需要修正的说明准确性问题，结构评分器当前捕捉不到。
- 执行 `& .\.venv\Scripts\python.exe -m pytest tests/test_evals.py -q`：6 passed。下一步优先提高外部模型调用可用性、修正 Agent 确认文案，并在人审事实与引用后重跑基线；目前不应按成功样本的 100% 结构分数宣称项目整体质量达标。

## 2026-10-26 离线质量评测基础

- 当前只读数据库核对：1 份知识文档 `refund_policy.md`（`demo/demo-user` 私有，3 个 chunk）、3 条 `demo-*` 订单、0 条退款申请。数据库可通过 `docker compose exec db psql -U smartservice -d smartservice` 查看，README 已补常用查询。
- 新增 `evals/cases/smartservice.jsonl`：20 条 RAG 与 10 条 Agent 种子用例，覆盖来源命中、无证据、ACL、订单工具、退款资格及准备。标签根据演示 fixture 编写，尚未独立人工复核。
- 新增 `app/evals/runner.py`：可评分已有 JSONL 观测，或显式使用 `--live` 采集真实 API 结果；分别统计来源命中、引用格式、无证据拒答、工具与参数及待确认动作。非 200 错误和缺失观测独立统计，不混入质量分母。
- 全量 RAG live 运行前需将配送政策和产品 FAQ 两份 fixture 上传至 `demo/demo-user`；当前数据库仅有退款政策。真实 30 条基线尚未运行，不能据此声称项目回答质量达到目标。
- 评分器只自动检查可确定的结构指标；事实忠实度和引用事实正确性仍需根据 `review_notes` 人工复核。用法、指标边界与数据准备见 [EVALUATION.md](EVALUATION.md)。
- 本轮执行 `& .\.venv\Scripts\python.exe -m pytest -q`：56 passed、2 skipped（live 用例默认跳过）；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。CLI 读取录制观测并写报告的测试已通过，尚未运行全量真实评测基线。

## 2026-10-26 工程收尾（进行中）

- 已实现 `GET /api/v1/knowledge/documents`：支持分页，并在数据库查询中应用与 RAG 一致的 public/tenant/private ACL。
- 已实现 `DELETE /api/v1/knowledge/documents/{document_id}`：只有同租户文档所有者可删除，角色可读权限不授予删除权限；chunks 由外键级联删除。
- Agent 待确认动作新增 `cancel_pending_action=true`，确认和取消互斥，二者均绕过模型并由服务端确定性处理。
- 新增 `db/demo/reset_demo_data.sql`，只重置三条 `demo-*` 订单、明细和关联模拟退款，支持重复演示。
- 新增两个需显式设置 `RUN_LIVE_TESTS=1` 的真实端到端测试，覆盖知识上传/列表/RAG/删除和 Agent 退款准备/确认；默认测试不会调用外部模型。
- 已同步 README、API 契约与路线图，补充文档管理、退款确认/取消、演示数据重置和真实联调命令。
- 当前默认验证为 `50 passed, 2 skipped`，Ruff 与 `pip check` 通过；两个默认跳过项需显式启用真实 PostgreSQL、Embedding、GLM。
- 首轮 live 验收中知识库全链路通过，Agent 退款准备连续两次在 45 秒 API 总预算处超时。诊断发现 OpenAI SDK 重试虽已关闭，但 smolagents 自身仍默认对 429 重试；显式设置 `retry=False` 后，失败可在约 4 秒内返回 502。最小真实请求确认外部原因为智谱 `429 / code 1305`（模型当前访问量过大），Agent 退款 live 流程尚未通过，待免费模型恢复后复验。
- `db/demo/reset_demo_data.sql` 已在真实 PostgreSQL 执行成功：删除 3 条订单明细和 3 条订单后重新写入，关联退款当时为 0 条；事务完整提交。
- 运行态复核通过：`GET /health` 与 `GET /health/db` 均返回 200；OpenAPI 列出 11 条路径，并包含 `conversation_id`、确认和取消字段。
- 最终敏感配置检查只发现 `.env.example` 中的占位值；`.env` 由 `.gitignore` 明确排除。

## 2026-10-24 工作总结：受控退款确认与前端规划

### 今日完成

- 在现有 `order_query`、`refund_eligibility_check` 基础上新增只读 `refund_prepare` 工具。模型只负责识别退款意图、收集订单号和原因、检查资格，不具备创建退款申请的写权限。
- 新增结构化 `pending_action` 与 `conversation_id`。待确认内容保存在服务端，不以模型自然语言输出作为执行依据。
- 用户必须通过请求字段 `confirm_pending_action=true` 明确确认；该分支绕过 GLM 和 ToolCallingAgent，由 FastAPI 校验会话归属后直接调用业务层 `apply_refund(confirmed=True)`。
- 确认操作使用稳定幂等键，成功后清除待确认动作；返回状态为模拟申请 `pending`，不表示真实资金已经退回。
- 新增单进程内存会话存储，配置为 30 分钟过期、最多 1000 条；适合本地演示，但不支持服务重启恢复或多实例共享。
- Agent API 增加 45 秒端到端等待上限，超时返回 `504 AGENT_TIMEOUT`；单次模型请求仍为 15 秒、关闭 SDK 自动重试、最多 3 个 Agent 步骤。
- 最终自动化验证为 `46 passed`；Ruff 为 `All checks passed`；`pip check` 为 `No broken requirements found`。
- 已重启 FastAPI 并验证 `GET /health`、`GET /health/db` 均正常；OpenAPI 已出现 `conversation_id` 和 `confirm_pending_action` 字段。
- 已将 2026-10-23 12:00 之后关于 ToolCallingAgent、CodeAgent、smolagents 与自研 Loop、受控参数、工具路由、Embedding 分工、写操作确认、生产选型和前端职责的讨论集中整理到 [AGENT_ENGINEERING_NOTES.md](AGENT_ENGINEERING_NOTES.md)。

### 今日形成的技术认识

- Tool 最小化不是取消模型意图识别，而是只向模型暴露当前场景、当前权限和当前状态允许的工具；工具规模较小时可一次提供，规模较大时再增加规则、Embedding 或小模型路由进行预筛选。
- Embedding 模型负责把文本转换为向量，当前用于 RAG 检索；GLM 对话模型负责意图理解、工具选择和答案生成；pgvector 只负责向量存储与相似度计算。
- 高风险写操作不能仅依赖模型判断“用户是否确认”。模型可以准备动作和生成提示，但最终授权应使用结构化字段或前端确认按钮，由确定性服务端代码执行。
- 当前项目尚无前端，但可以在同一个 VS Code 工作区增加 `frontend/`，推荐 React + TypeScript + Vite。源码预计约 900～1800 行，主要磁盘占用来自可重建的 `node_modules`，总额外占用约 300～800 MB。
- Agent 工程师在个人项目和小团队中通常需要能制作轻量演示页面；中大型团队的生产页面通常由前端工程师负责，但 Agent 工程师仍需设计流式响应、会话、工具状态、来源引用和确认协议。

### 今日未执行

- 没有重新调用真实 GLM 验证 `refund_prepare`，避免免费模型拥堵；本轮通过自动化测试验证工具和确认编排。
- 没有创建前端工程，前端仍处于方案讨论阶段。
- 没有实现普通自然语言聊天历史持久化；当前“多轮”只覆盖结构化待确认动作。

## 2026-10-23 阶段 5：smolagents 工具编排（进行中）

- 已新增 `OrderQueryTool` 与 `RefundEligibilityTool`，分别复用 `get_order()` 和 `check_refund_eligibility()`，工具不直接访问或修改数据库。
- `user_id` 在服务端创建 Tool 时绑定，GLM 只能提交 `order_id`，不能通过工具参数切换为其他用户。
- Agent 不暴露退款创建工具；模型只能查询资格，并必须说明创建模拟退款仍需用户明确确认。
- 已安装并固化 `smolagents[openai]` 依赖，使用 `OpenAIServerModel` 连接智谱 OpenAI 兼容接口。
- 真实 smolagents 联调成功：GLM-4.7-Flash 依次调用 `order_query` 和 `refund_eligibility_check`，工具结果来自真实 PostgreSQL，最终答案正确说明订单可退款及确认边界。
- 已新增 `POST /api/v1/agent/chat`；最初为无状态单轮接口，后续已扩展为带结构化退款待确认状态的 `conversation_id`。
- 免费模型随后出现拥堵：两次 Agent HTTP 验收超过 90 秒客户端上限，最终配置的复验仍达到 70 秒客户端上限。已将单次模型请求限制为 15 秒、关闭 SDK 自动重试，并将 Agent 限制为 3 步；但当前 SDK 的超时按模型步骤计算，不是整个 Agent 的总预算，后续仍需增加端到端任务超时与取消机制。
- 阶段 5 最初验收为 40 passed；当前仍不保存普通自然语言历史，但已实现结构化退款确认会话。
- 新增只读 `RefundPreparationTool`：模型可提交订单号和用户给出的退款原因，工具复用业务层检查资格，只返回结构化待确认动作，不创建退款。
- `POST /api/v1/agent/chat` 现返回服务端生成的 `conversation_id`；通过同一会话提交 `confirm_pending_action=true` 后，服务端校验会话归属并确定性调用 `apply_refund()`，模型不能直接执行写操作。
- 确认使用由会话 ID 和动作 ID 构造的稳定幂等键；成功后清除待确认动作，返回的 `pending` 仍明确表示模拟退款申请。
- 新增单进程内存会话存储：30 分钟 TTL、1000 条上限。它不保存普通聊天历史，不支持重启恢复或多实例共享，生产环境需迁移到 Redis/数据库并接入真实认证上下文。
- Agent API 新增 45 秒端到端等待上限，超时返回 `504 AGENT_TIMEOUT`。线程池中的同步任务无法被强制终止，硬取消仍需独立进程或任务队列。
- 本轮自动化测试更新为 46 passed，Ruff 与 `pip check` 通过；覆盖待确认动作、会话归属、确认执行、smolagents 字符串 observation 和总超时。

## 2026-10-23 阶段 4：订单与模拟退款

- 已实现订单查询、退款资格检查、模拟退款申请创建和退款申请查询接口；业务逻辑位于 `app/biz`，API 层不直接操作数据库。
- 退款资格以 `delivered_at` 为起点，只有 `completed` 且签收不超过 7 个自然日的订单符合资格。
- 创建申请必须显式传入 `confirmed=true`；所有结果均表示模拟申请，初始状态为 `pending`，不代表真实资金已退回。
- 已增加客户端 `idempotency_key`，数据库使用 `(user_id, idempotency_key)` 唯一索引支持安全重放，并以 `order_id` 唯一索引阻止同订单重复退款；并发冲突由数据库约束兜底。
- 已执行 `004_refund_idempotency.sql`，并写入三条演示订单：`demo-refundable`、`demo-expired`、`demo-shipped`。
- 真实 HTTP 验收通过：订单查询和资格检查成功；同一请求提交两次返回同一退款 ID；未确认返回 `409 NOT_CONFIRMED`；同订单新请求返回 `409 DUPLICATE_REFUND`；过期订单返回不可退款。
- 自动化与静态检查：`pytest -q` 为 33 passed，Ruff 为 All checks passed，`pip check` 未发现依赖冲突。
- 阶段说明见 [STAGE4_BUSINESS_APIS.md](STAGE4_BUSINESS_APIS.md)。

## 2026-10-23 对话模型升级与连通性验证

- 根据智谱官方模型概览与定价页，当前最新的免费文本模型为 `glm-4.7-flash`；`glm-5.3-flash` 是更新、更强的低价模型，但并非免费模型。
- 已使用本地 `.env` 中的标准 API Key 调用 `glm-4.7-flash`：`POST /chat/completions` 返回 HTTP 200，服务端返回模型名一致，首次最小请求共使用 14 Tokens。
- 已通过项目现有 `app.ai.llm.chat_completion()` 封装再次验证，模型成功返回 `OK`，无需更换 API 协议或 SDK。
- 连续快速调用期间两次收到 HTTP 429，稍后重试恢复成功；免费模型存在较严格限流，生产调用应增加指数退避、抖动和最大重试次数。
- 已将 `.env`、`.env.example`、应用默认配置和项目长期技术选型更新为 `glm-4.7-flash`；Embedding 继续使用独立的 `embedding-3`，不受本次变更影响。

## 2026-10-23 阶段 3：ACL 向量检索

- 已新增 `app/ai/rag.py`：问题向量化、请求参数校验、数据库内 ACL 条件、相似度阈值和 Top-K 余弦检索。
- 已新增 `app/db/vector.py`，统一校验 1024 维有限数值并生成 pgvector literal；知识导入与查询复用同一实现。
- ACL 检索语义已落入 SQL：公开文档，或同租户的 tenant 文档，或同租户 private 文档的所有者/允许角色。
- pgvector 使用 `<=>` 计算余弦距离，返回分数为 `1 - distance`；默认 `top_k=5`、`min_score=0.5`，阈值仍需后续评测集校准。
- 离线测试覆盖检索 SQL、参数、错误向量、非有限数值、LLM 响应、无证据分支和 Chat API；当前 `pytest -q` 为 27 passed，Ruff 通过。
- 首次真实检索时 Docker 数据库未运行，问题 Embedding 已成功，但数据库连接超时并被正确映射为 `DATABASE_UNAVAILABLE`；随后启动容器并恢复就绪。
- 真实 ACL 检索通过：`support` 角色查询“商品签收后多少天内可以申请退款？”返回 3 条，Top-1 为退款申请时限，分数约 0.7236；无角色且非所有者返回 0 条。
- 已真实确认本地配置 `glm-4-flash` 可用：`/chat/completions` 返回 HTTP 200，请求和响应模型名一致。
- 已实现 `POST /api/v1/chat`：带 ACL 检索、编号证据提示、GLM 回答、结构化来源和无证据回退。
- 真实 RAG HTTP 验收通过：有 `support` 角色时回答 7 个自然日并引用 `[1]`，返回 3 条来源；无权限时返回固定无证据文案和 0 条来源。
- 低相关度验收通过：有权限用户询问火星天气并设置 `min_score=0.8`，返回固定无证据文案和 0 条来源。
- 阶段 3 实现、Docker 启动关系和真实验收记录见 [STAGE3_RAG_IMPLEMENTATION.md](STAGE3_RAG_IMPLEMENTATION.md)。

## 2026-10-23 知识库上传与 ACL

- 已实现 `POST /api/v1/knowledge/upload`，支持 UTF-8 Markdown/TXT、10MB 限制、文件名与路径穿越校验。
- 已串联同步处理链路：上传校验、结构化分块、真实 `embedding-3`、PostgreSQL 事务写入。
- 文档保存文件哈希、字节数、租户、所有者、可见范围和允许角色；chunk 保存标题路径、文本、文本哈希、顺序和 `vector(1024)`。
- ACL 以文档表为唯一事实来源，后续向量检索必须在 SQL 中联表并应用权限条件。
- 已执行 `003_knowledge_metadata_acl.sql` 迁移。
- 真实 HTTP 上传 `refund_policy.md` 成功：文档 ID `ee752eb5-6ca1-4379-aae1-8bdbe8f4fc60`，3 个 chunk，数据库确认三个向量均为 1024 维。
- 首次在受限网络进程中调用返回 `502 EMBEDDING_UNAVAILABLE`，没有写入半成品；使用允许联网的服务进程后端到端成功。
- MVP 的 ACL 表单参数不代表真实鉴权；生产环境必须从可信认证上下文获取租户、用户和角色。
- `pytest -q`：16 passed；`ruff check app tests`：All checks passed；`pip check`：No broken requirements found。
- 数据库验收时共有 1 个成功导入文档和 3 个 chunks；首次 502 失败没有产生残留记录。
- 已将阶段 2 的 RAG 摄取流程、技术选型、chunk/ACL 数据结构、事务边界、线上化注意事项和面试讲解口径整理到 [STAGE2_KNOWLEDGE_INGESTION.md](STAGE2_KNOWLEDGE_INGESTION.md)。
- 已补充知识导入调用链的学习记录：异步事件循环与线程池、二进制和多模态的区别、规则分块职责，以及文件断点续传与导入任务恢复的取舍。

## 2026-10-22 Embedding 集成进展

- 已新增 `app/ai/embedding.py`，通过智谱兼容接口 `/embeddings` 调用真实 Embedding 服务。
- 已新增 Embedding 配置校验、响应数量校验、数值类型校验和向量维度校验。
- `.env.example` 已恢复为占位 Key，并增加 `EMBEDDING_DIMENSIONS=1024` 示例配置。
- 发现真实 API Key 曾被误写入可提交的 `.env.example`；该 Key 应在智谱控制台撤销并重新生成，不再用于项目调用。
- 已使用本地 `.env` 中的新 Key 真实调用 `embedding-3`；请求显式指定 1024 维，响应包含 1 个 1024 维数值向量。
- 已将初始化结构及当前数据库的 `ai.document_chunks.embedding` 固定为 `vector(1024)`；数据库实际查询确认列类型为 `vector(1024)`。
- 已新增 `db/init/002_embedding_dimension.sql`，记录现有数据库的维度迁移。
- 已实现 Markdown/TXT 结构感知分块：Markdown 标题路径继承、自然边界切分、最大长度限制和相邻块重叠。
- 已增加退款政策、配送政策和产品 FAQ 三份 Mock 知识文档，位于 `tests/fixtures/knowledge/`。
- 分块默认参数为目标 800 字符、最大 1200 字符、重叠 120 字符，可通过环境变量调整。
- 下一步：实现上传文件安全校验，将分块批量生成 Embedding 并事务写入数据库。

## 当前阶段

阶段 5 的核心工具编排和结构化退款确认已完成。当前处于阶段 6 工程收尾：离线功能、文档管理和安全检查已有记录；千问下一个只读多工具样例真实通过，待完成退款准备/确认端到端和固定评测集复验。轻量前端不属于当前收尾范围。

阶段 1 的实现方式、SQLAlchemy 当前职责与验证边界记录在 [STAGE1_IMPLEMENTATION.md](STAGE1_IMPLEMENTATION.md)。

## 已完成内容

- [x] 环境检查：Python 3.14.7、pip 26.2.1、Git 2.55.0
- [x] 确认项目为 Python-only 架构（无 Java）
- [x] 初始化 Git 仓库
- [x] 创建项目目录结构
- [x] 创建 AGENTS.md、docs/PROJECT_STATUS.md、docs/ROADMAP.md、docs/API_CONTRACTS.md
- [x] 创建 .gitignore、.env.example、pyproject.toml
- [x] 确认 .venv 中已安装 FastAPI 0.156.8、pydantic 2.14.1
- [x] 将 `agent.md` 中仍适用的长期规则合并到 `AGENTS.md`，统一为 Python-only 单工作区方案
- [x] 创建 PostgreSQL 16 + pgvector 的 Compose 配置及 `ai`、`biz` 五张基础表初始化 SQL（文件已创建，尚未在真实数据库执行）
- [x] 实现 FastAPI `/health` 和 `/health/db`，`/health` 经真实 HTTP 请求返回 200；数据库未运行时 `/health/db` 返回 503
- [x] 项目 `.venv` 安装并导入 SQLAlchemy、psycopg、pgvector、smolagents 等核心依赖
- [x] 修正 `pyproject.toml` 的 setuptools 包发现范围，项目可通过 editable 模式安装
- [x] 添加阶段 1 本地启动说明和健康检查测试
- [x] 将阶段 1 实现链路、SQLAlchemy 的当前用途、验证证据与后续验收步骤整理到 `docs/STAGE1_IMPLEMENTATION.md`
- [x] 安装并启动 Docker Desktop 4.96.1，确认 Docker Engine 29.9.2、Compose 5.6.0 和 `desktop-linux` 上下文可用
- [x] 将 Docker Desktop CLI 目录加入用户级 PATH；新开的 PowerShell/VS Code 终端可直接使用 `docker`
- [x] 创建本地 `.env`，配置数据库连接并确认该文件被 `.gitignore` 排除
- [x] 拉取 `pgvector/pgvector:0.8.7-pg16-bookworm`，启动 PostgreSQL 16 容器并达到 healthy
- [x] 真实验证 pgvector 0.8.7、`ai`/`biz` schema 和五张基础表
- [x] 真实执行 SQLAlchemy `check_database()`，并验证 `/health`、`/health/db` 均返回 HTTP 200

## 未完成内容

- [x] 实现知识库文档列表与删除接口
- [x] 实现订单查询、退款资格检查与模拟退款申请
- [x] 知识库真实上传、列表、RAG、删除端到端通过
- [x] Agent 退款准备与确认真实端到端通过（千问 3.7 Flash；仅模拟退款，测试结束已清理申请）
- [x] 完成最终敏感信息扫描与离线交付检查

## 环境检查结果

| 工具 | 状态 | 版本 | 备注 |
|------|------|------|------|
| Python | ✅ 已安装 | 3.14.7 | .venv 虚拟环境 |
| pip | ✅ 已安装 | 26.2.1 | |
| FastAPI | ✅ 已安装 | 0.156.8 | |
| pydantic | ✅ 已安装 | 2.14.1 | |
| SQLAlchemy / psycopg / pgvector | ✅ 已安装并完成真实联调 | 2.1.5 / 3.3.6 / 0.5.1 | PostgreSQL 运行于 Docker Desktop |
| smolagents | ✅ 已安装并完成真实 GLM 工具调用 | 1.26.0 | 订单查询和退款资格工具已联调；新增准备工具尚未重新调用真实 GLM |
| Git | ✅ 已安装 | 2.55.0.windows.5 | |
| WSL / Linux Engine | ✅ 可用 | WSL2 kernel 6.18.54.1 | Docker Engine 实际运行于 `desktop-linux` |
| Docker Desktop / Engine / Compose | ✅ 可用 | 4.96.1 / 29.9.2 / 5.6.0 | 用户级安装；CLI 路径已加入用户 PATH |
| Java | ⏭ 不需要 | - | 项目为 Python-only |
| Maven | ⏭ 不需要 | - | 项目为 Python-only |

## 阻塞问题

智谱免费模型此前连续返回 `429 / code 1305`，DeepSeek 最小请求返回 402（余额不足）；当前本机已切换到千问 `qwen3.7-flash`。数据库已恢复，知识/RAG 和模拟退款准备/确认真实测试通过。跨知识与订单的 `refund_policy` 任务仍有漏引与 `AgentGenerationError`，完整固定集质量复验未完成。3.8 系列此前的失败发生在数据库未就绪时，不能直接比较模型能力。

## 已知缺陷与技术债务

- 当前仅使用精确向量检索，尚未建立 HNSW/IVFFlat 索引；数据规模增大并完成召回评测后再选择近似索引。
- 当前 MVP 以一个订单最多一份退款申请为规则；若未来支持驳回后重新申请，需要将唯一约束调整为状态相关的部分索引。
- `pyproject.toml` 使用依赖版本下限，尚无锁定依赖的文件；当前安装结果不等于所有未来安装均一致。
- `.env.example` 中的 `FASTAPI_HOST`、`FASTAPI_PORT` 当前未被 Uvicorn 启动命令读取；实际监听地址由命令行的 `--host`、`--port` 决定。以后若需要统一配置，应明确接入或删除这两个示例变量。
- Agent 会话当前保存在单进程内存，不能跨重启或多实例共享；生产环境应迁移到 Redis 或数据库。
- 45 秒 API 等待超时不能强制终止已经进入线程池的同步 Agent；若需要硬取消，应使用独立工作进程或任务队列。
- 当前不保存普通对话历史，仅保存退款待确认动作；后续如实现完整多轮对话，需要限制历史长度并避免将自然语言历史当作写操作授权。

## 下一步任务

1. 排查 `refund_policy` 多工具任务的 `AgentGenerationError` 和漏引来源，保留服务端证据门禁；用固定样本重复验证其可用性与事实正确性。
2. 用固定 RAG/Agent 集运行真实模型评测，人工检查来源事实、工具轨迹、错误率与成本；单例和两项端到端测试通过不能替代基线。
3. 核对 Git 待提交文件；在用户要求提交时再创建首次提交。

## 本次核对（2026-10-22）

- `docker version`：Client/Server 29.9.2；Server 为 Docker Desktop 4.96.1，`desktop-linux` 上下文，WSL2 Linux 内核。
- `docker compose version`：5.6.0；Compose 配置校验通过。
- 首次 `docker compose up -d` 因 Docker CLI 目录不在 PATH，找不到 `docker-credential-desktop`；临时补充 PATH 后镜像拉取和容器启动成功，随后将该目录持久加入用户级 PATH。
- `docker compose ps`：`smartservice-db-1` 为 healthy，绑定 `127.0.0.1:5432`。
- 初始化日志：`vector` 扩展、`ai`/`biz` schema 和五张表均创建成功；容器内 SQL 查询确认 pgvector 0.8.7 和五张表存在。
- `& ./.venv/Scripts/python.exe -c "from app.db.connection import check_database; check_database(); print('database_ready')"`：成功输出 `database_ready`。
- 实际 HTTP：`GET /health` 返回 `{"status":"ok","version":"0.1.0"}`；`GET /health/db` 返回 `{"status":"ok"}`；OpenAPI 包含两个路径。
- `pytest -q`：3 passed；Ruff：All checks passed；`pip check`：No broken requirements found。
- `.env` 已创建且 `git check-ignore -v .env` 确认由 `.gitignore` 排除；未在文档中记录本地数据库密码。
- 敏感信息扫描首次因 ripgrep 默认正则不支持前瞻而失败；改用 `rg --pcre2` 后完成扫描，除被排除的本地 `.env` 外未发现真实 API Key 或数据库密码。
- Uvicorn 当前运行于 `http://127.0.0.1:8000`；数据库容器当前保持运行。

## 历史核对（2026-10-21）

- `git status --short --branch`：仓库尚无提交，现有项目文件均未跟踪；没有覆盖已有文件。
- `./.venv/Scripts/python.exe --version`：Python 3.14.7；`pip --version`：26.2.1。
- `Get-Command docker`：未找到；`wsl --list --verbose`：无已安装发行版（退出码 1）。
- `wsl --status`：默认版本 2，但系统明确提示“WSL2 无法启动，因为此计算机上未启用虚拟化”；命令本身退出码为 0。
- `& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"`：首次在沙箱内因 PyPI 访问受限失败；沙箱外首次因 setuptools 将 `db`、`app`、`data` 误识别为多个顶层包失败；修正包发现后重试成功。
- `& ./.venv/Scripts/python.exe -m pytest -q`：3 passed。
- `& ./.venv/Scripts/python.exe -m ruff check app tests`：All checks passed。
- `& ./.venv/Scripts/python.exe -m pip check`：No broken requirements found。
- `import smolagents, sqlalchemy, psycopg, pgvector`：成功。
- 实际启动 Uvicorn 后，`GET /health` 返回 `{"status":"ok","version":"0.1.0"}`；`GET /health/db` 返回 HTTP 503；OpenAPI 已列出两个路由。
- Docker Compose、PostgreSQL 初始化 SQL、真实数据库就绪检查、外部 GLM 和 Embedding 调用均未执行。
- 2026-10-21 文档整理后复测：`& ./.venv/Scripts/python.exe -m pytest -q` 为 3 passed；`& ./.venv/Scripts/python.exe -m ruff check app tests` 为 All checks passed；`& ./.venv/Scripts/python.exe -m pip check` 为 No broken requirements found。此次未进行真实数据库联调。

# 2026-10-27：企业化优先级 1 质量门禁

已实现固定案例与演示数据双指纹、Agent 必要工具/额外调用检查、人工事实与安全审阅门禁；详情和真实运行命令见 [EVALUATION_GATE_2026_10_27.md](EVALUATION_GATE_2026_10_27.md)。最新 30 条真实评测 30/30 可用，Agent 精确工具选择 9/10，人工事实审核 29/30，最终门禁 **block**。当前待修复项为 `rag-refund-06` 的退款资格过度推断；修复后须重新评测和人工复核。此前 Agent 指令试验发生漏调必要工具，已撤销。单测 89 passed、4 skipped，Ruff 检查通过。旧数据快照和新快照的指标不可直接归因比较。此前终端显示的知识片段乱码经检查只是输出编码问题。

**同日后续更新：** RAG 提示词修复后，20 条固定 RAG 案例真实复测 20/20 可用、人工事实复核 20/20、RAG 子集门禁 `pass`。30 条完整复测曾出现 Agent 漏调资格工具与重复查询，整体仍未通过，不把 RAG 子集结果称为整体验收。跨知识与订单模式增加三类工具故障注入，均验证不会保存待确认动作。单测 92 passed、4 skipped；Ruff 检查通过。下一步是稳定 Agent 必要工具调用，再做完整固定集与人工复核。详见 [EVALUATION_GATE_2026_10_27.md](EVALUATION_GATE_2026_10_27.md)。

