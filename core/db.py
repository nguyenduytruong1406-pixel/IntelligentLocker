"""
core/db.py — Kết nối SQLite + Firebase init + migrate schema
Không import gì từ các module core khác.
"""

import sqlite3
import datetime
from contextlib import contextmanager
import firebase_admin
from firebase_admin import credentials, db as fdb

# ── Cấu hình ──────────────────────────────────────────────────────────────────
DB_PATH          = "IntelligentLocker.db"
SERVICE_KEY_PATH = r"D:/DATN/Software/test_db_ver1/private_key_lockers.json"
FIREBASE_URL     = "https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app"

MAX_FAILS    = 5
LOCKOUT_SECS = 60
LOCKER_EVENTS = {'OPEN_LOCKER', 'ASSIGN_LOCKER', 'RELEASE_LOCKER'}

# ── Khởi tạo Firebase 1 lần ───────────────────────────────────────────────────
def init_firebase():
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(SERVICE_KEY_PATH)
            firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_URL})
    except Exception as e:
        print(f"[Firebase] Cảnh báo khởi tạo: {e}")

init_firebase()

# ── Context manager kết nối SQLite ────────────────────────────────────────────
@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

# ── Migrate schema — idempotent ───────────────────────────────────────────────
def migrate():
    """Thêm cột/bảng còn thiếu. Gọi 1 lần khi khởi động app."""
    with _conn() as con:
        existing_tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        cols = [r[1] for r in con.execute("PRAGMA table_info(Users)").fetchall()]

        for col, ddl in [
            ("has_face",       "ALTER TABLE Users ADD COLUMN has_face INTEGER DEFAULT 0"),
            ("face_embedding", "ALTER TABLE Users ADD COLUMN face_embedding BLOB"),
            ("password",       "ALTER TABLE Users ADD COLUMN password TEXT"),
            ("email",          "ALTER TABLE Users ADD COLUMN email TEXT DEFAULT ''"),
        ]:
            if col not in cols:
                con.execute(ddl)
                print(f"[db] ✓ Thêm cột '{col}' vào Users")

        if "LockerLog" not in existing_tables:
            con.execute("""
                CREATE TABLE LockerLog (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event     TEXT NOT NULL,
                    locker_id TEXT,
                    mssv      TEXT,
                    name      TEXT
                )
            """)
            print("[db] ✓ Tạo bảng LockerLog")

        if "FaceLog" not in existing_tables:
            con.execute("""
                CREATE TABLE FaceLog (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event     TEXT NOT NULL,
                    mssv      TEXT,
                    name      TEXT
                )
            """)
            print("[db] ✓ Tạo bảng FaceLog")

    print(f"[db] ✓ DB ready: {DB_PATH}")
