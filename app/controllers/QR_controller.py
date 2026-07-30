from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtCore import QTimer, Qt, QDate, QTime
from PyQt6.QtGui import QPixmap
from app.nav import PAGES
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # trỏ về thư mục app/



class QRController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()

        uic.loadUi("app/ui/QR_CODE.ui", self)
        self.stacked_widget = stacked_widget

        ########### SETUP BUTTON ###########
        for btn in [self.back_b]:
            btn.setCheckable(True)
            btn.setAutoExclusive(False)

            btn.setProperty("class", "systemButton")
            
            def create_release_handler(b=btn):
                def safe_clear():
                    try:
                        if b and not b.isHidden():
                            b.setChecked(False)
                    except RuntimeError:
                        pass
                QTimer.singleShot(150, safe_clear)

            btn.released.connect(create_release_handler)

        pixmap = QPixmap(str(BASE_DIR / "assets/icon/Form.PNG"))

        self.qr_code.setPixmap(
            pixmap.scaled(
                self.qr_code.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
        pixmap1 = QPixmap(str(BASE_DIR / "assets/icon/dki_muon_tu.PNG"))

        self.huongdan.setPixmap(
            pixmap1.scaled(
                self.huongdan.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )

        # EVENT
        self.back_b.clicked.connect(self.go_to_begin)



    def go_to_begin(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(PAGES["begin"]))