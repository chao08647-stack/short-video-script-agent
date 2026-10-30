# 有依据的短视频脚本 Agent

小影校招考核 **第 4 题**。使用 **Python、LangGraph、16 个按需加载的业务 Skills 和三阶段人工审核**，根据产品资料生成文字分镜、旁白与字幕，检查事实和时长，并根据实际反馈修改。

交付的是可编辑脚本及检查证据，不需要视频输入，不生成配音或 MP4。仓库包含离线 Mock；真实模型服务需要单独配置。

**当前状态：DeepSeek Flash 已接入，321 项工程测试和 14 项 Mock 场景通过；完整真实验收仍未全部通过。** 四批真实测试与后续文件审阅保留了成功和失败。最近一轮全量测试为 13/15 自动通过，后续六项定向验证为 3/6；人工返修再次耗尽 60 次上限，两项新变体又遇 HTTP 402。不能用此前成功覆盖最新失败。16 个技能包均有真实加载／声明记录，但部分来自定向或未完成任务，不代表全部技能效果已验证。见 [评估文档](docs/03-evaluation.md) 和 [完整批次索引](examples/deepseek-validation-index.json)。

## 评审入口

| 内容 | 入口 |
|---|---|
| 需求与验收范围 | [docs/01-requirements.md](docs/01-requirements.md) |
| 图流程、技能、检查及人审设计 | [docs/02-solution.md](docs/02-solution.md) |
| 实际测试、成功与失败、已知限制 | [docs/03-evaluation.md](docs/03-evaluation.md) |
| AI 辅助范围与真实贡献记录 | [docs/04-ai-usage.md](docs/04-ai-usage.md) |
| 难点与后续改进 | [docs/05-retrospective.md](docs/05-retrospective.md) |
| 可复现输入 | [examples/inputs](examples/inputs) |
| Mock 实际结果与覆盖 | [examples/mock/summary.json](examples/mock/summary.json)、[技能覆盖](examples/mock/skill_coverage.json) |
| DeepSeek 实际结果与审阅 | [批次索引](examples/deepseek-validation-index.json)、[最近定向审阅](examples/deepseek-flash-validation/content_review.json)、[全部真实技能记录](examples/deepseek-skill-coverage.json) |
| 历史 Qwen 对照 | [examples/live/summary.json](examples/live/summary.json) |
| 多轮开发实验与失败记录 | [examples/experiments](examples/experiments) |

以评估文档和实际运行文件判断完成情况。Mock 不证明真实模型决策效果；评估程序中的人工回复明确标记为模拟，不冒充真人审核。

## 环境与安装

要求 Python 3.11 以上，开发环境使用 Python 3.12。当前锁定版本为 LangGraph 1.2.18、`langgraph-checkpoint-sqlite` 3.1.2，分别负责有状态图与中断、SQLite checkpoint 持久化。请在仓库根目录运行。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
source .venv/bin/activate
```

下文使用激活后的 `python`。如果 PowerShell 不允许运行激活脚本，可将命令中的 `python` 直接替换为 `.\.venv\Scripts\python.exe`，无需修改执行策略。需要复现提交环境的精确依赖时，先安装 `requirements-lock.txt`，再以 `python -m pip install --no-deps -e .` 安装项目。

精确依赖安装命令：

```console
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
```

## 先运行离线流程

```console
python -m script_agent run --input examples/inputs/normal.json --mode mock
```

程序运行到第一道人审门，显示 `run_id` 和当前 `review_id`，状态为 `waiting_human`。这不是卡住，也不代表完成。

下面命令中的 `<run_id>` 和 `<当前review_id>` 需要替换为程序实际显示的值，去掉尖括号。

```console
python -m script_agent status --run-id <run_id>
python -m script_agent review --run-id <run_id>
python -m script_agent resume --run-id <run_id> --review-id <当前review_id> --decision approve
```

依次查看并批准 **方向 → 初稿 → 终稿**。每次暂停产生新的审核 ID，不能重复使用旧 ID。只有终稿批准且当前版本的检查有效，状态才变为 `completed`。

提交修改意见或取消：

```console
python -m script_agent resume --run-id <run_id> --review-id <当前review_id> --decision revise --feedback "开场直接展示操作，减少铺垫，原时长保持不变"
python -m script_agent resume --run-id <run_id> --review-id <当前review_id> --decision cancel
```

用户只提交意见，由模型修改稿件。修改后重新检查和审核；人工批准不能让超时或无依据事实变成合格。

缺信息请求使用 `reply`。例如将下面内容保存为 `answers.json`：

```json
{
  "audience": "短视频剪辑新手",
  "target_seconds": 30,
  "style": "轻松、直白"
}
```

```console
python -m script_agent resume --run-id <run_id> --review-id <当前review_id> --decision reply --answers answers.json
```

产品事实不能靠填写创作字段补造。需要新产品资料时，更新资料集并新建任务；一般澄清说明也可以通过 `--feedback` 提交。

状态默认保存在 `.runs/`，包含 SQLite checkpoint。正常暂停在人审门后，关闭终端仍可用同一任务 ID 恢复。恢复操作对同一任务使用跨进程锁：另一个进程正在处理时会明确拒绝，须稍后查看新的审核状态。进程退出后操作系统释放锁；这不等于支持任意模型请求中途崩溃后的自动续跑。

可通过 `SCRIPT_AGENT_RUNS_DIR` 或命令前的 `--runs-dir` 指定另一目录，后续查询和恢复须使用同一目录。例如 `python -m script_agent --runs-dir .runs/review-demo status --run-id <run_id>`。

## 接入真实模型

参考 [.env.example](.env.example) 创建本地 `.env`，填入自己的密钥，或直接配置环境变量。已有 `.env` 时只修改所需字段。主配置使用 DeepSeek Flash：

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=120
LLM_ACTION_PROTOCOL=native
LLM_THINKING=disabled
LLM_MAX_TOKENS=4096
LLM_CONTEXT_WINDOW=16384
```

