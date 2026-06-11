from PyQt6.QtWidgets import QMainWindow, QMessageBox
from app.paths import UI, GIF, QSS, find_video
from PyQt6 import uic

from app.utils.session import Session
from app.services.locker_service import LockerService
from app.services.auth_service import AuthService
from app.widgets.locker_button import LockerButton
from datetime import datetime
from PyQt6.QtCore import QTimer
class SelectLockerController(QMainWindow):

    def __init__(self, stacked_widget, loading_page, success_page):

        super().__init__()

        uic.loadUi(UI("SELECT_LOCKER.ui"), self)

        self.loading_page = loading_page
        self.success_page = success_page
        self.stacked_widget = stacked_widget
        self.locker_service = LockerService()
        self.auth_service = AuthService()

        Session.selected_locker = None
        self.locker_buttons = []

        self.load_style()
        self.setup_locker_buttons()

        # self.load_locker_status()

        self.back_mode.clicked.connect(self.go_to_begin)
        self.chon_tu.clicked.connect(self.confirm_action)

    # ================= STYLE =================
    def load_style(self):
        with open(QSS("locker.qss"), "r") as file:
            self.setStyleSheet(file.read())

    # ================= SETUP BUTTONS =================
    def setup_locker_buttons(self):

        for i in range(1, 10):

            old_btn = getattr(self, f"tu{i}")

            new_btn = LockerButton(i)
            # new_btn.locker_id = i

            new_btn.setParent(old_btn.parent())
            new_btn.setGeometry(old_btn.geometry())
            new_btn.setFont(old_btn.font())
            # new_btn.setText(old_btn.text())
            new_btn.show()

            old_btn.deleteLater()

            setattr(self, f"tu{i}", new_btn)
            self.locker_buttons.append(new_btn)

            new_btn.clicked.connect(
                lambda _, btn=new_btn:
                self.highlight_locker(
                    btn.locker_id,
                    btn
                )
            )

    # ================= LOAD STATUS =================
    def load_locker_status(self):

        lockers = (
            self.locker_service.get_all_lockers()
        )

        current_user = Session.current_user

        for locker_id, status, holder in lockers:

            try:
                # Cắt chữ 'L' ở đầu và ép kiểu về int (Ví dụ: "L01" -> "01" -> 1)
                ui_index = int(locker_id[1:]) 
            except (ValueError, IndexError):
                continue

            button = getattr(
                self,
                f"tu{ui_index}",
                None
            )

            if button is None:
                continue

            # ĐỪNG cập nhật lại trạng thái DB lên nút đang được người dùng "Click chọn" tạm thời
            if Session.selected_locker == locker_id:
                continue


            # Tủ trống
            if status == "empty":

                button.set_available()
                
            elif status == "maintenance":
                button.set_maintenance()
            # Tủ của mình
            elif holder == current_user:

                button.set_my_locker()

            # Tủ người khác
            else:

                button.set_busy()

    # ================= SHOW EVENT =================
    def showEvent(self, event):

        self.reset_form()  # Xóa dữ liệu rác cũ trước khi load màn hình
        self.load_locker_status()

        super().showEvent(event)


    # ================= CLICK SELECT =================
    def highlight_locker(self, locker_id, button_obj):

        if not button_obj.isEnabled():

            self.thong_bao_tu.setText(
                "Tủ này đang được sử dụng"
            )

            return

        Session.selected_locker = None
        self.load_locker_status()
 

        # =========================
        # SELECTED STATE
        # =========================
        # 2. Đặt tủ vừa bấm thành trạng thái Selected
        Session.selected_locker = locker_id  # Lưu chuỗi "L01" vào Session
        button_obj.set_selected()

        # Session.selected_locker = locker_id

        self.thong_bao_tu.setText(f"Đã chọn tủ {locker_id}")
        self.thong_bao_tu.setStyleSheet("color: #00796B;")
    # ================= CONFIRM ACTION =================
    def confirm_action(self):

        # =========================
        # CHECK INPUT
        # =========================
        if not Session.selected_locker:
            self.thong_bao_tu.setText("Vui lòng chọn tủ")
            return

        user = Session.current_user
        locker_id = Session.selected_locker
        name = self.auth_service.get_name_user(user)

        print("===== CONFIRM =====")
        print("USER:", user)
        print("LOCKER:", locker_id)
        print("NAME:", name)
        
        # success = self.locker_service.set_status_locker( user, locker_id)
        self.locker_service.set_status_locker( user, locker_id, name)

        self.loading_page.set_message(
            "Tiến hành mở tủ..."
        )

        self.stacked_widget.setCurrentWidget(
            self.loading_page
        )

        # ===== SAU 1 GIÂY =====

        QTimer.singleShot(2000,lambda: self.show_success(
            "Mở tủ thành công!!!",
            self.go_to_begin
            )
        )
        
     
     

    def show_success(
        self,
        message,
        next_function,
        delay= 2000
    ):

        self.success_page.set_message(
            message
        )

        self.stacked_widget.setCurrentWidget(
            self.success_page
        )

        QTimer.singleShot(
            delay,
            next_function
        )



    # ================= NAV =================
    def go_to_begin(self):
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def go_to_mode(self):
        self.stacked_widget.setCurrentIndex(3)

    def reset_form(self):
        Session.selected_locker = None
        self.thong_bao_tu.clear() # Xóa dòng thông báo