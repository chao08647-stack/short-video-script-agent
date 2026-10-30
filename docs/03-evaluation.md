# 实际验证与限制

**接口接入完成；完整真实验收仍有缺口。** 最终工程测试 **321 passed in 25.64s**，离线基础场景 **14/14**。最近完整真实批次为 **13/15 自动通过**，随后六项定向验证为 **3/6**；最新人工返修耗尽60次模型尝试，两项新变体再次遇HTTP 402。不能用早先成功覆盖最新失败，也不能把自动通过等同于全稿事实可靠。

## 环境、配置与复现

Python 3.12.9、LangGraph 1.2.18、langgraph-checkpoint-sqlite 3.1.2；精确依赖见 [requirements-lock.txt](../requirements-lock.txt)。主模型为 `deepseek-flash`，地址 `https://api.deepseek.com`，native工具协议、thinking disabled、temperature 0、输出上限4096、超时120秒、应用预算16384。

16k是**单次请求**预算，不是任务累计token或费用上限。请求前使用固定官方Flash1017 tokenizer和消息模板，完整计入工具定义，取模板和序列化计数较大值并加10%+128余量，再预留4096输出；响应后核对实际usage。这仍是本地估算，不能声称已设置服务端16k硬上限。[资产与许可来源](../src/script_agent/vendor/deepseek/provenance.json)。

```console
python -m pytest --junitxml=examples/test-results.xml
python -m script_agent.evaluate --mode mock --simulate-human --output .runs/reviewer-mock
python -m script_agent.evaluate --mode live --simulate-human --output .runs/reviewer-live
python -m script_agent.evaluate --mode live --simulate-human --cases skill_showcase --output .runs/reviewer-skills
```

真实命令需要有效额度，默认14个基础场景，技能展示是额外场景。新目录保留历史证据。默认每任务40次模型、60次工具尝试；人工返修、耳机、检索改写输入显式为60/80，执行上限用例为1次模型。计数包括失败或拒绝的尝试，不等于计费请求数。

评估中的批准、返修意见与缺字段回复都标记`evaluation_simulated_human`，不是用户真实签字。直接CLI运行会在方向、初稿、终稿三道人审门等待真实用户。工具批量请求全部拒绝；单次patch允许最多20项关联编辑，全部成功才保存一个新版本。

## 工程结果

[JUnit结果](../examples/test-results.xml)：321项通过，覆盖原子修改、模型协议与预算、引用和时长、状态绑定、跨进程人审、重复审核、错误保留及已观察漏检的回归。最终[Mock结果](../examples/mock/summary.json)为14/14，不能证明真实模型决策效果。

[打包检查](../examples/package-check.json)使用已安装依赖，验证解压后的代码完成三道人审及本地tokenizer预算探测；不是全新机器安装或真实模型复验。上游原始资产按字节保留；跨平台文本审阅哈希使用UTF-8/LF规范化。

## 四批真实运行

| 批次 | 原始自动结果 | 事实与限制 |
|---|---:|---|
| [首轮接入](../examples/deepseek-flash/summary.json) | 8/14 | 6项遇402；4份完成稿事后发现具体UI、导出或引用问题，已记录撤回完整内容合格结论 |
| [第一次修补复验](../examples/deepseek-flash-recheck/summary.json) | 10/14 | 四份旧问题稿已有改正证据；人工返修、耳机、改写、过短时长耗尽40次 |
| [完整复验批次](../examples/deepseek-flash-final/summary.json) | 13/15 | 原14场景13项通过；过短时长提前追问但缺要求的测量证据，额外三镜头场景生成了四镜；另发现两处收尾漏挂引用 |
| [最后定向验证](../examples/deepseek-flash-validation/summary.json) | 3/6 | 品牌收尾、实际估时后澄清、严格三镜技能展示通过；人工返修60次耗尽，需求／检索技能变体遇402 |

各批次内执行源码指纹一致，但批次间代码、规则、提示和部分输入发生变化，**不是同一冻结版本的准确率基准**。`final`只是第三批目录名，不代表最终版本全通过。完整索引见 [deepseek-validation-index.json](../examples/deepseek-validation-index.json)。

四批共记录898条成功响应的usage，合计 **5,838,719 tokens**（含重复提示及缓存计数，不能直接当作金额账单）；单请求最高10,844，未超过16,384。用户在首次402后充值，最后两个定向变体又收到402，随后没有继续付费调用。后续应先设置整批请求／token预算，再做小范围对照，避免重复全量运行放大成本。

## 每个场景的最近一次尝试

以下保留最近失败，不能挑选早先成功冒充最近结果。需求、检索、技能展示的最后输入明确指定相关技能，属于定向验证；原输入与结果均留在此前目录。按每例最近尝试汇总为12/15，仍不是同版本通过率。

