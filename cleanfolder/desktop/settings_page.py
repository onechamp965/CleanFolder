from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.categories import CATEGORIES
from ..core.settings import Settings, SettingsError, parse_entries
from .widgets import label


def scroll_page():
    content = QWidget()
    content.setObjectName("settingsContent")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 16, 4, 4)
    layout.setSpacing(14)
    area = QScrollArea()
    area.setObjectName("settingsScroll")
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidgetResizable(True)
    area.setWidget(content)
    return area, layout


def card(title: str, description: str):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    layout.addWidget(label(title, "sectionTitle"))
    detail = label(description, "secondary")
    detail.setWordWrap(True)
    layout.addWidget(detail)
    return frame, layout


class SettingsPage(QWidget):
    saveRequested = Signal(object)

    def __init__(self, settings: Settings):
        super().__init__()
        self.saved = settings
        self._loading = False
        self.dirty = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.sections = QTabWidget()
        self.sections.setObjectName("settingsTabs")
        general, general_layout = scroll_page()

        folder_card, folder_layout = card("분류 폴더 사용 방식", "직접 만든 폴더는 보호합니다. 재사용은 작업 기록과 폴더 정보가 일치하는 경우에만 허용합니다.")
        self.folder_mode = QComboBox()
        self.folder_mode.addItem("매번 새 분류 폴더 만들기", "new")
        self.folder_mode.addItem("CleanFolder가 만든 분류 폴더 재사용", "managed")
        self.folder_mode.setAccessibleName("분류 폴더 사용 방식")
        folder_layout.addWidget(self.folder_mode)
        general_layout.addWidget(folder_card)

        startup_card, startup_layout = card("앱을 열었을 때", "시작할 폴더를 미리 정해두세요. 폴더를 열어 미리보기만 표시하며, 자동으로 파일을 이동하지 않습니다.")
        self.startup_mode = QComboBox()
        self.startup_mode.addItem("폴더를 선택하지 않고 시작", "empty")
        self.startup_mode.addItem("지정한 폴더로 시작", "default")
        self.startup_mode.addItem("마지막으로 사용한 폴더로 시작", "last")
        self.startup_mode.setAccessibleName("시작 폴더 방식")
        startup_layout.addWidget(self.startup_mode)
        path_row = QHBoxLayout()
        self.default_folder = QLineEdit()
        self.default_folder.setReadOnly(True)
        self.default_folder.setPlaceholderText("기본 시작 폴더를 선택하세요")
        self.default_folder.setAccessibleName("기본 시작 폴더")
        self.browse_button = QPushButton("폴더 선택")
        self.browse_button.clicked.connect(self.browse_folder)
        path_row.addWidget(self.default_folder, 1)
        path_row.addWidget(self.browse_button)
        startup_layout.addLayout(path_row)
        self.last_folder = label("", "muted")
        self.last_folder.setWordWrap(True)
        startup_layout.addWidget(self.last_folder)
        general_layout.addWidget(startup_card)

        appearance_card, appearance_layout = card("화면 모드", "시스템 설정을 따르거나 앱에만 밝은 모드·어두운 모드를 지정할 수 있습니다.")
        self.appearance = QComboBox()
        self.appearance.addItem("시스템 설정 따르기", "system")
        self.appearance.addItem("밝게", "light")
        self.appearance.addItem("어둡게", "dark")
        self.appearance.setAccessibleName("화면 모드")
        appearance_layout.addWidget(self.appearance)
        general_layout.addWidget(appearance_card)
        general_layout.addStretch()
        self.sections.addTab(general, "일반")

        rules, rules_layout = scroll_page()
        rules_card, rules_card_layout = card("분류 기준과 폴더 이름", "확장자는 쉼표로 구분하세요. 같은 확장자를 두 분류에 넣을 수 없으며, 분류되지 않은 파일은 Others로 정리합니다.")
        column_titles = QHBoxLayout()
        category_title = label("분류", "muted")
        category_title.setFixedWidth(100)
        folder_title = label("만들 폴더 이름", "muted")
        folder_title.setFixedWidth(155)
        column_titles.addWidget(category_title)
        column_titles.addWidget(folder_title)
        column_titles.addWidget(label("확장자", "muted"), 1)
        rules_card_layout.addLayout(column_titles)
        self.folder_fields = {}
        self.extension_fields = {}
        for category in CATEGORIES:
            row = QHBoxLayout()
            row.setSpacing(10)
            category_label = label(category, "settingsCategory")
            category_label.setFixedWidth(100)
            folder_field = QLineEdit()
            folder_field.setFixedWidth(155)
            folder_field.setAccessibleName(f"{category} 폴더 이름")
            extension_field = QLineEdit()
            extension_field.setAccessibleName(f"{category} 확장자")
            if category == "Others":
                extension_field.setReadOnly(True)
                extension_field.setPlaceholderText("그 외 모든 확장자")
            row.addWidget(category_label)
            row.addWidget(folder_field)
            row.addWidget(extension_field, 1)
            rules_card_layout.addLayout(row)
            self.folder_fields[category] = folder_field
            self.extension_fields[category] = extension_field
        protected = label(".dmg, .pkg, .msi, .exe, .iso는 Installers 분류에 유지됩니다. 기존 폴더의 이름은 변경하지 않습니다.", "muted")
        protected.setWordWrap(True)
        rules_card_layout.addWidget(protected)
        rules_layout.addWidget(rules_card)
        rules_layout.addStretch()
        self.sections.addTab(rules, "분류 규칙")

        exclusions, exclusions_layout = scroll_page()
        extensions_card, extensions_layout = card("정리에서 제외할 확장자", "원래 위치에 남겨둘 확장자를 쉼표나 줄바꿈으로 구분하세요. 제외한 설치 파일은 설치 파일 목록에도 표시하지 않습니다.")
        self.excluded_extensions = QPlainTextEdit()
        self.excluded_extensions.setPlaceholderText("예: .tmp, .part, .log")
        self.excluded_extensions.setFixedHeight(90)
        self.excluded_extensions.setAccessibleName("제외할 확장자")
        extensions_layout.addWidget(self.excluded_extensions)
        exclusions_layout.addWidget(extensions_card)
        names_card, names_layout = card("정리에서 제외할 파일 이름", "한 줄에 하나씩 입력하세요. *는 여러 글자, ?는 한 글자를 뜻합니다. 폴더 경로는 입력하지 않습니다.")
        self.excluded_names = QPlainTextEdit()
        self.excluded_names.setPlaceholderText("중요문서.pdf\nkeep-*\n*.download")
        self.excluded_names.setFixedHeight(150)
        self.excluded_names.setAccessibleName("제외할 파일 이름과 패턴")
        names_layout.addWidget(self.excluded_names)
        exclusions_layout.addWidget(names_card)
        exclusions_layout.addStretch()
        self.sections.addTab(exclusions, "제외 항목")
        layout.addWidget(self.sections, 1)

        self.feedback = label("변경 사항은 저장한 뒤 적용됩니다.", "secondary")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        actions = QHBoxLayout()
        self.defaults_button = QPushButton("기본값 불러오기")
        self.defaults_button.setObjectName("quiet")
        self.defaults_button.clicked.connect(self.use_defaults)
        self.cancel_button = QPushButton("변경 취소")
        self.cancel_button.clicked.connect(lambda: self.load(self.saved))
        self.save_button = QPushButton("설정 저장")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.request_save)
        actions.addWidget(self.defaults_button)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.startup_mode.currentIndexChanged.connect(self.update_startup_controls)
        for combo in (self.folder_mode, self.startup_mode, self.appearance):
            combo.currentIndexChanged.connect(self.mark_dirty)
        for field in (*self.folder_fields.values(), *self.extension_fields.values(), self.default_folder):
            field.textChanged.connect(self.mark_dirty)
        self.excluded_extensions.textChanged.connect(self.mark_dirty)
        self.excluded_names.textChanged.connect(self.mark_dirty)
        self.load(settings)

    def load(self, settings: Settings, saved: bool = True):
        self._loading = True
        if saved:
            self.saved = settings
        self.folder_mode.setCurrentIndex(self.folder_mode.findData(settings.folder_mode))
        self.startup_mode.setCurrentIndex(self.startup_mode.findData(settings.startup_mode))
        self.appearance.setCurrentIndex(self.appearance.findData(settings.theme))
        self.default_folder.setText(settings.default_folder)
        self.default_folder.setToolTip(settings.default_folder)
        self.last_folder.setText(f"마지막 사용 폴더: {settings.last_folder}" if settings.last_folder else "아직 선택한 폴더가 없습니다.")
        for category in CATEGORIES:
            self.folder_fields[category].setText(settings.folder_names[category])
            self.extension_fields[category].setText(", ".join(settings.extensions[category]))
        self.excluded_extensions.setPlainText(", ".join(settings.excluded_extensions))
        self.excluded_names.setPlainText("\n".join(settings.excluded_names))
        self._loading = False
        self.dirty = not saved
        self.update_startup_controls()
        self.feedback.setObjectName("secondary")
        self.feedback.setText("변경 사항은 저장한 뒤 적용됩니다." if self.dirty else "설정은 이 컴퓨터에 저장됩니다. 작업 기록은 별도로 유지됩니다.")

    def mark_dirty(self, *_):
        if not self._loading:
            self.dirty = True
            self.feedback.setText("저장하지 않은 변경 사항이 있습니다.")

    def update_startup_controls(self, *_):
        enabled = self.startup_mode.currentData() == "default"
        self.default_folder.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "기본 시작 폴더 선택", self.default_folder.text() or str(Path.home()))
        if folder:
            self.default_folder.setText(str(Path(folder).resolve()))

    def use_defaults(self):
        self.load(replace(Settings(), last_folder=self.saved.last_folder), saved=False)

    def collect(self) -> Settings:
        return replace(
            self.saved,
            folder_mode=self.folder_mode.currentData(),
            startup_mode=self.startup_mode.currentData(),
            default_folder=self.default_folder.text(),
            theme=self.appearance.currentData(),
            folder_names={category: field.text() for category, field in self.folder_fields.items()},
            extensions={category: parse_entries(field.text()) for category, field in self.extension_fields.items()},
            excluded_extensions=parse_entries(self.excluded_extensions.toPlainText()),
            excluded_names=tuple(line.strip() for line in self.excluded_names.toPlainText().splitlines() if line.strip()),
        ).validated()

    def request_save(self):
        try:
            settings = self.collect()
        except SettingsError as error:
            self.feedback.setText(str(error))
            return
        self.saveRequested.emit(settings)
