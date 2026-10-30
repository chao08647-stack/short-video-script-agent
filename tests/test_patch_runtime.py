"""Patch integration preserves revision/check/review and exported-artifact boundaries."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from script_agent.engine import checks_current, fingerprint
from script_agent.mock_model import MockModel
from script_agent.runtime import Runtime, read_json


ROOT = Path(__file__).resolve().parents[1]


class PatchFeedbackModel(MockModel):
    """Offline driver chooses a local title edit after human revision feedback."""

    def chat(self, messages, tools=None):
        if self.state.get("revision_required") and self.state["phase"] == "final":
            self.request_count += 1
            load = self._load("human-feedback")
            return load or self._action(
                "patch_script",
                edits=[{"op": "replace", "path": "/title", "value": self.state["script"]["title"] + "（修改版）"}],
                used_skills=["human-feedback"], reason="Offline fixture: apply the requested title edit",
            )
        return super().chat(messages, tools)


@pytest.fixture
def pending_final(tmp_path):
    runtime = Runtime(PatchFeedbackModel(), tmp_path / "runs", ROOT)
    state = runtime.start(read_json(ROOT / "examples" / "inputs" / "normal.json"), mode="mock")
    for _ in range(2):
        state = runtime.resume(state["run_id"], "approve", review_id=state["pending_review"]["review_id"],
                               actor="evaluation_simulated_human")
    assert state["pending_review"]["stage"] == "final"
    assert checks_current(state)
    return runtime, state


def run_tool(runtime, original, tool, **arguments):
    state = deepcopy(original)
    arguments.setdefault("reason", "Exercise patch integration boundary")
    state["pending_calls"] = [{"id": f"patch-integration-{state['tool_calls']}", "type": "function", "function": {
        "name": tool, "arguments": json.dumps(arguments, ensure_ascii=False),
    }}]
    updated = runtime.engine.tools(state)
    return updated, json.loads(updated["messages"][-1]["content"])


def approval(state):
    return {"review_id": state["pending_review"]["review_id"], "decision": "approve", "feedback": "",
            "answers": {}, "actor": "evaluation_simulated_human"}


def test_patch_invalidates_old_checks_and_approval_and_requires_both_rechecks(pending_final):
    runtime, original = pending_final
    old_approval = approval(original)
    patched, result = run_tool(runtime, original, "patch_script", used_skills=["claim-grounding"],
                               edits=[{"op": "replace", "path": "/title", "value": "字幕功能介绍（更新）"}])
    assert result["ok"] is True
    assert patched["script_version"] == original["script_version"] + 1
    assert patched["checks"] == {}
    assert checks_current(patched) is False
    assert checks_current(original) is True

    stale = runtime.engine.apply_review({**patched, "human_response": old_approval})
    assert stale["status"] == "failed"
    assert stale["stop_reason"]["code"] == "stale_approval"
    with pytest.raises(ValueError, match="全部通过"):
        runtime.engine.execute(patched, "request_review", {"reason": "Try old passing checks"})

    timed, timing = run_tool(runtime, patched, "estimate_duration")
    assert timing["passed"] is True
    with pytest.raises(ValueError, match="全部通过"):
        runtime.engine.execute(timed, "request_review", {"reason": "Timing alone cannot approve facts"})
    checked, rules = run_tool(runtime, timed, "check_rules")
    assert rules["passed"] is True
    assert checks_current(checked)
    runtime.engine.execute(checked, "request_review", {"reason": "Both current-version checks passed"})
    assert checked["pending_review"]["review_id"] != old_approval["review_id"]
    completed = runtime.engine.apply_review({**checked, "human_response": approval(checked)})
    assert completed["status"] == "completed"
    assert completed["completed_script_hash"] == fingerprint(patched["script"])


def test_failed_patch_keeps_script_version_checks_and_pending_review(pending_final):
    runtime, original = pending_final
    failed, result = run_tool(runtime, original, "patch_script", used_skills=["claim-grounding"], edits=[
        {"op": "replace", "path": "/title", "value": "Must roll back this intermediate edit"},
        {"op": "replace", "path": "/scenes/0/min_display_seconds", "value": "0"},
    ])
    assert result["ok"] is False
    assert "edits[1]" in result["error"]
    for key in ("script", "script_version", "checks", "pending_review", "review_history"):
        assert failed[key] == original[key]
    assert failed["tool_calls"] == original["tool_calls"] + 1
    assert failed["model_calls"] == original["model_calls"]
    assert checks_current(failed)


def test_runtime_patch_revision_exports_edits_and_the_complete_new_script(pending_final, tmp_path):
    runtime, original = pending_final
    old_review_id = original["pending_review"]["review_id"]
    revised = runtime.resume(original["run_id"], "revise", feedback="请在标题末尾加上（修改版）。",
                             review_id=old_review_id, actor="evaluation_simulated_human")
    assert revised["status"] == "waiting_human"
    assert revised["pending_review"]["stage"] == "final"
    assert revised["script_version"] == original["script_version"] + 1
    assert checks_current(revised)
    with pytest.raises(ValueError, match="旧版本|当前 review-id"):
        runtime.resume(original["run_id"], "approve", review_id=old_review_id)

    destination = tmp_path / "export"
    runtime.export(revised["run_id"], destination)
    versions = read_json(destination / "script_versions.json")
    patch_versions = [version for version in versions if version.get("tool") == "patch_script"]
    assert len(patch_versions) == 1
    patch = patch_versions[0]
    assert patch["version"] == revised["script_version"]
    assert patch["script"] == revised["script"]
    assert patch["arguments"]["edits"] == [
        {"op": "replace", "path": "/title", "value": revised["script"]["title"]},
    ]
    assert patch["script"]["scenes"] == original["script"]["scenes"]
    assert patch["script"]["claims"] == original["script"]["claims"]
    trace = [json.loads(line) for line in (destination / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    artifact = next(event for event in trace if event["seq"] == patch["event_seq"])
    assert artifact["tool"] == "patch_script"
    assert artifact["result"]["script"] == patch["script"]
    assert artifact["result"]["script_hash"] == fingerprint(patch["script"])
    assert read_json(destination / "output.json")["script"] == patch["script"]
