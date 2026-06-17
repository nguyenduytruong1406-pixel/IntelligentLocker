"""
ai/ai_utils.py — Face AI utilities: liveness check, landmarks, embedding

Dùng:
    from ai.ai_utils import liveness, landmarks, embedding, ir_to_bgr, hash_password

Thay đổi so với phiên bản cũ:
    - Thêm ir_to_bgr() để convert IR grayscale → BGR giả
    - landmarks() và embedding() vẫn nhận BGR như cũ — không đổi signature
    - face_worker.py sẽ truyền ir_to_bgr(ir) thay vì color khi IR available
"""

import hashlib
import cv2
import numpy as np
import dlib

from ai.models import shape_pred, face_encoder
from ai.face_utils import center_face

# ── IR → BGR helper ───────────────────────────────────────────────────────────

def ir_to_bgr(ir_img: np.ndarray) -> np.ndarray:
    """
    Convert IR grayscale → BGR giả để feed vào dlib / MediaPipe.

    dlib ResNet và BlazeFace đều expect 3-channel.
    Duplicate channel: 3 channel giống nhau, model vẫn hoạt động bình thường
    vì chỉ cần độ tương phản và cấu trúc hình học, không cần màu thật.

    Args:
        ir_img: grayscale numpy array (H, W) từ IR camera

    Return:
        BGR numpy array (H, W, 3)
    """
    return cv2.cvtColor(ir_img, cv2.COLOR_GRAY2BGR)


# ── Liveness (IR Rule-based) ──────────────────────────────────────────────────

# Ngưỡng liveness — điều chỉnh trong môi trường thực tế
BRIGHT_THRESHOLD = 220   # IR mean > → phản quang giả
DARK_THRESHOLD   = 30    # IR mean < → quá tối
TEXTURE_MIN      = 8.0   # IR std  < → không có texture (ảnh phẳng)

def liveness(ir_img: np.ndarray) -> tuple[bool, str]:
    """
    Kiểm tra liveness qua IR camera (rule-based, không cần GPU).

    Args:
        ir_img: grayscale numpy array từ IR camera

    Return:
        (True, "REAL")         — khuôn mặt thật
        (False, lý do)         — fake / không xác định
    """
    if ir_img is None:
        return False, "Chờ IR..."

    norm = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    box  = center_face(cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR))
    if not box:
        return False, "Không thấy mặt (IR)"

    l, t, r, b = box
    roi        = norm[t:b, l:r]
    m, s       = float(np.mean(roi)), float(np.std(roi))

    if m > BRIGHT_THRESHOLD: return False, "Ánh sáng quá mạnh"
    if m < DARK_THRESHOLD:   return False, "Quá tối"
    if s < TEXTURE_MIN:      return False, "Không có texture"

    return True, "REAL"


# ── Landmarks (dlib 68 điểm) ──────────────────────────────────────────────────

def landmarks(img: np.ndarray):
    """
    Detect 68 landmarks từ ảnh BGR (color hoặc ir_to_bgr).

    Return:
        (shape, dlib.rectangle) nếu tìm thấy mặt
        (None, None)            nếu không có mặt
    """
    box = center_face(img)
    if not box:
        return None, None

    l, t, r, b = box
    det        = dlib.rectangle(l, t, r, b)
    rgb        = np.ascontiguousarray(img[:, :, ::-1])
    shape      = shape_pred(rgb, det)
    return shape, det


# ── Embedding (dlib ResNet 128-D) ─────────────────────────────────────────────

def embedding(img: np.ndarray, shape) -> np.ndarray:
    """
    Tính face embedding 128-D từ ảnh BGR (color hoặc ir_to_bgr) và dlib shape.

    Return: numpy array shape (128,)
    """
    rgb  = np.ascontiguousarray(img[:, :, ::-1])
    chip = dlib.get_face_chip(rgb, shape, size=150)
    return np.array(face_encoder.compute_face_descriptor(chip))


# ── Auth helpers ──────────────────────────────────────────────────────────────

def hash_password(pw: str) -> str:
    """SHA-256 hash mật khẩu."""
    return hashlib.sha256(pw.encode()).hexdigest()