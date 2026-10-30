"""Acceptance labels require observable paths, not only a completed status."""

import copy
import json
from pathlib import Path

import pytest

from script_agent.engine import checks_current, fingerprint
from script_agent.evaluate import acceptance, coverage
from script_agent.mock_model import MockModel
from script_agent.model import ModelError
from script_agent.runtime import Runtime, read_json


ROOT = Path(__file__).resolve().parents[1]


def run_mock_case(tmp_path, case, model=None):
    runtime = Runtime(model or MockModel(), tmp_path / case, ROOT)
    state = runtime.start(read_json(ROOT / "examples" / "inputs" / f"{case}.json"), mode="mock")
    feedback_sent = False
    for _ in range(12):
        if state["status"] != "waiting_human":
            break
        pending = state["pending_review"]
        if pending["stage"] == "clarification":
            if case != "missing_info":
                break
            defaults = {"audience": "剪辑新手", "platform": "抖音", "target_seconds": 30.0, "style": "轻松直白"}
            answers = {key: value for key, value in defaults.items() if state["brief"].get(key) is None}
            state = runtime.resume(state["run_id"], "reply", answers=answers,
                                   review_id=pending["review_id"], actor="evaluation_simulated_human")
        elif case == "human_feedback" and pending["stage"] == "draft" and not feedback_sent:
            feedback_sent = True
            state = runtime.resume(state["run_id"], "revise", feedback="删掉开场反问，直接介绍字幕功能。",
                                   review_id=pending["review_id"], actor="evaluation_simulated_human")
        else:
            state = runtime.resume(state["run_id"], "approve", review_id=pending["review_id"],
                                   actor="evaluation_simulated_human")
    return runtime, state


@pytest.fixture
def completed(tmp_path):
    return run_mock_case(tmp_path, "normal")


@pytest.mark.parametrize("case", [
    "normal", "missing_info", "no_materials", "conflict", "too_short", "step_limit",
    "duration_revision", "brand_and_fact_revision", "human_feedback", "tool_failure",
])
def test_observed_mock_acceptance_paths_remain_valid(tmp_path, case):
    _, state = run_mock_case(tmp_path, case)
    passed, errors = acceptance(case, state)
    assert passed, errors


@pytest.mark.parametrize("case", [
    "human_feedback", "query_rewrite", "duration_revision", "brand_and_fact_revision", "tool_failure", "missing_info", "skill_showcase",
])
def test_normal_completion_cannot_be_relabelled_as_unobserved_special_path(completed, case):
    _, state = completed
    passed, errors = acceptance(case, state)
    assert passed is False
    assert errors


@pytest.mark.parametrize("field", ["narration", "subtitle"])
@pytest.mark.parametrize("question_mark", ["?", "？"])
def test_human_feedback_rejects_residual_opening_question_despite_renewed_review(tmp_path, field, question_mark):
    class PartialFeedbackModel(MockModel):
        """Offline regression for the observed narration-only live revision."""

        def _script(self, *, compact=False, revised=False):
            script = super()._script(compact=compact, revised=revised)
            if revised:
                opening = {"scene_id": "HOOK", "visual": "创作者准备字幕的情景。",
                           "narration": "剪完视频，需要字幕。", "subtitle": "剪完视频，需要字幕。",
                           "source_ids": [], "min_display_seconds": 1.0}
                opening[field] = "剪完还要一句句敲字幕" + question_mark
                script["scenes"].insert(0, opening)
            elif not compact:
                script["scenes"][0]["narration"] = "剪完还要一句句敲字幕" + question_mark
                script["scenes"][0]["subtitle"] = "剪完还要一句句敲字幕" + question_mark
            return script

    _, state = run_mock_case(tmp_path, "human_feedback", PartialFeedbackModel())
    assert state["status"] == "completed"
    assert checks_current(state)
    assert any(event.get("kind") == "human_decision" and event.get("decision") == "revise"
               for event in state["events"])
    passed, errors = acceptance("human_feedback", state)
    assert passed is False
    # A valid changed-version -> renewed-review path must not hide partial feedback.
    assert errors == [f"Opening {field} still contains a question mark after human feedback"]


