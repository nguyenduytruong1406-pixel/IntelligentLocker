"""
ai/ai_utils.py — Face AI utilities: liveness check, landmarks, embedding

Dùng:
    from ai.ai_utils import liveness, landmarks, embedding, hash_password
"""

import hashlib
import cv2
import numpy as np
import dlib

from ai.models import shape_pred, face_encoder
from ai.face_utils import center_face

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
    Detect 68 landmarks từ ảnh BGR.

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
    Tính face embedding 128-D từ ảnh BGR và dlib shape.

    Return: numpy array shape (128,)
    """
    rgb  = np.ascontiguousarray(img[:, :, ::-1])
    chip = dlib.get_face_chip(rgb, shape, size=150)
    return np.array(face_encoder.compute_face_descriptor(chip))


# ── Auth helpers ──────────────────────────────────────────────────────────────

def hash_password(pw: str) -> str:
    """SHA-256 hash mật khẩu."""
    return hashlib.sha256(pw.encode()).hexdigest()
