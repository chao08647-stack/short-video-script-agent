"""Human clarification must survive later model/tool turns and process restart."""
import json
from pathlib import Path

from script_agent.mock_model import MockModel
from script_agent.prompts import build_messages
from script_agent.runtime import Runtime


def test_clarification_survives_tools_and_restart(tmp_path):
    runtime = Runtime(MockModel(), tmp_path / "runs")
    state = runtime.start({"brief": {"topic": "小剪字幕", "platform": "抖音"}} , mode="mock")
    note = "开场先说明字幕需求，不要提问，保持真实功能描述。"
    state = runtime.resume(state["run_id"], "reply", feedback=note,
                           answers={"audience": "剪辑新手", "target_seconds": 30.0, "style": "直白"},
                           review_id=state["pending_review"]["review_id"])
    assert state["pending_review"]["stage"] == "direction"
    # Several tools have executed since reply; the latest history is no longer human.
    assert state["messages"][-1]["role"] == "tool"
    restored = Runtime(MockModel(), tmp_path / "runs").get(state["run_id"])
    assert note in json.dumps(build_messages(restored, runtime.registry.catalog()), ensure_ascii=False)
    assert restored["brief"]["target_seconds"] == 30.0
