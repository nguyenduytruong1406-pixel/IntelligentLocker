"""
hardware/camera.py — Camera Backend, port trực tiếp từ main_gui.py

start(use_ir)  → bật color + IR(nếu cần), chỉ gọi khi vào verify/enroll
stop()         → set _running=False, loop asyncio tự dọn dẹp hardware
get()          → lấy frame mới nhất
"""

import threading
import asyncio
import cv2
import numpy as np

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

IR_GROUP_NAME = "Rts-DMFT-Group"


def parse_bgr(bmp) -> np.ndarray | None:
    bmp_buf = ref = None
    try:
        w, h    = bmp.pixel_width, bmp.pixel_height
        bmp_buf = bmp.lock_buffer(BitmapBufferAccessMode.READ)
        ref     = bmp_buf.create_reference()
        arr     = np.frombuffer(ref, dtype=np.uint8, count=int(w * h * 1.5)).copy()
        return cv2.cvtColor(arr.reshape(int(h * 1.5), w), cv2.COLOR_YUV2BGR_NV12)
    except:
        return None
    finally:
        if ref:     ref.close()
        if bmp_buf: bmp_buf.close()


def parse_gray(bmp) -> np.ndarray | None:
    bmp_buf = ref = None
    try:
        w, h    = bmp.pixel_width, bmp.pixel_height
        bmp_buf = bmp.lock_buffer(BitmapBufferAccessMode.READ)
        ref     = bmp_buf.create_reference()
        arr     = np.frombuffer(ref, dtype=np.uint8, count=w * h).copy()
        return arr.reshape(h, w)
    except:
        return None
    finally:
        if ref:     ref.close()
        if bmp_buf: bmp_buf.close()


class CameraBackend:
    def __init__(self):
        self.color       = None
        self.ir          = None
        self._lock       = threading.Lock()
        self._loop       = None
        self._running    = False
        self._thread     = None
        self._ir_reader  = None
        self._ir_running = False   # IR đang chạy hay không
        self._use_ir     = False   # IR có được yêu cầu không

    def start(self, use_ir: bool = False):
        """Bật camera. Nếu đang chạy với use_ir khác thì stop trước rồi start lại."""
        if self._running:
            if self._use_ir == use_ir:
                return   # đang chạy đúng mode
            self.stop()
            # chờ thread cũ thoát hẳn
            if self._thread:
                self._thread.join(timeout=3.0)
        self._use_ir  = use_ir
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """
        Tắt camera — chỉ set _running=False.
        Asyncio loop tự thoát khỏi while loop và cleanup hardware.
        KHÔNG gọi loop.stop() từ ngoài để tránh deadlock.
        """
        self._running = False
        with self._lock:
            self.color = None
            self.ir    = None

    def get(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        with self._lock:
            c = self.color.copy() if self.color is not None else None
            i = self.ir.copy()    if self.ir    is not None else None
        return c, i

    @property
    def is_active(self) -> bool:
        return self._running

    # ── Internal ───────────────────────────────────────────────────────────────

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._camera_loop())
        except Exception as e:
            print(f"[Camera] Lỗi: {e}")
        # KHÔNG close loop ở đây — để GC dọn

    async def _camera_loop(self):
        groups = await MediaFrameSourceGroup.find_all_async()
        group  = next((g for g in groups if g.display_name == IR_GROUP_NAME), None)
        if not group:
            print(f"[Camera] Không tìm thấy group '{IR_GROUP_NAME}'")
            return

        mc = MediaCapture()
        s  = MediaCaptureInitializationSettings()
        s.source_group      = group
        s.sharing_mode      = 0
        s.memory_preference = 1
        await mc.initialize_async(s)

        color_src = ir_src = None
        for _, src in mc.frame_sources.items():
            k = int(src.info.source_kind)
            if k == int(MediaFrameSourceKind.COLOR)    and not color_src: color_src = src
            if k == int(MediaFrameSourceKind.INFRARED) and not ir_src:    ir_src    = src

        # Color reader — luôn bật
        cr = await mc.create_frame_reader_async(color_src)
        cr.add_frame_arrived(lambda r, a: self._on_frame(r, parse_bgr, "color"))
        await cr.start_async()

        # IR reader — tạo sẵn, bật ngay nếu use_ir=True
        ir = None
        if ir_src:
            ir = await mc.create_frame_reader_async(ir_src)
            self._ir_reader = ir
            ir.add_frame_arrived(lambda r, a: self._on_frame(r, parse_gray, "ir"))
            if self._use_ir:
                await ir.start_async()
                self._ir_running = True

        print(f"[Camera] ✓ Bật (IR={'ON' if self._ir_running else 'OFF'})")

        # Chạy cho đến khi stop() set _running=False
        while self._running:
            await asyncio.sleep(0.033)

        # Dọn dẹp hardware — y hệt main_gui
        print("[Camera] Đang tắt...")
        await cr.stop_async()
        if self._ir_running and ir:
            await ir.stop_async()
            self._ir_running = False
        self._ir_reader = None
        print("[Camera] Đã tắt")

    def _on_frame(self, reader, parser, attr: str):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parser(ref.video_media_frame.software_bitmap)
                if img is not None:
                    with self._lock:
                        setattr(self, attr, img)
        finally:
            if ref: ref.close()