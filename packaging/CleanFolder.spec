from pathlib import Path
from importlib.metadata import distribution
import re
import sysconfig

from cleanfolder import __version__


project = Path(SPECPATH).parent
assets = project / "cleanfolder" / "assets"
wheel = distribution("PySide6_Essentials").read_text("WHEEL") or ""
minimum_versions = [tuple(map(int, version)) for version in re.findall(r"macosx_(\d+)_(\d+)", wheel)]
minimum_versions.append(tuple(map(int, (sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET") or "11.0").split("."))))
minimum_version = ".".join(map(str, max(minimum_versions)))

analysis = Analysis(
    [str(project / "packaging" / "launcher.py")],
    pathex=[str(project)],
    datas=[(str(assets), "cleanfolder/assets")],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml"],
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="CleanFolder",
    console=False,
    strip=False,
    upx=False,
    argv_emulation=False,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="CleanFolder",
)
application = BUNDLE(
    collection,
    name="CleanFolder.app",
    icon=str(assets / "app-icon.icns"),
    bundle_identifier="com.onechamp965.cleanfolder",
    version=__version__,
    info_plist={
        "CFBundleDisplayName": "CleanFolder",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "LSMinimumSystemVersion": minimum_version,
    },
)
