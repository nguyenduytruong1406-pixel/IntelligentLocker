"""
verify_with_liveness.py — Pipeline 3 luồng tối ưu
─────────────────────────────────────────────────────
  Thread 1 (Camera)  : asyncio + winsdk → Frame Queue
  Thread 2 (AI)      : liveness + detect + embedding → Result Queue
  Thread 3 (UI/main) : cv2.imshow luôn mượt ~30 FPS

Lợi ích:
  - UI không bị giật khi AI đang tính toán
  - Camera không bị mất frame khi UI bận vẽ
  - AI chỉ nhận frame mới nhất, bỏ qua frame cũ (maxsize=1)
"""

import asyncio
import threading
import queue
import time
import cv2
import numpy as np

from face_utils     import detect_faces_bgr, embedding_from_box, MTCNN_AVAILABLE
from liveness_check import check_liveness_ir
from locker_db      import (migrate, load_all_embeddings, is_locked_out,
                             log_access, open_locker, get_user_locker)

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

# ── Cấu hình ──────────────────────────────────────────────────────────────────
THRESHOLD     = 0.45
VERIFY_FRAMES = 3
IR_GROUP_NAME = "Rts-DMFT-Group"
UI_FPS        = 30          # FPS mục tiêu của UI thread
# ──────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
#  PARSE BITMAP (dùng chung)
# ══════════════════════════════════════════════════════════════════════════════

def parse_bgr(bmp):
    bmp_buf = ref = None
    try:
        w, h    = bmp.pixel_width, bmp.pixel_height
        bmp_buf = bmp.lock_buffer(BitmapBufferAccessMode.READ)
        ref     = bmp_buf.create_reference()
        arr     = np.frombuffer(ref, dtype=np.uint8, count=int(w * h * 1.5)).copy()
        return cv2.cvtColor(arr.reshape(int(h * 1.5), w), cv2.COLOR_YUV2BGR_NV12)
    except: return None
    finally:
        if ref:     ref.close()
        if bmp_buf: bmp_buf.close()

def parse_gray(bmp):
    bmp_buf = ref = None
    try:
        w, h    = bmp.pixel_width, bmp.pixel_height
        bmp_buf = bmp.lock_buffer(BitmapBufferAccessMode.READ)
        ref     = bmp_buf.create_reference()
        arr     = np.frombuffer(ref, dtype=np.uint8, count=w * h).copy()
        return arr.reshape(h, w)
    except: return None
    finally:
        if ref:     ref.close()
        if bmp_buf: bmp_buf.close()


# ══════════════════════════════════════════════════════════════════════════════
#  THREAD 1: CAMERA (asyncio trong background thread)
# ══════════════════════════════════════════════════════════════════════════════

class CameraThread(threading.Thread):
    """
    Chạy asyncio event loop trong background thread.
    Đẩy (color_img, ir_img) vào frame_q liên tục.
    """
    def __init__(self, frame_q: queue.Queue):
        super().__init__(daemon=True, name="CameraThread")
        self.frame_q  = frame_q
        self._color   = None
        self._ir      = None
        self._running = True
        self._loop    = None

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._camera_loop())
        finally:
            self._loop.close()

    async def _camera_loop(self):
        groups = await MediaFrameSourceGroup.find_all_async()
        group  = next((g for g in groups if g.display_name == IR_GROUP_NAME), None)
        if group is None:
            raise RuntimeError(f"Không tìm thấy camera group '{IR_GROUP_NAME}'!")

        mc = MediaCapture()
        s  = MediaCaptureInitializationSettings()
        s.source_group = group; s.sharing_mode = 0; s.memory_preference = 1
        await mc.initialize_async(s)

        color_src = ir_src = None
        for _, src in mc.frame_sources.items():
            k = int(src.info.source_kind)
            if k == int(MediaFrameSourceKind.COLOR)    and color_src is None: color_src = src
            if k == int(MediaFrameSourceKind.INFRARED) and ir_src    is None: ir_src    = src

        cr = await mc.create_frame_reader_async(color_src)
        ir = await mc.create_frame_reader_async(ir_src)
        tc = cr.add_frame_arrived(self._on_color)
        ti = ir.add_frame_arrived(self._on_ir)
        await cr.start_async()
        await ir.start_async()
        print("[Camera] ✓ Đã khởi động — đang stream frames...")

        try:
            while self._running:
                # Chỉ đẩy vào queue khi có đủ cả 2 frame
                if self._color is not None and self._ir is not None:
                    pair = (self._color.copy(), self._ir.copy())
                    # Dùng put_nowait + try để không block camera thread
                    try:
                        self.frame_q.put_nowait(pair)
                    except queue.Full:
                        # Queue đầy → bỏ frame cũ nhất, thay bằng frame mới
                        try: self.frame_q.get_nowait()
                        except queue.Empty: pass
                        self.frame_q.put_nowait(pair)
                await asyncio.sleep(0.03)   # ~33 FPS camera poll
        finally:
            cr.remove_frame_arrived(tc)
            ir.remove_frame_arrived(ti)
            await cr.stop_async()
            await ir.stop_async()
            try: cr.close()
            except: pass
            try: ir.close()
            except: pass

    def _on_color(self, reader, args):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parse_bgr(ref.video_media_frame.software_bitmap)
                if img is not None: self._color = img
        finally:
            if ref:
                try: ref.close()
                except: pass

    def _on_ir(self, reader, args):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parse_gray(ref.video_media_frame.software_bitmap)
                if img is not None: self._ir = img
        finally:
            if ref:
                try: ref.close()
                except: pass

    def stop(self):
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)


