from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import pyqtSignal, Qt, QTimer


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.original_style = ""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.original_style = self.styleSheet()
            self.setStyleSheet(
                self.original_style
                + "; background-color: rgba(0, 0, 0, 0.15); border-radius: 6px;"
            )
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            QTimer.singleShot(120, lambda: self.setStyleSheet(self.original_style))
        super().mouseReleaseEvent(event)