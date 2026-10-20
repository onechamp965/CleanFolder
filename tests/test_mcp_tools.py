import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from cleanfolder.core.filesystem import SafetyError
from cleanfolder.core.history import HistoryStore
from cleanfolder.core.path_validator import PathAllowlist
from cleanfolder.core.service import Organizer
from cleanfolder.mcp_server.tools import FolderTools


class FolderToolsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "Downloads"
        self.root.mkdir()
        self.organizer = Organizer(HistoryStore(self.base / "history"))
        self.tools = FolderTools(self.organizer, PathAllowlist([self.root]))

    def preview(self, **kwargs):
        return self.tools.preview_organization(str(self.root), **kwargs)

    def organize(self):
        return self.tools.organize_files(self.preview()["preview_id"], approved=True)

    def test_scan_and_preview_only_read_top_level_regular_files(self):
        (self.root / "report.pdf").write_text("report")
        (self.root / ".hidden").write_text("hidden")
        (self.root / "PDF").mkdir()
        (self.root / "PDF/keep.pdf").write_text("keep")
        (self.root / "alias.pdf").symlink_to(self.root / "PDF/keep.pdf")
        original_iterdir = Path.iterdir

        def forbid_existing_folder(path):
            self.assertNotEqual(path, self.root / "PDF")
            return original_iterdir(path)

        with patch.object(Path, "iterdir", forbid_existing_folder):
            scan = self.tools.scan_folder(str(self.root))
            preview = self.preview()
            self.assertEqual(scan["files"], [{"name": "report.pdf", "category": "PDF", "size": 6}])
            self.assertEqual(scan["skipped"], 3)
            self.assertEqual(preview["moves"][0]["destination"], "PDF (1)/report.pdf")
            self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertEqual((self.root / "PDF/keep.pdf").read_text(), "keep")

    def test_managed_gui_folders_are_not_reused_by_mcp(self):
        self.organizer.apply_settings(replace(self.organizer.settings, folder_mode="managed"))
        (self.root / "first.pdf").write_text("first")
        self.organizer.organize(self.organizer.preview(self.root))
        (self.root / "second.pdf").write_text("second")
        self.assertEqual(self.organizer.preview(self.root).files[0].folder, "PDF")
        preview = self.preview()
        self.assertEqual(preview["moves"][0]["destination"], "PDF (1)/second.pdf")
        self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertEqual((self.root / "PDF/first.pdf").read_text(), "first")

    def test_hangul_scan_preview_organize_and_undo(self):
        for name in ("보고서.hwp", "계획서.HWPX"):
            (self.root / name).write_text(name)
        scan = self.tools.scan_folder(str(self.root))
        self.assertEqual([item["category"] for item in scan["files"]], ["Hangul", "Hangul"])
        preview = self.preview()
        self.assertTrue(all(item["destination"].startswith("Hangul/") for item in preview["moves"]))
        result = self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertEqual(result["completed"], 2)
        restored = self.tools.undo_last_operation(str(self.root), result["operation_id"], approved=True)
        self.assertEqual(restored["completed"], 2)


    def test_selection_is_bound_to_the_approved_preview(self):
        (self.root / "keep.dmg").write_text("installer")
        (self.root / "move.pdf").write_text("report")
        preview = self.preview(include_names=["move.pdf"])
        with self.assertRaises(SafetyError):
            self.tools.organize_files(preview["preview_id"])
        self.assertTrue((self.root / "move.pdf").exists())
        result = self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertEqual(result["completed"], 1)
        self.assertTrue((self.root / "keep.dmg").exists())
        with self.assertRaises(SafetyError):
            self.tools.organize_files(preview["preview_id"], approved=True)

    def test_empty_selection_is_noop_and_unknown_names_are_rejected(self):
        (self.root / "report.pdf").write_text("report")
        for names in (["../report.pdf"], ["missing.pdf"]):
            with self.assertRaises(SafetyError):
                self.preview(include_names=names)
        preview = self.preview(include_names=[])
        result = self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertEqual(result["completed"], 0)
        self.assertIsNone(result["operation_id"])
        self.assertEqual(self.organizer.jobs(), [])

    def test_expired_unknown_and_evicted_previews_are_rejected(self):
        (self.root / "report.pdf").write_text("report")
        with patch("cleanfolder.mcp_server.tools.time.monotonic", return_value=10):
            preview = self.preview()
        with patch("cleanfolder.mcp_server.tools.time.monotonic", return_value=311):
            with self.assertRaises(SafetyError):
                self.tools.organize_files(preview["preview_id"], approved=True)
        with self.assertRaises(SafetyError):
            self.tools.organize_files("invented", approved=True)
        self.tools.preview_limit = 1
        first = self.preview()
        self.preview()
        with self.assertRaises(SafetyError):
            self.tools.organize_files(first["preview_id"], approved=True)
        self.assertTrue((self.root / "report.pdf").exists())

    def test_changed_file_and_new_destination_block_execution(self):
        source = self.root / "report.pdf"
        source.write_text("report")
        preview = self.preview()
        source.write_text("modified report")
        with self.assertRaises(SafetyError):
            self.tools.organize_files(preview["preview_id"], approved=True)
        preview = self.preview()
        (self.root / "PDF").mkdir()
        with self.assertRaises(SafetyError):
            self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertEqual(source.read_text(), "modified report")
        self.assertEqual(self.organizer.jobs(), [])

    def test_file_added_after_preview_is_not_moved(self):
        (self.root / "first.pdf").write_text("first")
        preview = self.preview()
        (self.root / "later.pdf").write_text("later")
        self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertEqual((self.root / "later.pdf").read_text(), "later")

    def test_external_settings_change_requires_new_preview(self):
        (self.root / "report.pdf").write_text("report")
        preview = self.preview()
        gui = Organizer(self.organizer.history)
        gui.apply_settings(replace(gui.settings, excluded_names=("report.pdf",)))
        with self.assertRaises(SafetyError):
            self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertEqual(self.preview()["count"], 0)

    def test_undo_uses_shared_history_after_restart_and_preserves_collisions(self):
        (self.root / "report.pdf").write_text("original")
        result = self.organize()
        restarted = FolderTools(Organizer(self.organizer.history), PathAllowlist([self.root]))
        self.assertEqual(restarted.scan_folder(str(self.root))["latest_operation_id"], result["operation_id"])
        (self.root / "report.pdf").write_text("new")
        with self.assertRaises(SafetyError):
            restarted.undo_last_operation(str(self.root), result["operation_id"])
        restored = restarted.undo_last_operation(str(self.root), result["operation_id"], approved=True)
        self.assertEqual(restored["completed"], 1)
        self.assertEqual((self.root / "report.pdf").read_text(), "new")
        self.assertEqual((self.root / "report (1).pdf").read_text(), "original")
        self.assertFalse((self.root / "PDF").exists())

    def test_undo_refuses_a_different_latest_operation(self):
        (self.root / "first.pdf").write_text("first")
        first = self.organize()
        (self.root / "second.pdf").write_text("second")
        second = self.organize()
        with self.assertRaises(SafetyError):
            self.tools.undo_last_operation(str(self.root), first["operation_id"], approved=True)
        self.assertEqual(self.organizer.latest(self.root)["id"], second["operation_id"])

    def test_history_lock_conflict_does_not_move_files(self):
        (self.root / "report.pdf").write_text("report")
        preview = self.preview()
        with self.organizer.history.locked():
            with self.assertRaises(SafetyError):
                self.tools.organize_files(preview["preview_id"], approved=True)
        self.assertTrue((self.root / "report.pdf").exists())

    def test_all_path_tools_reject_unlisted_folders(self):
        outside = self.base / "outside"
        outside.mkdir()
        for folder in (outside, self.root / "child", self.base / "Downloads-extra"):
            for call in (self.tools.scan_folder, self.tools.preview_organization):
                with self.assertRaises(SafetyError):
                    call(str(folder))
            with self.assertRaises(SafetyError):
                self.tools.undo_last_operation(str(folder), "id", approved=True)

    def test_allowlist_rejects_empty_relative_traversal_and_symlink_paths(self):
        with self.assertRaises(SafetyError):
            PathAllowlist([])
        for folder in (Path("Downloads"), self.root / ".." / "Downloads"):
            with self.assertRaises(SafetyError):
                PathAllowlist([folder])
        alias = self.base / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        for folder in (alias, alias / "nested"):
            with self.assertRaises((SafetyError, OSError)):
                PathAllowlist([folder])
        with self.assertRaises(SafetyError):
            self.tools.scan_folder(str(alias))

    def test_allowlist_revalidates_replaced_root(self):
        (self.root / "report.pdf").write_text("report")
        preview = self.preview()
        moved = self.base / "original"
        self.root.rename(moved)
        self.root.mkdir()
        (self.root / "report.pdf").write_text("replacement")
        with self.assertRaises(SafetyError):
            self.tools.organize_files(preview["preview_id"], approved=True)
        with self.assertRaises(SafetyError):
            self.tools.scan_folder(str(self.root))
        self.assertEqual((moved / "report.pdf").read_text(), "report")

    def test_allowlist_revalidates_symlinked_ancestor(self):
        parent = self.base / "parent"
        parent.mkdir()
        child = parent / "child"
        child.mkdir()
        allowlist = PathAllowlist([child])
        original = self.base / "original"
        parent.rename(original)
        parent.symlink_to(original, target_is_directory=True)
        with self.assertRaises(SafetyError):
            allowlist.validate(child)

    def test_registered_child_requires_explicit_registration(self):
        child = self.root / "child"
        child.mkdir()
        with self.assertRaises(SafetyError):
            self.tools.scan_folder(str(child))
        allowed = FolderTools(self.organizer, PathAllowlist([self.root, child]))
        self.assertEqual(allowed.scan_folder(str(child))["count"], 0)


if __name__ == "__main__":
    unittest.main()