| 场景 | 最近状态 | 实际证据 |
|---|---|---|
| 品牌与事实修正 | completed／自动通过  | [deepseek-flash-validation](../examples/deepseek-flash-validation/brand_and_fact_revision/evaluation.json) · [输入](../examples/deepseek-flash-validation/brand_and_fact_revision/input.json) · [输出](../examples/deepseek-flash-validation/brand_and_fact_revision/output.json) · [Trace](../examples/deepseek-flash-validation/brand_and_fact_revision/trace.jsonl) |
| 资料冲突 | waiting_human／自动通过  | [deepseek-flash-final](../examples/deepseek-flash-final/conflict/evaluation.json) · [输入](../examples/deepseek-flash-final/conflict/input.json) · [输出](../examples/deepseek-flash-final/conflict/output.json) · [Trace](../examples/deepseek-flash-final/conflict/trace.jsonl) |
| 超时修正 | completed／自动通过  | [deepseek-flash-final](../examples/deepseek-flash-final/duration_revision/evaluation.json) · [输入](../examples/deepseek-flash-final/duration_revision/input.json) · [输出](../examples/deepseek-flash-final/duration_revision/output.json) · [Trace](../examples/deepseek-flash-final/duration_revision/trace.jsonl) |
| 耳机产品 | completed／自动通过  | [deepseek-flash-final](../examples/deepseek-flash-final/headphones/evaluation.json) · [输入](../examples/deepseek-flash-final/headphones/input.json) · [输出](../examples/deepseek-flash-final/headphones/output.json) · [Trace](../examples/deepseek-flash-final/headphones/trace.jsonl) |
| 人工返修 | incomplete／未通过 model_call_limit | [deepseek-flash-validation](../examples/deepseek-flash-validation/human_feedback/evaluation.json) · [输入](../examples/deepseek-flash-validation/human_feedback/input.json) · [输出](../examples/deepseek-flash-validation/human_feedback/output.json) · [Trace](../examples/deepseek-flash-validation/human_feedback/trace.jsonl) |
| 单功能短稿 | completed／自动通过  | [deepseek-flash-final](../examples/deepseek-flash-final/minimal/evaluation.json) · [输入](../examples/deepseek-flash-final/minimal/input.json) · [输出](../examples/deepseek-flash-final/minimal/output.json) · [Trace](../examples/deepseek-flash-final/minimal/trace.jsonl) |
| 缺信息 | failed／未通过 model_unavailable | [deepseek-flash-validation](../examples/deepseek-flash-validation/missing_info/evaluation.json) · [输入](../examples/deepseek-flash-validation/missing_info/input.json) · [输出](../examples/deepseek-flash-validation/missing_info/output.json) · [Trace](../examples/deepseek-flash-validation/missing_info/trace.jsonl) |
| 无素材 | waiting_human／自动通过  | [deepseek-flash-final](../examples/deepseek-flash-final/no_materials/evaluation.json) · [输入](../examples/deepseek-flash-final/no_materials/input.json) · [输出](../examples/deepseek-flash-final/no_materials/output.json) · [Trace](../examples/deepseek-flash-final/no_materials/trace.jsonl) |
| 正常生成 | completed／自动通过  | [deepseek-flash-final](../examples/deepseek-flash-final/normal/evaluation.json) · [输入](../examples/deepseek-flash-final/normal/input.json) · [输出](../examples/deepseek-flash-final/normal/output.json) · [Trace](../examples/deepseek-flash-final/normal/trace.jsonl) |
| 检索改写 | failed／未通过 model_unavailable | [deepseek-flash-validation](../examples/deepseek-flash-validation/query_rewrite/evaluation.json) · [输入](../examples/deepseek-flash-validation/query_rewrite/input.json) · [输出](../examples/deepseek-flash-validation/query_rewrite/output.json) · [Trace](../examples/deepseek-flash-validation/query_rewrite/trace.jsonl) |
| 定向技能展示 | completed／自动通过  | [deepseek-flash-validation](../examples/deepseek-flash-validation/skill_showcase/evaluation.json) · [输入](../examples/deepseek-flash-validation/skill_showcase/input.json) · [输出](../examples/deepseek-flash-validation/skill_showcase/output.json) · [Trace](../examples/deepseek-flash-validation/skill_showcase/trace.jsonl) |
| 执行上限 | incomplete／自动通过 model_call_limit | [deepseek-flash-final](../examples/deepseek-flash-final/step_limit/evaluation.json) · [输入](../examples/deepseek-flash-final/step_limit/input.json) · [输出](../examples/deepseek-flash-final/step_limit/output.json) · [Trace](../examples/deepseek-flash-final/step_limit/trace.jsonl) |
| 不可行时长 | waiting_human／自动通过  | [deepseek-flash-validation](../examples/deepseek-flash-validation/too_short/evaluation.json) · [输入](../examples/deepseek-flash-validation/too_short/input.json) · [输出](../examples/deepseek-flash-validation/too_short/output.json) · [Trace](../examples/deepseek-flash-validation/too_short/trace.jsonl) |
| 工具失败 | completed／自动通过  | [deepseek-flash-final](../examples/deepseek-flash-final/tool_failure/evaluation.json) · [输入](../examples/deepseek-flash-final/tool_failure/input.json) · [输出](../examples/deepseek-flash-final/tool_failure/output.json) · [Trace](../examples/deepseek-flash-final/tool_failure/trace.jsonl) |
| 教程形式 | completed／自动通过  | [deepseek-flash-final](../examples/deepseek-flash-final/tutorial/evaluation.json) · [输入](../examples/deepseek-flash-final/tutorial/input.json) · [输出](../examples/deepseek-flash-final/tutorial/output.json) · [Trace](../examples/deepseek-flash-final/tutorial/trace.jsonl) |

