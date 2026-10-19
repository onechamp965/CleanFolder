import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from cleanfolder import __version__


PROJECT = Path(__file__).resolve().parents[1]


def bundle_size(path: Path) -> dict:
    entries = [entry for entry in path.rglob("*") if entry.is_file() and not entry.is_symlink()]
    return {"files": len(entries), "bytes": sum(entry.stat().st_size for entry in entries)}


def write_report(directory: Path, bundle: Path, artifacts: list[Path], baseline: Path | None = None):
    report = {"version": __version__, "platform": sys.platform, "architecture": platform.machine(),
              "bundle": bundle_size(bundle),
              "artifacts": [{"name": path.name, "bytes": path.stat().st_size} for path in artifacts]}
    if baseline is not None:
        if not baseline.is_dir():
            raise ValueError(f"비교할 이전 앱을 찾을 수 없습니다: {baseline}")
        previous = bundle_size(baseline)
        report["baseline"] = previous
        report["saved_bytes"] = previous["bytes"] - report["bundle"]["bytes"]
    (directory / "size-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    checksums = []
    for path in artifacts:
        with path.open("rb") as handle:
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        checksums.append(f"{digest.hexdigest()}  {path.name}")
        print(f"{path.name}: {path.stat().st_size / 1024 ** 2:.1f} MiB")
    (directory / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"설치 후 앱: {report['bundle']['bytes'] / 1024 ** 2:.1f} MiB")
    return report


def build(target: str, baseline: Path | None = None):
    expected = "darwin" if target == "macos" else "win32"
    if sys.platform != expected:
        raise SystemExit(f"{target} 배포 파일은 해당 운영체제에서 빌드해 주세요.")
    if baseline is not None and not baseline.is_dir():
        raise ValueError(f"비교할 이전 앱을 찾을 수 없습니다: {baseline}")
    output = PROJECT / "dist" / target
    work = PROJECT / "build" / target
    work.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(work / "pyinstaller-cache")
    command_line_tools = Path("/Library/Developer/CommandLineTools")
    if target == "macos" and not environment.get("DEVELOPER_DIR") and command_line_tools.is_dir():
        environment["DEVELOPER_DIR"] = str(command_line_tools)
        environment["PATH"] = str(command_line_tools / "usr/bin") + os.pathsep + environment.get("PATH", "")
    subprocess.run([sys.executable, "-m", "scripts.build_icons"], cwd=PROJECT, env=environment, check=True)
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(output), "--workpath", str(work / "pyinstaller"),
         str(PROJECT / "packaging" / target / "CleanFolder.spec")],
        cwd=PROJECT, env=environment, check=True,
    )
    if target == "macos":
        bundle = output / "CleanFolder.app"
        architecture = "AppleSilicon" if platform.machine() == "arm64" else "Intel"
        name = f"CleanFolder-{__version__}-macOS-{architecture}"
        archive = output / f"{name}.zip"
        subprocess.run(["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(bundle), str(archive)], check=True)
        background = work / "installer"
        subprocess.run([sys.executable, "-m", "scripts.build_dmg_background", "--output", str(background)],
                       cwd=PROJECT, env=environment, check=True)
        image = output / f"{name}.dmg"
        subprocess.run(
            [sys.executable, "-m", "dmgbuild", "-s", str(PROJECT / "packaging/macos/dmg_settings.py"),
             "-D", f"app={bundle}", "-D", f"background={background / 'installer-background.png'}",
             "CleanFolder 설치", str(image)], env=environment, check=True,
        )
        artifacts = [archive, image]
    else:
        bundle = output / "CleanFolder"
        architecture = "ARM64" if platform.machine().casefold() in ("arm64", "aarch64") else "x64"
        archive = Path(shutil.make_archive(str(output / f"CleanFolder-{__version__}-Windows-{architecture}"),
                                           "zip", root_dir=output, base_dir=bundle.name))
        artifacts = [archive]
    write_report(output, bundle, artifacts, baseline)


def main(argv=None):
    parser = argparse.ArgumentParser(description="운영체제별 CleanFolder 배포 파일 생성")
    parser.add_argument("target", choices=("macos", "windows"))
    parser.add_argument("--baseline", type=Path, help="용량을 비교할 이전 앱 폴더")
    arguments = parser.parse_args(argv)
    build(arguments.target, arguments.baseline)


if __name__ == "__main__":
    main()
