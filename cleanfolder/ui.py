import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QSize, QThread, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import __version__
from .icons import app_icon, symbol_icon
from .service import Organizer, Preview, Result


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
        self.installer_items = []
        self.latest_job = None
        self.task: Task | None = None
        self.setWindowTitle("CleanFolder")
        self.setWindowIcon(app_icon())
        self.resize(900, 640)
        self.setMinimumSize(700, 510)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(QSize(56, 56), self.devicePixelRatioF()))
        logo.setAccessibleName("CleanFolder 앱 아이콘")
        title_row.addWidget(logo)
        title = QLabel("CleanFolder")
        font = title.font()
        font.setPointSize(26)
        font.setBold(True)
        title.setFont(font)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)
        description = QLabel("폴더를 가볍게, 파일은 안전하게.")
        layout.addWidget(description)

        folder_row = QHBoxLayout()
        self.folder_text = QLineEdit()
        self.folder_text.setReadOnly(True)
        self.folder_text.setPlaceholderText("정리할 폴더를 선택하세요")
        self.choose_button = QPushButton("폴더 선택…")
        self.choose_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_text, 1)
        folder_row.addWidget(self.choose_button)
        layout.addLayout(folder_row)

        self.tabs = QTabWidget()
        self.preview_table = make_table(["파일", "크기", "분류", "정리될 위치"])
        self.preview_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabs.addTab(self.preview_table, "정리 미리보기")

        installers_page = QWidget()
        installers_layout = QVBoxLayout(installers_page)
        installers_layout.setContentsMargins(0, 12, 0, 0)
        explanation = QLabel("선택한 설치 파일만 휴지통으로 이동합니다. 복원은 Finder의 휴지통에서 해 주세요.")
        explanation.setWordWrap(True)
        installers_layout.addWidget(explanation)
        self.installers_table = make_table(["선택", "설치 파일", "위치"])
        self.installers_table.itemChanged.connect(self.update_buttons)
        installers_layout.addWidget(self.installers_table)
        self.trash_button = QPushButton("선택한 파일을 휴지통으로…")
        self.trash_button.clicked.connect(self.trash_selected)
        installers_layout.addWidget(self.trash_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(installers_page, "설치 파일")

        self.history_table = make_table(["정리한 시간", "파일 수", "상태"])
        self.tabs.addTab(self.history_table, "작업 기록")
        layout.addWidget(self.tabs, 1)
        self.summary = QLabel("선택한 폴더의 최상위 파일만 검사합니다. 기존 폴더와 숨김 파일은 유지합니다.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        actions = QHBoxLayout()
        self.undo_button = QPushButton("원래대로 돌리기…")
        self.undo_button.clicked.connect(self.undo)
        self.refresh_button = QPushButton("다시 미리보기")
        self.refresh_button.clicked.connect(self.refresh)
        self.organize_button = QPushButton("정리하기")
        self.organize_button.setDefault(True)
        self.organize_button.clicked.connect(self.organize)
        actions.addWidget(self.undo_button)
        actions.addStretch()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.organize_button)
        layout.addLayout(actions)
        self.setCentralWidget(content)

        file_menu = self.menuBar().addMenu("파일")
        self.open_action = QAction("폴더 선택…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.choose_folder)
        file_menu.addAction(self.open_action)
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
        self.update_icons()
        self.update_buttons()

    def update_icons(self):
        for button, name in (
            (self.choose_button, "folder"), (self.refresh_button, "refresh"),
            (self.organize_button, "organize"), (self.undo_button, "undo"),
            (self.trash_button, "trash"),
        ):
            button.setIcon(symbol_icon(name, self.palette()))
            button.setIconSize(QSize(18, 18))
        self.open_action.setIcon(symbol_icon("folder", self.palette()))
        for index, name in enumerate(("preview", "installers", "history")):
            self.tabs.setTabIcon(index, symbol_icon(name, self.palette()))

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange) and hasattr(self, "open_action"):
            self.update_icons()

    def update_buttons(self, *_):
        busy = self.task is not None
        self.choose_button.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy and self.folder is not None)
        self.organize_button.setEnabled(not busy and self.preview is not None and bool(self.preview.files))
        self.undo_button.setEnabled(not busy and self.latest_job is not None)
        self.trash_button.setEnabled(not busy and bool(self.selected_installers()))
        self.installers_table.setEnabled(not busy)
        self.progress.setVisible(busy)

    def selected_installers(self):
        return [item for row, item in enumerate(self.installer_items)
                if self.installers_table.item(row, 0) is not None
                and self.installers_table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def choose_folder(self):
        if self.task is not None:
            return
        path = QFileDialog.getExistingDirectory(self, "정리할 폴더 선택", str(self.folder or Path.home()))
        if path:
            self.folder = Path(path).resolve()
            self.folder_text.setText(str(self.folder))
            self.refresh()

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
            self.organize_button.setEnabled(False)
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
        self.preview_table.setRowCount(len(self.preview.files))
        for row, item in enumerate(self.preview.files):
            values = (item.name, size_text(item.size), item.category, f"{item.folder}/{item.name}")
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.preview_table.setItem(row, column, cell)
        self.installers_table.blockSignals(True)
        self.installers_table.setRowCount(len(self.installer_items))
        for row, item in enumerate(self.installer_items):
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.installers_table.setItem(row, 0, checkbox)
            self.installers_table.setItem(row, 1, QTableWidgetItem(item.path.name))
            self.installers_table.setItem(row, 2, QTableWidgetItem(str(item.path.parent)))
        self.installers_table.blockSignals(False)
        self.latest_job = next((job for job in jobs if job["state"] == "active"), None)
        self.history_table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            pending = sum(action["state"] not in ("restored", "trashed") for action in job["actions"])
            status = "복구 완료" if job["state"] == "restored" else f"복구 가능 · {pending}개"
            values = (datetime.fromisoformat(job["created_at"]).astimezone().strftime("%Y.%m.%d %H:%M:%S"), str(len(job["actions"])), status)
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(value))
        self.summary.setText(f"정리할 파일 {len(self.preview.files)}개 · 폴더·숨김 파일 등 {self.preview.skipped}개 제외")
        self.update_buttons()

    def organize(self):
        if self.preview is None or self.task is not None:
            return
        preview = self.preview
        self.start_task(lambda: self.organizer.organize(preview),
                        lambda result: self.report(result, "정리"), "파일을 정리하고 있습니다…")

    def undo(self):
        if self.folder is None or self.latest_job is None or self.task is not None:
            return
        reply = QMessageBox.question(self, "원래대로 돌리기", "이 폴더의 최근 정리 작업을 복구할까요?\n같은 이름이 있으면 새 이름으로 복구합니다.\n휴지통으로 보낸 파일은 Finder에서 복원해 주세요.",
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
        reply = QMessageBox.question(self, "휴지통으로 이동", f"선택한 설치 파일 {len(selected)}개를 휴지통으로 이동할까요?\n복원은 Finder의 휴지통에서 할 수 있습니다.",
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
    application.setApplicationName("CleanFolder")
    application.setOrganizationName("CleanFolder")
    application.setApplicationVersion(__version__)
    application.setWindowIcon(app_icon())
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(13)
    application.setFont(font)
    window = MainWindow()
    window.show()
    return application.exec()
