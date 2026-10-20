import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QFontDatabase, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.filesystem import SafetyError
from .icons import app_icon, symbol_icon
from ..core.service import Organizer, Preview, Result
from ..core.settings import Settings, SettingsError
from ..platforms.environment import trash_location
from .settings_page import SettingsPage
from .theme import category_color, colors, stylesheet
from .widgets import CategoryDelegate, EmptyState, StatCard, label


class Task(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable, parent: QWidget):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.succeeded.emit(self.operation())
        except Exception as error:
            self.failed.emit(str(error))


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(46)
    table.setIconSize(QSize(20, 20))
    table.setFrameShape(QFrame.Shape.NoFrame)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    table.horizontalHeader().setMinimumSectionSize(70)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def size_text(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return ""


class MainWindow(QMainWindow):
    def __init__(self, organizer: Organizer | None = None):
        super().__init__()
        self.organizer = organizer or Organizer()
        self.folder: Path | None = None
        self.preview: Preview | None = None
        self.selection_root = None
        self.excluded_names: set[str] = set()
        self.installer_items = []
        self.latest_job = None
        self.task: Task | None = None
        self.setWindowTitle("CleanFolder")
        self.setWindowIcon(app_icon())
        self.resize(1080, 740)
        self.setMinimumSize(900, 620)
        self._theme_dark = None

        root = QWidget()
        root.setObjectName("canvas")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(194)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 25, 16, 20)
        sidebar_layout.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(QSize(34, 34), self.devicePixelRatioF()))
        logo.setAccessibleName("CleanFolder 앱 아이콘")
        brand_row.addWidget(logo)
        brand_row.addWidget(label("CleanFolder", "brand"))
        brand_row.addStretch()
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addSpacing(32)
        sidebar_layout.addWidget(label("내 파일 관리", "eyebrow"))
        sidebar_layout.addSpacing(3)
        self.nav_buttons = []
        for index, text in enumerate(("파일 정리", "설치 파일", "작업 기록")):
            button = QPushButton(text)
            button.setObjectName("navigation")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked, page=index: self.tabs.setCurrentIndex(page))
            self.nav_buttons.append(button)
            sidebar_layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        sidebar_layout.addStretch()
        settings_button = QPushButton("설정")
        settings_button.setObjectName("navigation")
        settings_button.setCheckable(True)
        settings_button.setAutoExclusive(True)
        settings_button.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        self.nav_buttons.append(settings_button)
        sidebar_layout.addWidget(settings_button)
        self.undo_button = QPushButton("원래대로 돌리기")
        self.undo_button.setObjectName("quiet")
        self.undo_button.setToolTip("선택한 폴더의 최근 정리 작업을 복구합니다")
        self.undo_button.clicked.connect(self.undo)
        sidebar_layout.addWidget(self.undo_button)
        sidebar_layout.addSpacing(14)
        sidebar_layout.addWidget(label("폴더는 그대로, 파일만 깔끔하게.", "muted"))
        shell.addWidget(sidebar)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(18)
        self.page_title = label("파일 정리", "pageTitle")
        self.page_description = label("어디로 옮길지 먼저 확인하고, 안심하고 정리하세요.", "secondary")
        page_heading = QVBoxLayout()
        page_heading.setSpacing(6)
        page_heading.addWidget(self.page_title)
        page_heading.addWidget(self.page_description)
        layout.addLayout(page_heading)

        folder_card = QFrame()
        self.folder_card = folder_card
        folder_card.setObjectName("card")
        folder_row = QHBoxLayout(folder_card)
        folder_row.setContentsMargins(18, 16, 18, 16)
        folder_row.setSpacing(14)
        self.folder_glyph = label("", "folderGlyph")
        self.folder_glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.folder_glyph.setFixedSize(46, 46)
        folder_row.addWidget(self.folder_glyph)
        folder_details = QVBoxLayout()
        folder_details.setSpacing(4)
        self.folder_name = label("정리할 폴더를 선택하세요", "folderName")
        folder_details.addWidget(self.folder_name)
        self.folder_text = QLineEdit()
        self.folder_text.setObjectName("folderPath")
        self.folder_text.setReadOnly(True)
        self.folder_text.setFrame(False)
        self.folder_text.setPlaceholderText("최상위 파일만 확인하고 기존 폴더는 보호합니다")
        folder_details.addWidget(self.folder_text)
        folder_row.addLayout(folder_details, 1)
        self.choose_button = QPushButton("폴더 선택")
        self.choose_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.choose_button)
        layout.addWidget(folder_card)

        self.stats_widget = QWidget()
        stats_row = QHBoxLayout(self.stats_widget)
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(12)
        self.file_stat = StatCard("정리할 파일")
        self.size_stat = StatCard("정리할 파일 크기")
        self.protected_stat = StatCard("안전하게 제외")
        for card in (self.file_stat, self.size_stat, self.protected_stat):
            stats_row.addWidget(card, 1)
        layout.addWidget(self.stats_widget)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        preview_page = QFrame()
        preview_page.setObjectName("card")
        preview_layout = QVBoxLayout(preview_page)
        preview_layout.setContentsMargins(1, 1, 1, 10)
        preview_layout.setSpacing(0)
        list_header = QHBoxLayout()
        list_header.setContentsMargins(18, 10, 14, 10)
        list_header.addWidget(label("정리 미리보기", "sectionTitle"))
        self.file_badge = label("0개", "countBadge")
        list_header.addWidget(self.file_badge)
        list_header.addStretch()
        self.refresh_button = QPushButton("다시 미리보기")
        self.refresh_button.setObjectName("quiet")
        self.refresh_button.clicked.connect(self.refresh)
        list_header.addWidget(self.refresh_button)
        preview_layout.addLayout(list_header)
        self.selection_bar = QWidget()
        selection_row = QHBoxLayout(self.selection_bar)
        selection_row.setContentsMargins(18, 0, 14, 8)
        selection_hint = label("남겨둘 파일은 체크를 해제하세요.", "secondary")
        selection_hint.setToolTip("같은 폴더에서 다시 미리보기 해도 선택을 유지합니다. 폴더를 바꾸거나 앱을 다시 열면 초기화됩니다. 계속 제외할 파일은 설정의 제외 항목에 등록하세요.")
        selection_hint.setWordWrap(True)
        selection_row.addWidget(selection_hint, 1)
        self.select_all_button = QPushButton("모두 선택")
        self.exclude_all_button = QPushButton("모두 제외")
        for button in (self.select_all_button, self.exclude_all_button):
            button.setObjectName("quiet")
            selection_row.addWidget(button)
        self.select_all_button.clicked.connect(lambda: self.select_all_files(True))
        self.exclude_all_button.clicked.connect(lambda: self.select_all_files(False))
        self.selection_bar.hide()
        preview_layout.addWidget(self.selection_bar)
        self.preview_table = make_table(["파일 이름", "크기", "분류", "이동할 위치"])
        self.preview_table.setAccessibleName("정리할 파일 선택 목록")
        self.preview_table.itemChanged.connect(self.change_file_selection)
        self.preview_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 104), (2, 108)):
            self.preview_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.preview_table.setColumnWidth(column, width)
        self.category_delegate = CategoryDelegate(self.preview_table)
        self.preview_table.setItemDelegateForColumn(2, self.category_delegate)
        self.preview_stack = QStackedWidget()
        self.empty_preview = EmptyState("어떤 폴더를 정리할까요?",
                                        "폴더를 선택하면 이동할 파일을 먼저 보여드릴게요.",
                                        "folder", self.choose_folder)
        self.preview_stack.addWidget(self.preview_table)
        self.preview_stack.addWidget(self.empty_preview)
        self.preview_stack.setCurrentWidget(self.empty_preview)
        preview_layout.addWidget(self.preview_stack, 1)
        self.tabs.addTab(preview_page, "파일 정리")

        installers_page = QFrame()
        installers_page.setObjectName("card")
        installers_layout = QVBoxLayout(installers_page)
        installers_layout.setContentsMargins(14, 16, 14, 14)
        installers_layout.setSpacing(14)
        explanation = label(f"필요 없는 설치 파일만 선택하세요. 복원은 {trash_location()}에서 할 수 있어요.", "secondary")
        explanation.setWordWrap(True)
        installers_layout.addWidget(explanation)
        self.installers_table = make_table(["선택", "설치 파일", "위치"])
        self.installers_table.horizontalHeader().setMinimumSectionSize(46)
        self.installers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.installers_table.setColumnWidth(0, 46)
        self.installers_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.installers_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.installers_table.itemChanged.connect(self.update_buttons)
        self.installer_stack = QStackedWidget()
        self.empty_installers = EmptyState("설치 파일이 없어요", "최상위 파일과 CleanFolder가 정리한 설치 파일만 표시합니다.", "installers")
        self.installer_stack.addWidget(self.installers_table)
        self.installer_stack.addWidget(self.empty_installers)
        self.installer_stack.setCurrentWidget(self.empty_installers)
        installers_layout.addWidget(self.installer_stack, 1)
        self.trash_button = QPushButton("선택한 파일을 휴지통으로…")
        self.trash_button.setObjectName("danger")
        self.trash_button.clicked.connect(self.trash_selected)
        installers_layout.addWidget(self.trash_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(installers_page, "설치 파일")

        history_page = QFrame()
        history_page.setObjectName("card")
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(14, 16, 14, 14)
        history_layout.setSpacing(14)
        history_layout.addWidget(label("선택한 폴더의 정리 기록입니다. 최근 작업부터 원래대로 돌릴 수 있어요.", "secondary"))
        self.history_table = make_table(["정리한 시간", "파일 수", "상태"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.history_stack = QStackedWidget()
        self.empty_history = EmptyState("아직 정리 기록이 없어요", "이 폴더에서 정리한 기록을 여기에 모아둘게요.", "history")
        self.history_stack.addWidget(self.history_table)
        self.history_stack.addWidget(self.empty_history)
        self.history_stack.setCurrentWidget(self.empty_history)
        history_layout.addWidget(self.history_stack, 1)
        self.tabs.addTab(history_page, "작업 기록")
        self.settings_page = SettingsPage(self.organizer.settings)
        self.settings_page.saveRequested.connect(self.apply_preferences)
        self.tabs.addTab(self.settings_page, "설정")
        layout.addWidget(self.tabs, 1)

        self.footer = QWidget()
        actions = QHBoxLayout(self.footer)
        actions.setContentsMargins(0, 0, 0, 0)
        footer_details = QVBoxLayout()
        footer_details.setSpacing(5)
        self.summary = label("폴더를 선택하면 정리할 파일을 확인할 수 있어요.", "secondary")
        self.summary.setWordWrap(True)
        footer_details.addWidget(self.summary)
        self.safety_note = label("기존 폴더와 폴더 안의 파일은 그대로 유지됩니다.", "muted")
        if self.organizer.settings.folder_mode == "managed":
            self.safety_note.setText("CleanFolder가 만든 분류 폴더만 재사용합니다. 다른 폴더는 보호됩니다.")
        self.safety_note.setWordWrap(True)
        footer_details.addWidget(self.safety_note)
        actions.addLayout(footer_details, 1)
        self.organize_button = QPushButton("정리하기")
        self.organize_button.setObjectName("primary")
        self.organize_button.setDefault(True)
        self.organize_button.clicked.connect(self.organize)
        actions.addWidget(self.organize_button)
        layout.addWidget(self.footer)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(3)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        shell.addWidget(content, 1)
        self.setCentralWidget(root)

        file_menu = self.menuBar().addMenu("파일")
        self.open_action = QAction("폴더 선택…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.choose_folder)
        file_menu.addAction(self.open_action)
        self.settings_action = QAction("설정…", self)
        self.settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        self.settings_action.triggered.connect(lambda: self.tabs.setCurrentIndex(3))
        file_menu.addAction(self.settings_action)
        quit_action = QAction("종료", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        help_menu = self.menuBar().addMenu("도움말")
        about_action = QAction("CleanFolder 정보", self)
        about_action.triggered.connect(lambda: QMessageBox.about(
            self, "CleanFolder", f"CleanFolder {__version__}\n선택한 폴더의 파일을 안전하게 정리합니다."
        ))
        help_menu.addAction(about_action)
        self.tabs.currentChanged.connect(self.change_page)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().messageChanged.connect(lambda message: self.statusBar().setVisible(bool(message)))
        self.statusBar().hide()
        QApplication.instance().paletteChanged.connect(self.apply_theme)
        self.apply_theme()
        self.update_buttons()
        if self.organizer.settings.startup_folder() is not None:
            QTimer.singleShot(0, self.load_startup_folder)

    def apply_theme(self, palette: QPalette | None = None):
        application_palette = palette if isinstance(palette, QPalette) else QApplication.palette()
        dark = application_palette.color(QPalette.ColorRole.Window).lightness() < 128
        if self.organizer.settings.theme != "system":
            dark = self.organizer.settings.theme == "dark"
        if self._theme_dark == dark:
            return
        self._theme_dark = dark
        self.theme = colors(dark)
        self._file_icons = {}
        self.setStyleSheet(stylesheet(self.theme))
        self.category_delegate.dark = dark
        self.update_icons()
        self.preview_table.viewport().update()

    def update_icons(self):
        palette = QPalette(self.palette())
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor(self.theme["secondary"]))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(self.theme["disabled_text"]))
        for button, name in (
            (self.choose_button, "folder"), (self.refresh_button, "refresh"),
            (self.organize_button, "organize"), (self.undo_button, "undo"),
            (self.trash_button, "trash"),
        ):
            button_palette = QPalette(palette)
            if button is self.organize_button:
                button_palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
            button.setIcon(symbol_icon(name, button_palette))
            button.setIconSize(QSize(16, 16))
        self.open_action.setIcon(symbol_icon("folder", palette))
        for index, name in enumerate(("preview", "installers", "history", "settings")):
            navigation_palette = QPalette(palette)
            if self.nav_buttons[index].isChecked():
                navigation_palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor(self.theme["accent"]))
            navigation_icon = symbol_icon(name, navigation_palette)
            self.nav_buttons[index].setIcon(navigation_icon)
            self.tabs.setTabIcon(index, navigation_icon)
            self.nav_buttons[index].setIconSize(QSize(18, 18))
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor(self.theme["accent"]))
        self.folder_glyph.setPixmap(symbol_icon("folder", palette).pixmap(QSize(25, 25), self.devicePixelRatioF()))
        for empty in (self.empty_preview, self.empty_installers, self.empty_history):
            empty.update_icon(palette)
        if self.preview is not None:
            for row, item in enumerate(self.preview.files):
                cell = self.preview_table.item(row, 0)
                if cell is not None:
                    cell.setIcon(self.file_icon(item.category))
                    cell.setForeground(QColor(self.theme["secondary"] if item.name in self.excluded_names else self.theme["text"]))
                for column in (1, 3):
                    cell = self.preview_table.item(row, column)
                    if cell is not None:
                        cell.setForeground(QColor(self.theme["secondary"]))

    def file_icon(self, category: str):
        if category not in self._file_icons:
            palette = QPalette(self.palette())
            palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText,
                             category_color(category, self._theme_dark))
            self._file_icons[category] = symbol_icon("document", palette)
        return self._file_icons[category]

    def change_page(self, index: int):
        titles = ("파일 정리", "설치 파일", "작업 기록", "설정")
        descriptions = ("어디로 옮길지 먼저 확인하고, 안심하고 정리하세요.",
                        "필요 없는 설치 파일을 골라 폴더를 더 가볍게 만드세요.",
                        "정리한 내용을 확인하고, 필요하면 원래대로 돌리세요.",
                        "정리 방식부터 화면까지, 나에게 맞게 설정하세요.")
        self.page_title.setText(titles[index])
        self.page_description.setText(descriptions[index])
        self.nav_buttons[index].setChecked(True)
        self.organize_button.setVisible(index == 0)
        self.organize_button.setDefault(index == 0)
        for widget in (self.folder_card, self.stats_widget, self.footer):
            widget.setVisible(index != 3)
        self.update_icons()

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange) and hasattr(self, "open_action"):
            self.apply_theme()

    def update_buttons(self, *_):
        busy = self.task is not None
        self.choose_button.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.settings_action.setEnabled(not busy)
        self.nav_buttons[3].setEnabled(not busy)
        self.settings_page.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy and self.folder is not None)
        selected = self.selected_files()
        self.organize_button.setEnabled(not busy and bool(selected))
        self.organize_button.setText(f"선택한 {len(selected)}개 정리" if selected else "정리하기")
        self.preview_table.setEnabled(not busy)
        for button in (self.select_all_button, self.exclude_all_button):
            button.setEnabled(not busy and self.preview is not None and bool(self.preview.files))
        self.undo_button.setEnabled(not busy and self.latest_job is not None)
        self.trash_button.setEnabled(not busy and bool(self.selected_installers()))
        self.installers_table.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.empty_preview.action.setEnabled(not busy)
        if busy and self.preview is None:
            self.preview_stack.setCurrentWidget(self.empty_preview)
            self.empty_preview.title.setText("파일을 확인하고 있어요")
            self.empty_preview.detail.setText("최상위 파일의 종류와 이동할 위치를 살펴보고 있습니다.")
            self.empty_preview.action.hide()

    def selected_installers(self):
        return [item for row, item in enumerate(self.installer_items)
                if self.installers_table.item(row, 0) is not None
                and self.installers_table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def selected_files(self):
        if self.preview is None:
            return ()
        return tuple(item for item in self.preview.files if item.name not in self.excluded_names)

    def change_file_selection(self, cell: QTableWidgetItem):
        if self.task is not None or self.preview is None or cell.column() != 0:
            return
        if not 0 <= cell.row() < len(self.preview.files):
            return
        item = self.preview.files[cell.row()]
        if cell.checkState() == Qt.CheckState.Checked:
            self.excluded_names.discard(item.name)
        else:
            self.excluded_names.add(item.name)
        self.update_file_selection()

    def select_all_files(self, selected: bool):
        if self.task is not None or self.preview is None:
            return
        for item in self.preview.files:
            if selected:
                self.excluded_names.discard(item.name)
            else:
                self.excluded_names.add(item.name)
        self.update_file_selection()

    def update_file_selection(self):
        if self.preview is None:
            return
        self.preview_table.blockSignals(True)
        for row, item in enumerate(self.preview.files):
            selected = item.name not in self.excluded_names
            checkbox = self.preview_table.item(row, 0)
            checkbox.setCheckState(Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
            checkbox.setForeground(QColor(self.theme["text"] if selected else self.theme["secondary"]))
            location = self.preview_table.item(row, 3)
            destination = f"{item.folder}/{item.target or item.name}" if selected else "원래 위치에 유지"
            location.setText(destination)
            location.setToolTip(destination)
        self.preview_table.blockSignals(False)
        selected = self.selected_files()
        excluded = len(self.preview.files) - len(selected)
        self.file_stat.value.setText(f"{len(selected)}개")
        self.size_stat.value.setText(size_text(sum(item.size for item in selected)))
        self.protected_stat.value.setText(f"{self.preview.skipped + excluded}개")
        self.file_badge.setText(f"{len(selected)}/{len(self.preview.files)}개 선택")
        self.summary.setText(f"정리할 파일 {len(selected)}개 · 직접 제외 {excluded}개 · 보호·규칙 제외 {self.preview.skipped}개")
        self.selection_bar.setVisible(bool(self.preview.files))
        self.update_buttons()

    def choose_folder(self):
        if self.task is not None:
            return
        path = QFileDialog.getExistingDirectory(self, "정리할 폴더 선택", str(self.folder or Path.home()))
        if path:
            self.select_folder(Path(path))

    def select_folder(self, path: Path):
        if self.task is not None:
            return
        if self.folder != path.resolve():
            self.selection_root = None
            self.excluded_names.clear()
        self.folder = path.resolve()
        self.folder_name.setText(self.folder.name or str(self.folder))
        self.folder_text.setText(self.display_path(self.folder))
        self.folder_text.setToolTip(str(self.folder))
        self.choose_button.setText("변경")
        try:
            self.organizer.apply_settings(replace(self.organizer.settings, last_folder=str(self.folder)))
            if not self.settings_page.dirty:
                self.settings_page.load(self.organizer.settings)
        except (SettingsError, SafetyError, OSError) as error:
            self.statusBar().showMessage(f"최근 폴더를 저장하지 못했습니다: {error}")
        self.refresh()

    def load_startup_folder(self):
        folder = self.organizer.settings.startup_folder()
        if folder is None or self.task is not None:
            return
        if not folder.is_dir():
            self.statusBar().showMessage("시작 폴더를 찾을 수 없습니다. 다른 폴더를 선택해 주세요.")
            return
        self.select_folder(folder)

    def apply_preferences(self, settings: Settings):
        if self.task is not None:
            return
        try:
            self.organizer.apply_settings(replace(settings, last_folder=self.organizer.settings.last_folder))
        except (SettingsError, SafetyError, OSError) as error:
            QMessageBox.warning(self, "설정을 저장하지 못했어요", str(error))
            return
        self.settings_page.load(self.organizer.settings)
        self.apply_theme()
        self.safety_note.setText(
            "CleanFolder가 만든 분류 폴더만 재사용합니다. 다른 폴더는 보호됩니다."
            if settings.folder_mode == "managed" else "기존 폴더와 폴더 안의 파일은 그대로 유지됩니다."
        )
        self.preview = None
        self.update_buttons()
        self.refresh()
        self.statusBar().showMessage("설정을 저장했습니다. 시작 폴더는 다음 실행부터 적용됩니다.", 7000)

    @staticmethod
    def display_path(path: Path) -> str:
        try:
            return str(Path("~") / path.relative_to(Path.home()))
        except ValueError:
            return str(path)

    def start_task(self, operation: Callable, finished: Callable, message: str):
        if self.task is not None:
            return
        self.summary.setText(message)
        task = Task(operation, self)
        self.task = task
        self._task_result = None
        self._task_error = None
        task.succeeded.connect(self.store_result)
        task.failed.connect(self.store_error)
        task.finished.connect(lambda: self.finish_task(task, finished))
        self.update_buttons()
        task.start()

    def store_result(self, result):
        self._task_result = result

    def store_error(self, error: str):
        self._task_error = error

    def finish_task(self, task: Task, finished: Callable):
        self.task = None
        task.deleteLater()
        self.update_buttons()
        if self._task_error is not None:
            self.preview = None
            self.selection_bar.hide()
            self.file_badge.setText("0개")
            self.latest_job = None
            self.installer_items = []
            for table in (self.preview_table, self.installers_table, self.history_table):
                table.setRowCount(0)
            for stack, empty in ((self.preview_stack, self.empty_preview),
                                 (self.installer_stack, self.empty_installers),
                                 (self.history_stack, self.empty_history)):
                stack.setCurrentWidget(empty)
            for card in (self.file_stat, self.size_stat, self.protected_stat):
                card.value.setText("—")
            self.empty_preview.title.setText("폴더를 확인하지 못했어요")
            self.empty_preview.detail.setText("접근 권한을 확인하거나 다른 폴더를 선택해 주세요.")
            self.empty_preview.action.show()
            self.update_buttons()
            self.summary.setText("작업을 완료하지 못했습니다. 다시 미리보기로 현재 상태를 확인하세요.")
            QMessageBox.warning(self, "확인이 필요합니다", self._task_error)
            return
        finished(self._task_result)

    def refresh(self):
        if self.folder is None or self.task is not None:
            return
        folder = self.folder
        self.preview = None
        self.start_task(lambda: (
            self.organizer.preview(folder), self.organizer.installers(folder), self.organizer.jobs(folder)
        ), self.show_snapshot, "파일을 확인하고 있습니다…")

    def show_snapshot(self, snapshot):
        self.preview, self.installer_items, jobs = snapshot
        selection_root = (self.preview.root, tuple(self.preview.identity))
        if self.selection_root != selection_root:
            self.excluded_names.clear()
            self.selection_root = selection_root
        self.folder = self.preview.root
        self.folder_name.setText(self.folder.name or str(self.folder))
        self.folder_text.setText(self.display_path(self.folder))
        self.folder_text.setToolTip(str(self.folder))
        self.folder_text.setCursorPosition(0)
        self.choose_button.setText("변경")
        self.preview_table.blockSignals(True)
        self.preview_table.setRowCount(len(self.preview.files))
        for row, item in enumerate(self.preview.files):
            values = (item.name, size_text(item.size), item.category, f"{item.folder}/{item.target or item.name}")
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                if column == 0:
                    cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                    cell.setCheckState(Qt.CheckState.Checked)
                    cell.setToolTip(f"{item.name}\n체크를 해제하면 원래 위치에 남겨둡니다.")
                    cell.setIcon(self.file_icon(item.category))
                elif column == 1:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column in (1, 3):
                    cell.setForeground(QColor(self.theme["secondary"]))
                self.preview_table.setItem(row, column, cell)
        self.preview_table.blockSignals(False)
        self.preview_stack.setCurrentWidget(self.preview_table if self.preview.files else self.empty_preview)
        self.empty_preview.title.setText("지금은 정리할 파일이 없어요")
        self.empty_preview.detail.setText("선택한 폴더에 정리할 최상위 파일이 없습니다.\n기존 폴더와 숨김 파일은 그대로 유지했어요.")
        self.empty_preview.action.hide()
        self.protected_stat.setToolTip("기존 폴더, 숨김 파일, 심볼릭 링크, 설정의 제외 규칙, 직접 체크를 해제한 파일입니다")
        self.installers_table.blockSignals(True)
        self.installers_table.setRowCount(len(self.installer_items))
        for row, item in enumerate(self.installer_items):
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.installers_table.setItem(row, 0, checkbox)
            self.installers_table.setItem(row, 1, QTableWidgetItem(item.path.name))
            location = QTableWidgetItem(self.display_path(item.path.parent))
            location.setToolTip(str(item.path.parent))
            self.installers_table.setItem(row, 2, location)
        self.installers_table.blockSignals(False)
        self.installer_stack.setCurrentWidget(self.installers_table if self.installer_items else self.empty_installers)
        self.latest_job = next((job for job in jobs if job["state"] == "active"), None)
        self.history_table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            pending = sum(action["state"] not in ("restored", "trashed") for action in job["actions"])
            status = "복구 완료" if job["state"] == "restored" else f"복구 가능 · {pending}개"
            values = (datetime.fromisoformat(job["created_at"]).astimezone().strftime("%Y.%m.%d %H:%M:%S"), str(len(job["actions"])), status)
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(value))
        self.history_stack.setCurrentWidget(self.history_table if jobs else self.empty_history)
        self.update_file_selection()

    def organize(self):
        if self.preview is None or self.task is not None:
            return
        selected = self.selected_files()
        if not selected:
            return
        preview = replace(self.preview, files=selected)
        self.start_task(lambda: self.organizer.organize(preview),
                        lambda result: self.report(result, "정리"), "파일을 정리하고 있습니다…")

    def undo(self):
        if self.folder is None or self.latest_job is None or self.task is not None:
            return
        reply = QMessageBox.question(self, "원래대로 돌리기", f"이 폴더의 최근 정리 작업을 복구할까요?\n같은 이름이 있으면 새 이름으로 복구합니다.\n휴지통으로 보낸 파일은 {trash_location()}에서 복원해 주세요.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            folder = self.folder
            self.start_task(lambda: self.organizer.undo(folder),
                            lambda result: self.report(result, "복구"), "파일을 원래 위치로 돌리고 있습니다…")

    def trash_selected(self):
        selected = self.selected_installers()
        if not selected or self.folder is None or self.task is not None:
            return
        reply = QMessageBox.question(self, "휴지통으로 이동", f"선택한 설치 파일 {len(selected)}개를 휴지통으로 이동할까요?\n복원은 {trash_location()}에서 할 수 있습니다.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            folder = self.folder
            self.start_task(lambda: self.organizer.trash(folder, selected),
                            lambda result: self.report(result, "휴지통 이동"), "선택한 파일을 휴지통으로 이동하고 있습니다…")

    def report(self, result: Result, verb: str):
        message = f"파일 {result.completed}개 {verb} 완료"
        if result.issues:
            dialog = QMessageBox(QMessageBox.Icon.Warning, "일부 파일 확인 필요",
                                 f"{message}\n처리하지 못한 항목 {len(result.issues)}개가 있습니다.", parent=self)
            dialog.setDetailedText("\n".join(result.issues))
            dialog.exec()
        else:
            self.statusBar().showMessage(message, 15000)
        self.refresh()

    def closeEvent(self, event: QCloseEvent):
        if self.task is not None:
            self.statusBar().showMessage("진행 중인 작업이 끝나면 종료할 수 있습니다.", 5000)
            event.ignore()
        else:
            event.accept()


def run() -> int:
    application = QApplication(sys.argv[:1])
    application.setStyle("Fusion")
    application.setApplicationName("CleanFolder")
    application.setOrganizationName("CleanFolder")
    application.setApplicationVersion(__version__)
    application.setWindowIcon(app_icon())
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(13)
    application.setFont(font)
    try:
        window = MainWindow()
    except SettingsError as error:
        QMessageBox.critical(None, "설정을 확인해 주세요", f"{error}\n설정 파일과 작업 기록은 변경하지 않았습니다.")
        return 1
    window.show()
    return application.exec()
