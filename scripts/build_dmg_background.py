import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def build_background(output: Path):
    application = QGuiApplication.instance() or QGuiApplication([])
    project = Path(__file__).resolve().parents[1]
    renderer = QSvgRenderer(str(project / "packaging" / "installer-background.svg"))
    if not renderer.isValid():
        raise ValueError("설치 화면 배경을 읽을 수 없습니다.")
    output.mkdir(parents=True, exist_ok=True)
    for scale in (1, 2):
        image = QImage(680 * scale, 440 * scale, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        image.setDotsPerMeterX(round(72 * scale / 0.0254))
        image.setDotsPerMeterY(round(72 * scale / 0.0254))
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        suffix = "@2x" if scale == 2 else ""
        if not image.save(str(output / f"installer-background{suffix}.png")):
            raise OSError("설치 화면 배경을 저장할 수 없습니다.")
    return application


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build_background(arguments.output)
