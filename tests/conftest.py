"""Keep temporary test artifacts in this workspace, including on Windows."""
from pathlib import Path
import uuid


def pytest_configure(config):
    if config.option.basetemp is None:
        parent = Path(__file__).resolve().parents[1] / ".runs" / "pytest"
        parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(parent / str(uuid.uuid4()))
    else:
        Path(config.option.basetemp).parent.mkdir(parents=True, exist_ok=True)
