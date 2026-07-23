from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtCore import QTimer, Qt, QSize
from PyQt6.QtGui import QPixmap, QIcon, QAction
from PyQt6.QtGui import QPixmap
from app.nav import PAGES
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # trỏ về thư mục app/


class NextCamController(QMainWindow):

    def __init__(self, stacked_widget):
        super().__init__()

        uic.loadUi("app/ui/NEXT_CAM.ui", self)
        self.stacked_widget = stacked_widget

        ########### SETUP BUTTON ###########
        for btn in [self.next_cam_b]:
            btn.setCheckable(True)
            btn.setAutoExclusive(False)

            btn.setProperty("class", "BackButton_NEXTCAM")

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
        self.next_cam_b.clicked.connect(self.open_camera_page) #("Tiếp theo") #CHƯA nối — để dành cho luồng mở tủ vật lý sau khi xác thực xong
        self.cam_wid.mousePressEvent = self.open_camera_page

        # ===== next_cam_controller.py =====
        pixmap = QPixmap(str(BASE_DIR / "assets/icon/camera.PNG"))

        self.cam_wid.setPixmap(
            pixmap.scaled(
                self.cam_wid.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )

        self.next_cam_b.setIcon(QIcon(str(BASE_DIR / "assets/icon/next.png")))
        self.next_cam_b.setIconSize(QSize(20, 20))

    

    def open_camera_page(self, event):
        # Đi qua AuthMethodController.go_to_face() để kiểm tra has_face:
        #   - Đã có khuôn mặt  → FaceController mode="auth" (mở tủ)
        #   - Chưa có khuôn mặt → FaceController mode="register" (đăng ký lần đầu)
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(PAGES["auth_method"]))
    
