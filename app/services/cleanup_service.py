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

IDLE_LOCKER_DAYS = 14  # 2 tuan khong mo tu thi tu thu hoi (co the chinh 7-14)

class CleanupService:

    def __init__(self):

        self.user_repo = UserRepository()
        self.locker_repo = LockerRepository()

    def send_warning_email(
        self,
        email,
        mssv
    ):

        sender = EMAIL_SENDER

        password = EMAIL_PASSWORD

        # Tạo Email định dạng HTML
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "⚠️ CẢNH BÁO HOẠT ĐỘNG - SMART LOCKER"
        msg["From"] = f"Smart Locker System <{sender}>"
        msg["To"] = email

        html = f"""
        <html>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; border: 1px solid #ddd;">
                <h2 style="color: #e67e22; text-align: center;">Cảnh Báo Tạm Dừng</h2>
                <p>Chào bạn (MSSV: <b>{mssv}</b>),</p>
                <p>Tài khoản của bạn đã không hoạt động hơn <b>2 phút</b>.</p>
                <div style="background: #fff3cd; color: #856404; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <b>Lưu ý:</b> Hệ thống sẽ tự động xóa phiên đăng nhập sau 1 phút nữa nếu bạn không quay lại.
                </div>
                <p style="text-align: center; margin-top: 25px;">
                    <span style="font-size: 12px; color: #999;">Đây là email tự động từ hệ thống quản lý Locker.</span>
                </p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html,"html","utf-8"))

        server = smtplib.SMTP(
            "smtp.gmail.com",
            587
        )

        server.starttls()

        server.login(
            sender,
            password
        )

        server.sendmail(
            sender,
            email,
            msg.as_string()
        )

        server.quit()


    def cleanup_users(self):
        try:
            # 1. Xóa user đã INACTIVE quá lâu trước
            self.user_repo.delete_expired_users()

            # 2. Lấy user chưa được cảnh báo
            users = self.user_repo.get_inactive_users()

            for email, mssv in users:
                try:
                    # 3. Gửi mail cảnh báo
                    self.send_warning_email(email, mssv)
                    # 4. Đánh dấu đã gửi mail
                    self.user_repo.mark_warned(mssv)

                except Exception as e:
                    print(f"Lỗi gửi mail {mssv}: {e}")

            # 5. Đánh dấu INACTIVE sau khi đã gửi mail
            self.user_repo.mark_inactive()

            print("Cleanup completed")

        except Exception as e:
            print(f"Cleanup Error: {e}")

    # ── Mới: thu hồi tủ idle (không mở trong IDLE_LOCKER_DAYS ngày) ───────────────
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

    def cleanup_idle_lockers(self, idle_days: int = IDLE_LOCKER_DAYS):
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