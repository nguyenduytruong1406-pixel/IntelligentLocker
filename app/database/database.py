"""
app/database/database.py — Kết nối SQLite + migrate schema hợp nhất
Gộp schema SML (account_status, last_active_time, warned_at, OTP,
Service_engineer_log, FaceLog) với IntelligentLocker (last_open,
assigned_date chuẩn, LOCKER_DELETE_LOG, LockerLog).
"""

import sqlite3
from pathlib import Path


class Database:
    def __init__(self):
        self.path = Path(__file__).parent / "IntelligentLocker.db"

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row          # truy cập cột theo tên
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def migrate():
    """
    Thêm cột/bảng còn thiếu vào DB hiện có — idempotent, gọi 1 lần khi boot.
    Chạy trên cả DB gốc SML lẫn DB gốc IntelligentLocker đều an toàn.
    """
    db = Database()
    with db.connect() as conn:

        # ── Bảng đang có — normalize về lowercase để so sánh an toàn ──────────
        existing_tables = {
            r[0].lower() for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        # ── Users: đảm bảo mọi cột cần thiết đều tồn tại ────────────────────
        user_cols = {r[1] for r in conn.execute("PRAGMA table_info(Users)").fetchall()}

        _add_columns(conn, "Users", user_cols, [
            # Cột IntelligentLocker có thể chưa có trong SML
            ("has_face",          "ALTER TABLE Users ADD COLUMN has_face INTEGER DEFAULT 0"),
            ("face_embedding",    "ALTER TABLE Users ADD COLUMN face_embedding BLOB"),
            ("password",          "ALTER TABLE Users ADD COLUMN password TEXT"),
            ("email",             "ALTER TABLE Users ADD COLUMN email TEXT DEFAULT ''"),
            ("role",              "ALTER TABLE Users ADD COLUMN role TEXT DEFAULT 'student'"),
            ("registered_at",     "ALTER TABLE Users ADD COLUMN registered_at TEXT DEFAULT ''"),
            # Cột SML có thể chưa có trong IntelligentLocker
            ("account_status",    "ALTER TABLE Users ADD COLUMN account_status TEXT DEFAULT 'ACTIVE'"),
            ("last_active_time",  "ALTER TABLE Users ADD COLUMN last_active_time TEXT DEFAULT ''"),
            ("warned_at",         "ALTER TABLE Users ADD COLUMN warned_at TEXT DEFAULT NULL"),
            ("OTP",               "ALTER TABLE Users ADD COLUMN OTP NUMERIC"),
        ])

        # ── Lockers: đảm bảo last_open tồn tại (SML chưa có) ────────────────
        locker_cols = {r[1] for r in conn.execute("PRAGMA table_info(Lockers)").fetchall()}

        _add_columns(conn, "Lockers", locker_cols, [
            ("last_open",     "ALTER TABLE Lockers ADD COLUMN last_open TEXT DEFAULT ''"),
            ("assigned_date", "ALTER TABLE Lockers ADD COLUMN assigned_date TEXT DEFAULT ''"),
        ])

        # ── Chuẩn hóa status Lockers về lowercase ────────────────────────────
        conn.execute("UPDATE Lockers SET status='empty'    WHERE status='Empty'")
        conn.execute("UPDATE Lockers SET status='occupied' WHERE status='Busy' OR status='Occupied'")

        # ── Bảng LockerLog (alias của Locker_access_log cho IntelligentLocker) ─
        # SML dùng "Locker_access_log"; IntelligentLocker dùng "LockerLog".
        # Tạo LockerLog nếu chưa có để core/log_db.py của IntelligentLocker không lỗi.
        if "lockerlog" not in existing_tables:
            conn.execute("""
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

        # ── FaceLog ───────────────────────────────────────────────────────────
        if "facelog" not in existing_tables:
            conn.execute("""
                CREATE TABLE FaceLog (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event     TEXT NOT NULL,
                    mssv      TEXT,
                    name      TEXT
                )
            """)
            print("[db] ✓ Tạo bảng FaceLog")

        # ── LOCKER_DELETE_LOG ─────────────────────────────────────────────────
        # SML có "Locker_delete_log" — SQLite case-insensitive, cùng 1 bảng.
        # Chỉ tạo mới nếu cả hai tên đều chưa tồn tại.
        if "locker_delete_log" not in existing_tables:
            conn.execute("""
                CREATE TABLE LOCKER_DELETE_LOG (
                    ID          INTEGER PRIMARY KEY AUTOINCREMENT,
                    MSSV        TEXT NOT NULL,
                    LOCKER_ID   TEXT NOT NULL,
                    DELETE_TIME TEXT NOT NULL,
                    REASON      TEXT NOT NULL
                )
            """)
            print("[db] ✓ Tạo bảng LOCKER_DELETE_LOG")

        # ── Service_engineer_log (SML) ────────────────────────────────────────
        if "service_engineer_log" not in existing_tables:
            conn.execute("""
                CREATE TABLE Service_engineer_log (
                    ID        INTEGER PRIMARY KEY AUTOINCREMENT,
                    locker_id TEXT,
                    ktv_id    TEXT,
                    ktv_name  TEXT,
                    action    TEXT,
                    timestamp TEXT NOT NULL,
                    notes     TEXT
                )
            """)
            print("[db] ✓ Tạo bảng Service_engineer_log")

        # ── Fix email trailing whitespace ─────────────────────────────────────
        conn.execute("UPDATE Users SET email = TRIM(email) WHERE email != TRIM(email)")

        conn.commit()

    print("[db] ✓ migrate() hoàn tất — DB sẵn sàng")


# ── Helper ────────────────────────────────────────────────────────────────────
def _add_columns(conn, table: str, existing_cols: set, definitions: list):
    for col, ddl in definitions:
        if col not in existing_cols:
            conn.execute(ddl)
            print(f"[db] ✓ Thêm cột '{col}' vào {table}")