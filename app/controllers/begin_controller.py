from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QLabel, QVBoxLayout, QDialog, QPushButton
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QTimer, QTime, QDate
from app.services.locker_service import LockerService
from app.widgets.locker_button import LockerButton
from app.nav import PAGES
from pathlib import Path
from PyQt6.QtGui import QPixmap, QIcon, QAction
from PyQt6.QtCore import QSize


BASE_DIR = Path(__file__).parent.parent

class BeginController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()

        uic.loadUi("app/ui/START_N.ui", self)
        self.stacked_widget = stacked_widget
        self.locker_service = LockerService()
        self.locker_buttons = []

        ########### SETUP LOCKER BUTTONS ###########
        self.setup_locker_buttons()

        ########### SETUP BUTTON ###########
        for btn in [self.chua_dk, self.da_dk, self.ho_tro]:
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

        # Trong __init__ sau phần SETUP BUTTON
        self.chua_dk.setIcon(QIcon(str(BASE_DIR / "assets/icon/send.png")))
        self.chua_dk.setIconSize(QSize(40, 40))

        self.da_dk.setIcon(QIcon(str(BASE_DIR / "assets/icon/open.png")))
        self.da_dk.setIconSize(QSize(40, 40))

        self.ho_tro.setIcon(QIcon(str(BASE_DIR / "assets/icon/support.png")))
        self.ho_tro.setIconSize(QSize(40, 40))


        ########### ĐỒNG HỒ REAL-TIME ###########
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)  # Cập nhật mỗi 1 giây
        self.update_clock()  # Hiện ngay khi vào màn hình


        ########### EVENT ###########
        self.da_dk.clicked.connect(self.go_to_login)
        self.chua_dk.clicked.connect(self.go_to_reg)
        self.ho_tro.clicked.connect(self.go_to_service)

        ########### TIMER CẬP NHẬT TRẠNG THÁI TỦ ###########
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.load_locker_status)
        self.refresh_timer.start(5000)  # Cập nhật mỗi 5 giây

    # ================= SETUP BUTTONS =================
    def setup_locker_buttons(self):
        for i in range(1, 10):
            old_btn = getattr(self, f"tu{i}")
            new_btn = LockerButton(i)

            new_btn.setParent(old_btn.parent())
            new_btn.setGeometry(old_btn.geometry())
            new_btn.setFont(old_btn.font())
            new_btn.show()

            old_btn.deleteLater()

            setattr(self, f"tu{i}", new_btn)
            self.locker_buttons.append(new_btn)

            # ❌ Không cho click - chỉ xem
            new_btn.setEnabled(False)


    def update_clock(self):
        # ===== GIỜ =====
        time = QTime.currentTime()
        self.time_label.setText(time.toString("hh:mm AP"))

        # ===== NGÀY =====
        date = QDate.currentDate()
        
        # Chuyển thứ sang tiếng Việt
        days = {
            1: "T2", 2: "T3", 3: "T4",
            4: "T5", 5: "T6", 6: "T7", 7: "CN"
        }
        day_str = days[date.dayOfWeek()]
        
        self.date_label.setText(
            f"{day_str}, {date.toString('dd/MM/yyyy')}"
        )

    # ================= LOAD STATUS =================
    def load_locker_status(self):
        lockers = self.locker_service.get_all_lockers()

        for locker_id, status, holder in lockers:
            try:
                ui_index = int(locker_id[1:])
            except (ValueError, IndexError):
                continue

            button = getattr(self, f"tu{ui_index}", None)
            if button is None:
                continue

            if status == "empty":
                button.set_available()
            elif status == "maintenance":
                button.set_maintenance()
            else:
                button.set_busy()



    def go_to_service(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Hỗ Trợ")
        dialog.setFixedSize(350, 450)

        layout = QVBoxLayout(dialog)

        # ===== TIÊU ĐỀ =====
        title = QLabel("📞 LIÊN HỆ HỖ TRỢ")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00796B;")
        layout.addWidget(title)

        # ===== TIN NHẮN =====
        message = QLabel(
            "Nếu bạn cần hỗ trợ, vui lòng:\n\n"
            "📱 Quét mã QR bên dưới\n"
            "📧 Email: support@locker.com\n"
            "☎️ Hotline: 1900 xxxx"
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setStyleSheet("font-size: 14px;")
        layout.addWidget(message)

        # ===== MÃ QR =====
        qr_label = QLabel()
        qr_pixmap = QPixmap("app/assets/icon/Form_locker.png")
        qr_label.setPixmap(
            qr_pixmap.scaled(
                200, 200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(qr_label)

        # ===== NÚT ĐÓNG =====
        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("closeButton_sp")

        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)

        dialog.exec()

    # ================= SHOW EVENT =================
    def showEvent(self, event):
        self.load_locker_status()  # Load ngay khi vào màn hình
        super().showEvent(event)

    # ================= NAV =================
    def go_to_login(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(PAGES["login"]))

    def go_to_reg(self):
        # "Chưa đăng ký" → hiện màn QR code (quét mã điền Google Form,
        # quản lý duyệt và cấp tài khoản/mật khẩu/tủ sau).
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(PAGES["qr_code"]))

    # ✅ Thêm hideEvent
    def hideEvent(self, event):
        self.refresh_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        self.load_locker_status()
        self.refresh_timer.start(5000)  # Chạy lại khi vào màn hình

        img_path = BASE_DIR / "assets/icon/logo_ute.jpg"
        # print(">>> Đường dẫn ảnh:", img_path)
        # print(">>> File tồn tại:", img_path.exists())
        pixmap = QPixmap(str(img_path))

        if not pixmap.isNull():
            self.logo_ute.setPixmap(
                pixmap.scaled(
                    self.logo_ute.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
            self.logo_ute.setVisible(True)   # ép hiện, phòng trường hợp bị set False đâu đó
            self.logo_ute.raise_()           # đưa lên trên cùng, phòng bị widget khác đè lên

        super().showEvent(event)



