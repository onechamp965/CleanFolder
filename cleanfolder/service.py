import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .categories import classify
from .filesystem import (
    SafetyError, available_name, identity, move_exclusive, name_key,
    regular_file, verify_directory, verify_file,
)
from .history import HistoryStore


@dataclass(frozen=True)
class PlannedFile:
    name: str
    category: str
    folder: str
    identity: list[int]
    size: int
    modified: int


@dataclass(frozen=True)
class Preview:
    root: Path
    identity: list[int]
    files: tuple[PlannedFile, ...]
    skipped: int


@dataclass
class Result:
    completed: int = 0
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Installer:
    path: Path
    identity: list[int]
    parent_identity: list[int]


class Organizer:
    def __init__(self, history: HistoryStore | None = None):
        self.history = history or HistoryStore()

    def preview(self, folder: Path) -> Preview:
        root = folder.expanduser().resolve(strict=True)
        root_identity = identity(root)
        verify_directory(root, root_identity)
        if root == self.history.directory:
            raise SafetyError("앱의 작업 기록 폴더 자체는 정리할 수 없습니다.")
        reserved = set()
        folders = {}
        files = []
        skipped = 0
        with os.scandir(root) as entries:
            snapshot = sorted(entries, key=lambda entry: name_key(entry.name))
        for entry in snapshot:
            if entry.name.startswith(".") or not entry.is_file(follow_symlinks=False):
                skipped += 1
                continue
            information = entry.stat(follow_symlinks=False)
            category = classify(entry.name)
            if category not in folders:
                folders[category] = available_name(root, category, reserved)
                reserved.add(name_key(folders[category]))
            files.append(PlannedFile(
                entry.name, category, folders[category],
                [information.st_dev, information.st_ino], information.st_size,
                information.st_mtime_ns,
            ))
        return Preview(root, root_identity, tuple(files), skipped)

    def organize(self, preview: Preview) -> Result:
        result = Result()
        with self.history.locked():
            verify_directory(preview.root, preview.identity)
            if not preview.files:
                return result
            for item in preview.files:
                source = preview.root / item.name
                verify_file(source, item.identity)
                information = source.lstat()
                if (information.st_size, information.st_mtime_ns) != (item.size, item.modified):
                    raise SafetyError("미리보기 이후 파일이 변경되었습니다. 다시 미리보기 해 주세요.")
            for folder in {item.folder for item in preview.files}:
                if os.path.lexists(preview.root / folder):
                    raise SafetyError("미리보기 이후 대상 폴더가 생겼습니다. 다시 미리보기 해 주세요.")
            job = {
                "version": 1, "id": uuid.uuid4().hex,
                "created_at": datetime.now().astimezone().isoformat(),
                "root": str(preview.root), "root_identity": preview.identity,
                "state": "active", "folders": {}, "actions": [],
            }
            self.history.save(job)
            for item in preview.files:
                verify_directory(preview.root, preview.identity)
                folder = preview.root / item.folder
                if item.folder not in job["folders"]:
                    folder.mkdir()
                    job["folders"][item.folder] = identity(folder)
                    self.history.save(job)
                verify_directory(folder, job["folders"][item.folder])
                target = available_name(folder, item.name)
                action = {
                    "name": item.name, "folder": item.folder, "target": target,
                    "identity": item.identity, "category": item.category,
                    "state": "pending", "restore_name": None,
                }
                job["actions"].append(action)
                self.history.save(job)
                try:
                    move_exclusive(preview.root / item.name, folder / target, item.identity,
                                   preview.identity, job["folders"][item.folder])
                except OSError as error:
                    result.issues.append(f"{item.name}: {error}")
                else:
                    action["state"] = "moved"
                    result.completed += 1
                self.history.save(job)
        return result

    def jobs(self, root: Path | None = None) -> list[dict]:
        return [job for job in self.history.jobs() if root is None or job["root"] == str(root)]

    def latest(self, root: Path) -> dict | None:
        return next((job for job in self.jobs(root) if job["state"] == "active"), None)

    def _validate_job(self, job: dict) -> Path:
        root = Path(job["root"])
        if not root.is_absolute() or root.resolve() != root:
            raise SafetyError("기록의 원래 폴더가 변경되었습니다.")
        verify_directory(root, job["root_identity"])
        for folder in job["folders"]:
            if Path(folder).name != folder or folder in (".", ".."):
                raise SafetyError("올바르지 않은 폴더 기록입니다.")
        for action in job["actions"]:
            for key in ("name", "target", "restore_name"):
                name = action[key]
                if name is not None and (Path(name).name != name or name in (".", "..")):
                    raise SafetyError("올바르지 않은 파일 기록입니다.")
            if action["folder"] not in job["folders"]:
                raise SafetyError("분류 폴더 기록을 찾을 수 없습니다.")
        return root

    def undo(self, folder: Path) -> Result:
        result = Result()
        with self.history.locked():
            job = self.latest(folder)
            if job is None:
                return result
            root = self._validate_job(job)
            for action in reversed(job["actions"]):
                if action["state"] in ("restored", "trashed"):
                    continue
                try:
                    verify_directory(root, job["root_identity"])
                    parent = root / action["folder"]
                    source = parent / action["target"]
                    destination = root / (action["restore_name"] or action["name"])
                    if os.path.lexists(parent):
                        verify_directory(parent, job["folders"][action["folder"]])
                    if not os.path.lexists(source):
                        if action["state"] == "trashing":
                            action["state"] = "trashed"
                            self.history.save(job)
                            continue
                        if action["state"] in ("pending", "restoring") and regular_file(destination) and identity(destination) == action["identity"]:
                            action["state"] = "restored"
                            self.history.save(job)
                            continue
                        raise SafetyError(f"{action['name']}: 정리된 파일을 찾을 수 없습니다.")
                    verify_directory(parent, job["folders"][action["folder"]])
                    verify_file(source, action["identity"])
                    if regular_file(destination) and identity(destination) == action["identity"] and action["state"] in ("pending", "restoring"):
                        source.unlink()
                    else:
                        action["restore_name"] = available_name(root, destination.name)
                        action["state"] = "restoring"
                        self.history.save(job)
                        move_exclusive(source, root / action["restore_name"], action["identity"],
                                       job["folders"][action["folder"]], job["root_identity"])
                    action["state"] = "restored"
                    result.completed += 1
                    self.history.save(job)
                except (OSError, SafetyError) as error:
                    result.issues.append(str(error))
            for name, expected in job["folders"].items():
                path = root / name
                if not os.path.lexists(path):
                    continue
                try:
                    verify_directory(path, expected)
                    if not any(path.iterdir()):
                        path.rmdir()
                except (OSError, SafetyError) as error:
                    result.issues.append(str(error))
            if all(action["state"] in ("restored", "trashed") for action in job["actions"]):
                job["state"] = "restored"
            self.history.save(job)
        return result

    def installers(self, folder: Path) -> list[Installer]:
        root = folder.resolve(strict=True)
        candidates = []
        with os.scandir(root) as entries:
            for entry in entries:
                if not entry.name.startswith(".") and entry.is_file(follow_symlinks=False) and classify(entry.name) == "Installers":
                    candidates.append(Installer(Path(entry.path), identity(Path(entry.path)), identity(root)))
        for job in self.jobs(root):
            self._validate_job(job)
            for action in job["actions"]:
                if action["category"] != "Installers" or action["state"] not in ("pending", "moved", "trashing"):
                    continue
                parent = root / action["folder"]
                path = parent / action["target"]
                try:
                    verify_directory(parent, job["folders"][action["folder"]])
                    verify_file(path, action["identity"])
                except (OSError, SafetyError):
                    continue
                candidates.append(Installer(path, action["identity"], job["folders"][action["folder"]]))
        return sorted({item.path: item for item in candidates}.values(), key=lambda item: name_key(str(item.path)))

    def trash(self, folder: Path, selected: list[Installer], send: Callable | None = None) -> Result:
        if send is None:
            from send2trash import send2trash

            send = send2trash
        result = Result()
        with self.history.locked():
            root_identity = identity(folder)
            verify_directory(folder, root_identity)
            allowed = {item.path: item for item in self.installers(folder)}
            for item in selected:
                try:
                    verify_directory(folder, root_identity)
                    if allowed.get(item.path) != item:
                        raise SafetyError(f"선택 이후 파일이 변경되었습니다: {item.path.name}")
                    verify_directory(item.path.parent, item.parent_identity)
                    verify_file(item.path, item.identity)
                    affected = []
                    for job in self.jobs(folder):
                        for action in job["actions"]:
                            if folder / action["folder"] / action["target"] == item.path and action["identity"] == item.identity and action["state"] in ("pending", "moved", "trashing"):
                                action["state"] = "trashing"
                                self.history.save(job)
                                affected.append((job, action))
                    send(str(item.path))
                    result.completed += 1
                    for job, action in affected:
                        action["state"] = "trashed"
                        self.history.save(job)
                except (OSError, SafetyError) as error:
                    for job in self.jobs(folder):
                        for action in job["actions"]:
                            if folder / action["folder"] / action["target"] == item.path and action["state"] == "trashing" and regular_file(item.path):
                                action["state"] = "moved"
                                self.history.save(job)
                    result.issues.append(str(error))
        return result
