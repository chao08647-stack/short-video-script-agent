import json
from pathlib import Path

from script_agent.mock_model import MockModel
from script_agent.prompts import build_messages
from script_agent.runtime import Runtime, _EXECUTED_CODE_HASHES


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