## 真实动态决策证据

- [工具失败恢复](../examples/deepseek-flash/tool_failure/trace.jsonl)：seq9实际检索错误→seq11换查询成功；seq46模型首稿30.55秒→seq52改旁白→seq56为29.5秒。该早期稿另有UI缺陷，恢复证据不能代替最终内容质量。
- [最终压缩稿](../examples/deepseek-flash-final/duration_revision/output.json)：保留用户提供54.35秒初稿的失败测量，经模型改稿、复检后21.9秒。初稿明确是合成输入，不冒充模型生成。
- [人工反馈闭环](../examples/deepseek-flash-final/human_feedback/trace.jsonl)：seq56模拟返修→seq61一次原子patch改旁白、字幕、画面→seq68复检通过→seq76重新初稿审核→seq81终稿审核。收尾漏引随后加严检查；最新重复运行没有完整完成，见后述。
- [耳机修订](../examples/deepseek-flash-final/headphones/trace.jsonl)：保留H1型号，未再报型号数字错误；seq55/66/77分别原子修改12/8/7项，最终28.6秒并完成审核。具体手势及引用问题由真实反馈驱动修订。
- [不可行时长](../examples/deepseek-flash-validation/too_short/trace.jsonl)：seq23实际估时4.1秒、目标1秒，seq27请求用户确认是否调整到约5秒，原要求未改变。不是实际录音或全局最短证明，未检查草稿也不冒充成稿。
- [三镜技能应用](../examples/deepseek-flash-validation/skill_showcase/output.json)：恰好S1/S2/S3、18秒；平台表达、镜头顺序、展示时间及抽象画面有实际产物。输入点名相关方法，不能据此证明自主技能路由。

## 审阅、修补与仍存局限

首轮[缺陷审阅](../examples/deepseek-flash/manual_audit.json)、[四稿复核](../examples/deepseek-flash-recheck/content_review.json)、[最新定向审阅](../examples/deepseek-flash-validation/content_review.json)均由Codex进行有限文件复核，明确无真人签字；原始output/trace/evaluation不改写。

已修补：具体功能/UI术语的证据检查；收尾复述已列功能短语也须本镜来源与有效claim；复合claim由自身原文独立支持；关联正文／引用原子修改；人工返修同步检查首镜旁白和字幕；原文中完整型号数字豁免；语义核验状态与失败usage记录；超时提示允许模型选择压缩、追问或停止。

仍未解决：

1. 同模型语义核验会波动，最新人工返修曾在本镜已有来源时误报空来源，经过多轮修改到v16、60次尝试后仍未完成复检。此前成功闭环不是稳定性保证。
2. 定向词表不理解全部否定或制作语境，会把“不展示按钮”及画面停留“1秒”当成需来源的断言。它也会漏过未列同义表达，不能称通用事实验证。
3. 少数创作措辞如“新手也能弄顺眼”存在易用性暗示，需创作者复核；应与明确编造数字或新功能区分。显式claim均有原文也不证明所有未声明语句已核对。
4. 最新不可行时长草稿包含未完成的复合引用，状态是waiting_human，不是通过事实检查的可交付脚本。
5. 模型仍会选无效patch、重复动作，教程曾用39/40次才完成。检查只能如实阻断，不能保证规划收敛。
6. 时长来自固定语速与展示时间；检索是词法规则、冲突依赖显式分组。未做真实配音、视频生成、分布式并发或任意节点崩溃续跑。

## 技能、历史对照与待办

有16个真实技能包，human-feedback和visual-direction为1.1，其余1.0。[跨批次技能记录](../examples/deepseek-skill-coverage.json)覆盖16项加载与模型声明；包含定向、失败和未完成任务，不等于16项效果或因果增益验证。最后需求变体成功使用澄清技能但在方向阶段402；最后检索变体首请求402，不能伪称这次使用了改写技能。

Qwen历史仍保存在[原live目录](../examples/live/summary.json)，3/14达到对应预期、未完整生成正常成稿，来自多轮迭代，不与Flash作同版本统计比较。

已记录的开发／验证时段为2026年10月30日21:02–23:00（约1小时58分钟），以及10月30日23:53至10月31日01:25（约1小时32分钟），合计约3小时30分钟，时区Asia/Shanghai。时间依据见 [progress.md](../progress.md)；不含此前选题调研、两阶段间隔、后续归档及提交材料核对。包含AI并行开发、等待与调用，不是候选人纯手工工时。

剩余：为后续实验建立总费用／请求预算，改善核验一致性与复杂返修收敛，再进行小范围真实复验；候选人亲自复核和解释；提供GitHub远端并提交最终URL、SHA。当前不宣称全部达标，也不虚构远端。
