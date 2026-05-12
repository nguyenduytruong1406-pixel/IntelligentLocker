"""
liveness_check.py — Rule-based IR liveness (không cần train)

Logic:
  1. Không detect mặt trong IR  → FAKE (màn hình hấp thụ IR)
  2. ROI quá sáng (mean > 220)  → FAKE (ảnh in bóng phản xạ IR)
  3. ROI quá tối  (mean <  30)  → FAKE (che camera / không có người)
  4. Còn lại                    → REAL

Import vào verify.py:
    from liveness_check import check_liveness_ir
"""

import cv2
import numpy as np
import dlib

_detector = dlib.get_frontal_face_detector()

# ── Ngưỡng (tuỳ chỉnh nếu cần) ───────────────────────────────────────────────
BRIGHT_THRESHOLD = 220   # > giá trị này → ảnh bóng (quá trắng)
DARK_THRESHOLD   =  30   # < giá trị này → quá tối
TEXTURE_MIN      =  8.0  # std dev tối thiểu — ảnh thật có texture, ảnh trắng/đen không có
# ──────────────────────────────────────────────────────────────────────────────


def check_liveness_ir(ir_img) -> tuple[bool, str]:
    """
    Kiểm tra liveness từ ảnh IR grayscale (numpy array HxW uint8).

    Returns:
        (is_real: bool, reason: str)
    """
    norm = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

    # ── Bước 1: Detect mặt ────────────────────────────────────────────────────
    rgb  = cv2.cvtColor(norm, cv2.COLOR_GRAY2RGB)
    dets = _detector(rgb, 1)

    if not dets:
        return False, "no_face"          # màn hình / không có người

    # Lấy ROI mặt lớn nhất
    det = max(dets, key=lambda d: (d.right()-d.left()) * (d.bottom()-d.top()))
    ih, iw = norm.shape
    l = max(0,  det.left())
    r = min(iw, det.right())
    t = max(0,  det.top())
    b = min(ih, det.bottom())
    roi = norm[t:b, l:r]

    if roi.size == 0:
        return False, "no_face"

    mean = float(np.mean(roi))
    std  = float(np.std(roi))

    # ── Bước 2: Kiểm tra độ sáng và texture ──────────────────────────────────
    if mean > BRIGHT_THRESHOLD:
        return False, f"too_bright(mean={mean:.0f})"   # ảnh in bóng

    if mean < DARK_THRESHOLD:
        return False, f"too_dark(mean={mean:.0f})"     # bị che / tối

    if std < TEXTURE_MIN:
        return False, f"no_texture(std={std:.1f})"     # ảnh phẳng không có texture

    return True, f"real(mean={mean:.0f},std={std:.1f})"


def get_ir_face_roi(ir_img):
    """Trả về (roi 64x64, coords) hoặc (None, None) nếu không detect được."""
    norm = cv2.normalize(ir_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    dets = _detector(cv2.cvtColor(norm, cv2.COLOR_GRAY2RGB), 1)
    if not dets:
        return None, None
    det = max(dets, key=lambda d: (d.right()-d.left()) * (d.bottom()-d.top()))
    ih, iw = norm.shape
    l, r = max(0, det.left()), min(iw, det.right())
    t, b = max(0, det.top()),  min(ih, det.bottom())
    if r <= l or b <= t:
        return None, None
    return cv2.resize(norm[t:b, l:r], (64, 64)), (l, t, r, b)
