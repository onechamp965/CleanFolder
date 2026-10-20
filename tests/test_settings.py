import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from cleanfolder.core.filesystem import SafetyError
from cleanfolder.core.history import HistoryStore
from cleanfolder.core.service import Organizer
from cleanfolder.core.settings import Settings, SettingsError, SettingsStore


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "Downloads"
        self.root.mkdir()
        self.history = HistoryStore(self.base / "history")
        self.organizer = Organizer(self.history)

    def file(self, name, content="sample"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def organize(self):
        result = self.organizer.organize(self.organizer.preview(self.root))
        self.assertEqual(result.issues, [])
        return result

    def managed(self):
        self.organizer.apply_settings(replace(self.organizer.settings, folder_mode="managed"))

    def test_preferences_persist_separately_from_history(self):
        settings = replace(Settings(), theme="dark", excluded_extensions=("TMP",), startup_mode="last", last_folder=str(self.root))
        self.organizer.apply_settings(settings)
        reopened = Organizer(self.history)
        self.assertEqual(reopened.settings.theme, "dark")
        self.assertEqual(reopened.settings.excluded_extensions, (".tmp",))
        self.assertEqual(reopened.settings.startup_folder(), self.root)
        self.assertEqual(reopened.jobs(), [])

    def test_atomic_write_failure_keeps_old_preferences(self):
        self.organizer.apply_settings(replace(Settings(), theme="light"))
        with patch("cleanfolder.core.settings.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(SettingsError):
                self.organizer.apply_settings(replace(Settings(), theme="dark"))
        self.assertEqual(self.organizer.settings.theme, "light")
        self.assertEqual(Organizer(self.history).settings.theme, "light")
        self.assertEqual(list(self.organizer.settings_store.path.parent.glob("*.tmp")), [])

    def test_corrupt_preferences_are_not_overwritten(self):
        store = SettingsStore(self.history.directory)
        store.path.parent.mkdir(parents=True)
        store.path.write_text("broken")
        with self.assertRaises(SettingsError):
            store.load()
        self.assertEqual(store.path.read_text(), "broken")

    def test_settings_directory_cannot_be_organized(self):
        self.organizer.apply_settings(Settings())
        with self.assertRaises(SafetyError):
            self.organizer.preview(self.organizer.settings_store.path.parent)
        self.assertTrue(self.organizer.settings_store.path.exists())

    def test_invalid_folder_names_rejected(self):
        for name in ("../Photos", ".hidden", "..", "a/b", "a\\b", "CON", "nul.txt", "bad:", "x."):
            with self.subTest(name=name), self.assertRaises(SettingsError):
                replace(Settings(), folder_names=dict(Settings().folder_names, Images=name)).validated()
        with self.assertRaises(SettingsError):
            replace(Settings(), folder_names=dict(Settings().folder_names, Images="pdf")).validated()

    def test_duplicate_extensions_and_installer_reassignment_rejected(self):
        settings = Settings()
        for extensions in (
            dict(settings.extensions, Images=(".PDF",)),
            dict(settings.extensions, Installers=(".dmg",)),
            dict(settings.extensions, Others=(".custom",)),
            dict(settings.extensions, Code=("../py",)),
        ):
            with self.subTest(extensions=extensions), self.assertRaises(SettingsError):
                replace(settings, extensions=extensions).validated()

    def test_compound_rules_and_exclusions(self):
        settings = Settings()
        extensions = dict(settings.extensions, Archives=(*settings.extensions["Archives"], "tar.gz"))
        settings = replace(settings, extensions=extensions, excluded_extensions=("TMP",), excluded_names=("keep-*", "secret?.pdf")).validated()
        self.assertEqual(settings.classify("BUNDLE.TAR.GZ"), "Archives")
        self.assertEqual(settings.classify("OTHER.unknown"), "Others")
        for name in ("file.TMP", "KEEP-report.pdf", "secret1.pdf"):
            self.assertTrue(settings.excludes(name))
        self.assertFalse(settings.excludes("secret12.pdf"))

    def test_invalid_exclusions_and_startup_settings_rejected(self):
        for settings in (
            replace(Settings(), excluded_names=("folder/file",)),
            replace(Settings(), excluded_extensions=("*",)),
            replace(Settings(), startup_mode="default"),
            replace(Settings(), default_folder="relative"),
            replace(Settings(), theme="unknown"),
        ):
            with self.subTest(settings=settings), self.assertRaises(SettingsError):
                settings.validated()

    def test_custom_rules_folders_and_exclusions(self):
        settings = Settings()
        self.organizer.apply_settings(replace(
            settings, folder_names=dict(settings.folder_names, Images="사진"),
            extensions=dict(settings.extensions, Images=(*settings.extensions["Images"], ".custom")),
            excluded_extensions=(".tmp",), excluded_names=("keep-*",),
        ))
        self.file("photo.custom")
        self.file("keep-report.pdf")
        self.file("cache.tmp")
        self.assertEqual(self.organize().completed, 1)
        self.assertTrue((self.root / "사진/photo.custom").exists())
        self.assertTrue((self.root / "keep-report.pdf").exists())
        self.assertTrue((self.root / "cache.tmp").exists())

    def test_managed_mode_never_adopts_user_folders(self):
        self.managed()
        self.file("Images/original.png", "original")
        self.file("photo.png")
        self.assertEqual(self.organizer.preview(self.root).files[0].folder, "Images (1)")
        self.organize()
        self.file("second.png")
        self.assertEqual(self.organizer.preview(self.root).files[0].folder, "Images (1)")
        self.organize()
        self.assertEqual((self.root / "Images/original.png").read_text(), "original")

    def test_reuse_collision_preview_and_lifo_undo(self):
        self.file("photo.png", "first")
        self.organize()
        self.managed()
        self.file("photo.png", "second")
        preview = self.organizer.preview(self.root)
        self.assertEqual(preview.files[0].folder, "Images")
        self.assertEqual(preview.files[0].target, "photo (1).png")
        self.assertEqual(self.organizer.organize(preview).completed, 1)
        self.assertEqual((self.root / "Images/photo.png").read_text(), "first")
        self.assertEqual((self.root / "Images/photo (1).png").read_text(), "second")
        self.assertEqual(self.organizer.undo(self.root).completed, 1)
        self.assertTrue((self.root / "Images").is_dir())
        self.assertEqual((self.root / "photo.png").read_text(), "second")
        self.assertEqual(self.organizer.undo(self.root).completed, 1)
        self.assertFalse((self.root / "Images").exists())
        self.assertEqual((self.root / "photo (1).png").read_text(), "first")

    def test_reused_empty_folder_is_not_removed_by_non_creator(self):
        self.managed()
        self.file("one.png")
        self.organize()
        (self.root / "Images/one.png").unlink()
        self.file("two.png")
        self.organize()
        self.assertEqual(self.organizer.undo(self.root).completed, 1)
        self.assertTrue((self.root / "Images").is_dir())

    def test_replaced_managed_folder_is_not_adopted(self):
        self.managed()
        self.file("one.png")
        self.organize()
        (self.root / "Images").rename(self.root / "old")
        self.file("Images/private.png")
        self.file("two.png")
        self.assertEqual(self.organizer.preview(self.root).files[0].folder, "Images (1)")

    def test_symlink_replacement_after_preview_blocks_move(self):
        self.managed()
        self.file("one.png")
        self.organize()
        self.file("two.png")
        preview = self.organizer.preview(self.root)
        (self.root / "Images").rename(self.root / "old")
        (self.root / "Images").symlink_to(self.root / "old", target_is_directory=True)
        with self.assertRaises(SafetyError):
            self.organizer.organize(preview)
        self.assertTrue((self.root / "two.png").exists())

    def test_new_folder_label_does_not_rename_old_folder(self):
        self.managed()
        self.file("one.png")
        self.organize()
        settings = self.organizer.settings
        self.organizer.apply_settings(replace(settings, folder_names=dict(settings.folder_names, Images="사진")))
        self.file("two.png")
        self.assertEqual(self.organizer.preview(self.root).files[0].folder, "사진")
        self.organize()
        self.assertTrue((self.root / "Images/one.png").exists())

    def test_rule_change_invalidates_preview_but_theme_change_does_not(self):
        self.file("one.pdf")
        preview = self.organizer.preview(self.root)
        self.organizer.apply_settings(replace(Settings(), excluded_extensions=(".pdf",)))
        with self.assertRaises(SafetyError):
            self.organizer.organize(preview)
        self.organizer.apply_settings(replace(Settings(), theme="dark"))
        self.assertEqual(self.organizer.organize(preview).completed, 1)

    def test_excluded_installers_not_listed_or_trashed(self):
        self.file("setup.dmg")
        selected = self.organizer.installers(self.root)
        self.organize()
        self.file("new.dmg")
        self.organizer.apply_settings(replace(Settings(), excluded_extensions=(".dmg",)))
        self.assertEqual(self.organizer.installers(self.root), [])
        with patch("send2trash.send2trash") as send:
            self.assertEqual(self.organizer.trash(self.root, selected).completed, 0)
            send.assert_not_called()

    def test_legacy_job_can_be_reused_and_restored(self):
        self.file("one.png")
        self.organize()
        job = self.organizer.latest(self.root)
        job.pop("created_folders")
        job.pop("folder_labels")
        self.history.save(job)
        self.managed()
        self.file("two.png")
        self.assertEqual(self.organizer.preview(self.root).files[0].folder, "Images")
        self.organize()
        self.organizer.undo(self.root)
        self.organizer.undo(self.root)
        self.assertFalse((self.root / "Images").exists())


if __name__ == "__main__":
    unittest.main()
