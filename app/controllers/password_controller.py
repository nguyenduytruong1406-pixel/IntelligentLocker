from PyQt6.QtWidgets import QMainWindow
from app.paths import UI, GIF, QSS, find_video
from PyQt6 import uic

from app.utils.session import Session
from app.services.auth_service import AuthService
from app.widgets.virtual_keyboard import VirtualKeyboard
from app.services.locker_service import LockerService
from PyQt6.QtCore import QTimer, QEvent, Qt


class PassWordController(QMainWindow):

    def __init__(self,stacked_widget):

        super().__init__()

        uic.loadUi(UI("PASSWORD.ui"), self)
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


        ########### SETUP BUTTON ###########
        for btn in [self.back_auth_method, self.next_mode]:
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


        ########### EVENT ############
        self.pass_account.installEventFilter(self)
        self.back_auth_method.clicked.connect(self.go_to_auth_method)
        self.next_mode.clicked.connect(self.password_account)



    def password_account(self):

        password = self.pass_account.text()
        user = Session.current_user

        success, message = (
            self.auth_service.password(user, password)
        )

        if success:

            Session.current_user = user

            self.thong_bao_pass.setStyleSheet(
                "color: green;"
            )

            self.thong_bao_pass.setText(message)
            QTimer.singleShot(1000, self.go_to_enterOTP)


        else:

            self.thong_bao_pass.setStyleSheet(
                "color: red;"
            )

            self.thong_bao_pass.setText(message)



    def go_to_enterOTP(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(11)) 
        self.reset_form()

    def go_to_auth_method(self):

        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(8))
        self.reset_form()

    def reset_form(self):
        self.pass_account.clear()
        self.thong_bao_pass.setText("")

    def eventFilter(self, source, event):

        if (
            source == self.pass_account
            and event.type() == QEvent.Type.MouseButtonPress
        ):

            self.keyboard.show()

            self.keyboard.set_target(
                self.pass_account
            )
            self.keyboard.mode = "NUM"
            self.keyboard.build_keyboard()

        return super().eventFilter(
            source,
            event
        )
    
