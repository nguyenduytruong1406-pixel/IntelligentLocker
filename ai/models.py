"""
ai/models.py — Load dlib models 1 lần duy nhất (singleton).

Import ở bất kỳ đâu trong app đều dùng chung instance,
không load lại nhiều lần.

Dùng:
    from ai.models import shape_pred, face_encoder
"""

import os
import dlib

# ── Đường dẫn model ───────────────────────────────────────────────────────────
# Thứ tự ưu tiên:
#   1. Biến môi trường FACE_MODELS_DIR  (linh hoạt cho mọi máy / CI)
#   2. Package face_recognition_models  (chuẩn nhất, không hardcode)
#   3. Fallback: cùng thư mục với file này (để dev copy model vào ai/)

def _resolve_model_paths() -> tuple[str, str]:
    # 1. Biến môi trường
    env_dir = os.environ.get("FACE_MODELS_DIR")
    if env_dir:
        return (
            os.path.join(env_dir, "shape_predictor_68_face_landmarks.dat"),
            os.path.join(env_dir, "dlib_face_recognition_resnet_model_v1.dat"),
        )

    # 2. Package face_recognition_models (pip install face_recognition_models)
    try:
        import face_recognition_models
        return (
            face_recognition_models.pose_predictor_model_location(),
            face_recognition_models.face_recognition_model_location(),
        )
    except ImportError:
        pass

    # 3. Fallback: thư mục ai/ (dev tự copy file .dat vào đây)
    _here = os.path.dirname(os.path.abspath(__file__))
    return (
        os.path.join(_here, "shape_predictor_68_face_landmarks.dat"),
        os.path.join(_here, "dlib_face_recognition_resnet_model_v1.dat"),
    )


SHAPE_MODEL_PATH, RECOG_MODEL_PATH = _resolve_model_paths()

# ── Load singleton ────────────────────────────────────────────────────────────
print("[AI Models] Đang load dlib models...")

if not os.path.isfile(SHAPE_MODEL_PATH):
    raise FileNotFoundError(
        f"[AI Models] Không tìm thấy shape model: {SHAPE_MODEL_PATH}\n"
        "  → Đặt biến môi trường FACE_MODELS_DIR hoặc cài: "
        "pip install face_recognition_models"
    )
if not os.path.isfile(RECOG_MODEL_PATH):
    raise FileNotFoundError(
        f"[AI Models] Không tìm thấy recognition model: {RECOG_MODEL_PATH}\n"
        "  → Đặt biến môi trường FACE_MODELS_DIR hoặc cài: "
        "pip install face_recognition_models"
    )

shape_pred   = dlib.shape_predictor(SHAPE_MODEL_PATH)
face_encoder = dlib.face_recognition_model_v1(RECOG_MODEL_PATH)
print("[AI Models] ✓ Sẵn sàng")