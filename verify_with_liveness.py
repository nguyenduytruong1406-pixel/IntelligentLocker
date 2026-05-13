"""
verify_with_liveness.py — Xác thực khuôn mặt + IR liveness → mở tủ
Pipeline: Rate limit → IR liveness → MTCNN detect → 1:N match → mở/gán tủ
"""

import asyncio
import cv2
import numpy as np

from face_utils     import detect_faces_bgr, embedding_from_box, MTCNN_AVAILABLE
from liveness_check import check_liveness_ir
from locker_db      import (migrate, load_all_embeddings, is_locked_out,
                             log_access, open_locker, get_user_locker)

from winsdk.windows.media.capture import MediaCapture, MediaCaptureInitializationSettings
from winsdk.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode

THRESHOLD     = 0.45
VERIFY_FRAMES = 3
IR_GROUP_NAME = "Rts-DMFT-Group"


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


class DualCatcher:
    def __init__(self, loop):
        self.color = None; self.ir = None; self.loop = loop

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
            await asyncio.sleep(0.05); elapsed += 0.05
        raise asyncio.TimeoutError()


async def init_cameras():
    groups = await MediaFrameSourceGroup.find_all_async()
    group  = next((g for g in groups if g.display_name == IR_GROUP_NAME), None)
    if group is None: raise RuntimeError(f"Không tìm thấy '{IR_GROUP_NAME}'!")
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


def match_1n(embedding, db_map, threshold):
    """db_map = {mssv: (emb, name)}. Trả về (mssv, name, dist) hoặc (None,None,dist)."""
    best_mssv = best_name = None
    best_dist = float("inf")
    for mssv, (emb, name) in db_map.items():
        d = float(np.linalg.norm(embedding - emb))
        if d < best_dist:
            best_dist = d; best_mssv = mssv; best_name = name
    if best_dist <= threshold:
        return best_mssv, best_name, best_dist
    return None, None, best_dist


def draw_overlay(color_img, ir_img, faces, mssv, name, dist,
                 live_ok, live_reason, consecutive, locker_info):
    PREV    = (640, 360)
    preview = cv2.resize(color_img, PREV)
    sx, sy  = PREV[0]/color_img.shape[1], PREV[1]/color_img.shape[0]

    for i, (l, t, r, b) in enumerate(faces):
        pl,pt,pr,pb = int(l*sx),int(t*sy),int(r*sx),int(b*sy)
        if i == 0:
            if not live_ok:
                color = (0,60,220); label = f"FAKE:{live_reason}"
            elif mssv:
                color = (0,220,80)
                label = f"{name}  {mssv}  d={dist:.3f}"
            else:
                color = (0,60,220); label = f"UNKNOWN  d={dist:.3f}"
        else:
            color = (180,180,0); label = "face"
        cv2.rectangle(preview, (pl,pt), (pr,pb), color, 2)
        cv2.rectangle(preview, (pl,pt-22), (pr,pt), color, -1)
        cv2.putText(preview, label, (pl+3,pt-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255,255,255), 1)

    # IR thumbnail
    ir_n = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    thumb = cv2.cvtColor(cv2.resize(ir_n,(120,120)), cv2.COLOR_GRAY2BGR)
    preview[10:130, PREV[0]-130:PREV[0]-10] = thumb
    tc = (0,220,80) if live_ok else (0,60,220)
    cv2.rectangle(preview,(PREV[0]-130,10),(PREV[0]-10,130),tc,2)
    cv2.putText(preview,"IR",(PREV[0]-125,25),cv2.FONT_HERSHEY_SIMPLEX,0.45,tc,1)

    # Locker info
    if locker_info:
        lk_str = f"Tủ #{locker_info['locker_id']} ({locker_info['status']})"
        cv2.putText(preview, lk_str, (PREV[0]-128,150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200,200,80), 1)

    # Status bar
    cv2.rectangle(preview,(0,PREV[1]-24),(PREV[0],PREV[1]),(20,20,20),-1)
    status = (f"Live:{'OK' if live_ok else 'FAKE'}  "
              f"Match:{name or 'None'}  "
              f"Confirm:{consecutive}/{VERIFY_FRAMES}  Q=thoat")
    cv2.putText(preview, status, (6,PREV[1]-7),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (200,200,200), 1)
    return preview


