"""
app/database/database.py — Kết nối SQLite + đảm bảo schema hoàn chỉnh (idempotent)

Thay thế cách tiếp cận "thêm cột dần dần" cũ (ALTER TABLE liệt kê cứng từng
migration). Giờ chỉ có MỘT nguồn sự thật: dict SCHEMA bên dưới, mô tả cấu
trúc bảng CUỐI CÙNG mà bạn muốn có.

  • Muốn đổi cấu trúc DB (thêm cột, đổi default...)?
      → Sửa trong SCHEMA, rồi chạy lại file này (py database.py hoặc
        gọi migrate() lúc app boot). Không cần viết thêm ALTER TABLE nào nữa.

  • ensure_schema() tự lo:
      - Bảng chưa tồn tại  → CREATE TABLE đúng theo SCHEMA.
      - Bảng đã tồn tại nhưng thiếu cột → ALTER TABLE ADD COLUMN cột đó.
      - Index                          → CREATE INDEX IF NOT EXISTS.

  • Giới hạn cần biết: SQLite không hỗ trợ ALTER để đổi kiểu cột, xoá cột,
    hay đổi PRIMARY KEY của bảng đã có dữ liệu. Nếu bạn cần loại thay đổi
    đó, ensure_schema() sẽ in cảnh báo thay vì tự ý làm hỏng dữ liệu —
    lúc đó cần migration thủ công (tạo bảng mới, copy dữ liệu, đổi tên).
    mssv hiện đã là PRIMARY KEY của Users — giữ nguyên, không đụng tới.
"""

import re
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


# ═════════════════════════════════════════════════════════════════════════
# SCHEMA — nguồn sự thật duy nhất về cấu trúc DB.
#
# Mỗi bảng: list các cột dạng (tên, kiểu, ràng buộc_khi_CREATE, ràng_buộc_khi_ALTER_ADD)
#   - ràng_buộc_khi_CREATE: dùng khi tạo bảng mới từ đầu (có thể là "PRIMARY KEY")
#   - ràng_buộc_khi_ALTER_ADD: dùng khi thêm cột vào bảng đã tồn tại
#     (None nghĩa là cột này BẮT BUỘC phải có ngay lúc tạo bảng — ví dụ
#     PRIMARY KEY — SQLite không cho ALTER TABLE ADD COLUMN PRIMARY KEY)
# ═════════════════════════════════════════════════════════════════════════