# ══════════════════════════════════════════════════════════════════════════════
#  THREAD 2: AI (chạy liveness + detect + embedding)
# ══════════════════════════════════════════════════════════════════════════════

class AIThread(threading.Thread):
    """
    Đọc frame từ frame_q → chạy AI → đẩy kết quả vào result_q.
    Luôn lấy frame mới nhất, bỏ qua frame cũ nếu queue nhiều hơn 1.
    """

    def __init__(self, frame_q: queue.Queue, result_q: queue.Queue, db_map: dict):
        super().__init__(daemon=True, name="AIThread")
        self.frame_q  = frame_q
        self.result_q = result_q
        self.db_map   = db_map
        self._running = True

    def run(self):
        print(f"[AI] ✓ Đã khởi động — "
              f"Detector: {'MTCNN→MediaPipe' if MTCNN_AVAILABLE else 'MediaPipe'} | "
              f"Threshold: {THRESHOLD}")

        while self._running:
            try:
                # Lấy frame — drain queue để luôn xử lý frame MỚI NHẤT
                color_img = ir_img = None
                while True:
                    try:
                        color_img, ir_img = self.frame_q.get_nowait()
                    except queue.Empty:
                        break

                if color_img is None:
                    time.sleep(0.02)
                    continue

                t0 = time.perf_counter()

                # ── Bước 1: IR Liveness ──────────────────────────────────
                live_ok, live_reason = check_liveness_ir(ir_img)

                # ── Bước 2: Face detect (chỉ chạy nếu liveness OK → tiết kiệm CPU) ──
                faces = []
                mssv = name = dist = None

                if live_ok:
                    faces = detect_faces_bgr(color_img)
                    if faces:
                        emb = embedding_from_box(color_img, faces[0])
                        if emb is not None:
                            mssv, name, dist = self._match_1n(emb)

                ms = (time.perf_counter() - t0) * 1000

                # ── Đẩy kết quả vào result_q ────────────────────────────
                result = {
                    "color_img":   color_img,
                    "ir_img":      ir_img,
                    "live_ok":     live_ok,
                    "live_reason": live_reason,
                    "faces":       faces,
                    "mssv":        mssv,
                    "name":        name,
                    "dist":        dist,
                    "ai_ms":       ms,
                }

                # Chỉ giữ kết quả mới nhất
                try: self.result_q.get_nowait()
                except queue.Empty: pass
                self.result_q.put_nowait(result)

            except Exception as e:
                print(f"[AI] Lỗi: {e}")
                time.sleep(0.05)

    def _match_1n(self, emb):
        best_mssv = best_name = None
        best_dist = float("inf")
        for ms, (e, n) in self.db_map.items():
            d = float(np.linalg.norm(emb - e))
            if d < best_dist:
                best_dist = d; best_mssv = ms; best_name = n
        if best_dist <= THRESHOLD:
            return best_mssv, best_name, best_dist
        return None, None, best_dist

    def stop(self):
        self._running = False


# ══════════════════════════════════════════════════════════════════════════════
#  THREAD 3: UI (main thread — cv2.imshow)
# ══════════════════════════════════════════════════════════════════════════════

