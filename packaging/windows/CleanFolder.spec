import sys
from pathlib import Path

project = Path(SPECPATH).parents[1]
sys.path.insert(0, str(project))
from scripts.bundle_policy import EXCLUDED_QT_MODULES

assets = project / "cleanfolder" / "assets"
analysis = Analysis(
    [str(project / "packaging" / "launcher.py")],
    pathex=[str(project)],
    datas=[(str(assets / name), "cleanfolder/assets") for name in ("app-icon.png", "checkmark.svg")],
    hookspath=[str(project / "packaging" / "hooks")],
    excludes=["PySide6." + module for module in EXCLUDED_QT_MODULES],
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="CleanFolder",
    console=False,
    icon=str(assets / "app-icon.ico"),
    strip=False,
    upx=False,
)
collection = COLLECT(
    executable, analysis.binaries, analysis.datas,
    name="CleanFolder", strip=False, upx=False,
)
