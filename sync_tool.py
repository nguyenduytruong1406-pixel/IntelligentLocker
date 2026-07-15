#!/usr/bin/env python3
"""
sync_tool.py — Đồng bộ 2 chiều SQLite ↔ Firebase (chạy 1 lần khi boot)

Dùng trong SML:
    python sync_tool.py            # --sync (mặc định)
    python sync_tool.py --pull     # chỉ kéo Firebase → SQLite
    python sync_tool.py --push     # chỉ đẩy SQLite → Firebase

Logic giữ nguyên từ IntelligentLocker/sync_tool.py.
Chỉ thay đổi: dùng app/firebase_config.py + app/database/database.py của SML.
"""

import sys
from pathlib import Path
from datetime import datetime

# ── 1. Firebase — dùng chung firebase_config của SML ─────────────────────────
from app.firebase_config import FIREBASE_OK
if not FIREBASE_OK:
    print("[SyncTool] ⚠ Firebase offline — bỏ qua sync.")
    sys.exit(0)

from firebase_admin import db as fdb

# ── 2. SQLite — dùng Database class của SML ───────────────────────────────────
from app.database.database import Database

_db  = Database()
con  = _db.connect()
cur  = con.cursor()


def _now_iso() -> str:
    """Timestamp dạng 'YYYY-MM-DD HH:MM:SS' — sortable, khớp định dạng
    assigned_date/delete_time đã chuẩn hoá bên web (index.html)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS — đọc dữ liệu
# ══════════════════════════════════════════════════════════════════════════════

def get_sqlite_users() -> dict:
    cur.execute(
        "SELECT mssv, name, has_face, role, face_embedding, email, password, is_first_login "
        "FROM Users"
    )
    return {r["mssv"]: dict(r) for r in cur.fetchall()}


def get_firebase_users() -> dict:
    return fdb.reference("users").get() or {}


def get_sqlite_lockers() -> dict:
    cur.execute(
        "SELECT locker_id, status, size, current_mssv, last_open, assigned_date "
        "FROM Lockers"
    )
    return {r["locker_id"]: dict(r) for r in cur.fetchall()}


def get_delete_logs() -> tuple[set, dict]:
    """
    Đọc locker_delete_logs từ Firebase.
    Return:
      admin_deleted_mssv : set MSSV bị admin xóa hoàn toàn
      released_lockers   : {mssv: {locker_id: delete_time_gần_nhất}} — lần trả
                            tủ GẦN NHẤT của mỗi cặp (mssv, locker_id). Dùng để
                            so sánh với assigned_date hiện tại trong push():
                            nếu locker đã được GÁN LẠI hợp lệ sau lần trả này
                            (assigned_date mới hơn delete_time) thì KHÔNG được
                            coi là "còn sót lại chưa dọn" nữa — tránh xóa nhầm
                            lần gán mới chỉ vì trùng (mssv, locker_id) với 1
                            log trả tủ cũ (log không bao giờ bị xóa/hết hạn).
    """
    snap = fdb.reference("locker_delete_logs").get() or {}
    admin_deleted_mssv: set  = set()
    released_lockers:   dict = {}

    for entry in snap.values():
        reason = entry.get("reason", "")
        mssv   = entry.get("mssv", "")
        lid    = entry.get("locker_id", "")
        dtime  = entry.get("delete_time", "") or ""

        if reason == "admin_delete_card" and mssv:
            admin_deleted_mssv.add(mssv)
        elif reason == "student_release" and mssv and lid and lid != "—":
            bucket = released_lockers.setdefault(mssv, {})
            # Giữ lần trả GẦN NHẤT nếu có nhiều lần trả cùng cặp (mssv, locker_id)
            if lid not in bucket or dtime > bucket[lid]:
                bucket[lid] = dtime

    return admin_deleted_mssv, released_lockers


# ══════════════════════════════════════════════════════════════════════════════
#  PULL — Firebase → SQLite
# ══════════════════════════════════════════════════════════════════════════════

def pull(sqlite_users: dict, firebase_users: dict, dry_run: bool = False):
    added = updated = deleted = 0
    fb_set = set(firebase_users.keys())
    sq_set = set(sqlite_users.keys())

    # Firebase → SQLite: thêm / cập nhật
    for mssv, fb in firebase_users.items():
        name        = fb.get("name", "Unknown")
        role        = fb.get("role", "student")
        fb_has_face = 1 if fb.get("has_face") else 0
        email       = fb.get("email", "")
        password_fb = fb.get("password")
        # None nếu Firebase chưa có field này — giữ nguyên giá trị SQLite
        fb_first_login = fb.get("is_first_login")

        if mssv in sqlite_users:
            sq          = sqlite_users[mssv]
            sq_email    = sq.get("email") or ""
            sq_password = sq.get("password")
            sq_first_login = 1 if sq.get("is_first_login") is None else int(sq.get("is_first_login"))

            merged_has_face = max(int(sq["has_face"] or 0), fb_has_face)
            final_password  = password_fb if password_fb else sq_password
            final_first_login = int(bool(fb_first_login)) if fb_first_login is not None else sq_first_login

            changed = (
                sq["name"] != name
                or (sq["role"] or "student") != role
                or int(sq["has_face"] or 0) != merged_has_face
                or sq_email != email
                or sq_password != final_password
                or sq_first_login != final_first_login
            )
            if changed:
                print(f"  [UPDATE] {name} ({mssv})")
                if not dry_run:
                    cur.execute(
                        "UPDATE Users SET name=?, role=?, has_face=?, "
                        "email=?, password=?, is_first_login=? WHERE mssv=?",
                        (name, role, merged_has_face, email, final_password, final_first_login, mssv),
                    )
                updated += 1
        else:
            new_first_login = int(bool(fb_first_login)) if fb_first_login is not None else 1
            print(f"  [ADD→SQLite] {name} ({mssv})")
            if not dry_run:
                cur.execute(
                    "INSERT OR IGNORE INTO Users "
                    "(mssv, name, role, has_face, email, password, is_first_login) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (mssv, name, role, fb_has_face, email, password_fb, new_first_login),
                )
            added += 1

    # SQLite có nhưng Firebase không có → xóa SQLite
    for mssv in sq_set - fb_set:
        sq = sqlite_users[mssv]
        print(f"  [DELETE←Cloud] {sq['name']} ({mssv})")
        if not dry_run:
            cur.execute(
                """UPDATE Lockers SET status='empty', current_mssv=NULL,
                   assigned_date=NULL, last_open=NULL WHERE current_mssv=?""",
                (mssv,),
            )
            cur.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
        deleted += 1

    if not dry_run:
        con.commit()
    print(f"\n  PULL xong: +{added} thêm, ~{updated} cập nhật, -{deleted} xóa")
    return added, updated, deleted


# ══════════════════════════════════════════════════════════════════════════════
#  PUSH — SQLite → Firebase
# ══════════════════════════════════════════════════════════════════════════════

def push(sqlite_users: dict, firebase_users: dict, sqlite_lockers: dict, dry_run: bool = False):
    admin_deleted, released_lockers = get_delete_logs()
    pushed_users = pushed_lockers = 0
    users_ref   = fdb.reference("users")
    lockers_ref = fdb.reference("lockers")

    # ── Push users ────────────────────────────────────────────────────────────
    for mssv, sq in sqlite_users.items():
        has_face    = bool(sq["face_embedding"] is not None and len(sq["face_embedding"] or b"") > 0)
        sq_password = sq.get("password")
        sq_first_login = 1 if sq.get("is_first_login") is None else int(sq.get("is_first_login"))

        if mssv not in firebase_users:
            # Chặn: user đã bị admin xóa từ web
            if mssv in admin_deleted:
                print(f"  [SKIP+DELETE] {sq['name']} ({mssv}) — admin đã xóa từ web")
                if not dry_run:
                    cur.execute(
                        """UPDATE Lockers SET status='empty', current_mssv=NULL,
                           assigned_date=NULL, last_open=NULL WHERE current_mssv=?""",
                        (mssv,),
                    )
                    cur.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
                    con.commit()
                continue

            print(f"  [ADD→Firebase] {sq['name']} ({mssv})")
            if not dry_run:
                data = {
                    "mssv"          : mssv,
                    "name"          : sq["name"],
                    "role"          : sq["role"] or "student",
                    "has_face"      : has_face,
                    "email"         : sq.get("email") or "",
                    "is_first_login": bool(sq_first_login),
                }
                if sq_password:
                    data["password"] = sq_password
                users_ref.child(mssv).set(data)
            pushed_users += 1
        else:
            fb      = firebase_users[mssv]
            updates = {}
            if has_face and not fb.get("has_face", False):
                updates["has_face"] = True
            sq_email = sq.get("email") or ""
            if sq_email and sq_email != (fb.get("email") or ""):
                updates["email"] = sq_email
            if sq_password and sq_password != fb.get("password"):
                updates["password"] = sq_password
            # Sync thêm account_status (is_approved đã bỏ — không còn dùng)
            sq_status = sq.get("account_status") or "ACTIVE"
            if sq_status != (fb.get("account_status") or "ACTIVE"):
                updates["account_status"] = sq_status
            # is_first_login: kiosk là nguồn xác thực (đổi khi sinh viên đổi
            # mật khẩu lần đầu) → luôn đẩy lên Firebase nếu khác/chưa có
            fb_first_login = fb.get("is_first_login")
            if fb_first_login is None or bool(fb_first_login) != bool(sq_first_login):
                updates["is_first_login"] = bool(sq_first_login)

            if updates:
                print(f"  [UPDATE→Firebase] {sq['name']} ({mssv}) — {list(updates.keys())}")
                if not dry_run:
                    users_ref.child(mssv).update(updates)
                pushed_users += 1

    # ── Push lockers ──────────────────────────────────────────────────────────
    for lid, lk in sqlite_lockers.items():
        mssv_local     = lk.get("current_mssv") or ""
        status_local   = (lk.get("status") or "empty").lower()
        assigned_local = lk.get("assigned_date") or ""

        release_time = released_lockers.get(mssv_local, {}).get(lid)
        # Chỉ coi là "còn sót lại chưa dọn" nếu KHÔNG có assigned_date (chưa
        # từng ghi nhận gán) HOẶC assigned_date CŨ HƠN/BẰNG lần trả tủ đó —
        # nếu assigned_date MỚI HƠN, nghĩa là tủ đã được gán lại hợp lệ sau
        # khi trả, không được đụng vào.
        is_stale_release = (
            status_local == "occupied"
            and mssv_local
            and release_time is not None
            and (not assigned_local or assigned_local <= release_time)
        )

        if is_stale_release:
            print(f"  [FIX LOCKER] {lid} ({mssv_local}) — đã trả từ web, dọn SQLite → push empty")
            if not dry_run:
                cur.execute(
                    "UPDATE Lockers SET status='empty', current_mssv=NULL, "
                    "assigned_date=NULL, last_open=NULL WHERE locker_id=?",
                    (lid,),
                )
                con.commit()
                lockers_ref.child(lid).update({
                    "status"       : "empty",
                    "size"         : lk["size"] or "",
                    "current_mssv" : "",
                    "assigned_date": "",
                    "last_open"    : "",
                })
                # Ghi log audit — trước đây bước dọn này không để lại dấu vết gì
                fdb.reference("locker_delete_logs").push({
                    "mssv"       : mssv_local,
                    "locker_id"  : lid,
                    "delete_time": _now_iso(),
                    "reason"     : "sync_auto_fix",
                })
            pushed_lockers += 1
            continue

        if not dry_run:
            lockers_ref.child(lid).update({
                "status"       : status_local,
                "size"         : lk["size"] or "",
                "current_mssv" : mssv_local,
                "assigned_date": lk.get("assigned_date") or "",
                "last_open"    : lk.get("last_open") or "",
            })
        pushed_lockers += 1

    print(f"\n  PUSH xong: {pushed_users} users, {pushed_lockers} lockers lên Firebase")
    return pushed_users, pushed_lockers



# ══════════════════════════════════════════════════════════════════════════════
#  PULL last_open từ Firebase lockers → SQLite
# ══════════════════════════════════════════════════════════════════════════════

def pull_lockers(dry_run: bool = False):
    """
    Pull Firebase → SQLite cho Lockers: status / current_mssv / assigned_date /
    last_open. Firebase là nguồn xác thực khi web vừa gán tủ trong lúc kiosk
    tắt — nếu không pull bước này trước khi push(), push() sẽ lấy SQLite (còn
    "trống" cũ) đè lên Firebase và XÓA MẤT assignment vừa gán trên web.
    """
    fb_lockers = fdb.reference("lockers").get() or {}
    updated = 0
    for lid, fb in fb_lockers.items():
        row = con.execute(
            "SELECT status, current_mssv, assigned_date, last_open FROM Lockers WHERE locker_id=?",
            (lid,),
        ).fetchone()
        if row is None:
            continue  # tủ không tồn tại trong SQLite — không tự tạo mới ở đây

        fb_status   = (fb.get("status") or "empty").lower()
        fb_mssv     = fb.get("current_mssv") or None
        fb_assigned = fb.get("assigned_date") or None
        fb_last_open = fb.get("last_open") or ""

        sq_status   = (row["status"] or "empty").lower()
        sq_mssv     = row["current_mssv"]
        sq_assigned = row["assigned_date"]
        sq_last_open = row["last_open"] or ""

        # last_open: lấy giá trị mới hơn (string so sánh được vì cùng format datetime)
        final_last_open = max(sq_last_open, fb_last_open) if sq_last_open else fb_last_open

        changed = (
            sq_status != fb_status
            or (sq_mssv or None) != fb_mssv
            or (sq_assigned or None) != fb_assigned
            or sq_last_open != final_last_open
        )
        if changed:
            print(f"  [LOCKER PULL] {lid}: {sq_status}/{sq_mssv} → {fb_status}/{fb_mssv}")
            if not dry_run:
                cur.execute(
                    "UPDATE Lockers SET status=?, current_mssv=?, assigned_date=?, last_open=? "
                    "WHERE locker_id=?",
                    (fb_status, fb_mssv, fb_assigned, final_last_open, lid),
                )
            updated += 1

    if not dry_run:
        con.commit()
    print(f"  PULL lockers: ~{updated} cập nhật")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--sync"
    print("=" * 55)
    print("  SMART LOCKER — Sync Tool")
    print("=" * 55)
    print(f"  Mode: {mode}\n")

    sqlite_users   = get_sqlite_users()
    firebase_users = get_firebase_users()
    sqlite_lockers = get_sqlite_lockers()

    if mode in ("--pull", "--sync"):
        print("── PULL Firebase → SQLite ──────────────────────────────")
        pull(sqlite_users, firebase_users)
        pull_lockers()

    if mode in ("--push", "--sync"):
        print("\n── PUSH SQLite → Firebase ──────────────────────────────")
        # Đọc lại sau pull để có data mới nhất
        sqlite_users   = get_sqlite_users()
        sqlite_lockers = get_sqlite_lockers()
        push(sqlite_users, firebase_users, sqlite_lockers)

    print("\n" + "=" * 55)
    print("  Sync hoàn tất!")
    print("=" * 55)
    con.close()


if __name__ == "__main__":
    main()