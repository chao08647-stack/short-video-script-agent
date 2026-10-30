"""Regression checks for approval races, stale checks, and malformed actions.

MockModel is used only as a deterministic driver. State checkpoints and review
interrupts run through the actual LangGraph/SQLite implementation.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from script_agent.engine import checks_current, fingerprint
from script_agent.locking import run_lock
from script_agent.mock_model import MockModel
from script_agent.runtime import Runtime


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def request_data():
    return {
        "brief": {
            "topic": "小剪自动字幕功能",
            "audience": "剪辑新手",
            "platform": "抖音",
            "target_seconds": 30.0,
            "style": "轻松直白",
        },
        "dataset": "demo",
    }


@pytest.fixture
def runtime(tmp_path):
    return Runtime(MockModel(), tmp_path / "runs", ROOT)


def approve(runtime, state):
    return runtime.resume(
        state["run_id"],
        "approve",
        review_id=state["pending_review"]["review_id"],
        actor="evaluation_simulated_human",
    )


@pytest.fixture
def pending_final(runtime, request_data):
    state = runtime.start(request_data, mode="mock")
    state = approve(runtime, state)
    state = approve(runtime, state)
    assert state["pending_review"]["stage"] == "final"
    assert checks_current(state)
    return runtime, state


def approval_response(state):
    return {
        "review_id": state["pending_review"]["review_id"],
        "decision": "approve",
        "feedback": "",
        "answers": {},
        "actor": "evaluation_simulated_human",
    }


def run_tool(engine, state, name, arguments):
    state = copy.deepcopy(state)
    state["pending_calls"] = [{
        "id": "integrity-regression-call",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }]
    result = engine.tools(state)
    observation = json.loads(result["messages"][-1]["content"])
    return result, observation


def test_run_lock_rejects_another_descriptor_and_releases_after_exception(tmp_path):
    with pytest.raises(RuntimeError, match="test interrupted work"):
        with run_lock(tmp_path, "same-task"):
            with pytest.raises(ValueError, match="另一进程"):
                with run_lock(tmp_path, "same-task"):
                    pytest.fail("a second descriptor acquired the same task lock")
            # Different tasks are independent; a global lock would be excessive.
            with run_lock(tmp_path, "different-task"):
                pass
            raise RuntimeError("test interrupted work")
    with run_lock(tmp_path, "same-task"):
        pass


def test_run_lock_is_visible_to_another_process(tmp_path):
    code = """
from pathlib import Path
import sys
from script_agent.locking import run_lock
try:
    with run_lock(Path(sys.argv[1]), sys.argv[2]):
        print('acquired')
except ValueError:
    print('blocked')
