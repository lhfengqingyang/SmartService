# 离线评测：固定样本与评分器

本阶段只建立固定样本和可运行的离线评分器；不把已有 pytest 单元测试或单次演示等同于 RAG/Agent 效果分数。

## 样本

`evals/cases/smartservice.jsonl` 包含 30 条基于项目 fixture 和演示订单编写的种子标注：20 条 RAG、10 条 Agent。问题覆盖退款、配送、产品 FAQ、无答案、跨用户/租户 ACL、订单查询、退款资格、退款准备和多工具请求。

2026-10-26 项目内部逐条复核见 [EVALUATION_MANUAL_REVIEW.md](EVALUATION_MANUAL_REVIEW.md)。16 条可回答 RAG 样本补充了文件名和 `chunk_index` 的片段标签；一条把“退货”混同“模拟退款申请”的含混题目已修正。该复核不是独立标注员评审。

这些标签是根据仓库里的模拟政策和订单数据人工整理的种子集，不代表真实用户流量，也未经过独立标注员复核。答案事实要求在 `review_notes`，目前仍需人工判断。

RAG 样本要求演示库中有三份 fixture，均属于 `demo` 租户、`demo-user` 用户，且设为私有并允许 `support` 角色。运行前可用 README 的 SQL 查看当前文档；缺少任一文件时 live 运行会明确报错。不要重复上传同名文档，否则重复 chunk 会影响排序和解释。

## 运行

```powershell
& ".\.venv\Scripts\python.exe" -m app.evals.runner --live --kind rag `
  --observations-out evals/reports/rag-observations.jsonl `
  --report evals/reports/rag-report.json
```

`--kind agent` 只运行 Agent 样本，`--kind all` 运行全部。它们会真实调用 Embedding/GLM，因此可能受外部 429 限流影响。Agent 样本只调用查询和准备工具，不发送退款确认请求，不创建退款申请。

再次评分时使用 `--observations` 指向保存的 JSONL，不再调用模型。`--cases` 可指定新的样本文件。JSON 报告的 `cases` 列出逐例结果，`metrics` 包含分子、分母和通过率。

## 指标解释

- `source_recall_at_k`：有答案用例中，预期文件是否出现在 API 返回的来源中。当前按文件名匹配，不宣称是 chunk 级召回率。
- `chunk_recall_at_k`：人工标了 `expected_chunks` 的用例中，预期文件的预期 `chunk_index` 是否出现在返回来源中；它仍不判断回答是否正确使用片段。
- `valid_citation`：回答是否包含落在来源编号范围内的引用。它不验证引用事实是否正确。
- `no_evidence`：无答案用例是否返回空来源和项目约定的固定拒答文案。
- `tool_selection`：调用工具名称的多重集合与预期完全一致。
- `tool_arguments`：每次工具调用是否都使用预期的订单号。
- `pending_action` / `pending_order_id`：待确认动作是否按预期出现，且绑定正确订单。

非 200 响应进入 `errors`，缺少观测进入 `missing`；它们不会进入质量指标分母。报告必须同时看 `observed`、`available` 和 `errors`，不能只看通过率。模型给出自然语言事实的忠实度、引用是否支持该事实、是否夸大模拟退款，需要根据 `review_notes` 人工复核，之后再考虑引入 Judge。

观测文件包含模型答案和知识片段，可能涉及业务内容，`evals/reports/` 已被 Git 忽略。不要将真实用户输入直接加入仓库中的种子集。

## 运行指标

`POST /api/v1/chat` 每次处理结束会向服务标准输出写一行 `rag_request` JSON，字段包括 UTC 时间、HTTP 状态、耗时（毫秒）、返回片段数、Top-1 相似度、前两名分差、无证据标记和应用错误码。记录检索分布时不写问题、答案、文档内容、文件名、用户或租户标识。

成功回答还会返回 `request_id`，可据此调用反馈接口。`ai.rag_requests` 保存成功请求的实验分组和检索摘要，`ai.rag_feedback` 保存用户明确提交的评价；原始问题只在反馈请求包含 `question` 时保存。查看演示实验分组及反馈：

```sql
SELECT r.variant, count(*) AS answers,
       count(f.request_id) AS feedback_count,
       count(*) FILTER (WHERE f.rating = 'helpful') AS helpful_count,
       count(*) FILTER (WHERE r.retrieved_count = 0) AS no_evidence_count
FROM ai.rag_requests r
LEFT JOIN ai.rag_feedback f ON f.request_id = r.id
WHERE r.experiment = 'threshold_v1'
GROUP BY r.variant;
```

这是成功回答的描述性统计；未收到反馈的回答不可当作差评，且失败请求不进入该表。用户级分组和演示数据不能直接证明实验因果效果，正式评估需要补齐曝光/失败日志、样本量与分流检查，并结合人工标注。

## 无用反馈的人工标注闭环

