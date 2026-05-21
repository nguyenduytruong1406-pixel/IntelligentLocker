"""
locker_db.py — Tích hợp face recognition vào IntelligentLocker.db
Schema mới (sau migrate_db.py):
  Users      : mssv PK, name, role, is_approved, has_face, face_embedding BLOB
  Lockers    : locker_id TEXT PK ("L01"...), size, status, current_mssv
  LockerLog  : id, timestamp, event, locker_id, mssv, name  ← sync Firebase
  FaceLog    : id, timestamp, event, mssv, name, face_dist, live_result, notes ← local only
"""

import sqlite3
import pickle
import datetime
import numpy as np
from pathlib import Path
from contextlib import contextmanager
import firebase_admin
from firebase_admin import credentials, db

# --- KHỞI TẠO FIREBASE ---
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(r'D:/DATN/Software/test_db_ver1/private_key_lockers.json')
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app'
        })
except Exception as e:
    print(f"[Cảnh báo] Lỗi khởi tạo Firebase trong locker_db: {e}")

DB_PATH = "IntelligentLocker.db"

# ── Rate limiting ──────────────────────────────────────────────────────────────
MAX_FAILS    = 5
LOCKOUT_SECS = 60

# Các event thuộc LockerLog (sync Firebase), còn lại vào FaceLog (local)
LOCKER_EVENTS = {'OPEN_LOCKER', 'ASSIGN_LOCKER', 'RELEASE_LOCKER'}


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
    Thêm các cột/bảng còn thiếu — an toàn, idempotent.
    Gọi 1 lần khi khởi động app (sau khi đã chạy migrate_db.py).
    """
    with _conn() as con:
        existing_tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        # Thêm has_face vào Users nếu chưa có
        cols = [r[1] for r in con.execute("PRAGMA table_info(Users)").fetchall()]
        if "has_face" not in cols:
            con.execute("ALTER TABLE Users ADD COLUMN has_face INTEGER DEFAULT 0")
            print("[locker_db] ✓ Thêm cột has_face vào Users")
        if "face_embedding" not in cols:
            con.execute("ALTER TABLE Users ADD COLUMN face_embedding BLOB")
            print("[locker_db] ✓ Thêm cột face_embedding vào Users")

        # LockerLog: log tủ, đồng bộ Firebase
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
            print("[locker_db] ✓ Tạo bảng LockerLog")

        # FaceLog: log khuôn mặt, chỉ local
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
            print("[locker_db] ✓ Tạo bảng FaceLog")

    print(f"[locker_db] ✓ DB ready: {DB_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
#  USER & FACE EMBEDDING — Thêm, sửa, lưu, tải dữ liệu
# ══════════════════════════════════════════════════════════════════════════════

def add_or_update_user(mssv: str, name: str, role: str = 'student', is_approved: int = 0, has_face: int = 0) -> bool:
    """
    Thêm mới hoặc cập nhật thông tin sinh viên vào SQLite và đồng bộ trực tiếp lên Firebase.
    """
    with _conn() as con:
        row = con.execute("SELECT mssv FROM Users WHERE mssv=?", (mssv,)).fetchone()
        if row:
            con.execute(
                "UPDATE Users SET name=?, role=?, is_approved=?, has_face=? WHERE mssv=?",
                (name, role, is_approved, has_face, mssv)
            )
            print(f"[locker_db] ✓ Cập nhật user {mssv} thành công trong SQLite.")
        else:
            con.execute(
                "INSERT INTO Users (mssv, name, role, is_approved, has_face) VALUES (?, ?, ?, ?, ?)",
                (mssv, name, role, is_approved, has_face)
            )
            print(f"[locker_db] ✓ Thêm mới user {mssv} vào SQLite.")

    try:
        db.reference(f'users/{mssv}').update({
            'name': name,
            'role': role,
            'is_approved': int(is_approved),
            'has_face': bool(has_face)
        })
        print(f"[Firebase] 🟢 Đã đồng bộ thông tin user {mssv} lên Web Admin.")
        return True
    except Exception as e:
        print(f"[Firebase Lỗi] Không thể đồng bộ dữ liệu của {mssv}: {e}")
        return False

def sync_all_to_firebase() -> bool:
    """
    Đọc toàn bộ dữ liệu hiện tại từ SQLite (Users, Lockers) 
    và đẩy lên Firebase. Dùng phục hồi dữ liệu hoặc sau khi sửa bằng DB Browser.
    """
    print("[Sync] Đang bắt đầu đồng bộ toàn bộ dữ liệu từ SQLite lên Firebase...")
    
    users_dict = {}
    with _conn() as con:
        user_rows = con.execute("SELECT mssv, name, role, is_approved, has_face FROM Users").fetchall()
        for r in user_rows:
            mssv = r["mssv"]
            users_dict[mssv] = {
                'name': r["name"],
                'role': r["role"],
                'is_approved': int(r["is_approved"]),
                'has_face': bool(r["has_face"])
            }
            
    lockers_dict = {}
    with _conn() as con:
        locker_rows = con.execute("SELECT locker_id, status, current_mssv FROM Lockers").fetchall()
        for r in locker_rows:
            lid = r["locker_id"]
            status = str(r["status"]).lower()
            current_mssv = r["current_mssv"] if r["current_mssv"] else ""
            
            lockers_dict[lid] = {
                'status': status,
                'current_mssv': current_mssv,
                'last_open_time': '' 
            }

    try:
        if users_dict:
            db.reference('users').update(users_dict)
            print(f"[Firebase] 🟢 Đã đồng bộ {len(users_dict)} sinh viên.")
            
        if lockers_dict:
            db.reference('lockers').update(lockers_dict)
            print(f"[Firebase] 🟢 Đã đồng bộ {len(lockers_dict)} tủ khóa.")
            
        print("[Sync] ✓ ĐỒNG BỘ THÀNH CÔNG.")
        return True
    except Exception as e:
        print(f"[Firebase Lỗi] Đồng bộ thất bại: {e}")
        return False

def save_embedding(mssv: str, embedding: np.ndarray) -> bool:
    """Lưu face embedding và CHỈ bật cờ has_face cho user trên Web."""
    blob = pickle.dumps(embedding)
    with _conn() as con:
        cur = con.execute(
            "UPDATE Users SET face_embedding=?, has_face=1 WHERE mssv=?",
            (blob, mssv)
        )
        if cur.rowcount == 0:
            print(f"[locker_db] ✗ Không tìm thấy mssv='{mssv}' trong DB")
            return False
    print(f"[locker_db] ✓ Lưu embedding cho mssv='{mssv}'")

    try:
        db.reference(f'users/{mssv}').update({'has_face': True})
        print(f"[Firebase] 🟢 Bật thông báo 'Có khuôn mặt' cho {mssv} trên Web.")
    except Exception as e:
        print(f"[Firebase Lỗi] {e}")

    log_access('FACE_REGISTER', mssv=mssv)
    return True


def load_all_embeddings() -> dict[str, tuple[np.ndarray, str]]:
    """Tải toàn bộ face embedding. Trả về {mssv: (embedding, name)}."""
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
    """Lấy thông tin user theo mssv (không có rfid)."""
    with _conn() as con:
        row = con.execute(
            "SELECT mssv, name, role, is_approved, has_face "
            "FROM Users WHERE mssv=?", (mssv,)
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    """Liệt kê tất cả user."""
    with _conn() as con:
        rows = con.execute(
            "SELECT mssv, name, role, is_approved, has_face "
            "FROM Users ORDER BY name"
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
    """Xử lý sau khi xác thực thành công."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = get_user(mssv)
    name = user["name"] if user else "Unknown"

    # TRƯỜNG HỢP 1: Sinh viên đã có tủ
    locker = get_user_locker(mssv)
    if locker:
        lid = locker["locker_id"]   
        log_access("OPEN_LOCKER", mssv=mssv, name=name, locker_id=lid)

        try:
            db.reference(f'lockers/{lid}').update({
                'current_mssv'  : mssv,
                'status'        : 'occupied',
                'last_open_time': now_str
            })
            db.reference('logs').push({
                'time'     : now_str,
                'event'    : 'OPEN_LOCKER',
                'mssv'     : mssv,
                'name'     : name,
                'locker_id': lid
            })
            print(f"[Firebase] 🔓 Báo cáo MỞ TỦ {lid} lên Web.")
        except Exception as e:
            print(f"[Firebase Lỗi] {e}")

        return True, f"Mở tủ {lid} (đang dùng)"

    # TRƯỜNG HỢP 2: Chưa có tủ → Gán tủ trống mới
    with _conn() as con:
        row = con.execute(
            "SELECT locker_id FROM Lockers "
            "WHERE LOWER(status)='empty' AND current_mssv IS NULL "
            "ORDER BY locker_id LIMIT 1"
        ).fetchone()

        if not row:
            return False, "Không còn tủ trống!"

        lid = row["locker_id"]  
        con.execute(
            "UPDATE Lockers SET status='occupied', current_mssv=? "
            "WHERE locker_id=?", (mssv, lid)
        )

    log_access("ASSIGN_LOCKER", mssv=mssv, name=name, locker_id=lid)

    try:
        db.reference(f'lockers/{lid}').update({
            'current_mssv'  : mssv,
            'status'        : 'occupied',
            'last_open_time': now_str
        })
        db.reference('logs').push({
            'time'     : now_str,
            'event'    : 'ASSIGN_LOCKER',
            'mssv'     : mssv,
            'name'     : name,
            'locker_id': lid
        })
        print(f"[Firebase] 🆕 Báo cáo GÁN TỦ MỚI {lid} lên Web.")
    except Exception as e:
        print(f"[Firebase Lỗi] {e}")

    return True, f"Gán tủ mới {lid}"


