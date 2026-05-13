"""
verify.py — Xác thực khuôn mặt (phiên bản bảo mật)
+ AES-256 DB mã hóa
+ Audit log mỗi lần xác thực
+ Rate limiting: khóa sau 5 lần thất bại
"""

import asyncio
import cv2
import numpy as np
import dlib

from secure_db import load_face_db, log_event, is_locked_out

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

# ── Cấu hình ──────────────────────────────────────────────────────────────────
PERSON_NAME   = "owner"
THRESHOLD     = 0.45
VERIFY_FRAMES = 3
PREVIEW_SIZE  = (640, 360)
# ──────────────────────────────────────────────────────────────────────────────

_face_detector   = dlib.get_frontal_face_detector()
_shape_predictor = dlib.shape_predictor(
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages\face_recognition_models\models\shape_predictor_68_face_landmarks.dat"
)
_face_encoder = dlib.face_recognition_model_v1(
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages\face_recognition_models\models\dlib_face_recognition_resnet_model_v1.dat"
)


# ── Camera ────────────────────────────────────────────────────────────────────
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


class ContinuousCatcher:
    def __init__(self, loop):
        self.img   = None
        self.loop  = loop
        self._ready = asyncio.Event()

    def on_frame(self, reader, args):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parse_bitmap_to_bgr(ref.video_media_frame.software_bitmap)
                if img is not None:
                    self.img = img
                    self.loop.call_soon_threadsafe(self._ready.set)
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
    group  = next(
        (g for g in groups
         if any(int(s.source_kind) == int(MediaFrameSourceKind.COLOR) for s in g.source_infos)),
        None
    )
    if group is None:
        raise RuntimeError("Không tìm thấy camera COLOR!")

    mc       = MediaCapture()
    settings = MediaCaptureInitializationSettings()
    settings.source_group      = group
    settings.sharing_mode      = 0
    settings.memory_preference = 1
    await mc.initialize_async(settings)

    rgb_source = None
    for _, src in mc.frame_sources.items():
        if int(src.info.source_kind) == int(MediaFrameSourceKind.COLOR):
            rgb_source = src
            break
    return mc, rgb_source


# ── Face recognition ──────────────────────────────────────────────────────────
def compare_face(bgr_img, known_embedding):
    rgb  = np.ascontiguousarray(bgr_img[:, :, ::-1])
    dets = _face_detector(rgb, 1)
    if not dets:
        return None, False, None

    h, w   = bgr_img.shape[:2]
    cx, cy = w // 2, h // 2
    best   = min(dets, key=lambda d: ((d.left()+d.right())/2-cx)**2
                                    +((d.top()+d.bottom())/2-cy)**2)

    shape     = _shape_predictor(rgb, best)
    face_chip = dlib.get_face_chip(rgb, shape, size=150)
    emb       = np.array(_face_encoder.compute_face_descriptor(face_chip))
    dist      = float(np.linalg.norm(emb - known_embedding))
    loc       = (best.top(), best.right(), best.bottom(), best.left())
    return dist, dist <= THRESHOLD, loc


