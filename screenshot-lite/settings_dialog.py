from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QVBoxLayout,
)


@dataclass(slots=True)
class ShortcutConfig:
    region_capture: str
    fullscreen_capture: str


@dataclass(slots=True)
class TranslationConfig:
    source_language: str
    target_language: str
    auto_translate_ocr: bool


TRANSLATION_LANGUAGES = [
    ("自动检测", "auto"),
    ("简体中文", "zh-CN"),
    ("繁体中文", "zh-TW"),
    ("英文", "en"),
    ("日文", "ja"),
    ("韩文", "ko"),
    ("法文", "fr"),
    ("德文", "de"),
    ("西班牙文", "es"),
    ("俄文", "ru"),
]


class ShortcutSettingsDialog(QDialog):
    def __init__(self, config: ShortcutConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setModal(True)

        self._region_edit = QKeySequenceEdit(QKeySequence(config.region_capture), self)
        self._fullscreen_edit = QKeySequenceEdit(QKeySequence(config.fullscreen_capture), self)

        form = QFormLayout()
        form.addRow("区域截图", self._region_edit)
        form.addRow("全屏截图", self._fullscreen_edit)

        hint = QLabel("保存后会立即尝试注册全局快捷键。若当前桌面环境不支持，全局热键可能不可用。", self)
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def config(self) -> ShortcutConfig:
        region = self._region_edit.keySequence().toString(QKeySequence.SequenceFormat.NativeText)
        fullscreen = self._fullscreen_edit.keySequence().toString(QKeySequence.SequenceFormat.NativeText)
        return ShortcutConfig(
            region_capture=region or "Ctrl+Alt+A",
            fullscreen_capture=fullscreen or "Ctrl+Alt+F",
        )


class TranslationSettingsDialog(QDialog):
    def __init__(self, config: TranslationConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("翻译设置")
        self.setModal(True)

        self._source_combo = QComboBox(self)
        self._target_combo = QComboBox(self)
        for label, code in TRANSLATION_LANGUAGES:
            self._source_combo.addItem(label, code)
            self._target_combo.addItem(label, code)

        self._set_current_language(self._source_combo, config.source_language)
        self._set_current_language(self._target_combo, config.target_language)

        self._auto_translate = QCheckBox("OCR 完成后自动翻译", self)
        self._auto_translate.setChecked(config.auto_translate_ocr)

        form = QFormLayout()
        form.addRow("源语言", self._source_combo)
        form.addRow("目标语言", self._target_combo)
        form.addRow("", self._auto_translate)

        hint = QLabel("翻译使用在线服务。若网络不可用或目标站点不可访问，翻译按钮会提示失败原因。", self)
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def config(self) -> TranslationConfig:
        return TranslationConfig(
            source_language=self._source_combo.currentData(),
            target_language=self._target_combo.currentData(),
            auto_translate_ocr=self._auto_translate.isChecked(),
        )

    def _set_current_language(self, combo_box: QComboBox, code: str) -> None:
        index = combo_box.findData(code)
        combo_box.setCurrentIndex(index if index >= 0 else 0)
