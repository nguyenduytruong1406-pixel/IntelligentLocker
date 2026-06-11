from PyQt6.QtWidgets import QMainWindow
from app.paths import UI, GIF, QSS, find_video
from PyQt6 import uic
from PyQt6.QtCore import QTimer

from app.utils.session import Session
from app.services.auth_service import AuthService
from app.controllers.send_otp_worker import SendOtpWorker


class SendEmailController(QMainWindow):

    def __init__(self, stacked_widget):

        super().__init__()

        uic.loadUi(UI("SEND_OTP.ui"),
            self
        )

        self.stacked_widget = stacked_widget
        self.auth_service = AuthService()

        self.worker = None

        # EVENT
        self.semail_b.clicked.connect(
            self.send_otp
        )

    # =========================
    # SEND OTP
    # =========================
    def send_otp(self):

        user = Session.current_user

        email = (
            self.auth_service
            .get_email_user(user)
        )

        if not email:

            self.thong_bao_email.setStyleSheet(
                "color: red;"
            )

            self.thong_bao_email.setText(
                "Không tìm thấy email!"
            )

            return

        # Hiện trạng thái đang gửi
        self.thong_bao_email.setStyleSheet(
            "color: blue;"
        )

        self.thong_bao_email.setText(
            "Đang gửi OTP..."
        )

        # khóa nút tránh spam
        self.semail_b.setEnabled(False)

        # tạo worker
        self.worker = SendOtpWorker(
            self.auth_service,
            email
        )

        self.worker.finished.connect(
            self.on_send_finished
        )

        self.worker.start()

    # =========================
    # KẾT QUẢ GỬI MAIL
    # =========================
    def on_send_finished(
        self,
        success,
        message
    ):

        self.semail_b.setEnabled(True)

        if success:

            self.thong_bao_email.setStyleSheet(
                "color: green;"
            )

            self.thong_bao_email.setText(
                message
            )

            QTimer.singleShot(
                1000,
                self.go_to_enter_otp
            )

        else:

            self.thong_bao_email.setStyleSheet(
                "color: red;"
            )

            self.thong_bao_email.setText(
                message
            )

    # =========================
    # CHUYỂN TRANG OTP
    # =========================
    def go_to_enter_otp(self):

        self.stacked_widget.setCurrentIndex(
            12
        )

        self.reset_form()

    # =========================
    # LOAD EMAIL
    # =========================
    def showEvent(self, event):

        self.load_email()

        super().showEvent(event)

    def load_email(self):

        user = Session.current_user

        email = (
            self.auth_service
            .get_email_user(user)
        )

        self.email_user.setText(
            email if email else ""
        )

    # =========================
    # RESET
    # =========================
    def reset_form(self):

        self.thong_bao_email.clear()