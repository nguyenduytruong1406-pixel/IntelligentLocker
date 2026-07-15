"""
app/services/firebase_hooks.py — Push dữ liệu lên Firebase sau mỗi thao tác tủ.

Tất cả hàm đều fail-safe: nếu Firebase offline → in log, không crash app.
Dùng chung cho LockerService và CleanupService.
"""

from __future__ import annotations
from datetime import datetime


# ── Helper lấy fdb an toàn ────────────────────────────────────────────────────
def _fdb():
    """Trả firebase_admin.db nếu Firebase đã init, None nếu offline."""
    try:
        from app.firebase_config import FIREBASE_OK
        if not FIREBASE_OK:
            return None
        from firebase_admin import db
        return db
    except Exception:
        return None


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Push sau khi BORROW (gán tủ) ──────────────────────────────────────────────
def push_borrow(mssv: str, locker_id: str, name: str, assigned_date: str = ""):
    """
    Cập nhật Firebase sau khi sinh viên được gán tủ:
      /lockers/{id}       → status=occupied, current_mssv, assigned_date, last_open
      /locker_delete_logs → push "new_assignment" (audit — hiển thị ở tab Lịch Sử Tủ)
    Lưu ý: KHÔNG push vào /logs nữa — /logs (Nhật Ký) chỉ dành cho lịch sử
    dùng tủ thực tế (mở tủ), gán/trả tủ xem ở tab Lịch Sử Tủ.
    """
    fdb = _fdb()
    if not fdb:
        return
    now = assigned_date or _now()
    try:
        fdb.reference(f"lockers/{locker_id}").update({
            "status"       : "occupied",
            "current_mssv" : mssv,
            "assigned_date": now,
            "last_open"    : now,
        })
        fdb.reference("locker_delete_logs").push({
            "mssv"       : mssv,
            "locker_id"  : locker_id,
            "delete_time": now,
            "reason"     : "new_assignment",
            "name"       : name,
        })
        print(f"[Firebase] 🟢 BORROW tủ {locker_id} → {mssv}")
    except Exception as e:
        print(f"[Firebase] ✗ push_borrow {locker_id}: {e}")


# ── Push sau khi OPEN (mở tủ đã mượn) ────────────────────────────────────────
def push_open(mssv: str, locker_id: str, name: str):
    """
    Cập nhật Firebase sau khi sinh viên mở tủ (trả lại đồ):
      /lockers/{id} → last_open
      /logs         → push OPEN_LOCKER
    """
    fdb = _fdb()
    if not fdb:
        return
    now = _now()
    try:
        fdb.reference(f"lockers/{locker_id}").update({
            "last_open": now,
        })
        fdb.reference("logs").push({
            "time"     : now,
            "event"    : "OPEN_LOCKER",
            "mssv"     : mssv,
            "name"     : name,
            "locker_id": locker_id,
        })
        print(f"[Firebase] 🔓 OPEN tủ {locker_id} bởi {mssv}")
    except Exception as e:
        print(f"[Firebase] ✗ push_open {locker_id}: {e}")


# ── Push sau khi RETURN (trả tủ) ──────────────────────────────────────────────
def push_return(mssv: str, locker_id: str, name: str, reason: str = "student_release"):
    """
    Cập nhật Firebase sau khi sinh viên trả tủ:
      /lockers/{id}       → status=empty, current_mssv='', assigned_date='', last_open=''
      /locker_delete_logs → push log (audit — hiển thị ở tab Lịch Sử Tủ)
    Lưu ý: KHÔNG push vào /logs — xem ghi chú ở push_borrow().
    """
    fdb = _fdb()
    if not fdb:
        return
    now = _now()
    try:
        fdb.reference(f"lockers/{locker_id}").update({
            "status"       : "empty",
            "current_mssv" : "",
            "assigned_date": "",
            "last_open"    : "",
        })
        fdb.reference("locker_delete_logs").push({
            "mssv"       : mssv,
            "locker_id"  : locker_id,
            "delete_time": now,
            "reason"     : reason,
            "name"       : name,
        })
        print(f"[Firebase] 🔒 RETURN tủ {locker_id} bởi {mssv} ({reason})")
    except Exception as e:
        print(f"[Firebase] ✗ push_return {locker_id}: {e}")


# ── Push sau khi REGISTER (đăng ký user mới) ─────────────────────────────────
def push_register(mssv: str, name: str, email: str, password: str = None):
    print(f"[DEBUG push_register] vào hàm, mssv={mssv}")   # ← thêm
    fdb = _fdb()
    print(f"[DEBUG push_register] fdb={fdb}")               # ← thêm
    if not fdb:
        print("[DEBUG] fdb=None, bỏ qua!")                  # ← thêm
        return
    now = _now()
    try:
        data = {
            "name"         : name,
            "role"         : "student",
            "is_approved"  : 0,
            "has_face"     : False,
            "email"        : email,
            "registered_at": now,
        }
        if password:
            data["password"] = password
        fdb.reference(f"users/{mssv}").set(data)
        print(f"[Firebase] 👤 Đăng ký user {mssv} lên Firebase")
    except Exception as e:
        print(f"[Firebase] ✗ push_register {mssv}: {e}")


# ── Push sau khi lưu face embedding ──────────────────────────────────────────
def push_has_face(mssv: str):
    """Cập nhật has_face=True trên Firebase sau khi lưu embedding thành công."""
    fdb = _fdb()
    if not fdb:
        return
    try:
        fdb.reference(f"users/{mssv}").update({"has_face": True})
        print(f"[Firebase] 🤖 has_face=True cho {mssv}")
    except Exception as e:
        print(f"[Firebase] ✗ push_has_face {mssv}: {e}")


# ── Push sau khi đổi mật khẩu (tắt is_first_login) ────────────────────────────
def push_password_changed(mssv: str, new_password: str):
    """Đồng bộ mật khẩu mới + is_first_login=False lên Firebase sau khi user tự đổi."""
    fdb = _fdb()
    if not fdb:
        return
    try:
        fdb.reference(f"users/{mssv}").update({
            "password": new_password,
            "is_first_login": False,
        })
        print(f"[Firebase] 🔑 Đã đổi mật khẩu cho {mssv}")
    except Exception as e:
        print(f"[Firebase] ✗ push_password_changed {mssv}: {e}")


# ── Push kiosk heartbeat ──────────────────────────────────────────────────────
def push_heartbeat():
    """Ghi /kiosk_status/last_seen — gọi từ _heartbeat_loop."""
    fdb = _fdb()
    if not fdb:
        return
    try:
        from datetime import timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fdb.reference("kiosk_status").update({"last_seen": ts})
    except Exception as e:
        print(f"[Heartbeat] ✗ {e}")


# ── Push locker_delete_log (auto cleanup) ────────────────────────────────────
def push_delete_log(mssv: str, locker_id: str, reason: str, name: str = ""):
    """Ghi /locker_delete_logs — dùng khi auto_cleanup_inactive."""
    fdb = _fdb()
    if not fdb:
        return
    now = _now()
    try:
        fdb.reference("locker_delete_logs").push({
            "mssv"       : mssv,
            "locker_id"  : locker_id,
            "delete_time": now,
            "reason"     : reason,
            "name"       : name,
        })
    except Exception as e:
        print(f"[Firebase] ✗ push_delete_log: {e}")