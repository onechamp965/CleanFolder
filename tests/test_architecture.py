import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cleanfolder.platforms.environment import data_directory, trash_location
from scripts.bundle_policy import keep_plugin, keep_translation
from scripts.release import build, bundle_size, write_report


class ArchitectureTests(unittest.TestCase):
    def test_core_imports_and_preview_without_gui_dependencies(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "report.pdf").write_text("report")
            code = (
                "import sys; from pathlib import Path; "
                "from cleanfolder.core.history import HistoryStore; "
                "from cleanfolder.core.service import Organizer; "
                "from cleanfolder.core.path_validator import PathAllowlist; "
                "root=Path(sys.argv[1]); app=Organizer(HistoryStore(root/'history')); "
                "assert app.preview(root).files[0].category == 'PDF'; "
                "assert not any(name.startswith(('PySide6', 'mcp', 'cleanfolder.mcp_server')) for name in sys.modules)"
            )
            completed = subprocess.run([sys.executable, "-S", "-c", code, str(root)],
                                       cwd=project, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((root / "report.pdf").read_text(), "report")

    def test_existing_macos_storage_location_is_preserved(self):
        with patch("cleanfolder.platforms.environment.sys.platform", "darwin"):
            self.assertEqual(data_directory(), Path.home() / "Library/Application Support/CleanFolder")
            self.assertEqual(trash_location(), "Finder의 휴지통")

    def test_windows_uses_local_app_data_and_generic_trash_text(self):
        with patch("cleanfolder.platforms.environment.sys.platform", "win32"):
            with patch.dict(os.environ, {"LOCALAPPDATA": str(Path.home() / "AppData/Local")}):
                self.assertEqual(data_directory(), Path.home() / "AppData/Local/CleanFolder")
                self.assertEqual(trash_location(), "휴지통")

    def test_heavy_unused_plugins_are_excluded_before_dependency_collection(self):
        for name in ("libqpdf.dylib", "qpdf.dll", "libqtvirtualkeyboardplugin.dylib", "qtvirtualkeyboardplugin.dll"):
            with self.subTest(name=name):
                self.assertFalse(keep_plugin(name, "plugins"))
        for name in ("libqcocoa.dylib", "qwindows.dll", "libqoffscreen.dylib", "libqsvg.dylib", "libqjpeg.dylib"):
            self.assertTrue(keep_plugin(name, "plugins"))

    def test_korean_english_translations_and_non_translation_data_are_kept(self):
        self.assertTrue(keep_translation("qtbase_ko.qm", "translations"))
        self.assertTrue(keep_translation("qtbase_en.qm", "translations"))
        self.assertTrue(keep_translation("app-icon.png", "assets"))
        self.assertFalse(keep_translation("qtbase_de.qm", "translations"))

    def test_wrong_platform_build_is_rejected_before_work_starts(self):
        target = "windows" if sys.platform != "win32" else "macos"
        with patch("scripts.release.subprocess.run") as command:
            with self.assertRaises(SystemExit):
                build(target)
            command.assert_not_called()

    def test_size_report_and_checksums_match_actual_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "app"
            baseline = root / "previous"
            bundle.mkdir()
            baseline.mkdir()
            (bundle / "data").write_bytes(b"123")
            (baseline / "data").write_bytes(b"123456")
            artifact = root / "app.zip"
            artifact.write_bytes(b"archive")
            report = write_report(root, bundle, [artifact], baseline)
            self.assertEqual(report["bundle"]["bytes"], 3)
            self.assertEqual(report["saved_bytes"], 3)
            self.assertEqual(json.loads((root / "size-report.json").read_text()), report)
            self.assertIn(hashlib.sha256(b"archive").hexdigest(), (root / "SHA256SUMS.txt").read_text())

    @unittest.skipIf(sys.platform == "win32", "Windows symlink creation requires additional permission")
    def test_size_measurement_does_not_count_symlink_targets_twice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").write_bytes(b"123")
            (root / "alias").symlink_to(root / "data")
            self.assertEqual(bundle_size(root), {"files": 1, "bytes": 3})


if __name__ == "__main__":
    unittest.main()
