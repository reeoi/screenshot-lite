from __future__ import annotations

import sys

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from screenshot-lite.capture import ScreenCaptureOverlay, SelectionResult, capture_desktop
from screenshot-lite.config import AppSettings
from screenshot-lite.editor import EditorWindow
from screenshot-lite.hotkeys import GlobalHotkeyManager
from screenshot-lite.pin_window import PinnedImageWindow
from screenshot-lite.settings_dialog import ShortcutSettingsDialog, TranslationSettingsDialog


class SnipasteApplication(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self._tray = QSystemTrayIcon(self._build_icon(), self)
        self._tray.setToolTip("Screenshot Lite")
        self._tray.activated.connect(self._handle_tray_activated)
        self._settings = AppSettings()
        self._shortcuts = self._settings.load_shortcuts()
        self._translation = self._settings.load_translation()
        self._hotkeys = GlobalHotkeyManager()
        self._editors: list[EditorWindow] = []
        self._pin_windows: list[PinnedImageWindow] = []
        self._overlay: ScreenCaptureOverlay | None = None
        self._build_menu()
        self._hotkeys.regionTriggered.connect(self.start_region_capture)
        self._hotkeys.fullscreenTriggered.connect(self.capture_fullscreen)
        self._register_hotkeys(show_feedback=False)
        self._tray.show()

    def _build_menu(self) -> None:
        menu = QMenu()

        self._region_action = QAction(self)
        self._region_action.triggered.connect(self.start_region_capture)
        menu.addAction(self._region_action)

        self._fullscreen_action = QAction(self)
        self._fullscreen_action.triggered.connect(self.capture_fullscreen)
        menu.addAction(self._fullscreen_action)

        shortcut_action = QAction("快捷键设置", self)
        shortcut_action.triggered.connect(self.open_shortcut_settings)
        menu.addAction(shortcut_action)

        translation_action = QAction("翻译设置", self)
        translation_action.triggered.connect(self.open_translation_settings)
        menu.addAction(translation_action)

        menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._app.quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._refresh_shortcut_labels()

    def _refresh_shortcut_labels(self) -> None:
        self._region_action.setText("区域截图")
        self._region_action.setShortcut(QKeySequence(self._shortcuts.region_capture))
        self._region_action.setShortcutVisibleInContextMenu(True)

        self._fullscreen_action.setText("全屏截图")
        self._fullscreen_action.setShortcut(QKeySequence(self._shortcuts.fullscreen_capture))
        self._fullscreen_action.setShortcutVisibleInContextMenu(True)

    def _build_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("#111827"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#f9fafb"))
        painter.drawRect(10, 10, 44, 44)
        painter.fillRect(20, 20, 24, 24, QColor("#3ddc97"))
        painter.end()
        return QIcon(pixmap)

    def _handle_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.start_region_capture()

    def start_region_capture(self) -> None:
        capture = capture_desktop()
        if capture.pixmap.isNull():
            QMessageBox.warning(None, "截图失败", "未能获取桌面图像")
            return
        self._overlay = ScreenCaptureOverlay(capture)
        self._overlay.selectionFinished.connect(self._create_pin_from_selection)
        self._overlay.canceled.connect(self._clear_overlay)
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()

    def capture_fullscreen(self) -> None:
        capture = capture_desktop()
        if capture.pixmap.isNull():
            QMessageBox.warning(None, "截图失败", "未能获取桌面图像")
            return
        self.open_editor(capture.pixmap)

    def open_editor(self, pixmap: QPixmap) -> None:
        self._clear_overlay()
        editor = EditorWindow(pixmap, self._translation)
        editor.pinRequested.connect(self._create_pin_window)
        self._editors.append(editor)
        editor.destroyed.connect(lambda _=None, window=editor: self._remove_editor(window))
        editor.show()
        editor.raise_()
        editor.activateWindow()

    def _create_pin_from_selection(self, selection: SelectionResult) -> None:
        self._clear_overlay()
        self._create_pin_window(selection.pixmap, selection.rect.topLeft())

    def _create_pin_window(self, pixmap: QPixmap, position=None) -> None:
        pin_window = PinnedImageWindow(pixmap, self._translation)
        self._pin_windows.append(pin_window)
        pin_window.destroyed.connect(lambda _=None, window=pin_window: self._remove_pin_window(window))
        if position is not None:
            pin_window.move(position)
        pin_window.show()

    def open_shortcut_settings(self) -> None:
        dialog = ShortcutSettingsDialog(self._shortcuts)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._shortcuts = dialog.config()
        self._settings.save_shortcuts(self._shortcuts)
        self._refresh_shortcut_labels()
        self._register_hotkeys(show_feedback=True)

    def open_translation_settings(self) -> None:
        dialog = TranslationSettingsDialog(self._translation)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._translation = dialog.config()
        self._settings.save_translation(self._translation)
        self._tray.showMessage("Screenshot Lite", "翻译设置已更新", QSystemTrayIcon.MessageIcon.Information, 2500)

    def _register_hotkeys(self, show_feedback: bool) -> None:
        result = self._hotkeys.register(
            self._shortcuts.region_capture,
            self._shortcuts.fullscreen_capture,
        )
        if show_feedback:
            if result.success:
                self._tray.showMessage("Screenshot Lite", "快捷键已更新", QSystemTrayIcon.MessageIcon.Information, 2500)
            else:
                QMessageBox.warning(None, "快捷键注册失败", result.message)

    def _remove_editor(self, window: EditorWindow) -> None:
        self._editors = [candidate for candidate in self._editors if candidate is not window]

    def _remove_pin_window(self, window: PinnedImageWindow) -> None:
        self._pin_windows = [candidate for candidate in self._pin_windows if candidate is not window]

    def _clear_overlay(self) -> None:
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None


def main() -> int:
    QGuiApplication.setApplicationDisplayName("Screenshot Lite")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Screenshot Lite")
    app.setOrganizationName("ScreenshotLite")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "环境不支持", "当前系统不支持托盘，程序无法继续运行")
        return 1

    manager = SnipasteApplication(app)
    app.aboutToQuit.connect(manager._hotkeys.unregister)
    app.aboutToQuit.connect(manager.deleteLater)
    return app.exec()
