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


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS — đọc dữ liệu
# ══════════════════════════════════════════════════════════════════════════════

def get_sqlite_users() -> dict:
    cur.execute(
        "SELECT mssv, name, is_approved, has_face, role, face_embedding, email, password "
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
      released_lockers   : {mssv: set(locker_id)} đã trả tủ từ web/kiosk
    """
    snap = fdb.reference("locker_delete_logs").get() or {}
    admin_deleted_mssv: set  = set()
    released_lockers:   dict = {}

    for entry in snap.values():
        reason = entry.get("reason", "")
        mssv   = entry.get("mssv", "")
        lid    = entry.get("locker_id", "")

        if reason == "admin_delete_card" and mssv:
            admin_deleted_mssv.add(mssv)
        elif reason == "student_release" and mssv and lid and lid != "—":
            released_lockers.setdefault(mssv, set()).add(lid)

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
        is_approved = int(fb.get("is_approved", 0))
        role        = fb.get("role", "student")
        fb_has_face = 1 if fb.get("has_face") else 0
        email       = fb.get("email", "")
        password_fb = fb.get("password")

        if mssv in sqlite_users:
            sq          = sqlite_users[mssv]
            sq_email    = sq.get("email") or ""
            sq_password = sq.get("password")

            merged_has_face = max(int(sq["has_face"] or 0), fb_has_face)
            final_password  = password_fb if password_fb else sq_password

            changed = (
                sq["name"] != name
                or int(sq["is_approved"] or 0) != is_approved
                or (sq["role"] or "student") != role
                or int(sq["has_face"] or 0) != merged_has_face
                or sq_email != email
                or sq_password != final_password
            )
            if changed:
                print(f"  [UPDATE] {name} ({mssv})")
                if not dry_run:
                    cur.execute(
                        "UPDATE Users SET name=?, is_approved=?, role=?, has_face=?, "
                        "email=?, password=? WHERE mssv=?",
                        (name, is_approved, role, merged_has_face, email, final_password, mssv),
                    )
                updated += 1
        else:
            print(f"  [ADD→SQLite] {name} ({mssv})")
            if not dry_run:
                cur.execute(
                    "INSERT OR IGNORE INTO Users "
                    "(mssv, name, is_approved, role, has_face, email, password) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (mssv, name, is_approved, role, fb_has_face, email, password_fb),
                )
            added += 1

    # SQLite có nhưng Firebase không có → xóa SQLite
    for mssv in sq_set - fb_set:
        sq = sqlite_users[mssv]
        print(f"  [DELETE←Cloud] {sq['name']} ({mssv})")
        if not dry_run:
            cur.execute(
                "UPDATE Lockers SET status='empty', current_mssv=NULL WHERE current_mssv=?",
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

        if mssv not in firebase_users:
            # Chặn: user đã bị admin xóa từ web
            if mssv in admin_deleted:
                print(f"  [SKIP+DELETE] {sq['name']} ({mssv}) — admin đã xóa từ web")
                if not dry_run:
                    cur.execute(
                        "UPDATE Lockers SET status='empty', current_mssv=NULL WHERE current_mssv=?",
                        (mssv,),
                    )
                    cur.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
                    con.commit()
                continue

            print(f"  [ADD→Firebase] {sq['name']} ({mssv})")
            if not dry_run:
                data = {
                    "mssv"       : mssv,
                    "name"       : sq["name"],
                    "is_approved": int(sq["is_approved"] or 0),
                    "role"       : sq["role"] or "student",
                    "has_face"   : has_face,
                    "email"      : sq.get("email") or "",
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
            # Sync thêm is_approved và account_status
            sq_approved = int(sq.get("is_approved") or 0)
            if sq_approved != int(fb.get("is_approved") or 0):
                updates["is_approved"] = sq_approved
            sq_status = sq.get("account_status") or "ACTIVE"
            if sq_status != (fb.get("account_status") or "ACTIVE"):
                updates["account_status"] = sq_status

            if updates:
                print(f"  [UPDATE→Firebase] {sq['name']} ({mssv}) — {list(updates.keys())}")
                if not dry_run:
                    users_ref.child(mssv).update(updates)
                pushed_users += 1

    # ── Push lockers ──────────────────────────────────────────────────────────
    for lid, lk in sqlite_lockers.items():
        mssv_local   = lk.get("current_mssv") or ""
        status_local = (lk.get("status") or "empty").lower()

        # Chặn: tủ đã trả từ web/kiosk, không push lại trạng thái cũ
        if (
            status_local == "occupied"
            and mssv_local
            and lid in released_lockers.get(mssv_local, set())
        ):
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

def pull_locker_last_open(dry_run: bool = False):
    """Merge last_open từ Firebase xuống SQLite — lấy giá trị mới hơn."""
    fb_lockers = fdb.reference("lockers").get() or {}
    updated = 0
    for lid, fb in fb_lockers.items():
        fb_last_open = fb.get("last_open") or ""
        if not fb_last_open:
            continue
        row = con.execute(
            "SELECT last_open FROM Lockers WHERE locker_id=?", (lid,)
        ).fetchone()
        if not row:
            continue
        sq_last_open = row["last_open"] or ""
        final = max(sq_last_open, fb_last_open) if sq_last_open else fb_last_open
        if final != sq_last_open:
            if not dry_run:
                cur.execute(
                    "UPDATE Lockers SET last_open=? WHERE locker_id=?", (final, lid)
                )
            updated += 1
    if not dry_run:
        con.commit()
    print(f"  PULL last_open lockers: ~{updated} cập nhật")


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
        pull_locker_last_open()

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