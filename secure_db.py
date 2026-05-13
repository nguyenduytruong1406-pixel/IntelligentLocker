"""
secure_db.py — Mã hóa AES-256-GCM + Audit log SQLite
Import module này vào enroll.py, verify.py, verify_with_liveness.py

Cài thêm: pip install cryptography
"""

import os
import pickle
import sqlite3
import hashlib
import secrets
import datetime
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ── Cấu hình ──────────────────────────────────────────────────────────────────
KEY_FILE   = "db.key"          # File lưu master key (bảo vệ file này!)
DB_PATH    = "face_db.enc"     # face_db dạng mã hóa (thay .pkl cũ)
LOG_PATH   = "audit.db"        # SQLite audit log
# ──────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
#  PHẦN 1 — MÃ HÓA AES-256-GCM
# ══════════════════════════════════════════════════════════════════════════════

def _load_or_create_key() -> bytes:
    """
    Load master key từ KEY_FILE, hoặc tạo mới nếu chưa có.
    Key 256-bit (32 bytes) random, lưu dạng hex.
    CẢNH BÁO: Mất file này = mất toàn bộ dữ liệu khuôn mặt!
    """
    key_path = Path(KEY_FILE)
    if key_path.exists():
        return bytes.fromhex(key_path.read_text().strip())

    # Tạo key mới
    key = secrets.token_bytes(32)
    key_path.write_text(key.hex())

    # Đặt quyền chỉ owner đọc được (Windows: không enforce nhưng vẫn ghi)
    try:
        os.chmod(KEY_FILE, 0o600)
    except Exception:
        pass

    print(f"[SECURE] Đã tạo master key mới → '{KEY_FILE}'")
    print(f"         ⚠️  Backup file này! Mất key = mất toàn bộ dữ liệu.")
    return key


def save_face_db(db: dict, path: str = DB_PATH) -> None:
    """Serialize dict → pickle → mã hóa AES-256-GCM → ghi file."""
    key   = _load_or_create_key()
    aesgcm = AESGCM(key)
    nonce  = secrets.token_bytes(12)          # 96-bit nonce, random mỗi lần

    plaintext  = pickle.dumps(db)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # Format: [12 bytes nonce][ciphertext + 16 bytes GCM tag]
    with open(path, "wb") as f:
        f.write(nonce + ciphertext)

    print(f"[SECURE] Đã lưu DB mã hóa → '{path}'  ({len(db)} người dùng)")


def load_face_db(path: str = DB_PATH) -> dict:
    """Đọc file → giải mã AES-256-GCM → deserialize dict."""
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Không tìm thấy '{path}'. Chạy enroll.py để tạo mới."
        )

    key    = _load_or_create_key()
    aesgcm = AESGCM(key)

    with open(path, "rb") as f:
        data = f.read()

    nonce      = data[:12]
    ciphertext = data[12:]

    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError(
            "Giải mã thất bại! Key sai hoặc file bị chỉnh sửa."
        )

    return pickle.loads(plaintext)


