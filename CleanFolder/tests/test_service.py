import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cleanfolder.categories import CATEGORIES, classify
from cleanfolder.filesystem import SafetyError, available_name, identity, move_exclusive
from cleanfolder.history import HistoryStore, HistoryWriteError
from cleanfolder.service import Organizer


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "Downloads"
        self.root.mkdir()
        self.store = HistoryStore(self.base / "history")
        self.organizer = Organizer(self.store)

    def file(self, name, content="sample"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def organize(self):
        return self.organizer.organize(self.organizer.preview(self.root))

    def test_all_categories_and_extensions(self):
        for category, extensions in CATEGORIES.items():
            for extension in extensions:
                with self.subTest(extension=extension):
                    self.assertEqual(classify("FILE" + extension.upper()), category)
        self.assertEqual(classify("unknown.custom"), "Others")
        self.assertEqual(classify("no-extension"), "Others")

    def test_preview_is_read_only_and_non_recursive(self):
        self.file("report.docx")
        self.file("existing/nested.pdf")
        self.file(".hidden.txt")
        self.file("empty.pkg/inside.txt")
        (self.root / "link.txt").symlink_to(self.root / "report.docx")
        (self.root / "folder-link").symlink_to(self.root / "existing", target_is_directory=True)
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        preview = self.organizer.preview(self.root)
        self.assertEqual([item.name for item in preview.files], ["report.docx"])
        self.assertEqual(preview.skipped, 5)
        self.assertEqual(sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")), before)
        self.assertEqual(self.store.jobs(), [])

    def test_existing_category_directory_is_never_used(self):
        self.file("Images/old.png", "old")
        self.file("photo.png", "new")
        self.assertEqual(self.organizer.preview(self.root).files[0].folder, "Images (1)")
        self.assertEqual(self.organize().completed, 1)
        self.assertEqual((self.root / "Images/old.png").read_text(), "old")
        self.assertEqual((self.root / "Images (1)/photo.png").read_text(), "new")
        self.assertEqual(self.organizer.undo(self.root).completed, 1)
        self.assertTrue((self.root / "Images").is_dir())
        self.assertFalse((self.root / "Images (1)").exists())

    def test_existing_category_symlink_is_never_followed(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "PDF").symlink_to(outside, target_is_directory=True)
        self.file("book.pdf")
        self.organize()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue((self.root / "PDF (1)/book.pdf").is_file())

    def test_installers_are_moved_without_deletion(self):
        for extension in ("dmg", "pkg", "msi", "exe", "iso"):
            self.file(f"setup.{extension}", extension)
        self.assertEqual(self.organize().completed, 5)
        for extension in ("dmg", "pkg", "msi", "exe", "iso"):
            self.assertEqual((self.root / f"Installers/setup.{extension}").read_text(), extension)

    def test_persistent_history_and_undo(self):
        self.file("문서.docx", "내용")
        self.file("song.mp3")
        self.organize()
        reopened = Organizer(HistoryStore(self.store.directory))
        result = reopened.undo(self.root)
        self.assertEqual(result.completed, 2)
        self.assertEqual(result.issues, [])
        self.assertEqual((self.root / "문서.docx").read_text(), "내용")
        self.assertFalse((self.root / "Word").exists())
        self.assertFalse((self.root / "Audio").exists())
        self.assertEqual(reopened.undo(self.root).completed, 0)

    def test_undo_renames_collision_without_overwriting(self):
        self.file("report.pdf", "original")
        self.organize()
        self.file("report.pdf", "new")
        self.file("report (1).pdf", "also new")
        self.assertEqual(self.organizer.undo(self.root).completed, 1)
        self.assertEqual((self.root / "report.pdf").read_text(), "new")
        self.assertEqual((self.root / "report (1).pdf").read_text(), "also new")
        self.assertEqual((self.root / "report (2).pdf").read_text(), "original")

    def test_collision_case_and_unicode_normalization(self):
        self.file("PHOTO.PNG")
        self.file("café.txt")
        self.assertEqual(available_name(self.root, "photo.png"), "photo (1).png")
        self.assertEqual(available_name(self.root, "cafe\u0301.txt"), "cafe\u0301 (1).txt")

    def test_exclusive_move_does_not_overwrite(self):
        source = self.file("source.txt", "source")
        destination = self.file("destination.txt", "destination")
        with self.assertRaises(FileExistsError):
            move_exclusive(source, destination, identity(source))
        self.assertEqual(source.read_text(), "source")
        self.assertEqual(destination.read_text(), "destination")

    def test_exclusive_move_rejects_changed_parent(self):
        source = self.file("source.txt")
        target_folder = self.root / "target"
        target_folder.mkdir()
        with self.assertRaises(SafetyError):
            move_exclusive(source, target_folder / source.name, identity(source),
                           identity(self.root), [0, 0])
        self.assertTrue(source.is_file())
        self.assertEqual(list(target_folder.iterdir()), [])

    def test_failed_source_unlink_rolls_back_link(self):
        source = self.file("source.txt")
        destination = self.root / "destination.txt"
        original_unlink = os.unlink

        def fail_source(path, **kwargs):
            if path == "source.txt":
                raise PermissionError("source locked")
            return original_unlink(path, **kwargs)

        with patch("cleanfolder.filesystem.os.unlink", side_effect=fail_source):
            with self.assertRaises(PermissionError):
                move_exclusive(source, destination, identity(source))
        self.assertTrue(source.is_file())
        self.assertFalse(destination.exists())

    def test_empty_preview_makes_no_job(self):
        self.assertEqual(self.organize().completed, 0)
        self.assertEqual(self.store.jobs(), [])

    def test_changed_file_invalidates_preview(self):
        source = self.file("photo.png")
        preview = self.organizer.preview(self.root)
        source.write_text("updated file contents")
        with self.assertRaises(SafetyError):
            self.organizer.organize(preview)
        self.assertTrue(source.exists())
        self.assertFalse((self.root / "Images").exists())

    def test_late_directory_collision_invalidates_preview(self):
        self.file("photo.png")
        preview = self.organizer.preview(self.root)
        self.file("Images/user.png", "user")
        with self.assertRaises(SafetyError):
            self.organizer.organize(preview)
        self.assertTrue((self.root / "photo.png").exists())
        self.assertEqual((self.root / "Images/user.png").read_text(), "user")

    def test_new_files_after_preview_stay_in_place(self):
        self.file("first.txt")
        preview = self.organizer.preview(self.root)
        self.file("second.txt")
        self.assertEqual(self.organizer.organize(preview).completed, 1)
        self.assertTrue((self.root / "second.txt").is_file())

    def test_missing_file_during_undo_reports_partial_result(self):
        self.file("first.pdf")
        self.file("second.txt")
        self.organize()
        (self.root / "PDF/first.pdf").unlink()
        result = self.organizer.undo(self.root)
        self.assertEqual(result.completed, 1)
        self.assertEqual(len(result.issues), 1)
        self.assertTrue((self.root / "second.txt").is_file())
        self.assertIsNotNone(self.organizer.latest(self.root))

    def test_replaced_file_during_undo_is_untouched(self):
        self.file("first.pdf", "original")
        self.organize()
        moved = self.root / "PDF/first.pdf"
        moved.rename(self.base / "keep-original.pdf")
        moved.write_text("replacement")
        result = self.organizer.undo(self.root)
        self.assertEqual(result.completed, 0)
        self.assertTrue(result.issues)
        self.assertEqual(moved.read_text(), "replacement")

    def test_nonempty_generated_folder_is_retained(self):
        self.file("photo.png")
        self.organize()
        self.file("Images/user.txt", "user")
        self.organizer.undo(self.root)
        self.assertEqual((self.root / "Images/user.txt").read_text(), "user")

    def test_replaced_folder_symlink_blocks_undo(self):
        self.file("photo.png")
        self.organize()
        outside = self.base / "moved-folder"
        (self.root / "Images").rename(outside)
        (self.root / "Images").symlink_to(outside, target_is_directory=True)
        result = self.organizer.undo(self.root)
        self.assertEqual(result.completed, 0)
        self.assertTrue(result.issues)
        self.assertTrue((outside / "photo.png").is_file())

    def test_replaced_root_blocks_undo(self):
        self.file("photo.png")
        self.organize()
        self.root.rename(self.base / "old-root")
        self.root.mkdir()
        with self.assertRaises(SafetyError):
            self.organizer.undo(self.root)

    def test_multiple_jobs_undo_latest_first(self):
        self.file("first.txt")
        self.organize()
        self.file("second.txt")
        self.organize()
        self.organizer.undo(self.root)
        self.assertTrue((self.root / "second.txt").is_file())
        self.assertTrue((self.root / "Text/first.txt").is_file())
        self.organizer.undo(self.root)
        self.assertTrue((self.root / "first.txt").is_file())

    def test_failed_link_keeps_source_and_can_be_reconciled(self):
        self.file("file.txt")
        with patch("cleanfolder.filesystem.os.link", side_effect=OSError("unsupported")):
            result = self.organize()
        self.assertEqual(result.completed, 0)
        self.assertTrue(result.issues)
        self.assertTrue((self.root / "file.txt").is_file())
        self.assertEqual(self.organizer.undo(self.root).issues, [])
        self.assertFalse((self.root / "Text").exists())

    def test_write_failure_before_move_keeps_source(self):
        self.file("file.txt")
        with patch.object(self.store, "save", side_effect=HistoryWriteError("disk full")):
            with self.assertRaises(HistoryWriteError):
                self.organize()
        self.assertTrue((self.root / "file.txt").is_file())

    def test_temporary_history_write_failure_stops_operation(self):
        self.file("file.txt")
        with patch("cleanfolder.history.tempfile.mkstemp", side_effect=OSError("disk full")):
            with self.assertRaises(HistoryWriteError):
                self.organize()
        self.assertTrue((self.root / "file.txt").is_file())

    def test_history_write_failure_during_undo_stops_safely(self):
        self.file("file.txt")
        self.organize()
        with patch.object(self.store, "save", side_effect=HistoryWriteError("disk full")):
            with self.assertRaises(HistoryWriteError):
                self.organizer.undo(self.root)
        self.assertTrue((self.root / "Text/file.txt").is_file())
        self.assertFalse((self.root / "file.txt").exists())
        self.assertEqual(self.organizer.undo(self.root).completed, 1)

    def test_pending_move_after_interruption_can_be_undone(self):
        self.file("file.txt")
        original_save = self.store.save

        def interrupt(job):
            if job["actions"] and job["actions"][0]["state"] == "moved":
                raise HistoryWriteError("simulated interruption")
            original_save(job)

        with patch.object(self.store, "save", side_effect=interrupt):
            with self.assertRaises(HistoryWriteError):
                self.organize()
        self.assertEqual(self.store.jobs()[0]["actions"][0]["state"], "pending")
        self.assertEqual(self.organizer.undo(self.root).completed, 1)
        self.assertTrue((self.root / "file.txt").is_file())

    def test_interrupted_link_with_both_names_is_reconciled(self):
        self.file("file.txt")
        self.organize()
        job = self.store.jobs()[0]
        job["actions"][0]["state"] = "pending"
        self.store.save(job)
        os.link(self.root / "Text/file.txt", self.root / "file.txt")
        self.assertEqual(self.organizer.undo(self.root).completed, 1)
        self.assertEqual((self.root / "file.txt").read_text(), "sample")
        self.assertFalse((self.root / "Text").exists())

    def test_interrupted_restore_is_reconciled(self):
        self.file("file.txt")
        self.organize()
        job = self.store.jobs()[0]
        action = job["actions"][0]
        action["state"] = "restoring"
        action["restore_name"] = "file (1).txt"
        self.store.save(job)
        (self.root / "Text/file.txt").rename(self.root / "file (1).txt")
        result = self.organizer.undo(self.root)
        self.assertEqual(result.issues, [])
        self.assertTrue((self.root / "file (1).txt").is_file())
        self.assertIsNone(self.organizer.latest(self.root))

    def test_installer_list_excludes_existing_directory_content(self):
        self.file("Installers/old.dmg")
        self.file("top.pkg")
        self.assertEqual([item.path.name for item in self.organizer.installers(self.root)], ["top.pkg"])
        self.organize()
        self.assertEqual([item.path.name for item in self.organizer.installers(self.root)], ["top.pkg"])

    def test_only_selected_installers_are_trashed(self):
        self.file("first.dmg")
        self.file("second.pkg")
        self.file("document.pdf")
        self.organize()
        selected = [item for item in self.organizer.installers(self.root) if item.path.name == "first.dmg"]
        calls = []

        def fake_trash(path):
            calls.append(path)
            Path(path).rename(self.base / "trashed.dmg")

        result = self.organizer.trash(self.root, selected, fake_trash)
        self.assertEqual(result.completed, 1)
        self.assertEqual(calls, [str(selected[0].path)])
        self.assertTrue((self.root / "Installers/second.pkg").is_file())
        self.assertTrue((self.root / "PDF/document.pdf").is_file())
        self.assertEqual(self.organizer.undo(self.root).completed, 2)
        self.assertEqual((self.base / "trashed.dmg").read_text(), "sample")

    def test_trash_failure_leaves_file_recoverable(self):
        self.file("setup.dmg")
        self.organize()
        selected = self.organizer.installers(self.root)
        result = self.organizer.trash(self.root, selected, lambda path: self.raise_os_error())
        self.assertEqual(result.completed, 0)
        self.assertTrue(result.issues)
        self.assertEqual(self.store.jobs()[0]["actions"][0]["state"], "moved")
        self.assertEqual(self.organizer.undo(self.root).completed, 1)

    def raise_os_error(self):
        raise OSError("trash unavailable")

    def test_interrupted_trash_is_reconciled(self):
        self.file("setup.dmg")
        self.organize()
        job = self.store.jobs()[0]
        job["actions"][0]["state"] = "trashing"
        self.store.save(job)
        (self.root / "Installers/setup.dmg").rename(self.base / "trash.dmg")
        self.assertEqual(self.organizer.undo(self.root).issues, [])
        self.assertFalse((self.root / "Installers").exists())

    def test_selection_stale_after_replacement_is_rejected(self):
        source = self.file("setup.dmg")
        selected = self.organizer.installers(self.root)
        source.rename(self.base / "original.dmg")
        source.write_text("replacement")
        calls = []
        result = self.organizer.trash(self.root, selected, calls.append)
        self.assertEqual(calls, [])
        self.assertTrue(result.issues)
        self.assertTrue(source.is_file())

    def test_concurrent_operation_is_rejected(self):
        self.file("photo.png")
        with self.store.locked():
            with self.assertRaises(SafetyError):
                self.organize()

    def test_history_directory_is_protected(self):
        with self.assertRaises(SafetyError):
            self.organizer.preview(self.store.directory)

    def test_ancestor_of_history_only_scans_top_level_files(self):
        preview = self.organizer.preview(self.base)
        self.assertEqual(preview.files, ())
        self.assertEqual(preview.skipped, 2)

    def test_corrupt_history_is_reported(self):
        (self.store.directory / "bad.json").write_text("invalid")
        with self.assertRaises(SafetyError):
            self.store.jobs()

    def test_path_traversal_in_history_is_rejected(self):
        self.file("file.txt")
        self.organize()
        job = self.store.jobs()[0]
        job["actions"][0]["name"] = "../outside.txt"
        self.store.save(job)
        with self.assertRaises(SafetyError):
            self.organizer.undo(self.root)
        self.assertTrue((self.root / "Text/file.txt").is_file())


if __name__ == "__main__":
    unittest.main()
