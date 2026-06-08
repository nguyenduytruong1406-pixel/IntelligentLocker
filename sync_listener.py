import sqlite3
import firebase_admin
from firebase_admin import credentials, db
import time
import smtplib
import os
import random
import string
import hashlib                          # ← MỚI: để hash OTP
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# --- KHỞI TẠO BIẾN MÔI TRƯỜNG CHO EMAIL ---
load_dotenv(r"D:/DATN/Software/test_db_ver1/app_password.env")

# --- KHỞI TẠO FIREBASE (Chống lỗi gọi 2 lần) ---
if not firebase_admin._apps:
    cred = credentials.Certificate(r'D:/DATN/Software/test_db_ver1/private_key_lockers.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app'
    })

DB_PATH = r'D:/DATN/Software/test_db_ver1/IntelligentLocker.db'

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# ── HÀM SINH & GỬI OTP TRẢ TỦ ───────────────────────────────────────────────

def _generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

def _hash_otp(code: str) -> str:
    """SHA-256 hash của OTP — cái này lưu Firebase, KHÔNG lưu code gốc."""
    return hashlib.sha256(code.encode()).hexdigest()


def send_otp_email(student_email: str, student_name: str, mssv: str, otp_code: str) -> bool:
    """Gửi mail OTP xác nhận trả tủ."""
    sender_email    = os.getenv("MAIL_SENDER")
    sender_password = os.getenv("MAIL_PASSWORD")
    sender_name     = os.getenv("MAIL_SENDER_NAME", "Smart Locker — HCMUTE")

    if not sender_email or not sender_password:
        print("[Mail] ⚠ Chưa cấu hình MAIL_SENDER / MAIL_PASSWORD — không thể gửi OTP.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔑 Mã OTP trả tủ Smart Locker ({mssv})"
        msg["From"]    = f"{sender_name} <{sender_email}>"
        msg["To"]      = student_email

        html = f"""
        <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;
                    border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
          <div style="background:#3b82f6;padding:24px 32px">
            <h2 style="color:#fff;margin:0">🔑 Mã OTP Trả Tủ</h2>
          </div>
          <div style="padding:28px 32px;color:#374151">
            <p>Xin chào <strong>{student_name}</strong>,</p>
            <p>Bạn vừa yêu cầu trả tủ Smart Locker (<code>{mssv}</code>).<br>
               Sử dụng mã OTP dưới đây để xác nhận:</p>
            <div style="text-align:center;margin:28px 0">
              <span style="font-size:40px;font-weight:700;letter-spacing:12px;
                           color:#1d4ed8;background:#eff6ff;padding:16px 28px;
                           border-radius:12px;display:inline-block">{otp_code}</span>
            </div>
            <p style="color:#6b7280;font-size:14px">⏱ Mã có hiệu lực trong <strong>5 phút</strong>.</p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px">
              Email tự động từ hệ thống Smart Locker — HCMUTE.<br>
              Nếu bạn không thực hiện yêu cầu này, vui lòng bỏ qua email.
            </p>
          </div>
        </div>"""

        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, student_email, msg.as_string())
        print(f"[OTP] ✉ Đã gửi OTP tới {mssv} ({student_email})")
        return True
    except Exception as e:
        print(f"[OTP] ✗ Lỗi gửi OTP cho {mssv}: {e}")
        return False


def on_otp_request(event):
    """Lắng nghe /otp_requests/{mssv} — sinh OTP, lưu HASH vào /otp_tokens/{mssv}, gửi code gốc qua mail."""
    if event.path == '/':
        return
    mssv = event.path.strip('/').split('/')[0]
    request_data = db.reference(f'otp_requests/{mssv}').get()
    if not request_data:
        return   # node bị xóa — bỏ qua

    email = request_data.get('email', '')
    name  = request_data.get('name', mssv)
    if not email:
        user_data = db.reference(f'users/{mssv}').get() or {}
        email = user_data.get('email', '')
        name  = user_data.get('name', mssv)

    if not email:
        print(f"[OTP] ⚠ Không tìm thấy email cho {mssv} — bỏ qua.")
        return

    code       = _generate_otp()
    hashed     = _hash_otp(code)                          # ← hash để lưu Firebase
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Lưu HASH (không lưu code gốc) + số lần thử còn lại
    try:
        db.reference(f'otp_tokens/{mssv}').set({
            "hashed_code": hashed,      # ← client KHÔNG thể reverse về code gốc
            "expires_at" : expires_at,
            "attempts"   : 0,           # ← đếm số lần thử sai
        })
    except Exception as e:
        print(f"[OTP] ✗ Lỗi ghi otp_tokens/{mssv}: {e}")
        return

    send_otp_email(email, name, mssv, code)  # gửi code GỐC qua mail

    try:
        db.reference(f'otp_requests/{mssv}').delete()
    except Exception:
        pass


