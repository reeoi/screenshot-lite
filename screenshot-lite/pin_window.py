from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QVBoxLayout,
    QWidget,
)

from snipaste_x.annotate import AnnotationCanvas, AnnotationToolbar
from snipaste_x.ocr import OCRResultDialog, recognize_text
from snipaste_x.settings_dialog import TranslationConfig

class PinnedImageWindow(QWidget):
    def __init__(self, pixmap: QPixmap, translation_config: TranslationConfig) -> None:
        super().__init__()
        self._drag_offset = QPoint()
        self._dragging_window = False
        self._resizing = False
        self._active_handle = ""
        self._resize_origin = QPoint()
        self._resize_start_scale = 1.0
        self._resize_start_geometry = QRect()
        self._translation_config = translation_config
        self._canvas = AnnotationCanvas(pixmap)
        self._canvas.installEventFilter(self)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(
            "QWidget { background: transparent; }"
            "AnnotationCanvas { border: 1px solid rgba(255, 255, 255, 40); background: #111827; }"
        )

        self._toolbar = AnnotationToolbar(include_pin=False, transparent=True)
        self._toolbar.toolChanged.connect(self._set_tool)
        self._toolbar.colorChanged.connect(self._canvas.set_color)
        self._toolbar.undoRequested.connect(self._canvas.undo)
        self._toolbar.redoRequested.connect(self._canvas.redo)
        self._toolbar.copyRequested.connect(self._copy_image)
        self._toolbar.saveRequested.connect(self._save_image)
        self._toolbar.ocrRequested.connect(self._run_ocr)
        self._toolbar.opacityDownRequested.connect(self._decrease_opacity)
        self._toolbar.opacityUpRequested.connect(self._increase_opacity)
        self._toolbar.closeRequested.connect(self.close)
        self._toolbar.set_active_color(self._canvas.color(), emit_signal=False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._toolbar, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._canvas)
        self.adjustSize()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._canvas:
            if event.type() == event.Type.MouseButtonPress:
                if self._canvas.tool() == "select" and event.button() == Qt.MouseButton.LeftButton:
                    handle = self._canvas.handle_at(event.position().toPoint())
                    if handle:
                        self._resizing = True
                        self._active_handle = handle
                        self._resize_origin = event.globalPosition().toPoint()
                        self._resize_start_scale = self._canvas.display_scale()
                        self._resize_start_geometry = self.frameGeometry()
                        self._canvas.setCursor(self._canvas.cursor_for_handle(handle))
                        return True
                    self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    self._dragging_window = True
                    self._canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True
            if event.type() == event.Type.MouseMove:
                if self._canvas.tool() == "select":
                    if self._resizing:
                        self._resize_from_handle(event.globalPosition().toPoint())
                        return True
                    handle = self._canvas.handle_at(event.position().toPoint())
                    if handle:
                        self._canvas.setCursor(self._canvas.cursor_for_handle(handle))
                    else:
                        self._canvas.setCursor(Qt.CursorShape.OpenHandCursor)
                if self._dragging_window and event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._drag_offset)
                    return True
            if event.type() == event.Type.MouseButtonRelease:
                self._dragging_window = False
                self._resizing = False
                self._active_handle = ""
                if self._canvas.tool() == "select":
                    self._canvas.setCursor(Qt.CursorShape.OpenHandCursor)
                    return True
            if event.type() == event.Type.Wheel:
                self.wheelEvent(event)
                return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = 0.05 if event.angleDelta().y() > 0 else -0.05
        opacity = min(1.0, max(0.2, self.windowOpacity() + delta))
        self.setWindowOpacity(opacity)
        event.accept()

    def _copy_image(self) -> None:
        QApplication.clipboard().setPixmap(self._canvas.composed_pixmap())

    def _save_image(self) -> None:
        pictures_dir = Path.home() / "Pictures"
        pictures_dir.mkdir(exist_ok=True)
        default_name = f"screenshot_lite_pin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        default_path = pictures_dir / default_name
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存贴图",
            str(default_path),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;BMP 图片 (*.bmp)",
        )
        if filename:
            self._canvas.composed_pixmap().save(filename)

    def _set_tool(self, tool: str) -> None:
        self._canvas.set_tool(tool)
        self._toolbar.set_active_tool(tool)

    def _resize_from_handle(self, global_point: QPoint) -> None:
        delta = global_point - self._resize_origin
        base_width = max(1, self._canvas.image_size().width())
        base_height = max(1, self._canvas.image_size().height())

        deltas: list[float] = []
        if "left" in self._active_handle:
            deltas.append(-delta.x() / float(base_width))
        if "right" in self._active_handle:
            deltas.append(delta.x() / float(base_width))
        if "top" in self._active_handle:
            deltas.append(-delta.y() / float(base_height))
        if "bottom" in self._active_handle:
            deltas.append(delta.y() / float(base_height))
        if not deltas:
            return

        if len(deltas) == 1:
            scale_delta = deltas[0]
        else:
            scale_delta = sum(deltas) / len(deltas)

        previous_geometry = self.frameGeometry()
        self._canvas.set_display_scale(self._resize_start_scale + scale_delta)
        self.adjustSize()
        new_geometry = self.frameGeometry()

        target_left = previous_geometry.left()
        target_top = previous_geometry.top()
        if "left" in self._active_handle:
            target_left = self._resize_start_geometry.right() - new_geometry.width() + 1
        if "top" in self._active_handle:
            target_top = self._resize_start_geometry.bottom() - new_geometry.height() + 1
        self.move(target_left, target_top)

    def _run_ocr(self) -> None:
        text = recognize_text(self._canvas.composed_pixmap())
        dialog = OCRResultDialog(text, self._translation_config, self)
        dialog.exec()

    def _increase_opacity(self) -> None:
        self.setWindowOpacity(min(1.0, self.windowOpacity() + 0.1))

    def _decrease_opacity(self) -> None:
        self.setWindowOpacity(max(0.2, self.windowOpacity() - 0.1))
