"""
face_utils.py — Module dùng chung: MTCNN detection + dlib embedding
Thay thế dlib HOG detector bằng MTCNN (chính xác hơn với mặt nghiêng, ánh sáng yếu)

Cài đặt (1 lần):
    pip install facenet-pytorch
"""

import numpy as np
import cv2
import dlib
from PIL import Image

# ── MTCNN detector (facenet-pytorch, không cần TensorFlow) ────────────────────
try:
    from facenet_pytorch import MTCNN as _MTCNN
    _mtcnn = _MTCNN(
        keep_all       = True,    # Phát hiện tất cả khuôn mặt
        min_face_size  = 40,      # Bỏ qua mặt quá nhỏ
        thresholds     = [0.6, 0.7, 0.7],   # P-Net, R-Net, O-Net
        post_process   = False,
        device         = "cpu",
    )
    MTCNN_AVAILABLE = True
except ImportError:
    MTCNN_AVAILABLE = False
    print("[face_utils] ⚠️  facenet-pytorch chưa cài → dùng dlib HOG fallback")
    print("             Cài: pip install facenet-pytorch")

# ── dlib fallback + embedding ──────────────────────────────────────────────────
_hog_detector = dlib.get_frontal_face_detector()

_SHAPE_MODEL = (
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    r"\face_recognition_models\models\shape_predictor_68_face_landmarks.dat"
)
_RECOG_MODEL = (
    r"C:\Users\ASUS\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    r"\face_recognition_models\models\dlib_face_recognition_resnet_model_v1.dat"
)

_shape_pred  = dlib.shape_predictor(_SHAPE_MODEL)
_face_encoder = dlib.face_recognition_model_v1(_RECOG_MODEL)


# ══════════════════════════════════════════════════════════════════════════════
#  DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_faces_bgr(bgr_img: np.ndarray) -> list[tuple[int,int,int,int]]:
    """
    Phát hiện khuôn mặt từ ảnh BGR.
    Trả về list [(left, top, right, bottom), ...] đã sort theo diện tích giảm dần.
    Dùng MTCNN nếu có, fallback sang dlib HOG.
    """
    rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)

    if MTCNN_AVAILABLE:
        return _detect_mtcnn(rgb)
    return _detect_hog(rgb)


def _detect_mtcnn(rgb_img: np.ndarray) -> list[tuple[int,int,int,int]]:
    pil_img = Image.fromarray(rgb_img)
    boxes, probs = _mtcnn.detect(pil_img)

    if boxes is None:
        return []

    h, w = rgb_img.shape[:2]
    results = []
    for box, prob in zip(boxes, probs):
        if prob is None or prob < 0.85:
            continue
        l = max(0,  int(box[0]))
        t = max(0,  int(box[1]))
        r = min(w,  int(box[2]))
        b = min(h,  int(box[3]))
        if r > l and b > t:
            results.append((l, t, r, b))

    # Sort: mặt lớn nhất trước
    results.sort(key=lambda x: (x[2]-x[0])*(x[3]-x[1]), reverse=True)
    return results


def _detect_hog(rgb_img: np.ndarray) -> list[tuple[int,int,int,int]]:
    dets = _hog_detector(rgb_img, 1)
    results = [(d.left(), d.top(), d.right(), d.bottom()) for d in dets]
    results.sort(key=lambda x: (x[2]-x[0])*(x[3]-x[1]), reverse=True)
    return results


def center_face(bgr_img: np.ndarray) -> tuple[int,int,int,int] | None:
    """
    Trả về bounding box mặt gần tâm ảnh nhất (cho verify 1:1).
    None nếu không phát hiện được.
    """
    faces = detect_faces_bgr(bgr_img)
    if not faces:
        return None

    h, w = bgr_img.shape[:2]
    cx, cy = w / 2, h / 2

    def dist_to_center(box):
        l, t, r, b = box
        return ((l+r)/2 - cx)**2 + ((t+b)/2 - cy)**2

    return min(faces, key=dist_to_center)


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