def release_locker(mssv: str) -> tuple[bool, str]:
    """Trả tủ. Thường gọi từ UI admin."""
    locker = get_user_locker(mssv)
    if not locker:
        return False, f"mssv='{mssv}' không đang giữ tủ nào"

    lid = locker["locker_id"]
    user = get_user(mssv)
    name = user["name"] if user else "Unknown"

    with _conn() as con:
        con.execute(
            "UPDATE Lockers SET status='empty', current_mssv=NULL "
            "WHERE locker_id=?", (lid,)
        )

    log_access("RELEASE_LOCKER", mssv=mssv, name=name, locker_id=lid)

    try:
        db.reference(f'lockers/{lid}').update({
            'current_mssv': '',
            'status'      : 'empty'
        })
        db.reference('logs').push({
            'time'     : datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'event'    : 'RELEASE_LOCKER',
            'mssv'     : mssv,
            'name'     : name,
            'locker_id': lid
        })
        print(f"[Firebase] 🔒 Báo cáo TRẢ TỦ {lid} lên Web.")
    except Exception as e:
        print(f"[Firebase Lỗi] {e}")

    return True, f"Đã trả tủ {lid}"


# ══════════════════════════════════════════════════════════════════════════════
#  AUDIT LOG — ghi vào LockerLog hoặc FaceLog tùy loại event
# ══════════════════════════════════════════════════════════════════════════════

