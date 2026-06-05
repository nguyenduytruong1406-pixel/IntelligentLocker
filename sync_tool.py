#!/usr/bin/env python3
"""
sync_tool.py — Đồng bộ 2 chiều SQLite ↔ Firebase (chạy 1 lần theo lệnh)
"""

import sys
import sqlite3
import firebase_admin
from firebase_admin import credentials, db as fdb

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH         = r"D:\DATN\Software\test_db_ver1\IntelligentLocker.db"
SERVICE_ACCOUNT = r"D:\DATN\Software\test_db_ver1\private_key_lockers.json"
DATABASE_URL    = "https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app"

# ── Init ──────────────────────────────────────────────────────────────────────
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
cur = con.cursor()

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_sqlite_users():
    cur.execute("SELECT mssv, name, is_approved, has_face, role, face_embedding, email, password FROM Users")
    rows = cur.fetchall()
    return {r['mssv']: dict(r) for r in rows}

def get_firebase_users():
    snap = fdb.reference('users').get()
    return snap or {}

def get_sqlite_lockers():
    cur.execute("SELECT locker_id, status, size, current_mssv, last_open, assigned_date FROM Lockers")
    return {r['locker_id']: dict(r) for r in cur.fetchall()}

def get_delete_logs():
    """
    Đọc locker_delete_logs từ Firebase, trả về:
      - admin_deleted_mssv : set MSSV bị admin xóa hoàn toàn
      - released_lockers   : dict {mssv: set(locker_id)} đã trả tủ từ web/kiosk
    """
    snap = fdb.reference('locker_delete_logs').get() or {}
    admin_deleted_mssv = set()
    released_lockers   = {}

    for entry in snap.values():
        reason = entry.get('reason', '')
        mssv   = entry.get('mssv', '')
        lid    = entry.get('locker_id', '')

        if reason == 'admin_delete_card' and mssv:
            admin_deleted_mssv.add(mssv)
        elif reason == 'student_release' and mssv and lid and lid != '—':
            released_lockers.setdefault(mssv, set()).add(lid)

    return admin_deleted_mssv, released_lockers

# ── PULL: Firebase → SQLite ───────────────────────────────────────────────────
def pull(sqlite_users, firebase_users, dry_run=False):
    added = updated = deleted = 0
    fb_mssv_set = set(firebase_users.keys())
    sq_mssv_set = set(sqlite_users.keys())

    for mssv, fb in firebase_users.items():
        name        = fb.get('name', 'Unknown')
        is_approved = int(fb.get('is_approved', 0))
        role        = fb.get('role', 'student')
        fb_has_face = 1 if fb.get('has_face') else 0
        email       = fb.get('email', '')
        password_fb = fb.get('password') # <-- Lấy từ web

        if mssv in sqlite_users:
            sq = sqlite_users[mssv]
            sq_email = sq.get('email') or ''
            sq_password = sq.get('password')

            merged_has_face = max(int(sq['has_face'] or 0), fb_has_face)
            final_password = password_fb if password_fb else sq_password

            changed = (
                sq['name'] != name or
                int(sq['is_approved'] or 0) != is_approved or
                (sq['role'] or 'student') != role or
                int(sq['has_face'] or 0) != merged_has_face or
                sq_email != email or
                sq_password != final_password
            )
            if changed:
                print(f"  [UPDATE] {name} ({mssv})")
                if not dry_run:
                    cur.execute(
                        "UPDATE Users SET name=?, is_approved=?, role=?, has_face=?, email=?, password=? WHERE mssv=?",
                        (name, is_approved, role, merged_has_face, email, final_password, mssv)
                    )
                updated += 1
        else:
            print(f"  [ADD→SQLite] {name} ({mssv})")
            if not dry_run:
                cur.execute(
                    "INSERT OR IGNORE INTO Users (mssv, name, is_approved, role, has_face, email, password) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (mssv, name, is_approved, role, fb_has_face, email, password_fb)
                )
            added += 1

    for mssv in sq_mssv_set - fb_mssv_set:
        sq = sqlite_users[mssv]
        print(f"  [DELETE←Cloud] {sq['name']} ({mssv})")
        if not dry_run:
            cur.execute("UPDATE Lockers SET status='empty', current_mssv=NULL WHERE current_mssv=?", (mssv,))
            cur.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
        deleted += 1

    if not dry_run:
        con.commit()
    print(f"\n  PULL xong: +{added} thêm, ~{updated} cập nhật, -{deleted} xóa")
    return added, updated, deleted

