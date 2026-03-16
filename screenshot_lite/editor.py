from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QVBoxLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QWidget,
)

from screenshot_lite.annotate import AnnotationCanvas, AnnotationToolbar
from screenshot_lite.ocr import OCRResultDialog, recognize_text
from screenshot_lite.settings_dialog import TranslationConfig


class EditorWindow(QMainWindow):
    pinRequested = Signal(QPixmap)

    def __init__(self, pixmap: QPixmap, translation_config: TranslationConfig) -> None:
        super().__init__()
        self._translation_config = translation_config
        self._canvas = AnnotationCanvas(pixmap)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidget(self._canvas)
        self._scroll_area.setWidgetResizable(False)
        self._toolbar = AnnotationToolbar(include_pin=True, transparent=True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(self._toolbar, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._scroll_area)
        self.setCentralWidget(container)

        self._bind_toolbar()
        self._build_shortcuts()
        self.resize(min(1200, pixmap.width() + 80), min(900, pixmap.height() + 120))
        self.setWindowTitle("Screenshot Lite")

    def _bind_toolbar(self) -> None:
        self._toolbar.toolChanged.connect(self._set_tool)
        self._toolbar.colorChanged.connect(self._canvas.set_color)
        self._toolbar.undoRequested.connect(self._canvas.undo)
        self._toolbar.redoRequested.connect(self._canvas.redo)
        self._toolbar.copyRequested.connect(self.copy_to_clipboard)
        self._toolbar.saveRequested.connect(self.save_image)
        self._toolbar.pinRequested.connect(self.pin_image)
        self._toolbar.ocrRequested.connect(self.run_ocr)
        self._toolbar.opacityDownRequested.connect(lambda: self.setWindowOpacity(max(0.4, self.windowOpacity() - 0.1)))
        self._toolbar.opacityUpRequested.connect(lambda: self.setWindowOpacity(min(1.0, self.windowOpacity() + 0.1)))
        self._toolbar.closeRequested.connect(self.close)
        self._toolbar.set_active_color(self._canvas.color(), emit_signal=False)

    def _set_tool(self, tool: str) -> None:
        self._canvas.set_tool(tool)
        self._toolbar.set_active_tool(tool)

    def _build_shortcuts(self) -> None:
        copy_shortcut = QAction(self)
        copy_shortcut.setShortcut(QKeySequence.StandardKey.Copy)
        copy_shortcut.triggered.connect(self.copy_to_clipboard)
        self.addAction(copy_shortcut)

        save_shortcut = QAction(self)
        save_shortcut.setShortcut(QKeySequence.StandardKey.Save)
        save_shortcut.triggered.connect(self.save_image)
        self.addAction(save_shortcut)

        undo_shortcut = QAction(self)
        undo_shortcut.setShortcut(QKeySequence.StandardKey.Undo)
        undo_shortcut.triggered.connect(self._canvas.undo)
        self.addAction(undo_shortcut)

        redo_shortcut = QAction(self)
        redo_shortcut.setShortcut(QKeySequence.StandardKey.Redo)
        redo_shortcut.triggered.connect(self._canvas.redo)
        self.addAction(redo_shortcut)

        pin_shortcut = QAction(self)
        pin_shortcut.setShortcut(QKeySequence("Ctrl+P"))
        pin_shortcut.triggered.connect(self.pin_image)
        self.addAction(pin_shortcut)

        close_shortcut = QAction(self)
        close_shortcut.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        close_shortcut.triggered.connect(self.close)
        self.addAction(close_shortcut)

    def final_pixmap(self) -> QPixmap:
        return self._canvas.composed_pixmap()

    def copy_to_clipboard(self) -> None:
        QApplication.clipboard().setPixmap(self.final_pixmap())
        self.statusBar().showMessage("已复制到剪贴板", 2000)

    def save_image(self) -> None:
        pictures_dir = Path.home() / "Pictures"
        pictures_dir.mkdir(exist_ok=True)
        default_name = f"screenshot_lite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        default_path = pictures_dir / default_name
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存截图",
            str(default_path),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;BMP 图片 (*.bmp)",
        )
        if not filename:
            return
        if not self.final_pixmap().save(filename):
            QMessageBox.warning(self, "保存失败", "图片保存失败，请检查路径权限")
            return
        self.statusBar().showMessage(f"已保存到 {filename}", 2500)

    def pin_image(self) -> None:
        self.pinRequested.emit(self.final_pixmap())
        self.statusBar().showMessage("已创建贴图", 2000)

    def run_ocr(self) -> None:
        text = recognize_text(self.final_pixmap())
        dialog = OCRResultDialog(text, self._translation_config, self)
        dialog.exec()
