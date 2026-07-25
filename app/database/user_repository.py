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
            conn.execute(
                """
                INSERT INTO Users (mssv, name, email, password)
                VALUES (?, ?, ?, ?)
                """,
                (mssv, name, email, password)
            )
            conn.commit()

    def register_user(self, mssv, name, email, password=None, role="student"):
        """Đăng ký đầy đủ — dùng cho sync_listener khi pull từ Firebase.
        `role` không còn lưu ở DB (đã bỏ cột) — giữ tham số để không phải
        sửa lại nơi gọi, nhưng giá trị bị bỏ qua."""
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO Users (mssv, name, email, password)
                VALUES (?, ?, ?, ?)
                """,
                (mssv, name, email, password)
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

    # NOTE: đã bỏ update_account_status() — dùng account_status/last_active_time,
    # cả 2 cột đã bỏ khỏi schema Users cùng với luồng cảnh báo idle phiên đăng
    # nhập (xem cleanup_idle_lockers trong cleanup_service.py — cơ chế thay thế
    # dựa trên Lockers.last_open, không cần cột nào ở Users).

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

    # NOTE: đã bỏ get_inactive_users() / mark_warned() / mark_inactive() /
    # delete_expired_users() — toàn bộ dùng account_status, last_active_time,
    # warned_at (đã bỏ khỏi schema Users). Đây là cơ chế "cảnh báo idle phiên
    # đăng nhập" cũ từ SML; cleanup_service.cleanup_users() gọi các hàm này
    # cũng đã bị bỏ theo. Cơ chế idle hiện tại là cleanup_idle_lockers()
    # (dựa trên Lockers.last_open) — không cần cột nào ở Users.