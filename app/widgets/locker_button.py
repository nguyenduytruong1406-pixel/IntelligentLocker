from PyQt6.QtWidgets import QPushButton


class LockerButton(QPushButton):

    def __init__(
        self,
        locker_id
    ):

        super().__init__()

        self.locker_id = f"L{locker_id:02d}"

        self.setText(f"TỦ {locker_id:02d}")

        self.setProperty(
            "lockerState",
            "available"
        )

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
            "mylocker"  # Dùng style mylocker để thành vàng
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



