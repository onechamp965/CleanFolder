from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QFrame, QLabel, QPushButton, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QTableWidget, QVBoxLayout, QWidget,
)

from .icons import symbol_icon
from .theme import category_color


def label(text: str, name: str) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    return widget


class EmptyState(QWidget):
    def __init__(self, title: str, detail: str, symbol: str, action=None):
        super().__init__()
        self.symbol = symbol
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addStretch()
        self.glyph = label("", "emptyGlyph")
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.glyph.setFixedSize(68, 68)
        layout.addWidget(self.glyph, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.title = label(title, "emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        self.detail = label(detail, "emptyDetail")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.action = QPushButton("폴더 선택하기")
        self.action.setObjectName("primary")
        self.action.setVisible(action is not None)
        if action is not None:
            self.action.clicked.connect(action)
        layout.addWidget(self.action, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def update_icon(self, palette):
        self.glyph.setPixmap(symbol_icon(self.symbol, palette).pixmap(QSize(30, 30), self.devicePixelRatioF()))


class StatCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 13, 18, 13)
        layout.setSpacing(4)
        layout.addWidget(label(title, "statLabel"))
        self.value = label("—", "statValue")
        layout.addWidget(self.value)


class FileSelectionTable(QTableWidget):
    def __init__(self, *arguments):
        super().__init__(*arguments)
        self._pressed_row = None
        self._pressed_state = None

    def mousePressEvent(self, event):
        self._pressed_row = None
        self._pressed_state = None
        index = self.indexAt(event.position().toPoint())
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton and index.isValid():
            checkbox = self.item(index.row(), 0)
            if checkbox is not None and checkbox.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                self._pressed_row = index.row()
                self._pressed_state = checkbox.checkState()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        row, state = self._pressed_row, self._pressed_state
        self._pressed_row = None
        self._pressed_state = None
        super().mouseReleaseEvent(event)
        index = self.indexAt(event.position().toPoint())
        if (self.isEnabled() and event.button() == Qt.MouseButton.LeftButton
                and index.isValid() and row == index.row()):
            checkbox = self.item(row, 0)
            if checkbox is not None and checkbox.checkState() == state:
                checkbox.setCheckState(Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def keyPressEvent(self, event):
        index = self.currentIndex()
        if self.isEnabled() and event.key() == Qt.Key.Key_Space and index.isValid():
            checkbox = self.item(index.row(), 0)
            if checkbox is not None and checkbox.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                if not event.isAutoRepeat():
                    checkbox.setCheckState(Qt.CheckState.Unchecked if checkbox.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)
                event.accept()
                return
        super().keyPressEvent(event)


class CategoryDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dark = False

    def paint(self, painter: QPainter, option, index):
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.text = ""
        style = option.widget.style() if option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, background, painter, option.widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = str(index.data() or "")
        foreground = category_color(text, self.dark)
        background = QColor(foreground)
        background.setAlpha(32 if self.dark else 22)
        font = option.font
        font.setPixelSize(11)
        painter.setFont(font)
        width = min(painter.fontMetrics().horizontalAdvance(text) + 18, option.rect.width() - 16)
        badge = QRectF(option.rect.left() + 10, option.rect.center().y() - 11, width, 23)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(badge, 6, 6)
        painter.setPen(foreground)
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
