"""
app/controllers/auth_method_controller.py
"""

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtCore import QTimer

from app.utils.session import Session
from app.services.locker_service import LockerService
from app.database.user_repository import UserRepository
from app.nav import PAGES


class AuthMethodController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()
        uic.loadUi("app/ui/AUTH_METHOD.ui", self)
        self.stacked_widget = stacked_widget
        self.locker_service = LockerService()
        self.user_repo      = UserRepository()

        # NOTE: đã bỏ hẳn xác thực bằng mật khẩu ở kiosk (password_controller.py
        # đã bị loại khỏi luồng vì quản lý cấp tài khoản/mật khẩu/tủ sẵn ngay khi
        # duyệt đơn — không còn màn "chọn phương thức: mật khẩu" nữa).
        # Nếu file .ui AUTH_METHOD.ui vẫn còn nút self.pass_select, ẩn nó đi để
        # tránh người dùng bấm vào nút chết:
        if hasattr(self, "pass_select"):
            self.pass_select.hide()

        for btn in [self.recog_select]:
            btn.setCheckable(True)
            btn.setAutoExclusive(False)

            def create_release_handler(b=btn):
                def safe_clear():
                    try:
                        if b and not b.isHidden():
                            b.setChecked(False)
                    except RuntimeError:
                        pass
                QTimer.singleShot(150, safe_clear)

            btn.released.connect(create_release_handler)

        self.recog_select.clicked.connect(self.go_to_face)

    def go_to_face(self):
        """
        Kiểm tra has_face của sinh viên hiện tại:
          • Đã có khuôn mặt → FaceController mode="auth"  (xác thực)
          • Chưa có          → FaceController mode="register" (đăng ký mới)

        Chỉ có 1 FaceController instance (self.stacked_widget widget tại
        PAGES["face"]) — chuyển giữa 2 chế độ bằng set_mode(), KHÔNG dùng
        2 trang riêng biệt.
        """
        mssv = Session.current_user
        face_page = self.stacked_widget.widget(PAGES["face"])

        if not mssv:
            if face_page and hasattr(face_page, "set_mode"):
                face_page.set_mode("auth")
            QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(PAGES["face"]))
            return

        user     = self.user_repo.find_user(mssv)
        has_face = bool(user and user["has_face"])

        if face_page and hasattr(face_page, "set_mode"):
            face_page.set_mode("auth" if has_face else "register")

        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(PAGES["face"]))