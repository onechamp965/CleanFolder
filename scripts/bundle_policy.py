from pathlib import Path


EXCLUDED_QT_MODULES = (
    "QtPdf", "QtPdfWidgets", "QtQml", "QtQuick", "QtQuickWidgets",
    "QtVirtualKeyboard", "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick",
)


def keep_plugin(source: str, destination: str) -> bool:
    name = Path(source).name.casefold()
    return not name.startswith(("libqpdf.", "qpdf.", "libqtvirtualkeyboardplugin.", "qtvirtualkeyboardplugin."))


def keep_translation(source: str, destination: str) -> bool:
    name = Path(source).name.casefold()
    return not name.endswith(".qm") or name.endswith(("_ko.qm", "_en.qm"))
