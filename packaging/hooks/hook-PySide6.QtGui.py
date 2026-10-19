import sys
from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.bundle_policy import keep_plugin, keep_translation

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [(source, destination) for source, destination in binaries if keep_plugin(source, destination)]
datas = [(source, destination) for source, destination in datas if keep_translation(source, destination)]
