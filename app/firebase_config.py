"""
app/firebase_config.py — Khởi tạo Firebase Admin SDK 1 lần duy nhất.

Import module này sớm nhất có thể (trong main.py, trước mọi thứ khác).
Các module khác chỉ cần:
    from firebase_admin import db as fdb
là dùng được ngay — không cần init lại.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db as fdb

# ── Đường dẫn ─────────────────────────────────────────────────────────────────
BASE_DIR         = Path(__file__).resolve().parent.parent
ENV_PATH         = BASE_DIR / ".env"
SERVICE_KEY_PATH = BASE_DIR / "private_key_lockers.json"
FIREBASE_URL     = "https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app"

load_dotenv(ENV_PATH)

# ── Init (idempotent) ──────────────────────────────────────────────────────────
def init_firebase() -> bool:
    """Khởi tạo Firebase Admin SDK. Trả True nếu thành công."""
    if firebase_admin._apps:
        return True  # đã init rồi

    if not SERVICE_KEY_PATH.exists():
        print(f"[Firebase] ⚠ Không tìm thấy service key: {SERVICE_KEY_PATH}")
        print("[Firebase] ⚠ Chạy ở chế độ offline — các tính năng Firebase sẽ bị tắt.")
        return False

    try:
        cred = credentials.Certificate(str(SERVICE_KEY_PATH))
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
        print("[Firebase] ✅ Đã kết nối Firebase Realtime DB")
        return True
    except Exception as e:
        print(f"[Firebase] ✗ Lỗi khởi tạo: {e}")
        return False


FIREBASE_OK = init_firebase()