def migrate_from_pkl(old_pkl: str = "face_db.pkl") -> bool:
    """
    Chuyển đổi face_db.pkl cũ (plaintext) sang face_db.enc (mã hóa).
    Gọi 1 lần duy nhất sau khi cập nhật code.
    """
    if not Path(old_pkl).exists():
        return False

    print(f"[MIGRATE] Tìm thấy '{old_pkl}' cũ → đang chuyển sang mã hóa...")
    with open(old_pkl, "rb") as f:
        db = pickle.load(f)

    save_face_db(db)

    # Đổi tên file cũ thay vì xóa (an toàn hơn)
    os.rename(old_pkl, old_pkl + ".bak")
    print(f"[MIGRATE] Xong! File cũ đổi tên → '{old_pkl}.bak' (có thể xóa sau)")
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  PHẦN 2 — AUDIT LOG (SQLite)
# ══════════════════════════════════════════════════════════════════════════════

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(LOG_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            event       TEXT    NOT NULL,   -- 'ENROLL' | 'VERIFY_PASS' | 'VERIFY_FAIL' | 'VERIFY_ABORT'
            person      TEXT,               -- tên người dùng
            face_dist   REAL,               -- khoảng cách embedding (NULL nếu không detect được)
            live_prob   REAL,               -- xác suất liveness (NULL nếu không dùng IR)
            ip_hint     TEXT,               -- thông tin thêm (tuỳ chọn)
            notes       TEXT                -- ghi chú thêm
        )
    """)
    conn.commit()
    return conn


def log_event(event: str,
              person:    str  = None,
              face_dist: float = None,
              live_prob: float = None,
              notes:     str  = None) -> None:
    """
    Ghi 1 dòng vào audit log.

    event: 'ENROLL' | 'VERIFY_PASS' | 'VERIFY_FAIL' | 'VERIFY_ABORT'
    """
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO audit_log (timestamp, event, person, face_dist, live_prob, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, event, person, face_dist, live_prob, notes)
        )
        conn.commit()
    finally:
        conn.close()


def print_log(n: int = 20) -> None:
    """In N dòng log gần nhất ra terminal."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT timestamp, event, person, face_dist, live_prob, notes "
            "FROM audit_log ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("(Chưa có log nào)")
        return

    print(f"\n{'─'*72}")
    print(f"{'THỜI GIAN':<22} {'SỰ KIỆN':<15} {'NGƯỜI':<10} {'DIST':<7} {'LIVE':<6} GHI CHÚ")
    print(f"{'─'*72}")
    for ts, ev, person, dist, live, notes in rows:
        icon = {"ENROLL":       "📝",
                "VERIFY_PASS":  "✅",
                "VERIFY_FAIL":  "❌",
                "VERIFY_ABORT": "⚠️"}.get(ev, "•")
        dist_s = f"{dist:.3f}" if dist is not None else "  —  "
        live_s = f"{live:.2f}" if live is not None else "  —  "
        print(f"{ts:<22} {icon} {ev:<13} {str(person):<10} {dist_s:<7} {live_s:<6} {notes or ''}")
    print(f"{'─'*72}\n")


def export_log_csv(path: str = "audit_log.csv") -> None:
    """Xuất toàn bộ log ra CSV."""
    import csv
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT timestamp, event, person, face_dist, live_prob, notes "
            "FROM audit_log ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "event", "person", "face_dist", "live_prob", "notes"])
        writer.writerows(rows)

    print(f"[LOG] Đã xuất {len(rows)} dòng → '{path}'")


# ══════════════════════════════════════════════════════════════════════════════
#  PHẦN 3 — RATE LIMITING (chống brute-force)
# ══════════════════════════════════════════════════════════════════════════════

MAX_FAILS    = 5      # Số lần thất bại tối đa trước khi khóa
LOCKOUT_SECS = 60     # Thời gian khóa (giây)


def _count_recent_fails(person: str, window_secs: int = LOCKOUT_SECS) -> int:
    """Đếm số lần VERIFY_FAIL trong window_secs giây gần nhất."""
    cutoff = (datetime.datetime.now() -
              datetime.timedelta(seconds=window_secs)).isoformat(timespec="seconds")
    conn = _get_conn()
    try:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM audit_log "
            "WHERE event='VERIFY_FAIL' AND person=? AND timestamp >= ?",
            (person, cutoff)
        ).fetchone()
    finally:
        conn.close()
    return count


def is_locked_out(person: str) -> tuple[bool, int]:
    """
    Trả về (bị_khóa, giây_còn_lại).
    Nếu số lần fail gần đây >= MAX_FAILS → bị khóa.
    """
    fails = _count_recent_fails(person)
    if fails < MAX_FAILS:
        return False, 0

    # Tìm thời điểm fail gần nhất
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT timestamp FROM audit_log "
            "WHERE event='VERIFY_FAIL' AND person=? "
            "ORDER BY id DESC LIMIT 1", (person,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return False, 0

    last_fail = datetime.datetime.fromisoformat(row[0])
    elapsed   = (datetime.datetime.now() - last_fail).total_seconds()
    remaining = int(LOCKOUT_SECS - elapsed)

    if remaining > 0:
        return True, remaining
    return False, 0


# ── Chạy thử khi gọi trực tiếp ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "log":
        print_log(50)
    elif len(sys.argv) > 1 and sys.argv[1] == "export":
        export_log_csv()
    elif len(sys.argv) > 1 and sys.argv[1] == "migrate":
        ok = migrate_from_pkl()
        if not ok:
            print("Không tìm thấy face_db.pkl để migrate.")
    else:
        print("Dùng: python secure_db.py [log|export|migrate]")
        print("  log     — In 50 dòng log gần nhất")
        print("  export  — Xuất toàn bộ log ra audit_log.csv")
        print("  migrate — Chuyển face_db.pkl cũ sang face_db.enc mã hóa")
