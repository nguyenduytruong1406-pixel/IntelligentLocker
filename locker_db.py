"""
locker_db.py — Tích hợp face recognition vào IntelligentLocker.db
Thay thế secure_db.py — dùng chung 1 file SQLite duy nhất

Schema bổ sung:
  Users       += face_embedding BLOB  (numpy array pickle'd)
  AccessLog    (bảng mới) — audit log nhận dạng
"""

import sqlite3
import pickle
import datetime
import numpy as np
from pathlib import Path
from contextlib import contextmanager

DB_PATH = "IntelligentLocker.db"   # ← chỉnh đường dẫn nếu cần

# ── Rate limiting ─────────────────────────────────────────────────────────────
MAX_FAILS    = 5
LOCKOUT_SECS = 60


# ══════════════════════════════════════════════════════════════════════════════
#  KẾT NỐI & MIGRATION
# ══════════════════════════════════════════════════════════════════════════════

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def migrate():
    """
    Thêm các cột/bảng còn thiếu vào DB hiện có — an toàn, idempotent.
    Gọi 1 lần khi khởi động app.
    """
    with _conn() as con:
        # Thêm cột face_embedding vào Users nếu chưa có
        cols = [r[1] for r in con.execute("PRAGMA table_info(Users)").fetchall()]
        if "face_embedding" not in cols:
            con.execute("ALTER TABLE Users ADD COLUMN face_embedding BLOB")
            print("[locker_db] ✓ Thêm cột face_embedding vào Users")

        # Tạo bảng AccessLog nếu chưa có
        con.execute("""
            CREATE TABLE IF NOT EXISTS AccessLog (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                event       TEXT    NOT NULL,
                mssv        TEXT,
                name        TEXT,
                locker_id   INTEGER,
                face_dist   REAL,
                live_result TEXT,
                notes       TEXT
            )
        """)
    print(f"[locker_db] ✓ DB ready: {DB_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
#  FACE EMBEDDING — lưu/tải theo mssv
# ══════════════════════════════════════════════════════════════════════════════

def save_embedding(mssv: str, embedding: np.ndarray) -> bool:
    """Lưu face embedding cho user có mssv. Trả về False nếu mssv không tồn tại."""
    blob = pickle.dumps(embedding)
    with _conn() as con:
        cur = con.execute(
            "UPDATE Users SET face_embedding=? WHERE mssv=?", (blob, mssv)
        )
        if cur.rowcount == 0:
            print(f"[locker_db] ✗ Không tìm thấy mssv='{mssv}' trong DB")
            return False
    print(f"[locker_db] ✓ Lưu embedding cho mssv='{mssv}'")
    return True


def load_all_embeddings() -> dict[str, tuple[np.ndarray, str]]:
    """
    Tải toàn bộ face embedding.
    Trả về {mssv: (embedding, name)} — chỉ user đã được approved và có embedding.
    """
    result = {}
    with _conn() as con:
        rows = con.execute(
            "SELECT mssv, name, face_embedding FROM Users "
            "WHERE is_approved=1 AND face_embedding IS NOT NULL"
        ).fetchall()
    for row in rows:
        try:
            emb = pickle.loads(row["face_embedding"])
            result[row["mssv"]] = (emb, row["name"])
        except Exception as e:
            print(f"[locker_db] ⚠ Lỗi load embedding mssv={row['mssv']}: {e}")
    return result


def get_user(mssv: str) -> dict | None:
    """Lấy thông tin user theo mssv."""
    with _conn() as con:
        row = con.execute(
            "SELECT id, name, mssv, rfid, role, is_approved "
            "FROM Users WHERE mssv=?", (mssv,)
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    """Liệt kê tất cả user."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, name, mssv, role, is_approved, "
            "CASE WHEN face_embedding IS NOT NULL THEN 1 ELSE 0 END as has_face "
            "FROM Users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  LOCKER — cập nhật trạng thái sau verify
# ══════════════════════════════════════════════════════════════════════════════

def get_user_locker(mssv: str) -> dict | None:
    """Lấy tủ hiện tại của user (nếu đang mượn)."""
    with _conn() as con:
        row = con.execute(
            "SELECT locker_id, status, size FROM Lockers WHERE current_mssv=?",
            (mssv,)
        ).fetchone()
    return dict(row) if row else None


def open_locker(mssv: str) -> tuple[bool, str]:
    """
    Xử lý sau khi xác thực thành công:
      - Nếu user đang giữ tủ → trả về thông tin tủ đó (mở tủ)
      - Nếu chưa có tủ       → gán tủ trống (status='Empty') phù hợp
    Trả về (success, message).
    """
    # Kiểm tra tủ hiện tại
    locker = get_user_locker(mssv)
    if locker:
        log_access("OPEN_LOCKER", mssv=mssv,
                   locker_id=locker["locker_id"],
                   notes="Mở tủ đang dùng")
        return True, f"Mở tủ #{locker['locker_id']} (đang dùng)"

    # Chưa có tủ → gán tủ trống
    with _conn() as con:
        row = con.execute(
            "SELECT locker_id FROM Lockers "
            "WHERE status='Empty' AND current_mssv IS NULL "
            "ORDER BY locker_id LIMIT 1"
        ).fetchone()

        if not row:
            return False, "Không còn tủ trống!"

        lid = row["locker_id"]
        con.execute(
            "UPDATE Lockers SET status='Occupied', current_mssv=? "
            "WHERE locker_id=?", (mssv, lid)
        )

    log_access("ASSIGN_LOCKER", mssv=mssv, locker_id=lid,
               notes="Gán tủ mới")
    return True, f"Gán tủ mới #{lid}"


def release_locker(mssv: str) -> tuple[bool, str]:
    """Trả tủ (khi user lấy đồ ra). Thường gọi từ UI admin."""
    locker = get_user_locker(mssv)
    if not locker:
        return False, f"mssv='{mssv}' không đang giữ tủ nào"

    with _conn() as con:
        con.execute(
            "UPDATE Lockers SET status='Empty', current_mssv=NULL "
            "WHERE locker_id=?", (locker["locker_id"],)
        )
    log_access("RELEASE_LOCKER", mssv=mssv, locker_id=locker["locker_id"])
    return True, f"Đã trả tủ #{locker['locker_id']}"


# ══════════════════════════════════════════════════════════════════════════════
#  AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

def log_access(event: str,
               mssv:      str   = None,
               name:      str   = None,
               locker_id: int   = None,
               face_dist: float = None,
               live_result: str = None,
               notes:     str   = None) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")

    # Tự điền name nếu có mssv
    if name is None and mssv:
        user = get_user(mssv)
        if user: name = user["name"]

    with _conn() as con:
        con.execute(
            "INSERT INTO AccessLog "
            "(timestamp, event, mssv, name, locker_id, face_dist, live_result, notes) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ts, event, mssv, name, locker_id, face_dist, live_result, notes)
        )


def print_log(n: int = 20) -> None:
    with _conn() as con:
        rows = con.execute(
            "SELECT timestamp, event, mssv, name, locker_id, face_dist, live_result, notes "
            "FROM AccessLog ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()

    if not rows:
        print("(Chưa có log nào)")
        return

    print(f"\n{'─'*82}")
    print(f"{'THỜI GIAN':<21} {'SỰ KIỆN':<16} {'MSSV':<12} {'TÊN':<18} "
          f"{'TỦ':<4} {'DIST':<7} GHI CHÚ")
    print(f"{'─'*82}")

    icons = {"VERIFY_PASS": "✅", "VERIFY_FAIL": "❌", "VERIFY_ABORT": "⚠️",
             "ENROLL": "📝", "OPEN_LOCKER": "🔓", "ASSIGN_LOCKER": "🆕",
             "RELEASE_LOCKER": "🔒"}

    for row in rows:
        ts, ev, mssv, name, lid, dist, live, notes = tuple(row)
        icon   = icons.get(ev, "•")
        dist_s = f"{dist:.3f}" if dist else "  —  "
        lid_s  = str(lid) if lid else " —"
        print(f"{ts:<21} {icon}{ev:<15} {str(mssv):<12} {str(name or ''):<18} "
              f"{lid_s:<4} {dist_s:<7} {notes or ''}")
    print(f"{'─'*82}\n")


def export_log_csv(path: str = "access_log.csv") -> None:
    import csv
    with _conn() as con:
        rows = con.execute(
            "SELECT timestamp, event, mssv, name, locker_id, "
            "face_dist, live_result, notes FROM AccessLog ORDER BY id"
        ).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp","event","mssv","name",
                         "locker_id","face_dist","live_result","notes"])
        writer.writerows(rows)
    print(f"[log] Xuất {len(rows)} dòng → '{path}'")


# ══════════════════════════════════════════════════════════════════════════════
#  RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════════

def is_locked_out(mssv: str) -> tuple[bool, int]:
    cutoff = (datetime.datetime.now() -
              datetime.timedelta(seconds=LOCKOUT_SECS)).isoformat(timespec="seconds")
    with _conn() as con:
        (fails,) = con.execute(
            "SELECT COUNT(*) FROM AccessLog "
            "WHERE event='VERIFY_FAIL' AND mssv=? AND timestamp>=?",
            (mssv, cutoff)
        ).fetchone()

        if fails < MAX_FAILS:
            return False, 0

        row = con.execute(
            "SELECT timestamp FROM AccessLog "
            "WHERE event='VERIFY_FAIL' AND mssv=? ORDER BY id DESC LIMIT 1",
            (mssv,)
        ).fetchone()

    if not row:
        return False, 0

    last = datetime.datetime.fromisoformat(row[0])
    remaining = int(LOCKOUT_SECS - (datetime.datetime.now() - last).total_seconds())
    return (True, remaining) if remaining > 0 else (False, 0)


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    migrate()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "log":
        print_log(50)
    elif cmd == "export":
        export_log_csv()
    elif cmd == "users":
        users = list_users()
        print(f"\n{'ID':<5} {'TÊN':<20} {'MSSV':<12} {'ROLE':<10} "
              f"{'APPROVED':<10} {'FACE'}")
        print("─" * 65)
        for u in users:
            face = "✓" if u["has_face"] else "✗"
            appr = "✓" if u["is_approved"] else "✗"
            print(f"{u['id']:<5} {u['name']:<20} {u['mssv']:<12} "
                  f"{u['role']:<10} {appr:<10} {face}")
    elif cmd == "lockers":
        with _conn() as con:
            rows = con.execute(
                "SELECT l.locker_id, l.status, l.size, l.current_mssv, u.name "
                "FROM Lockers l LEFT JOIN Users u ON l.current_mssv=u.mssv "
                "ORDER BY l.locker_id"
            ).fetchall()
        print(f"\n{'TỦ':<6} {'STATUS':<12} {'SIZE':<10} {'MSSV':<12} TÊN")
        print("─" * 55)
        for r in rows:
            print(f"{r[0]:<6} {r[1]:<12} {str(r[2]).strip():<10} "
                  f"{str(r[3] or '—'):<12} {r[4] or ''}")
    elif cmd == "release" and len(sys.argv) > 2:
        ok, msg = release_locker(sys.argv[2])
        print(f"{'✓' if ok else '✗'} {msg}")
    else:
        print("Dùng: python locker_db.py [log|export|users|lockers|release <mssv>]")
