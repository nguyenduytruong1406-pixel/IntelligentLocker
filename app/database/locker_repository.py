"""
app/database/locker_repository.py — Mở rộng từ SML
Thêm:
  • last_open khi OPEN/BORROW
  • assigned_date khi BORROW
  • Xóa last_open/assigned_date khi RETURN
  • LOCKER_DELETE_LOG khi return
  • LockerLog (alias của IntelligentLocker) song song với Locker_access_log
  • insert_service_log / update_locker_maintenance (giữ nguyên từ SML)
Firebase hooks sẽ được tích hợp ở Bước B — để trống TODO ở đây.
"""

from app.database.database import Database
from datetime import datetime


class LockerRepository:

    def __init__(self):
        self.db = Database()

    # ── Truy vấn ──────────────────────────────────────────────────────────────

    def get_user_locker(self, mssv):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT locker_id FROM Lockers WHERE current_mssv = ?",
                (mssv,)
            )
            result = cursor.fetchone()
            return result[0] if result else None

    def has_available_locker(self):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM Lockers WHERE status = 'empty' LIMIT 1"
            )
            return cursor.fetchone() is not None

    def get_all_lockers(self):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT locker_id, status, current_mssv
                FROM Lockers
            """)
            return cursor.fetchall()

    # ── Ghi log (dùng chung cho cả 2 tên bảng) ────────────────────────────────

    def _insert_log(self, conn, locker_id, mssv, event, name):
        """Ghi vào Locker_access_log (SML) VÀ LockerLog (IntelligentLocker)."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for table in ("Locker_access_log", "LockerLog"):
            try:
                conn.execute(
                    f"""
                    INSERT INTO {table}
                    (locker_id, mssv, event, timestamp, name)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (locker_id, mssv, event, now, name)
                )
            except Exception:
                pass  # bảng có thể chưa tồn tại trên DB cũ
        return now

    # ── Mượn tủ ───────────────────────────────────────────────────────────────

    def set_status_locker(self, mssv, locker_id, name):
        """Gán tủ cho sinh viên (BORROW)."""
        try:
            with self.db.connect() as conn:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """
                    UPDATE Lockers SET
                        status       = 'occupied',
                        current_mssv = ?,
                        assigned_date = ?,
                        last_open    = ?
                    WHERE locker_id = ?
                    """,
                    (mssv, now, now, locker_id)
                )
                self._insert_log(conn, locker_id, mssv, "BORROW", name)
                conn.execute(
                    "UPDATE Users SET last_active_time = ? WHERE mssv = ?",
                    (now, mssv)
                )
                conn.commit()
                # TODO (Bước B): push Firebase
                return True
        except Exception as e:
            print(f"[locker_repo] set_status_locker error: {e}")
            return False

    # ── Mở tủ (đã mượn rồi, chỉ OPEN) ───────────────────────────────────────

    def insert_access_log(self, locker_id, mssv, action, name):
        """Ghi log OPEN + cập nhật last_open."""
        with self.db.connect() as conn:
            now = self._insert_log(conn, locker_id, mssv, action, name)
            conn.execute(
                "UPDATE Lockers SET last_open = ? WHERE locker_id = ?",
                (now, locker_id)
            )
            conn.execute(
                "UPDATE Users SET last_active_time = ? WHERE mssv = ?",
                (now, mssv)
            )
            conn.commit()
            # TODO (Bước B): push Firebase last_open

    # ── Trả tủ ────────────────────────────────────────────────────────────────

    def return_locker(self, mssv, locker_id, name):
        """Trả tủ: reset Lockers + ghi log + ghi LOCKER_DELETE_LOG."""
        try:
            with self.db.connect() as conn:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """
                    UPDATE Lockers SET
                        status        = 'empty',
                        current_mssv  = NULL,
                        assigned_date = '',
                        last_open     = NULL
                    WHERE locker_id = ?
                    """,
                    (locker_id,)
                )
                self._insert_log(conn, locker_id, mssv, "RETURN", name)
                conn.execute(
                    "UPDATE Users SET last_active_time = ? WHERE mssv = ?",
                    (now, mssv)
                )
                # Ghi LOCKER_DELETE_LOG (IntelligentLocker standard)
                self._log_delete(conn, mssv, locker_id, now, "student_release")
                conn.commit()
                # TODO (Bước B): push Firebase release
                return True
        except Exception as e:
            print(f"[locker_repo] return_locker error: {e}")
            return False

    def _log_delete(self, conn, mssv, locker_id, delete_time, reason):
        """Ghi vào LOCKER_DELETE_LOG."""
        try:
            conn.execute(
                """
                INSERT INTO LOCKER_DELETE_LOG
                (MSSV, LOCKER_ID, DELETE_TIME, REASON)
                VALUES (?, ?, ?, ?)
                """,
                (mssv, locker_id, delete_time, reason)
            )
        except Exception as e:
            print(f"[locker_repo] _log_delete error: {e}")

    # ── Service Engineer ───────────────────────────────────────────────────────

    def insert_service_log(self, locker_id, ktv_id, ktv_name, action, notes=""):
        try:
            with self.db.connect() as conn:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """
                    INSERT INTO Service_engineer_log
                    (locker_id, ktv_id, ktv_name, action, timestamp, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (locker_id, ktv_id, ktv_name, action, now, notes)
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"[locker_repo] insert_service_log error: {e}")
            return False

    def update_locker_maintenance(self, locker_id, status):
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "UPDATE Lockers SET status = ? WHERE locker_id = ?",
                    (status, locker_id)
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"[locker_repo] update_locker_maintenance error: {e}")
            return False