def log_access(event: str,
               mssv:      str = None,
               name:      str = None,
               locker_id: str = None) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")

    if name is None and mssv:
        user = get_user(mssv)
        if user:
            name = user["name"]

    if event in LOCKER_EVENTS:
        with _conn() as con:
            con.execute(
                "INSERT INTO LockerLog (timestamp, event, locker_id, mssv, name) "
                "VALUES (?,?,?,?,?)",
                (ts, event, locker_id, mssv, name)
            )
    else:
        with _conn() as con:
            con.execute(
                "INSERT INTO FaceLog (timestamp, event, mssv, name) "
                "VALUES (?,?,?,?)",
                (ts, event, mssv, name)
            )


def print_log(n: int = 20) -> None:
    """In log hợp nhất từ LockerLog + FaceLog, sắp xếp mới nhất lên trên."""
    with _conn() as con:
        rows = con.execute("""
            SELECT timestamp, event, mssv, name, locker_id, 'locker' as src
            FROM LockerLog
            UNION ALL
            SELECT timestamp, event, mssv, name, NULL as locker_id, 'face' as src
            FROM FaceLog
            ORDER BY timestamp DESC LIMIT ?
        """, (n,)).fetchall()

    if not rows:
        print("(Chưa có log nào)")
        return

    print(f"\n{'─'*72}")
    print(f"{'THỜI GIAN':<21} {'SỰ KIỆN':<18} {'MSSV':<12} {'TÊN':<18} TỦ")
    print(f"{'─'*72}")

    icons = {
        "OPEN_LOCKER"    : "🔓",
        "ASSIGN_LOCKER"  : "🆕",
        "RELEASE_LOCKER" : "🔒",
        "FACE_REGISTER"  : "📝",
        "FACE_VERIFY"    : "✅",
        "FACE_FAIL"      : "❌",
    }

    for row in rows:
        ts, ev, mssv, name, lid, src = tuple(row)
        icon  = icons.get(ev, "•")
        lid_s = str(lid) if lid else "—"
        print(f"{ts:<21} {icon} {ev:<16} {str(mssv or ''):<12} "
              f"{str(name or ''):<18} {lid_s}")
    print(f"{'─'*72}\n")


