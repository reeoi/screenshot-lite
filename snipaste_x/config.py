from __future__ import annotations

from PySide6.QtCore import QSettings

from snipaste_x.settings_dialog import ShortcutConfig, TranslationConfig


class AppSettings:
    def __init__(self) -> None:
        self._settings = QSettings("ScreenshotLite", "ScreenshotLite")

    def load_shortcuts(self) -> ShortcutConfig:
        return ShortcutConfig(
            region_capture=self._settings.value("shortcuts/region_capture", "Ctrl+Alt+A", type=str),
            fullscreen_capture=self._settings.value("shortcuts/fullscreen_capture", "Ctrl+Alt+F", type=str),
        )

    def save_shortcuts(self, config: ShortcutConfig) -> None:
        self._settings.setValue("shortcuts/region_capture", config.region_capture)
        self._settings.setValue("shortcuts/fullscreen_capture", config.fullscreen_capture)
        self._settings.sync()

    def load_translation(self) -> TranslationConfig:
        return TranslationConfig(
            source_language=self._settings.value("translation/source_language", "auto", type=str),
            target_language=self._settings.value("translation/target_language", "zh-CN", type=str),
            auto_translate_ocr=self._settings.value("translation/auto_translate_ocr", False, type=bool),
        )

    def save_translation(self, config: TranslationConfig) -> None:
        self._settings.setValue("translation/source_language", config.source_language)
        self._settings.setValue("translation/target_language", config.target_language)
        self._settings.setValue("translation/auto_translate_ocr", config.auto_translate_ocr)
        self._settings.sync()