def draw_lockout(remaining):
    img = np.zeros((360,640,3),dtype=np.uint8)
    cv2.rectangle(img,(0,0),(640,360),(0,0,160),-1)
    cv2.putText(img,"TAI KHOAN BI KHOA",(90,150),
                cv2.FONT_HERSHEY_SIMPLEX,1.0,(255,255,255),2)
    cv2.putText(img,f"Thu lai sau {remaining} giay",(190,210),
                cv2.FONT_HERSHEY_SIMPLEX,0.7,(200,200,200),1)
    return img


async def verify_once(mc, color_src, ir_src, db_map, loop,
                      max_attempts=120) -> tuple[bool, str|None, str|None]:
    """Trả về (passed, mssv, name)."""
    catcher = DualCatcher(loop)
    color_reader = await mc.create_frame_reader_async(color_src)
    ir_reader    = await mc.create_frame_reader_async(ir_src)
    t_color = color_reader.add_frame_arrived(catcher.on_color)
    t_ir    = ir_reader.add_frame_arrived(catcher.on_ir)
    await color_reader.start_async()
    await ir_reader.start_async()

    consecutive = 0; result = False
    w_mssv = w_name = None
    last_dist = last_live = None
    aborted = False

    try:
        for _ in range(max_attempts):
            if w_mssv:
                locked, remaining = is_locked_out(w_mssv)
                if locked:
                    cv2.imshow("Verify", draw_lockout(remaining))
                    if cv2.waitKey(1000) & 0xFF == ord('q'):
                        aborted = True; break
                    continue

            try:
                color_img, ir_img = await catcher.wait_both(timeout=3.0)
            except asyncio.TimeoutError:
                print("  [!] Timeout"); break

            live_ok, live_reason = check_liveness_ir(ir_img)
            last_live = 1.0 if live_ok else 0.0

            faces = detect_faces_bgr(color_img)
            mssv = name = dist = None

            if live_ok and faces:
                emb = embedding_from_box(color_img, faces[0])
                if emb is not None:
                    mssv, name, dist = match_1n(emb, db_map, THRESHOLD)
                    last_dist = dist
                    if mssv: w_mssv = mssv; w_name = name

            locker_info = get_user_locker(w_mssv) if w_mssv else None

            all_ok = live_ok and mssv is not None
            consecutive = consecutive + 1 if all_ok else 0

            preview = draw_overlay(color_img, ir_img, faces,
                                   mssv, name, dist,
                                   live_ok, live_reason,
                                   consecutive, locker_info)
            cv2.imshow("Verify — Intelligent Locker", preview)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                aborted = True; break

            if consecutive >= VERIFY_FRAMES:
                result = True; break

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

    log_mssv = w_mssv or "unknown"
    ev = "VERIFY_ABORT" if aborted else ("VERIFY_PASS" if result else "VERIFY_FAIL")
    log_access(ev, mssv=log_mssv, face_dist=last_dist,
               live_result="real" if last_live else "fake")

    return result, (w_mssv if result else None), (w_name if result else None)


async def main():
    migrate()

    db_map = load_all_embeddings()
    if not db_map:
        print("[ERR] Chưa có embedding nào. Chạy enroll.py trước!"); return

    print("=== INTELLIGENT LOCKER — XÁC THỰC ===")
    print(f"    {len(db_map)} user đã đăng ký: "
          f"{', '.join(f'{n} ({m})' for m,(e,n) in db_map.items())}")
    print(f"    Detector: {'MTCNN' if MTCNN_AVAILABLE else 'dlib HOG'}\n")

    loop = asyncio.get_running_loop()
    mc, color_src, ir_src = await init_cameras()

    passed, mssv, name = await verify_once(mc, color_src, ir_src, db_map, loop)

    line = "=" * 46
    if passed:
        ok, msg = open_locker(mssv)
        print(f"\n{line}")
        print(f"  ✅  XÁC THỰC THÀNH CÔNG")
        print(f"      {name} ({mssv})")
        print(f"      🔓 {msg}")
        print(f"{line}\n")
    else:
        print(f"\n{line}")
        print(f"  ❌  XÁC THỰC THẤT BẠI")
        print(f"{line}\n")
        if w := (mssv or "unknown"):
            locked, rem = is_locked_out(w)
            if locked: print(f"⛔  Bị khóa {rem}s\n")

    from locker_db import print_log
    print_log(5)


if __name__ == "__main__":
    asyncio.run(main())
