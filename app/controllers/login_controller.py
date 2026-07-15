from PyQt6.QtWidgets import QMainWindow
from PyQt6 import uic

from app.utils.session import Session
from app.services.auth_service import AuthService
from app.services.locker_service import LockerService
from app.widgets.virtual_keyboard import VirtualKeyboard
from PyQt6.QtCore import QTimer, QEvent, Qt
from app.nav import PAGES


class LoginController(QMainWindow):

    def __init__(self,stacked_widget):

        super().__init__()

        uic.loadUi("app/ui/LOGIN_08_07.ui", self)
        self.stacked_widget = stacked_widget

        self.auth_service = AuthService()
        self.locker_service = LockerService()

        ########### SETUP BÀN PHÍM ###########
        self.keyboard = VirtualKeyboard()
        # self.keyboard_container.layout().addWidget(self.keyboard,alignment=Qt.AlignmentFlag.AlignCenter)
        self.keyboard_container.layout().addWidget(
            self.keyboard,
            alignment=Qt.AlignmentFlag.AlignTop
        )
        
        ########### EVENT ############
        self.mssv.installEventFilter(self)
        self.mat_khau.installEventFilter(self)
        self.back_login.clicked.connect(self.go_to_begin)
        self.next_login.clicked.connect(self.login_account)


# # 👉 THÊM: Load file QSS riêng cho màn hình này (nếu file main.py chưa load)
#         try:
#             with open("app/assets/styles/keyboard.qss", "r", encoding="utf-8") as file:
#                 self.setStyleSheet(file.read())
#         except FileNotFoundError:
#             print("Lưu ý: Không tìm thấy file QSS tại đường dẫn quy định!")


        # 1. Gom danh sách các nút bằng tên biến logic riêng biệt (Không lo bị trùng)
        system_buttons = [self.back_login, self.next_login]
        for btn in system_buttons:
            # Bật tính năng lưu trạng thái cảm ứng
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            
            # 👉 MẸO QUAN TRỌNG: Gán class "systemButton" để nút tự động ăn theo file QSS
            btn.setProperty("class", "systemButton")
            
            # Ép Qt vẽ lại giao diện để nhận thuộc tính class vừa gán
            # btn.style().unpolish(btn)
            # btn.style().polish(btn)
            
            # 2. Cài đặt QTimer giữ màu 120ms chống trơ trên màn Waveshare
            def create_release_handler(b=btn):
                def safe_clear():
                    try:
                        # Nếu nút bấm vẫn còn sống và chưa bị xóa
                        if b and not b.isHidden(): 
                            b.setChecked(False)
                    except RuntimeError:
                        # Nếu nút đã bị xóa bởi build_keyboard(), bỏ qua lỗi này an toàn
                        pass

                # Giữ màu trong 120ms rồi chạy hàm kiểm tra an toàn ở trên
                QTimer.singleShot(150, safe_clear)

            btn.released.connect(create_release_handler)
  
        #     # =======================================================
            # =======================================================
            # =======================================================



    def login_account(self):

        user = self.mssv.text()
        pw = self.mat_khau.text()

        if not user.isdigit():
            self.thong_bao.setStyleSheet("color: red;")
            self.thong_bao.setText("MSSV chỉ được chứa số!")
            return
        

        success, message = (
            self.auth_service.mssv_pass( user, pw)
        )

        if success:

            Session.current_user = user

            self.thong_bao.setStyleSheet(
                "color: green;"
            )

            self.thong_bao.setText(message)
            QTimer.singleShot(1000, self.after_enterotp_success)


        else:

            self.thong_bao.setStyleSheet(
                "color: red;"
            )

            self.thong_bao.setText(message)


    # ============================
    # Xử lý sau khi Đăng nhập đúng
    # ============================
    def after_enterotp_success(self):

        user = self.auth_service.get_user(Session.current_user)

        if user['is_first_login'] == 1:
            # Mật khẩu random do admin cấp — bắt đổi mật khẩu trước, CHƯA kiểm tra
            # tủ ở bước này (return ngay, không cho nhánh check-locker bên dưới
            # chạy song song và ghi đè lên màn đổi mật khẩu).
            QTimer.singleShot(150, lambda: self.go_to_changepass())
            return

        locker = self.locker_service.check_user_has_locker(
            Session.current_user
        )

        if locker:
            # Đã có tủ được quản lý cấp sẵn → qua màn thao tác với tủ (mở/trả)
            QTimer.singleShot(150, lambda: self.open_camera_page())
        else:
            # Luồng "tự chọn tủ" đã bị bỏ — quản lý cấp tài khoản/mật khẩu/tủ
            # ngay khi duyệt đơn đăng ký, nên nếu đăng nhập được mà chưa có tủ
            # nghĩa là đơn CHƯA được duyệt xong hoặc có lỗi cấp phát.
            # Hiện thông báo thay vì chuyển tới luồng gán tủ không còn tồn tại.
            self.thong_bao.setStyleSheet("color: red;")
            self.thong_bao.setText(
                "Tài khoản chưa được cấp tủ. Vui lòng liên hệ quản lý!"
            )

    def go_to_changepass(self):
        # NOTE: hiện chưa có nút nào trong LOGIN_08_07.ui gọi hàm này —
        # nếu có nút "Đổi mật khẩu" / "Quên mật khẩu" trên UI, nối vào đây.
        self.stacked_widget.setCurrentIndex(PAGES["change_pass"])
        self.reset_form()

    def open_camera_page(self):
        self.reset_form()
        self.stacked_widget.setCurrentIndex(PAGES["next_cam"])

    def go_to_begin(self):
        self.stacked_widget.setCurrentIndex(PAGES["begin"])
        self.reset_form()

    def reset_form(self):
        self.mssv.clear()
        self.mat_khau.clear()
        self.thong_bao.setText("")



    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonPress:

            # ===== MSSV =====
            if source == self.mssv:
                self.keyboard.set_target(self.mssv)
                self.keyboard.mode = "NUM"
                self.keyboard.build_keyboard()
                self.keyboard.confirm_button = None

            # ===== MẬT KHẨU =====
            elif source == self.mat_khau:
                self.keyboard.set_target(self.mat_khau)
                self.keyboard.mode = "NUM"
                self.keyboard.build_keyboard()
                self.keyboard.confirm_button = self.next_login

        return super().eventFilter(source, event)

    def showEvent(self, event):
        # Hiện bàn phím ngay khi vào màn hình login
        self.keyboard.show()
        self.keyboard.set_target(self.mssv)
        self.keyboard.mode = "NUM"
        self.keyboard.build_keyboard()
        self.keyboard.confirm_button = None
        super().showEvent(event)
    
    # def hideEvent(self, event):
    #     self.keyboard.hide()
    #     self.keyboard.confirm_button = None  # ← Reset
    #     super().hideEvent(event)