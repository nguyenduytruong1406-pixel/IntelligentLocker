"""
enroll.py — Đăng ký khuôn mặt (chạy 1 lần duy nhất)
Chụp N ảnh từ camera COLOR, tính face embedding trung bình, lưu vào face_db.pkl
"""

import asyncio
import cv2
import numpy as np
import pickle
import os
import face_recognition
import dlib

_face_detector   = dlib.get_frontal_face_detector()
_shape_predictor = dlib.shape_predictor(
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages\face_recognition_models\models\shape_predictor_68_face_landmarks.dat"
)
_face_encoder = dlib.face_recognition_model_v1(
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages\face_recognition_models\models\dlib_face_recognition_resnet_model_v1.dat"
)

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

# ── Cấu hình ──────────────────────────────────────────────────────────────────
ENROLL_SHOTS   = 5          # Số ảnh chụp để tính embedding trung bình
DB_PATH        = "face_db.pkl"
PERSON_NAME    = "owner"    # Tên người dùng (thay nếu muốn)
PREVIEW_SIZE   = (640, 360)
# ──────────────────────────────────────────────────────────────────────────────


# ── Camera helpers (giữ nguyên từ code gốc) ───────────────────────────────────
def parse_bitmap_to_bgr(bmp):
    bmp_buf = ref = None
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
        if ref:     ref.close()
        if bmp_buf: bmp_buf.close()


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


async def capture_one_frame(mc, source, loop, timeout=5.0):
    reader = await mc.create_frame_reader_async(source)
    catcher = FrameCatcher(parse_bitmap_to_bgr, loop)
    token = reader.add_frame_arrived(catcher.on_frame)
    await reader.start_async()
    try:
        await asyncio.wait_for(catcher.event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        print("  [✗] Timeout — không lấy được frame.")
    finally:
        reader.remove_frame_arrived(token)
        await reader.stop_async()
        try: reader.close()
        except: pass
    return catcher.img


async def init_camera():
    groups = await MediaFrameSourceGroup.find_all_async()
    group = next(
        (g for g in groups
         if any(int(s.source_kind) == int(MediaFrameSourceKind.COLOR) for s in g.source_infos)),
        None
    )
    if group is None:
        raise RuntimeError("Không tìm thấy camera COLOR!")
    print(f"[OK] Camera: {group.display_name}")

    mc = MediaCapture()
    settings = MediaCaptureInitializationSettings()
    settings.source_group = group
    settings.sharing_mode = 0
    settings.memory_preference = 1
    await mc.initialize_async(settings)

    rgb_source = None
    for _, src in mc.frame_sources.items():
        if int(src.info.source_kind) == int(MediaFrameSourceKind.COLOR):
            rgb_source = src
            break

    return mc, rgb_source
# ──────────────────────────────────────────────────────────────────────────────


def extract_embedding(bgr_img):
    rgb = np.ascontiguousarray(bgr_img[:, :, ::-1])
    dets = _face_detector(rgb, 1)
    if not dets:
        return None
    shape = _shape_predictor(rgb, dets[0])
    # dlib 20.x yêu cầu crop 150x150 trước
    face_chip = dlib.get_face_chip(rgb, shape, size=150)
    emb = _face_encoder.compute_face_descriptor(face_chip)
    return np.array(emb)

async def main():
    loop = asyncio.get_running_loop()
    mc, rgb_source = await init_camera()

    embeddings = []
    shot = 0

    print(f"\n=== ĐĂNG KÝ KHUÔN MẶT: {PERSON_NAME} ===")
    print(f"Sẽ chụp {ENROLL_SHOTS} ảnh. Nhìn thẳng vào camera, nhấn SPACE để chụp, Q để thoát.\n")

    while shot < ENROLL_SHOTS:
        # Chụp preview
        img = await capture_one_frame(mc, rgb_source, loop)
        if img is None:
            print("  Không lấy được frame, thử lại...")
            await asyncio.sleep(0.3)
            continue

        preview = cv2.resize(img, PREVIEW_SIZE)

        # Vẽ hướng dẫn
        status = f"Da chup: {shot}/{ENROLL_SHOTS}  |  SPACE=chup  Q=thoat"
        cv2.rectangle(preview, (0, 0), (PREVIEW_SIZE[0], 30), (30, 30, 30), -1)
        cv2.putText(preview, status, (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 100), 1)

        # Vẽ khung face nếu phát hiện được
        rgb_small = preview[:, :, ::-1]
        locs = face_recognition.face_locations(rgb_small, model="hog")
        for top, right, bottom, left in locs:
            cv2.rectangle(preview, (left, top), (right, bottom), (0, 220, 120), 2)

        cv2.imshow("Enroll — Dang ky khuon mat", preview)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            print("\n[!] Hủy đăng ký.")
            break

        if key == ord(' '):
            emb = extract_embedding(img)
            if emb is None:
                print(f"  [!] Shot {shot+1}: Không thấy mặt — thử lại.")
                continue
            embeddings.append(emb)
            shot += 1
            print(f"  [✓] Shot {shot}/{ENROLL_SHOTS} — OK")
            # Flash xanh lá báo chụp thành công
            flash = preview.copy()
            cv2.rectangle(flash, (0, 0), (PREVIEW_SIZE[0], PREVIEW_SIZE[1]), (0, 220, 80), 8)
            cv2.imshow("Enroll — Dang ky khuon mat", flash)
            cv2.waitKey(150)

        await asyncio.sleep(0.05)

    cv2.destroyAllWindows()

    if not embeddings:
        print("\n[ERR] Không có embedding nào được lưu.")
        return

    # Tính embedding trung bình → bền hơn 1 ảnh đơn lẻ
    mean_embedding = np.mean(embeddings, axis=0)

    # Load DB cũ (nếu có) rồi ghi thêm/ghi đè người này
    db = {}
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            db = pickle.load(f)

    db[PERSON_NAME] = mean_embedding

    with open(DB_PATH, "wb") as f:
        pickle.dump(db, f)

    print(f"\n[✓] Đã lưu embedding của '{PERSON_NAME}' vào '{DB_PATH}'")
    print(f"    ({len(embeddings)} ảnh → 1 vector 128-D)")


if __name__ == "__main__":
    asyncio.run(main())
