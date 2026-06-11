"""
app/controllers/auth_method_controller.py
"""

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtCore import QTimer

from app.utils.session import Session
from app.services.locker_service import LockerService
from app.database.user_repository import UserRepository


# Index trong QStackedWidget
IDX_PASSWORD    = 9
IDX_FACE_AUTH   = 15   # FaceController mode="auth"
IDX_FACE_REG    = 15   # FaceController mode="register" (cùng widget, đổi mode)
IDX_AUTH_METHOD = 8


class AuthMethodController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()
        uic.loadUi("app/ui/AUTH_METHOD.ui", self)
        self.stacked_widget = stacked_widget
        self.locker_service = LockerService()
        self.user_repo      = UserRepository()

        for btn in [self.pass_select, self.recog_select]:
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

        self.pass_select.clicked.connect(self.go_to_password)
        self.recog_select.clicked.connect(self.go_to_face)

    def go_to_password(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(IDX_PASSWORD))

    def go_to_face(self):
        """
        Kiểm tra has_face của sinh viên hiện tại:
          • Đã có khuôn mặt → FaceController mode="auth"  (xác thực)
          • Chưa có          → FaceController mode="register" (đăng ký mới)
        """
        mssv = Session.current_user
        if not mssv:
            QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(IDX_FACE_AUTH))
            return

        user      = self.user_repo.find_user(mssv)
        has_face = bool(user and user["has_face"])

        face_page = self.stacked_widget.widget(IDX_FACE_AUTH)

        if has_face:
            # ── Xác thực khuôn mặt ──────────────────────────────────────────
            if face_page and hasattr(face_page, "set_mode"):
                face_page.set_mode("auth")
            QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(IDX_FACE_AUTH))
        else:
            # ── Chưa có khuôn mặt → chuyển sang đăng ký ────────────────────
            if face_page and hasattr(face_page, "set_mode"):
                face_page.set_mode("register")
            QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(IDX_FACE_REG))