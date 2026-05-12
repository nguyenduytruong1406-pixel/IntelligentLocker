"""
verify_with_liveness.py — Xác thực khuôn mặt + kiểm tra liveness IR
Pipeline: IR liveness check → face recognition → PASS / FAIL
"""

import asyncio
import cv2
import numpy as np
import pickle
import os
import dlib

from liveness_check import check_liveness_ir, get_ir_face_roi

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

# ── Cấu hình ──────────────────────────────────────────────────────────────────
DB_PATH        = "face_db.pkl"
PERSON_NAME    = "owner"
THRESHOLD      = 0.45
VERIFY_FRAMES  = 3        # Cần N frame liên tiếp PASS cả liveness lẫn face
IR_GROUP_NAME  = "Rts-DMFT-Group"
# ──────────────────────────────────────────────────────────────────────────────

_face_detector   = dlib.get_frontal_face_detector()
_shape_predictor = dlib.shape_predictor(
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages\face_recognition_models\models\shape_predictor_68_face_landmarks.dat"
)
_face_encoder = dlib.face_recognition_model_v1(
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages\face_recognition_models\models\dlib_face_recognition_resnet_model_v1.dat"
)


# ── Parse ─────────────────────────────────────────────────────────────────────
def parse_bgr(bmp):
    bmp_buf = ref = None
    try:
        w, h = bmp.pixel_width, bmp.pixel_height
        bmp_buf = bmp.lock_buffer(BitmapBufferAccessMode.READ)
        ref = bmp_buf.create_reference()
        arr = np.frombuffer(ref, dtype=np.uint8, count=int(w * h * 1.5)).copy()
        return cv2.cvtColor(arr.reshape(int(h * 1.5), w), cv2.COLOR_YUV2BGR_NV12)
    except: return None
    finally:
        if ref: ref.close()
        if bmp_buf: bmp_buf.close()

def parse_gray(bmp):
    bmp_buf = ref = None
    try:
        w, h = bmp.pixel_width, bmp.pixel_height
        bmp_buf = bmp.lock_buffer(BitmapBufferAccessMode.READ)
        ref = bmp_buf.create_reference()
        arr = np.frombuffer(ref, dtype=np.uint8, count=w * h).copy()
        return arr.reshape(h, w)
    except: return None
    finally:
        if ref: ref.close()
        if bmp_buf: bmp_buf.close()


# ── DualCatcher (polling) ─────────────────────────────────────────────────────
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
                img = parse_bgr(ref.video_media_frame.software_bitmap)
                if img is not None: self.color = img
        finally:
            if ref:
                try: ref.close()
                except: pass

    def on_ir(self, reader, args):
        ref = None
        try:
            ref = reader.try_acquire_latest_frame()
            if ref and ref.video_media_frame and ref.video_media_frame.software_bitmap:
                img = parse_gray(ref.video_media_frame.software_bitmap)
                if img is not None: self.ir = img
        finally:
            if ref:
                try: ref.close()
                except: pass

    async def wait_both(self, timeout=5.0):
        elapsed = 0.0
        while elapsed < timeout:
            if self.color is not None and self.ir is not None:
                return self.color, self.ir
            await asyncio.sleep(0.05)
            elapsed += 0.05
        raise asyncio.TimeoutError()


# ── Camera ────────────────────────────────────────────────────────────────────
async def init_cameras():
    groups = await MediaFrameSourceGroup.find_all_async()
    group  = next((g for g in groups if g.display_name == IR_GROUP_NAME), None)
    if group is None:
        raise RuntimeError(f"Không tìm thấy group '{IR_GROUP_NAME}'!")

    mc = MediaCapture()
    s  = MediaCaptureInitializationSettings()
    s.source_group = group; s.sharing_mode = 0; s.memory_preference = 1
    await mc.initialize_async(s)

    color_src = ir_src = None
    for _, src in mc.frame_sources.items():
        k = int(src.info.source_kind)
        if k == int(MediaFrameSourceKind.COLOR)    and color_src is None: color_src = src
        if k == int(MediaFrameSourceKind.INFRARED) and ir_src    is None: ir_src    = src

    return mc, color_src, ir_src


# ── Face recognition trên COLOR ───────────────────────────────────────────────
def compare_face(bgr_img, known_emb):
    rgb  = np.ascontiguousarray(bgr_img[:, :, ::-1])
    dets = _face_detector(rgb, 1)
    if not dets: return None, False, None

    # Mặt gần tâm nhất
    h, w = bgr_img.shape[:2]
    cx, cy = w//2, h//2
    best = min(dets, key=lambda d: ((d.left()+d.right())/2-cx)**2
                                  +((d.top()+d.bottom())/2-cy)**2)

    shape     = _shape_predictor(rgb, best)
    face_chip = dlib.get_face_chip(rgb, shape, size=150)
    emb       = np.array(_face_encoder.compute_face_descriptor(face_chip))
    dist      = float(np.linalg.norm(emb - known_emb))
    loc       = (best.top(), best.right(), best.bottom(), best.left())
    return dist, dist <= THRESHOLD, loc