SCHEMA = {
    "Users": [
        ("mssv",               "TEXT",    "PRIMARY KEY",                 None),
        ("name",                "TEXT",    "NOT NULL",                    "TEXT NOT NULL DEFAULT ''"),
        ("has_face",            "INTEGER", "NOT NULL DEFAULT 0",         "INTEGER NOT NULL DEFAULT 0"),
        ("face_embedding",       "BLOB",    "",                            "BLOB"),
        ("password",             "TEXT",    "",                            "TEXT"),
        ("email",                "TEXT",    "NOT NULL DEFAULT ''",        "TEXT NOT NULL DEFAULT ''"),
        ("locker_expiry_date",   "TEXT",    "NOT NULL DEFAULT ''",        "TEXT NOT NULL DEFAULT ''"),
        ("OTP",                  "NUMERIC", "",                            "NUMERIC"),
        ("is_first_login",       "INTEGER", "NOT NULL DEFAULT 1",         "INTEGER NOT NULL DEFAULT 1"),
    ],
    # current_mssv: ON DELETE SET NULL — xoá 1 Users không còn bị
    # "FOREIGN KEY constraint failed" nữa; locker liên quan tự trả về
    # NULL (trống) thay vì chặn thao tác xoá. Log lịch sử (LockerLog,
    # LOCKER_DELETE_LOG) không bị ảnh hưởng vì chúng lưu mssv dạng text
    # thường, không có FK trỏ tới Users.
    "Lockers": [
        ("locker_id",     "TEXT", "PRIMARY KEY",          None),
        ("size",          "TEXT", "NOT NULL",             "TEXT NOT NULL DEFAULT ''"),
        ("status",        "TEXT", "NOT NULL DEFAULT 'empty'", "TEXT NOT NULL DEFAULT 'empty'"),
        ("current_mssv",  "TEXT", "UNIQUE REFERENCES Users(mssv) ON DELETE SET NULL",  "TEXT UNIQUE REFERENCES Users(mssv) ON DELETE SET NULL"),
        ("assigned_date", "TEXT", "",  "TEXT"),
        ("last_open",     "TEXT", "",  "TEXT"),
        # idle_warned_at: đã gửi mail cảnh báo idle (ngày 14) cho lượt mượn
        # hiện tại chưa — reset về NULL mỗi khi BORROW mới / OPEN / RETURN.
        ("idle_warned_at",   "TEXT", "DEFAULT NULL", "TEXT DEFAULT NULL"),
        # expiry_warned_at: đã gửi mail cảnh báo sắp hết hạn mượn (trước 2 ngày)
        # cho lượt mượn hiện tại chưa — reset về NULL mỗi khi BORROW mới / RETURN.
        ("expiry_warned_at", "TEXT", "DEFAULT NULL", "TEXT DEFAULT NULL"),
    ],
    "LockerLog": [
        ("id",        "INTEGER", "PRIMARY KEY AUTOINCREMENT",   None),
        ("timestamp", "TEXT",    "NOT NULL",                     "TEXT NOT NULL DEFAULT ''"),
        ("event",     "TEXT",    "NOT NULL",                     "TEXT NOT NULL DEFAULT ''"),
        ("locker_id", "TEXT",    "REFERENCES Lockers(locker_id)", "TEXT REFERENCES Lockers(locker_id)"),
        ("mssv",      "TEXT",    "",                              "TEXT"),
        ("name",      "TEXT",    "",                              "TEXT"),
        # door_closed_at: thời điểm ESP32 xác nhận cửa đã đóng thật sự
        # (tín hiệu CLOSED:xx) — NULL nghĩa là chưa đóng / chưa nhận tín hiệu.
        ("door_closed_at", "TEXT", "DEFAULT NULL", "TEXT DEFAULT NULL"),
        # warned_door: thời điểm đã gửi mail cảnh báo quên đóng tủ cho lượt
        # mở hiện tại — NULL nghĩa là chưa gửi, dùng để tránh gửi lặp lại.
        ("warned_door",    "TEXT", "DEFAULT NULL", "TEXT DEFAULT NULL"),
    ],
    "FaceLog": [
        ("id",        "INTEGER", "PRIMARY KEY AUTOINCREMENT", None),
        ("timestamp", "TEXT",    "NOT NULL",                   "TEXT NOT NULL DEFAULT ''"),
        ("event",     "TEXT",    "NOT NULL",                   "TEXT NOT NULL DEFAULT ''"),
        ("mssv",      "TEXT",    "",                            "TEXT"),
        ("name",      "TEXT",    "",                            "TEXT"),
    ],
    "LOCKER_DELETE_LOG": [
        ("ID",          "INTEGER", "PRIMARY KEY AUTOINCREMENT", None),
        ("MSSV",        "TEXT",    "NOT NULL",                   "TEXT NOT NULL DEFAULT ''"),
        ("LOCKER_ID",   "TEXT",    "NOT NULL",                   "TEXT NOT NULL DEFAULT ''"),
        ("DELETE_TIME", "TEXT",    "NOT NULL",                   "TEXT NOT NULL DEFAULT ''"),
        ("REASON",      "TEXT",    "NOT NULL",                   "TEXT NOT NULL DEFAULT ''"),
    ],
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_lockerlog_mssv          ON LockerLog(mssv)",
    "CREATE INDEX IF NOT EXISTS idx_lockerlog_locker_id     ON LockerLog(locker_id)",
    "CREATE INDEX IF NOT EXISTS idx_facelog_mssv            ON FaceLog(mssv)",
    "CREATE INDEX IF NOT EXISTS idx_delete_log_mssv         ON LOCKER_DELETE_LOG(MSSV)",
]


def _fk_on_delete(create_clause: str) -> str:
    """Trích ON DELETE ... từ chuỗi ràng buộc CREATE, mặc định NO ACTION."""
    if "ON DELETE" not in create_clause.upper():
        return "NO ACTION"
    return create_clause.upper().split("ON DELETE", 1)[1].strip().split(",")[0].strip()


def _needs_rebuild(conn, real_name: str, columns) -> bool:
    """
    True nếu bảng hiện tại có cột THỪA so với SCHEMA (cần xoá) hoặc FK
    ON DELETE khác với SCHEMA mong muốn — cả hai đều không thể sửa bằng
    ALTER TABLE ADD COLUMN, phải rebuild lại bảng.
    """
    existing_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({real_name})").fetchall()}
    desired_cols = {name for name, *_ in columns}
    if existing_cols - desired_cols:
        return True

    desired_fk = {name: _fk_on_delete(create_c) for name, _, create_c, _ in columns if "REFERENCES" in create_c.upper()}
    actual_fk = {r["from"]: (r["on_delete"] or "NO ACTION").upper() for r in conn.execute(f"PRAGMA foreign_key_list({real_name})").fetchall()}
    for col, wanted in desired_fk.items():
        if actual_fk.get(col, "NO ACTION") != wanted:
            return True
    return False


def _extract_default(create_c: str):
    """Lấy giá trị DEFAULT (nếu có) từ chuỗi ràng buộc, ví dụ DEFAULT '' → '''''' ."""
    m = re.search(r"DEFAULT\s+('(?:[^']|'')*'|\S+)", create_c, re.IGNORECASE)
    return m.group(1) if m else None


