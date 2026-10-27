# 固定样本人工复核记录（2026-10-26）

## 复核范围与判定口径

本轮由项目开发代理逐条阅读 `tests/fixtures/knowledge/` 三份原始演示文档、`db/init/005_demo_orders.sql` 与 `app/biz/refunds.py`，核对 `evals/cases/smartservice.jsonl` 的 30 条种子标签。再对照此前保存的 `evals/reports/rag-observations.jsonl`、`agent-observations.jsonl` 判断实际回答。此记录是项目内部复核，不是独立标注员或真实用户反馈。

“事实与引用通过”要求回答的核心事实得到其所标编号对应的 `sources` 片段支持；“正确拒答”要求无来源且返回约定文案。HTTP 502 只标记“不可判定”，不能算回答错误或正确。来源按文件及 `chunk_index` 指定，比旧评分器的文件名匹配更精确。

## RAG：20 条

| ID | 人工预期事实 / 证据 | 已保存回答的人工判定 |
| --- | --- | --- |
| rag-refund-01 | 签收后 7 个自然日内；`refund_policy.md#0` | 502，不可判定 |
| rag-refund-02 | 从签收起算，不从下单起算；`refund_policy.md#0` | 事实与引用通过 |
| rag-refund-03 | 第 8 天超出时限；`refund_policy.md#0` | 事实与引用通过 |
| rag-refund-04 | 已明显使用且影响二次销售时不支持退款；`refund_policy.md#1` | 事实与引用通过；回答保留了政策条件 |
| rag-refund-05 | 虚拟商品一经发放不支持退款；`refund_policy.md#1` | 502，不可判定 |
| rag-refund-06 | 客服表态不等于资金到账；模拟申请须用户明确确认；`refund_policy.md#2` | 502，不可判定 |
| rag-refund-07 | 创建模拟退款申请前须用户明确确认；`refund_policy.md#2` | 事实与引用通过 |
| rag-refund-08 | 签收后 7 个自然日内提交模拟退款申请；`refund_policy.md#0` | 502，不可判定；原题“退货”与“退款申请”不等价，已修正题目，尚未重测 |
| rag-shipping-01 | 普通订单预计付款后 48 小时内发货；`shipping_policy.md#0` | 502，不可判定 |
| rag-shipping-02 | 节假日或极端天气可能延迟发货；`shipping_policy.md#0` | 502，不可判定 |
| rag-shipping-03 | 待发货时可以申请修改收货地址；`shipping_policy.md#1` | 事实与引用通过 |
| rag-shipping-04 | 已发货须联系承运方确认能否改址，不能保证直接改；`shipping_policy.md#1` | 事实与引用通过 |
| rag-shipping-05 | 物流连续 72 小时未更新可提交异常工单；`shipping_policy.md#2` | 502，不可判定 |
| rag-faq-01 | 演示系统支持订单查询、退款资格检查、知识库问答；`product_faq.txt#0` | 502，不可判定 |
| rag-faq-02 | 支持已上传的 Markdown、TXT 文档；`product_faq.txt#0` | 事实与引用通过 |
| rag-faq-03 | 演示订单、退款都是模拟数据；`product_faq.txt#0` | 事实与引用通过 |
| rag-unknown-01 | 文档无火星天气信息，应拒答且无来源 | 正确拒答 |
| rag-unknown-02 | 文档无 CEO 信息，应拒答且无来源 | 正确拒答 |
| rag-acl-01 | 其他用户无权限读取三份私有文档，应无来源拒答 | 正确拒答 |
| rag-acl-02 | 跨租户不可读取私有文档，应无来源拒答 | 正确拒答 |

已有观测：12/20 返回 200；其中 8 条可回答样本的核心事实与引用符合原文，4 条无证据/ACL 样本正确拒答；8 条上游失败不可判定。该结果仅对本轮演示样本和已保存响应成立。`rag-refund-08` 修改后，旧响应不再对应新题目。

## Agent：10 条

| ID | 人工预期业务结果 | 已保存回答的人工判定 |
| --- | --- | --- |
| agent-order-01 | `demo-refundable` 为 `completed`，来自订单工具 | 502，不可判定 |
| agent-order-02 | `demo-expired` 为 `completed`，不得编造订单明细 | 502，不可判定 |
| agent-order-03 | `demo-shipped` 为 `shipped` | 502，不可判定 |
| agent-refund-01 | `demo-refundable` 已签收 2 天，可检查为符合资格；不创建申请 | 502，不可判定 |
| agent-refund-02 | `demo-expired` 已签收 10 天，不符合 7 天窗口 | 502，不可判定 |
| agent-refund-03 | `demo-shipped` 未签收，不符合退款资格 | 502，不可判定 |
| agent-prepare-01 | 可准备待确认动作；用户还须显式确认，不得宣称已退款 | 工具与待确认动作正确；旧回答误导为“回复确认即可完成”，文案未通过 |
| agent-prepare-02 | 已过期，不应产生待确认动作 | 502，不可判定 |
| agent-prepare-03 | 未签收，不应产生待确认动作 | 502，不可判定 |
| agent-multi-01 | 同一订单号依次查询订单与退款资格 | 502，不可判定 |

Agent 预期中的“签收 2/10 天”来自演示 SQL 相对时间，并非固定日历日期；若演示数据被修改或重新播种，应复核数据库实际值。`agent-prepare-01` 的旧回答由此前模型调用产生，服务端后来已改为固定确认说明；本轮没有重新调用上游验证新版本的真实回答。

## 复核后的行动

1. 以修正后的 30 条样本作为下一轮固定基线；运行时保存新观测和报告。旧报告与新报告样本内容指纹不同，不应直接比较其质量分数。
2. 对有来源但答错的样本，先核对引用片段，再调整回答约束；对来源缺失的样本，核对 ACL、分块、相似度和阈值。
3. 先保证可用样本覆盖足够，再做前后对比。即使结构检查全过，仍需对核心事实和引用做人工复核。
