"""
app/controllers/face_worker.py — AI pipeline chạy trong QThread riêng.

Thay đổi so với phiên bản cũ:
    - Dùng IR frame làm nguồn chính cho landmarks + embedding
    - ir_to_bgr(ir) convert grayscale → BGR giả để feed vào dlib/MediaPipe
    - Fallback về color nếu IR không available (tránh crash)
    - frame_ready vẫn emit color frame để UI hiển thị preview màu tự nhiên
      (người dùng thấy ảnh màu, nhưng AI chạy trên IR)

LƯU Ý QUAN TRỌNG:
    Sau khi deploy bản này, tất cả embedding cũ (train trên color) phải xóa
    và enroll lại — IR embedding và color embedding không tương thích nhau.
"""

import time
import numpy as np
from collections import deque

from PyQt6.QtCore import QThread, pyqtSignal

from hardware.camera              import CameraBackend
from ai.face_utils                import center_face
from ai.ai_utils                  import liveness, landmarks, embedding, ir_to_bgr
from app.database.user_repository import UserRepository

MATCH_THRESHOLD  = 0.45
CONFIRM_FRAMES   = 3
LIVENESS_WINDOW  = 7   # số frame gần nhất để xét liveness
LIVENESS_MIN_OK  = 2    # cần ít nhất 4/7 frame REAL mới pass (auth)
MAX_FAILS        = 5
LOCKOUT_SECS     = 60
ENROLL_FRAMES    = 10


