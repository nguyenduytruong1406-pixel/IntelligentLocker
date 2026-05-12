"""
verify.py — Xác thực khuôn mặt (1:1 verification)
Chụp ảnh từ camera COLOR, so embedding với face_db.pkl → PASS / FAIL
Có thể import hàm verify_once() vào project khác để tích hợp login.
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
DB_PATH        = "face_db.pkl"
PERSON_NAME    = "owner"        # Phải khớp với enroll.py
THRESHOLD      = 0.45           # Khoảng cách tối đa (0.0=giống hệt, 0.6=ngưỡng thư viện)
                                # 0.45 chặt hơn mặc định → ít false-positive
VERIFY_FRAMES  = 3              # Cần pass liên tiếp N frame → tránh false-positive
PREVIEW_SIZE   = (640, 360)
# ──────────────────────────────────────────────────────────────────────────────


# ── Camera helpers ─────────────────────────────────────────────────────────────
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


class ContinuousCatcher:
    """Liên tục nhận frame mới nhất từ camera."""
    def __init__(self, parser_func, loop):
        self.img = None
        self.parser_func = parser_func
        self.loop = loop
        self._ready = asyncio.Event()

    def on_frame(self, reader, args):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                res = self.parser_func(ref.video_media_frame.software_bitmap)
                if res is not None:
                    self.img = res
                    self.loop.call_soon_threadsafe(self._ready.set)
        except Exception as e:
            print(f"[CALLBACK LỖI] {e}")
        finally:
            if ref:
                try: ref.close()
                except: pass

    async def wait_frame(self, timeout=3.0):
        self._ready.clear()
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        return self.img


async def init_camera():
    groups = await MediaFrameSourceGroup.find_all_async()
    group = next(
        (g for g in groups
         if any(int(s.source_kind) == int(MediaFrameSourceKind.COLOR) for s in g.source_infos)),
        None
    )
    if group is None:
        raise RuntimeError("Không tìm thấy camera COLOR!")

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


def load_db():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Không tìm thấy '{DB_PATH}'. Hãy chạy enroll.py trước!"
        )
    with open(DB_PATH, "rb") as f:
        return pickle.load(f)


def compare_face(bgr_img, known_embedding, threshold=THRESHOLD):
    rgb = np.ascontiguousarray(bgr_img[:, :, ::-1])
    dets = _face_detector(rgb, 1)
    if not dets:
        return None, False, None

    h, w = bgr_img.shape[:2]
    cx, cy = w // 2, h // 2
    best_det, best_dist_center = None, float('inf')
    for det in dets:
        face_cx = (det.left() + det.right()) / 2
        face_cy = (det.top()  + det.bottom()) / 2
        d = ((face_cx - cx)**2 + (face_cy - cy)**2) ** 0.5
        if d < best_dist_center:
            best_dist_center = d
            best_det = det

    shape     = _shape_predictor(rgb, best_det)
    face_chip = dlib.get_face_chip(rgb, shape, size=150)
    emb       = np.array(_face_encoder.compute_face_descriptor(face_chip))

    distance = np.linalg.norm(emb - known_embedding)
    is_match = bool(distance <= threshold)
    loc = (best_det.top(), best_det.right(), best_det.bottom(), best_det.left())
    return float(distance), is_match, loc


def draw_result(frame, loc, distance, is_match, consecutive, total_needed):
    """Vẽ overlay kết quả lên frame."""
    preview = cv2.resize(frame, PREVIEW_SIZE)
    scale_x = PREVIEW_SIZE[0] / frame.shape[1]
    scale_y = PREVIEW_SIZE[1] / frame.shape[0]

    if loc is not None:
        top, right, bottom, left = loc
        top    = int(top    * scale_y)
        bottom = int(bottom * scale_y)
        left   = int(left   * scale_x)
        right  = int(right  * scale_x)

        color = (0, 220, 80) if is_match else (0, 60, 220)
        cv2.rectangle(preview, (left, top), (right, bottom), color, 2)

        label = f"{'PASS' if is_match else 'FAIL'}  dist={distance:.3f}"
        cv2.rectangle(preview, (left, top - 24), (right, top), color, -1)
        cv2.putText(preview, label, (left + 4, top - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    # Thanh tiến trình phía dưới
    bar_h = 28
    cv2.rectangle(preview, (0, PREVIEW_SIZE[1] - bar_h),
                  (PREVIEW_SIZE[0], PREVIEW_SIZE[1]), (20, 20, 20), -1)

    if distance is not None:
        pct = max(0.0, 1.0 - distance / THRESHOLD)
        bar_w = int(pct * PREVIEW_SIZE[0])
        bar_color = (0, 200, 80) if is_match else (0, 80, 200)
        cv2.rectangle(preview,
                      (0, PREVIEW_SIZE[1] - bar_h),
                      (bar_w, PREVIEW_SIZE[1]),
                      bar_color, -1)

    status = (f"Xac nhan: {consecutive}/{total_needed}"
              if distance is not None else "Khong thay mat — nhin thang vao camera")
    cv2.putText(preview, status, (8, PREVIEW_SIZE[1] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    return preview


# ── Hàm chính có thể import vào project khác ──────────────────────────────────
async def verify_once(mc, rgb_source, known_embedding, loop,
                      show_window=True, max_attempts=60) -> bool:
    """
    Chạy vòng lặp xác thực. Trả về True nếu PASS, False nếu FAIL/timeout.
    show_window=False để dùng headless (không cần màn hình).
    """
    catcher = ContinuousCatcher(parse_bitmap_to_bgr, loop)
    reader = await mc.create_frame_reader_async(rgb_source)
    token = reader.add_frame_arrived(catcher.on_frame)
    await reader.start_async()

    consecutive = 0
    attempts    = 0
    result      = False

    try:
        while attempts < max_attempts:
            try:
                img = await catcher.wait_frame(timeout=3.0)
            except asyncio.TimeoutError:
                print("  [!] Timeout frame")
                break

            distance, is_match, loc = compare_face(img, known_embedding)

            if is_match:
                consecutive += 1
            else:
                consecutive = 0   # Reset nếu frame không khớp

            if show_window:
                preview = draw_result(img, loc, distance, is_match,
                                      consecutive, VERIFY_FRAMES)
                cv2.imshow(f"Verify — Xac thuc: {PERSON_NAME}", preview)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break

            attempts += 1

            # PASS khi đủ N frame liên tiếp
            if consecutive >= VERIFY_FRAMES:
                result = True
                break

            await asyncio.sleep(0.05)

    finally:
        reader.remove_frame_arrived(token)
        await reader.stop_async()
        try: reader.close()
        except: pass
        if show_window:
            cv2.destroyAllWindows()

    return result


async def main():
    print("=== XÁC THỰC KHUÔN MẶT ===\n")

    db = load_db()
    if PERSON_NAME not in db:
        print(f"[ERR] Chưa có dữ liệu của '{PERSON_NAME}'. Chạy enroll.py trước!")
        return

    known_embedding = db[PERSON_NAME]
    print(f"[OK] Đã load embedding của '{PERSON_NAME}'")
    print(f"     Threshold: {THRESHOLD}  |  Cần {VERIFY_FRAMES} frame liên tiếp")
    print(f"     Nhìn vào camera... nhấn Q để hủy.\n")

    loop = asyncio.get_running_loop()
    mc, rgb_source = await init_camera()

    passed = await verify_once(mc, rgb_source, known_embedding, loop,
                               show_window=True, max_attempts=120)

    # ── Kết quả cuối ──────────────────────────────────────────────────────────
    line = "=" * 40
    if passed:
        print(f"\n{line}")
        print("  ✅  XÁC THỰC THÀNH CÔNG — ĐĂNG NHẬP OK")
        print(f"{line}\n")
    else:
        print(f"\n{line}")
        print("  ❌  XÁC THỰC THẤT BẠI — TỪ CHỐI ĐĂNG NHẬP")
        print(f"{line}\n")

    # Ở đây bạn có thể gọi hàm login / mở khóa / trigger event tiếp theo
    # Ví dụ: if passed: open_session()


if __name__ == "__main__":
    asyncio.run(main())
