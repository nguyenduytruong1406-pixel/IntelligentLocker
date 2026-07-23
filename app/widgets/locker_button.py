from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtCore import QRectF, Qt

class LockerButton(QPushButton):

    # Icon + màu badge theo từng trạng thái
    BADGE_ICON = {
        "available":            ("✓", "#22C55E"),
        "busy":                 ("🔒", "#EF4444"),
        "selected":              ("✓", "#2563EB"),
        "mylocker":              ("🔑", "#2563EB"),
        "maintenance":           ("🔧", "#F59E0B"),   # sau khi tách riêng khỏi "mylocker"
        "maintenance_selected":  ("🔧", "#C2410C"),
    }

    def __init__(self,locker_id):

        super().__init__()
        self.locker_id = f"L{locker_id:02d}"
        self.setText(f"TỦ {locker_id:02d}")
        self.setProperty("lockerState", "available")

    # =========================
    # AVAILABLE
    # =========================
    def set_available(self):

        self.setEnabled(True)

        self.setProperty(
            "lockerState",
            "available"
        )

        self.refresh_style()

    # =========================
    # BUSY
    # =========================
    def set_busy(self):

        self.setEnabled(False)

        self.setProperty(
            "lockerState",
            "busy"
        )

        self.refresh_style()

    # =========================
    # SELECTED
    # =========================
    def set_selected(self):

        self.setEnabled(True)

        self.setProperty(
            "lockerState",
            "selected"
        )

        self.refresh_style()

    # =========================
    # MY LOCKER
    # =========================
    def set_my_locker(self):

        self.setEnabled(True)

        self.setProperty(
            "lockerState",
            "mylocker"
        )

        self.refresh_style()

    # ========================= 
# MAINTENANCE
# =========================
    def set_maintenance(self):
        """
        Trạng thái bảo trì - màu vàng, KHÔNG thể click
        """
        self.setEnabled(False)  # ✅ DISABLED - không thể click
        
        self.setProperty(
            "lockerState",
            "maintenance"  # Dùng style mylocker để thành vàng
        )
        
        self.refresh_style()
    # =========================
    # REFRESH STYLE
    # =========================

    # =========================
    # MAINTENANCE SELECTED
    # =========================
    def set_selected_maintenance(self):
        """
        Trạng thái bảo trì được chọn - màu cam đậm
        """
        self.setEnabled(True)
        
        self.setProperty(
            "lockerState",
            "maintenance_selected"
        )
        
        self.refresh_style()


        
    def refresh_style(self):

        self.style().unpolish(self)
        self.style().polish(self)

        self.update()



    # =========================
    # VẼ BADGE ICON GÓC TRÊN-PHẢI
    # =========================
    def paintEvent(self, event):
        super().paintEvent(event)

        state = self.property("lockerState")
        icon_char, color = self.BADGE_ICON.get(state, (None, None))
        if not icon_char:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        badge_size = min(self.width(), self.height()) * 0.30
        margin = 5
        rect = QRectF(
            self.width() - badge_size - margin,
            margin,
            badge_size,
            badge_size,
        )

        # Nền tròn trắng cho badge
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor(color), 1.5))
        painter.drawEllipse(rect)

        # Icon chữ/emoji bên trong
        painter.setPen(QColor(color))
        font = QFont()
        font.setPointSize(max(6, int(badge_size * 0.5)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, icon_char)

        painter.end()


