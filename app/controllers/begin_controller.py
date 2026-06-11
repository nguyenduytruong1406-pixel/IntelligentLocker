from PyQt6 import uic
from app.paths import UI, GIF, QSS, find_video
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtCore import QTimer


class BeginController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()

        uic.loadUi(UI("test_bg.ui"), self)
        self.stacked_widget = stacked_widget

        ########### SETUP BUTTON ###########
        for btn in [self.login_b, self.sign_in, self.service_button]:
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
        # EVENT
        self.login_b.clicked.connect(self.go_to_login)
        self.sign_in.clicked.connect(self.go_to_sign_in)
        self.service_button.clicked.connect(self.go_to_service)

    def go_to_login(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(1))

    def go_to_sign_in(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(2))

    def go_to_service(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(13))