`LLM_API_KEY` 在本地填入有效密钥。接口使用 Chat Completions；`native` 让模型返回原生工具调用，工具执行结果会送回模型决定下一步。本适配器不保留推理内容供工具调用续接，因此显式关闭 thinking；DeepSeek 官方支持该组合，见 [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。动作协议需要根据服务能力选择：

| `LLM_ACTION_PROTOCOL` | 服务要求与行为 |
|---|---|
| `native`（代码默认） | 支持原生 `tool_calls` 与自动工具选择；普通正文中的 JSON 不当作原生调用执行。 |
| `json`（可选本地服务） | 支持严格 `json_schema` 结构化输出及 `anyOf`、`const`；每个分支绑定动作名和对应参数，适配层再次校验后交给相同工具执行。 |

DeepSeek 的 `response_format` 文档列出 `text` 和 `json_object`，不支持本项目 `json` 协议所要求的 `json_schema`，所以 DeepSeek 配置必须选择 `native`。两种协议都调用真实模型、返回真实工具观察，并使用相同的人审与检查约束；JSON 协议不属于 Mock。服务不支持所需格式时会直接报错，不自动降级或切换协议。见 [Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)。实际采用的协议与运行效果以 [评估记录](docs/03-evaluation.md) 为准，不能只用普通聊天成功证明可用。

这里的 **16K = 16,384 token，是应用为每次模型请求设置的输入与预留输出总预算**。`LLM_MAX_TOKENS=4096` 只限制输出，`LLM_CONTEXT_WINDOW=16384` 由项目在发送请求前检查，不作为 DeepSeek API 参数发送。官方当前列出的 Flash 服务端原生上下文为 1M；设置应用预算不会改变服务端容量。见 [模型规格](https://api-docs.deepseek.com/quick_start/pricing/)。

预检使用 [DeepSeek-V4.1-Flash-1017 官方 tokenizer 与编码参考](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017/tree/1bae0e1088993b9b82de08f59de5be5a34e42170)：取完整提示渲染与请求 JSON 的 token 计数较大值，再加入 10% + 128 token 余量，并预留本次输出额度。超过预算时明确停止；响应返回后还会检查 `usage`。公开编码参考不能证明与云端实际提示模板完全一致，因此这是 tokenizer 估算与事后核对，不能承诺服务端精确的 16K 硬上限。实际 token 用量以响应 `usage` 为准，见 [Token 用量说明](https://api-docs.deepseek.com/quick_start/token_usage/)。

已有本地 Qwen 服务时，可把 `.env` 中对应字段改为以下配置；保留 `LLM_TIMEOUT_SECONDS=120`。地址属于开发者自己的服务，其他电脑需提供自己的地址；无鉴权时密钥可留空。

```dotenv
LLM_BASE_URL=http://127.0.0.1:8012/v1
LLM_MODEL=qwen25-14b-pbn-answer
LLM_API_KEY=
LLM_ACTION_PROTOCOL=json
LLM_THINKING=default
LLM_MAX_TOKENS=2048
LLM_CONTEXT_WINDOW=0
```

`LLM_CONTEXT_WINDOW=0` 关闭本项目的 DeepSeek 专用预算预检。Qwen 服务端的上下文容量由服务启动配置决定；已有基线服务配置为 32K。DeepSeek tokenizer 不用于声称 Qwen 的精确计数，服务参数配置成功也不等于业务验收通过。

```console
python -m script_agent run --input examples/inputs/normal.json --mode live
```

后续审核命令与 Mock 相同，恢复时自动使用任务原有模式。模型失败、上下文不足、输出截断等错误保持可见，不会自动切换为 Mock。具体设置与实际效果见评估文档。

需要观察执行进度时，PowerShell 使用：

```powershell
$env:SCRIPT_AGENT_PROGRESS = "1"
python -m script_agent run --input examples/inputs/normal.json --mode live
```

macOS / Linux 使用：

```bash
SCRIPT_AGENT_PROGRESS=1 python -m script_agent run --input examples/inputs/normal.json --mode live
```

## 输入、资料与输出

最小完整输入示例：

```json
{
  "brief": {
    "topic": "介绍小剪 App 的字幕功能",
    "audience": "短视频剪辑新手",
    "platform": "抖音",
    "target_seconds": 30,
    "style": "轻松、直白"
  },
  "dataset": "demo"
}
```

[data](data) 提供 `demo`、`empty`、`conflict` 三套合成资料。产品原文、来源 ID、版本、规则及估时参数在启动任务时生成快照。平台表达建议是项目的创作模板，不是实时官方平台政策。

脚本输出包含标题、分镜、画面文字描述、旁白／字幕、来源与支持原文、时长估计、检查结果和任务状态。估时使用固定语速与镜头展示需求，不等于真实配音或成片测量。

每次暂停或结束都会保存运行产物，也可以导出到指定目录：

```console
python -m script_agent export --run-id <run_id> --output .runs/export-normal
```

导出内容包括 `input.json`、`output.json`、`data_snapshot.json`、`trace.jsonl`、`script_versions.json` 和 `script.md`。导出中间结果会保留 `waiting_human` 等实际状态，不自动标为完成。

## 技能与运行边界

```console
python -m script_agent skills list
```

[skills](skills) 中有 16 个独立技能包，覆盖需求、资料、脚本创作和修订。模型先读取技能 ID 与适用场景描述，再按需加载具体 `SKILL.md`；目录命令可查看描述及版本。当前上下文保留所有已加载技能的完整正文，每个技能每轮只提供一次，并包含当前稿件、完整错误定位及最近 8 次动作摘要。三个业务工具负责检索、估时和规则／事实检查，另有提交稿件、局部编辑、审核等控制动作。技能加载、模型声明的使用和候选关联分别记录，不能用文件数量或加载次数证明效果。16 个技能的实际覆盖必须分别核对 Mock 与 live 的 Trace，未覆盖项不会因为存在技能文件就算通过。

模型可以通过 `patch_script` 修改现有稿件的一处文字或引用，成功后生成新版本并重新检查。动作清单按前置条件过滤：已加载技能不再加载、同一稿件的有效检查不重复执行、未改变内容的方向或稿件不接受重提。这里约束的是合法操作，具体查什么、改哪里、如何改仍由模型决定。

默认上限是每任务 40 次模型尝试、60 次工具尝试（包括被拒绝动作），人工恢复后继续累计；它们不是精确计费请求数。达到上限返回 `incomplete` 并保留成果。LangGraph 递归保护上限随配置预算计算，避免较大的合法调用预算先被固定图步数中断。事实检查结合确定性规则和独立模型核验，仍可能误判或漏判；明确限制和失败案例见评估文档。

## 执行测试与评估

```console
python -m pytest --basetemp .runs/pytest-tmp
python -m script_agent.evaluate --mode mock --simulate-human
```

具备可用模型服务后，可执行真实评估：

```console
python -m script_agent.evaluate --mode live --output .runs/reviewer-live --simulate-human
```

上述命令将新复验写入 `.runs/reviewer-live`，保留 `examples/` 下的所有已提交批次。需要有效额度；默认执行14个基础场景，单个任务上限不是整个评估的费用上限。命令本身不代表复验已通过。

也可以只跑部分场景并写入新目录，避免覆盖已提交证据：

```console
python -m script_agent.evaluate --mode live --cases normal,tool_failure,duration_revision --output .runs/my-live-evaluation --simulate-human
```

`--simulate-human` 明确允许评估器提供预设审核回复，记录中的身份是 `evaluation_simulated_human`。模型动作在 live 模式下仍来自真实模型，但这不代表真人审阅过每份脚本。默认评估分别写入 `examples/mock` 或 `examples/live`，包含实际输入、输出、Trace、汇总与技能覆盖；重新运行会更新该目录。评估器拒绝在同一输出目录混用两种模式。

检查命令的退出码：`pytest` 失败时返回非零；评估器完成导出后，只要输出目录内任一场景未通过验收，就返回退出码 `1`。PowerShell 查看 `$LASTEXITCODE`，macOS / Linux 查看 `$?`。出现结果文件或“已保存”不代表通过；现有 live 批次包含失败且结果有波动，应查看 `summary.json` 和各用例的 `evaluation.json`。

测试和评估包括正常路径、缺信息、无资料、工具失败、超时修订、不可行目标、资料冲突、品牌／事实问题、人审修改和调用上限。个别场景诚实返回未完成是预期结果；是否通过场景验收应查看其 `evaluation.json`，不能只数 `completed`。

## 提交说明

所有代码、说明和验证材料保存在同一仓库；真实密钥和本地运行数据库默认不入 Git。AI 辅助范围、用户决策与尚未发生的个人复核在 AI 使用文档中如实区分。GitHub URL 和最终 commit SHA 应在实际创建远程仓库并提交后填写，本文不提供虚构地址或提交号。
