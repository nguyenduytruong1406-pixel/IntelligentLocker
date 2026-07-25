import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.database.user_repository import UserRepository
from app.database.locker_repository import LockerRepository
from app.services.firebase_hooks import push_return
from app.config import (
    EMAIL_SENDER,
    EMAIL_PASSWORD
)

IDLE_WARN_DAYS   = 14  # không mở tủ quá 14 ngày → gửi mail cảnh báo
IDLE_REVOKE_DAYS = 16  # không mở tủ quá 16 ngày → tự thu hồi (2 ngày ân hạn sau cảnh báo)
EXPIRY_WARN_DAYS = 2   # còn 2 ngày nữa hết hạn mượn (locker_expiry_date) → gửi mail cảnh báo

class CleanupService:

    def __init__(self):

        self.user_repo = UserRepository()
        self.locker_repo = LockerRepository()

    # NOTE: đã bỏ send_warning_email() / cleanup_users() — luồng "cảnh báo idle
    # phiên đăng nhập" cũ từ SML, dùng account_status/last_active_time/warned_at
    # (đã bỏ khỏi schema Users, xem app/database/database.py). Cơ chế idle hiện
    # tại là cleanup_idle_lockers() bên dưới, dựa trên Lockers.last_open.

    # Khác với cleanup_users() (đăng xuất phiên idle theo GIỜ, ở trên).
    # Hàm này xét theo Lockers.last_open, đơn vị NGÀY — hạn tối đa thật sự
    # vẫn do locker_expiry_date quyết định riêng (chiều người dùng khác).

    def send_idle_release_email(self, email, mssv, locker_id, idle_days):
        if not email:
            return
        sender = EMAIL_SENDER
        password = EMAIL_PASSWORD

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"ℹ️ Tủ {locker_id} đã được thu hồi do không sử dụng"
        msg["From"] = f"Smart Locker System <{sender}>"
        msg["To"] = email

        html = f"""
        <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; border: 1px solid #ddd;">
                <h2 style="color: #dc3545; text-align: center;">Tủ đã bị thu hồi</h2>
                <p>Chào bạn (MSSV: <b>{mssv}</b>),</p>
                <p>Tủ <b>{locker_id}</b> của bạn đã không được mở trong hơn <b>{idle_days} ngày</b>
                   nên hệ thống đã tự động thu hồi để nhường cho người khác.</p>
                <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <b>Nếu vẫn cần dùng tủ:</b> vui lòng liên hệ quản lý Makerspace để được cấp lại.
                </div>
                <p style="text-align: center; margin-top: 25px;">
                    <span style="font-size: 12px; color: #999;">Đây là email tự động từ hệ thống quản lý Locker.</span>
                </p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, email, msg.as_string())
            server.quit()
        except Exception as e:
            print(f"Lỗi gửi mail thu hồi tủ idle {mssv}: {e}")

    # ── Giai đoạn 1: CẢNH BÁO idle (ngày 14) ─────────────────────────────────

    def send_idle_warning_email(self, email, mssv, locker_id, warn_days, revoke_days):
        if not email:
            return
        sender = EMAIL_SENDER
        password = EMAIL_PASSWORD

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"⚠️ Tủ {locker_id} sắp bị thu hồi do không sử dụng"
        msg["From"] = f"Smart Locker System <{sender}>"
        msg["To"] = email

        grace_days = revoke_days - warn_days
        html = f"""
        <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; border: 1px solid #ddd;">
                <h2 style="color: #e67e22; text-align: center;">Cảnh Báo Tủ Sắp Bị Thu Hồi</h2>
                <p>Chào bạn (MSSV: <b>{mssv}</b>),</p>
                <p>Tủ <b>{locker_id}</b> của bạn đã không được mở trong hơn <b>{warn_days} ngày</b>.</p>
                <div style="background: #fff3cd; color: #856404; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <b>Lưu ý:</b> Nếu tủ tiếp tục không được mở, hệ thống sẽ tự động
                    thu hồi sau <b>{grace_days} ngày nữa</b> (tổng {revoke_days} ngày không sử dụng).
                </div>
                <p style="text-align: center; margin-top: 25px;">
                    <span style="font-size: 12px; color: #999;">Đây là email tự động từ hệ thống quản lý Locker.</span>
                </p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, email, msg.as_string())
            server.quit()
        except Exception as e:
            print(f"Lỗi gửi mail cảnh báo idle {mssv}: {e}")

    def cleanup_idle_warning(self, warn_days: int = IDLE_WARN_DAYS, revoke_days: int = IDLE_REVOKE_DAYS):
        """Gửi mail cảnh báo cho tủ không mở quá warn_days ngày, chưa từng
        được cảnh báo ở lượt mượn hiện tại. Không thu hồi — chỉ cảnh báo."""
        try:
            lockers = self.locker_repo.get_lockers_needing_idle_warning(warn_days)
            for locker_id, mssv in lockers:
                try:
                    email = self.user_repo.get_email_by_mssv(mssv)
                    self.send_idle_warning_email(email, mssv, locker_id, warn_days, revoke_days)
                    self.locker_repo.mark_idle_warned(locker_id)
                    print(f"[CleanupIdleWarning] Đã cảnh báo tủ {locker_id} của {mssv} (idle {warn_days}+ ngày)")
                except Exception as e:
                    print(f"[CleanupIdleWarning] Lỗi xử lý {mssv}/{locker_id}: {e}")

            print("Cleanup idle warning completed")

        except Exception as e:
            print(f"Cleanup Idle Warning Error: {e}")

    # ── Giai đoạn 2: THU HỒI idle (ngày 16) ──────────────────────────────────

    def cleanup_idle_lockers(self, idle_days: int = IDLE_REVOKE_DAYS):
        """Tự thu hồi tủ đang mượn nhưng không mở quá idle_days ngày.
        Không đụng đến locker_expiry_date (hạn tối đa) — đó là kiểm tra riêng."""
        try:
            idle_lockers = self.locker_repo.get_idle_lockers(idle_days)
            for locker_id, mssv in idle_lockers:
                try:
                    name = self.user_repo.get_name_by_mssv(mssv) or mssv
                    email = self.user_repo.get_email_by_mssv(mssv)

                    ok = self.locker_repo.return_locker(
                        mssv, locker_id, name, reason="auto_idle_locker"
                    )
                    if ok:
                        push_return(mssv, locker_id, name, reason="auto_idle_locker")
                        print(f"[CleanupIdleLockers] Thu hồi tủ {locker_id} của {mssv} (idle {idle_days}+ ngày)")
                        self.send_idle_release_email(email, mssv, locker_id, idle_days)
                except Exception as e:
                    print(f"[CleanupIdleLockers] Lỗi xử lý {mssv}/{locker_id}: {e}")

            print("Cleanup idle lockers completed")

        except Exception as e:
            print(f"Cleanup Idle Lockers Error: {e}")

    # ── Cảnh báo sắp hết hạn mượn tủ (locker_expiry_date, trước 2 ngày) ──────

    def send_expiry_warning_email(self, email, mssv, locker_id, expiry_date, days_left):
        if not email:
            return
        sender = EMAIL_SENDER
        password = EMAIL_PASSWORD

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"⏰ Tủ {locker_id} sắp hết hạn mượn"
        msg["From"] = f"Smart Locker System <{sender}>"
        msg["To"] = email

        html = f"""
        <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; border: 1px solid #ddd;">
                <h2 style="color: #0d6efd; text-align: center;">Sắp Hết Hạn Mượn Tủ</h2>
                <p>Chào bạn (MSSV: <b>{mssv}</b>),</p>
                <p>Tủ <b>{locker_id}</b> của bạn sẽ hết hạn mượn vào ngày
                   <b>{expiry_date}</b> (còn khoảng {days_left} ngày).</p>
                <div style="background: #cfe2ff; color: #084298; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <b>Cần gia hạn?</b> Vui lòng liên hệ quản lý Makerspace trước khi hết hạn.
                </div>
                <p style="text-align: center; margin-top: 25px;">
                    <span style="font-size: 12px; color: #999;">Đây là email tự động từ hệ thống quản lý Locker.</span>
                </p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, email, msg.as_string())
            server.quit()
        except Exception as e:
            print(f"Lỗi gửi mail cảnh báo hết hạn {mssv}: {e}")

    def cleanup_expiry_warning(self, days_before: int = EXPIRY_WARN_DAYS):
        """Gửi mail cảnh báo cho tủ mà locker_expiry_date của người mượn sắp
        tới (trong vòng days_before ngày), chưa từng được cảnh báo. Chỉ cảnh
        báo — thu hồi thật khi hết hạn nằm ở cleanup_expired_lockers()."""
        try:
            lockers = self.locker_repo.get_lockers_expiring_soon(days_before)
            for locker_id, mssv, name, email, expiry_date in lockers:
                try:
                    self.send_expiry_warning_email(email, mssv, locker_id, expiry_date, days_before)
                    self.locker_repo.mark_expiry_warned(locker_id)
                    print(f"[CleanupExpiryWarning] Đã cảnh báo tủ {locker_id} của {mssv} (hết hạn {expiry_date})")
                except Exception as e:
                    print(f"[CleanupExpiryWarning] Lỗi xử lý {mssv}/{locker_id}: {e}")

            print("Cleanup expiry warning completed")

        except Exception as e:
            print(f"Cleanup Expiry Warning Error: {e}")

    # ── Thu hồi CỨNG khi đã QUA locker_expiry_date ───────────────────────────

    def send_expiry_release_email(self, email, mssv, locker_id, expiry_date):
        if not email:
            return
        sender = EMAIL_SENDER
        password = EMAIL_PASSWORD

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"ℹ️ Tủ {locker_id} đã được thu hồi do hết hạn mượn"
        msg["From"] = f"Smart Locker System <{sender}>"
        msg["To"] = email

        html = f"""
        <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; border: 1px solid #ddd;">
                <h2 style="color: #dc3545; text-align: center;">Tủ đã bị thu hồi</h2>
                <p>Chào bạn (MSSV: <b>{mssv}</b>),</p>
                <p>Tủ <b>{locker_id}</b> của bạn đã hết hạn mượn từ ngày <b>{expiry_date}</b>
                   nên hệ thống đã tự động thu hồi để nhường cho người khác.</p>
                <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <b>Nếu vẫn cần dùng tủ:</b> vui lòng liên hệ quản lý Makerspace để được cấp lại.
                </div>
                <p style="text-align: center; margin-top: 25px;">
                    <span style="font-size: 12px; color: #999;">Đây là email tự động từ hệ thống quản lý Locker.</span>
                </p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, email, msg.as_string())
            server.quit()
        except Exception as e:
            print(f"Lỗi gửi mail thu hồi hết hạn {mssv}: {e}")

    def cleanup_expired_lockers(self):
        """Tự thu hồi tủ mà locker_expiry_date đã qua — không phụ thuộc đã
        cảnh báo hay chưa (tới hạn là thu hồi, giống cleanup_idle_lockers)."""
        try:
            expired = self.locker_repo.get_expired_lockers()
            for locker_id, mssv, name, email, expiry_date in expired:
                try:
                    ok = self.locker_repo.return_locker(
                        mssv, locker_id, name, reason="auto_expired"
                    )
                    if ok:
                        push_return(mssv, locker_id, name, reason="auto_expired")
                        print(f"[CleanupExpiredLockers] Thu hồi tủ {locker_id} của {mssv} (hết hạn {expiry_date})")
                        self.send_expiry_release_email(email, mssv, locker_id, expiry_date)
                except Exception as e:
                    print(f"[CleanupExpiredLockers] Lỗi xử lý {mssv}/{locker_id}: {e}")

            print("Cleanup expired lockers completed")

        except Exception as e:
            print(f"Cleanup Expired Lockers Error: {e}")