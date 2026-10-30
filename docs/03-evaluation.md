# 实际验证与限制

本文件区分自动化工程测试、离线 Mock 流程和真实模型效果。最终运行结果以对应目录中的 `evaluation.json`、`output.json` 和 `trace.jsonl` 为准，不能只看截图或模型自述。

**结论：工程测试 220/220 通过，离线场景 14/14 通过；当前真实模型仍未完成正常脚本及有效修订的完整验收，不能把本版本作为已经达标的答卷。** 真实记录中没有把失败稿标为完成。下一步应先用另一指令模型对照复验，再决定是否需要进一步改动设计。

## 环境与复现

开发环境为 Windows、Python 3.12.9、LangGraph 1.2.18、langgraph-checkpoint-sqlite 3.1.2。精确依赖见 [requirements-lock.txt](../requirements-lock.txt)。在仓库根目录安装后运行：

```console
python -m pytest --junitxml=examples/test-results.xml
python -m script_agent.evaluate --mode mock --simulate-human
python -m script_agent.evaluate --mode live --simulate-human
```

真实模型为用户提供的 `qwen25-14b-pbn-answer`，地址 `http://127.0.0.1:8012/v1`；这不是随仓库分发的服务。用户重启后接口报告 32768-token 上下文。测试中使用温度 0、输出上限 2048 tokens，JSON 协议运行设置超时 120 秒。每份新输出的 `execution` 记录实际参数和关键源文件指纹，默认配置可能与某次实验配置不同。

`native` 使用服务端原生工具解析；显式 `LLM_ACTION_PROTOCOL=json` 使用 JSON Schema 约束动作格式，要求服务支持 `anyOf` 和 `const`。两者均由真实模型选择动作，程序执行工具并回传观察。语法约束不证明业务选择正确。失败不会自动改为 Mock 或自动换协议。

## 工程测试与证据判据

最终执行 `pytest` 得到 **220 passed in 29.05s**，JUnit 结果见 [examples/test-results.xml](../examples/test-results.xml)。测试覆盖实际规则/估时计算、引用与冲突、模型适配、技能加载、模型及工具预算、跨进程人审恢复、重复审核、旧版本拒绝、失败检查失效、局部编辑原子性和导出。

评估器不会仅凭 `completed` 标记算通过。完成必须有三阶段批准和当前内容/需求/资料对应的有效检查；超时修订须看到超限检查、模型提交不同内容的新版本、同一时长上限下的通过检查；查询改写须看到空结果、不同查询和后续命中；故障恢复须实际观察到注入错误及后续模型选择。任一评估失败返回非零退出码。

所有自动评估中的批准、修改意见和缺字段回复均标记 `evaluation_simulated_human`。这验证 HITL 的程序链路，不代表用户已经认可作品质量。CLI 直接运行会暂停等待真人输入。

对于预期完成的场景，评估器最多另提供一次明确的模拟提醒：“依据已有资料自主修订，保持原要求”。该提醒不提供产品新事实。无资料、资料冲突和不可能时长的场景保留等待确认或未完成，不由评估器编造答案。

## 结果入口

- [Mock 汇总](../examples/mock/summary.json)：只证明流程和工程行为。
- [真实模型汇总](../examples/live/summary.json)：逐例列出实际状态、调用数和验收错误。
- [真实技能记录](../examples/live/skill_coverage.json)：分别列出加载、模型声明和候选关联。
- [开发失败记录](../examples/experiments/README.md)：保留上下文、工具协议与无效循环等问题，供对照改进。

以下是每个场景最后保留的真实运行。它们来自开发迭代中的不同批次，**3 个达到预期、11 个未达到；这不是同一冻结版本的模型准确率基准**。其中正常与工具失败两例最终用独立进程复验，六份执行源码指纹相同，`code_hash_capture=process_import`；其余记录用于保留已经观察到的行为和失败。

