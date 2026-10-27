# 阶段 5：smolagents 工具编排

## 当前调用链

```text
POST /api/v1/agent/chat
  -> answer_business_question
  -> ToolCallingAgent
  -> GLM-4.7-Flash 选择工具
  -> OrderQueryTool / RefundEligibilityTool / RefundPreparationTool
  -> app.biz 业务函数
  -> PostgreSQL
  -> 工具结果返回 GLM
  -> 最终回答和工具轨迹返回客户端
```

## 安全边界

- Tool 在服务端绑定当前 `user_id`，模型只能提供 `order_id`。
- Tool 复用业务函数，不能绕过订单归属和退款规则。
- Agent 只拥有查询订单和检查退款资格两个只读工具。
- `apply_refund()` 没有注册为 Agent Tool，因此模型不能自行创建退款申请。
- `refund_prepare` 只检查资格并产生结构化待确认动作，不写数据库。
- 用户确认由 API 根据 `conversation_id` 校验并直接调用业务层，模型不能把普通对话文字当成执行授权。
- 用户也可提交 `cancel_pending_action=true` 清除待确认动作；确认和取消互斥，均不调用模型。
- 当前 API 的 `user_id` 仍来自请求体，只是 MVP 演示输入；生产环境必须改为认证上下文。

## 已验证结果

真实调用中，GLM-4.7-Flash 先调用：

```json
{"tool_name":"order_query","arguments":{"order_id":"demo-refundable"}}
```

再调用：

```json
{"tool_name":"refund_eligibility_check","arguments":{"order_id":"demo-refundable"}}
```

两个工具均返回真实 PostgreSQL 数据。最终回答说明订单符合 7 天模拟退款资格，并保留“创建申请需要明确确认”的边界。

免费模型存在拥堵和 429 风险。OpenAI 兼容客户端设置单次请求超时 15 秒、SDK 不自动重试，smolagents 自身的 429 重试也已关闭，Agent 最多执行 3 步；API 另以 45 秒作为端到端等待上限，超时返回 `504 AGENT_TIMEOUT`。由于底层 Agent 是同步执行，HTTP 等待可及时结束，但已进入线程池的任务不能被 Python 强制终止，这是当前实现的已知限制。

## 结构化确认流程

```text
用户提出退款并给出原因
  -> GLM 调用 refund_prepare
  -> 业务层检查资格（不写库）
  -> 服务端保存 pending_action
  -> 返回 conversation_id 和待确认内容
  -> 用户显式提交 confirm_pending_action=true
  -> 服务端校验会话所有者
  -> 服务端以稳定幂等键调用 apply_refund(confirmed=True)
  -> 清除 pending_action，返回 pending 模拟退款申请
```

若用户取消，则客户端提交同一 `conversation_id` 和 `cancel_pending_action=true`，服务端清除待确认动作且不创建退款申请。

会话状态当前保存在单进程内存中，30 分钟过期并限制为 1000 条，适合本地演示，不支持进程重启恢复或多实例共享。生产环境应迁移到 Redis 或数据库，并从认证上下文获取用户身份。

## 未完成

- 当前每次普通问答仍创建新 Agent，并使用 `reset=True`，不保存自然语言聊天历史。
- API 总超时不能强制杀死已经进入线程池的同步 Agent 任务；若要硬取消，应改用独立工作进程或任务队列。
- 内存会话状态尚未支持多实例共享和服务重启恢复。

## 前端接入规划（尚未实现）

当前项目只有 FastAPI 后端，不包含前端代码。后续可在同一 VS Code 工作区新增 `frontend/`，采用 React + TypeScript + Vite：

- 展示 Agent 对话、知识来源和工具调用轨迹。
- 收到 `pending_action` 时渲染明确的确认/取消控件。
- 点击确认后提交同一 `conversation_id` 和 `confirm_pending_action=true`，不让模型解释自然语言确认并决定写操作。
- 开发期前端预计运行在 `127.0.0.1:5173`，后端运行在 `127.0.0.1:8000`；届时需为 FastAPI 增加限定来源的 CORS 配置。
- 最小演示前端预计约 900～1800 行代码；源码和构建产物较小，主要磁盘占用为可删除、可重装的 `node_modules`。
