import cv2
import numpy as np
import asyncio
from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

# ==========================================
# PARSER MỚI: lock_buffer → raw memory access
# ==========================================
def parse_bitmap_to_bgr(bmp):
    """NV12 640x360 → BGR dùng lock_buffer"""
    bmp_buf = None
    ref = None
    try:
        w, h = bmp.pixel_width, bmp.pixel_height
        bmp_buf = bmp.lock_buffer(BitmapBufferAccessMode.READ)
        ref = bmp_buf.create_reference()
        arr = np.frombuffer(ref, dtype=np.uint8, count=int(w * h * 1.5)).copy()
        return cv2.cvtColor(arr.reshape(int(h * 1.5), w), cv2.COLOR_YUV2BGR_NV12)
    except Exception as e:
        print(f"[LỖI COLOR] {e}")
        return None
    finally:
        if ref:    ref.close()
        if bmp_buf: bmp_buf.close()

def parse_bitmap_to_gray(bmp):
    """GRAY8 340x340 → numpy grayscale dùng lock_buffer"""
    bmp_buf = None
    ref = None
    try:
        w, h = bmp.pixel_width, bmp.pixel_height
        bmp_buf = bmp.lock_buffer(BitmapBufferAccessMode.READ)
        ref = bmp_buf.create_reference()
        arr = np.frombuffer(ref, dtype=np.uint8, count=w * h).copy()
        return arr.reshape(h, w)
    except Exception as e:
        print(f"[LỖI IR] {e}")
        return None
    finally:
        if ref:    ref.close()
        if bmp_buf: bmp_buf.close()

# ==========================================
# Phần còn lại giữ nguyên
# ==========================================
class FrameCatcher:
    def __init__(self, parser_func, loop):
        self.img = None
        self.parser_func = parser_func
        self.loop = loop
        self.event = asyncio.Event()

    def on_frame(self, reader, args):
        if self.event.is_set():
            return
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                res = self.parser_func(ref.video_media_frame.software_bitmap)
                if res is not None:
                    self.img = res
                    self.loop.call_soon_threadsafe(self.event.set)
        except Exception as e:
            print(f"[CALLBACK LỖI] {e}")
        finally:
            if ref:
                try: ref.close()
                except: pass

async def capture_one_frame(mc, source, parser_func, label, loop, timeout=5.0):
    reader = await mc.create_frame_reader_async(source)
    catcher = FrameCatcher(parser_func, loop)
    token = reader.add_frame_arrived(catcher.on_frame)
    await reader.start_async()
    print(f"  [→] Đang chụp {label}...")
    try:
        await asyncio.wait_for(catcher.event.wait(), timeout=timeout)
        print(f"  [✓] Lấy được {label}.")
    except asyncio.TimeoutError:
        print(f"  [✗] Timeout — không lấy được {label}.")
    finally:
        reader.remove_frame_arrived(token)
        await reader.stop_async()
        try: reader.close()
        except: pass
    return catcher.img

async def main():
    loop = asyncio.get_running_loop()

    groups = await MediaFrameSourceGroup.find_all_async()
    group = next(
        (g for g in groups
         if any(int(s.source_kind) == int(MediaFrameSourceKind.COLOR)    for s in g.source_infos)
         and any(int(s.source_kind) == int(MediaFrameSourceKind.INFRARED) for s in g.source_infos)),
        None
    )
    if group is None:
        print("[ERR] Không tìm thấy group COLOR+IR!")
        return
    print(f"[OK] Dùng group: {group.display_name}")

    mc = MediaCapture()
    settings = MediaCaptureInitializationSettings()
    settings.source_group = group
    settings.sharing_mode = 0
    settings.memory_preference = 1
    await mc.initialize_async(settings)

    rgb_source = ir_source = None
    for _, src in mc.frame_sources.items():
        k = int(src.info.source_kind)
        if k == int(MediaFrameSourceKind.COLOR)    and rgb_source is None: rgb_source = src
        if k == int(MediaFrameSourceKind.INFRARED) and ir_source  is None: ir_source  = src

    print("\n[1/2] Chụp ảnh MÀU...")
    img_color = await capture_one_frame(mc, rgb_source, parse_bitmap_to_bgr, "MÀU", loop)

    print("\n      Chờ sensor ổn định...")
    await asyncio.sleep(0.8)

    print("\n[2/2] Chụp ảnh HỒNG NGOẠI...")
    img_ir = await capture_one_frame(mc, ir_source, parse_bitmap_to_gray, "IR", loop)

    if img_color is not None:
        cv2.imshow("Anh MAU (640x360)", cv2.resize(img_color, (640, 360)))
    if img_ir is not None:
        ir_norm = cv2.normalize(img_ir, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        cv2.imshow("Anh IR (340x340)", ir_norm)
    if img_color is not None or img_ir is not None:
        print("\n[OK] Nhấn phím bất kỳ để đóng.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

if __name__ == "__main__":
    asyncio.run(main())