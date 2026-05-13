"""
enroll.py — Đăng ký khuôn mặt vào IntelligentLocker.db
Dùng: python enroll.py <mssv>
      python enroll.py 22146436
"""

import asyncio
import sys
import cv2
import numpy as np

from face_utils  import detect_faces_bgr, extract_embedding, MTCNN_AVAILABLE
from locker_db   import migrate, save_embedding, get_user, log_access

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

ENROLL_SHOTS = 5
PREVIEW_SIZE = (640, 360)


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


class FrameCatcher:
    def __init__(self, loop):
        self.img = None; self.loop = loop; self.event = asyncio.Event()

    def on_frame(self, reader, args):
        if self.event.is_set(): return
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parse_bgr(ref.video_media_frame.software_bitmap)
                if img is not None:
                    self.img = img
                    self.loop.call_soon_threadsafe(self.event.set)
        finally:
            if ref:
                try: ref.close()
                except: pass


async def capture_frame(mc, source, loop, timeout=5.0):
    reader  = await mc.create_frame_reader_async(source)
    catcher = FrameCatcher(loop)
    token   = reader.add_frame_arrived(catcher.on_frame)
    await reader.start_async()
    try:    await asyncio.wait_for(catcher.event.wait(), timeout=timeout)
    except: print("  [✗] Timeout frame")
    finally:
        reader.remove_frame_arrived(token)
        await reader.stop_async()
        try: reader.close()
        except: pass
    return catcher.img


async def init_camera():
    groups = await MediaFrameSourceGroup.find_all_async()
    group  = next(
        (g for g in groups
         if any(int(s.source_kind) == int(MediaFrameSourceKind.COLOR) for s in g.source_infos)),
        None
    )
    if group is None: raise RuntimeError("Không tìm thấy camera COLOR!")
    mc = MediaCapture()
    s  = MediaCaptureInitializationSettings()
    s.source_group = group; s.sharing_mode = 0; s.memory_preference = 1
    await mc.initialize_async(s)
    rgb_src = None
    for _, src in mc.frame_sources.items():
        if int(src.info.source_kind) == int(MediaFrameSourceKind.COLOR):
            rgb_src = src; break
    return mc, rgb_src


async def main():
    migrate()   # Đảm bảo cột face_embedding tồn tại

    # Lấy mssv từ CLI hoặc input
    if len(sys.argv) > 1:
        mssv = sys.argv[1].strip()
    else:
        mssv = input("Nhập MSSV cần đăng ký khuôn mặt: ").strip()

    if not mssv:
        print("[ERR] MSSV không được để trống."); return

    # Kiểm tra user tồn tại trong DB
    user = get_user(mssv)
    if not user:
        print(f"[ERR] MSSV '{mssv}' không tồn tại trong DB!")
        print("      Hãy thêm user qua app chính trước.")
        return

    print(f"\n=== ĐĂNG KÝ KHUÔN MẶT ===")
    print(f"    Tên  : {user['name']}")
    print(f"    MSSV : {mssv}")
    print(f"    Role : {user['role']}  |  Approved: {bool(user['is_approved'])}")
    print(f"    Detector: {'MTCNN' if MTCNN_AVAILABLE else 'dlib HOG'}")
    print(f"\nSẽ chụp {ENROLL_SHOTS} ảnh. SPACE=chụp  Q=hủy\n")

    loop = asyncio.get_running_loop()
    mc, rgb_src = await init_camera()

    embeddings = []
    shot = 0

    while shot < ENROLL_SHOTS:
        img = await capture_frame(mc, rgb_src, loop)
        if img is None:
            await asyncio.sleep(0.3); continue

        faces   = detect_faces_bgr(img)
        preview = cv2.resize(img, PREVIEW_SIZE)
        sx = PREVIEW_SIZE[0] / img.shape[1]
        sy = PREVIEW_SIZE[1] / img.shape[0]

        for l, t, r, b in faces:
            cv2.rectangle(preview,
                          (int(l*sx), int(t*sy)), (int(r*sx), int(b*sy)),
                          (0, 220, 120), 2)

        status = (f"[{user['name']}  {mssv}]  "
                  f"Shot: {shot}/{ENROLL_SHOTS}  SPACE=chup  Q=thoat")
        cv2.rectangle(preview, (0,0), (PREVIEW_SIZE[0], 28), (30,30,30), -1)
        cv2.putText(preview, status, (8, 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255,255,100), 1)

        cv2.imshow(f"Enroll — {user['name']}", preview)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            log_access("ENROLL_ABORT", mssv=mssv, notes="Hủy bởi người dùng")
            print("\n[!] Hủy đăng ký."); break

        if key == ord(' '):
            emb, box = extract_embedding(img)
            if emb is None:
                print("  [!] Không thấy mặt — thử lại"); continue
            embeddings.append(emb)
            shot += 1
            print(f"  [✓] Shot {shot}/{ENROLL_SHOTS}")
            flash = preview.copy()
            cv2.rectangle(flash, (0,0), PREVIEW_SIZE, (0,220,80), 8)
            cv2.imshow(f"Enroll — {user['name']}", flash)
            cv2.waitKey(150)

        await asyncio.sleep(0.05)

    cv2.destroyAllWindows()

    if not embeddings:
        print("\n[ERR] Không có embedding nào. Hủy."); return

    mean_emb = np.mean(embeddings, axis=0)
    ok = save_embedding(mssv, mean_emb)
    if ok:
        log_access("ENROLL", mssv=mssv,
                   notes=f"{len(embeddings)} shots | MTCNN={MTCNN_AVAILABLE}")
        print(f"\n[✓] Đã lưu embedding của '{user['name']}' ({mssv}) "
              f"→ IntelligentLocker.db")


if __name__ == "__main__":
    asyncio.run(main())
