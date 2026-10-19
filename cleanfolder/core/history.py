import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .filesystem import SafetyError
from ..platforms.environment import data_directory


class HistoryWriteError(RuntimeError):
    pass


def default_history_directory() -> Path:
    return data_directory()


class HistoryStore:
    def __init__(self, directory: Path | None = None):
        self.directory = (directory or default_history_directory()).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        with (self.directory / "operation.lock").open("a+b") as handle:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                handle.write(b"0")
                handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise SafetyError("다른 CleanFolder 작업이 진행 중입니다.") from error
            else:
                import fcntl

                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise SafetyError("다른 CleanFolder 작업이 진행 중입니다.") from error
            try:
                yield
            finally:
                if sys.platform == "win32":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def save(self, job: dict) -> None:
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(job, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.directory / f"{job['id']}.json")
            if os.name == "posix":
                directory_descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
        except OSError as error:
            raise HistoryWriteError("작업 기록을 저장할 수 없어 작업을 중단했습니다. 저장 공간과 접근 권한을 확인해 주세요.") from error
        finally:
            if temporary is not None and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def jobs(self) -> list[dict]:
        jobs = []
        for path in self.directory.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job["version"] != 1 or path.stem != job["id"]:
                    raise ValueError("지원하지 않는 기록 형식")
                jobs.append(job)
            except (ValueError, KeyError, TypeError) as error:
                raise SafetyError(f"작업 기록을 읽을 수 없습니다: {path.name}") from error
        return sorted(jobs, key=lambda job: job["created_at"], reverse=True)
