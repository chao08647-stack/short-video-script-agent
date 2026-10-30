# 开发阶段真实失败记录

这里保存修复前的实际运行，供评审核对问题、修改依据和限制。它们不计为当前实现通过的证据，不能与 `examples/mock` 混算。

- `context-4k`：服务原 4096-token 上下文不足，首个业务请求 HTTP 400。用户后来升级到 32768。
- `initial-32k/normal`：原生工具模式下引用映射错误，重复检查，最后模型请求超时。
- `native-business`：多场景原生工具测试，包括正文里的动作未被解析、技能 ID 被当成工具名、无效字段和重复动作。
- `json-loop/normal`：严格 JSON Schema 修复格式后，40 次动作格式正确，但模型误把加载压缩技能当作已经修改稿件，达到上限。
- `identical-drafts/duration_revision`：模型多次原样提交初稿。开发者停止诊断进程，导出的是最后 checkpoint；`interruption.json` 说明中断，不能把 `running` 快照当作完成任务。
- `invalid-clarification/normal`：追问字段 `angle` 不属于允许的创作要求；后来让模型 schema 与工具字段约束保持一致。

记录中的人工回复均为评估器模拟。早期记录可能缺少后续加入的代码指纹或动作协议字段，以各实验说明及原始 Trace 为准。没有重写失败 Trace 来模拟成功。

其它后续目录（如 `pre-patch`、`batch-index-shift`、`before-final-check`）保存对应改进前的原始单例记录。带 `interruption.json` 的目录仅是开发者中止进程时的最后 checkpoint，不能当作自然完成的验收。早期多用例进程的源码指纹可能读取了后来修改的磁盘版本；最终独立进程复验已使用导入时快照，详见评估文档。
