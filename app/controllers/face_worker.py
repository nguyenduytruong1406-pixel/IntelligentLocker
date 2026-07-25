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
from app.utils.session             import Session

MATCH_THRESHOLD    = 0.45
CONFIRM_FRAMES     = 3
LIVENESS_WINDOW    = 7   # số frame gần nhất để xét liveness
LIVENESS_MIN_OK    = 4    # cần ít nhất 3/9 frame REAL mới pass (auth)
MAX_FAILS          = 20
LOCKOUT_SECS       = 60
ENROLL_FRAMES      = 10
BOX_LOST_GRACE     = 3   # số frame liên tiếp KHÔNG thấy mặt trước khi thật sự reset
                          # (MediaPipe detect chập chờn frame-to-frame trên IR —
                          # mất box 1 frame đơn lẻ không có nghĩa là mặt đã rời khung hình)
POSE_MAX_OFFSET    = 0.35   # lệch mũi so với tâm 2 mắt (tỉ lệ theo khoảng cách 2 mắt)
                             # vượt ngưỡng này coi là nghiêng quá — bỏ qua embedding/match


def _pose_ok(shape) -> bool:
    """
    Kiểm tra mặt có đủ chính diện để embedding đáng tin không.

    dlib ResNet 128-D được train chủ yếu trên mặt gần chính diện — embedding
    từ góc nghiêng mạnh (gần profile) không đáng tin, dù liveness vẫn pass
    bình thường (liveness chỉ kiểm tra da thật, không quan tâm góc mặt).

    Heuristic đơn giản, không cần model riêng: so lệch vị trí mũi (landmark
    #30) so với điểm giữa 2 mắt (landmark #36, #45), chuẩn hóa theo khoảng
    cách 2 mắt. Mặt càng nghiêng, mũi càng lệch khỏi tâm 2 mắt.
    """
    try:
        pts       = shape.parts()
        left_eye  = pts[36]
        right_eye = pts[45]
        nose      = pts[30]
    except (IndexError, AttributeError):
        return True  # shape không đủ 68 điểm — không gate, để bước sau xử lý

    eye_width = abs(right_eye.x - left_eye.x)
    if eye_width < 1:
        return False

    eye_mid_x     = (left_eye.x + right_eye.x) / 2
    offset_ratio  = abs(nose.x - eye_mid_x) / eye_width
    return offset_ratio < POSE_MAX_OFFSET


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
    camera_error       = pyqtSignal(str)
    lockout_active     = pyqtSignal(int)   # còn lại bao nhiêu giây bị khóa

    def __init__(self, mode: str = "auth", cam_index: int = 0):
        super().__init__()
        self.mode      = mode
        self.cam_index = cam_index
        self._running  = False
        self._camera   = CameraBackend()

    def run(self):
        self._running = True

        mssv_session = Session.current_user or ""

        user_repo = UserRepository()
        known     = user_repo.get_all_embeddings()

        # ── Verify-mode: đã biết trước tài khoản (mssv_session có sẵn) ────────
        # Chỉ nên so khớp với ĐÚNG người này, không phải nearest-neighbor toàn
        # hệ thống — nếu không, người đứng trước camera có thể bị match nhầm
        # sang MSSV khác (embedding gần người khác hơn), Session.current_user
        # bị ghi đè sai, và select_mode mở tủ của người khác chứ không phải
        # tài khoản đang đăng nhập.
        #
        # Identify-mode (mssv_session rỗng, vd đăng nhập chỉ bằng khuôn mặt,
        # chưa biết trước là ai) vẫn giữ nguyên nearest-neighbor trên toàn bộ
        # `known` như cũ.
        verify_mode = self.mode == "auth" and bool(mssv_session)

        # ── Khóa xác thực (MAX_FAILS) — kiểm tra TRƯỚC KHI mở camera ──────────
        # Lưu ở Session (không phải biến local) nên vẫn còn hiệu lực dù người
        # dùng bấm "Quay lại" rồi chọn "Nhận diện" lại — không bị mất khóa.
        if self.mode == "auth":
            lockout_key       = mssv_session or "__anonymous__"
            remaining_lockout = Session.get_face_lockout_remaining(lockout_key)
            if remaining_lockout > 0:
                self.lockout_active.emit(int(remaining_lockout) + 1)
                self._running = False
                return

        if verify_mode:
            user = user_repo.find_user(mssv_session)
            if not (user and user["has_face"]):
                self.no_face_registered.emit()
                self._running = False
                return

            known = [item for item in known if item[0] == mssv_session]
            if not known:
                self.no_face_registered.emit()
                self._running = False
                return

        # Bật camera với IR
        self._camera.start(use_ir=True)

        # Chờ tối đa CAMERA_START_TIMEOUT giây để camera thật sự mở được.
        # Trước đây chỉ time.sleep(0.5) rồi vào thẳng while loop — nếu camera
        # mở lỗi (VD: đang bị phiên trước giữ độc quyền do race condition khi
        # ẩn/hiện màn hình nhanh, group không tìm thấy, driver lỗi...) thì
        # color/ir mãi mãi là None, loop cứ spin im lặng, UI kẹt ở "Đang phân
        # tích..." vô thời hạn mà không ai biết vì sao.
        CAMERA_START_TIMEOUT = 5.0
        t0 = time.time()
        got_frame = False
        while self._running and (time.time() - t0) < CAMERA_START_TIMEOUT:
            if not self._camera.is_active:
                break
            color, ir = self._camera.get()
            if color is not None or ir is not None:
                got_frame = True
                break
            time.sleep(0.05)

        if not got_frame:
            err = self._camera.error or "Camera không phản hồi (hết thời gian chờ)"
            self.camera_error.emit(err)
            self._running = False
            self._camera.stop()
            return

        liveness_window   = deque(maxlen=LIVENESS_WINDOW)
        confirm_count     = 0
        last_match_mssv   = None
        fail_count        = 0
        enroll_embeddings = []
        box_lost_streak   = 0

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
                    box_lost_streak += 1
                    if box_lost_streak >= BOX_LOST_GRACE:
                        liveness_window.clear()
                        confirm_count   = 0
                        last_match_mssv = None
                    time.sleep(0.033)
                    continue

                # Mặt đã thấy lại — reset streak mất box
                box_lost_streak = 0

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

                # ── Pose gate ──────────────────────────────────────────────
                # Liveness đã pass (da thật) nhưng góc mặt có thể vẫn nghiêng
                # quá — không burn fail_count / không reset liveness_window,
                # chỉ bỏ qua frame này và chờ frame chính diện hơn.
                if not _pose_ok(shape):
                    self.liveness_status.emit(True, "Vui lòng nhìn thẳng camera")
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
                        lockout_key = mssv_log or "__anonymous__"
                        Session.set_face_lockout(lockout_key, LOCKOUT_SECS)
                        self.lockout_active.emit(LOCKOUT_SECS)
                        break
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