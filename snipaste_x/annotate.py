from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QColorDialog, QHBoxLayout, QInputDialog, QPushButton, QSizePolicy, QVBoxLayout, QWidget


@dataclass(slots=True)
class Annotation:
    kind: str
    start: QPoint
    end: QPoint | None = None
    text: str = ""
    color: QColor | None = None


class OutlinedToolButton(QPushButton):
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.isChecked() or not self.text():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        metrics = painter.fontMetrics()
        x = (self.width() - metrics.horizontalAdvance(self.text())) / 2
        y = (self.height() + metrics.ascent() - metrics.descent()) / 2

        path = QPainterPath()
        path.addText(x, y, painter.font(), self.text())
        painter.setPen(QPen(QColor("#08130d"), 2.4))
        painter.drawPath(path)
        painter.fillPath(path, QColor("#f8fafc"))


class AnnotationCanvas(QWidget):
    imageChanged = Signal()
    scaleChanged = Signal(float)

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()
        self._base_image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        self._tool = "select"
        self._start_point = QPoint()
        self._end_point = QPoint()
        self._dragging = False
        self._annotations: list[Annotation] = []
        self._redo_stack: list[Annotation] = []
        self._font = QFont("Sans Serif", 18)
        self._current_color = QColor("#ff5a36")
        self._display_scale = 1.0
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._update_display_size()

    def sizeHint(self) -> QSize:
        return self._scaled_size()

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        if tool == "select":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()
        self.update()

    def tool(self) -> str:
        return self._tool

    def set_color(self, color: QColor) -> None:
        self._current_color = QColor(color)

    def color(self) -> QColor:
        return QColor(self._current_color)

    def display_scale(self) -> float:
        return self._display_scale

    def image_size(self) -> QSize:
        return self._base_image.size()

    def handle_rects(self) -> dict[str, QRect]:
        size = 16
        half = size // 2
        rect = self.rect().adjusted(2, 2, -2, -2)
        center_x = rect.center().x()
        center_y = rect.center().y()
        return {
            "top_left": QRect(rect.left() - half, rect.top() - half, size, size),
            "top": QRect(center_x - half, rect.top() - half, size, size),
            "top_right": QRect(rect.right() - half, rect.top() - half, size, size),
            "right": QRect(rect.right() - half, center_y - half, size, size),
            "bottom_right": QRect(rect.right() - half, rect.bottom() - half, size, size),
            "bottom": QRect(center_x - half, rect.bottom() - half, size, size),
            "bottom_left": QRect(rect.left() - half, rect.bottom() - half, size, size),
            "left": QRect(rect.left() - half, center_y - half, size, size),
        }

    def handle_at(self, point: QPoint) -> str:
        if self._tool != "select":
            return ""
        for name, rect in self.handle_rects().items():
            if rect.contains(point):
                return name
        return ""

    def cursor_for_handle(self, handle: str) -> Qt.CursorShape:
        cursor_map = {
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
        }
        return cursor_map.get(handle, Qt.CursorShape.OpenHandCursor)

    def set_display_scale(self, scale: float) -> None:
        bounded_scale = max(0.2, min(4.0, scale))
        if abs(bounded_scale - self._display_scale) < 0.001:
            return
        self._display_scale = bounded_scale
        self._update_display_size()
        self.scaleChanged.emit(self._display_scale)
        self.update()

    def undo(self) -> None:
        if not self._annotations:
            return
        self._redo_stack.append(self._annotations.pop())
        self.update()
        self.imageChanged.emit()

    def redo(self) -> None:
        if not self._redo_stack:
            return
        self._annotations.append(self._redo_stack.pop())
        self.update()
        self.imageChanged.emit()

    def composed_image(self) -> QImage:
        image = self._base_image.copy()
        painter = QPainter(image)
        for annotation in self._annotations:
            self._paint_annotation(painter, annotation, scale=1.0)
        painter.end()
        return image

    def composed_pixmap(self) -> QPixmap:
        return QPixmap.fromImage(self.composed_image())

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._to_image_point(event.position().toPoint())
        if self._tool == "text":
            text, accepted = QInputDialog.getText(self, "添加文本", "输入文本内容")
            if accepted and text.strip():
                self._annotations.append(Annotation(kind="text", start=point, text=text.strip(), color=self.color()))
                self._redo_stack.clear()
                self.update()
                self.imageChanged.emit()
            return
        if self._tool == "select":
            return
        self._dragging = True
        self._start_point = point
        self._end_point = point
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        self._end_point = self._to_image_point(event.position().toPoint())
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        self._dragging = False
        self._end_point = self._to_image_point(event.position().toPoint())
        rect = QRect(self._start_point, self._end_point).normalized()
        if rect.width() < 4 or rect.height() < 4:
            self.update()
            return
        self._annotations.append(Annotation(kind=self._tool, start=rect.topLeft(), end=rect.bottomRight(), color=self.color()))
        self._redo_stack.clear()
        self.update()
        self.imageChanged.emit()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(QRect(QPoint(0, 0), self.size()), self._base_image)
        for annotation in self._annotations:
            self._paint_annotation(painter, annotation, scale=self._display_scale)
        if self._dragging and self._tool != "text":
            preview = Annotation(kind=self._tool, start=self._start_point, end=self._end_point, color=self.color())
            self._paint_annotation(painter, preview, preview_mode=True, scale=self._display_scale)
        if self._tool == "select":
            painter.setPen(QPen(QColor(255, 255, 255, 70), 1.2, Qt.PenStyle.DashLine))
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
            painter.setPen(QPen(QColor("#f8fafc"), 1.2))
            painter.setBrush(QColor(15, 23, 42, 185))
            for name, handle_rect in self.handle_rects().items():
                painter.drawRoundedRect(handle_rect, 5, 5)
                if name == "bottom_right":
                    painter.drawLine(handle_rect.left() + 4, handle_rect.bottom() - 4, handle_rect.right() - 4, handle_rect.top() + 4)
                    painter.drawLine(handle_rect.left() + 7, handle_rect.bottom() - 4, handle_rect.right() - 4, handle_rect.top() + 7)
        painter.end()

    def _paint_annotation(self, painter: QPainter, annotation: Annotation, preview_mode: bool = False, scale: float = 1.0) -> None:
        color = annotation.color if annotation.color is not None else self.color()

        if annotation.kind == "rect" and annotation.end is not None:
            rect = self._scaled_rect(QRect(annotation.start, annotation.end).normalized(), scale)
            painter.setPen(QPen(color, max(2, int(round(3 * scale))), Qt.PenStyle.SolidLine))
            painter.drawRect(rect)
            return

        if annotation.kind == "arrow" and annotation.end is not None:
            start = self._scaled_point(annotation.start, scale)
            end = self._scaled_point(annotation.end, scale)
            painter.setPen(QPen(color, max(2, int(round(4 * scale))), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            self._draw_arrow_head(painter, start, end, color, scale)
            return

        if annotation.kind == "text":
            font = QFont(self._font)
            font.setPointSizeF(max(8.0, self._font.pointSizeF() * scale))
            painter.setPen(color)
            painter.setFont(font)
            painter.drawText(self._scaled_point(annotation.start, scale), annotation.text)
            return

        if annotation.kind == "mosaic" and annotation.end is not None:
            source_rect = QRect(annotation.start, annotation.end).normalized().intersected(self._image_rect())
            if source_rect.isEmpty():
                return
            target_rect = self._scaled_rect(source_rect, scale)
            source = self._base_image.copy(source_rect)
            tiny = source.scaled(
                max(1, source_rect.width() // 12),
                max(1, source_rect.height() // 12),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            mosaic = tiny.scaled(
                target_rect.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            painter.drawImage(target_rect.topLeft(), mosaic)
            if preview_mode:
                painter.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine))
                painter.drawRect(target_rect)

    def _draw_arrow_head(self, painter: QPainter, start: QPoint, end: QPoint, color: QColor, scale: float) -> None:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = max((dx * dx + dy * dy) ** 0.5, 1.0)
        ux = dx / length
        uy = dy / length
        arrow_size = max(10.0, 14.0 * scale)

        left = QPoint(
            int(end.x() - arrow_size * ux - arrow_size * 0.6 * uy),
            int(end.y() - arrow_size * uy + arrow_size * 0.6 * ux),
        )
        right = QPoint(
            int(end.x() - arrow_size * ux + arrow_size * 0.6 * uy),
            int(end.y() - arrow_size * uy - arrow_size * 0.6 * ux),
        )

        path = QPainterPath()
        path.moveTo(end)
        path.lineTo(left)
        path.lineTo(right)
        path.closeSubpath()
        painter.fillPath(path, color)

    def _scaled_size(self) -> QSize:
        size = self._base_image.size()
        return QSize(max(1, int(round(size.width() * self._display_scale))), max(1, int(round(size.height() * self._display_scale))))

    def _update_display_size(self) -> None:
        scaled = self._scaled_size()
        self.setMinimumSize(scaled)
        self.resize(scaled)
        self.updateGeometry()

    def _scaled_point(self, point: QPoint, scale: float) -> QPoint:
        return QPoint(int(round(point.x() * scale)), int(round(point.y() * scale)))

    def _scaled_rect(self, rect: QRect, scale: float) -> QRect:
        top_left = self._scaled_point(rect.topLeft(), scale)
        bottom_right = self._scaled_point(rect.bottomRight(), scale)
        return QRect(top_left, bottom_right).normalized()

    def _to_image_point(self, point: QPoint) -> QPoint:
        x = int(round(point.x() / self._display_scale))
        y = int(round(point.y() / self._display_scale))
        image_rect = self._image_rect()
        return QPoint(
            max(image_rect.left(), min(x, image_rect.right())),
            max(image_rect.top(), min(y, image_rect.bottom())),
        )

    def _image_rect(self) -> QRect:
        return QRect(QPoint(0, 0), self._base_image.size())


class AnnotationToolbar(QWidget):
    toolChanged = Signal(str)
    colorChanged = Signal(QColor)
    undoRequested = Signal()
    redoRequested = Signal()
    copyRequested = Signal()
    saveRequested = Signal()
    pinRequested = Signal()
    ocrRequested = Signal()
    opacityDownRequested = Signal()
    opacityUpRequested = Signal()
    closeRequested = Signal()

    def __init__(self, include_pin: bool = True, transparent: bool = True) -> None:
        super().__init__()
        self._tool_buttons: dict[str, QPushButton] = {}
        self._current_color = QColor("#ff5a36")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, transparent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            "QWidget { background: transparent; }"
            "QPushButton {"
            "background: rgba(15, 23, 42, 145);"
            "color: white;"
            "border: 1px solid rgba(255, 255, 255, 38);"
            "padding: 7px 12px;"
            "border-radius: 9px;"
            "font-size: 13px;"
            "}"
            "QPushButton:checked { background: rgba(61, 220, 151, 200); color: transparent; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 65); }"
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(6)

        panel = QWidget(self)
        panel.setStyleSheet(
            "QWidget { background: rgba(7, 12, 20, 110); border: 1px solid rgba(255, 255, 255, 30); border-radius: 14px; }"
        )
        root_layout.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        tools_row = QHBoxLayout()
        tools_row.setContentsMargins(0, 0, 0, 0)
        tools_row.setSpacing(6)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(6)

        for label, tool in [("选择", "select"), ("矩形", "rect"), ("箭头", "arrow"), ("文本", "text"), ("马赛克", "mosaic")]:
            button = OutlinedToolButton(label, self)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, selected=tool: self.toolChanged.emit(selected))
            tools_row.addWidget(button)
            self._tool_buttons[tool] = button

        self._color_button = QPushButton("颜色", self)
        self._color_button.clicked.connect(self._open_color_dialog)
        tools_row.addWidget(self._color_button)

        for hex_color in ["#ff5a36", "#00bcd4", "#ffeb3b", "#8b5cf6", "#22c55e"]:
            swatch = QPushButton("", self)
            swatch.setFixedSize(26, 26)
            swatch.setStyleSheet(
                f"QPushButton {{ background: {hex_color}; border: 1px solid rgba(255, 255, 255, 70); border-radius: 13px; padding: 0; }}"
                f"QPushButton:hover {{ background: {hex_color}; border: 2px solid white; }}"
            )
            swatch.clicked.connect(lambda checked=False, selected=hex_color: self.set_active_color(QColor(selected), emit_signal=True))
            tools_row.addWidget(swatch)

        for label, signal in [
            ("撤销", self.undoRequested),
            ("重做", self.redoRequested),
            ("复制", self.copyRequested),
            ("保存", self.saveRequested),
            ("识别文字", self.ocrRequested),
        ]:
            button = QPushButton(label, self)
            button.clicked.connect(signal.emit)
            actions_row.addWidget(button)

        if include_pin:
            pin_button = QPushButton("贴图", self)
            pin_button.clicked.connect(self.pinRequested.emit)
            actions_row.addWidget(pin_button)

        for label, signal in [("透明-", self.opacityDownRequested), ("透明+", self.opacityUpRequested), ("关闭", self.closeRequested)]:
            button = QPushButton(label, self)
            button.clicked.connect(signal.emit)
            actions_row.addWidget(button)

        layout.addLayout(tools_row)
        layout.addLayout(actions_row)
        self.set_active_tool("select")
        self.set_active_color(self._current_color, emit_signal=False)

    def set_active_tool(self, tool: str) -> None:
        for name, button in self._tool_buttons.items():
            button.setChecked(name == tool)

    def set_active_color(self, color: QColor, emit_signal: bool = False) -> None:
        self._current_color = QColor(color)
        text_color = "#08130d" if self._current_color.lightness() > 140 else "white"
        self._color_button.setStyleSheet(
            f"QPushButton {{ background: {self._current_color.name()}; color: {text_color}; border: 1px solid rgba(255, 255, 255, 65); padding: 7px 12px; border-radius: 9px; }}"
        )
        if emit_signal:
            self.colorChanged.emit(self._current_color)

    def _open_color_dialog(self) -> None:
        color = QColorDialog.getColor(self._current_color, self, "选择标注颜色")
        if color.isValid():
            self.set_active_color(color, emit_signal=True)
