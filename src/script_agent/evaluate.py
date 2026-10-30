"""Explicit acceptance runner. Human decisions are simulated and labeled."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .engine import checks_current
from .model import ModelClient
from .mock_model import MockModel
from .runtime import Runtime, project_root, read_json, write_json

for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty() and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def acceptance(case: str, state: dict) -> tuple[bool, list[str]]:
    """Judge observed behavior, rather than treating a terminal label as proof."""
    from .engine import fingerprint

    errors = []
    events = state["events"]
    tools = [(index, e) for index, e in enumerate(events) if e.get("kind") == "tool_result"]

    def tool_events(name):
        return [(index, event) for index, event in tools if event.get("tool") == name]

    def report_pair(name, failed):
        """Find failed check -> changed saved script -> passing same-target check."""
        for before_index, before in tool_events(name):
            old = before.get("result", {})
            if old.get("passed") is not False or not failed(old):
                continue
            for after_index, after in tool_events(name):
                new = after.get("result", {})
                if after_index <= before_index or new.get("passed") is not True:
                    continue
                if new.get("script_version", 0) <= old.get("script_version", 0):
                    continue
                if not old.get("script_hash") or new.get("script_hash") == old["script_hash"]:
                    continue
                if name == "estimate_duration" and new.get("target_seconds") != old.get("target_seconds"):
                    continue
                if any(before_index < index < after_index and event.get("result", {}).get("ok") is True
                       and any(e.get("kind") == "model_action" for e in events[before_index + 1:index])
                       for index, event in tools if event.get("tool") in {"submit_script", "patch_script"}):
                    return True
        return False

    for prefix in ("model", "tool"):
        count, maximum = state.get(f"{prefix}_calls", 0), state.get(f"max_{prefix}_calls", float("inf"))
        if count > maximum:
            errors.append(f"{prefix} call budget exceeded")
    if state["status"] == "completed":
        if not checks_current(state):
            errors.append("completed without valid passing checks")
        stages = {r["stage"] for r in state["review_history"] if r["decision"] == "approve"}
        if stages != {"direction", "draft", "final"}:
            errors.append("completed without all three approval stages")
        if state.get("completed_script_hash") != fingerprint(state.get("script")):
            errors.append("completed script does not match the approved artifact")
    if case in {"no_materials", "conflict", "too_short", "step_limit"}:
        if state["status"] not in {"incomplete", "waiting_human"}:
            errors.append("Expected honest non-completion")
    elif state["status"] != "completed":
        errors.append(f"Expected completed, got {state['status']}")
    if case == "tool_failure":
        failures = [index for index, event in tools
                    if event.get("result", {}).get("ok") is False
                    and "INJECTED_FAILURE" in str(event["result"].get("error", ""))]
        if not failures or not any(event.get("kind") == "model_action" for event in events[failures[0] + 1:]):
            errors.append("Injected failure and a subsequent model decision were not observed")
    if case == "missing_info":
        if not any(e.get("kind") == "human_review_requested" and e.get("stage") == "clarification" for e in events):
            errors.append("Missing information was not clarified")
        if not any(e.get("kind") == "human_decision" and e.get("stage") == "clarification"
                   and e.get("decision") == "reply" and e.get("answers") for e in events):
            errors.append("No actual human answers supplied the missing requirements")
    if case == "duration_revision":
        if not report_pair("estimate_duration", lambda report: report.get("estimated_seconds", 0) > report.get("target_seconds", float("inf"))):
            errors.append("No ordered over-duration -> revised script -> passing same-target feedback path")
        if state["status"] == "completed":
            cited = {claim.get("source_id") for claim in (state.get("script") or {}).get("claims", [])}
            if not {"P01", "P02"}.issubset(cited):
                errors.append("Compression dropped required auto-caption or manual-edit evidence")
    if case == "brand_and_fact_revision":
        def observed_both_issues(report):
            codes = {str(issue.get("code", "")).upper() for issue in report.get("issues", [])}
            return "BANNED_PHRASE" in codes and bool(codes & {"UNSUPPORTED_NUMBER", "UNSUPPORTED_CLAIM", "UNCERTAIN_CLAIM", "MISSING_CITATION"})
        if not report_pair("check_rules", observed_both_issues):
            errors.append("No observed brand/fact violations -> revised script -> passing rules path")
    if case == "human_feedback":
        revised = False
        for index, decision in enumerate(events):
            if decision.get("kind") != "human_decision" or decision.get("decision") != "revise" or not decision.get("feedback"):
                continue
            submit_tool = "submit_direction" if decision.get("stage") == "direction" else "submit_script"
            version_key = "direction_version" if submit_tool == "submit_direction" else "script_version"
            for submit_index, submission in tools:
                if submission.get("tool") not in ({"submit_script", "patch_script"} if submit_tool == "submit_script" else {submit_tool}):
                    continue
                result = submission.get("result", {})
                if submit_index <= index or result.get("ok") is not True or result.get(version_key, 0) <= decision.get("version", 0):
                    continue
                if (any(e.get("kind") == "model_action" for e in events[index + 1:submit_index])
                        and any(e.get("kind") == "human_review_requested" and e.get("stage") == decision.get("stage")
                                for e in events[submit_index + 1:])):
                    revised = True
        if not revised:
            errors.append("No human revision feedback followed by a model revision and renewed review")
        if state["status"] == "completed":
            # This fixed scenario asks to remove opening rhetorical questions.
            # Observable punctuation checks supplement the version/review path;
            # they do not claim to judge arbitrary human feedback semantically.
            scenes = (state.get("script") or {}).get("scenes", [])
            opening = scenes[0] if scenes else {}
            for field in ("narration", "subtitle"):
                if any(mark in opening.get(field, "") for mark in ("?", "？")):
                    errors.append(f"Opening {field} still contains a question mark after human feedback")
    if case == "skill_showcase" and state["status"] == "completed":
        required = {"platform-adaptation", "storyboard-planning", "visual-direction"}
        declared = {e.get("skill_id") for e in events
                    if e.get("kind") == "skill_application" and e.get("attribution") == "model_declared"
                    and e.get("tool") in {"submit_direction", "submit_script", "patch_script"}}
        if not required.issubset(declared):
            errors.append("Directed showcase did not associate all three requested skills with artifacts")
        if len((state.get("script") or {}).get("scenes", [])) != 3:
            errors.append("Directed showcase requires exactly three scenes")
    if case == "query_rewrite":
        searches = tool_events("search_materials")
        recovered = any(
            after_index > before_index
            and before.get("result", {}).get("matches") == []
            and bool(after.get("result", {}).get("matches"))
            and str(before.get("arguments", {}).get("query", "")).strip().casefold()
                != str(after.get("arguments", {}).get("query", "")).strip().casefold()
            and any(e.get("kind") == "model_action" for e in events[before_index + 1:after_index])
            for before_index, before in searches for after_index, after in searches
        )
        if not recovered:
            errors.append("No observed empty search -> changed query -> successful retrieval path")
    if case in {"no_materials", "conflict", "too_short"}:
        honest_stop = state["status"] == "incomplete" and state.get("stop_reason", {}).get("code") == "model_stopped"
        clarification = state["status"] == "waiting_human" and (state.get("pending_review") or {}).get("stage") == "clarification"
        if not (honest_stop or clarification):
            errors.append("Expected a grounded clarification/stop, not an unrelated failure or exhausted loop")
        if case == "no_materials" and not any(e.get("result", {}).get("matches") == [] for _, e in tool_events("search_materials")):
            errors.append("No actual empty search result observed")
        if case == "conflict" and not any(e.get("result", {}).get("conflicts") for _, e in tool_events("search_materials")):
            errors.append("No actual conflicting evidence observed")
        if case == "too_short" and not any(e.get("result", {}).get("passed") is False
                and e["result"].get("estimated_seconds", 0) > e["result"].get("target_seconds", float("inf"))
                for _, e in tool_events("estimate_duration")):
            errors.append("No actual over-duration observation explains non-completion")
    if case == "step_limit":
        code = state.get("stop_reason", {}).get("code")
        prefix = {"model_call_limit": "model", "tool_call_limit": "tool"}.get(code)
        if (state["status"] != "incomplete" or not prefix
                or state.get(f"{prefix}_calls", 0) != state.get(f"max_{prefix}_calls")):
            errors.append("No explicit stop at the configured execution limit")
    return not errors, errors


def run_case(case: str, mode: str, output: Path) -> dict:
    root = project_root()
    started = time.monotonic()
    client = ModelClient() if mode == "live" else MockModel()
    runtime = Runtime(client, root / ".runs" / f"evaluation-{mode}")
    request = read_json(root / "examples" / "inputs" / f"{case}.json")
    print(json.dumps({"case": case, "mode": mode, "event": "start"}), flush=True)
    state = runtime.start(request, mode)
    feedback_sent = False
    clarification_sent = False
    try:
        for _ in range(12):
            if state["status"] != "waiting_human":
                break
            pending = state["pending_review"]
            if pending["stage"] == "clarification":
                if case in {"no_materials", "conflict", "too_short", "step_limit"}:
                    break
                answers = {"audience": "短视频剪辑新手", "platform": "抖音", "target_seconds": 30.0, "style": "轻松、直白"} if case == "missing_info" else {}
                # Only supply absent fields; do not silently change an existing requirement.
                answers = {k: v for k, v in answers.items() if not state["brief"].get(k)}
                if not answers and clarification_sent:
                    break
                clarification_sent = True
                state = runtime.resume(state["run_id"], "reply", answers=answers,
                                       feedback="请依据已有资料自主完成创作并修正稿件问题，保持原始需求和时长不变。没有证据的事实不能添加；真实资料缺口或冲突仍需明确说明。",
                                       review_id=pending["review_id"], actor="evaluation_simulated_human")
            elif case == "human_feedback" and pending["stage"] == "draft" and not feedback_sent:
                feedback_sent = True
                state = runtime.resume(state["run_id"], "revise", feedback="开场请直接说明字幕需求，删掉反问句；其它事实和时长要求不变。",
                                       review_id=pending["review_id"], actor="evaluation_simulated_human")
            else:
                state = runtime.resume(state["run_id"], "approve", review_id=pending["review_id"],
                                       actor="evaluation_simulated_human")
        destination = output / case
        runtime.export_state(state, destination)
        passed, errors = acceptance(case, state)
        result = {"case": case, "mode": mode, "run_id": state["run_id"], "status": state["status"],
                  "acceptance_passed": passed, "acceptance_errors": errors,
                  "elapsed_seconds": round(time.monotonic() - started, 2), "model_calls": state["model_calls"],
                  "tool_calls": state["tool_calls"], "skills_loaded": sorted(state["loaded_skills"]),
                  "human_decisions": "evaluation_simulated_human", "artifacts": str(destination.relative_to(root)) if destination.is_relative_to(root) else str(destination)}
        write_json(destination / "evaluation.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return result
    finally:
        if hasattr(client, "close"):
            client.close()


def coverage(output: Path) -> dict:
    records = {}
    from .skill_registry import SkillRegistry
    for skill in SkillRegistry(project_root() / "skills").catalog():
        records[skill["name"]] = {"loaded": [], "model_declared_artifacts": [], "candidate_links": []}
    for trace in sorted(output.glob("*/trace.jsonl")):
        for line in trace.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            name = entry.get("skill_id")
            if name not in records:
                continue
            evidence = {"case": trace.parent.name, "trace": str(trace.relative_to(output)), "event_seq": entry["seq"]}
            if entry["kind"] == "skill_loaded":
                records[name]["loaded"].append(evidence)
            elif entry["kind"] == "skill_application":
                key = "model_declared_artifacts" if entry["attribution"] == "model_declared" else "candidate_links"
                records[name][key].append({**evidence, "tool": entry["tool"], "artifact_event_seq": entry["artifact_event_seq"]})
    report = {"note": "加载、模型声明与候选关联分别统计。候选关联不等于证明技能有效，须结合对应产物审阅。Mock与live输出目录分离。", "skills": records}
    write_json(output / "skill_coverage.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["live", "mock"], required=True)
    parser.add_argument("--cases", default="normal,missing_info,no_materials,tool_failure,duration_revision,too_short,conflict,brand_and_fact_revision,human_feedback,headphones,tutorial,query_rewrite,step_limit,minimal")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--simulate-human", action="store_true", required=True, help="明确授权评估器模拟审核回复，记录不会冒充真实人工批准")
    options = parser.parse_args()
    output = (options.output or project_root() / "examples" / options.mode).resolve()
    output.mkdir(parents=True, exist_ok=True)
    existing_modes = {read_json(p).get("mode") for p in output.glob("*/evaluation.json")}
    if existing_modes - {options.mode}:
        raise ValueError("评估目录已有另一模式的记录，请使用独立目录，不能混合 Mock 与真实证据。")
    for case in options.cases.split(","):
        case = case.strip()
        if not case or not all(c.isalnum() or c == "_" for c in case):
            raise ValueError("Invalid case name")
        run_case(case, options.mode, output)
    results = [read_json(p) for p in sorted(output.glob("*/evaluation.json"))]
    write_json(output / "summary.json", {"mode": options.mode, "human_decisions": "evaluation_simulated_human", "cases": results,
                                        "passed": sum(r["acceptance_passed"] for r in results), "total": len(results)})
    coverage(output)
    if any(not result["acceptance_passed"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
