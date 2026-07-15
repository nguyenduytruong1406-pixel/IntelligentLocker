from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtCore import QTimer, Qt, QDate, QTime
from PyQt6.QtGui import QPixmap

class BeginController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()

        uic.loadUi("app/ui/START.ui", self)
        self.stacked_widget = stacked_widget

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
        # EVENT
        self.da_dk.clicked.connect(self.go_to_login)
        self.chua_dk.clicked.connect(self.go_to_reg)
        self.ho_tro.clicked.connect(self.go_to_service)


    def go_to_login(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(1))

    def go_to_reg(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(7))

    def go_to_service(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(13))