# ── PUSH: SQLite → Firebase ───────────────────────────────────────────────────
def push(sqlite_users, firebase_users, sqlite_lockers, dry_run=False):
    admin_deleted, released_lockers = get_delete_logs()
    pushed_users = pushed_lockers = 0
    users_ref   = fdb.reference('users')
    lockers_ref = fdb.reference('lockers')

    # ── Push users ────────────────────────────────────────────────────────────
    for mssv, sq in sqlite_users.items():
        has_face    = bool(sq['face_embedding'] is not None and len(sq['face_embedding'] or b'') > 0)
        sq_password = sq.get('password')

        if mssv not in firebase_users:
            # Chặn: user đã bị admin xóa từ web, không push ngược lên
            if mssv in admin_deleted:
                print(f"  [SKIP+DELETE] {sq['name']} ({mssv}) — admin đã xóa từ web")
                if not dry_run:
                    cur.execute(
                        "UPDATE Lockers SET status='empty', current_mssv=NULL WHERE current_mssv=?",
                        (mssv,)
                    )
                    cur.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
                    con.commit()
                continue

            print(f"  [ADD→Firebase] {sq['name']} ({mssv})")
            if not dry_run:
                data = {
                    'mssv'       : mssv,
                    'name'       : sq['name'],
                    'is_approved': int(sq['is_approved'] or 0),
                    'role'       : sq['role'] or 'student',
                    'has_face'   : has_face,
                    'email'      : sq.get('email') or '',
                }
                if sq_password: data['password'] = sq_password
                users_ref.child(mssv).set(data)
            pushed_users += 1
        else:
            fb_has_face = firebase_users[mssv].get('has_face', False)
            fb_email    = firebase_users[mssv].get('email') or ''
            fb_password = firebase_users[mssv].get('password')
            sq_email    = sq.get('email') or ''

            updates = {}
            if has_face and not fb_has_face: updates['has_face'] = True
            if sq_email and sq_email != fb_email: updates['email'] = sq_email
            if sq_password and sq_password != fb_password: updates['password'] = sq_password

            if updates:
                print(f"  [UPDATE→Firebase] {sq['name']} ({mssv})")
                if not dry_run:
                    users_ref.child(mssv).update(updates)
                pushed_users += 1

    # ── Push lockers ──────────────────────────────────────────────────────────
    for lid, lk in sqlite_lockers.items():
        mssv_local   = lk.get('current_mssv') or ''
        status_local = (lk.get('status') or 'empty').lower()

        # Chặn: tủ này đã được trả từ web/kiosk, không push lại trạng thái cũ
        if (
            status_local == 'occupied'
            and mssv_local
            and lid in released_lockers.get(mssv_local, set())
        ):
            print(f"  [FIX LOCKER] {lid} ({mssv_local}) — đã trả từ web, dọn SQLite → push empty")
            if not dry_run:
                cur.execute(
                    "UPDATE Lockers SET status='empty', current_mssv=NULL WHERE locker_id=?",
                    (lid,)
                )
                con.commit()
                lockers_ref.child(lid).set({
                    'status'      : 'empty',
                    'size'        : lk['size'] or '',
                    'current_mssv': '',
                    'last_open'   : lk['last_open'] or '',
                })
            pushed_lockers += 1
            continue

        if not dry_run:
            lockers_ref.child(lid).set({
                'status'      : status_local,
                'size'        : lk['size'] or '',
                'current_mssv': mssv_local,
                'last_open'   : lk['last_open'] or '',
            })
        pushed_lockers += 1

    print(f"\n  PUSH xong: {pushed_users} users, {pushed_lockers} lockers lên Firebase")
    return pushed_users, pushed_lockers

# ── PULL last_open từ Firebase lockers → SQLite ───────────────────────────────
def pull_locker_last_open(dry_run=False):
    """Đồng bộ last_open từ Firebase /lockers xuống SQLite Lockers."""
    fb_lockers = fdb.reference('lockers').get() or {}
    updated = 0
    for lid, fb in fb_lockers.items():
        fb_last_open = fb.get('last_open') or ''
        if not fb_last_open:
            continue
        row = con.execute(
            "SELECT last_open FROM Lockers WHERE locker_id=?", (lid,)
        ).fetchone()
        if not row:
            continue
        sq_last_open = row['last_open'] or ''
        # Lấy giá trị mới hơn
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

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else '--sync'
    print("=" * 55); print("  SMART LOCKER — Sync Tool"); print("=" * 55)
    print(f"  Mode: {mode}\n")

    sqlite_users   = get_sqlite_users()
    firebase_users = get_firebase_users()
    sqlite_lockers = get_sqlite_lockers()

    if mode in ('--pull', '--sync'):
        print("── PULL Firebase → SQLite ──────────────────────────────")
        pull(sqlite_users, firebase_users)
        pull_locker_last_open()

    if mode in ('--push', '--sync'):
        print("\n── PUSH SQLite → Firebase ──────────────────────────────")
        sqlite_users   = get_sqlite_users()
        sqlite_lockers = get_sqlite_lockers()
        push(sqlite_users, firebase_users, sqlite_lockers)

    print("\n" + "=" * 55); print("  Sync hoàn tất!"); print("=" * 55)
    con.close()

if __name__ == "__main__":
    main()