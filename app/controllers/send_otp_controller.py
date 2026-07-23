from PyQt6.QtWidgets import QMainWindow
from PyQt6 import uic
from PyQt6.QtCore import QTimer, QEvent, Qt, QSize
from PyQt6.QtGui import QIcon

from app.utils.session import Session
from app.services.auth_service import AuthService
from app.controllers.send_otp_worker import SendOtpWorker
from app.widgets.virtual_keyboard import VirtualKeyboard
from PyQt6.QtGui import QPixmap, QIcon, QAction
from app.nav import PAGES
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


class SendEmailController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()

        uic.loadUi("app/ui/SEND_OTP.ui", self)
        self.stacked_widget = stacked_widget
        self.auth_service = AuthService()
        self.worker = None

        ########### SETUP BÀN PHÍM ###########
        self.keyboard = VirtualKeyboard()
        self.keyboard_container.layout().addWidget(
            self.keyboard,
            alignment=Qt.AlignmentFlag.AlignTop
        )

        ########### SETUP BUTTON ###########
        send_otp_buttons = [self.semail_b, self.back_auth_b]
        for btn in send_otp_buttons:
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            btn.setProperty("class", "BackButton_SEND_OTP")

            def create_release_handler(b=btn):
                def safe_clear():
                    try:
                        if b and not b.isHidden():
                            b.setChecked(False)
                    except RuntimeError:
                        pass
                QTimer.singleShot(150, safe_clear)

            self.semail_b.released.connect(create_release_handler)

        ########### ICON ###########
        self.back_auth_b.setIcon(QIcon(str(BASE_DIR / "assets/icon/back.png")))
        self.back_auth_b.setIconSize(QSize(20, 20))

        ########### EVENT ###########
        self.email_user.installEventFilter(self)
        self.semail_b.clicked.connect(self.send_otp)
        self.back_auth_b.clicked.connect(self.back_auth_method)

        # ===== Icon cho ô nhập =====
        self._setup_input_icons()



    def _setup_input_icons(self):
        # Scale icon trước khi thêm vào
        pixmap = QPixmap("app/assets/icon/email.png").scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        user_action = QAction(QIcon(pixmap), "", self.email_user)
        self.email_user.addAction(user_action,self.email_user.ActionPosition.LeadingPosition)

    # =========================
    # BACK
    # ========================= 

    def back_auth_method(self):
        self.stacked_widget.setCurrentIndex(PAGES["auth_method"])
        self.reset_form()
    # =========================
    # SEND OTP
    # =========================
    def send_otp(self):
        # ✅ Lấy email từ ô nhập liệu
        email = self.email_user.text().strip()

        if not email:
            self.thong_bao_email.setStyleSheet("color: red;")
            self.thong_bao_email.setText("Vui lòng nhập email!")
            return

        # Kiểm tra định dạng email cơ bản
        if "@" not in email or "." not in email:
            self.thong_bao_email.setStyleSheet("color: red;")
            self.thong_bao_email.setText("Email không hợp lệ!")
            return

        self.thong_bao_email.setStyleSheet("color: blue;")
        self.thong_bao_email.setText("Đang gửi OTP...")
        self.semail_b.setEnabled(False)

        self.worker = SendOtpWorker(self.auth_service, email)
        self.worker.finished.connect(self.on_send_finished)
        self.worker.start()

    # =========================
    # KẾT QUẢ GỬI MAIL
    # =========================
    def on_send_finished(self, success, message):
        self.semail_b.setEnabled(True)

        if success:
            self.thong_bao_email.setStyleSheet("color: green;")
            self.thong_bao_email.setText(message)
            QTimer.singleShot(1000, self.go_to_enter_otp)
        else:
            self.thong_bao_email.setStyleSheet("color: red;")
            self.thong_bao_email.setText(message)

    # =========================
    # CHUYỂN TRANG OTP
    # =========================
    def go_to_enter_otp(self):
        QTimer.singleShot(150, lambda: (
            self.reset_form(),
            self.stacked_widget.setCurrentIndex(PAGES["Enter_OTP"])
        ))

    # =========================
    # SHOW EVENT
    # =========================
    def showEvent(self, event):
        
        self.load_email()
        super().showEvent(event)

    # =========================
    # LOAD EMAIL MẶC ĐỊNH
    # =========================
    def load_email(self):
        user = Session.current_user
        email = self.auth_service.get_email_user(user)
        self.email_user.setText(email if email else "")
        self.email_user.setPlaceholderText("Nhập email để nhận OTP")

    # =========================
    # RESET
    # =========================
    def reset_form(self):
        self.thong_bao_email.clear()

    # =========================
    # EVENT FILTER
    # =========================
    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if source == self.email_user:
                self.keyboard.set_target(self.email_user)
                self.keyboard.mode = "ABC"
                self.keyboard.build_keyboard()
                self.keyboard.confirm_button = self.semail_b
                # Delay nhỏ để Qt xử lý click xong rồi mới setFocus
                # QTimer.singleShot(50, self.email_user.setFocus)

        return super().eventFilter(source, event)
    
