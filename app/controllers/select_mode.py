from PyQt6.QtWidgets import QMainWindow
from app.paths import UI, GIF, QSS, find_video
from PyQt6 import uic

from app.utils.session import Session
from app.services.auth_service import AuthService
from app.services.locker_service import LockerService
from app.widgets.virtual_keyboard import VirtualKeyboard
from PyQt6.QtCore import QTimer, QEvent, Qt


class SelectModeController(QMainWindow):

    def __init__(self, stacked_widget, loading_page, success_page):
        super().__init__()
        uic.loadUi(UI("SELECT_MODE.ui"), self)
        self.stacked_widget = stacked_widget
        self.loading_page   = loading_page
        self.success_page   = success_page
        self.locker_service = LockerService()
        self.auth_service   = AuthService()

        self.lay_do.clicked.connect(self.MO_TU)
        self.tra_tu.clicked.connect(self.TRA_TU)

    # ── ESC → về màn hình chính (thay cho nút Home hiển thị — kiosk công khai
    #    không nên có nút thoát rõ ràng, ESC chỉ dành cho người biết bấm) ──────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.go_to_begin()
        else:
            super().keyPressEvent(event)

    # ── Mỗi lần màn hình được hiển thị → check trạng thái tủ ────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._update_buttons()

    def _update_buttons(self):
        """
        Chưa có tủ → chuyển thẳng sang màn chọn tủ (SelectLocker).
        Đã có tủ   → ở lại, hiện Mở tủ + Trả tủ bình thường.
        """
        user       = Session.current_user
        has_locker = bool(self.locker_service.check_user_has_locker(user))

        if not has_locker:
            # Chưa mượn tủ nào → vào chọn tủ luôn
            self.thong_bao_tu.setText("")
            QTimer.singleShot(0, self.go_to_select_locker)
        else:
            # Đã có tủ → hiện menu Mở/Trả
            self.thong_bao_tu.setText("")

    # ── Mở tủ (user đã có tủ) ────────────────────────────────────────────────

    def MO_TU(self):
        user    = Session.current_user
        name    = self.auth_service.get_name_user(user)
        success, message = self.locker_service.open_locker(user, name)

        if not success:
            self.thong_bao_tu.setStyleSheet("color: red;")
            self.thong_bao_tu.setText(message)
        else:
            self.loading_page.set_message("Đang tiến hành mở tủ...")
            self.stacked_widget.setCurrentWidget(self.loading_page)
            QTimer.singleShot(2000, lambda: self.show_success(
                "Mở tủ thành công", self.go_to_begin
            ))

    # ── Trả tủ ───────────────────────────────────────────────────────────────

    def TRA_TU(self):
        user    = Session.current_user
        name    = self.auth_service.get_name_user(user)
        success, message = self.locker_service.return_locker(user, name)

        if not success:
            self.thong_bao_tu.setStyleSheet("color: red;")
            self.thong_bao_tu.setText(message)
        else:
            self.loading_page.set_message("Đang tiến hành trả tủ...")
            self.stacked_widget.setCurrentWidget(self.loading_page)
            QTimer.singleShot(2000, lambda: self.show_success(
                "Trả tủ thành công", self.go_to_begin_TRATU
            ))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def show_success(self, message, next_function, delay=2000):
        self.success_page.set_message(message)
        self.stacked_widget.setCurrentWidget(self.success_page)
        QTimer.singleShot(delay, next_function)

    def go_to_begin_TRATU(self):
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def go_to_begin(self):
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def go_to_select_locker(self):
        self.stacked_widget.setCurrentIndex(4)
        self.reset_form()

    def reset_form(self):
        self.thong_bao_tu.setText("")
