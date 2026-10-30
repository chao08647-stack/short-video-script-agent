import copy
import json
from pathlib import Path

import pytest

from script_agent.engine import checks_current, fingerprint
from script_agent.mock_model import MockModel
from script_agent.model import ModelError
from script_agent.runtime import Runtime


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def run_request():
    return {"brief": {"topic": "小剪自动字幕功能", "audience": "剪辑新手", "platform": "抖音", "target_seconds": 30.0, "style": "轻松直白"}, "dataset": "demo"}


@pytest.fixture
def runtime(tmp_path):
    return Runtime(MockModel(), tmp_path / "runs", ROOT)


def approve(runtime, state):
    return runtime.resume(state["run_id"], "approve", review_id=state["pending_review"]["review_id"], actor="evaluation_simulated_human")


def tool_events(state, name):
    return [e for e in state["events"] if e["kind"] == "tool_result" and e.get("tool") == name]


def test_three_review_gates_survive_new_runtime_instances(tmp_path, run_request):
    runs = tmp_path / "runs"
    runtime = Runtime(MockModel(), runs, ROOT)
    state = runtime.start(run_request, mode="mock")
    run_id = state["run_id"]
    assert state["status"] == "waiting_human"
    assert state["pending_review"]["stage"] == "direction"
    assert state["mode"] == "mock"
    for expected in ("draft", "final"):
        before_calls = state["model_calls"]
        runtime = Runtime(MockModel(), runs, ROOT)
        assert runtime.get(run_id)["pending_review"] == state["pending_review"]
        state = approve(runtime, state)
        assert state["status"] == "waiting_human"
        assert state["pending_review"]["stage"] == expected
        assert state["model_calls"] > before_calls
    before_events = len(state["events"])
    runtime = Runtime(MockModel(), runs, ROOT)
    state = approve(runtime, state)
    assert state["status"] == "completed"
    assert state["completed_script_hash"] == fingerprint(state["script"])
    assert len(state["review_history"]) == 3
    assert all(e["actor"] == "evaluation_simulated_human" for e in state["review_history"])
    assert len(state["events"]) == before_events + 2  # human decision, completion; no repeated tools
    assert checks_current(state)


def test_direction_revision_gets_new_version_and_rejects_stale_review(runtime, run_request):
    state = runtime.start(run_request, mode="mock")
    old = state["pending_review"]["review_id"]
    original_direction = copy.deepcopy(state["direction"])
    updated = runtime.resume(state["run_id"], "revise", feedback="调整为更直接的功能介绍。", review_id=old)
    assert updated["direction_version"] == state["direction_version"] + 1
    assert updated["direction"] != original_direction
    assert updated["pending_review"]["stage"] == "direction"
    with pytest.raises(ValueError, match="旧版本|当前 review-id"):
        runtime.resume(state["run_id"], "approve", review_id=old)
    assert runtime.get(state["run_id"])["model_calls"] == updated["model_calls"]


def test_final_revision_rechecks_new_version_and_exports_pending_status(runtime, run_request, tmp_path):
    state = runtime.start(run_request, mode="mock")
    state = approve(runtime, state)
    state = approve(runtime, state)
    assert state["phase"] == "final"
    previous_version = state["script_version"]
    previous_hash = state["checks"]["duration"]["script_hash"]
    updated = runtime.resume(state["run_id"], "revise", feedback="删掉开场，直接介绍功能。", review_id=state["pending_review"]["review_id"])
    assert updated["status"] == "waiting_human"
    assert updated["script_version"] > previous_version
    assert updated["checks"]["duration"]["script_hash"] != previous_hash
    assert all(c["script_version"] == updated["script_version"] for c in updated["checks"].values())
    assert checks_current(updated)
    assert "human-feedback" in updated["loaded_skills"]
    runtime.export(state["run_id"], tmp_path / "export")
    output = json.loads((tmp_path / "export" / "output.json").read_text(encoding="utf-8"))
    assert output["status"] == "waiting_human"
    assert (tmp_path / "export" / "trace.jsonl").exists()
    assert (tmp_path / "export" / "script_versions.json").exists()


def test_duplicate_approve_does_not_execute_again(runtime, run_request):
    state = runtime.start(run_request, mode="mock")
    old_review = state["pending_review"]["review_id"]
    updated = approve(runtime, state)
    count = updated["model_calls"]
    with pytest.raises(ValueError):
        runtime.resume(state["run_id"], "approve", review_id=old_review)
    assert runtime.get(state["run_id"])["model_calls"] == count


def test_cancel_preserves_existing_draft(runtime, run_request):
    state = approve(runtime, runtime.start(run_request, mode="mock"))
    draft = copy.deepcopy(state["script"])
    state = runtime.resume(state["run_id"], "cancel", review_id=state["pending_review"]["review_id"])
    assert state["status"] == "cancelled"
    assert state["script"] == draft
    with pytest.raises(ValueError, match="没有待处理"):
        runtime.resume(state["run_id"], "approve", review_id="old")


