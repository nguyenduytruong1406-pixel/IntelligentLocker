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
                        status         = 'occupied',
                        current_mssv   = ?,
                        assigned_date  = ?,
                        last_open      = ?,
                        idle_warned_at   = NULL,
                        expiry_warned_at = NULL
                    WHERE locker_id = ?
                    """,
                    (mssv, now, now, locker_id)
                )
                self._insert_log(conn, locker_id, mssv, "BORROW", name)
                # Ghi LOCKER_DELETE_LOG (dùng chung bảng audit "Lịch Sử Tủ")
                self._log_delete(conn, mssv, locker_id, now, "new_assignment")
                conn.commit()
                # TODO (Bước B): push Firebase
                return True
        except Exception as e:
            print(f"[locker_repo] set_status_locker error: {e}")
            return False

    # ── Mở tủ (đã mượn rồi, chỉ OPEN) ───────────────────────────────────────

    def insert_access_log(self, locker_id, mssv, action, name):
        """Ghi log OPEN + cập nhật last_open. Mở tủ = hết idle, xoá cảnh báo
        idle cũ (nếu có) để lượt idle tiếp theo được cảnh báo lại từ đầu.
        Không đụng expiry_warned_at — mở tủ không kéo dài hạn mượn."""
        with self.db.connect() as conn:
            now = self._insert_log(conn, locker_id, mssv, action, name)
            conn.execute(
                "UPDATE Lockers SET last_open = ?, idle_warned_at = NULL WHERE locker_id = ?",
                (now, locker_id)
            )
            conn.commit()
            # TODO (Bước B): push Firebase last_open

    # ── Trả tủ ────────────────────────────────────────────────────────────────

    def return_locker(self, mssv, locker_id, name, reason="student_release"):
        """Trả tủ: reset Lockers + ghi log + ghi LOCKER_DELETE_LOG."""
        try:
            with self.db.connect() as conn:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """
                    UPDATE Lockers SET
                        status           = 'empty',
                        current_mssv     = NULL,
                        assigned_date    = '',
                        last_open        = NULL,
                        idle_warned_at   = NULL,
                        expiry_warned_at = NULL
                    WHERE locker_id = ?
                    """,
                    (locker_id,)
                )
                self._insert_log(conn, locker_id, mssv, "RETURN", name)
                # Ghi LOCKER_DELETE_LOG (IntelligentLocker standard)
                self._log_delete(conn, mssv, locker_id, now, reason)
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

    # ── Thu hồi tủ idle (không mở trong X ngày) ──────────────────────────────────

    def get_idle_lockers(self, idle_days: int):
        """Tủ đang occupied nhưng không mở (last_open) quá idle_days ngày.
        Trả về list (locker_id, current_mssv). Dùng cho mốc THU HỒI CỨNG
        (idle_days=16) — không lọc theo idle_warned_at, tới hạn là thu hồi
        dù mail cảnh báo trước đó có gửi thành công hay không."""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT locker_id, current_mssv
                FROM Lockers
                WHERE status = 'occupied'
                  AND current_mssv IS NOT NULL
                  AND current_mssv != ''
                  AND last_open IS NOT NULL
                  AND last_open != ''
                  AND datetime(last_open) < datetime('now', 'localtime', ?)
                """,
                (f"-{idle_days} days",)
            )
            return cursor.fetchall()

    def get_lockers_needing_idle_warning(self, warn_days: int):
        """Tủ occupied, không mở quá warn_days ngày, CHƯA được cảnh báo idle
        ở lượt mượn hiện tại (idle_warned_at IS NULL). Mốc CẢNH BÁO (ngày 14).
        Trả về list (locker_id, current_mssv)."""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT locker_id, current_mssv
                FROM Lockers
                WHERE status = 'occupied'
                  AND current_mssv IS NOT NULL
                  AND current_mssv != ''
                  AND last_open IS NOT NULL
                  AND last_open != ''
                  AND datetime(last_open) < datetime('now', 'localtime', ?)
                  AND idle_warned_at IS NULL
                """,
                (f"-{warn_days} days",)
            )
            return cursor.fetchall()

    def mark_idle_warned(self, locker_id):
        """Đánh dấu đã gửi mail cảnh báo idle cho tủ này (lượt mượn hiện tại)."""
        with self.db.connect() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE Lockers SET idle_warned_at = ? WHERE locker_id = ?",
                (now, locker_id)
            )
            conn.commit()

    def get_lockers_expiring_soon(self, days_before: int):
        """Tủ occupied mà Users.locker_expiry_date rơi trong days_before ngày
        tới, CHƯA được cảnh báo hết hạn (expiry_warned_at IS NULL).
        Trả về list (locker_id, mssv, name, email, locker_expiry_date)."""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT l.locker_id, u.mssv, u.name, u.email, u.locker_expiry_date
                FROM Lockers l
                JOIN Users u ON u.mssv = l.current_mssv
                WHERE l.status = 'occupied'
                  AND u.locker_expiry_date IS NOT NULL
                  AND u.locker_expiry_date != ''
                  AND date(u.locker_expiry_date) BETWEEN date('now', 'localtime')
                                                       AND date('now', 'localtime', ?)
                  AND l.expiry_warned_at IS NULL
                """,
                (f"+{days_before} days",)
            )
            return cursor.fetchall()

    def mark_expiry_warned(self, locker_id):
        """Đánh dấu đã gửi mail cảnh báo sắp hết hạn cho tủ này."""
        with self.db.connect() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE Lockers SET expiry_warned_at = ? WHERE locker_id = ?",
                (now, locker_id)
            )
            conn.commit()

    def get_expired_lockers(self):
        """Tủ occupied mà Users.locker_expiry_date đã QUA (< hôm nay).
        Mốc THU HỒI CỨNG theo hạn mượn — không phụ thuộc đã cảnh báo hay
        chưa, tới hạn là thu hồi. Trả về list (locker_id, mssv, name, email,
        locker_expiry_date)."""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT l.locker_id, u.mssv, u.name, u.email, u.locker_expiry_date
                FROM Lockers l
                JOIN Users u ON u.mssv = l.current_mssv
                WHERE l.status = 'occupied'
                  AND u.locker_expiry_date IS NOT NULL
                  AND u.locker_expiry_date != ''
                  AND date(u.locker_expiry_date) < date('now', 'localtime')
                """
            )
            return cursor.fetchall()


#   ************************************************************************ #
#   ********************** GỬI THÔNG BÁO ĐÓNG TỦ *************************** #
#   ************************************************************************ #

    def get_open_lockers(self):
        """Lấy các tủ đang mở quá 5 phút chưa đóng"""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.locker_id, l.mssv, l.timestamp, u.email
                FROM LockerLog l
                JOIN Users u ON l.mssv = u.mssv
                WHERE l.event = 'OPEN'
                AND l.door_closed_at IS NULL

                AND l.warned_door IS NULL 

                AND datetime(l.timestamp) 
                    < datetime('now', 'localtime', '-1 minutes')
                ORDER BY l.timestamp DESC
            """)
            return cursor.fetchall()

    def mark_door_warned(self, locker_id):
        """Đánh dấu đã gửi mail → không gửi lại"""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                UPDATE LockerLog
                SET warned_door = ?
                WHERE locker_id = ?
                AND event = 'OPEN'
                AND door_closed_at IS NULL
                AND warned_door IS NULL
            """, (now, locker_id))
            conn.commit()

    def mark_door_closed(self, locker_id):
        """Cập nhật thời gian đóng tủ khi nhận tín hiệu từ ESP32"""
        with self.db.connect() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                UPDATE LockerLog
                SET door_closed_at = ?
                WHERE locker_id = ?
                AND event = 'OPEN'
                AND door_closed_at IS NULL
            """, (now, locker_id))
            conn.commit()