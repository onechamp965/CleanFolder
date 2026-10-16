import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def build_icons():
    application = QGuiApplication.instance() or QGuiApplication([])
    assets = Path(__file__).resolve().parents[1] / "cleanfolder" / "assets"
    renderer = QSvgRenderer(str(assets / "app-icon.svg"))
    if not renderer.isValid():
        raise ValueError("앱 아이콘 SVG를 읽을 수 없습니다.")
    chunks = []
    for kind, size in ((b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
                       (b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024)):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise OSError("아이콘 PNG를 만들 수 없습니다.")
        png = bytes(buffer.data())
        chunks.append(kind + struct.pack(">I", len(png) + 8) + png)
        if size == 1024:
            (assets / "app-icon.png").write_bytes(png)
    payload = b"".join(chunks)
    (assets / "app-icon.icns").write_bytes(b"icns" + struct.pack(">I", len(payload) + 8) + payload)
    print(f"PNG / macOS ICNS 아이콘 생성 완료: {assets}")
    return application


if __name__ == "__main__":
    build_icons()
