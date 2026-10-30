import json
from pathlib import Path

from script_agent.mock_model import MockModel
from script_agent.prompts import build_messages
from script_agent.runtime import Runtime, _EXECUTED_CODE_HASHES
from script_agent.model import ContextLimitError


def test_execution_source_snapshot_is_not_relabelled_after_disk_changes(tmp_path, monkeypatch):
    original = Path.read_text

    def changed_source(path, *args, **kwargs):
        if path.name == "prompts.py":
            return "new source that the running process has not imported"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", changed_source)
    state = Runtime(MockModel(), tmp_path / "runs").start({"brief": {}}, "mock")
    assert state["execution"]["code_hash_capture"] == "process_import"
    assert state["execution"]["code_hashes"] == _EXECUTED_CODE_HASHES


def test_failed_search_is_never_projected_as_an_empty_search():
    state = {"messages": [
        {"role": "assistant", "tool_calls": [{"id": "a", "type": "function", "function": {
            "name": "search_materials", "arguments": '{"query":"小剪","reason":"find evidence"}'}}]},
        {"role": "tool", "tool_call_id": "a", "content": '{"ok":false,"error":"temporary failure"}'},
    ]}
    messages = build_messages(state, [])
    observed = json.loads(next(m["content"] for m in messages if m["role"] == "tool"))
    assert observed["observation_status"] == "tool_error_not_empty_search"
    assert "matched_source_ids" not in observed
    assert observed["error"] == "temporary failure"


def test_context_limit_stops_incomplete_without_running_tools(tmp_path):
    class LimitedModel(MockModel):
        last_response_metadata = {"context_budget": {"context_window": 16384, "accepted": False}}

        def chat(self, messages, tools=None):
            raise ContextLimitError("Context budget exceeded before HTTP request")

    state = Runtime(LimitedModel(), tmp_path / "runs").start({"brief": {}}, "mock")
    assert state["status"] == "incomplete"
    assert state["stop_reason"]["code"] == "context_budget_exceeded"
    assert state["tool_calls"] == 0
    error = next(e for e in state["events"] if e["kind"] == "model_error")
    assert error["response_metadata"]["context_budget"]["accepted"] is False


def test_verifier_context_limit_preserves_draft_and_stops(tmp_path):
    class LimitedVerifier(MockModel):
        def verify_script(self, script, materials):
            raise ContextLimitError("Verifier input exceeds context budget")

    runtime = Runtime(LimitedVerifier(), tmp_path / "runs")
    request = json.loads((Path(__file__).resolve().parents[1] / "examples/inputs/normal.json").read_text(encoding="utf-8"))
    state = runtime.start(request, "mock")
    assert state["pending_review"]["stage"] == "direction"
    state = runtime.resume(state["run_id"], "approve", review_id=state["pending_review"]["review_id"], actor="evaluation_simulated_human")
    assert state["status"] == "incomplete"
    assert state["stop_reason"]["code"] == "context_budget_exceeded"
    assert state["script"]
    assert state["checks"]["rules"]["passed"] is False


def test_verifier_actual_usage_overflow_exports_semantic_failure_evidence(tmp_path):
    class OverBudgetVerifier(MockModel):
        private_reasoning = "PRIVATE_REASONING_MUST_NOT_BE_EXPORTED"

        def verify_script(self, script, materials):
            self.request_count += 1
            self.last_request_count = 1
            self.last_usage = {"prompt_tokens": 16000, "completion_tokens": 500, "total_tokens": 16500}
            self.last_response_metadata = {
                "context_budget": {"estimate_only": True, "context_window": 16384, "within_budget": True},
                "context_usage_check": {
                    "phase": "response_usage", "request_sent": True, "context_window": 16384,
                    "observed_total_tokens": 16500, "exceeded": True,
                },
                "public_response": '{"passed":false,"issues":[],"claims":[]}',
            }
            raise ContextLimitError("Context budget exceeded after HTTP: provider reported 16500 input + output tokens")

    model = OverBudgetVerifier()
    runtime = Runtime(model, tmp_path / "runs")
    request = json.loads((Path(__file__).resolve().parents[1] / "examples/inputs/normal.json").read_text(encoding="utf-8"))
    state = runtime.start(request, "mock")
    state = runtime.resume(state["run_id"], "approve", review_id=state["pending_review"]["review_id"],
                           actor="evaluation_simulated_human")
    assert state["status"] == "incomplete"
    assert state["stop_reason"]["code"] == "context_budget_exceeded"
    assert state["script"] and state["checks"]["rules"]["passed"] is False
    error = next(event for event in state["events"] if event["kind"] == "semantic_error")
    assert error["usage"] == model.last_usage
    assert error["response_metadata"] == model.last_response_metadata
    assert error["model_call"] == state["model_calls"]
    assert error["response_metadata"]["context_usage_check"]["request_sent"] is True
    trace_text = (runtime.runs_dir / state["run_id"] / "trace.jsonl").read_text(encoding="utf-8")
    exported = [json.loads(line) for line in trace_text.splitlines()]
    assert next(event for event in exported if event["kind"] == "semantic_error") == error
    assert model.private_reasoning not in trace_text
