from PyQt6.QtWidgets import QMainWindow
from app.paths import UI, GIF, QSS, find_video
from PyQt6 import uic

from app.utils.session import Session
from app.services.auth_service import AuthService
from app.services.locker_service import LockerService
from app.widgets.virtual_keyboard import VirtualKeyboard
from PyQt6.QtCore import QTimer, QEvent, Qt


class LoginController(QMainWindow):

    def __init__(self,stacked_widget):

        super().__init__()

        uic.loadUi(UI("LOGIN.ui"), self)
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
        self.keyboard.hide()

        ########### EVENT ############
        self.mssv.installEventFilter(self)
        self.back_login.clicked.connect(self.go_to_begin)
        self.next_login.clicked.connect(self.login_account)


# # 👉 THÊM: Load file QSS riêng cho màn hình này (nếu file main.py chưa load)
#         try:
#             with open(QSS("keyboard.qss"), "r", encoding="utf-8") as file:
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

        success, message = (
            self.auth_service.login(user)
        )

        if success:

            Session.current_user = user

            self.thong_bao.setStyleSheet(
                "color: green;"
            )

            self.thong_bao.setText(message)
            QTimer.singleShot(1000, self.go_to_auth_method)


        else:

            self.thong_bao.setStyleSheet(
                "color: red;"
            )

            self.thong_bao.setText(message)

    def go_to_auth_method(self):
        self.stacked_widget.setCurrentIndex(8)
        self.reset_form()

    def go_to_begin(self):
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def reset_form(self):
        self.mssv.clear()
        self.thong_bao.setText("")


    def eventFilter(self, source, event):

        if (
            source == self.mssv
            and event.type() == QEvent.Type.MouseButtonPress
        ):

            self.keyboard.show()
            self.keyboard.set_target(self.mssv)
            self.keyboard.mode = "NUM"
            self.keyboard.build_keyboard()

        return super().eventFilter(source,event)
    
