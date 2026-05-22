"""
core/locker_db.py — Thao tác Lockers: open, assign, release, get
"""

import datetime
from firebase_admin import db as fdb

from core.db import _conn
from core.user_db import get_user
from core.log_db import log_access


def get_user_locker(mssv: str) -> dict | None:
    """Lấy tủ hiện tại của user. None nếu không có."""
    with _conn() as con:
        row = con.execute(
            "SELECT locker_id, status, size FROM Lockers WHERE current_mssv=?",
            (mssv,)
        ).fetchone()
    return dict(row) if row else None


def get_all_lockers() -> dict:
    """Return {locker_id: {status, size, current_mssv}}"""
    with _conn() as con:
        rows = con.execute(
            "SELECT locker_id, status, size, current_mssv FROM Lockers"
        ).fetchall()
    return {r["locker_id"]: dict(r) for r in rows}


def open_locker(mssv: str) -> tuple[bool, str]:
    """
    Mở tủ đang giữ. Nếu chưa có tủ → tự động gán tủ trống.
    Return (True, "Mở tủ L0X") hoặc (False, lý do).
    """
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user    = get_user(mssv)
    name    = user["name"] if user else "Unknown"
    locker  = get_user_locker(mssv)

    if locker:
        lid = locker["locker_id"]
        log_access("OPEN_LOCKER", mssv=mssv, name=name, locker_id=lid)
        try:
            fdb.reference(f'lockers/{lid}').update({
                'current_mssv': mssv, 'status': 'occupied', 'last_open_time': now_str
            })
            fdb.reference('logs').push({
                'time': now_str, 'event': 'OPEN_LOCKER',
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
            "UPDATE Lockers SET status='occupied', current_mssv=? WHERE locker_id=?",
            (mssv, lid)
        )

    log_access("ASSIGN_LOCKER", mssv=mssv, name=name, locker_id=lid)
    try:
        fdb.reference(f'lockers/{lid}').update({
            'current_mssv': mssv, 'status': 'occupied', 'last_open_time': now_str
        })
        fdb.reference('logs').push({
            'time': now_str, 'event': 'ASSIGN_LOCKER',
            'mssv': mssv, 'name': name, 'locker_id': lid
        })
    except Exception as e:
        print(f"[Firebase Lỗi] open_locker (assign): {e}")

    return True, f"Gán tủ mới {lid}"


def assign_locker(mssv: str, locker_id: str) -> bool:
    """Gán tủ cụ thể cho user (admin gọi từ GUI)."""
    try:
        with _conn() as con:
            con.execute(
                "UPDATE Lockers SET status='occupied', current_mssv=? WHERE locker_id=?",
                (mssv, locker_id)
            )
        fdb.reference(f'lockers/{locker_id}').update({
            'status': 'occupied', 'current_mssv': mssv
        })
        print(f"[Firebase] 🟢 Gán tủ {locker_id} cho {mssv}")
        return True
    except Exception as e:
        print(f"[Firebase Lỗi] assign_locker: {e}")
        return False


def release_locker(mssv: str) -> tuple[bool, str]:
    """Trả tủ cho user."""
    locker = get_user_locker(mssv)
    if not locker:
        return False, f"mssv='{mssv}' không đang giữ tủ nào"

    lid  = locker["locker_id"]
    user = get_user(mssv)
    name = user["name"] if user else "Unknown"

    with _conn() as con:
        con.execute(
            "UPDATE Lockers SET status='empty', current_mssv=NULL WHERE locker_id=?",
            (lid,)
        )

    log_access("RELEASE_LOCKER", mssv=mssv, name=name, locker_id=lid)
    try:
        fdb.reference(f'lockers/{lid}').update({'current_mssv': '', 'status': 'empty'})
        fdb.reference('logs').push({
            'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'event': 'RELEASE_LOCKER', 'mssv': mssv, 'name': name, 'locker_id': lid
        })
    except Exception as e:
        print(f"[Firebase Lỗi] release_locker: {e}")

    return True, f"Đã trả tủ {lid}"


def sync_lockers_to_firebase() -> bool:
    """Push toàn bộ Lockers table lên Firebase (dùng cho sync_tool)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT locker_id, status, current_mssv FROM Lockers"
        ).fetchall()
    lockers_dict = {
        r["locker_id"]: {
            'status'      : str(r["status"]).lower(),
            'current_mssv': r["current_mssv"] or '',
            'last_open_time': ''
        }
        for r in rows
    }
    try:
        if lockers_dict:
            from firebase_admin import db as fdb
            fdb.reference('lockers').update(lockers_dict)
            print(f"[Firebase] 🟢 Đồng bộ {len(lockers_dict)} tủ.")
        return True
    except Exception as e:
        print(f"[Firebase Lỗi] sync_lockers: {e}")
        return False
