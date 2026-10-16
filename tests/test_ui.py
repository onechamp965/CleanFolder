import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication, QMessageBox

    from cleanfolder.ui import MainWindow
except ImportError:
    QApplication = None

from cleanfolder.history import HistoryStore
from cleanfolder.service import Organizer


@unittest.skipIf(QApplication is None, "PySide6가 설치되어 있지 않습니다.")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "Downloads"
        self.root.mkdir()
        self.organizer = Organizer(HistoryStore(self.base / "history"))
        self.window = MainWindow(self.organizer)
        self.window.show()

    def tearDown(self):
        self.wait_until_idle()
        self.window.close()
        self.application.processEvents()
        self.temporary.cleanup()

    def wait_until_idle(self):
        deadline = time.monotonic() + 15
        while self.window.task is not None:
            self.application.processEvents()
            if time.monotonic() > deadline:
                self.fail("화면 작업이 시간 안에 끝나지 않았습니다.")
            time.sleep(0.005)
        self.application.processEvents()

    def load_folder(self):
        self.window.folder = self.root
        self.window.folder_text.setText(str(self.root))
        self.window.refresh()
        self.wait_until_idle()

    def test_initial_controls(self):
        self.assertTrue(self.window.choose_button.isEnabled())
        self.assertFalse(self.window.organize_button.isEnabled())
        self.assertFalse(self.window.undo_button.isEnabled())
        self.assertFalse(self.window.trash_button.isEnabled())

    def test_preview_organize_and_undo_workflow(self):
        (self.root / "보고서.pdf").write_text("report")
        (self.root / "setup.dmg").write_text("installer")
        self.load_folder()
        self.assertEqual(self.window.preview_table.rowCount(), 2)
        self.assertTrue(self.window.organize_button.isEnabled())
        self.assertTrue((self.root / "보고서.pdf").exists())
        self.window.organize_button.click()
        self.assertFalse(self.window.choose_button.isEnabled())
        self.assertFalse(self.window.organize_button.isEnabled())
        self.wait_until_idle()
        self.assertTrue((self.root / "PDF/보고서.pdf").exists())
        self.assertTrue(self.window.undo_button.isEnabled())
        self.assertEqual(self.window.history_table.rowCount(), 1)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.undo_button.click()
        self.wait_until_idle()
        self.assertTrue((self.root / "보고서.pdf").exists())
        self.assertTrue((self.root / "setup.dmg").exists())
        self.assertFalse((self.root / "PDF").exists())
        self.assertFalse(self.window.undo_button.isEnabled())

    def test_select_and_trash_installer(self):
        (self.root / "setup.dmg").write_text("installer")
        self.load_folder()
        self.assertFalse(self.window.trash_button.isEnabled())
        self.window.installers_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        self.assertTrue(self.window.trash_button.isEnabled())

        def fake_trash(path):
            Path(path).rename(self.base / "trash.dmg")

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            with patch("send2trash.send2trash", side_effect=fake_trash) as mocked:
                self.window.trash_button.click()
                self.wait_until_idle()
                mocked.assert_called_once()
        self.assertFalse((self.root / "setup.dmg").exists())
        self.assertTrue((self.base / "trash.dmg").exists())
        self.assertEqual(self.window.installers_table.rowCount(), 0)

    def test_cancel_trash_keeps_file(self):
        (self.root / "setup.dmg").write_text("installer")
        self.load_folder()
        self.window.installers_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.window.trash_button.click()
        self.assertIsNone(self.window.task)
        self.assertTrue((self.root / "setup.dmg").exists())

    def test_worker_error_is_shown_and_controls_recover(self):
        self.window.folder = self.base / "missing-folder"
        with patch.object(QMessageBox, "warning") as warning:
            self.window.refresh()
            self.wait_until_idle()
            warning.assert_called_once()
        self.assertTrue(self.window.choose_button.isEnabled())
        self.assertFalse(self.window.organize_button.isEnabled())

    def test_empty_folder_state_updates_after_files_are_added_and_organized(self):
        (self.root / "existing").mkdir()
        self.load_folder()
        self.assertIs(self.window.preview_stack.currentWidget(), self.window.empty_preview)
        self.assertEqual(self.window.file_stat.value.text(), "0개")
        self.assertEqual(self.window.protected_stat.value.text(), "1개")
        self.assertFalse(self.window.empty_preview.action.isVisible())
        (self.root / "report.pdf").write_text("report")
        self.window.refresh()
        self.wait_until_idle()
        self.assertIs(self.window.preview_stack.currentWidget(), self.window.preview_table)
        self.assertEqual(self.window.file_stat.value.text(), "1개")
        self.window.organize_button.click()
        self.wait_until_idle()
        self.assertIs(self.window.preview_stack.currentWidget(), self.window.empty_preview)
        self.assertTrue(self.window.undo_button.isEnabled())
        self.assertEqual(self.window.file_stat.value.text(), "0개")

    def test_sidebar_navigation_keeps_folder_and_limits_default_action(self):
        (self.root / "setup.dmg").write_text("installer")
        self.load_folder()
        self.window.nav_buttons[1].click()
        self.assertEqual(self.window.tabs.currentIndex(), 1)
        self.assertEqual(self.window.page_title.text(), "설치 파일")
        self.assertFalse(self.window.organize_button.isVisible())
        self.assertFalse(self.window.organize_button.isDefault())
        self.assertEqual(self.window.folder, self.root)
        self.window.nav_buttons[2].click()
        self.assertIs(self.window.history_stack.currentWidget(), self.window.empty_history)
        self.window.nav_buttons[0].click()
        self.assertTrue(self.window.organize_button.isVisible())
        self.assertTrue(self.window.organize_button.isDefault())
        self.assertEqual(self.window.preview_table.rowCount(), 1)

    def test_palette_changes_update_both_light_and_dark_themes(self):
        original = QPalette(self.application.palette())
        try:
            for color, expected in (("#17191F", True), ("#F5F7FB", False), ("#17191F", True)):
                palette = QPalette(original)
                palette.setColor(QPalette.ColorRole.Window, QColor(color))
                self.application.setPalette(palette)
                self.application.processEvents()
                self.assertEqual(self.window._theme_dark, expected)
        finally:
            self.application.setPalette(original)
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