"""
    command = [sys.executable, "-c", code, str(tmp_path), "cross-process-task"]
    with run_lock(tmp_path, "cross-process-task"):
        blocked = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
        assert blocked.stdout.strip() == "blocked", blocked.stderr
    available = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
    assert available.stdout.strip() == "acquired", available.stderr


def test_resume_lock_conflict_does_not_consume_review_or_call_model(runtime, request_data):
    state = runtime.start(request_data, mode="mock")
    before_calls = runtime.engine.model.request_count
    pending = copy.deepcopy(state["pending_review"])
    with run_lock(runtime.runs_dir, state["run_id"]):
        with pytest.raises(ValueError, match="另一进程"):
            approve(runtime, state)
    retained = runtime.get(state["run_id"])
    assert retained["pending_review"] == pending
    assert retained["review_history"] == []
    assert runtime.engine.model.request_count == before_calls
    resumed = approve(runtime, retained)
    assert resumed["pending_review"]["stage"] == "draft"


@pytest.mark.parametrize("mutation", ["response_id", "version", "content"])
def test_apply_review_rechecks_binding_even_after_runtime_validation(pending_final, mutation):
    runtime, original = pending_final
    state = copy.deepcopy(original)
    state["human_response"] = approval_response(state)
    if mutation == "response_id":
        state["human_response"]["review_id"] = "earlier-stage-review"
    elif mutation == "version":
        state["script_version"] += 1
    else:
        state["script"]["title"] += "（外部改动）"
    result = runtime.engine.apply_review(state)
    assert result["status"] == "failed"
    assert result["stop_reason"]["code"] == "stale_approval"
    assert result["review_history"] == original["review_history"]
    assert not any(event["kind"] == "completed" for event in result["events"])
    # The regression probe did not write its corrupted snapshot to persistence.
    assert runtime.get(original["run_id"])["pending_review"] == original["pending_review"]


@pytest.mark.parametrize("mutation", ["target_seconds", "audience", "material_snapshot"])
def test_previously_passing_reports_expire_when_brief_or_data_changes(pending_final, mutation):
    runtime, original = pending_final
    state = copy.deepcopy(original)
    if mutation == "material_snapshot":
        state["materials"][0]["text"] = "该产品不再支持自动生成字幕。"
        state["data_hash"] = fingerprint({"materials": state["materials"], "rules": state["rules"]})
    elif mutation == "target_seconds":
        state["brief"]["target_seconds"] = 1.0
    else:
        state["brief"]["audience"] = "专业剪辑师"
    assert all(report["passed"] is True for report in state["checks"].values())
    assert checks_current(state) is False
    assert checks_current(state, require_pass=False) is False
    with pytest.raises(ValueError, match="当前版本"):
        runtime.engine.execute(state, "request_review", {"reason": "尝试使用旧报告。"})
    state["human_response"] = approval_response(state)
    result = runtime.engine.apply_review(state)
    assert result["status"] == "failed"
    assert result["stop_reason"]["code"] == "stale_approval"


def test_repeating_old_approval_after_stage_transition_keeps_new_gate_pending(runtime, request_data):
    first = runtime.start(request_data, mode="mock")
    old_review_id = first["pending_review"]["review_id"]
    second = approve(runtime, first)
    assert second["pending_review"]["stage"] == "draft"
    before_calls = runtime.engine.model.request_count
    with pytest.raises(ValueError, match="review-id|旧版本"):
        runtime.resume(first["run_id"], "approve", review_id=old_review_id)
    unchanged = runtime.get(first["run_id"])
    assert unchanged["pending_review"] == second["pending_review"]
    assert unchanged["review_history"] == second["review_history"]
    assert runtime.engine.model.request_count == before_calls


def test_direction_revision_cannot_be_acknowledged_with_identical_direction(runtime, request_data):
    state = runtime.start(request_data, mode="mock")
    state["human_response"] = {
        **approval_response(state),
        "decision": "revise",
        "feedback": "换一个开场角度。",
    }
    waiting_for_change = runtime.engine.apply_review(state)
    assert waiting_for_change["revision_required"] is True
    arguments = {
        **state["direction"],
        "used_skills": ["audience-angle"],
        "reason": "提交完全相同的内容以触发回归检查。",
    }
    result, observation = run_tool(runtime.engine, waiting_for_change, "submit_direction", arguments)
    assert observation["ok"] is False
    assert "没有变化" in observation["error"]
    assert result["revision_required"] is True
    assert result["direction_version"] == state["direction_version"]
    assert result["direction"] == state["direction"]


@pytest.mark.parametrize("used_skills", [[{}], [1], "audience-angle", ["not-loaded-skill"]])
def test_invalid_skill_metadata_returns_tool_error_without_mutating_direction(runtime, request_data, used_skills):
    state = runtime.start(request_data, mode="mock")
    arguments = {**state["direction"], "reason": "验证工具元数据边界。", "used_skills": used_skills}
    result, observation = run_tool(runtime.engine, state, "submit_direction", arguments)
    assert observation["ok"] is False
    assert observation["recoverable"] is True
    assert result["direction"] == state["direction"]
    assert result["direction_version"] == state["direction_version"]
    assert result["pending_review"] == state["pending_review"]
    assert result["tool_calls"] == state["tool_calls"] + 1
    assert result["events"][-1]["kind"] == "tool_result"


@pytest.mark.parametrize("reason", [None, 10, "", "   "])
def test_invalid_reason_is_rejected_before_tool_execution(runtime, request_data, reason):
    state = runtime.start(request_data, mode="mock")
    result, observation = run_tool(runtime.engine, state, "search_materials", {"query": "字幕", "reason": reason})
    assert observation["ok"] is False
    assert "reason" in observation["error"]
    assert result["retrieved_materials"] == state["retrieved_materials"]


def test_injection_schedule_is_not_exposed_in_initial_model_messages(tmp_path, request_data):
    class RecordingMock(MockModel):
        def __init__(self):
            super().__init__()
            self.observed_messages = []

        def chat(self, messages, tools=None):
            self.observed_messages.append(copy.deepcopy(messages))
            return super().chat(messages, tools)

    model = RecordingMock()
    runtime = Runtime(model, tmp_path / "runs", ROOT)
    request_data["failure_injections"] = {"search_materials": 1}
    state = runtime.start(request_data, mode="mock")
    first_request = json.dumps(model.observed_messages[0], ensure_ascii=False)
    assert "failure_injections" not in first_request
    assert "failure_remaining" not in first_request
    assert "INJECTED_FAILURE" not in first_request
    # The model may learn about the failure only after the tool actually returns it.
    assert any("INJECTED_FAILURE" in json.dumps(messages) for messages in model.observed_messages[1:])
    assert any(
        event["kind"] == "tool_result"
        and event.get("tool") == "search_materials"
        and event["result"].get("ok") is False
        for event in state["events"]
    )
