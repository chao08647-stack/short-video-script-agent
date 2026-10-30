# 实际验证与限制

本文件区分工程测试、离线 Mock、真实模型运行和对成稿的事后审阅。原始 Trace 不改写，自动通过也不能替代事实质量复核。

**当前结论：DeepSeek Flash 已接入；修补后工程测试 282/282、Mock 场景 14/14 通过。修补前真实批次自动通过 8/14，另 6 项因 HTTP 402 余额不足未完成；事后审阅发现其中 4 份完成稿仍有无依据的界面细节，已修补检查但尚无额度复验。本项目仍不能声明完整达标。**

## 环境与复现

Windows、Python 3.12.9、LangGraph 1.2.18、langgraph-checkpoint-sqlite 3.1.2。依赖见 [requirements-lock.txt](../requirements-lock.txt)。按 README 安装并配置本地 `.env` 后运行：

```console
python -m pytest --junitxml=examples/test-results.xml
python -m script_agent.evaluate --mode mock --simulate-human --output examples/mock
python -m script_agent.evaluate --mode live --simulate-human --output examples/deepseek-flash-recheck
```

最后一条会真实调用计费接口，需要有效额度。使用新的目录保留本次修补前证据。CLI 正常运行会等待真人审核；评估器的批准、澄清和修改意见均明确标记 `evaluation_simulated_human`，不是用户真实签字。

本次主模型配置为 `https://api.deepseek.com`、`deepseek-flash`、native 工具协议、thinking disabled、temperature 0、输出上限 4096、超时 120 秒、应用预算 16384。16k 是每次请求的本地预算，不是服务原生容量，也不是整个任务的累计额度。请求前用固定官方 Flash 1017 tokenizer 与模板计数，并计入工具定义、余量和输出预留；响应后核对实际 usage。估算不能保证服务端模板完全一致。依据及固定版本见 [来源清单](../src/script_agent/vendor/deepseek/provenance.json)。

## 最终工程验证

`pytest`：**282 passed in 23.66s**，见 [JUnit](../examples/test-results.xml)。覆盖 LangGraph 状态、检查绑定、跨进程人审恢复、失败保留、预算和协议、引用检查、原子编辑及定向事实漏检回归。修补后的 [Mock 汇总](../examples/mock/summary.json) 为 14/14；Mock 不能证明真实模型决策质量。

源码打包与离线审核恢复检查见 [package-check.json](../examples/package-check.json)。它使用已安装依赖，不冒充全新机器安装或真实模型复验。

评估器要求当前版本的有效检查与三阶段批准，超时修订须包含实际失败→模型修改→同一上限下复检通过；缺信息必须发生问答，工具失败必须有真实错误和后续动作。工具批量调用会全部拒绝，必须重新选择单个工具。模型及工具计数包含尝试与被拒绝动作，不能直接当作计费请求数。

## DeepSeek 原始批次与审阅

- [原始自动汇总](../examples/deepseek-flash/summary.json)：8/14，包括 5 个 completed 和 3 个合理等待确认；其余 6 个 HTTP 402。
- [AI 辅助文件复核](../examples/deepseek-flash/manual_audit.json)：具体原句、JSON 位置、来源及原始文件哈希。不是新增模型调用，也不是真人质量签字。
- [修补后离线重检](../examples/grounding-regression.json)：新确定性规则能够阻断已发现的四份历史稿；未重新生成稿件或调用语义模型。
- [实际技能记录](../examples/deepseek-flash/skill_coverage.json)：本批次 12/16 加载、12/16 模型声明关联，不能声称 16 项效果全部验证。