def test_model_budget_is_not_reset_on_resume(runtime, run_request):
    run_request["max_model_calls"] = 5
    state = runtime.start(run_request, mode="mock")
    assert state["status"] == "waiting_human"
    assert state["model_calls"] == 5
    state = approve(runtime, state)
    assert state["status"] == "incomplete"
    assert state["model_calls"] == 5
    assert state["stop_reason"]["code"] == "model_call_limit"


def test_tool_budget_returns_explicit_incomplete(runtime, run_request):
    run_request["max_tool_calls"] = 2
    state = runtime.start(run_request, mode="mock")
    assert state["status"] == "incomplete"
    assert state["tool_calls"] == 2
    assert state["stop_reason"]["code"] == "tool_call_limit"


def test_missing_brief_pauses_for_reply_and_does_not_accept_approval(runtime, run_request):
    del run_request["brief"]["target_seconds"]
    state = runtime.start(run_request, mode="mock")
    assert state["pending_review"]["stage"] == "clarification"
    with pytest.raises(ValueError, match="reply 或 cancel"):
        approve(runtime, state)
    state = runtime.resume(state["run_id"], "reply", answers={"target_seconds": 30.0}, review_id=state["pending_review"]["review_id"])
    assert state["brief"]["target_seconds"] == 30.0
    assert state["pending_review"]["stage"] == "direction"


def test_empty_materials_asks_for_help_without_inventing_script(runtime, run_request):
    run_request["dataset"] = "empty"
    state = runtime.start(run_request, mode="mock")
    assert state["status"] == "waiting_human"
    assert state["pending_review"]["stage"] == "clarification"
    assert state["script"] is None
    assert len(tool_events(state, "search_materials")) == 2
    assert "query-rewrite" in state["loaded_skills"]


def test_injected_tool_failure_is_recorded_then_recovered(runtime, run_request):
    run_request["failure_injections"] = {"search_materials": 1}
    state = runtime.start(run_request, mode="mock")
    searches = tool_events(state, "search_materials")
    assert len(searches) == 2
    assert searches[0]["result"]["ok"] is False
    assert "INJECTED_FAILURE" in searches[0]["result"]["error"]
    assert searches[1]["result"]["matches"]
    assert state["pending_review"]["stage"] == "direction"


def long_script():
    quote = "小剪 App 支持自动生成字幕。"
    return {"title": "字幕功能", "scenes": [{"scene_id": "S1", "visual": "展示产品资料中的功能文字。", "narration": quote * 20, "subtitle": quote, "source_ids": ["P01"], "min_display_seconds": 1.0}], "claims": [{"text": quote, "source_id": "P01", "quote": quote, "scene_id": "S1"}]}


def test_user_provided_overlong_draft_is_revised_after_observation(runtime, run_request):
    run_request["initial_script"] = long_script()
    state = approve(runtime, runtime.start(run_request, mode="mock"))
    assert state["checks"]["duration"]["passed"] is False
    assert state["script_version"] == 1
    state = approve(runtime, state)
    assert state["pending_review"]["stage"] == "final"
    assert state["script_version"] > 1
    timings = tool_events(state, "estimate_duration")
    assert timings[0]["result"]["passed"] is False
    assert timings[-1]["result"]["passed"] is True
    assert timings[-1]["result"]["estimated_seconds"] < timings[0]["result"]["estimated_seconds"]
    assert "duration-compression" in state["loaded_skills"]
    assert state["events"][0]["initial_script_provided"] is True


def test_unachievable_duration_stops_without_final_approval(runtime, run_request):
    run_request["brief"]["target_seconds"] = 0.5
    state = approve(runtime, runtime.start(run_request, mode="mock"))
    state = approve(runtime, state)
    assert state["status"] == "incomplete"
    assert state["checks"]["duration"]["passed"] is False
    assert not any(r["stage"] == "final" for r in state["review_history"])


def test_provider_error_never_switches_to_mock(tmp_path, run_request):
    class FailingModel:
        def chat(self, messages, tools):
            raise ModelError("offline endpoint")

    runtime = Runtime(FailingModel(), tmp_path / "runs", ROOT)
    state = runtime.start(run_request, mode="live")
    assert state["status"] == "failed"
    assert state["mode"] == "live"
    assert state["model_calls"] == 1
    assert state["stop_reason"]["code"] == "model_unavailable"


def test_final_gate_cannot_be_bypassed_by_requesting_review(runtime, run_request):
    class PrematureFinal(MockModel):
        def chat(self, messages, tools=None):
            if self.state.get("phase") == "final":
                return self._action("request_review", reason="attempt to bypass failed checks")
            return super().chat(messages, tools)

    runtime.engine.model = PrematureFinal()
    run_request["initial_script"] = long_script()
    run_request["max_model_calls"] = 20
    state = approve(runtime, runtime.start(run_request, mode="mock"))
    state = approve(runtime, state)
    assert state["status"] == "incomplete"
    rejections = [e for e in tool_events(state, "request_review") if e["result"].get("ok") is False]
    assert rejections
    assert "终稿审核要求" in rejections[0]["result"]["error"]


def test_dataset_path_traversal_is_rejected(runtime, run_request):
    run_request["dataset"] = "../../outside"
    with pytest.raises(ValueError, match="data"):
        runtime.start(run_request, mode="mock")