def export_log_csv(path: str = "access_log.csv") -> None:
    import csv
    with _conn() as con:
        rows = con.execute("""
            SELECT timestamp, event, mssv, name, locker_id
            FROM LockerLog
            UNION ALL
            SELECT timestamp, event, mssv, name, NULL
            FROM FaceLog
            ORDER BY timestamp
        """).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "event", "mssv", "name", "locker_id"])
        writer.writerows(rows)
    print(f"[log] Xuất {len(rows)} dòng → '{path}'")


# ══════════════════════════════════════════════════════════════════════════════
#  RATE LIMITING — dựa trên FaceLog
# ══════════════════════════════════════════════════════════════════════════════

def is_locked_out(mssv: str) -> tuple[bool, int]:
    cutoff = (datetime.datetime.now() -
              datetime.timedelta(seconds=LOCKOUT_SECS)).isoformat(timespec="seconds")
    with _conn() as con:
        (fails,) = con.execute(
            "SELECT COUNT(*) FROM FaceLog "
            "WHERE event='FACE_FAIL' AND mssv=? AND timestamp>=?",
            (mssv, cutoff)
        ).fetchone()

        if fails < MAX_FAILS:
            return False, 0

        row = con.execute(
            "SELECT timestamp FROM FaceLog "
            "WHERE event='FACE_FAIL' AND mssv=? ORDER BY id DESC LIMIT 1",
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
        print(f"\n{'MSSV':<12} {'TÊN':<20} {'ROLE':<10} {'APPROVED':<10} FACE")
        print("─" * 60)
        for u in users:
            face = "✓" if u["has_face"] else "✗"
            appr = "✓" if u["is_approved"] else "✗"
            print(f"{u['mssv']:<12} {u['name']:<20} {u['role']:<10} {appr:<10} {face}")
    elif cmd == "add_user" and len(sys.argv) > 3:
        mssv = sys.argv[2]
        name = sys.argv[3]
        role = sys.argv[4] if len(sys.argv) > 4 else "student"
        is_approved = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        add_or_update_user(mssv, name, role, is_approved, has_face=0)
    elif cmd == "sync_all":
        sync_all_to_firebase()
    elif cmd == "lockers":
        with _conn() as con:
            rows = con.execute(
                "SELECT l.locker_id, l.status, l.size, l.current_mssv, u.name "
                "FROM Lockers l LEFT JOIN Users u ON l.current_mssv=u.mssv "
                "ORDER BY l.locker_id"
            ).fetchall()
        print(f"\n{'TỦ':<6} {'STATUS':<12} {'SIZE':<8} {'MSSV':<12} TÊN")
        print("─" * 55)
        for r in rows:
            print(f"{r[0]:<6} {r[1]:<12} {str(r[2]).strip():<8} "
                  f"{str(r[3] or '—'):<12} {r[4] or ''}")
    elif cmd == "release" and len(sys.argv) > 2:
        ok, msg = release_locker(sys.argv[2])
        print(f"{'✓' if ok else '✗'} {msg}")
    else:
        print("Dùng: python locker_db.py [log|export|users|add_user <mssv> <tên>|sync_all|lockers|release <mssv>]")