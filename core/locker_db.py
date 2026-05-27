"""
core/locker_db.py — Thao tác Lockers: open, assign, release, get
Bao gồm: ghi LOCKER_DELETE_LOG, auto-cleanup tủ không dùng sau 7 ngày.
"""

import datetime
from firebase_admin import db as fdb

from core.db import _conn
from core.user_db import get_user
from core.log_db import log_access


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ── Truy vấn tủ ───────────────────────────────────────────────────────────────

def get_user_locker(mssv: str) -> dict | None:
    """Lấy tủ hiện tại của user. None nếu không có."""
    with _conn() as con:
        row = con.execute(
            "SELECT locker_id, status, size FROM Lockers "
            "WHERE current_mssv=? AND LOWER(status)='occupied'",
            (mssv,)
        ).fetchone()
    return dict(row) if row else None


def get_all_lockers() -> dict:
    """Return {locker_id: {status, size, current_mssv}}"""
    with _conn() as con:
        rows = con.execute(
            "SELECT locker_id, status, size, current_mssv FROM Lockers "
            "ORDER BY locker_id"
        ).fetchall()
    return {r["locker_id"]: dict(r) for r in rows}


# ── Ghi LOCKER_DELETE_LOG ──────────────────────────────────────────────────────

def log_locker_delete(mssv: str, locker_id: str, reason: str):
    """
    Ghi vào LOCKER_DELETE_LOG (local) + push lên Firebase /locker_delete_logs.
    reason: 'student_release' | 'auto_inactive_7days' | 'admin_force' | 'admin_deactivate'
    """
    now = _now_str()
    with _conn() as con:
        con.execute(
            """INSERT INTO LOCKER_DELETE_LOG (MSSV, LOCKER_ID, DELETE_TIME, REASON)
               VALUES (?, ?, ?, ?)""",
            (mssv, locker_id, now, reason)
        )
    print(f"[LOCKER_DELETE_LOG] mssv={mssv} locker={locker_id} reason={reason}")
    try:
        fdb.reference('locker_delete_logs').push({
            'mssv'       : mssv,
            'locker_id'  : locker_id,
            'delete_time': now,
            'reason'     : reason
        })
    except Exception as e:
        print(f"[Firebase Lỗi] log_locker_delete: {e}")


# ── Mở tủ ─────────────────────────────────────────────────────────────────────

def open_locker(mssv: str) -> tuple[bool, str]:
    """
    Mở tủ đang giữ. Nếu chưa có tủ → tự động gán tủ trống.
    Return (True, "Mở tủ L0X") hoặc (False, lý do).
    """
    now  = _now_str()
    user = get_user(mssv)
    name = user["name"] if user else "Unknown"
    locker = get_user_locker(mssv)

    if locker:
        lid = locker["locker_id"]
        log_access("OPEN_LOCKER", mssv=mssv, name=name, locker_id=lid)
        try:
            fdb.reference(f'lockers/{lid}').update({
                'current_mssv': mssv, 'status': 'occupied', 'last_open_time': now
            })
            fdb.reference('logs').push({
                'time': now, 'event': 'OPEN_LOCKER',
                'mssv': mssv, 'name': name, 'locker_id': lid
            })
        except Exception as e:
            print(f"[Firebase Lỗi] open_locker: {e}")
        return True, f"Mở tủ {lid}"

    # Chưa có tủ → tự gán tủ trống
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
            "UPDATE Lockers SET status='occupied', current_mssv=?, assigned_date=? WHERE locker_id=?",
            (mssv, now, lid)
        )

    log_access("ASSIGN_LOCKER", mssv=mssv, name=name, locker_id=lid)
    try:
        fdb.reference(f'lockers/{lid}').update({
            'current_mssv': mssv, 'status': 'occupied',
            'last_open_time': now, 'assigned_date': now
        })
        fdb.reference('logs').push({
            'time': now, 'event': 'ASSIGN_LOCKER',
            'mssv': mssv, 'name': name, 'locker_id': lid
        })
    except Exception as e:
        print(f"[Firebase Lỗi] open_locker (assign): {e}")

    return True, f"Gán tủ mới {lid}"


# ── Gán tủ (admin) ─────────────────────────────────────────────────────────────

def assign_locker(mssv: str, locker_id: str) -> bool:
    """Gán tủ cụ thể cho user (admin gọi từ GUI)."""
    now = _now_str()
    try:
        with _conn() as con:
            con.execute(
                "UPDATE Lockers SET status='occupied', current_mssv=?, assigned_date=? WHERE locker_id=?",
                (mssv, now, locker_id)
            )
        fdb.reference(f'lockers/{locker_id}').update({
            'status': 'occupied', 'current_mssv': mssv, 'assigned_date': now
        })
        print(f"[Firebase] 🟢 Gán tủ {locker_id} cho {mssv}")
        return True
    except Exception as e:
        print(f"[Firebase Lỗi] assign_locker: {e}")
        return False


# ── Trả tủ (sinh viên chủ động) ────────────────────────────────────────────────

