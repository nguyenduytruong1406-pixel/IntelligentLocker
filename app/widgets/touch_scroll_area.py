from PyQt6.QtWidgets import QScrollArea
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent

class TouchScrollArea(QScrollArea):
    """ScrollArea hỗ trợ kéo bằng tay trên màn hình cảm ứng"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start = None
        self._scroll_start = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self._scroll_start = QPoint(
                self.horizontalScrollBar().value(),
                self.verticalScrollBar().value()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start is not None:
            delta = event.position().toPoint() - self._drag_start
            self.verticalScrollBar().setValue(
                self._scroll_start.y() - delta.y()
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_start = None
        self._scroll_start = None
        super().mouseReleaseEvent(event)