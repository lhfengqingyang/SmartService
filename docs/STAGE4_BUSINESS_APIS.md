# 阶段 4：订单与模拟退款业务接口

## 调用链

```text
FastAPI route
  -> run_in_threadpool
  -> app.biz 业务函数
  -> SQLAlchemy transaction
  -> PostgreSQL biz schema
```

API 层负责 Pydantic 参数校验、线程池调度和错误映射。`app.biz.orders` 与 `app.biz.refunds` 是业务事实来源，后续 Agent 工具必须调用这些函数，不能直接修改数据库。

## 退款规则

- 订单必须属于请求中的 `user_id`；MVP 尚无真实鉴权，生产环境不能信任查询参数中的用户身份。
- 只有 `completed` 且存在 `delivered_at` 的订单进入退款窗口判断。
- 退款截止时间为 `delivered_at + 7 days`，超过截止时间不可申请。
- 创建模拟退款前必须传入 `confirmed=true`，否则返回 `409 NOT_CONFIRMED`。
- 创建结果固定从 `pending` 开始，只表示模拟申请已创建，不表示真实退款成功。

## 幂等与并发

客户端为一次业务意图生成稳定的 `idempotency_key`。相同用户、相同 Key、相同订单和原因的重复请求返回原退款记录；相同 Key 改变参数返回 `IDEMPOTENCY_CONFLICT`。

数据库唯一索引 `(user_id, idempotency_key)` 防止同一请求并发创建两份记录，`order_id` 唯一索引防止同一订单用不同 Key 重复申请。应用在 `IntegrityError` 后重新读取冲突记录，因此正确性最终由 PostgreSQL 约束保证，而不是依赖“先查询再插入”的时间窗口。

## 演示数据

- `demo-refundable`：已签收 2 天，可退款。
- `demo-expired`：已签收 10 天，超过窗口。
- `demo-shipped`：运输中，尚不可退款。

`db/init` 只在新数据卷首次创建时自动执行。现有数据库需要按顺序手动执行 `004_refund_idempotency.sql` 和 `005_demo_orders.sql`。

## 验证结果

- 离线测试覆盖订单接口、归属隐藏、退款窗口、未签收和确认边界。
- 真实 HTTP 查询演示订单成功，资格检查返回可退款及明确截止时间。
- 相同退款请求连续提交两次返回相同退款 ID。
- 未确认请求返回 `409 NOT_CONFIRMED`；同一订单使用新 Key 再申请返回 `409 DUPLICATE_REFUND`。
- 本阶段不接入支付渠道，也不会执行真实资金操作。
