"""
collect_liveness.py — Thu thập dữ liệu IR (polling-based, giống code gốc)
Chạy 2 lần:
  - Lần 1: label="real"  → nhìn thẳng vào camera
  - Lần 2: label="fake"  → giơ ảnh in / màn hình vào camera
"""

import asyncio
import cv2
import numpy as np
import os
import dlib

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

# ── Cấu hình ──────────────────────────────────────────────────────────────────
LABEL         = "fake"          # ← ĐỔI THÀNH "fake" khi chụp ảnh giả mạo
SAVE_DIR      = "liveness_data"
TARGET_COUNT  = 60
IR_GROUP_NAME = "Rts-DMFT-Group"
# ──────────────────────────────────────────────────────────────────────────────

_detector = dlib.get_frontal_face_detector()


# ── Parse (giữ y chang code gốc) ─────────────────────────────────────────────
def parse_bitmap_to_bgr(bmp):
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

def parse_bitmap_to_gray(bmp):
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


# ── DualCatcher — polling, KHÔNG dùng asyncio.Event (giống code gốc) ─────────
class DualCatcher:
    def __init__(self, loop):
        self.color = None
        self.ir    = None
        self.loop  = loop

    def on_color(self, reader, args):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parse_bitmap_to_bgr(ref.video_media_frame.software_bitmap)
                if img is not None:
                    self.color = img
        finally:
            if ref:
                try: ref.close()
                except: pass

    def on_ir(self, reader, args):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parse_bitmap_to_gray(ref.video_media_frame.software_bitmap)
                if img is not None:
                    self.ir = img
        finally:
            if ref:
                try: ref.close()
                except: pass

    async def wait_ir(self, timeout=5.0):
        """Poll mỗi 50ms đến khi có frame IR — y chang code gốc."""
        elapsed = 0.0
        while elapsed < timeout:
            if self.ir is not None:
                return self.ir
            await asyncio.sleep(0.05)
            elapsed += 0.05
        raise asyncio.TimeoutError()


# ── Init camera ───────────────────────────────────────────────────────────────
async def init_cameras():
    groups = await MediaFrameSourceGroup.find_all_async()
    group  = next((g for g in groups if g.display_name == IR_GROUP_NAME), None)
    if group is None:
        raise RuntimeError(f"Không tìm thấy group '{IR_GROUP_NAME}'!")
    print(f"[OK] Camera group: {group.display_name}")

    mc = MediaCapture()
    s  = MediaCaptureInitializationSettings()
    s.source_group      = group
    s.sharing_mode      = 0   # EXCLUSIVE — y chang code gốc
    s.memory_preference = 1
    await mc.initialize_async(s)

    color_src = ir_src = None
    for _, src in mc.frame_sources.items():
        k = int(src.info.source_kind)
        if k == int(MediaFrameSourceKind.COLOR)    and color_src is None: color_src = src
        if k == int(MediaFrameSourceKind.INFRARED) and ir_src    is None: ir_src    = src

    if ir_src is None:
        raise RuntimeError("Không tìm thấy IR source!")
    return mc, color_src, ir_src


# ── ROI ───────────────────────────────────────────────────────────────────────
def extract_roi(ir_img):
    norm = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    dets = _detector(cv2.cvtColor(norm, cv2.COLOR_GRAY2RGB), 1)
    if not dets:
        return None, None
    det = dets[0]
    ih, iw = ir_img.shape[:2]
    l, r = max(0, det.left()), min(iw, det.right())
    t, b = max(0, det.top()),  min(ih, det.bottom())
    if r <= l or b <= t:
        return None, None
    return cv2.resize(norm[t:b, l:r], (64, 64)), (l, t, r, b)


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    save_path = os.path.join(SAVE_DIR, LABEL)
    os.makedirs(save_path, exist_ok=True)
    existing = len([f for f in os.listdir(save_path) if f.endswith(".png")])

    print(f"\n=== THU THẬP DỮ LIỆU IR: label='{LABEL}' ===")
    print(f"Đã có: {existing} ảnh  |  Cần thêm: {max(0, TARGET_COUNT - existing)} ảnh")
    print("→ Nhìn thẳng vào camera" if LABEL == "real"
          else "→ Giơ ảnh in / màn hình vào camera")
    print("Nhấn SPACE để chụp, Q để thoát.\n")

    loop = asyncio.get_running_loop()
    mc, color_src, ir_src = await init_cameras()

    catcher = DualCatcher(loop)

    # Mở cả 2 reader — y chang code gốc
    color_reader = await mc.create_frame_reader_async(color_src)
    ir_reader    = await mc.create_frame_reader_async(ir_src)
    t_color = color_reader.add_frame_arrived(catcher.on_color)
    t_ir    = ir_reader.add_frame_arrived(catcher.on_ir)
    await color_reader.start_async()
    await ir_reader.start_async()
    print("[OK] Readers started...\n")

    count     = existing
    bar_color = (0, 220, 80) if LABEL == "real" else (0, 60, 220)

    try:
        while count < TARGET_COUNT:
            try:
                ir_img = await catcher.wait_ir(timeout=5.0)
            except asyncio.TimeoutError:
                print("  [!] Timeout — thử lại...")
                await asyncio.sleep(0.3)
                continue

            # Preview IR
            norm    = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            preview = cv2.cvtColor(cv2.resize(norm, (480, 480)), cv2.COLOR_GRAY2BGR)

            _, coords = extract_roi(ir_img)
            face_ok = coords is not None
            if face_ok:
                sx, sy = 480 / ir_img.shape[1], 480 / ir_img.shape[0]
                l, t, r, b = coords
                cv2.rectangle(preview,
                              (int(l*sx), int(t*sy)),
                              (int(r*sx), int(b*sy)), bar_color, 2)

            status = (f"[{LABEL.upper()}] {count}/{TARGET_COUNT}"
                      f"  {'[MAT OK]' if face_ok else '[KHONG THAY MAT]'}"
                      f"  SPACE=chup  Q=thoat")
            cv2.rectangle(preview, (0, 0), (480, 26), (20, 20, 20), -1)
            cv2.putText(preview, status, (5, 17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.43, bar_color, 1)

            cv2.imshow("Collect Liveness — IR", preview)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                break

            if key == ord(' '):
                roi, _ = extract_roi(ir_img)
                if roi is None:
                    print("  [!] Không thấy mặt — thử lại")
                    continue
                fname = os.path.join(save_path, f"{count:04d}.png")
                cv2.imwrite(fname, roi)
                count += 1
                print(f"  [✓] {fname}")
                flash = preview.copy()
                cv2.rectangle(flash, (0, 0), (480, 480), bar_color, 8)
                cv2.imshow("Collect Liveness — IR", flash)
                cv2.waitKey(120)

            await asyncio.sleep(0.04)

    finally:
        color_reader.remove_frame_arrived(t_color)
        ir_reader.remove_frame_arrived(t_ir)
        await color_reader.stop_async()
        await ir_reader.stop_async()
        try: color_reader.close()
        except: pass
        try: ir_reader.close()
        except: pass
        cv2.destroyAllWindows()

    print(f"\n[✓] Đã lưu {count} ảnh '{LABEL}' vào '{save_path}'")
    if LABEL == "real":
        print("→ Tiếp theo: đổi LABEL = 'fake' và chạy lại")
    else:
        print("→ Tiếp theo: chạy train_liveness.py")


if __name__ == "__main__":
    asyncio.run(main())