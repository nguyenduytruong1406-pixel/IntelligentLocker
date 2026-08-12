"""
main.py — Entry point (IntelligentLocker, luồng hiện tại + SML)

Trang được đăng ký qua app.nav.PAGES (tên -> index thật), mọi controller
điều hướng bằng PAGES["ten_trang"], KHÔNG dùng số cứng.
"""

import sys
import os
import subprocess
import traceback

# ── 1. Migrate DB ─────────────────────────────────────────────────────────────
from app.database.database import migrate
migrate()

# ── 2. Init Firebase ──────────────────────────────────────────────────────────
from app.firebase_config import FIREBASE_OK  # noqa: F401

# NOTE: subprocess.run ở đây là BLOCKING và chạy TRƯỚC khi có QApplication.
# Nếu sync chậm (mạng yếu / Firebase timeout) app sẽ đứng hình một lúc trước
# khi có gì hiện ra. Giữ nguyên hành vi hiện tại, chỉ ghi chú lại.
subprocess.run(
    [sys.executable, "sync_tool.py", "--sync"],
    cwd=os.path.dirname(os.path.abspath(__file__)),
)

# ── 3. Sync listener + daemon threads ────────────────────────────────────────
import sync_listener
sync_listener.start()

# ── 4. GUI ────────────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import QApplication, QStackedWidget
from PyQt6.QtCore    import QTimer, QObject, QEvent
from app.services.auth_service import AuthService
from app.controllers.door_monitor_worker import DoorMonitorWorker

from app.controllers.login_controller           import LoginController
from app.controllers.begin_controller           import BeginController
from app.controllers.loading_controller         import LoadingController
from app.controllers.success_controller         import SuccessController
from app.controllers.video                      import VideoScreenController
from app.controllers.auth_method_controller     import AuthMethodController
from app.controllers.face_controller            import FaceController
from app.controllers.select_mode                import SelectModeController


# ── Các trang mới lấy từ SML ──────────────────────────────────────────────────
from app.controllers.change_password_controller import ChangePassController
from app.controllers.next_cam_controller        import NextCamController
from app.controllers.QR_controller              import QRController
from app.controllers.cleanup_worker             import CleanupWorker
from app.controllers.send_otp_controller        import SendEmailController
from app.controllers.enter_otp_controller       import EnterOtpController
from app.services.cleanup_service import CleanupService
from app.nav import PAGES



app = QApplication(sys.argv)
cleanup_service = CleanupService()
auth_service   = AuthService()

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

# Tạo các trang đang thực sự dùng.
# CHÚ Ý: chỉ tạo 1 FaceController duy nhất — auth_method_controller.py chuyển
# đổi giữa 2 chế độ "auth"/"register" bằng face_page.set_mode(), không dùng
# 2 trang riêng biệt.
loading_page     = LoadingController()
success_page     = SuccessController()
begin_page       = BeginController(stacked_widget)
login_page       = LoginController(stacked_widget)
video_page       = VideoScreenController(stacked_widget)
auth_method_page = AuthMethodController(stacked_widget)
face_page        = FaceController(stacked_widget, mode="auth", cam_index=0)
select_mode_page = SelectModeController(stacked_widget, loading_page, success_page)
sendOTP_page     = SendEmailController(stacked_widget)
enterOTP_page    = EnterOtpController(stacked_widget)
# Trang mới từ SML
change_pass_page = ChangePassController(stacked_widget, loading_page, success_page)
nextcam_page     = NextCamController(stacked_widget)
QR_page          = QRController(stacked_widget)

# ── Đăng ký vào stack qua PAGES (app.nav) — tên -> index thật ────────────────
def add_page(name: str, widget) -> None:
    stacked_widget.addWidget(widget)
    PAGES[name] = stacked_widget.indexOf(widget)

add_page("begin",       begin_page)
add_page("login",       login_page)
add_page("loading",     loading_page)
add_page("success",     success_page)
add_page("video",       video_page)
add_page("auth_method", auth_method_page)
add_page("face",        face_page)
add_page("select_mode", select_mode_page)
add_page("change_pass", change_pass_page)
add_page("next_cam",    nextcam_page)
add_page("qr_code",     QR_page)
add_page("Send_OTP",   sendOTP_page)
add_page("Enter_OTP", enterOTP_page)

print("[main] PAGES index map:", PAGES)


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

# ── CleanupWorker chạy nền (QThread), tránh block UI khi gửi mail cảnh báo ───
cleanup_worker = None  # giữ reference để tránh bị garbage collect

def run_cleanup():
    global cleanup_worker
    if cleanup_worker and cleanup_worker.isRunning():
        return  # đang chạy lượt trước, bỏ qua lượt này
    cleanup_worker = CleanupWorker(cleanup_service)
    cleanup_worker.start()

timer_cleanup.timeout.connect(run_cleanup)
run_cleanup()
timer_cleanup.start(60_000)


# ── DoorMonitorWorker chạy nền — kiểm tra tủ quên đóng ──────────────────────
door_monitor_worker = None

def run_door_monitor():
    global door_monitor_worker
    if door_monitor_worker and door_monitor_worker.isRunning():
        return
    door_monitor_worker = DoorMonitorWorker(auth_service)
    door_monitor_worker.start()

timer_door = QTimer()
timer_door.timeout.connect(run_door_monitor)
timer_door.start(60_000)  # Kiểm tra mỗi 1 phút


# ── Window ────────────────────────────────────────────────────────────────────
stacked_widget.setFixedSize(1024, 600)
stacked_widget.setCurrentIndex(PAGES["video"])   # bắt đầu từ màn hình video
stacked_widget.showFullScreen()


# ── Thoát app: connect on_quit TRƯỚC khi gọi app.exec(), và chỉ gọi 1 LẦN ────
def on_quit():
    print("[App] Đang thoát, dọn dẹp kết nối...")
    try:
        sync_listener._stop_event.set()
    except Exception:
        pass
    try:
        timer_cleanup.stop()
    except Exception:
        pass
    try:
        idle_timer.stop()
    except Exception:
        pass
    if cleanup_worker and cleanup_worker.isRunning():
        cleanup_worker.wait(3000)
        
    try:
        timer_door.stop()  # ← Thêm dòng này
    except Exception:
        pass
    if door_monitor_worker and door_monitor_worker.isRunning():
        door_monitor_worker.wait(3000)  # ← Thêm dòng này

app.aboutToQuit.connect(on_quit)

exit_code = app.exec()   # ← CHỈ gọi app.exec() một lần duy nhất

try:
    import firebase_admin
    if firebase_admin._apps:
        firebase_admin.delete_app(firebase_admin.get_app())
        print("[App] Firebase đã đóng")
except Exception:
    pass

os._exit(exit_code)