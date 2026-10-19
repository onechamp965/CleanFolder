import os
import zipfile
from pathlib import Path

from cleanfolder import __version__


def export():
    project = Path(__file__).resolve().parents[1]
    archive = project.parent / f"CleanFolder-source-{__version__}.zip"
    excluded = {".git", ".venv", "__pycache__", "build", "dist", ".pytest_cache", ".ruff_cache"}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for directory, folders, files in os.walk(project):
            folders[:] = sorted(folder for folder in folders if folder not in excluded and not folder.endswith(".egg-info"))
            for filename in sorted(files):
                path = Path(directory) / filename
                if filename == ".DS_Store" or path.suffix in (".pyc", ".pyo") or path.is_symlink():
                    continue
                bundle.write(path, path.relative_to(project).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        for path in ("README.md", "requirements.txt", ".gitignore", "cleanfolder/core/service.py", "cleanfolder/desktop/window.py",
                     "packaging/macos/CleanFolder.spec", "packaging/windows/CleanFolder.spec"):
            assert path in bundle.namelist(), path
    print(archive)
    return archive


if __name__ == "__main__":
    export()