只有用户在反馈里主动提交 `question` 的“无用”记录可入队。先运行可重复的离线扫描，再导出待审核队列；定时调度器也可以定期调用同一个 `sync` 命令。候选文件和人工评测集均放在被 Git 忽略的 `evals/private_cases/`；不要将真实用户问题复制进公开种子集。

```powershell
& ".\.venv\Scripts\python.exe" -m app.evals.feedback_review sync

& ".\.venv\Scripts\python.exe" -m app.evals.feedback_review export `
  --out evals/private_cases/pending_review.jsonl
```

人工逐条检查问题是否适合保存和复现，核对知识库证据，并在 JSONL 行中填写：`approved=true`、`answerable`、`expected_filenames`、`review_notes` 和 `failure_type`。明确不应入集的行可设 `rejected=true`；两者均为 false 的行继续待审。`failure_type` 可选 `retrieval_missing`、`retrieval_irrelevant`、`answer_unsupported`、`incorrect_refusal`、`other`；必要时修正 `request.roles` 以复现原场景。未批准的行不会进入评测集，标签不完整的批准行会报错。

```powershell
& ".\.venv\Scripts\python.exe" -m app.evals.feedback_review promote `
  --reviewed evals/private_cases/pending_review.jsonl `
  --out evals/private_cases/reviewed_cases.jsonl

& ".\.venv\Scripts\python.exe" -m app.evals.runner --live --kind rag `
  --cases evals/private_cases/reviewed_cases.jsonl `
  --observations-out evals/reports/feedback-observations.jsonl `
  --report evals/reports/feedback-report.json
```

`promote` 按 ID 合并已批准样本，重复运行不会产生重复行，并把批准或驳回写回队列。固定评测集只提供回归标准，不会训练或更新 GLM 权重。提升后续回答要根据失败类型实施具体修复：漏召回时调整分块、知识内容或检索策略；无关召回时调整阈值与排序；证据已命中但回答不可靠时改提示词、引用检查或拒答逻辑。每次改动前后对同一批样本测可用率、结构指标，并人工复核事实正确性，确认改善后再发布。仅有“无用”反馈属于负样本，不能单独估算整体满意率。

## 改动前后对比

用同一份固定样本，分别在改动前和改动后运行评测并保存两份报告，再执行：

```powershell
& ".\.venv\Scripts\python.exe" -m app.evals.compare `
  --before evals/reports/before.json `
  --after evals/reports/after.json `
  --out evals/reports/comparison.json
```

对比器要求两份报告的 case ID 完全一致；新报告还包含样本内容指纹，指纹不一致时拒绝比较。旧报告没有指纹时仍可对比，但 `case_content_verified=false`，需人工确认样本文件确实相同。它分别显示成功请求数变化、错误与成功之间的转换，以及两次都成功的同一条样本上各项结构检查的得失。新失败会标为回退；仅在有成对成功样本且无自动检查回退时，才可能给出 `improved_candidate`。这个状态只是待人工复核的候选改善，不代表答案事实正确，也不构成上线决策。没有成对成功样本会标为 `insufficient_paired_cases`。

例如在 PowerShell 启动服务时，可用 `Tee-Object` 同时查看和保存运行日志；日志应按部署环境设置访问权限与保留期。当前仅有逐请求事件，没有聚合看板、长期存储或跨实例汇总。若 LLM 在检索后失败，该请求计入错误，当前事件的 `retrieved_count` 为 0，不能据此判断检索是否真的无结果；`no_evidence` 仅统计成功返回且来源为空的请求。

## 线上流程如何拆分

1. 在线 API 接收反馈，先持久化评价与用户明确同意回流的问题；不要让用户请求等待人工标注。
2. 后台周期任务扫描未入队的负反馈，按 `request_id` 幂等入队。本项目的 `sync` 是这个最小实现；它扫描数据库，不监听字段变化，也不需要 Redis/Kafka。
3. 运营或质检平台按权限读取待标注任务，人工核对问题、证据、期望答案与失败类型；可批准、驳回或保持待审。复杂场景可增加双人标注、冲突仲裁和抽样质检。
4. 批准样本形成版本化固定评测集。研发定位是文档、检索还是生成问题，修复后用相同样本做前后对比及人工事实核对，再决定上线。线上指标和后续反馈继续监测。

高流量或跨服务场景可以用事务 outbox 或 CDC 把“反馈已写入”事件可靠地送往队列，由独立消费者创建标注任务；消费者仍需按请求 ID 去重。事务 outbox 用于避免数据库写成功但消息发布失败的双写问题；它不是本项目 MVP 的必要依赖。参考 [AWS Transactional Outbox Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) 与 [SageMaker human-in-the-loop labeling](https://docs.aws.amazon.com/sagemaker/latest/dg/data-label.html)。上线还需真实鉴权、运营权限、个人信息脱敏、保留与删除策略、审核审计及对“有用”样本的抽样，避免只看负样本。
