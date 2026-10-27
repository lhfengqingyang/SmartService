# 质量评测门禁实测（2026-10-27）

## 目标和方法

对应 `ENTERPRISE_AGENT_PLAN.md` 的优先级 1。以固定的 20 条 RAG、10 条 Agent 案例调用真实服务，分别记录 HTTP 可用性、检索片段和引用、工具轨迹、参数及待确认动作。人工逐条核对答案事实与业务工具结果；模型返回成功不等于事实正确。

评测器现在为案例集和演示数据库分别计算指纹，要求同一次运行的观测来自相同数据快照。比较器拒绝数据快照不同的报告。门禁要求人工审阅记录与两个指纹匹配；任一关键检查、人工事实或安全审阅失败时阻断。`tool_selection` 的 90% 阈值衡量多余工具调用，`required_tools_present` 则检查必要工具不能漏掉。真实 API 失败单独计入可用性。

## 实际实验

1. 首次 30 条真实运行：30/30 返回成功；RAG 来源、片段、引用 16/16，无证据拒答 4/4；Agent 精确工具选择 8/10。人工发现一条订单回答编造商品名，进一步确认数据库中三条演示商品名已因旧的 SQL 写入编码错误成为问号。
2. 尝试修改 Agent 指令，重新运行 10 条 Agent 案例。工具选择仍为 8/10，而且跨知识库与订单的案例漏调退款资格工具。比较器判定回退，因此撤销该指令修改。**没有把这次尝试计为优化成功。**
3. 仅修复三条演示商品名，保留其他业务与知识数据，运行新的完整基线。由于数据快照变化，不能把新旧 8/10 与 9/10 归因于指令优化；模型输出也有随机性。

新基线文件（本地忽略目录）：`evals/reports/qwen37-clean-observations.jsonl`、`qwen37-clean-report.json`、`qwen37-clean-manual-review.json`、`qwen37-clean-gate.json`。数据指纹：`d6b56652bc22a434571844ffecec5137f91767f00692caccc1bdae3816e56633`。

| 指标 | 结果 |
| --- | --- |
| HTTP 可用性 | 30/30 |
| RAG 来源召回、片段召回、有效引用 | 各 16/16 |
| 无证据拒答 | 4/4 |
| Agent 必要工具、参数、待确认动作、无意外准备调用、无重复只读 | 各 10/10 |
| Agent 精确工具选择 | 9/10；一条退款资格问题多调用了一次只读订单查询 |
| 人工事实核对 | 29/30；`rag-refund-06` 未通过 |
| 门禁决策 | **block**，原因是 `rag-refund-06` 的资格断言缺少证据 |

`rag-refund-06` 问“客服说我可以退，是否就已经到账？”。回答正确否认已到账，但又说客服表态“仅代表已符合退款资格”。知识片段只能支持客服 Agent 可以检查资格、模拟申请需要用户明确确认、模拟申请不等于真实资金退回；不能从客服的一句话确定具体订单资格。引用格式检查 16/16 因而不能代替人工事实检查。曾怀疑演示知识库中文乱码；检查 JSON 字符串的实际内容后确认退款知识片段包含正常中文“退款”，此前看到的乱码是终端输出编码问题。

## 复现

```powershell
& .\.venv\Scripts\python.exe -m app.evals.runner --live --kind all --observations-out evals/reports/qwen37-clean-observations.jsonl --report evals/reports/qwen37-clean-report.json
& .\.venv\Scripts\python.exe -m app.evals.gate --report evals/reports/qwen37-clean-report.json --review evals/reports/qwen37-clean-manual-review.json --out evals/reports/qwen37-clean-gate.json
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check app/evals tests/test_eval_gate.py tests/test_eval_compare.py tests/test_evals.py
```

门禁命令失败时退出码为 1。重新运行真实模型后，旧人工审核文件不能直接复用；必须审核新输出并记录当前案例与数据指纹。此次测试为 89 passed、4 skipped；Ruff 检查通过。下一步是修复退款资格回答中的过度推断，重新运行真实评测并人工复核；只有门禁通过才能将该候选版本标记为质量验收通过。

## 同日后续：退款事实修复与 Agent 波动

在 RAG 系统指令中明确要求：不能把用户转述的客服意见推断为具体订单已符合资格、已提交申请或已到账。首版修改后，30 条真实复测 30/30 可用，但人工复核 `rag-refund-06` 仍有“仅代表已符合资格或已提交申请”的过度推断；同时 Agent 出现一条漏调资格工具和两条重复只读调用，因此整批结果继续阻断。第一次复测受执行环境网络权限阻断，20 条 Embedding 和 10 条 Agent 全部失败；在允许访问已配置的外部 API 后才获得上述真实服务结果，不能把网络阻断归因于模型质量。

随后补充更具体的反例指令，再跑 `rag-refund-06` 单例和完整 20 条 RAG。最终 RAG 结果 20/20 可用；16 条有证据案例的来源、片段、引用均 16/16，4 条无证据案例拒答 4/4。人工逐条复核为 20/20，`rag-refund-06` 现在明确区分客服转述与实际资格、申请和到账。同一演示数据快照的前后 RAG 报告比较为 `no_automated_change`，即自动结构指标保持全通过，事实改善由人工审核确认。`evals/reports/qwen37-rag-final-gate.json` 为 **pass**，只代表 RAG 子集，不能当作全部 Agent 的验收结果。

针对跨知识与订单任务，增加三种故障注入测试：缺失资格工具、资格工具失败、订单工具结果与请求订单不一致。三种情况下服务端均不保存待确认退款动作，返回人工处理说明。此检查验证安全失败路径，尚未解决真实模型有时漏调或重复调用工具的问题。最终单测 92 passed、4 skipped，Ruff 检查通过。下一项应稳定 Agent 的必要工具执行并重跑完整 30 条评测及人工复核。
