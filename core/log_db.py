"""
core/log_db.py — Audit log (LockerLog + FaceLog) + Rate limiting + Export
"""

import csv
import datetime
from core.db import _conn, LOCKER_EVENTS, MAX_FAILS, LOCKOUT_SECS


# ── Ghi log ───────────────────────────────────────────────────────────────────

def log_access(event: str, mssv: str = None,
               name: str = None, locker_id: str = None) -> None:
    """
    Ghi log vào LockerLog (OPEN/ASSIGN/RELEASE) hoặc FaceLog (REGISTER/VERIFY/FAIL).
    name tự động lấy từ DB nếu không truyền.
    """
    ts = datetime.datetime.now().isoformat(timespec="seconds")

    if name is None and mssv:
        # Lazy import tránh circular
        from core.user_db import get_user
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
                "INSERT INTO FaceLog (timestamp, event, mssv, name) VALUES (?,?,?,?)",
                (ts, event, mssv, name)
            )


# ── Xem log ───────────────────────────────────────────────────────────────────

def print_log(n: int = 20) -> None:
    with _conn() as con:
        rows = con.execute("""
            SELECT timestamp, event, mssv, name, locker_id FROM LockerLog
            UNION ALL
            SELECT timestamp, event, mssv, name, NULL FROM FaceLog
            ORDER BY timestamp DESC LIMIT ?
        """, (n,)).fetchall()

    if not rows:
        print("(Chưa có log nào)")
        return

    icons = {
        "OPEN_LOCKER"   : "🔓", "ASSIGN_LOCKER" : "🆕", "RELEASE_LOCKER": "🔒",
        "FACE_REGISTER" : "📝", "FACE_VERIFY"   : "✅", "FACE_FAIL"     : "❌",
    }
    print(f"\n{'─'*72}")
    print(f"{'THỜI GIAN':<21} {'SỰ KIỆN':<18} {'MSSV':<12} {'TÊN':<18} TỦ")
    print(f"{'─'*72}")
    for row in rows:
        ts, ev, mssv, name, lid = tuple(row)
        print(f"{ts:<21} {icons.get(ev,'•')} {ev:<16} {str(mssv or ''):<12} "
              f"{str(name or ''):<18} {lid or '—'}")
    print(f"{'─'*72}\n")


def export_log_csv(path: str = "access_log.csv") -> None:
    with _conn() as con:
        rows = con.execute("""
            SELECT timestamp, event, mssv, name, locker_id FROM LockerLog
            UNION ALL
            SELECT timestamp, event, mssv, name, NULL FROM FaceLog
            ORDER BY timestamp
        """).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "event", "mssv", "name", "locker_id"])
        writer.writerows(rows)
    print(f"[log] Xuất {len(rows)} dòng → '{path}'")


# ── Rate limiting ─────────────────────────────────────────────────────────────

def is_locked_out(mssv: str) -> tuple[bool, int]:
    """
    Return (True, seconds_remaining) nếu bị khóa,
           (False, 0) nếu bình thường.
    """
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

    last      = datetime.datetime.fromisoformat(row[0])
    remaining = int(LOCKOUT_SECS - (datetime.datetime.now() - last).total_seconds())
    return (True, remaining) if remaining > 0 else (False, 0)
