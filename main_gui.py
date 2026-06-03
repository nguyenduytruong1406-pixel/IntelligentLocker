"""
main_gui.py — Intelligent Locker: Giao diện chuẩn Windows Hello
Kiến trúc:
  1. Luồng Camera (Asyncio): Chụp ảnh liên tục.
  2. Luồng UI (Tkinter): Hiển thị và vẽ Landmark (MediaPipe).
  3. Luồng AI (Threading): Giải toán ResNet nặng nề ở phía sau.

FIX LOG:
  - sync_listener.start() chạy trên daemon thread (không block main thread)
  - _on_success có guard _verify_done chống gọi lặp
  - open_locker() chạy trên background thread
  - get_embedding_only() chạy trên background thread (_emb_busy flag)
  - _on_cancel() reset đầy đủ state
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import asyncio
import cv2
import numpy as np
import dlib
import os
import subprocess

# ── Firebase listener: PHẢI chạy trên daemon thread, KHÔNG được block main thread ──
import sync_listener
threading.Thread(target=sync_listener.start, daemon=True).start()

from PIL import Image, ImageTk

subprocess.Popen(["py", "-3.11", "sync_tool.py"],
                 creationflags=subprocess.CREATE_NO_WINDOW)

# Import các module nội bộ
from core.db import migrate
from core.user_db import load_all_embeddings, get_user, save_embedding
from core.locker_db import open_locker
from core.log_db import log_access
from ai.face_utils import center_face
from ai.models import shape_pred as _shape_pred, face_encoder as _face_encoder

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

IR_GROUP_NAME       = "Rts-DMFT-Group"
THRESHOLD           = 0.45
TARGET_SETUP_FRAMES = 20
VERIFY_FRAMES       = 6

C = {
    "bg": "#0f1117", "surface": "#1a1d27", "border": "#2e3150",
    "accent": "#4f6ef7", "green": "#22c55e", "red": "#ef4444",
    "yellow": "#fbbf24", "text": "#e2e8f0", "muted": "#64748b",
}

# ══════════════════════════════════════════════════════════════════════════════
#  CAMERA BACKEND
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
        if ref: ref.close()
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
        if ref: ref.close()
        if bmp_buf: bmp_buf.close()

class CameraBackend:
    def __init__(self):
        self.color = None; self.ir = None
        self._lock       = threading.Lock()
        self._loop       = None
        self._running    = False
        self._thread     = None
        self._ir_reader  = None
        self._ir_running = False

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_ir_state(self, enabled: bool):
        if self._loop and self._ir_reader:
            asyncio.run_coroutine_threadsafe(self._toggle_ir(enabled), self._loop)

    async def _toggle_ir(self, enabled: bool):
        if enabled and not self._ir_running:
            await self._ir_reader.start_async()
            self._ir_running = True
        elif not enabled and self._ir_running:
            await self._ir_reader.stop_async()
            self._ir_running = False
            with self._lock: self.ir = None

    def get_frames(self):
        with self._lock:
            c = self.color.copy() if self.color is not None else None
            i = self.ir.copy()    if self.ir    is not None else None
        return c, i

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try: self._loop.run_until_complete(self._camera_loop())
        except Exception as e: print(f"[Camera] {e}")

    async def _camera_loop(self):
        groups = await MediaFrameSourceGroup.find_all_async()
        group  = next((g for g in groups if g.display_name == IR_GROUP_NAME), None)
        if not group: return
        mc = MediaCapture(); s = MediaCaptureInitializationSettings()
        s.source_group = group; s.sharing_mode = 0; s.memory_preference = 1
        await mc.initialize_async(s)
        color_src = ir_src = None
        for _, src in mc.frame_sources.items():
            k = int(src.info.source_kind)
            if k == int(MediaFrameSourceKind.COLOR)    and not color_src: color_src = src
            if k == int(MediaFrameSourceKind.INFRARED) and not ir_src:    ir_src    = src
        cr = await mc.create_frame_reader_async(color_src)
        ir = await mc.create_frame_reader_async(ir_src)
        self._ir_reader = ir
        cr.add_frame_arrived(lambda r, a: self._handle_frame(r, parse_bgr,  "color"))
        ir.add_frame_arrived(lambda r, a: self._handle_frame(r, parse_gray, "ir"))
        await cr.start_async()
        while self._running: await asyncio.sleep(0.05)
        await cr.stop_async()
        if self._ir_running: await ir.stop_async()

    def _handle_frame(self, reader, parser, attr):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parser(ref.video_media_frame.software_bitmap)
                if img is not None:
                    with self._lock: setattr(self, attr, img)
        except Exception as e:
            print(f"[Camera] _handle_frame({attr}): {e}")
        finally:
            try:
                if ref: ref.close()
            except: pass

    def stop(self):
        self._running = False
        if self._loop: self._loop.call_soon_threadsafe(self._loop.stop)

# ══════════════════════════════════════════════════════════════════════════════
#  AI HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def fast_liveness_check(ir_img):
    norm = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    box = center_face(cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR))
    if not box: return False, "No face (IR)"
    l, t, r, b = box
    roi = norm[t:b, l:r]
    mean, std = np.mean(roi), np.std(roi)
    if mean > 220: return False, "Overexposed"
    if mean < 30:  return False, "Too dark"
    if std < 8.0:  return False, "No texture"
    return True, "REAL"

def get_landmarks_only(img):
    box = center_face(img)
    if not box: return None, None
    l, t, r, b = box
    det   = dlib.rectangle(l, t, r, b)
    shape = _shape_pred(np.ascontiguousarray(img[:, :, ::-1]), det)
    return shape, det

def get_embedding_only(img, shape):
    rgb       = np.ascontiguousarray(img[:, :, ::-1])
    face_chip = dlib.get_face_chip(rgb, shape, size=150)
    return np.array(_face_encoder.compute_face_descriptor(face_chip))

# ══════════════════════════════════════════════════════════════════════════════
#  GIAO DIỆN CHÍNH
# ══════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    MODE_IDLE, MODE_SETUP, MODE_VERIFY = "idle", "setup", "verify"

    def __init__(self):
        super().__init__()
        self.title("🔐 Intelligent Locker")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.mode     = self.MODE_IDLE
        self.cam      = CameraBackend()
        self.db_map   = {}

        # Setup state
        self._setup_mssv    = None
        self._setup_frames  = []
        self._capture_done  = False

        # Verify state
        self._verify_consec = 0
        self._verify_winner = None
        self._verify_done   = False   # GUARD: chặn _on_success gọi lặp
        self._emb_busy      = False   # GUARD: chặn embedding chạy song song

        self._build_ui()
        migrate()
        self._reload_db()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.cam.start()
        self._update_loop()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.canvas = tk.Canvas(self, width=640, height=400, bg="black", highlightthickness=0)
        self.canvas.grid(row=0, column=0, rowspan=4, padx=16, pady=16)

        panel = tk.Frame(self, bg=C["bg"], width=260)
        panel.grid(row=0, column=1, padx=(0,16), pady=16, sticky="n")

        tk.Label(panel, text="SMART LOCKER", bg=C["bg"], fg=C["accent"],
                 font=("Segoe UI", 18, "bold")).pack()

        self.lbl_status = tk.Label(panel, text="Sẵn sàng", bg=C["surface"], fg=C["text"],
                                   font=("Segoe UI", 11), wraplength=230, pady=12)
        self.lbl_status.pack(fill="x", pady=10)

        self.progress = ttk.Progressbar(panel, length=230, mode="determinate")
        self.progress.pack(pady=10)

        self.btn_setup = tk.Button(panel, text="⚙ THIẾT LẬP", bg="#1e3a5f", fg=C["accent"],
                                   font=("Segoe UI", 12, "bold"), command=self._on_setup)
        self.btn_setup.pack(fill="x", pady=5)

        self.btn_verify = tk.Button(panel, text="🔍 XÁC THỰC", bg="#14532d", fg=C["green"],
                                    font=("Segoe UI", 12, "bold"), command=self._on_verify)
        self.btn_verify.pack(fill="x", pady=5)

        self.btn_cancel = tk.Button(panel, text="Hủy", command=self._on_cancel)

        self.lbl_users = tk.Label(panel, text="Đã đăng ký:", bg=C["bg"],
                                  fg=C["muted"], justify="left")
        self.lbl_users.pack(anchor="w", pady=10)

    # ── Điều hướng mode ───────────────────────────────────────────────────────
    def _on_closing(self):
        print("\n[System] Đang dọn dẹp và tắt hệ thống...")
        self.cam.stop()
        self.destroy()
        import os; os._exit(0)

    def _on_setup(self):
        mssv = simpledialog.askstring("Thiết lập", "Nhập MSSV:")
        if not mssv or not get_user(mssv.strip()): return
        self._setup_mssv   = mssv.strip()
        self._setup_frames = []
        self._capture_done = False
        self.mode = self.MODE_SETUP
        self.btn_cancel.pack(fill="x")
        self._set_status(f"Đang thiết lập cho {mssv}...", C["accent"])

    def _on_verify(self):
        if not self.db_map: return
        self.cam.set_ir_state(True)
        self._verify_consec = 0
        self._verify_done   = False
        self._emb_busy      = False
        self.mode           = self.MODE_VERIFY
        self.btn_cancel.pack(fill="x")

    def _on_cancel(self):
        self.mode           = self.MODE_IDLE
        self._verify_done   = False
        self._emb_busy      = False
        self._verify_consec = 0
        self.cam.set_ir_state(False)
        self.btn_cancel.pack_forget()
        self.progress["value"] = 0

    def _set_status(self, text, color=None):
        self.lbl_status.config(text=text, fg=color or C["text"])

    # ── Frame loop ────────────────────────────────────────────────────────────
    def _update_loop(self):
        c, i = self.cam.get_frames()
        if c is not None:
            self._process_frame(c, i)
        self.after(30, self._update_loop)

    def _process_frame(self, color_img, ir_img):
        frame       = color_img.copy()
        shape, det  = get_landmarks_only(frame)

        if self.mode == self.MODE_SETUP and shape and not self._capture_done:
            self._setup_frames.append((frame.copy(), shape))
            pct = int(len(self._setup_frames) / TARGET_SETUP_FRAMES * 100)
            self.progress["value"] = pct
            self._draw_overlay(frame, shape, det, C["accent"])
            if len(self._setup_frames) >= TARGET_SETUP_FRAMES:
                self._capture_done = True
                self._set_status("Đang mã hóa...", C["yellow"])
                threading.Thread(target=self._background_ai_setup, daemon=True).start()

        elif self.mode == self.MODE_VERIFY and shape and not self._verify_done:
            live_ok, reason = (fast_liveness_check(ir_img)
                               if ir_img is not None else (False, "Loading IR..."))
            if live_ok:
                # Chạy embedding trên background thread, mỗi lần 1 thread duy nhất
                if not self._emb_busy:
                    self._emb_busy = True
                    threading.Thread(
                        target=self._background_verify,
                        args=(frame.copy(), shape),
                        daemon=True
                    ).start()
                color = C["green"] if self._verify_consec > 0 else C["yellow"]
                self._draw_overlay(frame, shape, det, color)
            else:
                self._verify_consec = 0
                self._set_status(reason, C["red"])

        elif shape:
            self._draw_overlay(frame, shape, det, C["muted"])

        self._show_frame(frame)

    # ── Background workers ────────────────────────────────────────────────────
    def _background_verify(self, frame, shape):
        """Tính embedding + match trên background thread."""
        try:
            emb = get_embedding_only(frame, shape)
            res = self._match(emb)
        except Exception as e:
            print(f"[Verify] Lỗi: {e}")
            res = (None, None)
        finally:
            self._emb_busy = False
        # Trả kết quả về main thread an toàn
        self.after(0, lambda: self._on_verify_result(res))

    def _on_verify_result(self, res):
        """Nhận kết quả từ background, cập nhật state trên main thread."""
        if self.mode != self.MODE_VERIFY or self._verify_done:
            return
        if res[0]:
            self._verify_consec += 1
            self._set_status(f"Nhận diện... ({self._verify_consec}/{VERIFY_FRAMES})", C["green"])
            if self._verify_consec >= VERIFY_FRAMES:
                self._verify_done = True      # ← GUARD: đặt trước khi làm gì khác
                self._on_success(res[0], res[1])
        else:
            self._verify_consec = 0

    def _background_ai_setup(self):
        embs = [get_embedding_only(f, s) for f, s in self._setup_frames]
        save_embedding(self._setup_mssv, np.mean(embs, axis=0))
        self.after(0, self._setup_finish)

    def _setup_finish(self):
        self._reload_db()
        self._on_cancel()
        self._set_status("Thiết lập thành công!", C["green"])

    def _on_success(self, mssv, name):
        """Mở tủ trên background thread để không block UI."""
        self._set_status(f"Chào {name}! Đang mở tủ...", C["green"])
        self._on_cancel()
        threading.Thread(target=open_locker, args=(mssv,), daemon=True).start()
        self.after(600, lambda: self._set_status(f"✅ Chào {name}! Đã mở tủ.", C["green"]))

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _match(self, emb):
        best_m, best_n, best_d = None, None, 1.0
        for m, (e, n) in self.db_map.items():
            d = np.linalg.norm(emb - e)
            if d < best_d: best_m, best_n, best_d = m, n, d
        return (best_m, best_n) if best_d < THRESHOLD else (None, None)

    def _draw_overlay(self, frame, shape, det, hex_color):
        c         = hex_color.lstrip("#")
        color_bgr = tuple(int(c[i:i+2], 16) for i in (4, 2, 0))
        for i in range(68):
            cv2.circle(frame, (shape.part(i).x, shape.part(i).y), 2, color_bgr, -1)
        cv2.rectangle(frame, (det.left(), det.top()), (det.right(), det.bottom()), color_bgr, 2)

    def _show_frame(self, bgr):
        rgb = cv2.cvtColor(cv2.resize(bgr, (640, 400)), cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb))
        if not hasattr(self, '_img_id'):
            self._img_id = self.canvas.create_image(0, 0, anchor="nw", image=img)
        else:
            self.canvas.itemconfig(self._img_id, image=img)
        self.canvas.image = img

    def _reload_db(self):
        self.db_map = load_all_embeddings()
        self.lbl_users.config(
            text="Đã đăng ký:\n" + "\n".join([f"• {n}" for m, (e, n) in self.db_map.items()])
        )

if __name__ == "__main__":
    App().mainloop()