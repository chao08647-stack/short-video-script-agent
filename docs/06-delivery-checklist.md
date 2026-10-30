# 提交材料核对

核对日期：2026-10-31（Asia/Shanghai）。依据本次提供的考核规则、GitHub 交付规范和第 4 题要求，检查现有文件、内容、链接及归档。此次未联网、未调用模型 API，也未重跑测试；不重新判定未完成的业务验收是否合格。

**结论：本地要求的文件与说明已齐全；GitHub 发布及评审可读性仍未完成。** 文件齐全不等于真实模型全部验收通过，具体结果见 [评估文档](03-evaluation.md)。

## 必需文件

| 要求 | 实际入口 | 本次核对 |
|---|---|---|
| README：环境、安装、运行、评审入口 | [README.md](../README.md) | 已包含 Python 环境、依赖安装、CLI、配置、人审恢复及文档入口 |
| 项目代码与模型／工具接入 | [src/script_agent](../src/script_agent) | 已纳入 Git，包含模型接口、LangGraph、检索／估时／检查和导出 |
| 可执行测试 | [tests](../tests) | 12 个测试模块及配置文件已纳入 Git；本次只检查文件 |
| 输入、实际输出、Trace | [examples](../examples) | 包含真实与 Mock 独立目录、失败记录及索引 |
| 合成资料和规则 | [data](../data) | demo、empty、conflict 资料集及规则；合成边界已注明 |
| 用户、目标、范围、成功标准 | [01-requirements.md](01-requirements.md) | 已覆盖，区分目标与已通过结果 |
| 调用流程、动态决策、技术取舍 | [02-solution.md](02-solution.md) | 已覆盖，包含流程图及模型／程序／人工职责 |
| 测试预期、结果、失败、限制 | [03-evaluation.md](03-evaluation.md) | 已记录实际结果并链接原始文件，不掩盖未通过项 |
| AI 辅助、个人贡献与验证 | [04-ai-usage.md](04-ai-usage.md) | 已区分用户决策／环境支持、AI 开发及模拟审核；无个人手写修改记录的部分如实说明 |
| 难点、学习、下一步 | [05-retrospective.md](05-retrospective.md) | 已记录实际问题、修补和后续方向，未冒充候选人个人经历 |
| 依赖文件 | [pyproject.toml](../pyproject.toml)、[requirements-lock.txt](../requirements-lock.txt) | 已提供安装方式及锁定版本 |
| 环境变量示例 | [.env.example](../.env.example) | 关键模型和运行变量齐全，真实密钥留空 |

16 个 [业务技能包](../skills) 和三阶段 human-in-the-loop 为本项目的附加设计，不能用技能数量替代题目验收。

## 证据文件完整性

至少三组输入、输出及运行记录均已存在，并在评估文档直接引用：

| 类型 | 输入 | 输出 | Trace |
|---|---|---|---|
| 正常生成 | [input.json](../examples/deepseek-flash-final/normal/input.json) | [output.json](../examples/deepseek-flash-final/normal/output.json) | [trace.jsonl](../examples/deepseek-flash-final/normal/trace.jsonl) |
| 资料不足 | [input.json](../examples/deepseek-flash-final/no_materials/input.json) | [output.json](../examples/deepseek-flash-final/no_materials/output.json) | [trace.jsonl](../examples/deepseek-flash-final/no_materials/trace.jsonl) |
| 工具失败 | [input.json](../examples/deepseek-flash-final/tool_failure/input.json) | [output.json](../examples/deepseek-flash-final/tool_failure/output.json) | [trace.jsonl](../examples/deepseek-flash-final/tool_failure/trace.jsonl) |

这些都是 `mode=live` 的已保存运行。资料不足时脚本和时长为空、状态为 `waiting_human`，缺口写在 `pending_review.reason`；这是如实保留未完成状态，不是遗漏成稿文件。

完成稿中的题目字段可定位到 `script.title`、`script.scenes`、`estimated_seconds`、`script.claims`／`sources`、`checks.*.issues` 和 `status`。风险放在检查问题数组中，没有另设顶层 `risks` 字段；题面没有要求固定字段名。

至少两条不同的动态执行记录可直接读出：工具失败 Trace 的 seq 6 报错、seq 7 模型改查询、seq 8 得到资料；无资料 Trace 的 seq 6 空结果、seq 8 和 11 改写查询、seq 14 请求补充。记录包含步骤、参数、结果和简短 `reason`，后续 `model_action` 表示下一动作，无须额外伪造 `next_action` 日志。

测试结果已保存为 [examples/test-results.xml](../examples/test-results.xml)，本次仅读取其现有记录。其他验收点、未通过项及各批次差异见评估文档，不能用上面三组文件的存在替代整体效果验证。

## 其他规范

- CLI 安装、运行、查询、审核恢复、导出步骤可在 README 复制；显式 `--mode mock` 无需模型服务，局限已注明。
- 文档说明 LangGraph 1.2.18 的图、路由和中断职责，以及 checkpoint-sqlite 3.1.2 的持久化职责。
- 代码和输入设置模型／工具次数上限；达到上限保留产物，输出明确未完成状态及原因，计数不因人审恢复清零。
- 已记录开发／验证时段：10 月 30 日 21:02–23:00、23:53 至次日 01:25，合计约 3 小时 30 分钟。选题调研、阶段间隔、后续归档与本次核对另计；不是候选人纯手工工时。
- 必需文件均已跟踪。未发现当前真实密钥或常见密钥格式混入跟踪文件及源码包；`.env` 未跟踪，其路径也未出现在提交历史中。现有 Trace 未包含私有推理字段。
- 本地 Markdown 文档链接已核对；源码包约 4.1 MB，包含必需文件，不含 `.env`、虚拟环境、运行数据库或 `.git`。

## 尚待提交的信息

| 项目 | 状态 |
|---|---|
| 题号 | 已明确为 4，短视频脚本 Agent |
| GitHub URL | 未配置远端；需要将最终仓库发布到实际 GitHub 地址 |
| 最终 commit SHA | 本地可获取；文档收尾提交后执行 `git rev-parse HEAD`，将完整值填入交卷表单 |
| 评审可读权限 | 尚无法确认；私有仓库须给指定评审账号读权限 |

压缩包可作为附带材料，不能替代题面要求的 GitHub URL 与最终 commit SHA。未新增许可申请或测试要求，也未将候选人尚未完成的本人修改、复核写成已经发生。