| 场景 | 实际状态／验收 | 输入、输出、运行记录 |
|---|---|---|
| 正常生成 | incomplete／未通过：引用映射未修好 | [输入](../examples/live/normal/input.json) · [输出](../examples/live/normal/output.json) · [Trace](../examples/live/normal/trace.jsonl) |
| 缺关键信息 | incomplete／未通过：已澄清，后续修订失败 | [输入](../examples/live/missing_info/input.json) · [输出](../examples/live/missing_info/output.json) · [Trace](../examples/live/missing_info/trace.jsonl) |
| 无资料 | waiting_human／通过：请求补充 | [输入](../examples/live/no_materials/input.json) · [输出](../examples/live/no_materials/output.json) · [Trace](../examples/live/no_materials/trace.jsonl) |
| 工具失败 | incomplete／未通过：检索恢复，但脚本仍超时 | [输入](../examples/live/tool_failure/input.json) · [输出](../examples/live/tool_failure/output.json) · [Trace](../examples/live/tool_failure/trace.jsonl) |
| 超时初稿修订 | incomplete／未通过：没有形成同目标下的通过稿 | [输入](../examples/live/duration_revision/input.json) · [输出](../examples/live/duration_revision/output.json) · [Trace](../examples/live/duration_revision/trace.jsonl) |
| 1 秒硬约束 | incomplete／未通过：耗尽次数，没有及时作出有效停止决策 | [输入](../examples/live/too_short/input.json) · [输出](../examples/live/too_short/output.json) · [Trace](../examples/live/too_short/trace.jsonl) |
| 资料冲突 | waiting_human／通过：补查后请求确认 | [输入](../examples/live/conflict/input.json) · [输出](../examples/live/conflict/output.json) · [Trace](../examples/live/conflict/trace.jsonl) |
| 品牌与虚假事实修订 | waiting_human／未通过：重复澄清，未形成修订链 | [输入](../examples/live/brand_and_fact_revision/input.json) · [输出](../examples/live/brand_and_fact_revision/output.json) · [Trace](../examples/live/brand_and_fact_revision/trace.jsonl) |
| 人工反馈修改 | incomplete／未通过：未进入有效初稿反馈链 | [输入](../examples/live/human_feedback/input.json) · [输出](../examples/live/human_feedback/output.json) · [Trace](../examples/live/human_feedback/trace.jsonl) |
| 耳机产品 | incomplete／未通过 | [输入](../examples/live/headphones/input.json) · [输出](../examples/live/headphones/output.json) · [Trace](../examples/live/headphones/trace.jsonl) |
| 教程形式 | incomplete／未通过 | [输入](../examples/live/tutorial/input.json) · [输出](../examples/live/tutorial/output.json) · [Trace](../examples/live/tutorial/trace.jsonl) |
| 查询改写 | incomplete／未通过：未观察到空结果后改写命中 | [输入](../examples/live/query_rewrite/input.json) · [输出](../examples/live/query_rewrite/output.json) · [Trace](../examples/live/query_rewrite/trace.jsonl) |
| 执行上限 | incomplete／通过：1 次预算耗尽明确停止 | [输入](../examples/live/step_limit/input.json) · [输出](../examples/live/step_limit/output.json) · [Trace](../examples/live/step_limit/trace.jsonl) |
| 单功能简短请求 | incomplete／未通过 | [输入](../examples/live/minimal/input.json) · [输出](../examples/live/minimal/output.json) · [Trace](../examples/live/minimal/trace.jsonl) |

## 不同观察如何改变真实动作

1. **无资料**：`no_materials/trace.jsonl` 的 seq 6 为实际空检索，seq 10 是模型请求补充，状态保留 `waiting_human`。
2. **有冲突**：`conflict/trace.jsonl` 的 seq 6 同时返回 C01/C02；模型使用包含测试条件、版本、优先级的新查询（seq 20），仍无法消除冲突，seq 25 追问，没有擅选 8 小时或 12 小时。
3. **工具错误**：`tool_failure/trace.jsonl` 的 seq 6 是注入错误；经过明确标记的模拟人工提醒后，模型换查询并在 seq 16 重新检索成功。这证明局部恢复路径发生了，但不证明整个任务成功：初稿 seq 33 为 58.75 秒，最后仍为 68.55 秒，超过 30 秒限制。
4. **检查失败后的修订尝试**：正常用例 seq 20 的估时为 27.45 秒，seq 23 报引用绑定错误。此后模型作了实际局部修改并重检，仍残留悬空来源映射，最终 `model_call_limit`。不能把工具返回 `ok=true` 的编辑动作当作有效修订通过。

这些动作来自模型响应，未预置决策日志；完整参数、返回、版本和简短依据均可在相应 Trace 检查。JSON 协议只约束可选动作及参数格式，没有替模型写修改内容。

## 技能与证据版本

仓库有 16 个实际可加载技能包。当前 live 记录覆盖 **16/16 加载、7/16 模型声明关联**；所有 16 项曾在失败循环中被逐一加载，不能据此证明有效运用。模型声明也不是独立成效评估，本轮没有得到完整合格成稿，因此“16 项效果已验证”这一目标尚未实现。离线技能覆盖单独记录，绝不补算进 live 成效。

早期多用例进程在运行期间同时发生代码修改，旧版 `execution.code_hashes` 读取的是任务启动时磁盘文件，可能与进程已加载代码不同。该问题已修复为进程导入时捕获，并增加回归测试；只有带 `code_hash_capture=process_import` 的记录使用新约定。旧 Trace 保留实际输入、响应、工具结果和状态，但其源码指纹不能当作精确执行版本证明。

## 已知限制

1. 模型可能选择错误动作、提出不必要追问或提前停止。结构化协议只能约束格式，不能保证规划和修订能力。
2. 独立核验使用同一模型的另一轮提示词，仍可能漏判或误判；正确的来源 ID 和原文匹配本身不证明语义支持。
3. 时长来自固定语速、字幕阅读和画面最短展示时间，未做真实配音或成片测量。项目仅交付文字脚本。
4. 本地词法检索依赖产品名、关键词和中文二元词；显式冲突组只覆盖已标记场景，不是通用知识冲突检测。
5. 人审可跨进程恢复，运行中强制终止后的任意节点自动续跑、分布式并发、用户权限及多文件原子导出不在本版范围。
6. 16 个技能包已实现，加载及模型声明不等于技能有效；需要对照实际产物审阅，不以文件数代替效果证据。

## 投入与未完成部分

本轮实施约 **2 小时墙钟时间**（2026-10-30 21:02 起，至约 23:00，Asia/Shanghai），包含依赖安装、并行 AI 编码、等待本地模型、多轮失败分析与验证；不是候选人纯人工工时。此前选题讨论和接口探测另计，不能把多个并行代理时长累加成人工投入。

仍未完成：真实模型的正常成稿、有效超时／事实修订、全套有效技能运用证据，以及 GitHub 远端提交。仓库提供可配置模型接口和重跑命令，下一步应更换或调整指令模型，用冻结代码重新跑整套用例；本轮没有用放宽检查、预设成功日志或 Mock 替代来填补这些缺口。