def draw_overlay(result: dict, consecutive: int, ai_fps: float) -> np.ndarray:
    """Vẽ toàn bộ overlay lên frame color."""
    color_img   = result["color_img"]
    ir_img      = result["ir_img"]
    live_ok     = result["live_ok"]
    live_reason = result["live_reason"]
    faces       = result["faces"]
    mssv        = result["mssv"]
    name        = result["name"]
    dist        = result["dist"]
    ai_ms       = result["ai_ms"]

    PREV = (640, 360)
    frame = cv2.resize(color_img, PREV)
    sx = PREV[0] / color_img.shape[1]
    sy = PREV[1] / color_img.shape[0]

    # ── Bbox khuôn mặt ────────────────────────────────────────────────────────
    for i, (l, t, r, b) in enumerate(faces):
        pl = int(l*sx); pt = int(t*sy); pr = int(r*sx); pb = int(b*sy)
        if i == 0:
            if not live_ok:
                color = (0, 60, 220); label = f"FAKE: {live_reason}"
            elif mssv:
                color = (0, 220, 80)
                label = f"{name}  {mssv}  d={dist:.3f}"
            else:
                color = (0, 60, 220)
                label = f"UNKNOWN  d={dist:.3f}" if dist else "No match"
        else:
            color = (180, 180, 0); label = "face"
        cv2.rectangle(frame, (pl, pt), (pr, pb), color, 2)
        cv2.rectangle(frame, (pl, pt-22), (pr, pt), color, -1)
        cv2.putText(frame, label, (pl+3, pt-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255,255,255), 1)

    # ── IR thumbnail ──────────────────────────────────────────────────────────
    ir_norm  = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    ir_thumb = cv2.cvtColor(cv2.resize(ir_norm, (120, 120)), cv2.COLOR_GRAY2BGR)
    frame[10:130, PREV[0]-130:PREV[0]-10] = ir_thumb
    thumb_color = (0, 220, 80) if live_ok else (0, 60, 220)
    cv2.rectangle(frame, (PREV[0]-130, 10), (PREV[0]-10, 130), thumb_color, 2)
    cv2.putText(frame, "IR", (PREV[0]-125, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, thumb_color, 1)

    # ── Status bar ────────────────────────────────────────────────────────────
    cv2.rectangle(frame, (0, PREV[1]-26), (PREV[0], PREV[1]), (20,20,20), -1)
    status = (f"Live:{'OK' if live_ok else 'FAKE'}  |  "
              f"Match:{name or 'None'}  |  "
              f"Confirm:{consecutive}/{VERIFY_FRAMES}  |  "
              f"AI:{ai_ms:.0f}ms  |  Q=thoat")
    cv2.putText(frame, status, (6, PREV[1]-7),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (200,200,200), 1)

    # ── Confirm progress bar ──────────────────────────────────────────────────
    bar_h   = 4
    bar_y   = PREV[1] - 26 - bar_h
    bar_pct = min(consecutive / VERIFY_FRAMES, 1.0)
    bar_w   = int(bar_pct * PREV[0])
    bar_col = (0, 220, 80) if consecutive >= VERIFY_FRAMES else (79, 110, 247)
    cv2.rectangle(frame, (0, bar_y), (bar_w, bar_y + bar_h), bar_col, -1)

    return frame


def draw_lockout(remaining: int) -> np.ndarray:
    img = np.zeros((360, 640, 3), dtype=np.uint8)
    cv2.rectangle(img, (0, 0), (640, 360), (0, 0, 160), -1)
    cv2.putText(img, "TAI KHOAN BI KHOA", (90, 150),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 2)
    cv2.putText(img, f"Thu lai sau {remaining} giay", (190, 210),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200,200,200), 1)
    return img


