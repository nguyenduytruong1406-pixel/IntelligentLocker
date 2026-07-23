from PyQt6.QtWidgets import QMainWindow
from PyQt6 import uic
from PyQt6.QtCore import QTimer

from app.utils.session import Session
from app.services.auth_service import AuthService
from app.services.locker_service import LockerService
from app.controllers.send_otp_worker import SendOtpWorker
from PyQt6.QtGui import QPixmap, QIcon, QAction
from PyQt6.QtCore import QTimer, QEvent, Qt, QSize
from datetime import datetime, timedelta
from app.nav import PAGES

# ✅ FIX 1: Đổi tên class cho đúng chức năng (EnterEmail → EnterOtp)
class EnterOtpController(QMainWindow):

    def __init__(self, stacked_widget):

        super().__init__()

        uic.loadUi("app/ui/ENTER_OTP.ui",self)

        self.gridLayout_2.setColumnStretch(0, 1)
        self.gridLayout_2.setColumnStretch(1, 1)
        self.gridLayout_2.setColumnStretch(2, 1)

        self.verticalLayout_2.setContentsMargins(40, 20, 40, 20)  # trái, trên, phải, dưới
        
        self.stacked_widget = stacked_widget
        self.auth_service = AuthService()
        self.locker_service = LockerService()

        # ============================
        # Khởi tạo timer đếm ngược
        # ============================
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(
            self.update_countdown
        )

        # ============================
        # Worker gửi OTP
        # ============================
        self.worker = None

        # ============================
        # Kết nối sự kiện nút SEND
        # ============================
        self.send_email.clicked.connect(self.send_otp)

        # ============================
        # Kết nối bàn phím số
        # ============================
        self.pin = ""

        self.b1.clicked.connect(lambda: self.add_number("1"))
        self.b2.clicked.connect(lambda: self.add_number("2"))
        self.b3.clicked.connect(lambda: self.add_number("3"))
        self.b4.clicked.connect(lambda: self.add_number("4"))
        self.b5.clicked.connect(lambda: self.add_number("5"))
        self.b6.clicked.connect(lambda: self.add_number("6"))
        self.b7.clicked.connect(lambda: self.add_number("7"))
        self.b8.clicked.connect(lambda: self.add_number("8"))
        self.b9.clicked.connect(lambda: self.add_number("9"))
        self.b0.clicked.connect(lambda: self.add_number("0"))

        self.clear_b.clicked.connect(self.clear_pin)
        self.enter_b.clicked.connect(self.check_otp)


        self.clock_icon.setPixmap(
            QPixmap("app/assets/icon/clock.png").scaled(
                80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )

        # ============================
        # Hiệu ứng nhấn nút
        # ============================
        all_buttons = [
            self.b0, self.b1, self.b2, self.b3, self.b4,
            self.b5, self.b6, self.b7, self.b8, self.b9,
            self.clear_b, self.enter_b, self.send_email
        ]

        for btn in all_buttons:
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

    # ============================
    # Xóa mã PIN
    # ============================
    # ✅ FIX 6: Đổi tên clear_def → clear_pin cho rõ nghĩa
    def clear_pin(self):
        self.pin = ""
        self.update_label()

    # ============================
    # Thêm số vào PIN
    # ============================
    def add_number(self, number):
        if len(self.pin) < 4:
            self.pin += number
            self.update_label()



    # ============================
    # Cập nhật hiển thị các ô PIN
    # ============================
    # ✅ FIX 6: Sửa typo update_lable → update_label
    def update_label(self):
        labels = [self.l1, self.l2, self.l3, self.l4]
        for i in range(4):
            if i < len(self.pin):
                labels[i].setText(self.pin[i])   # hiện đúng số đã nhập, thay vì "*"
                labels[i].setProperty("pinState", "filled")
            else:
                labels[i].setText("-")
                labels[i].setProperty("pinState", "empty")

            labels[i].style().unpolish(labels[i])
            labels[i].style().polish(labels[i])

    # ============================
    # Kiểm tra OTP
    # ============================
    def check_otp(self):
        otp_input = self.pin

        success, message = self.auth_service.verify_otp(otp_input)

        if success:
            self.thong_bao_otp.setStyleSheet("color: green;")
            self.thong_bao_otp.setText(message)
            QTimer.singleShot(1000, self.enterotp_success)
        else:
            self.thong_bao_otp.setStyleSheet("color: red;")
            self.thong_bao_otp.setText(message)

    # ============================
    # Xử lý sau khi OTP đúng
    # ============================
    def enterotp_success(self):

        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(PAGES["select_mode"]))   # Trang OPEN / RETURN



    # ===========================================================================
    #                              PHẦN GỬI OTP
    # ===========================================================================

    def send_otp(self):
        user = Session.current_user
        email = self.auth_service.get_email_user(user)

        if not email:
            self.thong_bao_email.setStyleSheet("color: red;")
            self.thong_bao_email.setText("Không tìm thấy email!")
            return

        # Hiện trạng thái đang gửi
        self.thong_bao_email.setStyleSheet("color: blue;")
        self.thong_bao_email.setText("Đang gửi OTP...")

        # ✅ Khóa nút SEND ngay khi bấm để tránh spam
        self.send_email.setEnabled(False)

        # Tạo worker gửi OTP bất đồng bộ
        self.worker = SendOtpWorker(self.auth_service, email)
        self.worker.finished.connect(self.on_send_finished)
        self.worker.start()

    def on_send_finished(self, success, message):
        if success:
            self.thong_bao_email.setStyleSheet("color: green;")
            self.thong_bao_email.setText(message)

            # Bắt đầu đếm ngược 60 giây
            Session.otp_expire_time = (
                datetime.now() + timedelta(seconds=60)
            )
            self.start_countdown()

            # ✅ FIX 2: KHÔNG mở lại nút SEND ở đây
            # Nút sẽ được mở lại sau khi hết 60 giây (trong update_countdown)

        else:
            self.thong_bao_email.setStyleSheet("color: red;")
            self.thong_bao_email.setText(message)

            # ✅ Nếu gửi thất bại → mở lại nút SEND để thử lại
            self.send_email.setEnabled(True)


    # ===========================================================================
    #                           ĐẾM NGƯỢC THỜI GIAN
    # ===========================================================================

    def start_countdown(self):
        if not Session.otp_expire_time:
            return
        self.countdown_timer.start(1000)
        self.update_countdown()

    def update_countdown(self):
        if not Session.otp_expire_time:
            self.countdown_timer.stop()
            self.time_label_otp.setText("00:00")
            self.send_email.setEnabled(True)
            return

        remaining = int((Session.otp_expire_time - datetime.now()).total_seconds())

        if remaining <= 0:
            self.countdown_timer.stop()
            self.time_label_otp.setText("00:00")
            self.send_email.setEnabled(True)
            return

        self.send_email.setEnabled(False)

        minutes = remaining // 60
        seconds = remaining % 60
        self.time_label_otp.setText(f"{minutes:02d}:{seconds:02d}")   # ← định dạng 00:28

        if remaining <= 10:
            self.time_label_otp.setStyleSheet("color: #DC2626; font-size: 35px; font-weight: 700;")
        else:
            self.time_label_otp.setStyleSheet("color: #D4AF37; font-size: 35px; font-weight: 700;")


    # ===========================================================================
    #                           SHOW / HIDE EVENTS
    # ===========================================================================

    def showEvent(self, event):
        # ✅ Reset giao diện mỗi lần vào màn hình
        self.pin = ""
        self.thong_bao_otp.setText("")
        # ✅ FIX 4: Thêm reset thong_bao_email
        self.thong_bao_email.setText("")
        # self.time_label.setText("")          # ← xóa trắng trước
        self.update_label()

        # Nếu vẫn còn OTP đang đếm thì tiếp tục hiển thị
        if Session.otp_expire_time:
            remaining = int(
                (Session.otp_expire_time - datetime.now()).total_seconds()
            )
            if remaining > 0:
                self.start_countdown()
            else:
                # delay nhỏ để trang render xong mới hiện chữ
                
                    self.time_label_otp.setText("OTP đã hết hạn"),
                    self.send_email.setEnabled(True)
                
        else:
            
                self.time_label_otp.setText("Chưa có OTP")
                self.send_email.setEnabled(True)
            

        super().showEvent(event)

    # ✅ FIX 5: Thêm hideEvent để dừng timer khi rời màn hình
    def hideEvent(self, event):
        self.countdown_timer.stop()
        super().hideEvent(event)