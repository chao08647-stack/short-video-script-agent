import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def invoke(runs, *arguments):
    env = {**os.environ, "PYTHONUTF8": "1"}
    result = subprocess.run([sys.executable, "-m", "script_agent", "--runs-dir", str(runs), *arguments],
                            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_cli_three_gates_across_separate_processes(tmp_path):
    runs = tmp_path / "runs"
    state = json.loads(invoke(runs, "run", "--input", "examples/inputs/normal.json", "--mode", "mock", "--json"))
    for stage in ("direction", "draft", "final"):
        queried = json.loads(invoke(runs, "review", "--run-id", state["run_id"], "--json"))
        assert queried["pending_review"]["stage"] == stage
        state = json.loads(invoke(runs, "resume", "--run-id", state["run_id"], "--review-id",
                                  queried["pending_review"]["review_id"], "--decision", "approve", "--json"))
    assert state["status"] == "completed"
    assert state["mode"] == "mock"
    target = tmp_path / "export"
    invoke(runs, "export", "--run-id", state["run_id"], "--output", str(target))
    assert json.loads((target / "output.json").read_text(encoding="utf-8"))["status"] == "completed"
    assert "小剪" in (target / "script.md").read_text(encoding="utf-8")
