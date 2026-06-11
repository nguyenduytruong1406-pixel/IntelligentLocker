"""
app/services/auth_service.py
"""

import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

from app.database.user_repository import UserRepository
from app.services.firebase_hooks import push_has_face, push_register
from app.utils.session import Session

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
EMAIL_SENDER   = os.getenv("EMAIL_SENDER") or os.getenv("MAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD") or os.getenv("MAIL_PASSWORD", "")
EMAIL_NAME     = os.getenv("MAIL_SENDER_NAME", "Smart Locker — HCMUTE")

OTP_EXPIRE_MINUTES = 1   # đủ để nhận mail + nhập OTP


class AuthService:

    def __init__(self):
        self.user_repo = UserRepository()

    # ── Đăng nhập ─────────────────────────────────────────────────────────────

    def login(self, mssv: str):
        user = self.user_repo.find_user(mssv)
        if not user:
            return False, "Chưa đăng ký tài khoản"
        if user["is_approved"] == 0:
            return False, "Tài khoản đang chờ phê duyệt"
        status = user["account_status"] if "account_status" in user.keys() else "ACTIVE"
        if status == "INACTIVE":
            return False, "Tài khoản đã bị khóa, vui lòng liên hệ admin"
        return True, "Đăng nhập thành công"

    def password(self, mssv: str, pass_input: str):
        """Xác thực mật khẩu — thử plaintext (SML) rồi SHA-256 (IntelligentLocker)."""
        if self.user_repo.find_password(mssv, pass_input):
            return True, "Truy cập thành công"
        if self.user_repo.find_password(mssv, self.hash_password(pass_input)):
            return True, "Truy cập thành công"
        return False, "NHẬP SAI MẬT KHẨU"

    # ── Đăng ký ───────────────────────────────────────────────────────────────

    def register(self, mssv: str, name: str, email: str, password: str):
        if self.user_repo.user_exists(mssv, email):
            return False, "TÀI KHOẢN ĐÃ TỒN TẠI"
        self.user_repo.create_user(mssv, name, email, password)
        print(f"[DEBUG] Gọi push_register cho {mssv}")   # ← thêm
        push_register(mssv, name, email, password)
        print(f"[DEBUG] push_register xong")              # ← thêm
        return True, "Đăng kí tài khoản thành công"

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_name_user(self, mssv: str):
        return self.user_repo.get_name_by_mssv(mssv)

    def get_email_user(self, mssv: str):
        return self.user_repo.get_email_by_mssv(mssv)

    @staticmethod
    def hash_password(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    # ── OTP đăng nhập kiosk (2FA mật khẩu) ──────────────────────────────────

    def send_otp_to_email(self, email: str):
        """
        Sinh OTP 6 số, gửi qua Gmail SMTP với HTML đẹp.
        Lưu vào Session để verify_otp() so sánh.
        Hết hạn sau OTP_EXPIRE_MINUTES phút.
        """
        otp = str(secrets.randbelow(900000) + 100000)  # 6 chữ số

        # Lấy tên user từ Session nếu có
        name = Session.user_name or "bạn"

        html = f"""
        <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;
                    border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
          <div style="background:#4D94FF;padding:24px 32px">
            <h2 style="color:#fff;margin:0">🔒 Mã xác thực đăng nhập</h2>
          </div>
          <div style="padding:28px 32px;color:#374151">
            <p>Xin chào <strong>{name}</strong>,</p>
            <p>Hệ thống nhận được yêu cầu đăng nhập vào Kiosk Smart Locker bằng mật khẩu.</p>
            <div style="background:#f3f4f6;text-align:center;padding:20px;
                        border-radius:8px;margin:20px 0">
              <p style="margin:0;font-size:14px;color:#6b7280">MÃ OTP CỦA BẠN LÀ:</p>
              <h1 style="margin:10px 0 0;font-size:36px;color:#1f2937;
                         letter-spacing:4px">{otp}</h1>
            </div>
            <p style="color:#6b7280;font-size:14px">
              ⏱ Mã có hiệu lực trong <strong>{OTP_EXPIRE_MINUTES} phút</strong>.
            </p>
            <p style="color:#ef4444;font-size:13px">
              ⚠ Tuyệt đối không chia sẻ mã này cho bất kỳ ai.
            </p>
            <p style="margin-top:28px;color:#9ca3af;font-size:12px">
              Email tự động từ hệ thống Smart Locker — HCMUTE.<br>
              Vui lòng không reply trực tiếp email này.
            </p>
          </div>
        </div>"""

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Mã xác thực OTP Smart Locker: {otp}"
            msg["From"]    = f"{EMAIL_NAME} <{EMAIL_SENDER}>"
            msg["To"]      = email
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_SENDER, email, msg.as_string())

            print(f"[AuthService] ✉ Đã gửi OTP tới {email}")
        except Exception as e:
            print(f"[AuthService] ✗ Lỗi gửi OTP: {e}")
            return False, "Gửi OTP thất bại, vui lòng thử lại"

        Session.current_otp     = otp
        Session.otp_expire_time = datetime.now() + timedelta(minutes=OTP_EXPIRE_MINUTES)
        return True, "Đã gửi OTP"

    def verify_otp(self, otp_input: str):
        if Session.current_otp is None:
            return False, "Chưa tạo OTP"
        if datetime.now() > Session.otp_expire_time:
            Session.current_otp     = None
            Session.otp_expire_time = None
            return False, "OTP đã hết hạn"
        if str(otp_input).strip() != str(Session.current_otp).strip():
            return False, "OTP không đúng"
        Session.current_otp     = None
        Session.otp_expire_time = None
        return True, "Xác thực thành công"

    # ── Face embedding ────────────────────────────────────────────────────────

    def save_face_embedding(self, mssv: str, embedding):
        """Lưu embedding vào SQLite và push has_face=True lên Firebase."""
        ok = self.user_repo.save_embedding(mssv, embedding)
        if ok:
            push_has_face(mssv)
        return ok