"""
app/database/user_repository.py — Mở rộng từ SML
Thêm:
  • save_embedding / load_embedding (face recognition từ IntelligentLocker)
  • get_user() trả dict-like Row (hỗ trợ cả cột mới)
  • Giữ nguyên tất cả method cleanup của SML (get_inactive_users, mark_warned, ...)

NOTE: đã bỏ khái niệm "chờ duyệt" (is_approved) — tài khoản chỉ được tạo khi
admin cấp trực tiếp qua web (xem sync_listener.py: on_pending_credentials).
"""

from app.database.database import Database
from datetime import datetime
import pickle
import sqlite3

class UserRepository:

    def log_face_event(self, mssv: str, event: str, detail: str = ""):
        """Ghi sự kiện khuôn mặt vào bảng FaceLog."""
        from datetime import datetime
        with self.db.connect() as conn:
            try:
                conn.execute(
                    """INSERT INTO FaceLog (timestamp, event, mssv, name)
                       VALUES (?, ?, ?, (SELECT name FROM Users WHERE mssv=?))""",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), event, mssv, mssv)
                )
                conn.commit()
            except Exception as e:
                print(f"[FaceLog] Lỗi ghi log: {e}")


    def __init__(self):
        self.db = Database()

    # ── Tìm kiếm ──────────────────────────────────────────────────────────────

    def find_user(self, mssv):

        with self.db.connect() as conn:

            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT *
                FROM Users
                WHERE mssv = ?
                """,
                (mssv,)
            )

            return cursor.fetchone()

    def find_password(self, mssv, password):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM Users WHERE mssv = ? AND password = ?",
                (mssv, password)
            )
            return cursor.fetchone()

    def user_exists(self, mssv, email):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM Users WHERE mssv = ? OR email = ?",
                (mssv, email)
            )
            return cursor.fetchone() is not None

    def get_name_by_mssv(self, mssv):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM Users WHERE mssv = ?", (mssv,))
            result = cursor.fetchone()
            return result[0] if result else None

    def get_email_by_mssv(self, mssv):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM Users WHERE mssv = ?", (mssv,))
            result = cursor.fetchone()
            return result[0] if result else None

    # ── Đăng ký ───────────────────────────────────────────────────────────────

    def create_user(self, mssv, name, email, password):
        """Đăng ký qua kiosk SML — luồng cũ, không còn dùng ở main.py hiện tại
        (RegisterController đã bị bỏ) nhưng giữ lại phòng khi còn nơi gọi tới."""
        with self.db.connect() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO Users
                (mssv, name, email, password, registered_at,
                 account_status, role)
                VALUES (?, ?, ?, ?, ?, 'ACTIVE', 'student')
                """,
                (mssv, name, email, password, now)
            )
            conn.commit()

    def register_user(self, mssv, name, email, password=None, role="student"):
        """Đăng ký đầy đủ — dùng cho sync_listener khi pull từ Firebase."""
        with self.db.connect() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT OR IGNORE INTO Users
                (mssv, name, email, password, registered_at,
                 account_status, role)
                VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?)
                """,
                (mssv, name, email, password, now, role)
            )
            conn.commit()

    # ── Face Embedding (IntelligentLocker) ────────────────────────────────────

    def save_embedding(self, mssv, embedding):
        """Lưu face embedding (numpy array → BLOB via pickle)."""
        try:
            blob = pickle.dumps(embedding)
            with self.db.connect() as conn:
                conn.execute(
                    "UPDATE Users SET face_embedding = ?, has_face = 1 WHERE mssv = ?",
                    (blob, mssv)
                )
                conn.commit()
            print(f"[UserRepository] ✓ Lưu embedding cho mssv='{mssv}'")
            return True
        except Exception as e:
            print(f"[UserRepository] ✗ save_embedding lỗi: {e}")
            return False

    def load_embedding(self, mssv):
        """Trả numpy array hoặc None."""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT face_embedding FROM Users WHERE mssv = ?", (mssv,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                return pickle.loads(row[0])
            return None

    def get_all_embeddings(self):
        """Trả list[(mssv, name, embedding)] cho tất cả user có khuôn mặt."""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT mssv, name, face_embedding FROM Users WHERE has_face = 1"
            )
            results = []
            for mssv, name, blob in cursor.fetchall():
                if blob:
                    results.append((mssv, name, pickle.loads(blob)))
            return results

    # ── Cập nhật trạng thái ───────────────────────────────────────────────────

    def update_account_status(self, mssv, status="ACTIVE"):
        with self.db.connect() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                UPDATE Users SET
                    account_status  = ?,
                    last_active_time = ?
                WHERE mssv = ?
                """,
                (status, now, mssv)
            )
            conn.commit()

    # NOTE: đã xoá approve_user() — dead code từ khi còn khái niệm "chờ duyệt"
    # (is_approved). Tài khoản giờ chỉ được tạo khi admin cấp trực tiếp qua
    # web (đã active ngay, không có bước duyệt riêng để gọi hàm này nữa).

    # ── Mật khẩu / First login ────────────────────────────────────────────────

    def get_pass_by_mssv(self, mssv):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password FROM Users WHERE mssv = ?", (mssv,))
            row = cursor.fetchone()
            return row[0] if row else None

    def update_pass(self, mssv, new_p):

        with self.db.connect() as conn:

            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE Users
                SET password = ?
                WHERE mssv = ?
                """,
                (
                    new_p,
                    mssv
                )
            )


            conn.commit()

    def update_is_first_login(self, mssv, value):

        with self.db.connect() as conn:
            
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE Users SET is_first_login = ?
                WHERE mssv = ?
                """,
                (value, mssv)
            )
            conn.commit()

    def is_first_login(self, mssv):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_first_login FROM Users WHERE mssv = ?", (mssv,))
            row = cursor.fetchone()
            return bool(row[0]) if row else False


    # ── Cleanup (giữ nguyên từ SML) ───────────────────────────────────────────

    def get_inactive_users(self):
        """User hoạt động > 2h trước, chưa cảnh báo, đang ACTIVE."""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT email, mssv
                FROM Users
                WHERE datetime(last_active_time)
                    < datetime('now','localtime','-2 hours')
                AND warned_at IS NULL
                AND account_status = 'ACTIVE'
                AND last_active_time != ''
                AND last_active_time IS NOT NULL
            """)
            return cursor.fetchall()

    def mark_warned(self, mssv):
        with self.db.connect() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE Users SET warned_at = ? WHERE mssv = ?", (now, mssv)
            )
            conn.commit()

    def mark_inactive(self):
        """Chuyển INACTIVE sau khi đã gửi mail cảnh báo."""
        with self.db.connect() as conn:
            conn.execute("""
                UPDATE Users SET
                    account_status = 'INACTIVE',
                    warned_at      = NULL
                WHERE account_status = 'ACTIVE'
                AND datetime(last_active_time)
                    < datetime('now','localtime','-2 hours')
                AND warned_at IS NOT NULL
            """)
            conn.commit()

    def delete_expired_users(self):
        """Xóa user đã INACTIVE quá 5 giờ không hoạt động."""
        with self.db.connect() as conn:
            conn.execute("""
                DELETE FROM Users
                WHERE account_status = 'INACTIVE'
                AND datetime(last_active_time)
                    < datetime('now','localtime','-5 hours')
            """)
            conn.commit()