# ── Overlay UI ────────────────────────────────────────────────────────────────
def draw_overlay(color_img, ir_img, loc, dist, face_ok,
                 live_ok, live_reason, consecutive):
    PREV = (640, 360)
    preview = cv2.resize(color_img, PREV)
    sx = PREV[0] / color_img.shape[1]
    sy = PREV[1] / color_img.shape[0]

    # Khung mặt
    if loc:
        top, right, bottom, left = loc
        top    = int(top*sy);  bottom = int(bottom*sy)
        left   = int(left*sx); right  = int(right*sx)
        all_ok = face_ok and live_ok
        color  = (0,220,80) if all_ok else (0,60,220)
        cv2.rectangle(preview, (left,top), (right,bottom), color, 2)

        tag = []
        if not live_ok: tag.append(f"FAKE:{live_reason}")
        elif not face_ok: tag.append(f"FACE_FAIL d={dist:.3f}")
        else: tag.append(f"OK d={dist:.3f}")
        label = " | ".join(tag)
        cv2.rectangle(preview, (left, top-22), (right, top), color, -1)
        cv2.putText(preview, label, (left+3, top-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255,255,255), 1)

    # IR thumbnail (góc phải)
    ir_norm  = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    ir_thumb = cv2.cvtColor(cv2.resize(ir_norm, (120, 120)), cv2.COLOR_GRAY2BGR)
    preview[10:130, PREV[0]-130:PREV[0]-10] = ir_thumb
    cv2.rectangle(preview, (PREV[0]-130,10), (PREV[0]-10,130),
                  (0,220,80) if live_ok else (0,60,220), 2)
    cv2.putText(preview, "IR", (PREV[0]-125, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0,220,80) if live_ok else (0,60,220), 1)

    # Status bar
    cv2.rectangle(preview, (0, PREV[1]-26), (PREV[0], PREV[1]), (20,20,20), -1)
    status = (f"Liveness: {'REAL' if live_ok else 'FAKE'}  |"
              f"  Face: {'PASS' if face_ok else 'FAIL'}  |"
              f"  Confirm: {consecutive}/{VERIFY_FRAMES}  |  Q=thoat")
    cv2.putText(preview, status, (6, PREV[1]-8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200,200,200), 1)
    return preview


# ── Verify loop ───────────────────────────────────────────────────────────────
async def verify_once(mc, color_src, ir_src, known_emb, loop,
                      max_attempts=120) -> bool:
    catcher = DualCatcher(loop)

    color_reader = await mc.create_frame_reader_async(color_src)
    ir_reader    = await mc.create_frame_reader_async(ir_src)
    t_color = color_reader.add_frame_arrived(catcher.on_color)
    t_ir    = ir_reader.add_frame_arrived(catcher.on_ir)
    await color_reader.start_async()
    await ir_reader.start_async()

    consecutive = 0
    result      = False

    try:
        for _ in range(max_attempts):
            try:
                color_img, ir_img = await catcher.wait_both(timeout=3.0)
            except asyncio.TimeoutError:
                print("  [!] Timeout frame")
                break

            # ── Liveness check (IR) ───────────────────────────────────────
            live_ok, live_reason = check_liveness_ir(ir_img)

            # ── Face recognition (COLOR) ──────────────────────────────────
            dist = face_ok = loc = None
            if live_ok:
                dist, face_ok, loc = compare_face(color_img, known_emb)

            all_ok = live_ok and face_ok

            if all_ok:
                consecutive += 1
            else:
                consecutive = 0

            # UI
            preview = draw_overlay(color_img, ir_img, loc,
                                   dist, face_ok, live_ok, live_reason,
                                   consecutive)
            cv2.imshow(f"Verify — {PERSON_NAME}", preview)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            if consecutive >= VERIFY_FRAMES:
                result = True
                break

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

    return result


async def main():
    print("=== XÁC THỰC KHUÔN MẶT + LIVENESS ===\n")

    if not os.path.exists(DB_PATH):
        print(f"[ERR] Không tìm thấy '{DB_PATH}'. Chạy enroll.py trước!")
        return

    with open(DB_PATH, "rb") as f:
        db = pickle.load(f)

    if PERSON_NAME not in db:
        print(f"[ERR] Chưa có dữ liệu của '{PERSON_NAME}'.")
        return

    known_emb = db[PERSON_NAME]
    print(f"[OK] Đã load embedding của '{PERSON_NAME}'")
    print(f"     Threshold={THRESHOLD} | Frames={VERIFY_FRAMES} | Q=hủy\n")

    loop = asyncio.get_running_loop()
    mc, color_src, ir_src = await init_cameras()

    passed = await verify_once(mc, color_src, ir_src, known_emb, loop)

    line = "=" * 42
    if passed:
        print(f"\n{line}\n  ✅  XÁC THỰC THÀNH CÔNG — ĐĂNG NHẬP OK\n{line}\n")
    else:
        print(f"\n{line}\n  ❌  XÁC THỰC THẤT BẠI — TỪ CHỐI\n{line}\n")


if __name__ == "__main__":
    asyncio.run(main())
