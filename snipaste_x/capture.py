from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


@dataclass(slots=True)
class CapturedPixmap:
    pixmap: QPixmap
    origin: QPoint


@dataclass(slots=True)
class SelectionResult:
    pixmap: QPixmap
    rect: QRect


def capture_desktop() -> CapturedPixmap:
    screens = QGuiApplication.screens()
    if not screens:
        return CapturedPixmap(QPixmap(), QPoint())

    geometries = [screen.geometry() for screen in screens]
    min_x = min(geometry.x() for geometry in geometries)
    min_y = min(geometry.y() for geometry in geometries)
    max_x = max(geometry.x() + geometry.width() for geometry in geometries)
    max_y = max(geometry.y() + geometry.height() for geometry in geometries)
    virtual_rect = QRect(min_x, min_y, max_x - min_x, max_y - min_y)

    canvas = QPixmap(virtual_rect.size())
    canvas.fill(Qt.GlobalColor.transparent)

    painter = QPainter(canvas)
    for screen in screens:
        geometry = screen.geometry()
        screenshot = screen.grabWindow(0)
        painter.drawPixmap(geometry.topLeft() - virtual_rect.topLeft(), screenshot)
    painter.end()
    return CapturedPixmap(canvas, virtual_rect.topLeft())


class ScreenCaptureOverlay(QWidget):
    selectionFinished = Signal(object)
    canceled = Signal()

    def __init__(self, capture: CapturedPixmap) -> None:
        super().__init__()
        self._capture = capture
        self._selection_rect = QRect()
        self._drag_origin = QPoint()
        self._drag_start_selection = QRect()
        self._interaction = "idle"
        self._active_handle = ""
        self._handle_size = 10
        self._minimum_selection = 16

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QRect(capture.origin, capture.pixmap.size()))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._action_bar = QWidget(self)
        self._action_bar.hide()
        self._action_bar.setStyleSheet(
            "background-color: rgba(15, 23, 42, 218);"
            "border: 1px solid rgba(255, 255, 255, 44);"
            "border-radius: 12px;"
        )
        layout = QHBoxLayout(self._action_bar)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self._size_label = QLabel("0 x 0", self._action_bar)
        self._size_label.setStyleSheet("color: rgba(255,255,255,0.94); font-weight: 600; padding-right: 10px;")
        layout.addWidget(self._size_label)

        self._confirm_button = QPushButton("确认", self._action_bar)
        self._confirm_button.clicked.connect(self._confirm_selection)
        self._confirm_button.setStyleSheet(
            "QPushButton { background: #3ddc97; color: #08130d; border: none;"
            "padding: 6px 14px; border-radius: 6px; font-weight: 600; }"
        )
        layout.addWidget(self._confirm_button)

        self._cancel_button = QPushButton("取消", self._action_bar)
        self._cancel_button.clicked.connect(self._cancel_selection)
        self._cancel_button.setStyleSheet(
            "QPushButton { background: #1f2937; color: white; border: none;"
            "padding: 6px 14px; border-radius: 6px; }"
        )
        layout.addWidget(self._cancel_button)

        self._hint_label = QLabel("拖动选择区域，双击或 Enter 确认，Esc 取消", self)
        self._hint_label.setStyleSheet(
            "QLabel { background: rgba(15, 23, 42, 160); color: rgba(255,255,255,0.94);"
            "border: 1px solid rgba(255,255,255,0.18); border-radius: 10px; padding: 8px 12px; }"
        )
        self._hint_label.adjustSize()
        self._hint_label.move(20, 20)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._selection_rect.contains(event.position().toPoint()):
            self._confirm_selection()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        handle = self._handle_at(point)
        if handle:
            self._interaction = "resize"
            self._active_handle = handle
            self._drag_start_selection = QRect(self._selection_rect)
            self._drag_origin = point
            self._action_bar.hide()
        elif self._selection_rect.contains(point):
            self._interaction = "move"
            self._drag_start_selection = QRect(self._selection_rect)
            self._drag_origin = point
            self._action_bar.hide()
        else:
            self._interaction = "draw"
            self._drag_origin = point
            self._selection_rect = QRect(point, point)
            self._action_bar.hide()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if self._interaction == "idle":
            self._update_cursor(point)
            return

        if self._interaction == "draw":
            self._selection_rect = QRect(self._drag_origin, point).normalized().intersected(self.rect())
        elif self._interaction == "move":
            delta = point - self._drag_origin
            moved = self._drag_start_selection.translated(delta)
            self._selection_rect = self._bounded_rect(moved)
        elif self._interaction == "resize":
            self._selection_rect = self._resize_rect(point)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._interaction == "idle":
            return
        self._interaction = "idle"
        self._active_handle = ""
        if self._selection_rect.width() < self._minimum_selection or self._selection_rect.height() < self._minimum_selection:
            self._selection_rect = QRect()
            self._action_bar.hide()
        else:
            self._size_label.setText(f"{self._selection_rect.width()} x {self._selection_rect.height()}")
            self._action_bar.adjustSize()
            self._reposition_action_bar()
            self._action_bar.show()
            self._action_bar.raise_()
        self._update_cursor(event.position().toPoint())
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._selection_rect.isNull():
                self.canceled.emit()
                self.close()
            else:
                self._cancel_selection()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self._selection_rect.isNull():
            self._confirm_selection()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._capture.pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        selection = self._selection_rect.normalized()
        if selection.width() > 1 and selection.height() > 1:
            painter.drawPixmap(selection, self._capture.pixmap, selection)
            painter.setPen(QPen(QColor("#3ddc97"), 2))
            painter.drawRect(selection)
            self._paint_handles(painter, selection)
            self._paint_size_badge(painter, selection)
        painter.end()

    def _cancel_selection(self) -> None:
        self._selection_rect = QRect()
        self._interaction = "idle"
        self._active_handle = ""
        self._action_bar.hide()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def _confirm_selection(self) -> None:
        selection = self._selection_rect.normalized()
        if selection.width() < self._minimum_selection or selection.height() < self._minimum_selection:
            return
        global_rect = QRect(selection.topLeft() + self._capture.origin, selection.size())
        self.selectionFinished.emit(SelectionResult(self._capture.pixmap.copy(selection), global_rect))
        self.close()

    def _handle_at(self, point: QPoint) -> str:
        if self._selection_rect.isNull():
            return ""
        for name, rect in self._handle_rects(self._selection_rect).items():
            if rect.contains(point):
                return name
        return ""

    def _handle_rects(self, rect: QRect) -> dict[str, QRect]:
        size = self._handle_size
        half = size // 2
        left = rect.left()
        right = rect.right()
        top = rect.top()
        bottom = rect.bottom()
        center_x = rect.center().x()
        center_y = rect.center().y()
        return {
            "top_left": QRect(left - half, top - half, size, size),
            "top": QRect(center_x - half, top - half, size, size),
            "top_right": QRect(right - half, top - half, size, size),
            "right": QRect(right - half, center_y - half, size, size),
            "bottom_right": QRect(right - half, bottom - half, size, size),
            "bottom": QRect(center_x - half, bottom - half, size, size),
            "bottom_left": QRect(left - half, bottom - half, size, size),
            "left": QRect(left - half, center_y - half, size, size),
        }

    def _paint_handles(self, painter: QPainter, rect: QRect) -> None:
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(QColor("#111827"))
        for handle_rect in self._handle_rects(rect).values():
            painter.drawRect(handle_rect)

    def _paint_size_badge(self, painter: QPainter, rect: QRect) -> None:
        badge_rect = QRect(rect.left(), max(12, rect.top() - 34), 122, 26)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 220))
        painter.drawRoundedRect(badge_rect, 8, 8)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(
            badge_rect.adjusted(10, 0, -10, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"{rect.width()} x {rect.height()}",
        )

    def _update_cursor(self, point: QPoint) -> None:
        handle = self._handle_at(point)
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
        if handle:
            self.setCursor(cursor_map[handle])
        elif self._selection_rect.contains(point):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def _bounded_rect(self, rect: QRect) -> QRect:
        bounded = QRect(rect)
        if bounded.left() < 0:
            bounded.moveLeft(0)
        if bounded.top() < 0:
            bounded.moveTop(0)
        if bounded.right() > self.rect().right():
            bounded.moveRight(self.rect().right())
        if bounded.bottom() > self.rect().bottom():
            bounded.moveBottom(self.rect().bottom())
        return bounded

    def _resize_rect(self, point: QPoint) -> QRect:
        rect = QRect(self._drag_start_selection)
        x = max(0, min(point.x(), self.rect().right()))
        y = max(0, min(point.y(), self.rect().bottom()))

        if "left" in self._active_handle:
            rect.setLeft(x)
        if "right" in self._active_handle:
            rect.setRight(x)
        if "top" in self._active_handle:
            rect.setTop(y)
        if "bottom" in self._active_handle:
            rect.setBottom(y)

        rect = rect.normalized().intersected(self.rect())
        if rect.width() < self._minimum_selection:
            if "left" in self._active_handle:
                rect.setLeft(rect.right() - self._minimum_selection)
            else:
                rect.setRight(rect.left() + self._minimum_selection)
        if rect.height() < self._minimum_selection:
            if "top" in self._active_handle:
                rect.setTop(rect.bottom() - self._minimum_selection)
            else:
                rect.setBottom(rect.top() + self._minimum_selection)
        return rect.intersected(self.rect())

    def _reposition_action_bar(self) -> None:
        self._action_bar.adjustSize()
        selection = self._selection_rect.normalized()
        margin = 12
        preferred_x = selection.right() - self._action_bar.width()
        x = max(margin, min(preferred_x, self.width() - self._action_bar.width() - margin))
        above_y = selection.top() - self._action_bar.height() - margin
        below_y = selection.bottom() + margin
        y = above_y if above_y >= margin else min(below_y, self.height() - self._action_bar.height() - margin)
        self._action_bar.move(x, y)
