import fnmatch
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .categories import CATEGORIES
from .filesystem import name_key


class SettingsError(ValueError):
    pass


def parse_entries(text: str) -> tuple[str, ...]:
    return tuple(entry.strip() for entry in re.split(r"[,;\n]+", text) if entry.strip())


def normalize_extension(extension: str) -> str:
    if not isinstance(extension, str):
        raise SettingsError("확장자는 문자열이어야 합니다.")
    extension = extension.strip().casefold()
    if not extension.startswith("."):
        extension = "." + extension
    if not re.fullmatch(r"\.[\w+-]+(?:\.[\w+-]+)*", extension) or len(extension) > 80:
        raise SettingsError(f"올바르지 않은 확장자입니다: {extension}")
    return extension


@dataclass(frozen=True)
class Settings:
    folder_mode: str = "new"
    folder_names: dict[str, str] = field(default_factory=lambda: {category: category for category in CATEGORIES})
    extensions: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(CATEGORIES))
    excluded_extensions: tuple[str, ...] = ()
    excluded_names: tuple[str, ...] = ()
    startup_mode: str = "empty"
    default_folder: str = ""
    last_folder: str = ""
    theme: str = "system"

    def validated(self):
        if self.folder_mode not in ("new", "managed"):
            raise SettingsError("분류 폴더 사용 방식을 확인해 주세요.")
        if self.startup_mode not in ("empty", "default", "last") or self.theme not in ("system", "light", "dark"):
            raise SettingsError("시작 폴더 또는 화면 모드 설정을 확인해 주세요.")
        if not isinstance(self.folder_names, dict) or set(self.folder_names) != set(CATEGORIES):
            raise SettingsError("분류별 폴더 이름을 모두 지정해 주세요.")
        if not isinstance(self.extensions, dict) or set(self.extensions) != set(CATEGORIES):
            raise SettingsError("분류 기준을 확인해 주세요.")
        names = {}
        occupied = set()
        reserved = {"con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)), *(f"lpt{index}" for index in range(1, 10))}
        for category, name in self.folder_names.items():
            if not isinstance(name, str):
                raise SettingsError("폴더 이름은 문자열이어야 합니다.")
            name = name.strip()
            if (not name or name.startswith(".") or name.endswith((".", " "))
                    or any(character in name for character in '/\\:<>"|?*')
                    or any(ord(character) < 32 for character in name)
                    or len(name.encode("utf-8")) > 120 or name_key(name).split(".")[0] in reserved):
                raise SettingsError(f"사용할 수 없는 폴더 이름입니다: {name or category}")
            if name_key(name) in occupied:
                raise SettingsError("분류 폴더 이름은 서로 다르게 지정해 주세요.")
            occupied.add(name_key(name))
            names[category] = name
        extensions = {}
        assigned = set()
        for category in CATEGORIES:
            values = self.extensions[category]
            if not isinstance(values, (list, tuple)):
                raise SettingsError(f"{category} 확장자 목록을 확인해 주세요.")
            normalized = tuple(dict.fromkeys(normalize_extension(value) for value in values))
            if assigned.intersection(normalized):
                raise SettingsError("같은 확장자를 여러 분류에 지정할 수 없습니다.")
            assigned.update(normalized)
            extensions[category] = normalized
        if not set(CATEGORIES["Installers"]).issubset(extensions["Installers"]):
            raise SettingsError(".dmg, .pkg, .msi, .exe, .iso는 Installers 분류에 유지해 주세요.")
        if extensions["Others"]:
            raise SettingsError("Others는 분류되지 않은 파일에 자동으로 적용됩니다.")
        if not isinstance(self.excluded_extensions, (list, tuple)) or not isinstance(self.excluded_names, (list, tuple)):
            raise SettingsError("제외 항목은 목록이어야 합니다.")
        excluded = tuple(dict.fromkeys(normalize_extension(value) for value in self.excluded_extensions))
        patterns = []
        for pattern in self.excluded_names:
            if not isinstance(pattern, str) or not pattern.strip() or any(character in pattern for character in "/\\\x00\n\r"):
                raise SettingsError("제외할 파일 이름에는 경로 대신 파일 이름이나 패턴을 입력해 주세요.")
            patterns.append(pattern.strip())
        for path in (self.default_folder, self.last_folder):
            if not isinstance(path, str) or "\x00" in path or (path and not Path(path).expanduser().is_absolute()):
                raise SettingsError("시작 폴더는 전체 경로로 지정해 주세요.")
        if self.startup_mode == "default" and not self.default_folder:
            raise SettingsError("기본 시작 폴더를 선택해 주세요.")
        return replace(self, folder_names=names, extensions=extensions,
                       excluded_extensions=excluded, excluded_names=tuple(dict.fromkeys(patterns)))

    def classify(self, name: str) -> str:
        matches = [(extension, category) for category, extensions in self.extensions.items()
                   for extension in extensions if name_key(name).endswith(extension)]
        return max(matches, key=lambda match: len(match[0]))[1] if matches else "Others"

    def excludes(self, name: str) -> bool:
        normalized = name_key(name)
        return (any(normalized.endswith(extension) for extension in self.excluded_extensions)
                or any(fnmatch.fnmatchcase(normalized, name_key(pattern)) for pattern in self.excluded_names))

    def sorting_key(self) -> str:
        data = asdict(self)
        for key in ("startup_mode", "default_folder", "last_folder", "theme"):
            data.pop(key)
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def startup_folder(self) -> Path | None:
        path = self.default_folder if self.startup_mode == "default" else self.last_folder if self.startup_mode == "last" else ""
        return Path(path).expanduser() if path else None


class SettingsStore:
    def __init__(self, history_directory: Path):
        self.path = history_directory / "preferences" / "settings.json"

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document["version"] != 1 or not isinstance(document["settings"], dict):
                raise ValueError("설정 형식")
            return Settings(**document["settings"]).validated()
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise SettingsError(f"설정 파일을 읽을 수 없습니다: {self.path}") from error

    def save(self, settings: Settings) -> Settings:
        settings = settings.validated()
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "settings": asdict(settings)}, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise SettingsError("설정을 저장할 수 없습니다. 접근 권한과 저장 공간을 확인해 주세요.") from error
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        return settings