class FaceWorker(QThread):

    frame_ready        = pyqtSignal(object)
    face_detected      = pyqtSignal(bool)
    liveness_status    = pyqtSignal(bool, str)
    auth_success       = pyqtSignal(str, str)
    auth_failed        = pyqtSignal(str)
    register_done      = pyqtSignal(object)
    enroll_progress    = pyqtSignal(int, int)
    face_log           = pyqtSignal(str, str, str)
    no_face_registered = pyqtSignal()

    def __init__(self, mode: str = "auth", cam_index: int = 0):
        super().__init__()
        self.mode      = mode
        self.cam_index = cam_index
        self._running  = False
        self._camera   = CameraBackend()

    def run(self):
        self._running = True

        try:
            from app.utils.session import Session
            mssv_session = Session.current_user or ""
        except Exception:
            mssv_session = ""

        user_repo = UserRepository()
        known     = user_repo.get_all_embeddings()

        # ── Check has_face (chỉ auth mode) ───────────────────────────────────
        if self.mode == "auth" and mssv_session:
            user = user_repo.find_user(mssv_session)
            if not (user and user["has_face"]):
                self.no_face_registered.emit()
                self._running = False
                return

        # Bật camera với IR
        self._camera.start(use_ir=True)
        time.sleep(0.5)

        liveness_window   = deque(maxlen=LIVENESS_WINDOW)
        confirm_count     = 0
        last_match_mssv   = None
        fail_count        = 0
        lockout_until     = 0.0
        enroll_embeddings = []

        try:
            while self._running:
                color, ir = self._camera.get()

                # ── Chọn frame để nhận diện ───────────────────────────────────
                # Ưu tiên IR (tốt hơn trong thiếu sáng).
                # Fallback về color nếu IR chưa về (vd: khởi động chậm).
                if ir is not None:
                    recog_frame = ir_to_bgr(ir)   # grayscale → BGR giả
                elif color is not None:
                    recog_frame = color            # fallback
                else:
                    time.sleep(0.033)
                    continue

                # ── UI preview: luôn dùng color nếu có, không thì dùng recog ──
                preview_frame = color if color is not None else recog_frame
                self.frame_ready.emit(preview_frame.copy())

                # ── Detect mặt trên recog_frame ───────────────────────────────
                box = center_face(recog_frame)
                self.face_detected.emit(box is not None)

                if not box:
                    liveness_window.clear()
                    confirm_count   = 0
                    last_match_mssv = None
                    time.sleep(0.033)
                    continue

                # ── Liveness — chạy trên IR gốc (grayscale), không phải BGR giả ──
                live_ok, live_msg = liveness(ir) if ir is not None else (False, "Chờ IR...")
                print(f"[LIVE] ok={live_ok}, msg={live_msg}")
                liveness_window.append(live_ok)

                ok_count = liveness_window.count(True)

                # Emit trạng thái cho UI
                if live_ok:
                    self.liveness_status.emit(True, f"REAL ({ok_count}/{LIVENESS_WINDOW})")
                else:
                    self.liveness_status.emit(False, live_msg)

                # Auth: cần đủ LIVENESS_MIN_OK frame REAL trong window gần nhất
                # Register: chỉ cần 1 frame REAL là đủ
                if self.mode == "auth":
                    if ok_count < LIVENESS_MIN_OK:
                        time.sleep(0.033)
                        continue
                else:
                    if not live_ok:
                        time.sleep(0.033)
                        continue

                # ── Landmarks + Embedding — chạy trên IR (qua ir_to_bgr) ──────
                shape, det = landmarks(recog_frame)
                if shape is None:
                    time.sleep(0.033)
                    continue

                try:
                    emb = embedding(recog_frame, shape)
                except Exception as e:
                    print(f"[FaceWorker] embedding error: {e}")
                    time.sleep(0.033)
                    continue

                # ── Mode: Đăng ký ─────────────────────────────────────────────
                if self.mode == "register":
                    enroll_embeddings.append(emb)
                    self.enroll_progress.emit(len(enroll_embeddings), ENROLL_FRAMES)
                    if len(enroll_embeddings) >= ENROLL_FRAMES:
                        avg_emb = np.mean(enroll_embeddings, axis=0)
                        try:
                            from app.utils.session import Session
                            self.face_log.emit(
                                Session.current_user or "unknown",
                                "FACE_REGISTER",
                                f"frames={ENROLL_FRAMES},source={'IR' if ir is not None else 'COLOR'}"
                            )
                        except Exception:
                            pass
                        self.register_done.emit(avg_emb)
                        break
                    time.sleep(0.033)
                    continue

                # ── Mode: Xác thực ────────────────────────────────────────────
                if not known:
                    self.auth_failed.emit("Chưa có dữ liệu khuôn mặt")
                    time.sleep(1)
                    continue

                best_dist = float("inf")
                best_mssv = None
                best_name = None

                for mssv, name, known_emb in known:
                    dist = float(np.linalg.norm(emb - known_emb))
                    if dist < best_dist:
                        best_dist = dist
                        best_mssv = mssv
                        best_name = name
                print(f"[MATCH] best_dist={best_dist:.4f}, mssv={best_mssv}, threshold={MATCH_THRESHOLD}")

                if best_dist <= MATCH_THRESHOLD:
                    if best_mssv == last_match_mssv:
                        confirm_count += 1
                    else:
                        confirm_count   = 1
                        last_match_mssv = best_mssv

                    if confirm_count >= CONFIRM_FRAMES:
                        fail_count = 0
                        self.face_log.emit(best_mssv, "FACE_VERIFY", f"dist={best_dist:.3f}")
                        self.auth_success.emit(best_mssv, best_name)
                        break
                else:
                    confirm_count   = 0
                    last_match_mssv = None
                    fail_count += 1
                    mssv_log = best_mssv or (mssv_session or "unknown")
                    self.face_log.emit(
                        mssv_log, "FACE_FAIL",
                        f"dist={best_dist:.3f} fail={fail_count}"
                    )
                    if fail_count >= MAX_FAILS:
                        lockout_until = time.time() + LOCKOUT_SECS
                        fail_count    = 0
                        self.auth_failed.emit(
                            f"❌ Thử sai {MAX_FAILS} lần — khóa {LOCKOUT_SECS}s"
                        )
                    else:
                        self.auth_failed.emit(
                            f"Không nhận ra khuôn mặt (còn {MAX_FAILS - fail_count} lần)"
                        )

                time.sleep(0.033)

        finally:
            self._camera.stop()
            print("[FaceWorker] Camera đã tắt")

    def stop(self):
        self._running = False
        self._camera.stop()
        self.wait(3000)