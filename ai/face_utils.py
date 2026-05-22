"""
ai/face_utils.py — Detection layer dùng MediaPipe BlazeFace.

Chỉ lo detect bounding box.
Embedding & matching nằm ở ai_utils.py (dùng dlib qua ai.models).
"""

import os
import urllib.request

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# ── BlazeFace model ───────────────────────────────────────────────────────────
# Tìm file .tflite theo thứ tự:
#   1. Cùng thư mục với file này  (ai/blaze_face_short_range.tflite)
#   2. Thư mục gốc project        (thư mục cha của ai/)
#   3. Tải về thư mục gốc project nếu chưa có

_HERE    = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.dirname(_HERE)
_FNAME   = "blaze_face_short_range.tflite"
_URL     = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_detector/blaze_face_short_range/float16/1/"
    "blaze_face_short_range.tflite"
)

def _find_or_download_model() -> str:
    for candidate in [os.path.join(_HERE, _FNAME), os.path.join(_ROOT, _FNAME)]:
        if os.path.isfile(candidate):
            return candidate
    # Không tìm thấy → tải về thư mục gốc project
    dest = os.path.join(_ROOT, _FNAME)
    print(f"[face_utils] Đang tải BlazeFace model → {dest}")
    urllib.request.urlretrieve(_URL, dest)
    print("[face_utils] Tải xong!")
    return dest

_MODEL_PATH  = _find_or_download_model()
_base_opts   = mp_python.BaseOptions(model_asset_path=_MODEL_PATH)
_det_opts    = mp_vision.FaceDetectorOptions(
    base_options=_base_opts,
    min_detection_confidence=0.7,
)
_mp_detector = mp_vision.FaceDetector.create_from_options(_det_opts)


# ── Public API ────────────────────────────────────────────────────────────────

def detect_faces_bgr(bgr_img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """
    Detect tất cả khuôn mặt trong ảnh BGR.

    Return: list[(left, top, right, bottom)] sắp xếp theo diện tích giảm dần.
    """
    rgb_img  = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_img)
    result   = _mp_detector.detect(mp_image)

    h, w  = bgr_img.shape[:2]
    faces = []
    for det in result.detections:
        bbox = det.bounding_box
        l = max(0, bbox.origin_x)
        t = max(0, bbox.origin_y)
        r = min(w, bbox.origin_x + bbox.width)
        b = min(h, bbox.origin_y + bbox.height)
        if r > l and b > t:
            faces.append((l, t, r, b))

    faces.sort(key=lambda x: (x[2] - x[0]) * (x[3] - x[1]), reverse=True)
    return faces


def center_face(bgr_img: np.ndarray) -> tuple[int, int, int, int] | None:
    """
    Trả về bounding box của khuôn mặt gần tâm ảnh nhất.
    Return None nếu không detect được mặt nào.
    """
    faces = detect_faces_bgr(bgr_img)
    if not faces:
        return None

    h, w   = bgr_img.shape[:2]
    cx, cy = w / 2, h / 2

    def _dist(box):
        l, t, r, b = box
        return ((l + r) / 2 - cx) ** 2 + ((t + b) / 2 - cy) ** 2

    return min(faces, key=_dist)