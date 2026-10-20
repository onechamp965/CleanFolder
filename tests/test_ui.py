import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtTest import QTest

    from cleanfolder.desktop.window import MainWindow
except ImportError:
    QApplication = None

from cleanfolder.core.history import HistoryStore
from cleanfolder.core.filesystem import SafetyError
from cleanfolder.core.service import Organizer
from cleanfolder.core.settings import Settings, SettingsError
from cleanfolder.core.path_validator import PathAllowlist
from cleanfolder.mcp_server.tools import FolderTools


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
        self.organizer.apply_settings(replace(
            self.organizer.settings, folder_mode="new", startup_mode="empty", view_mode="detailed",
        ))
        self.window = MainWindow(self.organizer)
        self.window.show()

    def tearDown(self):
        self.wait_until_idle()
        self.window.close()
        self.application.processEvents()
        self.temporary.cleanup()

    def wait_until_idle(self, window=None):
        window = window or self.window
        self.application.processEvents()
        deadline = time.monotonic() + 15
        while window.task is not None:
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

    def use_simple_repeat(self):
        self.window.apply_preferences(replace(
            self.organizer.settings, view_mode="simple", folder_mode="managed", startup_mode="last",
        ))
        self.wait_until_idle()

    def test_simple_mode_shows_exact_destinations_and_preserves_detail_selection(self):
        (self.root / "report.pdf").write_text("report")
        (self.root / "photo.png").write_text("photo")
        self.use_simple_repeat()
        self.load_folder()
        self.assertIs(self.window.preview_stack.currentWidget(), self.window.overview)
        self.assertFalse(self.window.stats_widget.isVisible())
        self.assertFalse(self.window.selection_bar.isVisible())
        self.assertIn("PDF  ·  1개", self.window.destination_summary.text())
        self.assertIn("Images  ·  1개", self.window.destination_summary.text())
        self.assertTrue((self.root / "report.pdf").exists())
        preview = self.window.preview
        self.window.details_button.click()
        self.assertIs(self.window.preview_stack.currentWidget(), self.window.preview_table)
        self.assertTrue(self.window.stats_widget.isVisible())
        self.window.preview_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.window.details_button.click()
        self.assertIs(self.window.preview, preview)
        self.assertEqual(self.window.overview_title.text(), "새로 정리할 파일 1개")
        self.assertNotIn("Images", self.window.destination_summary.text())
        self.assertEqual(Organizer(self.organizer.history).settings.view_mode, "simple")

    def test_simple_mode_survives_page_navigation_and_empty_selection(self):
        (self.root / "report.pdf").write_text("report")
        self.use_simple_repeat()
        self.load_folder()
        self.window.nav_buttons[1].click()
        self.window.nav_buttons[0].click()
        self.assertFalse(self.window.stats_widget.isVisible())
        self.assertIs(self.window.preview_stack.currentWidget(), self.window.overview)
        self.window.details_button.click()
        self.window.exclude_all_button.click()
        self.window.details_button.click()
        self.assertFalse(self.window.organize_button.isEnabled())
        self.assertEqual(self.window.overview_title.text(), "이번에 이동할 파일이 없습니다")
        self.assertEqual(self.organizer.jobs(), [])

    def test_view_mode_save_failure_keeps_previous_mode_and_plan(self):
        (self.root / "report.pdf").write_text("report")
        self.load_folder()
        preview = self.window.preview
        with patch.object(self.organizer.settings_store, "save", side_effect=SettingsError("disk full")):
            with patch.object(QMessageBox, "warning") as warning:
                self.window.details_button.click()
                warning.assert_called_once()
        self.assertTrue(self.window.details_button.isChecked())
        self.assertIs(self.window.preview, preview)
        self.assertIs(self.window.preview_stack.currentWidget(), self.window.preview_table)

    def test_existing_user_can_enable_repeat_without_losing_rules(self):
        (self.root / "keep.pdf").write_text("keep")
        (self.root / "photo.png").write_text("photo")
        self.window.apply_preferences(replace(self.organizer.settings, view_mode="simple", excluded_names=("keep-*",)))
        self.wait_until_idle()
        self.window.select_folder(self.root)
        self.wait_until_idle()
        self.assertTrue(self.window.repeat_button.isVisible())
        self.window.repeat_button.click()
        self.wait_until_idle()
        settings = Organizer(self.organizer.history).settings
        self.assertEqual((settings.folder_mode, settings.startup_mode), ("managed", "last"))
        self.assertEqual(settings.last_folder, str(self.root))
        self.assertEqual(settings.excluded_names, ("keep-*",))
        self.assertFalse(self.window.repeat_button.isVisible())
        self.assertTrue((self.root / "photo.png").exists())

    def test_restart_previews_previous_folder_without_user_selection_or_automatic_moves(self):
        (self.root / "first.png").write_text("first")
        self.use_simple_repeat()
        self.window.select_folder(self.root)
        self.wait_until_idle()
        self.window.organize_button.click()
        self.wait_until_idle()
        (self.root / "second.png").write_text("second")
        reopened = MainWindow(Organizer(self.organizer.history))
        try:
            reopened.show()
            self.wait_until_idle(reopened)
            self.assertEqual(reopened.folder, self.root)
            self.assertIs(reopened.preview_stack.currentWidget(), reopened.overview)
            self.assertEqual([item.name for item in reopened.selected_files()], ["second.png"])
            self.assertIn("Images  ·  1개  ·  앱 생성 폴더 재사용", reopened.destination_summary.text())
            self.assertTrue((self.root / "second.png").exists())
            reopened.organize_button.click()
            self.wait_until_idle(reopened)
            self.assertTrue((self.root / "Images/second.png").exists())
            self.assertFalse((self.root / "Images (1)").exists())
        finally:
            self.wait_until_idle(reopened)
            reopened.close()

    def test_simple_summary_uses_collision_resolved_folder_without_touching_user_folder(self):
        (self.root / "PDF").mkdir()
        (self.root / "PDF/keep.pdf").write_text("keep")
        (self.root / "report.pdf").write_text("report")
        self.use_simple_repeat()
        self.load_folder()
        self.assertIn("PDF (1)", self.window.destination_summary.text())
        self.window.organize_button.click()
        self.wait_until_idle()
        self.assertEqual((self.root / "PDF/keep.pdf").read_text(), "keep")
        self.assertTrue((self.root / "PDF (1)/report.pdf").exists())

    def test_completion_button_restores_exact_operation_without_extra_dialog(self):
        (self.root / "report.pdf").write_text("report")
        self.use_simple_repeat()
        self.load_folder()
        self.window.organize_button.click()
        self.wait_until_idle()
        operation_id = self.organizer.latest(self.root)["id"]
        self.assertTrue(self.window.completion_card.isVisible())
        self.assertTrue(self.window.completion_undo_button.isEnabled())
        self.assertEqual(self.window.completion_operation_id, operation_id)
        with patch.object(QMessageBox, "question") as question:
            self.window.completion_undo_button.click()
            self.wait_until_idle()
            question.assert_not_called()
        self.assertTrue((self.root / "report.pdf").exists())
        self.assertFalse((self.root / "PDF").exists())
        self.assertIn("복구 완료", self.window.completion_label.text())
        self.assertFalse(self.window.completion_undo_button.isVisible())
        self.assertTrue(self.window.completion_card.isVisible())

    def test_completion_cannot_undo_newer_external_operation(self):
        (self.root / "first.pdf").write_text("first")
        self.load_folder()
        self.window.organize_button.click()
        self.wait_until_idle()
        (self.root / "second.pdf").write_text("second")
        external = Organizer(self.organizer.history)
        result = external.organize(external.preview(self.root))
        with patch.object(QMessageBox, "warning") as warning:
            self.window.completion_undo_button.click()
            self.wait_until_idle()
            warning.assert_called_once()
        self.assertEqual(external.latest(self.root)["id"], result.operation_id)
        self.assertTrue((self.root / "PDF/first.pdf").exists())
        self.assertTrue((self.root / "PDF (1)/second.pdf").exists())
        self.assertFalse(self.window.completion_card.isVisible())

    def test_completion_is_cleared_when_folder_or_latest_job_changes(self):
        (self.root / "report.pdf").write_text("report")
        self.load_folder()
        self.window.organize_button.click()
        self.wait_until_idle()
        self.window.nav_buttons[3].click()
        self.assertFalse(self.window.completion_card.isVisible())
        self.window.nav_buttons[0].click()
        self.assertTrue(self.window.completion_card.isVisible())
        external = Organizer(self.organizer.history)
        external.undo(self.root)
        self.window.refresh()
        self.wait_until_idle()
        self.assertFalse(self.window.completion_card.isVisible())
        self.window.organize_button.click()
        self.wait_until_idle()
        other = self.base / "Other"
        other.mkdir()
        self.window.select_folder(other)
        self.wait_until_idle()
        self.assertIsNone(self.window.completion_operation_id)
        self.assertFalse(self.window.completion_card.isVisible())

    def test_busy_state_disables_view_switch_repeat_and_immediate_undo(self):
        (self.root / "report.pdf").write_text("report")
        self.load_folder()
        self.window.organize_button.click()
        self.assertFalse(self.window.details_button.isEnabled())
        self.assertFalse(self.window.repeat_button.isEnabled())
        self.assertFalse(self.window.completion_undo_button.isEnabled())
        self.wait_until_idle()

    def test_repeat_shortcut_does_not_discard_unsaved_settings(self):
        (self.root / "report.pdf").write_text("report")
        self.window.apply_preferences(replace(self.organizer.settings, view_mode="simple"))
        self.wait_until_idle()
        self.load_folder()
        page = self.window.settings_page
        self.window.nav_buttons[3].click()
        page.folder_fields["Images"].setText("사진")
        self.window.nav_buttons[0].click()
        self.assertFalse(self.window.repeat_button.isEnabled())
        self.window.enable_repeat()
        self.assertTrue(page.dirty)
        self.assertEqual(page.folder_fields["Images"].text(), "사진")
        self.assertEqual(self.organizer.settings.folder_mode, "new")

    def test_partial_organization_remains_immediately_recoverable(self):
        from cleanfolder.core.filesystem import move_exclusive

        (self.root / "first.pdf").write_text("first")
        (self.root / "second.pdf").write_text("second")
        self.use_simple_repeat()
        self.load_folder()

        def move_first_only(source, *arguments):
            if source.name == "second.pdf":
                raise OSError("file is busy")
            return move_exclusive(source, *arguments)

        with patch("cleanfolder.core.service.move_exclusive", side_effect=move_first_only):
            with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Ok):
                self.window.organize_button.click()
                self.wait_until_idle()
        self.assertTrue(self.window.completion_undo_button.isEnabled())
        self.assertIn("처리하지 못한 항목 1개", self.window.completion_label.text())
        self.assertTrue((self.root / "PDF/first.pdf").exists())
        self.assertTrue((self.root / "second.pdf").exists())
        self.window.completion_undo_button.click()
        self.wait_until_idle()
        self.assertTrue((self.root / "first.pdf").exists())
        self.assertEqual((self.root / "second.pdf").read_text(), "second")
        self.assertIsNone(self.organizer.latest(self.root))

    def test_initial_controls(self):
        self.assertTrue(self.window.choose_button.isEnabled())
        self.assertFalse(self.window.organize_button.isEnabled())
        self.assertFalse(self.window.undo_button.isEnabled())
        self.assertFalse(self.window.trash_button.isEnabled())

    def test_hangul_preview_and_settings_use_the_shared_category(self):
        (self.root / "보고서.hwp").write_text("report")
        (self.root / "계획서.HWPX").write_text("plan")
        self.load_folder()
        self.assertEqual(self.window.preview_table.rowCount(), 2)
        for row in range(2):
            self.assertTrue(self.window.preview_table.item(row, 3).text().startswith("Hangul/"))
        page = self.window.settings_page
        self.assertEqual(page.folder_fields["Hangul"].text(), "Hangul")
        self.assertIn(".hwpx", page.extension_fields["Hangul"].text())
        self.window.organize_button.click()
        self.wait_until_idle()
        self.assertTrue((self.root / "Hangul/보고서.hwp").exists())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.undo_button.click()
        self.wait_until_idle()
        self.assertTrue((self.root / "보고서.hwp").exists())

    def test_unchecked_file_stays_in_place_and_is_not_in_history(self):
        (self.root / "keep.pdf").write_text("keep")
        (self.root / "move.png").write_text("photo")
        self.load_folder()
        self.window.preview_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(self.window.preview_table.item(0, 3).text(), "원래 위치에 유지")
        self.assertEqual(self.window.file_stat.value.text(), "1개")
        self.assertEqual(self.window.size_stat.value.text(), "5 B")
        self.assertEqual(self.window.protected_stat.value.text(), "1개")
        self.window.organize_button.click()
        self.assertFalse(self.window.preview_table.isEnabled())
        self.assertFalse(self.window.select_all_button.isEnabled())
        self.wait_until_idle()
        self.assertEqual((self.root / "keep.pdf").read_text(), "keep")
        self.assertTrue((self.root / "Images/move.png").exists())
        self.assertFalse((self.root / "PDF").exists())
        job = self.organizer.latest(self.root)
        self.assertEqual([action["name"] for action in job["actions"]], ["move.png"])
        self.assertEqual(self.window.preview_table.item(0, 0).checkState(), Qt.CheckState.Unchecked)
        self.assertFalse(self.window.organize_button.isEnabled())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.undo_button.click()
        self.wait_until_idle()
        self.assertEqual((self.root / "keep.pdf").read_text(), "keep")
        self.assertTrue((self.root / "move.png").exists())

    def test_preview_checkbox_can_be_clicked(self):
        (self.root / "report.pdf").write_text("report")
        self.load_folder()
        cell = self.window.preview_table.item(0, 0)
        rectangle = self.window.preview_table.visualItemRect(cell)
        QTest.mouseClick(self.window.preview_table.viewport(), Qt.MouseButton.LeftButton,
                         pos=QPoint(rectangle.left() + 20, rectangle.center().y()))
        self.assertEqual(cell.checkState(), Qt.CheckState.Unchecked)
        self.assertFalse(self.window.organize_button.isEnabled())

    def test_clicking_any_file_row_column_toggles_the_checkbox_once(self):
        (self.root / "report.pdf").write_text("report")
        self.load_folder()
        checkbox = self.window.preview_table.item(0, 0)
        for column in range(4):
            with self.subTest(column=column):
                rectangle = self.window.preview_table.visualItemRect(self.window.preview_table.item(0, column))
                QTest.mouseClick(self.window.preview_table.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
                self.assertEqual(checkbox.checkState(), Qt.CheckState.Unchecked)
                self.assertFalse(self.window.organize_button.isEnabled())
                QTest.mouseClick(self.window.preview_table.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
                self.assertEqual(checkbox.checkState(), Qt.CheckState.Checked)
                self.assertTrue(self.window.organize_button.isEnabled())

    def test_space_key_toggles_current_file_from_any_column(self):
        (self.root / "report.pdf").write_text("report")
        self.load_folder()
        for column in range(4):
            with self.subTest(column=column):
                self.window.preview_table.setCurrentCell(0, column)
                QTest.keyClick(self.window.preview_table, Qt.Key.Key_Space)
                self.assertEqual(len(self.window.selected_files()), 0)
                QTest.keyClick(self.window.preview_table, Qt.Key.Key_Space)
                self.assertEqual(len(self.window.selected_files()), 1)

    def test_right_click_empty_area_and_drag_do_not_change_file_selection(self):
        (self.root / "first.pdf").write_text("first")
        (self.root / "second.pdf").write_text("second")
        self.load_folder()
        table = self.window.preview_table
        first = table.visualItemRect(table.item(0, 0)).center()
        second = table.visualItemRect(table.item(1, 0)).center()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.RightButton, pos=first)
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(20, table.viewport().height() - 3))
        self.assertEqual(len(self.window.selected_files()), 2)
        QTest.mousePress(table.viewport(), Qt.MouseButton.LeftButton, pos=first)
        QTest.mouseMove(table.viewport(), second)
        QTest.mouseRelease(table.viewport(), Qt.MouseButton.LeftButton, pos=second)
        self.assertEqual(len(self.window.selected_files()), 2)

    def test_simple_file_selection_button_opens_clickable_list_and_preserves_choice(self):
        (self.root / "keep.pdf").write_text("keep")
        (self.root / "move.png").write_text("move")
        self.use_simple_repeat()
        self.load_folder()
        self.assertEqual(self.window.details_button.text(), "파일 선택")
        self.window.details_button.click()
        rectangle = self.window.preview_table.visualItemRect(self.window.preview_table.item(0, 0))
        QTest.mouseClick(self.window.preview_table.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        self.assertEqual([item.name for item in self.window.selected_files()], ["move.png"])
        self.window.details_button.click()
        self.assertIs(self.window.preview_stack.currentWidget(), self.window.overview)
        self.assertNotIn("PDF", self.window.destination_summary.text())
        self.window.organize_button.click()
        self.wait_until_idle()
        self.assertEqual((self.root / "keep.pdf").read_text(), "keep")
        self.assertTrue((self.root / "Images/move.png").exists())
        self.assertEqual([action["name"] for action in self.organizer.latest(self.root)["actions"]], ["move.png"])

    def test_row_click_is_ignored_during_a_background_operation(self):
        (self.root / "report.pdf").write_text("report")
        self.load_folder()
        rectangle = self.window.preview_table.visualItemRect(self.window.preview_table.item(0, 0))
        self.window.organize_button.click()
        QTest.mouseClick(self.window.preview_table.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        self.wait_until_idle()
        self.assertTrue((self.root / "PDF/report.pdf").exists())

    def test_exclude_all_is_noop_and_select_all_restores_selection(self):
        (self.root / "report.pdf").write_text("report")
        (self.root / "existing").mkdir()
        self.load_folder()
        self.window.exclude_all_button.click()
        self.assertFalse(self.window.organize_button.isEnabled())
        self.assertEqual(self.window.file_stat.value.text(), "0개")
        self.assertEqual(self.window.size_stat.value.text(), "0 B")
        self.assertEqual(self.window.protected_stat.value.text(), "2개")
        self.window.organize()
        self.assertIsNone(self.window.task)
        self.assertEqual(self.organizer.jobs(self.root), [])
        self.assertFalse((self.root / "PDF").exists())
        self.window.select_all_button.click()
        self.assertTrue(self.window.organize_button.isEnabled())
        self.assertEqual(self.window.preview_table.item(0, 3).text(), "PDF/report.pdf")
        self.assertEqual(self.window.preview_table.item(0, 0).checkState(), Qt.CheckState.Checked)

    def test_exclusion_survives_refresh_and_new_files_are_selected(self):
        (self.root / "keep.pdf").write_text("keep")
        self.load_folder()
        self.window.exclude_all_button.click()
        (self.root / "new.pdf").write_text("new")
        self.window.refresh_button.click()
        self.wait_until_idle()
        self.assertEqual([item.name for item in self.window.selected_files()], ["new.pdf"])
        self.window.nav_buttons[1].click()
        self.window.nav_buttons[0].click()
        self.assertEqual(self.window.preview_table.item(0, 0).checkState(), Qt.CheckState.Unchecked)

    def test_folder_change_resets_temporary_exclusions(self):
        (self.root / "same.pdf").write_text("first")
        self.load_folder()
        self.window.exclude_all_button.click()
        other = self.base / "Other"
        other.mkdir()
        (other / "same.pdf").write_text("second")
        self.window.select_folder(other)
        self.wait_until_idle()
        self.assertEqual([item.name for item in self.window.selected_files()], ["same.pdf"])
        self.window.select_folder(self.root)
        self.wait_until_idle()
        self.assertEqual([item.name for item in self.window.selected_files()], ["same.pdf"])

    def test_temporary_exclusions_do_not_change_settings(self):
        (self.root / "keep.pdf").write_text("keep")
        self.load_folder()
        self.window.exclude_all_button.click()
        self.assertEqual(self.organizer.settings.excluded_names, ())
        reopened = MainWindow(Organizer(self.organizer.history))
        try:
            reopened.show_snapshot((self.organizer.preview(self.root), [], []))
            self.assertEqual(len(reopened.selected_files()), 1)
        finally:
            reopened.close()

    def test_settings_change_keeps_temporary_exclusions(self):
        (self.root / "keep.pdf").write_text("keep")
        self.load_folder()
        self.window.exclude_all_button.click()
        self.window.apply_preferences(replace(self.organizer.settings, theme="dark"))
        self.wait_until_idle()
        self.assertEqual(self.window.preview_table.item(0, 0).checkState(), Qt.CheckState.Unchecked)
        self.assertFalse(self.window.organize_button.isEnabled())

    def test_excluded_file_change_does_not_block_selected_files(self):
        keep = self.root / "keep.pdf"
        keep.write_text("keep")
        (self.root / "move.png").write_text("photo")
        self.load_folder()
        self.window.preview_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        keep.write_text("editing in progress")
        self.window.organize_button.click()
        self.wait_until_idle()
        self.assertEqual(keep.read_text(), "editing in progress")
        self.assertTrue((self.root / "Images/move.png").exists())

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

    def test_gui_can_undo_mcp_organization(self):
        (self.root / "report.pdf").write_text("report")
        tools = FolderTools(Organizer(self.organizer.history), PathAllowlist([self.root]))
        preview = tools.preview_organization(str(self.root))
        tools.organize_files(preview["preview_id"], approved=True)
        self.load_folder()
        self.assertEqual(self.window.history_table.rowCount(), 1)
        self.assertTrue(self.window.undo_button.isEnabled())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.undo_button.click()
        self.wait_until_idle()
        self.assertEqual((self.root / "report.pdf").read_text(), "report")
        self.assertFalse((self.root / "PDF").exists())

    def test_mcp_can_undo_gui_organization(self):
        (self.root / "report.pdf").write_text("report")
        self.load_folder()
        self.window.organize_button.click()
        self.wait_until_idle()
        tools = FolderTools(Organizer(self.organizer.history), PathAllowlist([self.root]))
        operation = tools.scan_folder(str(self.root))["latest_operation_id"]
        result = tools.undo_last_operation(str(self.root), operation, approved=True)
        self.assertEqual(result["completed"], 1)
        self.window.refresh()
        self.wait_until_idle()
        self.assertFalse(self.window.undo_button.isEnabled())
        self.assertEqual(self.window.preview_table.rowCount(), 1)
        self.assertEqual((self.root / "report.pdf").read_text(), "report")

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

    def test_settings_save_refreshes_preview_and_persists(self):
        (self.root / "photo.png").write_text("photo")
        (self.root / "keep.pdf").write_text("keep")
        self.load_folder()
        self.window.nav_buttons[3].click()
        self.assertFalse(self.window.folder_card.isVisible())
        self.assertFalse(self.window.footer.isVisible())
        page = self.window.settings_page
        page.folder_fields["Images"].setText("사진")
        page.excluded_names.setPlainText("keep.pdf")
        page.save_button.click()
        self.assertFalse(self.window.nav_buttons[3].isEnabled())
        self.wait_until_idle()
        self.assertFalse(page.dirty)
        self.assertEqual(self.window.tabs.currentIndex(), 3)
        self.assertEqual(self.window.preview_table.rowCount(), 1)
        self.assertEqual(self.window.preview_table.item(0, 3).text(), "사진/photo.png")
        self.assertEqual(Organizer(self.organizer.history).settings.folder_names["Images"], "사진")
        self.assertTrue((self.root / "photo.png").exists())

    def test_settings_invalid_draft_and_cancel(self):
        page = self.window.settings_page
        page.folder_fields["Images"].setText("../unsafe")
        page.save_button.click()
        self.assertTrue(page.dirty)
        self.assertIn("사용할 수 없는", page.feedback.text())
        self.assertEqual(self.organizer.settings.folder_names["Images"], "Images")
        page.cancel_button.click()
        self.assertFalse(page.dirty)
        self.assertEqual(page.folder_fields["Images"].text(), "Images")

    def test_defaults_are_only_a_draft_until_saved(self):
        self.window.apply_preferences(replace(Settings(), theme="dark"))
        page = self.window.settings_page
        page.defaults_button.click()
        self.assertTrue(page.dirty)
        self.assertEqual(page.appearance.currentData(), "system")
        self.assertEqual(self.organizer.settings.theme, "dark")
        page.cancel_button.click()
        self.assertEqual(page.appearance.currentData(), "dark")

    def test_settings_write_failure_leaves_preferences_and_draft_intact(self):
        page = self.window.settings_page
        page.appearance.setCurrentIndex(page.appearance.findData("dark"))
        with patch.object(self.organizer.settings_store, "save", side_effect=SettingsError("disk full")):
            with patch.object(QMessageBox, "warning") as warning:
                page.save_button.click()
                warning.assert_called_once()
        self.assertEqual(self.organizer.settings.theme, "system")
        self.assertTrue(page.dirty)

    def test_forced_theme_ignores_system_palette(self):
        original = QPalette(self.application.palette())
        try:
            self.window.apply_preferences(replace(Settings(), theme="dark"))
            palette = QPalette(original)
            palette.setColor(QPalette.ColorRole.Window, QColor("#FFFFFF"))
            self.application.setPalette(palette)
            self.application.processEvents()
            self.assertTrue(self.window._theme_dark)
            self.window.apply_preferences(replace(Settings(), theme="system"))
            self.assertFalse(self.window._theme_dark)
        finally:
            self.application.setPalette(original)
            self.application.processEvents()

    def test_settings_lock_conflict_is_shown_without_discarding_draft(self):
        page = self.window.settings_page
        page.folder_fields["Images"].setText("사진")
        with patch.object(self.organizer, "apply_settings", side_effect=SafetyError("다른 작업이 진행 중입니다")):
            with patch.object(QMessageBox, "warning") as warning:
                page.save_button.click()
                warning.assert_called_once()
        self.assertTrue(page.dirty)
        self.assertEqual(self.organizer.settings.folder_names["Images"], "Images")

    def test_selected_folder_is_remembered_without_losing_draft(self):
        page = self.window.settings_page
        page.folder_fields["Images"].setText("사진")
        with patch("cleanfolder.desktop.window.QFileDialog.getExistingDirectory", return_value=str(self.root)):
            self.window.choose_folder()
        self.wait_until_idle()
        self.assertTrue(page.dirty)
        self.assertEqual(page.folder_fields["Images"].text(), "사진")
        page.save_button.click()
        self.wait_until_idle()
        self.assertEqual(Organizer(self.organizer.history).settings.last_folder, str(self.root))

    def test_startup_folder_only_previews_and_missing_folder_is_safe(self):
        (self.root / "report.pdf").write_text("report")
        self.organizer.apply_settings(replace(Settings(), startup_mode="default", default_folder=str(self.root)))
        self.window.load_startup_folder()
        self.wait_until_idle()
        self.assertEqual(self.window.preview_table.rowCount(), 1)
        self.assertTrue((self.root / "report.pdf").exists())
        self.assertFalse((self.root / "PDF").exists())
        self.organizer.apply_settings(replace(Settings(), startup_mode="default", default_folder=str(self.base / "missing")))
        self.window.load_startup_folder()
        self.assertIn("시작 폴더를 찾을 수 없습니다", self.window.statusBar().currentMessage())
        self.assertTrue(self.window.choose_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