| 场景 | 原始状态／自动结果 | 当前判断 | 证据 |
|---|---|---|---|
| 正常生成 | completed／通过，25.35 秒 | 无依据进度条、滑块；复合引用需拆分，待复验 | [输入](../examples/deepseek-flash/normal/input.json) · [输出](../examples/deepseek-flash/normal/output.json) · [Trace](../examples/deepseek-flash/normal/trace.jsonl) |
| 缺关键信息 | completed／通过，26.65 秒 | 发生真实补问；无依据导出及 UI，待复验 | [输入](../examples/deepseek-flash/missing_info/input.json) · [输出](../examples/deepseek-flash/missing_info/output.json) · [Trace](../examples/deepseek-flash/missing_info/trace.jsonl) |
| 无素材 | waiting_human／通过 | 多次换查询仍无资料后追问 | [输入](../examples/deepseek-flash/no_materials/input.json) · [输出](../examples/deepseek-flash/no_materials/output.json) · [Trace](../examples/deepseek-flash/no_materials/trace.jsonl) |
| 工具失败 | completed／通过，29.5 秒 | 恢复和压缩真实发生；无依据 UI，待复验 | [输入](../examples/deepseek-flash/tool_failure/input.json) · [输出](../examples/deepseek-flash/tool_failure/output.json) · [Trace](../examples/deepseek-flash/tool_failure/trace.jsonl) |
| 超时长修正 | completed／通过，22.75 秒 | 超时修正真实发生；最终时间轴、面板缺依据，待复验 | [输入](../examples/deepseek-flash/duration_revision/input.json) · [输出](../examples/deepseek-flash/duration_revision/output.json) · [Trace](../examples/deepseek-flash/duration_revision/trace.jsonl) |
| 不可能时长 | waiting_human／通过 | 最短稿仍超 1 秒，未擅改上限 | [输入](../examples/deepseek-flash/too_short/input.json) · [输出](../examples/deepseek-flash/too_short/output.json) · [Trace](../examples/deepseek-flash/too_short/trace.jsonl) |
| 资料冲突 | waiting_human／通过 | 补查后追问，未擅选续航值 | [输入](../examples/deepseek-flash/conflict/input.json) · [输出](../examples/deepseek-flash/conflict/output.json) · [Trace](../examples/deepseek-flash/conflict/trace.jsonl) |
| 品牌／事实修正 | completed／通过，16.6 秒 | 删除禁语及无据数字；本次定向重检未新增问题，非全面保证 | [输入](../examples/deepseek-flash/brand_and_fact_revision/input.json) · [输出](../examples/deepseek-flash/brand_and_fact_revision/output.json) · [Trace](../examples/deepseek-flash/brand_and_fact_revision/trace.jsonl) |
| 人工返修 | failed／未通过 | 初稿阶段第 30 次模型尝试遇 402，尚未执行有效人工返修 | [输入](../examples/deepseek-flash/human_feedback/input.json) · [输出](../examples/deepseek-flash/human_feedback/output.json) · [Trace](../examples/deepseek-flash/human_feedback/trace.jsonl) |
| 耳机产品 | failed／未通过 | 首次请求 402，不能归因为模型业务能力 | [输入](../examples/deepseek-flash/headphones/input.json) · [输出](../examples/deepseek-flash/headphones/output.json) · [Trace](../examples/deepseek-flash/headphones/trace.jsonl) |
| 教程形式 | failed／未通过 | 首次请求 402 | [输入](../examples/deepseek-flash/tutorial/input.json) · [输出](../examples/deepseek-flash/tutorial/output.json) · [Trace](../examples/deepseek-flash/tutorial/trace.jsonl) |
| 查询改写后完成 | failed／未通过 | 首次请求 402；无素材用例的改写不替代本例 | [输入](../examples/deepseek-flash/query_rewrite/input.json) · [输出](../examples/deepseek-flash/query_rewrite/output.json) · [Trace](../examples/deepseek-flash/query_rewrite/trace.jsonl) |
| 步数上限 | failed／未通过 | 首次请求 402；Flash 未验证正常触顶路径 | [输入](../examples/deepseek-flash/step_limit/input.json) · [输出](../examples/deepseek-flash/step_limit/output.json) · [Trace](../examples/deepseek-flash/step_limit/trace.jsonl) |
| 单功能简短请求 | failed／未通过 | 首次请求 402 | [输入](../examples/deepseek-flash/minimal/input.json) · [输出](../examples/deepseek-flash/minimal/output.json) · [Trace](../examples/deepseek-flash/minimal/trace.jsonl) |

本次两批进程使用相同的八份执行源码指纹（导入时捕获）。随后修改了事实检查、提示和错误证据；因此原批次不能当作最终修补代码的真实验收。原始 `completed`、`acceptance_passed` 均保留，以展示自动检查漏检，审阅文件单独撤回完整内容合格结论。

