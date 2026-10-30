"""OS advisory locks: released automatically if a CLI process crashes."""
from contextlib import contextmanager
from pathlib import Path
import os


@contextmanager
def run_lock(directory: Path, run_id: str):
    folder = directory / "locks"
    folder.mkdir(parents=True, exist_ok=True)
    stream = (folder / f"{run_id}.lock").open("a+b")
    locked = False
    try:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise ValueError("该任务正由另一进程处理，请等待后重新查看当前审核请求。") from exc
        yield
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()
