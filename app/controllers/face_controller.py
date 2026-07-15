"""
app/controllers/face_controller.py — Màn hình nhận diện khuôn mặt (PyQt6).

Hoạt động ở 2 chế độ:
  • mode="auth"     — đăng nhập bằng khuôn mặt (từ AuthMethodController)
  • mode="register" — đăng ký khuôn mặt mới (sau khi admin duyệt)

Luồng (auth):
  AuthMethodController → [recog_select] → FaceController (index 15)
  FaceController       → auth OK        → SelectModeController (index 3)
  FaceController       → back           → AuthMethodController (index 8)

Luồng (register):
  RegisterController / profile → FaceController(mode="register")
  FaceController → capture OK  → về Begin (index 0)

Không dùng .ui file — build layout 100% bằng code (không phụ thuộc Qt Designer).
"""

from __future__ import annotations

import numpy as np
import cv2

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSizePolicy,
)
from PyQt6.QtCore  import Qt, QTimer, pyqtSlot
from PyQt6.QtGui   import QImage, QPixmap, QFont, QColor

from app.controllers.face_worker import FaceWorker
from app.utils.session           import Session
from app.services.auth_service   import AuthService
from app.database.user_repository import UserRepository
from app.nav                      import PAGES


# ── Màu sắc (khớp với QSS theme của SML) ─────────────────────────────────────
_BG         = "#1e1e2e"
_PANEL      = "#2a2a3e"
_ACCENT     = "#3b82f6"
_SUCCESS    = "#10b981"
_DANGER     = "#ef4444"
_WARNING    = "#f59e0b"
_TEXT       = "#e2e8f0"
_TEXT_DIM   = "#94a3b8"

_BTN_STYLE = """
QPushButton {{
    background: {bg};
    color: {fg};
    border: none;
    border-radius: 10px;
    padding: 12px 28px;
    font-size: 15px;
    font-weight: 600;
}}
QPushButton:hover  {{ background: {hover}; }}
QPushButton:pressed{{ background: {pressed}; }}
"""


