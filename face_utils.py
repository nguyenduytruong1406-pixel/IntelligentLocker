"""
face_utils.py — Module dùng chung (ĐÃ TỐI ƯU HÓA TẦNG DETECTION)
- Detection: Dùng Google MediaPipe (Siêu nhanh trên CPU, nhạy với mặt nghiêng)
- Embedding: Dlib ResNet 128-D (Giữ nguyên để tương thích Database)
"""

import numpy as np
import cv2
import dlib
import mediapipe as mp

# ══════════════════════════════════════════════════════════════════════════════
#  1. KHỞI TẠO CÁC MÔ HÌNH (MODELS)
# ══════════════════════════════════════════════════════════════════════════════
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import urllib.request, os

# Tự tải model nếu chưa có
_MODEL_PATH = "blaze_face_short_range.tflite"
if not os.path.exists(_MODEL_PATH):
    print("[face_utils] Đang tải BlazeFace model...")
    urllib.request.urlretrieve(
        "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
        _MODEL_PATH
    )
    print("[face_utils] Tải xong!")

_base_opts   = mp_python.BaseOptions(model_asset_path=_MODEL_PATH)
_det_opts    = mp_vision.FaceDetectorOptions(
    base_options=_base_opts,
    min_detection_confidence=0.7
)
_mp_detector = mp_vision.FaceDetector.create_from_options(_det_opts)

# --- Khởi tạo Dlib cho Embedding (Giữ nguyên đường dẫn của bạn) ---
_SHAPE_MODEL = (
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    r"\face_recognition_models\models\shape_predictor_68_face_landmarks.dat"
)
_RECOG_MODEL = (
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    r"\face_recognition_models\models\dlib_face_recognition_resnet_model_v1.dat"
)

try:
    _shape_pred   = dlib.shape_predictor(_SHAPE_MODEL)
    _face_encoder = dlib.face_recognition_model_v1(_RECOG_MODEL)
except Exception as e:
    print(f"[ERR] Không thể nạp mô hình Dlib: {e}")

# Biến cờ (flag) để các file khác không bị báo lỗi thiếu biến
MTCNN_AVAILABLE = False 

# ══════════════════════════════════════════════════════════════════════════════
#  2. TẦNG DETECTION (TỐI ƯU BẰNG MEDIAPIPE)
# ══════════════════════════════════════════════════════════════════════════════

def detect_faces_bgr(bgr_img: np.ndarray) -> list[tuple[int,int,int,int]]:
    rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_img)
    result   = _mp_detector.detect(mp_image)

    faces = []
    h, w  = bgr_img.shape[:2]
    for det in result.detections:
        bbox = det.bounding_box
        l = max(0,  bbox.origin_x)
        t = max(0,  bbox.origin_y)
        r = min(w,  bbox.origin_x + bbox.width)
        b = min(h,  bbox.origin_y + bbox.height)
        if r > l and b > t:
            faces.append((l, t, r, b))

    faces.sort(key=lambda x: (x[2]-x[0])*(x[3]-x[1]), reverse=True)
    return faces
def center_face(bgr_img: np.ndarray) -> tuple[int,int,int,int] | None:
    """Trả về bounding box mặt gần tâm ảnh nhất"""
    faces = detect_faces_bgr(bgr_img)
    if not faces:
        return None

    h, w = bgr_img.shape[:2]
    cx, cy = w / 2, h / 2

    def dist_to_center(box):
        l, t, r, b = box
        return ((l+r)/2 - cx)**2 + ((t+b)/2 - cy)**2

    return min(faces, key=dist_to_center)

# ==============================================================================
# HÃY GIỮ NGUYÊN CÁC HÀM BÊN DƯỚI TRONG FILE CỦA BẠN:
# - embedding_from_box
# - extract_embedding
# - match_face
# ==============================================================================
# ══════════════════════════════════════════════════════════════════════════════
#  EMBEDDING
# ══════════════════════════════════════════════════════════════════════════════

def embedding_from_box(bgr_img: np.ndarray,
                       box: tuple[int,int,int,int]) -> np.ndarray | None:
    """
    Tính face embedding 128-D từ bounding box đã biết.
    Dùng dlib resnet (tương thích với DB hiện có).
    """
    rgb = np.ascontiguousarray(bgr_img[:, :, ::-1])
    l, t, r, b = box
    dlib_rect = dlib.rectangle(l, t, r, b)

    try:
        shape     = _shape_pred(rgb, dlib_rect)
        face_chip = dlib.get_face_chip(rgb, shape, size=150)
        return np.array(_face_encoder.compute_face_descriptor(face_chip))
    except Exception as e:
        print(f"[face_utils] embedding error: {e}")
        return None


def extract_embedding(bgr_img: np.ndarray) -> tuple[np.ndarray | None,
                                                     tuple | None]:
    """
    Detect mặt gần tâm + tính embedding.
    Trả về (embedding, box) hoặc (None, None).
    """
    box = center_face(bgr_img)
    if box is None:
        return None, None
    emb = embedding_from_box(bgr_img, box)
    return emb, box


# ══════════════════════════════════════════════════════════════════════════════
#  MATCHING (1:N multi-user)
# ══════════════════════════════════════════════════════════════════════════════

def match_face(embedding: np.ndarray,
               db: dict,
               threshold: float = 0.45) -> tuple[str | None, float]:
    """
    So sánh embedding với toàn bộ DB (1:N).

    Returns:
        (person_name, distance) — name=None nếu không khớp ai
    """
    if not db:
        return None, float("inf")

    best_name = None
    best_dist = float("inf")

    for name, known_emb in db.items():
        dist = float(np.linalg.norm(embedding - known_emb))
        if dist < best_dist:
            best_dist = dist
            best_name = name

    if best_dist <= threshold:
        return best_name, best_dist
    return None, best_dist