170 条成功响应的 usage 合计 989,939 tokens，含重复提示和可能命中的缓存；单请求最高 9,837 tokens，均低于 16,384。这不是金额账单，也不是任务总额度上限。402 后停止了进一步付费复验，等待用户补充额度。

## 工具结果如何改变动作

1. **故障恢复后自主压缩**：[tool_failure Trace](../examples/deepseek-flash/tool_failure/trace.jsonl) seq 9 注入检索错误，seq 11 模型改查询成功；seq 46 对模型生成的 v1 估时 30.55 秒，seq 52 修改旁白，seq 56 为 29.5 秒。该链路无须预设下一动作，但最终画面仍须事实复验。
2. **用户初稿超时**：[duration_revision Trace](../examples/deepseek-flash/duration_revision/trace.jsonl) seq 25 为 54.35 秒，模型重写后 seq 42 为 22.75 秒，最终 v3 的 seq 54 再次确认。初稿是合成测试输入，不能冒充模型首稿；P01/P02 的两项必讲事实保留。
3. **没有资料**：[no_materials Trace](../examples/deepseek-flash/no_materials/trace.jsonl) seq 9、15、18 是不同查询，均零结果，seq 22 请求补资料。
4. **来源冲突**：[conflict Trace](../examples/deepseek-flash/conflict/trace.jsonl) seq 9 发现 C01/C02 冲突，seq 15 补查测试条件与版本，seq 19 请求确认，没有按日期擅选 8 或 12 小时。
5. **硬时长不可满足**：[too_short Trace](../examples/deepseek-flash/too_short/trace.jsonl) 先后 21.15、3.85、2.35 秒仍超 1 秒，seq 68 请求用户确认是否调整时长，未自行改要求。

## 本次漏检、修补与边界

原检查认可了来源 ID 和主要功能，但遗漏未声明的 UI／操作，且同模型语义核验曾借其他 claim 补足单条证据。修补包括：

- 配置 `evidence_required_terms`，已列功能/UI词在标题、画面、旁白、字幕中出现时，须由该字段实际 claim 及其同一原文支持。“示意”一词不能豁免；无具体 UI 的抽象画面仍允许。
- 要求模型逐字段核查未登记断言；每条 claim 独立由自身 `source_id` 与 `quote` 支持，复合事实拆分引用。
- 修正完成语义核验后仍显示 `not_checked` 的元数据，补齐语义核验超预算等异常的 usage 和错误证据。

定向词表可能误报通用拍摄场景，也可能漏过换词表达；提示改动尚无修补后真实模型证据。不能称为解决了通用事实核验。回归测试固定保存实际失败片段，避免重新运行正确稿件后测试失效。

## 历史 Qwen 对照

[历史汇总](../examples/live/summary.json) 为 3/14 达到预期，其余存在无效重复、提前停止或修订失败；无正常完整成稿。它来自多轮迭代，不能与本次 Flash 数字作同版本准确率比较。[实验记录](../examples/experiments/README.md) 保留上下文及协议问题。Flash 使用 native，Qwen 后期使用显式 JSON Schema 协议；均无自动 Mock 回退。

早期 Qwen 源码指纹可能采集任务启动时磁盘内容而非进程已加载版本；带 `code_hash_capture=process_import` 的记录才使用修正约定。真实 Trace 中 16 项加载曾发生在失败循环，不能当作技能效果。当前仍有 16 个可加载技能包，未完成 16 项有效运用证明。

## 已知限制与剩余工作

同模型独立提示核验会漏判；词法检索和显式冲突组不是通用知识核验；时长是固定语速估算而非录音测量。本项目只输出文字脚本，不合成视频。运行中崩溃的任意节点自动续跑、分布式并发及多文件原子导出不在范围。

此前实施约 2 小时墙钟时间（10 月 30 日 21:02–23:00）；DeepSeek 本阶段从 10 月 30 日 23:53 开始跨天继续，结束时间见 progress.md。包括 AI 并行编码、等待和验证，不能算作候选人纯手工投入。

待完成：额度恢复后对修补版重新跑真实验收，特别是四份存在内容漏检的稿件及六个中断场景；补充技能有效应用证据；候选人本人复核和解释；提供 GitHub 远端并填写最终 URL、commit SHA。当前仅有本地交付，不虚构远端。
