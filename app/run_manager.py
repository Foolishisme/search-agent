import shutil
import tempfile
import threading
from pathlib import Path
from uuid import uuid4


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, threading.Event] = {}

    def create(self) -> str:
        run_id = uuid4().hex
        with self._lock:
            self._runs[run_id] = threading.Event()
        return run_id

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            event = self._runs.get(run_id)
        if event is None:
            return False
        event.set()
        return True

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            event = self._runs.get(run_id)
        return event.is_set() if event else False

    def remove(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)


class SessionStateGuard:
    def __init__(self, session_id: str, session_store, attachment_store, artifact_store) -> None:
        self.session_id = session_id
        self._targets = [
            Path(session_store.storage_dir) / f"{session_id}.md",
            Path(attachment_store.storage_dir) / session_id,
            Path(artifact_store.storage_dir) / session_id,
        ]
        self._tempdir = Path(tempfile.mkdtemp(prefix="search-agent-run-"))
        self._snapshots: list[tuple[Path, Path | None]] = []
        self._closed = False

    def begin(self) -> None:
        for index, target in enumerate(self._targets):
            if target.exists():
                backup = self._tempdir / f"snapshot-{index}"
                if target.is_dir():
                    shutil.copytree(target, backup)
                else:
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                self._snapshots.append((target, backup))
            else:
                self._snapshots.append((target, None))

    def commit(self) -> None:
        self._cleanup()

    def rollback(self) -> None:
        if self._closed:
            return
        for target, backup in self._snapshots:
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            if backup is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if backup.is_dir():
                shutil.copytree(backup, target)
            else:
                shutil.copy2(backup, target)
        self._cleanup()

    def _cleanup(self) -> None:
        if self._closed:
            return
        if self._tempdir.exists():
            shutil.rmtree(self._tempdir, ignore_errors=True)
        self._closed = True
