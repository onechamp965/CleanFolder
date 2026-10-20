import os
import sys
from pathlib import Path


def data_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CleanFolder"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "CleanFolder"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "CleanFolder"


def trash_location() -> str:
    return "Finder의 휴지통" if sys.platform == "darwin" else "휴지통"