def on_verify_attempt(event):
    """
    Lắng nghe /verify_attempts/{mssv} — client gửi code nhập vào đây.
    Server so sánh hash và ghi kết quả vào /verify_results/{mssv}.
    Client KHÔNG bao giờ đọc otp_tokens.
    """
    if event.path == '/':
        return
    mssv = event.path.strip('/').split('/')[0]

    attempt_data = db.reference(f'verify_attempts/{mssv}').get()
    if not attempt_data:
        return

    entered_code = str(attempt_data.get('code', '')).strip()

    # Lấy token từ Firebase
    token = db.reference(f'otp_tokens/{mssv}').get()

    def _write_result(ok: bool, reason: str):
        db.reference(f'verify_results/{mssv}').set({
            "ok"       : ok,
            "reason"   : reason,
            "ts"       : datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        # Xóa attempt sau khi xử lý
        try:
            db.reference(f'verify_attempts/{mssv}').delete()
        except Exception:
            pass
        # Xóa verify_results sau 15 giây (đủ để client đọc xong)
        import threading
        def _cleanup():
            time.sleep(15)
            try:
                db.reference(f'verify_results/{mssv}').delete()
            except Exception:
                pass
        threading.Thread(target=_cleanup, daemon=True).start()

    if not token:
        _write_result(False, "no_token")
        print(f"[OTP-Verify] ⚠ {mssv}: không tìm thấy token")
        return

    # Kiểm tra hết hạn
    try:
        expires_dt = datetime.strptime(token['expires_at'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_dt:
            db.reference(f'otp_tokens/{mssv}').delete()
            _write_result(False, "expired")
            print(f"[OTP-Verify] ⏰ {mssv}: token hết hạn")
            return
    except Exception:
        _write_result(False, "invalid_token")
        return

    # Rate limit: tối đa 5 lần thử
    attempts = int(token.get('attempts', 0))
    MAX_ATTEMPTS = 5
    if attempts >= MAX_ATTEMPTS:
        db.reference(f'otp_tokens/{mssv}').delete()
        _write_result(False, "too_many_attempts")
        print(f"[OTP-Verify] 🚫 {mssv}: vượt quá {MAX_ATTEMPTS} lần thử — hủy token")
        return

    # So sánh hash
    hashed_entered = _hash_otp(entered_code)
    if hashed_entered == token.get('hashed_code', ''):
        # Đúng → xóa token (dùng 1 lần)
        try:
            db.reference(f'otp_tokens/{mssv}').delete()
        except Exception:
            pass
        _write_result(True, "ok")
        print(f"[OTP-Verify] ✅ {mssv}: OTP hợp lệ")
    else:
        # Sai → tăng attempts
        try:
            db.reference(f'otp_tokens/{mssv}').update({"attempts": attempts + 1})
        except Exception:
            pass
        remaining = MAX_ATTEMPTS - attempts - 1
        _write_result(False, f"wrong_code:{remaining}_left")
        print(f"[OTP-Verify] ❌ {mssv}: OTP sai — còn {remaining} lần thử")


# ── HÀM GỬI EMAIL THÔNG BÁO DUYỆT ───────────────────────────────────────────
def send_approval_email(student_email: str, student_name: str, mssv: str) -> bool:
    """Gửi email báo tài khoản đã được phê duyệt."""
    sender_email = os.getenv("MAIL_SENDER")
    sender_password = os.getenv("MAIL_PASSWORD")
    sender_name = os.getenv("MAIL_SENDER_NAME", "Smart Locker — HCMUTE")

    if not sender_email or not sender_password:
        print("[Mail] ⚠ Chưa cấu hình MAIL_SENDER / MAIL_PASSWORD — không thể gửi thư duyệt.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"✅ Tài khoản Smart Locker ({mssv}) đã được phê duyệt"
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = student_email

        html = f"""
        <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;
                    border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
          <div style="background:#10b981;padding:24px 32px">
            <h2 style="color:#fff;margin:0">✅ Đăng ký thành công!</h2>
          </div>
          <div style="padding:28px 32px;color:#374151">
            <p>Xin chào <strong>{student_name}</strong>,</p>
            <p>Yêu cầu đăng ký tài khoản tủ khóa (MSSV: <strong>{mssv}</strong>) của bạn 
               đã được admin xét duyệt thành công.</p>
            <div style="background:#d1fae5;border-left:4px solid #10b981;
                        padding:12px 16px;border-radius:6px;margin:20px 0">
              <strong>Bước tiếp theo:</strong> Vui lòng đến Kiosk tủ khóa để quét 
              và đăng ký khuôn mặt trước khi có thể mượn tủ.
            </div>
            <p style="margin-top:28px;color:#9ca3af;font-size:13px">
              Email tự động từ hệ thống Smart Locker — HCMUTE.<br>
              Vui lòng không reply trực tiếp email này.
            </p>
          </div>
        </div>"""
        
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, student_email, msg.as_string())
            
        print(f"[SyncListener] ✉ Đã gửi mail báo duyệt thành công tới {mssv}")
        return True
    except Exception as e:
        print(f"[SyncListener] ✗ Lỗi gửi mail duyệt cho {mssv}: {e}")
        return False


# ── 1. LẮNG NGHE THAY ĐỔI USER ───────────────────────────────────────────────
def on_user_change(event):
    if event.path == '/': return
    mssv = event.path.strip('/').split('/')[0]

    user_data = db.reference(f'users/{mssv}').get()
    
    if user_data is None:
        with get_conn() as conn:
            conn.execute("UPDATE Lockers SET status='empty', current_mssv=NULL WHERE current_mssv=?", (mssv,))
            conn.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
        print(f"[Sync] 🗑 Đã xóa user {mssv} và thu hồi tủ (nếu có)")
        return

    name        = user_data.get('name', 'Unknown')
    is_approved = int(user_data.get('is_approved', 0))
    email       = user_data.get('email', '')
    password_fb = user_data.get('password')
    has_face_fb = 1 if user_data.get('has_face') else 0

    old_is_approved = 0

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT has_face, password, is_approved FROM Users WHERE mssv=?", (mssv,))
        row = cur.fetchone()

        if row:
            merged_has_face  = max(row[0] or 0, has_face_fb)
            current_password = row[1]
            old_is_approved  = row[2] or 0
            final_password   = password_fb if password_fb else current_password

            cur.execute(
                "UPDATE Users SET name=?, is_approved=?, has_face=?, email=?, password=? WHERE mssv=?",
                (name, is_approved, merged_has_face, email, final_password, mssv)
            )
            act = "Cập nhật"
        else:
            cur.execute(
                "INSERT INTO Users (mssv, name, is_approved, has_face, email, password) VALUES (?, ?, ?, ?, ?, ?)",
                (mssv, name, is_approved, has_face_fb, email, password_fb)
            )
            act = "Thêm mới"
            
    status_text = "Đã duyệt" if is_approved == 1 else "Chờ duyệt"
    print(f"[Sync] 👤 {act} User: {name} ({mssv}) | {status_text}")

    if is_approved == 1 and old_is_approved == 0 and email:
        send_approval_email(email, name, mssv)


# ── 2. LẮNG NGHE THAY ĐỔI TỦ (TRẢ TỦ TỪ WEB) ───────────────────────────────
def on_locker_change(event):
    if event.path == '/': return
    lid = event.path.strip('/').split('/')[0]

    locker_data = db.reference(f'lockers/{lid}').get()
    if not locker_data: return

    status    = locker_data.get('status', 'empty').lower()
    last_open = locker_data.get('last_open') or ''

    with get_conn() as conn:
        if status == 'empty':
            conn.execute(
                """UPDATE Lockers
                   SET status='empty', current_mssv=NULL,
                       assigned_date=NULL, last_open=NULL
                   WHERE locker_id=?""",
                (lid,)
            )
            print(f"[Sync] 🔓 Trả tủ {lid} (Lệnh từ Web)")
            return

        if last_open:
            row = conn.execute(
                "SELECT last_open FROM Lockers WHERE locker_id=?", (lid,)
            ).fetchone()
            sq_last_open = (row[0] or '') if row else ''
            if last_open > sq_last_open:
                conn.execute(
                    "UPDATE Lockers SET last_open=? WHERE locker_id=?",
                    (last_open, lid)
                )
                print(f"[Sync] 🕐 last_open tủ {lid} → {last_open}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def start():
    print("[System] 📡 Đang bật kết nối Websocket Realtime...")
    db.reference('users').listen(on_user_change)
    db.reference('lockers').listen(on_locker_change)
    db.reference('otp_requests').listen(on_otp_request)
    db.reference('verify_attempts').listen(on_verify_attempt)   # ← MỚI
    print("[System] 📡 Đã bật listener: users / lockers / otp_requests / verify_attempts")

if __name__ == "__main__":
    start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Dừng lắng nghe.")