class FaceController(QMainWindow):

    def __init__(self, stacked_widget, mode: str = "auth", cam_index: int = 0):
        super().__init__()
        self.stacked_widget = stacked_widget
        self.mode           = mode
        self.cam_index      = cam_index
        self.auth_service   = AuthService()
        self._worker: FaceWorker | None = None

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {_BG}; color: {_TEXT};")

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        # ── Tiêu đề ───────────────────────────────────────────────────────────
        title_text = "ĐĂNG KÝ KHUÔN MẶT" if self.mode == "register" else "XÁC THỰC KHUÔN MẶT"
        self.lbl_title = QLabel(title_text)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet(f"color: {_TEXT}; font-size: 20px; font-weight: 700;")
        outer.addWidget(self.lbl_title)

        # ── Camera feed ───────────────────────────────────────────────────────
        self.lbl_cam = QLabel()
        self.lbl_cam.setFixedSize(480, 360)
        self.lbl_cam.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cam.setStyleSheet(
            f"background: #000; border: 3px solid {_PANEL}; border-radius: 12px;"
        )
        self.lbl_cam.setText("Đang khởi động camera...")
        self.lbl_cam.setStyleSheet(
            f"background: #111; border: 3px solid {_PANEL}; border-radius: 12px;"
            f"color: {_TEXT_DIM}; font-size: 14px;"
        )

        cam_wrapper = QHBoxLayout()
        cam_wrapper.addStretch()
        cam_wrapper.addWidget(self.lbl_cam)
        cam_wrapper.addStretch()
        outer.addLayout(cam_wrapper)

        # ── Khung trạng thái ─────────────────────────────────────────────────
        status_frame = QFrame()
        status_frame.setStyleSheet(
            f"background: {_PANEL}; border-radius: 10px; padding: 4px;"
        )
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(16, 10, 16, 10)
        status_layout.setSpacing(6)

        self.lbl_liveness = QLabel("⏳ Chờ khuôn mặt...")
        self.lbl_liveness.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_liveness.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 13px;")

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 14px; font-weight: 600;")
        self.lbl_status.setWordWrap(True)

        status_layout.addWidget(self.lbl_liveness)
        status_layout.addWidget(self.lbl_status)
        outer.addWidget(status_frame)

        # ── Nút ──────────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_back = QPushButton("← Quay lại")
        self.btn_back.setStyleSheet(_BTN_STYLE.format(
            bg=_PANEL, fg=_TEXT, hover="#3a3a5c", pressed="#2a2a4c"
        ))
        self.btn_back.setFixedHeight(48)
        self.btn_back.clicked.connect(self._on_back)

        self.btn_retry = QPushButton("🔄 Thử lại")
        self.btn_retry.setStyleSheet(_BTN_STYLE.format(
            bg=_ACCENT, fg="#fff", hover="#2563eb", pressed="#1d4ed8"
        ))
        self.btn_retry.setFixedHeight(48)
        self.btn_retry.setVisible(False)
        self.btn_retry.clicked.connect(self._start_worker)

        btn_row.addWidget(self.btn_back)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_retry)
        outer.addLayout(btn_row)

        outer.addStretch()

    # ══════════════════════════════════════════════════════════════════════════
    #  LIFECYCLE — bật/tắt camera khi màn hình hiện/ẩn
    # ══════════════════════════════════════════════════════════════════════════

    def showEvent(self, event):
        super().showEvent(event)
        self._reset_ui()
        self._start_worker()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._stop_worker()

    def set_mode(self, mode: str):
        """
        Đổi mode từ bên ngoài (auth_method_controller gọi trước khi show).
        Cập nhật title label để UI phản ánh đúng chế độ.
        """
        self.mode = mode
        if hasattr(self, "lbl_title"):
            self.lbl_title.setText(
                "ĐĂNG KÝ KHUÔN MẶT" if mode == "register" else "XÁC THỰC KHUÔN MẶT"
            )


    # ══════════════════════════════════════════════════════════════════════════
    #  WORKER
    # ══════════════════════════════════════════════════════════════════════════

    def _start_worker(self):
        self._stop_worker()
        self.btn_retry.setVisible(False)
        self._set_status("Đang phân tích...", _TEXT_DIM)

        self._worker = FaceWorker(mode=self.mode, cam_index=self.cam_index)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.face_detected.connect(self._on_face_detected)
        self._worker.liveness_status.connect(self._on_liveness)
        self._worker.auth_success.connect(self._on_auth_success)
        self._worker.auth_failed.connect(self._on_auth_failed)
        self._worker.register_done.connect(self._on_register_done)
        self._worker.enroll_progress.connect(self._on_enroll_progress)
        self._worker.face_log.connect(self._on_face_log)
        self._worker.no_face_registered.connect(self._on_no_face_registered)
        self._worker.start()

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self._worker = None

    # ══════════════════════════════════════════════════════════════════════════
    #  SLOTS — nhận signal từ FaceWorker
    # ══════════════════════════════════════════════════════════════════════════

    @pyqtSlot(object)
    def _on_frame(self, frame: np.ndarray):
        """Hiển thị frame lên QLabel."""
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img   = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix   = QPixmap.fromImage(img).scaled(
            480, 360,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_cam.setPixmap(pix)
        # reset stylesheet để hiển thị ảnh đúng
        self.lbl_cam.setStyleSheet(
            "background: #000; border: 3px solid #3b82f6; border-radius: 12px;"
        )

    @pyqtSlot(bool)
    def _on_face_detected(self, detected: bool):
        border_color = _ACCENT if detected else _PANEL
        self.lbl_cam.setStyleSheet(
            f"background: #000; border: 3px solid {border_color}; border-radius: 12px;"
        )

    @pyqtSlot(bool, str)
    def _on_liveness(self, ok: bool, msg: str):
        if ok:
            self.lbl_liveness.setText(f"✅ Liveness: {msg}")
            self.lbl_liveness.setStyleSheet(f"color: {_SUCCESS}; font-size: 13px;")
        else:
            self.lbl_liveness.setText(f"⚠ {msg}")
            self.lbl_liveness.setStyleSheet(f"color: {_WARNING}; font-size: 13px;")

    @pyqtSlot(str, str)
    def _on_auth_success(self, mssv: str, name: str):
        """Nhận diện thành công → set Session → chuyển sang SelectMode (index 3)."""
        self._stop_worker()
        Session.current_user  = mssv
        Session.user_name     = name
        self._set_status(f"✅ Xin chào, {name}!", _SUCCESS)

        QTimer.singleShot(1200, self._go_to_select_mode)

    @pyqtSlot(str)
    def _on_auth_failed(self, reason: str):
        """Match thất bại — hiển thị lý do, không dừng worker (tiếp tục quét)."""
        self._set_status(reason, _DANGER)

    @pyqtSlot(int, int)
    def _on_enroll_progress(self, current: int, total: int):
        """Cập nhật tiến độ thu thập frame khi đăng ký."""
        self._set_status(f"📸 Đang chụp... {current}/{total}", _WARNING)

    @pyqtSlot(object)
    def _on_register_done(self, emb: np.ndarray):
        """Capture embedding khi đăng ký — lưu vào DB + push Firebase."""
        self._stop_worker()
        mssv = Session.current_user
        if not mssv:
            self._set_status("Lỗi: Chưa đăng nhập", _DANGER)
            self.btn_retry.setVisible(True)
            return

        ok = self.auth_service.save_face_embedding(mssv, emb)
        if ok:
            self._set_status("✅ Đã lưu khuôn mặt!", _SUCCESS)
            QTimer.singleShot(1500, self._go_to_begin)
        else:
            self._set_status("❌ Lưu thất bại, thử lại", _DANGER)
            self.btn_retry.setVisible(True)

    @pyqtSlot(str, str, str)
    def _on_face_log(self, mssv: str, event: str, detail: str):
        """Ghi FaceLog vào SQLite."""       
        try:
            from app.database.user_repository import UserRepository
            UserRepository().log_face_event(mssv, event, detail)
        except Exception as e:
            print(f"[FaceController] FaceLog error: {e}")

    @pyqtSlot()
    def _on_no_face_registered(self):
        """User chưa có khuôn mặt → chuyển sang chế độ đăng ký."""        
        self._stop_worker()
        self._set_status("📸 Chưa có khuôn mặt — chuyển sang đăng ký...", _WARNING)
        QTimer.singleShot(1500, self._switch_to_register)

    def _switch_to_register(self):
        """Giữ nguyên Session.current_user, đổi mode sang register rồi restart."""    
        self.mode = "register"
        self.lbl_title.setText("ĐĂNG KÝ KHUÔN MẶT")
        self._reset_ui()
        self._start_worker()

    # ══════════════════════════════════════════════════════════════════════════
    #  NAVIGATION
    # ══════════════════════════════════════════════════════════════════════════

    def _go_to_select_mode(self):
        self._stop_worker()
        self.stacked_widget.setCurrentIndex(PAGES["select_mode"])

    def _go_to_begin(self):
        self._stop_worker()
        self.stacked_widget.setCurrentIndex(0)

    def _on_back(self):
        self._stop_worker()
        if self.mode == "register":
            self.stacked_widget.setCurrentIndex(0)
        else:
            self.stacked_widget.setCurrentIndex(8)  # AuthMethodController

    # ── Helper ────────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, color: str):
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: 600;"
        )

    def _reset_ui(self):
        self.lbl_liveness.setText("⏳ Chờ khuôn mặt...")
        self.lbl_liveness.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 13px;")
        self.lbl_status.setText("")
        self.btn_retry.setVisible(False)
        self.lbl_cam.clear()
        self.lbl_cam.setText("Đang khởi động camera...")