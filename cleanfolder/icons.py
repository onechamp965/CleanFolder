from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer


ASSETS = Path(__file__).with_name("assets")

SYMBOLS = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 10h18"/>',
    "preview": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    "installers": '<path d="m3 7 9-4 9 4v10l-9 4-9-4Z"/><path d="m3 7 9 4 9-4M12 11v10M7.5 5l9 4"/>',
    "history": '<path d="M3 10a9 9 0 1 1 1.7 7M3 4v6h6"/><path d="M12 7v5l3 2"/>',
    "refresh": '<path d="M20 10a8 8 0 0 0-14-5L3 8M3 3v5h5M4 14a8 8 0 0 0 14 5l3-3M21 21v-5h-5"/>',
    "undo": '<path d="m8 4-5 5 5 5M3 9h10a7 7 0 0 1 0 14" transform="translate(0 -2)"/>',
    "organize": '<path d="M4 5h16M4 11h9M4 17h6M15 16l3 3 4-6"/>',
    "trash": '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
}


def app_icon() -> QIcon:
    return QIcon(str(ASSETS / "app-icon.png"))


def symbol_icon(name: str, palette: QPalette) -> QIcon:
    icon = QIcon()
    for mode, group, role in (
        (QIcon.Mode.Normal, QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText),
        (QIcon.Mode.Disabled, QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText),
        (QIcon.Mode.Selected, QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText),
    ):
        color = palette.color(group, role).name()
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{SYMBOLS[name]}</svg>'
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        for size in (16, 20, 24, 32):
            image = QImage(size * 2, size * 2, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            pixmap = QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(2)
            icon.addPixmap(pixmap, mode)
    return icon
