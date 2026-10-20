from pathlib import Path

from PySide6.QtGui import QColor


def colors(dark: bool) -> dict[str, str]:
    if dark:
        return {
            "canvas": "#17191F", "sidebar": "#1D2027", "surface": "#22252D",
            "raised": "#2A2E38", "border": "#323744", "text": "#EEF1F7",
            "secondary": "#A0A8BA", "muted": "#788296", "accent": "#82AEFF",
            "tint": "#273751", "primary": "#4B88FF", "hover": "#343A47",
            "disabled": "#2C3443", "disabled_text": "#748097", "success": "#8DD9BC",
            "selection": "#283D5F", "row": "#252932",
        }
    return {
        "canvas": "#F5F7FB", "sidebar": "#EDF1F7", "surface": "#FFFFFF",
        "raised": "#F7F9FC", "border": "#E3E8F0", "text": "#202B40",
        "secondary": "#6C7890", "muted": "#8C96A9", "accent": "#326BD5",
        "tint": "#E1EBFF", "primary": "#3478F6", "hover": "#E6EBF3",
        "disabled": "#E7EDF6", "disabled_text": "#97A5BA", "success": "#258664",
        "selection": "#EBF2FF", "row": "#FBFCFE",
    }


def category_color(category: str, dark: bool) -> QColor:
    accents = {
        "Word": "#568AE8", "Hangul": "#429DB7", "PowerPoint": "#C48050", "Excel": "#419F7D",
        "PDF": "#D56874", "Images": "#8D7AD6", "Videos": "#A57DC3",
        "Audio": "#BD78A4", "Archives": "#6A9AAB", "Installers": "#C38B42",
        "Code": "#5E9BA1", "Text": "#7C8BA3", "Others": "#8591A4",
    }
    color = QColor(accents.get(category, accents["Others"]))
    return color.lighter(125) if dark else color.darker(115)


def stylesheet(palette: dict[str, str]) -> str:
    palette = dict(palette, checkmark=(Path(__file__).resolve().parents[1] / "assets" / "checkmark.svg").as_posix())
    return """
        QMainWindow { background: %(canvas)s; color: %(text)s; }
        QWidget#canvas { background: %(canvas)s; }
        QWidget { font-size: 13px; }
        QLabel { color: %(text)s; background: transparent; border: none; }
        QFrame#sidebar { background: %(sidebar)s; border: none; border-right: 1px solid %(border)s; }
        QLabel#brand { font-size: 16px; font-weight: 700; }
        QLabel#eyebrow { color: %(muted)s; font-size: 11px; }
        QLabel#pageTitle { font-size: 25px; font-weight: 700; }
        QLabel#secondary { color: %(secondary)s; font-size: 12px; }
        QLabel#muted { color: %(muted)s; font-size: 11px; }
        QLabel#folderName { font-size: 15px; font-weight: 600; }
        QLabel#sectionTitle { font-size: 14px; font-weight: 600; }
        QLabel#countBadge { background: %(tint)s; color: %(accent)s; border-radius: 9px; padding: 3px 8px; font-size: 11px; }
        QLabel#folderGlyph { background: %(tint)s; border-radius: 13px; }
        QFrame#card { background: %(surface)s; border: 1px solid %(border)s; border-radius: 14px; }
        QFrame#statCard { background: %(surface)s; border: 1px solid %(border)s; border-radius: 12px; }
        QLabel#statValue { font-size: 23px; font-weight: 600; }
        QLabel#statLabel { color: %(secondary)s; font-size: 11px; }
        QLabel#statGlyph { color: %(accent)s; }
        QLineEdit#folderPath { background: transparent; border: none; color: %(secondary)s; padding: 0; font-size: 11px; selection-background-color: %(tint)s; }
        QPushButton { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 8px; padding: 8px 12px; font-size: 12px; }
        QPushButton:hover { background: %(raised)s; border-color: %(muted)s; }
        QPushButton:pressed { background: %(hover)s; }
        QPushButton:focus { border-color: %(primary)s; }
        QPushButton:disabled { color: %(disabled_text)s; border-color: %(border)s; background: %(raised)s; }
        QPushButton#primary { background: %(primary)s; color: white; border: 1px solid %(primary)s; font-weight: 600; padding: 11px 19px; }
        QPushButton#primary:hover { background: #246CE7; }
        QPushButton#primary:disabled { background: %(disabled)s; border-color: %(disabled)s; color: %(disabled_text)s; }
        QPushButton#navigation { background: transparent; border: 1px solid transparent; text-align: left; padding: 11px 12px; border-radius: 9px; color: %(secondary)s; }
        QPushButton#navigation:hover { background: %(hover)s; }
        QPushButton#navigation:checked { background: %(tint)s; color: %(accent)s; font-weight: 600; }
        QPushButton#quiet { background: transparent; border-color: transparent; color: %(secondary)s; }
        QPushButton#quiet:hover { background: %(hover)s; }
        QPushButton#quiet:disabled { background: transparent; color: %(muted)s; }
        QPushButton#danger { color: #CE6A70; }
        QPushButton#danger:disabled { color: %(muted)s; }
        QTabWidget::pane { border: none; background: transparent; }
        QWidget#settingsContent, QScrollArea#settingsScroll { background: %(canvas)s; border: none; }
        QTabBar::tab { background: transparent; color: %(secondary)s; padding: 10px 17px; border-bottom: 2px solid transparent; }
        QTabBar::tab:selected { color: %(accent)s; border-bottom-color: %(primary)s; }
        QLineEdit, QPlainTextEdit, QComboBox { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 7px; padding: 8px; selection-background-color: %(selection)s; }
        QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: %(primary)s; }
        QLineEdit:disabled, QComboBox:disabled { color: %(muted)s; }
        QComboBox { padding-right: 28px; }
        QComboBox::drop-down { border: none; width: 26px; }
        QComboBox QAbstractItemView { background: %(surface)s; color: %(text)s; selection-background-color: %(selection)s; selection-color: %(text)s; }
        QTableWidget { border: none; background: %(surface)s; alternate-background-color: %(row)s; color: %(text)s; selection-background-color: %(selection)s; selection-color: %(text)s; outline: none; }
        QTableWidget::item { padding: 9px 12px; border: none; border-bottom: 1px solid %(border)s; }
        QTableWidget::item:selected { background: %(selection)s; }
        QTableWidget::indicator { width: 16px; height: 16px; border: 1px solid %(muted)s; border-radius: 4px; background: %(surface)s; }
        QTableWidget::indicator:checked { border-color: %(primary)s; background: %(primary)s; image: url("%(checkmark)s"); }
        QHeaderView { background: %(raised)s; border: none; }
        QHeaderView::section { background: %(raised)s; color: %(secondary)s; border: none; border-bottom: 1px solid %(border)s; padding: 10px 12px; font-size: 11px; font-weight: 500; }
        QScrollBar:vertical { background: transparent; width: 8px; margin: 3px 1px; }
        QScrollBar::handle:vertical { background: %(border)s; border-radius: 3px; min-height: 26px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        QProgressBar { border: none; border-radius: 2px; background: %(border)s; }
        QProgressBar::chunk { background: %(primary)s; border-radius: 2px; }
        QLabel#emptyGlyph { background: %(tint)s; border-radius: 19px; }
        QLabel#emptyTitle { font-size: 17px; font-weight: 600; }
        QLabel#emptyDetail { color: %(secondary)s; font-size: 12px; }
        QStatusBar { background: %(canvas)s; border: none; color: %(success)s; padding-left: 18px; font-size: 12px; }
        QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 6px; }
    """ % palette