def draw_result(frame, loc, distance, is_match, consecutive):
    preview = cv2.resize(frame, PREVIEW_SIZE)
    sx = PREVIEW_SIZE[0] / frame.shape[1]
    sy = PREVIEW_SIZE[1] / frame.shape[0]

    if loc is not None:
        top, right, bottom, left = loc
        top    = int(top*sy);  bottom = int(bottom*sy)
        left   = int(left*sx); right  = int(right*sx)
        color  = (0, 220, 80) if is_match else (0, 60, 220)
        cv2.rectangle(preview, (left, top), (right, bottom), color, 2)
        label = f"{'PASS' if is_match else 'FAIL'}  dist={distance:.3f}"
        cv2.rectangle(preview, (left, top-24), (right, top), color, -1)
        cv2.putText(preview, label, (left+4, top-6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

    bar_h = 28
    cv2.rectangle(preview, (0, PREVIEW_SIZE[1]-bar_h),
                  (PREVIEW_SIZE[0], PREVIEW_SIZE[1]), (20,20,20), -1)
    if distance is not None:
        pct      = max(0.0, 1.0 - distance / THRESHOLD)
        bar_w    = int(pct * PREVIEW_SIZE[0])
        bar_col  = (0,200,80) if is_match else (0,80,200)
        cv2.rectangle(preview, (0, PREVIEW_SIZE[1]-bar_h),
                      (bar_w, PREVIEW_SIZE[1]), bar_col, -1)
    status = (f"Xac nhan: {consecutive}/{VERIFY_FRAMES}"
              if distance is not None else "Khong thay mat — nhin thang vao camera")
    cv2.putText(preview, status, (8, PREVIEW_SIZE[1]-8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    return preview


# ── Verify loop ───────────────────────────────────────────────────────────────
async def verify_once(mc, rgb_source, known_embedding, loop,
                      show_window=True, max_attempts=120) -> bool:
    catcher = ContinuousCatcher(loop)
    reader  = await mc.create_frame_reader_async(rgb_source)
    token   = reader.add_frame_arrived(catcher.on_frame)
    await reader.start_async()

    consecutive = 0
    result      = False
    last_dist   = None

    try:
        for _ in range(max_attempts):
            try:
                img = await catcher.wait_frame(timeout=3.0)
            except asyncio.TimeoutError:
                print("  [!] Timeout frame")
                break

            dist, is_match, loc = compare_face(img, known_embedding)
            last_dist = dist

            consecutive = consecutive + 1 if is_match else 0

            if show_window:
                preview = draw_result(img, loc, dist, is_match, consecutive)
                cv2.imshow(f"Verify — {PERSON_NAME}", preview)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    log_event("VERIFY_ABORT", person=PERSON_NAME,
                              face_dist=last_dist, notes="Q bởi người dùng")
                    break

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

    # Ghi audit log
    if result:
        log_event("VERIFY_PASS", person=PERSON_NAME, face_dist=last_dist)
    else:
        log_event("VERIFY_FAIL", person=PERSON_NAME, face_dist=last_dist)

    return result


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print("=== XÁC THỰC KHUÔN MẶT (bảo mật) ===\n")

    # ── Kiểm tra rate limiting trước ─────────────────────────────────────────
    locked, remaining = is_locked_out(PERSON_NAME)
    if locked:
        print(f"⛔  Tài khoản '{PERSON_NAME}' bị khóa do nhiều lần thất bại.")
        print(f"   Thử lại sau {remaining} giây.")
        log_event("VERIFY_ABORT", person=PERSON_NAME,
                  notes=f"Bị khóa, còn {remaining}s")
        return

    # ── Load DB mã hóa ────────────────────────────────────────────────────────
    db = load_face_db()
    if PERSON_NAME not in db:
        print(f"[ERR] Chưa có dữ liệu '{PERSON_NAME}'. Chạy enroll.py trước!")
        return

    known_embedding = db[PERSON_NAME]
    print(f"[OK] Đã load embedding của '{PERSON_NAME}' (từ DB mã hóa)")
    print(f"     Threshold={THRESHOLD}  |  Cần {VERIFY_FRAMES} frame liên tiếp")
    print(f"     Nhìn vào camera... nhấn Q để hủy.\n")

    loop = asyncio.get_running_loop()
    mc, rgb_source = await init_camera()

    passed = await verify_once(mc, rgb_source, known_embedding, loop,
                               show_window=True, max_attempts=120)

    line = "=" * 42
    if passed:
        print(f"\n{line}\n  ✅  XÁC THỰC THÀNH CÔNG — ĐĂNG NHẬP OK\n{line}\n")
    else:
        # Kiểm tra lại xem có bị khóa sau lần fail này không
        locked, remaining = is_locked_out(PERSON_NAME)
        print(f"\n{line}\n  ❌  XÁC THỰC THẤT BẠI — TỪ CHỐI ĐĂNG NHẬP\n{line}")
        if locked:
            print(f"\n⛔  Tài khoản bị khóa {remaining}s do nhiều lần thất bại liên tiếp.\n")


if __name__ == "__main__":
    asyncio.run(main())
