from app.database.user_repository import UserRepository

from datetime import datetime, timedelta

from app.utils.session import Session

from app.config import EMAIL_SENDER, EMAIL_PASSWORD

from email.mime.text import MIMEText

from email.mime.multipart import MIMEMultipart

import secrets

import smtplib





class AuthService:



    def __init__(self):



        self.user_repo = UserRepository()





    def login(self, mssv):



        user = self.user_repo.find_user(mssv)



        if not user:

            return (

                False,

                "Chưa đăng ký tài khoản"

            )





        

        



            

        return (

            True,

            "Đăng nhập thành công"

        )

    

    def password(self, mssv, pass_account):



        user = self.user_repo.find_password(mssv, pass_account)



        if not user:

            user = self.user_repo.find_password(mssv, self._sha256_hex(pass_account))



        if not user:

            return (

                False,

                "NHẬP SAI MẬT KHẨU"

            )



        return (

            True,

            "Truy cập thành công"

        )



    def mssv_pass(self, mssv, pass_account):



        user = self.user_repo.find_user(mssv)



        if not user:

            return (

                False,

                "Chưa đăng ký tài khoản"

            )

        





       



            

        pw = self.user_repo.find_password(mssv, self._sha256_hex(pass_account))



        if not pw:

            return (

                False,

                "NHẬP SAI MẬT KHẨU"

            )





        return (

            True,

            "Truy cập thành công"

        )



    @staticmethod

    def _sha256_hex(text: str) -> str:

        """Hash SHA-256 hex — khớp với hàm sha256Hex() bên web admin (index.html)."""

        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()





    def register(self, mssv, name, email, password):



        user = self.user_repo.user_exists(mssv, email)



        if not user:

            

            self.user_repo.create_user(mssv, name, email, password)



            return (

                True,

                "Đăng kí tài khoản thành công"

            )





        return(

            False,

            "TÀI KHOẢN ĐÃ TỒN TẠI"

        )

    



    def change_password(self, mssv, old_pass, new_pass, verify_pass):



        # lấy mật khẩu hiện tại (đã lưu dạng hash SHA-256)



        current_pass = self.user_repo.get_pass_by_mssv(mssv)



        if current_pass != self._sha256_hex(old_pass):

            return False, "Mật khẩu cũ không đúng"



        if new_pass != verify_pass:

            return False, "Mật khẩu xác nhận không khớp"

        

        if old_pass == new_pass:

            return False, "Mật khẩu đã trùng lập"



        new_hash = self._sha256_hex(new_pass)

        self.user_repo.update_pass(mssv, new_hash)

        self.user_repo.update_is_first_login(mssv, 0)  # ✅ Đánh dấu đã đổi mk





        try:

            from app.services.firebase_hooks import push_password_changed

            push_password_changed(mssv, new_hash)

        except Exception as e:

            print(f"[AuthService] push_password_changed lỗi: {e}")



        return True, "Đổi mật khẩu thành công"



    def is_first_login(self, mssv):

        """True nếu tài khoản chưa đổi mật khẩu lần đầu (admin cấp mật khẩu random)."""

        return self.user_repo.is_first_login(mssv)



    def save_face_embedding(self, mssv, embedding):

        """

        Lưu face embedding — được FaceController gọi sau khi enroll xong.

        Ghi SQLite (has_face=1) rồi push has_face=True lên Firebase.

        """

        ok = self.user_repo.save_embedding(mssv, embedding)

        if ok:

            try:

                from app.services.firebase_hooks import push_has_face

                push_has_face(mssv)

            except Exception as e:

                print(f"[AuthService] push_has_face lỗi: {e}")

        return ok

    



    # def get_password(self, mssv):

    #     return self.user_repo.get_pass_by_mssv(mssv)



    def get_name_user(self, mssv):

        return self.user_repo.get_name_by_mssv(mssv)



    def get_email_user(self, mssv):



        return self.user_repo.get_email_by_mssv(mssv)



    def get_user(self, mssv):

    

        return self.user_repo.find_user(mssv)



    def send_otp_to_email(self, email):

        # random otp
        otp = str(secrets.randbelow(9000)+1000)

        subject = "🔑 Mã OTP Smart Locker"
        html = f"""
        <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;
                    border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
          <div style="background:#3b82f6;padding:24px 32px">
            <h2 style="color:#fff;margin:0">🔑 Mã OTP Xác Nhận</h2>
          </div>
          <div style="padding:28px 32px;color:#374151">
            <p>Bạn vừa yêu cầu mã OTP tại Kiosk Smart Locker.<br>
               Sử dụng mã dưới đây để xác nhận:</p>
            <div style="text-align:center;margin:28px 0">
              <span style="font-size:40px;font-weight:700;letter-spacing:12px;
                           color:#1d4ed8;background:#eff6ff;padding:16px 28px;
                           border-radius:12px;display:inline-block">{otp}</span>
            </div>
            <p style="color:#6b7280;font-size:14px">⏱ Mã có hiệu lực trong <strong>30 giây</strong>.</p>
            <p style="color:#ef4444;font-size:13px">⚠ Tuyệt đối không chia sẻ mã này cho bất kỳ ai.</p>
            <p style="margin-top:28px;color:#9ca3af;font-size:12px">
              Email tự động từ hệ thống Smart Locker — HCMUTE.<br>
              Nếu bạn không thực hiện yêu cầu này, vui lòng bỏ qua email.
            </p>
          </div>
        </div>"""

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"Smart Locker — HCMUTE <{EMAIL_SENDER}>"
            msg["To"]      = email
            msg.attach(MIMEText(html, "html", "utf-8"))

            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, email, msg.as_string())
            server.quit()
        except Exception as e:
            print(f"Lỗi gửi email: {e}")
            return (False, "Gửi OTP thất bại, vui lòng thử lại")


        Session.current_otp = otp

        Session.otp_expire_time = (
            datetime.now()
            + timedelta(seconds=60)
        )

        return (
            True,
            "Đã gửi OTP"
        )

    def verify_otp(self, otp_input):



        if Session.current_otp is None:



            return (

                False,

                "Chưa tạo OTP"

            )



        if datetime.now() > Session.otp_expire_time:



            Session.current_otp = None

            Session.otp_expire_time = None



            return (

                False,

                "OTP đã hết hạn"

            )



        if str(otp_input).strip() != str(Session.current_otp).strip():



            return (

                False,

                "OTP không đúng"

            )



        Session.current_otp = None

        Session.otp_expire_time = None





        return (

            True,

            "Xác thực thành công"



        )