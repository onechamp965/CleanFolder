import hashlib
import os
import platform
import plistlib
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from ds_store import DSStore

from cleanfolder import __version__
from cleanfolder.core.settings import Settings, SettingsStore


def verify():
    if sys.platform != "darwin":
        raise SystemExit("macOS에서 검증해 주세요.")
    project = Path(__file__).resolve().parents[1]
    distribution = project / "dist/macos"
    architecture = "AppleSilicon" if platform.machine() == "arm64" else "Intel"
    name = f"CleanFolder-{__version__}-macOS-{architecture}"
    archive, image = distribution / f"{name}.zip", distribution / f"{name}.dmg"
    for entry in (distribution / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, filename = entry.split("  ", 1)
        actual = hashlib.sha256((distribution / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"체크섬이 일치하지 않습니다: {filename}")
    environment = os.environ.copy()
    environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    environment["QT_QPA_PLATFORM"] = "offscreen"
    for key in ("VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        environment.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="cleanfolder-verify-") as temporary:
        directory = Path(temporary).resolve()
        home = directory / "home"
        home.mkdir()
        environment["HOME"] = str(home)
        settings = Settings()
        SettingsStore(home / "Library/Application Support/CleanFolder").save(replace(
            settings, theme="dark", folder_names=dict(settings.folder_names, PDF="Documents"),
        ))
        subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive), str(directory)], check=True)
        bundle = directory / "CleanFolder.app"
        information = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
        assert information["CFBundleIdentifier"] == "com.onechamp965.cleanfolder"
        assert information["CFBundleShortVersionString"] == __version__
        assert list(bundle.rglob("libqcocoa.dylib"))
        assert list(bundle.rglob("libqoffscreen.dylib"))
        for name in ("QtPdf.framework", "QtQml.framework", "QtQuick.framework", "QtVirtualKeyboard.framework"):
            assert not list(bundle.rglob(name)), name
        for name in ("app-icon.png", "checkmark.svg"):
            assert (bundle / "Contents/Resources/cleanfolder/assets" / name).is_file()
        for path in bundle.rglob("*"):
            if path.is_symlink():
                assert path.resolve().is_relative_to(bundle.resolve()), str(path)
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
        folder = directory / "Downloads"
        folder.mkdir()
        (folder / "보고서.pdf").write_text("document", encoding="utf-8")
        (folder / "회의록.hwp").write_text("hangul", encoding="utf-8")
        (folder / "기획서.hwpx").write_text("hangul xml", encoding="utf-8")
        executable = bundle / "Contents/MacOS/CleanFolder"
        preview = subprocess.run([str(executable), "--preview", str(folder)], cwd=directory,
                                 env=environment, capture_output=True, timeout=30)
        assert preview.returncode == 0, preview.stderr
        assert "Documents/보고서.pdf" in preview.stdout.decode("utf-8"), preview.stdout
        assert "Hangul/회의록.hwp" in preview.stdout.decode("utf-8"), preview.stdout
        assert "Hangul/기획서.hwpx" in preview.stdout.decode("utf-8"), preview.stdout
        assert (folder / "보고서.pdf").read_text(encoding="utf-8") == "document"
        assert (folder / "회의록.hwp").read_text(encoding="utf-8") == "hangul"
        assert (folder / "기획서.hwpx").read_text(encoding="utf-8") == "hangul xml"
        process = subprocess.Popen([str(executable)], cwd=directory, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=5)
            raise RuntimeError(f"앱이 초기화 중 종료되었습니다: {process.returncode}: {stderr!r}")
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout, stderr = process.communicate(timeout=10)
            assert b"Traceback" not in stderr, stderr
        subprocess.run(["/usr/bin/hdiutil", "verify", str(image)], check=True, stdout=subprocess.DEVNULL)
        mount = directory / "mounted"
        mount.mkdir()
        subprocess.run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(image)],
                       check=True, stdout=subprocess.DEVNULL)
        try:
            assert (mount / "Applications").is_symlink()
            assert os.readlink(mount / "Applications") == "/Applications"
            assert (mount / ".background.tiff").is_file()
            subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(mount / "CleanFolder.app")], check=True)
            with DSStore.open(str(mount / ".DS_Store"), "r") as store:
                assert store["CleanFolder.app"]["Iloc"] == (190, 220)
                assert store["Applications"]["Iloc"] == (490, 220)
        finally:
            subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], check=True, stdout=subprocess.DEVNULL)
    print("검증 완료: 체크섬, 앱 서명, 내장 실행 환경, 한글 파일 미리보기, 화면 초기화, DMG 설치 구성")


if __name__ == "__main__":
    verify()
