import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, replace
from pathlib import Path

from ..core.filesystem import SafetyError
from ..core.path_validator import PathAllowlist
from ..core.service import Organizer, Preview


class FolderTools:
    preview_lifetime = 300
    preview_limit = 128

    def __init__(self, organizer: Organizer, allowlist: PathAllowlist):
        self.organizer = organizer
        self.allowlist = allowlist
        self._previews: OrderedDict[str, tuple[float, Preview]] = OrderedDict()
        self._lock = threading.RLock()

    def _folder(self, folder: str) -> Path:
        return self.allowlist.validate(Path(folder))

    def _refresh_settings(self) -> None:
        self.organizer.settings = self.organizer.settings_store.load()

    def scan_folder(self, folder: str) -> dict:
        """List eligible top-level files only; return the latest undoable operation ID."""
        with self._lock:
            root = self._folder(folder)
            self._refresh_settings()
            scan = self.organizer.scan(root)
            job = self.organizer.latest(scan.root)
            return {
                "folder": str(scan.root), "count": len(scan.files), "skipped": scan.skipped,
                "files": [{"name": item.name, "category": item.category, "size": item.size}
                          for item in scan.files],
                "latest_operation_id": job["id"] if job else None,
            }

    def preview_organization(self, folder: str, include_names: list[str] | None = None) -> dict:
        """Create a five-minute, single-use plan. Show its exact moves to the user for approval.

        include_names selects exact top-level names; omitted means all eligible files.
        Existing folders are never reused, including GUI-managed folders.
        """
        with self._lock:
            root = self._folder(folder)
            self._refresh_settings()
            preview = self.organizer.preview(root, reuse_managed=False)
            if include_names is not None:
                selected = set(include_names)
                if selected.difference(item.name for item in preview.files):
                    raise SafetyError("선택한 파일이 미리보기에 없습니다. 최상위 파일 이름을 확인해 주세요.")
                preview = replace(preview, files=tuple(item for item in preview.files if item.name in selected))
            now = time.monotonic()
            self._previews = OrderedDict((token, plan) for token, plan in self._previews.items()
                                         if plan[0] > now)
            while len(self._previews) >= self.preview_limit:
                self._previews.popitem(last=False)
            token = secrets.token_urlsafe(32)
            self._previews[token] = (now + self.preview_lifetime, preview)
            return {
                "folder": str(preview.root), "preview_id": token,
                "expires_in_seconds": self.preview_lifetime, "approval_required": True,
                "count": len(preview.files), "skipped": preview.skipped,
                "moves": [{"source": item.name, "destination": f"{item.folder}/{item.target or item.name}",
                           "category": item.category, "size": item.size} for item in preview.files],
            }

    def organize_files(self, preview_id: str, approved: bool = False) -> dict:
        """Execute the stored plan only after the client obtains explicit user approval.

        approved is a client assertion, not proof of human consent. Never set it before
        showing the preview and receiving approval. Expired or consumed IDs require a new preview.
        """
        with self._lock:
            if approved is not True:
                raise SafetyError("미리보기 내용을 사용자에게 보여주고 승인받아 주세요.")
            plan = self._previews.pop(preview_id, None)
            if plan is None or plan[0] <= time.monotonic():
                raise SafetyError("미리보기가 없거나 만료되었습니다. 다시 미리보기 해 주세요.")
            preview = plan[1]
            self._folder(str(preview.root))
            self._refresh_settings()
            return asdict(self.organizer.organize(preview))

    def undo_last_operation(self, folder: str, operation_id: str, approved: bool = False) -> dict:
        """Restore the latest recorded operation after user approval; never trash files.

        Obtain operation_id from scan_folder or organize_files. Only recorded files
        in recorded category folders are visited during undo.
        """
        with self._lock:
            root = self._folder(folder)
            if approved is not True:
                raise SafetyError("원래대로 돌리기 전에 사용자 승인을 받아 주세요.")
            if not operation_id:
                raise SafetyError("복구할 작업 ID를 지정해 주세요.")
            return asdict(self.organizer.undo(root, expected_operation_id=operation_id))
