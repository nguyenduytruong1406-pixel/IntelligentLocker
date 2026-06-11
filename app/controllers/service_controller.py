from PyQt6.QtWidgets import QMainWindow
from app.paths import UI, GIF, QSS, find_video
from PyQt6 import uic

from app.utils.ktv_config import load_ktv_settings, verify_ktv_pin
from app.widgets.virtual_keyboard import VirtualKeyboard
from PyQt6.QtCore import QTimer, QEvent, Qt


class ServiceController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()

        uic.loadUi(UI("SERVICE.ui"), self)
        self.stacked_widget = stacked_widget

        self.lineEdit.setEchoMode(self.lineEdit.EchoMode.Password)

        ########### SETUP BÀN PHÍM ###########
        self.keyboard = VirtualKeyboard()
        self.keyboard_container.layout().addWidget(
            self.keyboard,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        self.keyboard.hide()

        ########### EVENT ############
        self.lineEdit.installEventFilter(self)
        self.back.clicked.connect(self.go_to_begin)
        self.next.clicked.connect(self.verify_pin_and_continue)

    def verify_pin_and_continue(self):
        pin = self.lineEdit.text().strip()

        if not pin:
            self.show_message("Vui lòng nhập mã PIN", error=True)
            return

        success, message = verify_ktv_pin(pin)

        if success:
            settings = load_ktv_settings()
            next_index = settings["next_page_index"]
            # Lưu thông tin KTV vào Session
            from app.utils.session import Session
            Session.ktv_pin = pin
            Session.ktv_name = settings.get("ktv_name", "KTV")
            Session.ktv_id = settings.get("ktv_id", "KTV001")
            # ===================================
            self.show_message(message, error=False)
            QTimer.singleShot(
                500,
                lambda: self.go_to_next_page(next_index),
            )
        else:
            self.show_message(message, error=True)

    def go_to_next_page(self, page_index: int):
        self.stacked_widget.setCurrentIndex(page_index)
        self.reset_form()

    def go_to_begin(self):
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def show_message(self, text: str, error: bool):
        color = "red" if error else "green"
        self.thong_bao_pin.setStyleSheet(f"color: {color};")
        self.thong_bao_pin.setText(text)

    def reset_form(self):
        self.lineEdit.clear()
        self.thong_bao_pin.clear()
        self.keyboard.hide()

    def eventFilter(self, source, event):
        if (
            source == self.lineEdit
            and event.type() == QEvent.Type.MouseButtonPress
        ):
            self.keyboard.show()
            self.keyboard.set_target(self.lineEdit)
            self.keyboard.mode = "NUM"
            self.keyboard.build_keyboard()

        return super().eventFilter(source, event)
