import os
import platform
import subprocess
import sys
from pathlib import Path


def build():
    if sys.platform != "darwin":
        raise SystemExit("macOS에서 실행해 주세요.")
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    from cleanfolder import __version__

    build_directory = project / "build"
    build_directory.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(build_directory / "pyinstaller-cache")
    command_line_tools = Path("/Library/Developer/CommandLineTools")
    if not environment.get("DEVELOPER_DIR") and command_line_tools.is_dir():
        environment["DEVELOPER_DIR"] = str(command_line_tools)
        environment["PATH"] = str(command_line_tools / "usr" / "bin") + os.pathsep + environment.get("PATH", "")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm",
         "--distpath", str(project / "dist"),
         "--workpath", str(build_directory / "macos"),
         str(project / "packaging" / "CleanFolder.spec")],
        cwd=project, env=environment, check=True,
    )
    application = project / "dist" / "CleanFolder.app"
    architecture = "AppleSilicon" if platform.machine() == "arm64" else "Intel"
    name = f"CleanFolder-{__version__}-macOS-{architecture}"
    archive = project / "dist" / f"{name}.zip"
    subprocess.run(
        ["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(application), str(archive)],
        check=True,
    )
    background_directory = build_directory / "installer"
    subprocess.run(
        [sys.executable, str(project / "scripts" / "build_dmg_background.py"),
         "--output", str(background_directory)],
        env=environment, check=True,
    )
    image = project / "dist" / f"{name}.dmg"
    subprocess.run(
        [sys.executable, "-m", "dmgbuild", "-s", str(project / "packaging" / "dmg_settings.py"),
         "-D", f"app={application}",
         "-D", f"background={background_directory / 'installer-background.png'}",
         "CleanFolder 설치", str(image)],
        env=environment, check=True,
    )
    print(f"앱: {application}\n배포용 ZIP: {archive}\n설치용 DMG: {image}")


if __name__ == "__main__":
    build()
