"""
core/user_db.py — User CRUD, face embedding, xác thực mật khẩu
"""

import pickle
import datetime
import numpy as np
from firebase_admin import db as fdb

from core.db import _conn

# ── User CRUD ─────────────────────────────────────────────────────────────────

def get_user(mssv: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT mssv, name, role, is_approved, has_face "
            "FROM Users WHERE mssv=?", (mssv,)
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT mssv, name, role, is_approved, has_face "
            "FROM Users ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def register_user(mssv: str, name: str, email: str, pw_hash: str) -> bool:
    """
    Tạo user mới từ kiosk/web. Trả False nếu MSSV đã tồn tại.
    is_approved = 0 (chờ admin duyệt).
    """
    with _conn() as con:
        if con.execute("SELECT mssv FROM Users WHERE mssv=?", (mssv,)).fetchone():
            print(f"[user_db] ✗ MSSV {mssv} đã tồn tại")
            return False
        con.execute(
            "INSERT INTO Users (mssv, name, role, is_approved, has_face, password, email) "
            "VALUES (?, ?, 'student', 0, 0, ?, ?)",
            (mssv, name, pw_hash, email)
        )
        print(f"[user_db] ✓ Đăng ký user mới: {mssv} - {name}")

    try:
        fdb.reference(f'users/{mssv}').set({
            'name'         : name,
            'role'         : 'student',
            'is_approved'  : 0,
            'has_face'     : False,
            'email'        : email,
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    except Exception as e:
        print(f"[Firebase Lỗi] register_user: {e}")

    return True


def get_user_by_password(mssv: str, pw_hash: str) -> dict | None:
    """Xác thực MSSV + SHA256 hash. Trả None nếu sai."""
    with _conn() as con:
        row = con.execute(
            "SELECT mssv, name, role, is_approved, has_face "
            "FROM Users WHERE mssv=? AND password=?",
            (mssv, pw_hash)
        ).fetchone()
    return dict(row) if row else None


def add_or_update_user(mssv: str, name: str, role: str = 'student',
                       is_approved: int = 0, has_face: int = 0) -> bool:
    """Thêm mới hoặc cập nhật user (admin/sync). Không ghi đè password."""
    with _conn() as con:
        if con.execute("SELECT mssv FROM Users WHERE mssv=?", (mssv,)).fetchone():
            con.execute(
                "UPDATE Users SET name=?, role=?, is_approved=?, has_face=? WHERE mssv=?",
                (name, role, is_approved, has_face, mssv)
            )
            print(f"[user_db] ✓ Cập nhật user {mssv}")
        else:
            con.execute(
                "INSERT INTO Users (mssv, name, role, is_approved, has_face) "
                "VALUES (?, ?, ?, ?, ?)",
                (mssv, name, role, is_approved, has_face)
            )
            print(f"[user_db] ✓ Thêm mới user {mssv}")

    try:
        fdb.reference(f'users/{mssv}').update({
            'name': name, 'role': role,
            'is_approved': int(is_approved), 'has_face': bool(has_face)
        })
        return True
    except Exception as e:
        print(f"[Firebase Lỗi] add_or_update_user: {e}")
        return False


# ── Face Embedding ────────────────────────────────────────────────────────────

def save_embedding(mssv: str, embedding: np.ndarray) -> bool:
    blob = pickle.dumps(embedding)
    with _conn() as con:
        cur = con.execute(
            "UPDATE Users SET face_embedding=?, has_face=1 WHERE mssv=?",
            (blob, mssv)
        )
        if cur.rowcount == 0:
            print(f"[user_db] ✗ Không tìm thấy mssv='{mssv}'")
            return False
    print(f"[user_db] ✓ Lưu embedding cho mssv='{mssv}'")

    try:
        fdb.reference(f'users/{mssv}').update({'has_face': True})
    except Exception as e:
        print(f"[Firebase Lỗi] save_embedding: {e}")

    return True


def load_all_embeddings() -> dict[str, tuple[np.ndarray, str]]:
    """Load tất cả embedding của user đã duyệt. Return {mssv: (embedding, name)}"""
    result = {}
    with _conn() as con:
        rows = con.execute(
            "SELECT mssv, name, face_embedding FROM Users "
            "WHERE is_approved=1 AND face_embedding IS NOT NULL"
        ).fetchall()
    for row in rows:
        try:
            result[row["mssv"]] = (pickle.loads(row["face_embedding"]), row["name"])
        except Exception as e:
            print(f"[user_db] ⚠ Lỗi load embedding mssv={row['mssv']}: {e}")
    return result


# ── Firebase sync toàn bộ users ───────────────────────────────────────────────

def sync_users_to_firebase() -> bool:
    """Push toàn bộ Users table lên Firebase (dùng cho sync_tool)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT mssv, name, role, is_approved, has_face FROM Users"
        ).fetchall()
    users_dict = {
        r["mssv"]: {
            'name': r["name"], 'role': r["role"],
            'is_approved': int(r["is_approved"]), 'has_face': bool(r["has_face"])
        }
        for r in rows
    }
    try:
        if users_dict:
            fdb.reference('users').update(users_dict)
            print(f"[Firebase] 🟢 Đồng bộ {len(users_dict)} sinh viên.")
        return True
    except Exception as e:
        print(f"[Firebase Lỗi] sync_users: {e}")
        return False