def release_locker(mssv: str) -> tuple[bool, str]:
    """
    Sinh viên bấm 'Trả tủ'.
    Ghi LockerLog (sync Firebase) + LOCKER_DELETE_LOG (local, reason=student_release).
    """
    locker = get_user_locker(mssv)
    if not locker:
        return False, f"mssv='{mssv}' không đang giữ tủ nào"

    lid  = locker["locker_id"]
    user = get_user(mssv)
    name = user["name"] if user else "Unknown"

    with _conn() as con:
        con.execute(
            "UPDATE Lockers SET status='empty', current_mssv=NULL, assigned_date=NULL WHERE locker_id=?",
            (lid,)
        )

    # Ghi LockerLog → sync Firebase
    log_access("RELEASE_LOCKER", mssv=mssv, name=name, locker_id=lid)

    # Ghi LOCKER_DELETE_LOG → local only
    log_locker_delete(mssv, lid, "student_release")

    try:
        fdb.reference(f'lockers/{lid}').update({
            'current_mssv': '', 'status': 'empty', 'assigned_date': ''
        })
        fdb.reference('logs').push({
            'time': _now_str(), 'event': 'RELEASE_LOCKER',
            'mssv': mssv, 'name': name, 'locker_id': lid
        })
    except Exception as e:
        print(f"[Firebase Lỗi] release_locker: {e}")

    return True, f"Đã trả tủ {lid}"


# ── Auto-cleanup tủ không dùng ─────────────────────────────────────────────────

def get_inactive_lockers(days: int) -> list[dict]:
    """
    Trả danh sách tủ đang occupied nhưng không có OPEN_LOCKER
    trong 'days' ngày qua.
    Mỗi item: {mssv, locker_id, name, last_open}
    """
    cutoff = (
        datetime.datetime.now() - datetime.timedelta(days=days)
    ).isoformat(timespec="seconds")

    with _conn() as con:
        rows = con.execute(
            """
            SELECT l.current_mssv  AS mssv,
                   l.locker_id,
                   u.name,
                   MAX(lg.timestamp) AS last_open
            FROM   Lockers l
            LEFT JOIN Users     u  ON u.mssv      = l.current_mssv
            LEFT JOIN LockerLog lg ON lg.locker_id = l.locker_id
                                  AND lg.event     = 'OPEN_LOCKER'
            WHERE  LOWER(l.status) = 'occupied'
            GROUP  BY l.locker_id
            HAVING last_open IS NULL OR last_open < ?
            """,
            (cutoff,)
        ).fetchall()

    return [dict(r) for r in rows]


def auto_cleanup_inactive(
    warn_callback=None,
    delete_days: int = 7,
    warn_days:   int = 6,
) -> dict:
    """
    Gọi định kỳ (mỗi 1 giờ từ background thread).

    Bước 1 — Cảnh báo (ngày thứ 6):
        Gọi warn_callback(mssv, locker_id, name, last_open) nếu được truyền vào.

    Bước 2 — Xóa (ngày thứ 7):
        release_locker() + log_locker_delete(reason='auto_inactive_7days').

    Return: {'warned': [...], 'deleted': [...]}
    """
    warned  = []
    deleted = []

    # Lấy tủ không dùng ≥ warn_days (bao gồm cả ≥ delete_days)
    candidates = get_inactive_lockers(days=warn_days)

    for c in candidates:
        mssv      = c["mssv"]
        locker_id = c["locker_id"]
        name      = c["name"] or "Unknown"
        last_open = c["last_open"]

        # Xác định đã đủ delete_days chưa
        if last_open is None:
            should_delete = True
        else:
            inactive_since = datetime.datetime.fromisoformat(last_open)
            idle_days = (datetime.datetime.now() - inactive_since).days
            should_delete = idle_days >= delete_days

        if should_delete:
            # --- XÓA ---
            ok, msg = release_locker(mssv)
            if ok:
                # release_locker đã ghi log_locker_delete(reason='student_release')
                # Ghi lại đúng reason auto
                log_locker_delete(mssv, locker_id, "auto_inactive_7days")
                print(f"[AutoCleanup] 🗑 Xóa tủ {locker_id} của {mssv} ({name}) — {last_open or 'chưa dùng lần nào'}")
                deleted.append({"mssv": mssv, "locker_id": locker_id, "name": name})
        else:
            # --- CẢNH BÁO ---
            print(f"[AutoCleanup] ⚠ Cảnh báo tủ {locker_id} của {mssv} ({name}) — last_open={last_open}")
            if warn_callback:
                try:
                    warn_callback(mssv, locker_id, name, last_open)
                except Exception as e:
                    print(f"[AutoCleanup] warn_callback lỗi: {e}")
            warned.append({"mssv": mssv, "locker_id": locker_id, "name": name, "last_open": last_open})

    return {"warned": warned, "deleted": deleted}


# ── Sync toàn bộ Lockers lên Firebase ─────────────────────────────────────────

def sync_lockers_to_firebase() -> bool:
    """Push toàn bộ Lockers table lên Firebase (dùng cho sync_tool)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT locker_id, status, current_mssv, assigned_date FROM Lockers"
        ).fetchall()
    lockers_dict = {
        r["locker_id"]: {
            'status'        : str(r["status"]).lower(),
            'current_mssv'  : r["current_mssv"] or '',
            'last_open_time': '',
            'assigned_date' : r["assigned_date"] or ''
        }
        for r in rows
    }
    try:
        if lockers_dict:
            fdb.reference('lockers').update(lockers_dict)
            print(f"[Firebase] 🟢 Đồng bộ {len(lockers_dict)} tủ.")
        return True
    except Exception as e:
        print(f"[Firebase Lỗi] sync_lockers: {e}")
        return False