@pytest.mark.parametrize("case", ["no_materials", "conflict", "too_short"])
def test_unrelated_budget_exhaustion_is_not_evidence_for_data_or_timing_failure(completed, case):
    _, original = completed
    state = copy.deepcopy(original)
    state.update(status="incomplete", stop_reason={"code": "model_call_limit", "message": "unrelated exhausted loop"})
    state["model_calls"] = state["max_model_calls"]
    passed, errors = acceptance(case, state)
    assert passed is False
    assert any("grounded clarification/stop" in error for error in errors)


def test_waiting_for_review_does_not_prove_limit_enforcement(completed):
    _, original = completed
    state = copy.deepcopy(original)
    state.update(status="waiting_human", pending_review={"stage": "direction"})
    passed, errors = acceptance("step_limit", state)
    assert passed is False
    assert any("execution limit" in error for error in errors)


@pytest.mark.parametrize("mutation", ["missing_submission", "missing_decision", "unchanged_version", "changed_target"])
def test_duration_path_requires_a_real_intervening_same_target_revision(tmp_path, mutation):
    _, state = run_mock_case(tmp_path, "duration_revision")
    timing_events = [event for event in state["events"]
                     if event.get("kind") == "tool_result" and event.get("tool") == "estimate_duration"]
    assert timing_events[0]["result"]["passed"] is False
    assert timing_events[-1]["result"]["passed"] is True
    if mutation == "missing_submission":
        state["events"] = [event for event in state["events"]
                           if not (event.get("kind") == "tool_result" and event.get("tool") == "submit_script")]
    elif mutation == "missing_decision":
        state["events"] = [event for event in state["events"] if event.get("kind") != "model_action"]
    elif mutation == "unchanged_version":
        timing_events[-1]["result"]["script_version"] = timing_events[0]["result"]["script_version"]
    else:
        timing_events[-1]["result"]["target_seconds"] += 100
    passed, errors = acceptance("duration_revision", state)
    assert passed is False
    assert any("same-target feedback path" in error for error in errors)


def test_query_rewrite_accepts_an_observed_empty_then_recovered_search(tmp_path):
    class EmptyFirstSearch(MockModel):
        """Scripted offline planner drives real retrieval observations for this test."""

        def chat(self, messages, tools=None):
            searches = [event for event in self.state["events"]
                        if event.get("kind") == "tool_result" and event.get("tool") == "search_materials"]
            if "material-search" in self.state["loaded_skills"] and not searches:
                self.request_count += 1
                return self._action("search_materials", query="unindexedword", reason="Offline first-query fixture")
            return super().chat(messages, tools)

    _, state = run_mock_case(tmp_path, "query_rewrite", EmptyFirstSearch())
    passed, errors = acceptance("query_rewrite", state)
    assert passed, errors


def test_skill_applications_all_point_to_the_actual_tool_artifact(completed):
    _, state = completed
    by_seq = {event["seq"]: event for event in state["events"]}
    applications = [event for event in state["events"] if event["kind"] == "skill_application"]
    assert any(event["attribution"] == "model_declared" for event in applications)
    for application in applications:
        artifact = by_seq[application["artifact_event_seq"]]
        assert artifact["kind"] == "tool_result"
        assert artifact["tool"] == application["tool"]
        assert fingerprint(artifact["result"]) == application["artifact_hash"]
        assert artifact["seq"] < application["seq"]


def test_coverage_does_not_promote_candidate_links_to_declared_application(tmp_path):
    directory = tmp_path / "case"
    directory.mkdir()
    events = [
        {"seq": 1, "kind": "skill_loaded", "skill_id": "material-search"},
        {"seq": 2, "kind": "tool_result", "tool": "search_materials", "result": {"matches": []}},
        {"seq": 3, "kind": "skill_application", "skill_id": "material-search", "attribution": "subsequent_action_candidate",
         "tool": "search_materials", "artifact_event_seq": 2},
    ]
    (directory / "trace.jsonl").write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
    report = coverage(tmp_path)
    record = report["skills"]["material-search"]
    assert len(record["loaded"]) == 1
    assert len(record["candidate_links"]) == 1
    assert record["model_declared_artifacts"] == []


