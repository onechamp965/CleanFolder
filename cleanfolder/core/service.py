import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .filesystem import (
    SafetyError, available_name, identity, move_exclusive, name_key,
    regular_file, suggest_name, verify_directory, verify_file,
)
from .history import HistoryStore
from .settings import Settings, SettingsStore


@dataclass(frozen=True)
class ScannedFile:
    name: str
    category: str
    identity: list[int]
    size: int
    modified: int


@dataclass(frozen=True)
class Scan:
    root: Path
    identity: list[int]
    files: tuple[ScannedFile, ...]
    skipped: int


@dataclass(frozen=True)
class PlannedFile:
    name: str
    category: str
    folder: str
    identity: list[int]
    size: int
    modified: int
    target: str = ""


@dataclass(frozen=True)
class Preview:
    root: Path
    identity: list[int]
    files: tuple[PlannedFile, ...]
    skipped: int
    settings_key: str = ""
    existing_folders: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class Result:
    completed: int = 0
    issues: list[str] = field(default_factory=list)
    operation_id: str | None = None


@dataclass(frozen=True)
class Installer:
    path: Path
    identity: list[int]
    parent_identity: list[int]


class Organizer:
    def __init__(self, history: HistoryStore | None = None):
        self.history = history or HistoryStore()
        self.settings_store = SettingsStore(self.history.directory)
        self.settings = self.settings_store.load()

    def apply_settings(self, settings: Settings) -> None:
        with self.history.locked():
            self.settings = self.settings_store.save(settings)

    def _managed_folders(self, root: Path, root_identity: list[int]) -> dict[str, tuple[str, list[int]]]:
        managed = {}
        for job in self.jobs(root):
            if job["root_identity"] != root_identity:
                continue
            for action in job["actions"]:
                category, name = action["category"], action["folder"]
                if category in managed or category not in self.settings.folder_names or Path(name).name != name or name in (".", ".."):
                    continue
                expected = job["folders"].get(name)
                desired = job.get("folder_labels", {}).get(name, category)
                if expected is None or name_key(desired) != name_key(self.settings.folder_names[category]):
                    continue
                try:
                    verify_directory(root / name, expected)
                except (OSError, SafetyError):
                    continue
                managed[category] = (name, expected)
        return managed

    def scan(self, folder: Path) -> Scan:
        root = folder.expanduser().resolve(strict=True)
        root_identity = identity(root)
        verify_directory(root, root_identity)
        if root == self.history.directory or self.history.directory in root.parents:
            raise SafetyError("앱의 작업 기록과 설정 폴더는 정리할 수 없습니다.")
        files = []
        skipped = 0
        with os.scandir(root) as entries:
            snapshot = sorted(entries, key=lambda entry: name_key(entry.name))
        for entry in snapshot:
            if entry.name.startswith(".") or self.settings.excludes(entry.name) or not entry.is_file(follow_symlinks=False):
                skipped += 1
                continue
            information = entry.stat(follow_symlinks=False)
            files.append(ScannedFile(
                entry.name, self.settings.classify(entry.name),
                [information.st_dev, information.st_ino], information.st_size,
                information.st_mtime_ns,
            ))
        return Scan(root, root_identity, tuple(files), skipped)

    def preview(self, folder: Path, *, reuse_managed: bool = True) -> Preview:
        scan = self.scan(folder)
        root, root_identity = scan.root, scan.identity
        reserved = set()
        folders = {}
        existing_folders = {}
        destination_names = {}
        managed = self._managed_folders(root, root_identity) if reuse_managed and self.settings.folder_mode == "managed" else {}
        files = []
        for entry in scan.files:
            category = entry.category
            if category not in folders:
                if category in managed:
                    name, expected = managed[category]
                    verify_directory(root / name, expected)
                    folders[category] = name
                    existing_folders[name] = expected
                    destination_names[name] = {name_key(child.name) for child in (root / name).iterdir()}
                else:
                    folders[category] = available_name(root, self.settings.folder_names[category], reserved)
                    destination_names[folders[category]] = set()
                reserved.add(name_key(folders[category]))
            target = suggest_name(entry.name, destination_names[folders[category]])
            destination_names[folders[category]].add(name_key(target))
            files.append(PlannedFile(
                entry.name, category, folders[category],
                entry.identity, entry.size, entry.modified, target,
            ))
        return Preview(root, root_identity, tuple(files), scan.skipped, self.settings.sorting_key(), existing_folders)

    def organize(self, preview: Preview) -> Result:
        result = Result()
        with self.history.locked():
            verify_directory(preview.root, preview.identity)
            if preview.settings_key != self.settings.sorting_key():
                raise SafetyError("정리 설정이 변경되었습니다. 다시 미리보기 해 주세요.")
            if preview.settings_key != self.settings_store.load().sorting_key():
                raise SafetyError("다른 CleanFolder에서 정리 설정이 변경되었습니다. 다시 미리보기 해 주세요.")
            if not preview.files:
                return result
            for item in preview.files:
                source = preview.root / item.name
                verify_file(source, item.identity)
                information = source.lstat()
                if (information.st_size, information.st_mtime_ns) != (item.size, item.modified):
                    raise SafetyError("미리보기 이후 파일이 변경되었습니다. 다시 미리보기 해 주세요.")
            for folder in {item.folder for item in preview.files}:
                if folder in preview.existing_folders:
                    candidates = self._managed_folders(preview.root, preview.identity)
                    if not any(name == folder and expected == preview.existing_folders[folder] for name, expected in candidates.values()):
                        raise SafetyError("앱이 만든 분류 폴더가 변경되었습니다. 다시 미리보기 해 주세요.")
                    verify_directory(preview.root / folder, preview.existing_folders[folder])
                elif os.path.lexists(preview.root / folder):
                    raise SafetyError("미리보기 이후 대상 폴더가 생겼습니다. 다시 미리보기 해 주세요.")
            job = {
                "version": 1, "id": uuid.uuid4().hex,
                "created_at": datetime.now().astimezone().isoformat(),
                "root": str(preview.root), "root_identity": preview.identity,
                "state": "active", "folders": {}, "actions": [],
                "created_folders": [], "folder_labels": {},
            }
            result.operation_id = job["id"]
            self.history.save(job)
            for item in preview.files:
                verify_directory(preview.root, preview.identity)
                folder = preview.root / item.folder
                if item.folder not in job["folders"]:
                    if item.folder in preview.existing_folders:
                        verify_directory(folder, preview.existing_folders[item.folder])
                        job["folders"][item.folder] = preview.existing_folders[item.folder]
                    else:
                        folder.mkdir()
                        job["folders"][item.folder] = identity(folder)
                        job["created_folders"].append(item.folder)
                    job["folder_labels"][item.folder] = self.settings.folder_names[item.category]
                    self.history.save(job)
                verify_directory(folder, job["folders"][item.folder])
                target = available_name(folder, item.target or item.name)
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
        created = job.get("created_folders", list(job["folders"]))
        if not isinstance(created, list) or any(name not in job["folders"] for name in created):
            raise SafetyError("생성한 폴더 기록이 올바르지 않습니다.")
        for action in job["actions"]:
            for key in ("name", "target", "restore_name"):
                name = action[key]
                if name is not None and (Path(name).name != name or name in (".", "..")):
                    raise SafetyError("올바르지 않은 파일 기록입니다.")
            if action["folder"] not in job["folders"]:
                raise SafetyError("분류 폴더 기록을 찾을 수 없습니다.")
        return root

    def undo(self, folder: Path, *, expected_operation_id: str | None = None) -> Result:
        result = Result()
        with self.history.locked():
            job = self.latest(folder)
            if expected_operation_id is not None and (job is None or job["id"] != expected_operation_id):
                raise SafetyError("최근 작업이 변경되었습니다. 작업 기록을 다시 확인해 주세요.")
            if job is None:
                return result
            result.operation_id = job["id"]
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
            for name in job.get("created_folders", list(job["folders"])):
                expected = job["folders"][name]
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
                if not entry.name.startswith(".") and not self.settings.excludes(entry.name) and entry.is_file(follow_symlinks=False) and self.settings.classify(entry.name) == "Installers":
                    candidates.append(Installer(Path(entry.path), identity(Path(entry.path)), identity(root)))
        for job in self.jobs(root):
            self._validate_job(job)
            for action in job["actions"]:
                if action["category"] != "Installers" or action["state"] not in ("pending", "moved", "trashing"):
                    continue
                parent = root / action["folder"]
                path = parent / action["target"]
                if self.settings.excludes(path.name):
                    continue
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
