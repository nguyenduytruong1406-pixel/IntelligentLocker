"""
main.py — Entry point hoàn chỉnh (SML + IntelligentLocker)

Stack index:
  0  begin_page
  1  login_page
  2  register_page
  3  select_mode
  4  select_page
  5  loading_page
  6  success_page
  7  video_page
  8  auth_method_page
  9  password_page
  10 select_guido
  11 sendOTP_page
  12 enterOTP_page
  13 service_page
  14 menu_service
  15 face_page          ← MỚI (FaceController auth)
  16 face_register_page ← MỚI (FaceController register)
"""

import sys

# ── 1. Migrate DB ─────────────────────────────────────────────────────────────
from app.database.database import migrate
migrate()

# ── 2. Init Firebase ──────────────────────────────────────────────────────────
from app.firebase_config import FIREBASE_OK  # noqa: F401
import subprocess, sys, os
subprocess.run(
    [sys.executable, "sync_tool.py", "--sync"],
    cwd=os.path.dirname(os.path.abspath(__file__)),
)
# ── 3. Sync listener + daemon threads ────────────────────────────────────────
import sync_listener
sync_listener.start()

# ── 4. GUI ────────────────────────────────────────────────────────────────────
import traceback
from PyQt6.QtWidgets import QApplication, QStackedWidget
from PyQt6.QtCore    import QTimer, QObject, QEvent

from app.controllers.login_controller        import LoginController
from app.controllers.begin_controller        import BeginController
from app.controllers.select_locker_controller import SelectLockerController
from app.controllers.register_controller     import RegisterController
from app.controllers.select_mode             import SelectModeController
from app.controllers.loading_controller      import LoadingController
from app.controllers.success_controller      import SuccessController
from app.controllers.video                   import VideoScreenController
from app.controllers.auth_method_controller  import AuthMethodController   # ← bản patch
from app.controllers.password_controller     import PassWordController
from app.controllers.service_controller      import ServiceController
from app.controllers.GUI_DO                  import SelectMode_GUIDOController
from app.controllers.send_otp_controller     import SendEmailController
from app.controllers.enter_otp_controller    import EnterOtpController
from app.controllers.menu_service            import MenuServiceController
from app.controllers.face_controller         import FaceController         # ← MỚI
from app.services.cleanup_service            import CleanupService


app = QApplication(sys.argv)
cleanup_service = CleanupService()


# ── Load QSS ──────────────────────────────────────────────────────────────────
def load_global_style():
    styles = ""
    for path in [
        "app/assets/styles/keyboard.qss",
        "app/assets/styles/locker.qss",
        "app/assets/styles/begin.qss",
    ]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                styles += f.read() + "\n"
        except FileNotFoundError:
            print(f"[QSS] Không tìm thấy: {path}")
    app.setStyleSheet(styles)

load_global_style()


# ── Idle timer ────────────────────────────────────────────────────────────────
idle_timer    = QTimer()
timer_cleanup = QTimer()


class GlobalFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.KeyPress,
        ):
            idle_timer.start(60_000)
        return super().eventFilter(obj, event)

_filter = GlobalFilter()
app.installEventFilter(_filter)


# ── Stacked widget ────────────────────────────────────────────────────────────
stacked_widget = QStackedWidget()

# Tạo các trang
loading_page      = LoadingController()
success_page      = SuccessController()
begin_page        = BeginController(stacked_widget)
login_page        = LoginController(stacked_widget)
register_page     = RegisterController(stacked_widget, loading_page, success_page)
select_mode       = SelectModeController(stacked_widget, loading_page, success_page)
select_page       = SelectLockerController(stacked_widget, loading_page, success_page)
video_page        = VideoScreenController(stacked_widget)
auth_method_page  = AuthMethodController(stacked_widget)   # ← bản patch
password_page     = PassWordController(stacked_widget)
service_page      = ServiceController(stacked_widget)
select_guido      = SelectMode_GUIDOController(stacked_widget, loading_page, success_page)
sendOTP_page      = SendEmailController(stacked_widget)
enterOTP_page     = EnterOtpController(stacked_widget)
menu_service      = MenuServiceController(stacked_widget, loading_page, success_page)
face_page         = FaceController(stacked_widget, mode="auth",     cam_index=0)  # ← MỚI #15
face_register_page= FaceController(stacked_widget, mode="register", cam_index=0)  # ← MỚI #16

# Thêm vào stack — GIỮ ĐÚNG THỨ TỰ INDEX
stacked_widget.addWidget(begin_page)            # 0
stacked_widget.addWidget(login_page)            # 1
stacked_widget.addWidget(register_page)         # 2
stacked_widget.addWidget(select_mode)           # 3
stacked_widget.addWidget(select_page)           # 4
stacked_widget.addWidget(loading_page)          # 5
stacked_widget.addWidget(success_page)          # 6
stacked_widget.addWidget(video_page)            # 7
stacked_widget.addWidget(auth_method_page)      # 8
stacked_widget.addWidget(password_page)         # 9
stacked_widget.addWidget(select_guido)          # 10
stacked_widget.addWidget(sendOTP_page)          # 11
stacked_widget.addWidget(enterOTP_page)         # 12
stacked_widget.addWidget(service_page)          # 13
stacked_widget.addWidget(menu_service)          # 14
stacked_widget.addWidget(face_page)             # 15 ← FaceController (auth)
stacked_widget.addWidget(face_register_page)    # 16 ← FaceController (register)


# ── Idle / cleanup ────────────────────────────────────────────────────────────
def back_to_video():
    idle_timer.stop()
    stacked_widget.setCurrentWidget(video_page)
    video_page.player.setPosition(0)
    video_page.player.play()

def show_begin():
    stacked_widget.setCurrentWidget(begin_page)
    idle_timer.start(60_000)

video_page.touched.connect(show_begin)
idle_timer.timeout.connect(back_to_video)
timer_cleanup.timeout.connect(cleanup_service.cleanup_users)
timer_cleanup.start(60_000)


# ── Window ────────────────────────────────────────────────────────────────────
stacked_widget.setFixedSize(1024, 600)
stacked_widget.setCurrentIndex(7)   # bắt đầu từ màn hình video
stacked_widget.show()

def on_quit():
    print("[App] Đang thoát, dọn dẹp kết nối...")
    try:
        import sync_listener
        sync_listener._stop_event.set()
    except: pass
    try: timer_cleanup.stop()
    except: pass
    try: idle_timer.stop()
    except: pass

app.aboutToQuit.connect(on_quit)
app.exec()

# Qt đã thoát hoàn toàn — giờ mới kill Firebase threads
try:
    import firebase_admin
    if firebase_admin._apps:
        firebase_admin.delete_app(firebase_admin.get_app())
        print("[App] Firebase đã đóng")
except: pass
import os
os._exit(0)