def run_tool(runtime, original, name):
    state = copy.deepcopy(original)
    state["pending_calls"] = [{"id": "failure-boundary", "type": "function", "function": {
        "name": name, "arguments": json.dumps({"reason": "Test failure boundary"})}}]
    result = runtime.engine.tools(state)
    return result, json.loads(result["messages"][-1]["content"])


def test_check_failure_invalidates_old_pass_but_preserves_successful_draft(completed):
    runtime, original = completed
    state = copy.deepcopy(original)
    state["status"] = "running"
    state["failure_remaining"]["check_rules"] = 1
    before_verifications = runtime.engine.model.request_count
    result, observation = run_tool(runtime, state, "check_rules")
    assert observation["ok"] is False
    assert "INJECTED_FAILURE" in observation["error"]
    assert result["script"] == original["script"]
    assert result["script_version"] == original["script_version"]
    assert result["checks"]["duration"] == original["checks"]["duration"]
    assert result["checks"]["rules"]["passed"] is False
    assert checks_current(result) is False
    assert runtime.engine.model.request_count == before_verifications
    with pytest.raises(ValueError, match="全部通过"):
        runtime.engine.execute(result, "request_review", {"reason": "Old success must not survive a failed recheck"})


def test_semantic_verifier_error_is_counted_and_never_reuses_old_success(completed):
    runtime, original = completed

    class FailingVerifier(MockModel):
        def verify_script(self, script, materials):
            self.request_count += 1
            raise ModelError("Synthetic verifier outage")

    model = FailingVerifier()
    runtime.engine.model = model
    state = copy.deepcopy(original)
    state["status"] = "running"
    result, observation = run_tool(runtime, state, "check_rules")
    assert observation["passed"] is False
    assert any(issue["code"] == "semantic_unavailable" for issue in observation["issues"])
    assert result["model_calls"] == original["model_calls"] + 1
    assert model.request_count == 1
    assert result["script"] == original["script"]
    assert checks_current(result) is False


def test_semantic_check_cannot_spend_one_more_model_call_after_budget(completed):
    runtime, original = completed
    state = copy.deepcopy(original)
    state["status"] = "running"
    state["max_model_calls"] = state["model_calls"]
    before_requests = runtime.engine.model.request_count
    result, observation = run_tool(runtime, state, "check_rules")
    assert result["status"] == "incomplete"
    assert result["stop_reason"]["code"] == "model_call_limit"
    assert result["model_calls"] == state["max_model_calls"]
    assert runtime.engine.model.request_count == before_requests
    assert observation["passed"] is False
    assert result["script"] == original["script"]


def test_high_configured_budget_stops_explicitly_and_exports_incomplete(tmp_path):
    class LoopModel(MockModel):
        def chat(self, messages, tools=None):
            self.request_count += 1
            return self._action("load_skill", name="material-search", reason="Exercise a valid high call limit")

    request = read_json(ROOT / "examples" / "inputs" / "normal.json")
    request.update(max_model_calls=120, max_tool_calls=120)
    runs = tmp_path / "high-budget"
    runtime = Runtime(LoopModel(), runs, ROOT)
    state = runtime.start(request, mode="mock")
    assert state["status"] == "incomplete"
    assert state["stop_reason"]["code"] == "model_call_limit"
    assert state["model_calls"] == 120
    assert state["tool_calls"] == 120
    output = read_json(runs / state["run_id"] / "output.json")
    assert output["status"] == "incomplete"
    assert output["stop_reason"] == state["stop_reason"]
    assert output["model_calls"] == 120
    assert (runs / state["run_id"] / "trace.jsonl").is_file()
