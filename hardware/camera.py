"""
hardware/camera.py — Camera Backend (Intel RealSense IR + Color, winsdk)

On-Demand: Chỉ bật khi gọi .start(), tắt khi gọi .stop()
→ Tránh nóng máy khi ở màn hình IDLE.

Dùng:
    from hardware.camera import CameraBackend
    cam = CameraBackend()
    cam.start(use_ir=True)   # use_ir=True khi cần liveness check
    color, ir = cam.get()
    cam.stop()
"""

import threading
import asyncio
import time
import cv2
import numpy as np

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

# ── Cấu hình ──────────────────────────────────────────────────────────────────
IR_GROUP_NAME = "Rts-DMFT-Group"   # Display name của Intel RealSense source group


# ── Parse bitmap từ winsdk → numpy ────────────────────────────────────────────

def parse_bgr(bmp) -> np.ndarray | None:
    """Chuyển SoftwareBitmap (NV12) → BGR numpy array."""
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
    """Chuyển SoftwareBitmap (IR 8-bit) → grayscale numpy array."""
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


# ── Camera Backend ─────────────────────────────────────────────────────────────

class CameraBackend:
    """
    Thread-safe camera backend cho Intel RealSense qua winsdk.

    Attributes:
        color : np.ndarray | None  — frame BGR mới nhất
        ir    : np.ndarray | None  — frame IR mới nhất (nếu use_ir=True)
    """

    def __init__(self):
        self.color    = None
        self.ir       = None
        self._lock    = threading.Lock()
        self._active  = False
        self.use_ir   = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self, use_ir: bool = False):
        """
        Bật camera. Gọi được nhiều lần — tự restart nếu cần đổi use_ir.
        """
        if self._active:
            if self.use_ir != use_ir:
                self.stop()
                time.sleep(0.5)
            else:
                return   # Đang chạy đúng mode rồi
        self._active = True
        self.use_ir  = use_ir
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        """Tắt camera, giải phóng hardware."""
        self._active = False
        with self._lock:
            self.color = None
            self.ir    = None

    def get(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        """
        Lấy frame mới nhất (thread-safe).
        Return: (color_bgr, ir_gray)
        """
        with self._lock:
            c = self.color.copy() if self.color is not None else None
            i = self.ir.copy()    if self.ir    is not None else None
        return c, i

    @property
    def is_active(self) -> bool:
        return self._active

    # ── Internal ───────────────────────────────────────────────────────────────

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._loop_cam())
        except Exception as e:
            print(f"[Camera] Lỗi: {e}")
        finally:
            loop.close()

    async def _loop_cam(self):
        groups = await MediaFrameSourceGroup.find_all_async()
        group  = next((g for g in groups if g.display_name == IR_GROUP_NAME), None)
        if not group:
            print(f"[Camera] Không tìm thấy group '{IR_GROUP_NAME}'")
            return

        mc = MediaCapture()
        s  = MediaCaptureInitializationSettings()
        s.source_group    = group
        s.sharing_mode    = 0
        s.memory_preference = 1
        await mc.initialize_async(s)

        cs = ir = None
        for _, src in mc.frame_sources.items():
            k = int(src.info.source_kind)
            if k == int(MediaFrameSourceKind.COLOR)    and not cs: cs = src
            if k == int(MediaFrameSourceKind.INFRARED) and not ir: ir = src

        cr = irr = None
        if cs:
            cr = await mc.create_frame_reader_async(cs)
            cr.add_frame_arrived(lambda r, a: self._on_frame(r, parse_bgr, "color"))
            await cr.start_async()

        if self.use_ir and ir:
            irr = await mc.create_frame_reader_async(ir)
            irr.add_frame_arrived(lambda r, a: self._on_frame(r, parse_gray, "ir"))
            await irr.start_async()

        print("[Camera] ✓ Bật phần cứng")
        while self._active:
            await asyncio.sleep(0.05)

        print("[Camera] Tắt phần cứng (on-demand sleep)")
        if cr:  await cr.stop_async()
        if irr: await irr.stop_async()

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