def ui_loop(result_q: queue.Queue, db_map: dict) -> tuple[bool, str | None, str | None]:
    """
    UI loop chạy trên main thread.
    Trả về (passed, mssv, name) khi kết thúc.
    """
    consecutive  = 0
    last_result  = None
    passed       = False
    w_mssv = w_name = None
    last_dist = last_live = None
    aborted  = False

    # FPS tracking
    ui_times   = []
    ai_fps_val = 0.0
    frame_idx  = 0

    print(f"[UI] ✓ Đang chờ camera... nhấn Q để hủy.")
    FRAME_MS = int(1000 / UI_FPS)

    while True:
        t_frame_start = time.perf_counter()

        # ── Lấy kết quả AI mới nhất (không block UI) ─────────────────────────
        try:
            result = result_q.get_nowait()
            last_result = result
            frame_idx  += 1
            # Tính AI FPS
            ui_times.append(time.perf_counter())
            if len(ui_times) > 30:
                ui_times.pop(0)
            if len(ui_times) >= 2:
                ai_fps_val = len(ui_times) / (ui_times[-1] - ui_times[0] + 1e-9)
        except queue.Empty:
            pass

        if last_result is None:
            # Chưa có frame nào — hiển thị màn hình chờ
            blank = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(blank, "Dang khoi dong camera...", (160, 185),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100,100,100), 1)
            cv2.imshow("Verify — Intelligent Locker", blank)
            if cv2.waitKey(FRAME_MS) & 0xFF == ord('q'):
                aborted = True; break
            continue

        # ── Rate limiting ─────────────────────────────────────────────────────
        if w_mssv:
            locked, remaining = is_locked_out(w_mssv)
            if locked:
                cv2.imshow("Verify — Intelligent Locker", draw_lockout(remaining))
                if cv2.waitKey(1000) & 0xFF == ord('q'):
                    aborted = True; break
                continue

        # ── Cập nhật consecutive ──────────────────────────────────────────────
        res = last_result
        all_ok = res["live_ok"] and res["mssv"] is not None

        if all_ok:
            consecutive += 1
            if res["mssv"]: w_mssv = res["mssv"]; w_name = res["name"]
        else:
            consecutive = 0

        last_dist = res["dist"]
        last_live = 1.0 if res["live_ok"] else 0.0

        # ── Vẽ frame ──────────────────────────────────────────────────────────
        frame = draw_overlay(res, consecutive, res["ai_ms"])
        cv2.imshow("Verify — Intelligent Locker", frame)

        # ── PASS ──────────────────────────────────────────────────────────────
        if consecutive >= VERIFY_FRAMES:
            passed = True; break

        # ── waitKey — thời gian còn lại của frame ─────────────────────────────
        elapsed_ms = int((time.perf_counter() - t_frame_start) * 1000)
        wait_ms    = max(1, FRAME_MS - elapsed_ms)
        key = cv2.waitKey(wait_ms) & 0xFF
        if key == ord('q'):
            aborted = True; break

    cv2.destroyAllWindows()

    # ── Ghi audit log ──────────────────────────────────────────────────────────
    log_mssv = w_mssv or "unknown"
    if aborted:
        log_access("VERIFY_ABORT", mssv=log_mssv,
                   live_result="real" if last_live else "fake",
                   face_dist=last_dist, notes="Q bởi người dùng")
    elif passed:
        log_access("VERIFY_PASS", mssv=log_mssv,
                   live_result="real", face_dist=last_dist)
    else:
        log_access("VERIFY_FAIL", mssv=log_mssv,
                   live_result="real" if last_live else "fake",
                   face_dist=last_dist)

    return passed, (w_mssv if passed else None), (w_name if passed else None)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    migrate()

    db_map = load_all_embeddings()
    if not db_map:
        print("[ERR] Chưa có embedding nào. Chạy enroll.py trước!"); return

    print("=== INTELLIGENT LOCKER — XÁC THỰC (Pipeline 3 luồng) ===")
    print(f"    {len(db_map)} user: "
          f"{', '.join(f'{n}({m})' for m,(e,n) in db_map.items())}")
    print(f"    Detector: MediaPipe  |  Embedding: dlib ResNet\n")

    # ── Khởi động các queue ───────────────────────────────────────────────────
    # maxsize=1: AI thread luôn nhận frame MỚI NHẤT, bỏ frame cũ
    frame_q  = queue.Queue(maxsize=1)
    # maxsize=1: UI thread luôn nhận kết quả MỚI NHẤT
    result_q = queue.Queue(maxsize=1)

    # ── Khởi động Thread 1 & 2 ────────────────────────────────────────────────
    cam_thread = CameraThread(frame_q)
    ai_thread  = AIThread(frame_q, result_q, db_map)

    cam_thread.start()
    time.sleep(1.0)    # Chờ camera khởi động
    ai_thread.start()

    # ── Thread 3: UI chạy trên main thread (cv2 yêu cầu main thread) ─────────
    passed, mssv, name = ui_loop(result_q, db_map)

    # ── Dừng threads ─────────────────────────────────────────────────────────
    cam_thread.stop()
    ai_thread.stop()
    cam_thread.join(timeout=3)
    ai_thread.join(timeout=2)

    # ── Kết quả cuối ─────────────────────────────────────────────────────────
    line = "=" * 46
    if passed:
        ok, msg = open_locker(mssv)
        print(f"\n{line}")
        print(f"  ✅  XÁC THỰC THÀNH CÔNG")
        print(f"      {name} ({mssv})")
        print(f"      🔓 {msg}")
        print(f"{line}\n")
    else:
        print(f"\n{line}")
        print(f"  ❌  XÁC THỰC THẤT BẠI")
        print(f"{line}\n")
        if mssv:
            locked, rem = is_locked_out(mssv)
            if locked: print(f"⛔  Bị khóa {rem}s\n")

    from locker_db import print_log
    print_log(5)


if __name__ == "__main__":
    main()