def _rebuild_table(conn, table: str, real_name: str, columns):
    """
    Tạo lại bảng đúng SCHEMA hiện tại: cột thừa bị bỏ, cột thiếu để trống/default,
    FK theo đúng ON DELETE mới. Dữ liệu của các cột còn giữ được copy nguyên vẹn.

    Dữ liệu cũ có thể có NULL ở cột mà SCHEMA mới khai NOT NULL (cột được
    ALTER thêm từ trước khi có ràng buộc) — COALESCE về DEFAULT của SCHEMA
    khi copy để không bị "NOT NULL constraint failed" giữa chừng.
    """
    existing_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({real_name})").fetchall()}
    desired_names = [name for name, *_ in columns]
    shared = [(name, create_c) for name, _, create_c, _ in columns if name in existing_cols]

    tmp = f"{table}__rebuild"
    conn.execute(f"DROP TABLE IF EXISTS {tmp}")
    col_defs = ", ".join(f"{name} {ctype} {create_c}".strip() for name, ctype, create_c, _ in columns)
    conn.execute(f"CREATE TABLE {tmp} ({col_defs})")

    dest_cols_sql = ", ".join(name for name, _ in shared)
    select_exprs = []
    for name, create_c in shared:
        default = _extract_default(create_c)
        if "NOT NULL" in create_c.upper() and default is not None:
            select_exprs.append(f"COALESCE({name}, {default})")
        else:
            select_exprs.append(name)
    select_sql = ", ".join(select_exprs)
    conn.execute(f"INSERT INTO {tmp} ({dest_cols_sql}) SELECT {select_sql} FROM {real_name}")

    conn.execute(f"DROP TABLE {real_name}")
    conn.execute(f"ALTER TABLE {tmp} RENAME TO {table}")
    dropped = existing_cols - set(desired_names)
    if dropped:
        print(f"[db] ✓ Rebuild {table} — bỏ cột {sorted(dropped)}, dữ liệu các cột còn lại giữ nguyên")
    else:
        print(f"[db] ✓ Rebuild {table} — cập nhật ràng buộc khoá ngoại")


def ensure_schema(conn):
    """
    Đưa DB về đúng SCHEMA — idempotent, chạy bao nhiêu lần cũng an toàn,
    hoạt động cả trên DB rỗng lẫn DB đã có dữ liệu (SML cũ hoặc IntelligentLocker cũ).
    """
    conn.execute("PRAGMA foreign_keys = OFF")  # tắt tạm trong lúc rebuild bảng

    existing_tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    # so khớp không phân biệt hoa/thường (SML dùng tên khác case ở vài bảng)
    existing_lower = {t.lower(): t for t in existing_tables}

    for table, columns in SCHEMA.items():
        real_name = existing_lower.get(table.lower())

        if real_name is None:
            # ── Bảng chưa tồn tại → tạo mới đầy đủ từ SCHEMA ────────────
            col_defs = ", ".join(
                f"{name} {ctype} {create_c}".strip()
                for name, ctype, create_c, _ in columns
            )
            conn.execute(f"CREATE TABLE {table} ({col_defs})")
            print(f"[db] ✓ Tạo bảng {table}")
            continue

        if _needs_rebuild(conn, real_name, columns):
            _rebuild_table(conn, table, real_name, columns)
            continue

        # ── Bảng đã tồn tại, không cần rebuild → chỉ thêm cột còn thiếu ──
        existing_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({real_name})").fetchall()}
        for name, ctype, _, alter_c in columns:
            if name in existing_cols:
                continue
            if alter_c is None:
                # Cột kiểu PRIMARY KEY / AUTOINCREMENT bị thiếu trên bảng đã có dữ liệu
                # → SQLite không cho ALTER thêm kiểu này. Cần migration thủ công.
                print(f"[db] ⚠ {table}.{name} thiếu nhưng không thể ALTER thêm "
                      f"(cần PRIMARY KEY/AUTOINCREMENT) — kiểm tra thủ công")
                continue
            conn.execute(f"ALTER TABLE {real_name} ADD COLUMN {name} {alter_c}")
            print(f"[db] ✓ Thêm cột '{name}' vào {table}")

    for idx_sql in INDEXES:
        conn.execute(idx_sql)

    # ── Chuẩn hoá dữ liệu (idempotent, chạy lại vô hại) ─────────────────────
    conn.execute("UPDATE Lockers SET status='empty'    WHERE status='Empty'")
    conn.execute("UPDATE Lockers SET status='occupied' WHERE status='Busy' OR status='Occupied'")
    conn.execute("UPDATE Users SET email = TRIM(email) WHERE email != TRIM(email)")

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


def migrate():
    """Giữ tên migrate() để tương thích với main.py hiện tại."""
    db = Database()
    with db.connect() as conn:
        ensure_schema(conn)
    print("[db] ✓ migrate() hoàn tất — DB sẵn sàng")


if __name__ == "__main__":
    migrate()