import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.database.user_repository import UserRepository
from app.config import (
    EMAIL_SENDER,
    EMAIL_PASSWORD
)

class CleanupService:

    def __init__(self):

        self.user_repo = UserRepository()

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

