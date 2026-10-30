"""Model-driven LangGraph loop and version-bound human review gates."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from .business_tools import check_rules, estimate_duration, search_materials
from .prompts import build_messages, tools_for_state
from .schemas import Brief, Direction, Script
from .script_patch import apply_script_patch
from .model import ContextLimitError

TERMINAL = {"completed", "incomplete", "failed", "cancelled"}


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def event(state: dict, kind: str, **values: Any) -> None:
    state.setdefault("events", []).append({
        "seq": len(state.get("events", [])) + 1,
        "time": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "phase": state.get("phase"),
        "script_version": state.get("script_version", 0),
        **values,
    })
    if os.getenv("SCRIPT_AGENT_PROGRESS") == "1" and kind in {"model_action", "tool_result", "human_review_requested", "stopped", "completed"}:
        names = ",".join(c.get("function", {}).get("name", "") for c in values.get("tool_calls", []))
        print(f"[{state.get('run_id', '')[:8]}] {len(state['events'])} {state.get('phase')} {kind} {values.get('tool', names)}", file=sys.stderr, flush=True)


def missing_fields(brief: dict) -> list[str]:
    return [name for name in ("topic", "audience", "platform", "target_seconds", "style")
            if brief.get(name) is None or (isinstance(brief.get(name), str) and not brief[name].strip())]


def checks_current(state: dict, require_pass: bool = True) -> bool:
    script_hash = fingerprint(state.get("script"))
    for kind in ("duration", "rules"):
        report = state.get("checks", {}).get(kind, {})
        if report.get("script_hash") != script_hash or report.get("script_version") != state.get("script_version"):
            return False
        if report.get("data_hash") != state["data_hash"] or report.get("brief_hash") != fingerprint(state["brief"]):
            return False
        if require_pass and report.get("passed") is not True:
            return False
    return True


class AgentEngine:
    def __init__(self, model: Any, registry: Any):
        self.model = model
        self.registry = registry

    def build(self, checkpointer: Any):
        graph = StateGraph(dict)
        graph.add_node("agent", self.agent)
        graph.add_node("tools", self.tools)
        graph.add_node("human_review", self.human_review)
        graph.add_node("apply_review", self.apply_review)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", lambda s: END if s["status"] in TERMINAL else "tools")
        graph.add_conditional_edges("tools", self.after_tools)
        graph.add_edge("human_review", "apply_review")
        graph.add_conditional_edges("apply_review", lambda s: END if s["status"] in TERMINAL else "agent")
        return graph.compile(checkpointer=checkpointer)

    @staticmethod
    def after_tools(state: dict) -> str:
        if state["status"] in TERMINAL:
            return END
        return "human_review" if state.get("pending_review") else "agent"

    def agent(self, original: dict) -> dict:
        state = copy.deepcopy(original)
        if state["model_calls"] >= state["max_model_calls"]:
            return self.stop(state, "incomplete", "model_call_limit", "达到模型请求次数上限。")
        if state["tool_calls"] >= state["max_tool_calls"]:
            return self.stop(state, "incomplete", "tool_call_limit", "达到工具调用次数上限。")
        state["status"] = "running"
        state["model_calls"] += 1
        try:
            if hasattr(self.model, "set_state"):
                self.model.set_state(state)
            messages = build_messages(state, self.registry.catalog())
            reply = self.model.chat(messages, tools_for_state(state))
            state["messages"].append(reply)
            state["pending_calls"] = reply.get("tool_calls") or []
            event(state, "model_action", content=reply.get("content"), tool_calls=state["pending_calls"],
                  usage=getattr(self.model, "last_usage", {}), model_call=state["model_calls"],
                  action_protocol=getattr(self.model, "last_action_protocol", "explicit_offline_mock"),
                  response_metadata=getattr(self.model, "last_response_metadata", {}),
                  public_response=getattr(self.model, "last_public_response", None))
            if not state["pending_calls"]:
                state["no_action_count"] = state.get("no_action_count", 0) + 1
                if state["no_action_count"] >= 3:
                    return self.stop(state, "incomplete", "no_structured_action", "模型连续三次未提供结构化动作。")
                state["messages"].append({"role": "user", "content": "请使用提供的工具执行下一步。不能通过普通文本声称完成；需要提交稿件、检查并请求人工审核，或者明确申请未完成。"})
            else:
                state["no_action_count"] = 0
        except Exception as exc:
            event(state, "model_error", error=str(exc), model_call=state["model_calls"],
                  response_metadata=getattr(self.model, "last_response_metadata", {}))
            if isinstance(exc, ContextLimitError):
                return self.stop(state, "incomplete", "context_budget_exceeded", str(exc))
            return self.stop(state, "failed", "model_unavailable", str(exc))
        return state

    def tools(self, original: dict) -> dict:
        state = copy.deepcopy(original)
        calls = state.pop("pending_calls", [])
        if not calls:
            return state
        # Reject batches rather than applying a state mutation and a review against different versions.
        batch_error = len(calls) != 1
        for call in calls:
            if state["tool_calls"] >= state["max_tool_calls"]:
                return self.stop(state, "incomplete", "tool_call_limit", "达到工具调用次数上限。")
            state["tool_calls"] += 1
            name = call.get("function", {}).get("name", "")
            arguments: dict = {}
            try:
                raw = call.get("function", {}).get("arguments", "{}")
                arguments = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(arguments, dict):
                    raise ValueError("工具参数必须为 JSON 对象。")
                if not isinstance(arguments.get("reason"), str) or not arguments["reason"].strip():
                    raise ValueError("reason 必须为非空的简短动作依据。")
                names = arguments.get("used_skills", [])
                if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
                    raise ValueError("used_skills 必须是技能 ID 字符串列表。")
                if any(n not in state["loaded_skills"] for n in names):
                    raise ValueError("声明使用的技能尚未加载，请先 load_skill。")
                if name in {"submit_direction", "submit_script", "patch_script"} and not names:
                    raise ValueError("提交产物时必须声明至少一个实际采用的已加载技能 used_skills。")
                if batch_error:
                    raise ValueError("每一轮只允许调用一个工具，观察结果后再选择下一动作。")
                remaining = state["failure_remaining"].get(name, 0)
                if remaining > 0:
                    state["failure_remaining"][name] = remaining - 1
                    raise RuntimeError(f"INJECTED_FAILURE: {name} 本次调用模拟失败；已有成果已保留。")
                result = self.execute(state, name, arguments)
            except (ValueError, TypeError, KeyError, ValidationError, RuntimeError) as exc:
                result = {"ok": False, "error": str(exc), "recoverable": True}
                check_name = {"estimate_duration": "duration", "check_rules": "rules"}.get(name)
                if check_name:
                    self.save_check(state, check_name, {"passed": False, "issues": [{"code": "tool_error", "message": str(exc)}]})
            except Exception as exc:
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "recoverable": True}
                check_name = {"estimate_duration": "duration", "check_rules": "rules"}.get(name)
                if check_name:
                    self.save_check(state, check_name, {"passed": False, "issues": [{"code": "tool_error", "message": str(exc)}]})
            state["messages"].append({"role": "tool", "tool_call_id": call["id"],
                                      "content": json.dumps(result, ensure_ascii=False)})
            event(state, "tool_result", call_id=call["id"], tool=name, arguments=arguments, result=result,
                  tool_call=state["tool_calls"])
            if name != "load_skill" and result.get("ok", True) is not False:
                self.record_skill_use(state, name, arguments, result)
        return state

    @staticmethod
    def save_check(state: dict, kind: str, report: dict) -> dict:
        report = {**report, "script_version": state["script_version"],
                  "script_hash": fingerprint(state.get("script")), "data_hash": state["data_hash"],
                  "brief_hash": fingerprint(state["brief"])}
        state["checks"][kind] = report
        return report

    @staticmethod
    def record_skill_use(state: dict, tool: str, arguments: dict, result: dict) -> None:
        names = arguments.get("used_skills", [])
        if not names and state.get("last_loaded_skill"):
            names = [state["last_loaded_skill"]]
        # All skills declared for one action refer to the same tool-result event.
        # Appending an attribution must not move subsequent attributions forward.
        artifact_event_seq = state["events"][-1]["seq"]
        for name in dict.fromkeys(names):
            if name not in state["loaded_skills"]:
                continue
            skill = state["loaded_skills"][name]
            event(state, "skill_application", skill_id=name, skill_version=skill["version"],
                  tool=tool, reason=arguments.get("reason", ""),
                  artifact_hash=fingerprint(result), artifact_event_seq=artifact_event_seq,
                  attribution="model_declared" if arguments.get("used_skills") else "subsequent_action_candidate")

    def execute(self, state: dict, name: str, args: dict) -> dict:
        if name == "load_skill":
            if args["name"] in state["loaded_skills"]:
                raise ValueError("技能已加载，正文在当前状态中。加载不会修改方向或脚本，请应用方法提交实际产物。")
            skill = self.registry.load(args["name"])
            state["loaded_skills"][args["name"]] = skill
            state["last_loaded_skill"] = args["name"]
            event(state, "skill_loaded", skill_id=args["name"], version=skill["version"], reason=args.get("reason", ""))
            return skill

        if name == "search_materials":
            result = search_materials(args["query"], state["materials"])
            known = {m["source_id"]: m for m in state["retrieved_materials"]}
            for material in result.get("matches", []):
                known[material["source_id"]] = material
            state["retrieved_materials"] = list(known.values())
            return result

        if name == "submit_direction":
            missing = missing_fields(state["brief"])
            if missing:
                raise ValueError(f"请先通过 ask_user 补齐需求字段：{missing}")
            if state["phase"] != "direction":
                raise ValueError("当前不在方向阶段；改变创作要求需先请求用户明确补充。")
            payload = {k: v for k, v in args.items() if k not in ("reason", "used_skills")}
            direction = Direction.model_validate(payload).model_dump()
            if state.get("direction") and not state.get("revision_required"):
                raise ValueError("方向已提交，请请求人工审核；收到修改意见或新需求后才能重提方向。")
            known = {m["source_id"] for m in state["retrieved_materials"]}
            if not direction["source_ids"] or not set(direction["source_ids"]).issubset(known):
                raise ValueError("创作方向必须引用已通过 search_materials 查到的资料。无资料时请补查、追问或说明未完成。")
            if state.get("revision_required") and fingerprint(direction) == fingerprint(state.get("direction")):
                raise ValueError("用户要求修改方向，但提交内容没有变化。")
            state["direction"] = direction
            state["direction_version"] += 1
            state["revision_required"] = False
            return {"ok": True, "direction_version": state["direction_version"], "direction": direction}

        if name in {"submit_script", "patch_script"}:
            if state["phase"] not in ("draft", "final"):
                raise ValueError("需要先获得方向审核批准，才能提交脚本。")
            if name == "patch_script":
                if not state.get("script"):
                    raise ValueError("请先提交脚本，才能局部修订。")
                script = apply_script_patch(state["script"], args["edits"])
            else:
                payload = {k: v for k, v in args.items() if k not in ("reason", "used_skills")}
                script = Script.model_validate(payload).model_dump()
            old_hash = fingerprint(state.get("script"))
            if fingerprint(script) == old_hash:
                raise ValueError("提交的稿件内容没有变化；原版本及检查仍保留。请实际删改旁白、字幕、画面或引用，不能重复提交同一稿件。")
            state["script"] = script
            state["script_version"] += 1
            state["checks"] = {}
            state["revision_required"] = False
            return {"ok": True, "script_version": state["script_version"], "script_hash": fingerprint(script),
                    "script": script,
                    "message": "已保存当前稿件；旧检查与终稿批准失效，请对当前版本重新检查。"}

        if name in ("estimate_duration", "check_rules"):
            if not state.get("script"):
                raise ValueError("请先提交脚本。")
            if name == "estimate_duration":
                report = estimate_duration(state["script"], state["rules"], state["brief"]["target_seconds"])
                return self.save_check(state, "duration", report)
            report = check_rules(state["script"], state["materials"], state["rules"])
            if report["passed"]:
                if state["model_calls"] >= state["max_model_calls"]:
                    self.stop(state, "incomplete", "model_call_limit", "事实核验前达到模型请求次数上限。")
                    return self.save_check(state, "rules", {"passed": False, "issues": [{"code": "limit", "message": "未完成语义核验"}]})
                state["model_calls"] += 1
                # The checker sees the dataset, not the planner's assertions of success.
                try:
                    semantic = self.model.verify_script(state["script"], state["materials"])
                    event(state, "semantic_verification", result=semantic, usage=getattr(self.model, "last_usage", {}),
                          response_metadata=getattr(self.model, "last_response_metadata", {}),
                          model_call=state["model_calls"], mode=state["mode"])
                    report["semantic"] = semantic
                    report["scope"] = "deterministic_and_semantic"
                    report["semantic_status"] = "passed" if semantic.get("passed") is True else "failed"
                    report["requires_semantic_verification"] = False
                    report["passed"] = semantic.get("passed") is True
                    report["issues"] = report.get("issues", []) + semantic.get("issues", [])
                except Exception as exc:
                    event(state, "semantic_error", error=str(exc), usage=getattr(self.model, "last_usage", {}),
                          response_metadata=getattr(self.model, "last_response_metadata", {}),
                          model_call=state["model_calls"], mode=state["mode"])
                    if isinstance(exc, ContextLimitError):
                        self.stop(state, "incomplete", "context_budget_exceeded", str(exc))
                    report["semantic_status"] = "unavailable"
                    report["passed"] = False
                    report.setdefault("issues", []).append({"code": "semantic_unavailable", "message": str(exc)})
            else:
                report["semantic"] = {"status": "not_run", "reason": "deterministic_checks_failed"}
            return self.save_check(state, "rules", report)

        if name == "request_review":
            if state.get("revision_required"):
                raise ValueError("需要先根据人工意见修改并提交新版本。")
            phase = state["phase"]
            if phase == "direction" and not state.get("direction"):
                raise ValueError("请先提交创作方向。")
            if phase == "draft" and (not state.get("script") or not checks_current(state, False)):
                raise ValueError("初稿审核前需要提交稿件并运行当前版本的时长与规则初检；失败结果可带入初稿审核。")
            if phase == "final" and not checks_current(state, True):
                raise ValueError("终稿审核要求当前版本的时长与事实/品牌检查全部通过。请修订、复检或说明未完成。")
            self.queue_review(state, phase, args.get("reason", ""))
            return {"ok": True, "status": "waiting_human", "review_id": state["pending_review"]["review_id"], "phase": phase}

        if name == "ask_user":
            fields = args.get("fields", [])
            allowed = {"topic", "audience", "platform", "target_seconds", "style"}
            if not isinstance(fields, list) or any(f not in allowed for f in fields):
                raise ValueError("fields 只允许创作需求字段；一般资料问题请传空列表。")
            self.queue_review(state, "clarification", args["question"], fields=fields)
            return {"ok": True, "status": "waiting_human", "question": args["question"]}

        if name == "finish_incomplete":
            self.stop(state, "incomplete", "model_stopped", args["reason"])
            return {"ok": True, "status": "incomplete", "reason": args["reason"]}
        raise ValueError(f"未知工具：{name}")

    @staticmethod
    def queue_review(state: dict, stage: str, reason: str, fields: list[str] | None = None) -> None:
        version = state["direction_version"] if stage == "direction" else state["script_version"]
        review_id = fingerprint([state["run_id"], stage, version, len(state["review_history"]), len(state["events"])])[:20]
        state["pending_review"] = {"review_id": review_id, "stage": stage, "version": version,
                                   "object_hash": fingerprint(state.get("direction") if stage == "direction" else state.get("script")),
                                   "reason": reason, "fields": fields or [],
                                   "direction": state.get("direction"), "script": state.get("script"),
                                   "checks": state.get("checks", {})}
        state["status"] = "waiting_human"
        event(state, "human_review_requested", review_id=review_id, stage=stage, version=version, reason=reason)

    @staticmethod
    def human_review(state: dict) -> dict:
        response = interrupt(state["pending_review"])
        return {**state, "human_response": response}

    def apply_review(self, original: dict) -> dict:
        state = copy.deepcopy(original)
        response = state.pop("human_response")
        pending = state["pending_review"]
        expected_version = state["direction_version"] if pending["stage"] == "direction" else state["script_version"]
        expected_object = state.get("direction") if pending["stage"] == "direction" else state.get("script")
        if (response.get("review_id") != pending["review_id"] or pending["version"] != expected_version
                or pending["object_hash"] != fingerprint(expected_object)):
            return self.stop(state, "failed", "stale_approval", "审核回复与当前阶段、版本或内容不匹配。")
        stage, decision = pending["stage"], response["decision"]
        review = {**response, "stage": stage, "version": pending["version"]}
        state["review_history"].append(review)
        state["pending_review"] = None
        state["status"] = "running"
        event(state, "human_decision", **review)
        if decision == "cancel":
            return self.stop(state, "cancelled", "human_cancelled", response.get("feedback") or "用户取消任务。")
        if stage == "clarification":
            answers = response.get("answers", {})
            state.setdefault("clarification_history", []).append({
                "answers": answers, "feedback": response.get("feedback", ""), "review_id": pending["review_id"]})
            old_brief = state["brief"]
            updated = Brief.model_validate({**old_brief, **answers}).model_dump()
            if updated != old_brief:
                state["brief"] = updated
                state["phase"] = "direction"
                state["direction"] = None
                state["checks"] = {}
                state["revision_required"] = False
            state["messages"].append({"role": "user", "content": "人工补充：" + json.dumps({"answers": answers, "feedback": response.get("feedback", "")}, ensure_ascii=False)})
            return state
        if decision == "revise":
            state["revision_required"] = True
            state["feedback"].append({"stage": stage, "feedback": response["feedback"], "version": pending["version"]})
            state["messages"].append({"role": "user", "content": f"人工审核要求修改（{stage} 阶段）：{response['feedback']}。请加载适用技能、修改并提交新版本后重新送审。原始硬性要求保持有效；若需要改变请通过 ask_user 请求明确确认字段。"})
            if stage != "direction":
                state["checks"] = {}
            return state
        if stage == "direction":
            state["phase"] = "draft"
        elif stage == "draft":
            state["phase"] = "final"
        elif stage == "final":
            if not checks_current(state, True):
                return self.stop(state, "failed", "stale_approval", "当前版本的检查无效，不能完成。")
            state["status"] = "completed"
            state["completed_script_hash"] = fingerprint(state["script"])
            event(state, "completed", script_hash=state["completed_script_hash"])
            return state
        state["messages"].append({"role": "user", "content": f"人工已批准 {stage} 阶段。现在进入 {state['phase']} 阶段。初稿批准不豁免检查失败项；终稿必须通过全部检查。"})
        return state

    @staticmethod
    def stop(state: dict, status: str, code: str, reason: str) -> dict:
        state.update(status=status, stop_reason={"code": code, "message": reason})
        event(state, "stopped", status=status, code=code, reason=reason)
        return state
