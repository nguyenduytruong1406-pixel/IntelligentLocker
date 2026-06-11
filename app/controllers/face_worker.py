"""
app/controllers/face_worker.py — AI pipeline chạy trong QThread riêng.
"""

import time
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

from hardware.camera           import CameraBackend
from ai.face_utils             import center_face
from ai.ai_utils               import liveness, landmarks, embedding
from app.database.user_repository import UserRepository

MATCH_THRESHOLD = 0.45
CONFIRM_FRAMES  = 3
LIVENESS_FRAMES = 5
MAX_FAILS       = 5
LOCKOUT_SECS    = 60
ENROLL_FRAMES   = 10


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

        # Bật camera với IR (giữ nguyên như file cũ hoạt động tốt)
        self._camera.start(use_ir=True)
        time.sleep(0.5)

        liveness_ok_count = 0
        confirm_count     = 0
        last_match_mssv   = None
        fail_count        = 0
        lockout_until     = 0.0
        enroll_embeddings = []

        try:
            while self._running:
                color, ir = self._camera.get()

                if color is None:
                    time.sleep(0.033)
                    continue

                self.frame_ready.emit(color.copy())

                box = center_face(color)
                self.face_detected.emit(box is not None)

                if not box:
                    liveness_ok_count = 0
                    confirm_count     = 0
                    last_match_mssv   = None
                    time.sleep(0.033)
                    continue

                # ── Liveness — luôn chạy để hiển thị status ───────────────
                live_ok, live_msg = liveness(ir) if ir is not None else (False, "Chờ IR...")
                self.liveness_status.emit(live_ok, live_msg)

                if not live_ok:
                    liveness_ok_count = 0
                    confirm_count     = 0
                    time.sleep(0.033)
                    continue

                liveness_ok_count += 1

                # ── Register: KHÔNG cần chờ LIVENESS_FRAMES, liveness OK 1 lần là đủ ──
                # ── Auth: phải đủ LIVENESS_FRAMES frame liên tiếp ─────────────────────
                if self.mode == "auth" and liveness_ok_count < LIVENESS_FRAMES:
                    time.sleep(0.033)
                    continue

                # ── Landmarks + Embedding ──────────────────────────────────
                shape, det = landmarks(color)
                if shape is None:
                    time.sleep(0.033)
                    continue

                try:
                    emb = embedding(color, shape)
                except Exception as e:
                    print(f"[FaceWorker] embedding error: {e}")
                    time.sleep(0.033)
                    continue

                # ── Mode: Đăng ký ─────────────────────────────────────────
                if self.mode == "register":
                    enroll_embeddings.append(emb)
                    self.enroll_progress.emit(len(enroll_embeddings), ENROLL_FRAMES)
                    if len(enroll_embeddings) >= ENROLL_FRAMES:
                        avg_emb = np.mean(enroll_embeddings, axis=0)
                        try:
                            from app.utils.session import Session
                            self.face_log.emit(Session.current_user or "unknown", "FACE_REGISTER", f"frames={ENROLL_FRAMES}")
                        except Exception:
                            pass
                        self.register_done.emit(avg_emb)
                        break
                    time.sleep(0.033)
                    continue

                # ── Mode: Xác thực ─────────────────────────────────────────
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
                    self.face_log.emit(mssv_log, "FACE_FAIL", f"dist={best_dist:.3f} fail={fail_count}")
                    if fail_count >= MAX_FAILS:
                        lockout_until = time.time() + LOCKOUT_SECS
                        fail_count = 0
                        self.auth_failed.emit(f"❌ Thử sai {MAX_FAILS} lần — khóa {LOCKOUT_SECS}s")
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