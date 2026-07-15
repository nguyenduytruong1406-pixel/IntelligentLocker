"""
sync_listener.py — Firebase Websocket Realtime listener (SML edition).

Lắng nghe thay đổi từ Firebase → SQLite (realtime ~0ms):
  /users           → on_user_change
  /lockers         → on_locker_change
  /otp_requests    → on_otp_request   (sinh OTP trả tủ, gửi mail)
  /verify_attempts → on_verify_attempt (server-side SHA-256 verify)

Daemon threads:
  _heartbeat_loop      — ghi /kiosk_status/last_seen mỗi 30s
  _cleanup_loop        — auto-cleanup tủ idle mỗi 1h

Chạy từ main.py:
    import sync_listener
    sync_listener.start()
"""

import os
import time
import random
import string
import hashlib
import smtplib
import threading

_stop_event = threading.Event()  # set khi app thoát
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ── Firebase (đã init từ app/firebase_config.py) ──────────────────────────────
from app.firebase_config import FIREBASE_OK
if FIREBASE_OK:
    from firebase_admin import db
else:
    db = None

# ── DB — dùng Database class của SML ─────────────────────────────────────────
from app.database.database import Database

def get_conn():
    _db = Database()
    return _db.connect()

# ── Mail config ───────────────────────────────────────────────────────────────
MAIL_SENDER      = os.getenv("EMAIL_SENDER") or os.getenv("MAIL_SENDER", "")
MAIL_PASSWORD    = os.getenv("EMAIL_PASSWORD") or os.getenv("MAIL_PASSWORD", "")
MAIL_SENDER_NAME = os.getenv("MAIL_SENDER_NAME", "Smart Locker — HCMUTE")

# NOTE: đã bỏ PENDING_EXPIRE_DAYS/PENDING_WARN_DAYS — không còn trạng thái
# tài khoản "chờ duyệt" nữa, admin cấp tài khoản là dùng được ngay.


# ══════════════════════════════════════════════════════════════════════════════
#  MAIL HELPERS — giao diện HTML đầy đủ
# ══════════════════════════════════════════════════════════════════════════════

def _send_mail(to_email: str, subject: str, html_body: str) -> bool:
    """Gửi mail qua Gmail SMTP. Trả True nếu thành công."""
    if not MAIL_SENDER or not MAIL_PASSWORD:
        print("[Mail] ⚠ Chưa cấu hình EMAIL_SENDER / EMAIL_PASSWORD trong .env")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{MAIL_SENDER_NAME} <{MAIL_SENDER}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(MAIL_SENDER, MAIL_PASSWORD)
            server.sendmail(MAIL_SENDER, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[Mail] ✗ Lỗi gửi tới {to_email}: {e}")
        return False


def send_otp_email(student_email: str, student_name: str, mssv: str, otp_code: str) -> bool:
    """Gửi mail OTP xác nhận trả tủ — HTML đầy đủ."""
    subject = f"🔑 Mã OTP trả tủ Smart Locker ({mssv})"
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
        <p style="color:#ef4444;font-size:13px">⚠ Tuyệt đối không chia sẻ mã này cho bất kỳ ai.</p>
        <p style="margin-top:28px;color:#9ca3af;font-size:12px">
          Email tự động từ hệ thống Smart Locker — HCMUTE.<br>
          Nếu bạn không thực hiện yêu cầu này, vui lòng bỏ qua email.
        </p>
      </div>
    </div>"""
    ok = _send_mail(student_email, subject, html)
    if ok:
        print(f"[OTP] ✉ Đã gửi OTP tới {mssv} ({student_email})")
    return ok


def send_credentials_email(student_email: str, student_name: str, mssv: str,
                            plain_password: str, locker_id: str, expiry_date: str) -> bool:
    """Gửi mail mật khẩu + tủ được cấp — dùng khi Kiosk online (đọc từ /pending_credentials)."""
    subject = f"🔐 Tài khoản Smart Locker của bạn ({mssv})"
    html = f"""
    <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;
                border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:#3b82f6;padding:24px 32px">
        <h2 style="color:#fff;margin:0">🔐 Tài khoản đã được cấp</h2>
      </div>
      <div style="padding:28px 32px;color:#374151">
        <p>Xin chào <strong>{student_name}</strong>,</p>
        <p>Tài khoản Smart Locker của bạn đã được admin cấp cùng tủ khóa
           <strong>{locker_id}</strong>. Thông tin đăng nhập tại Kiosk:</p>
        <div style="background:#eff6ff;border-left:4px solid #3b82f6;
                    padding:14px 18px;border-radius:6px;margin:20px 0">
          <p style="margin:4px 0"><strong>MSSV:</strong> {mssv}</p>
          <p style="margin:4px 0"><strong>Mật khẩu:</strong>
            <span style="font-family:monospace;font-size:16px;font-weight:700;
                         color:#1d4ed8">{plain_password}</span></p>
          <p style="margin:4px 0"><strong>Hạn dùng tủ:</strong> {expiry_date}</p>
        </div>
        <p style="color:#ef4444;font-size:13px">⚠ Vui lòng đổi mật khẩu ngay lần
           đăng nhập đầu tiên tại Kiosk.</p>
        <p style="margin-top:28px;color:#9ca3af;font-size:12px">
          Email tự động từ hệ thống Smart Locker — HCMUTE.<br>
          Nếu bạn không thực hiện yêu cầu này, vui lòng liên hệ admin ngay.
        </p>
      </div>
    </div>"""
    ok = _send_mail(student_email, subject, html)
    print(f"[Credentials] {'✉ Đã gửi' if ok else '✗ Gửi thất bại'} tới {mssv} ({student_email})")
    return ok

# ══════════════════════════════════════════════════════════════════════════════
#  OTP TRẢ TỦ — server-side SHA-256 verify
# ══════════════════════════════════════════════════════════════════════════════

def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def on_otp_request(event):
    """Lắng nghe /otp_requests/{mssv} — sinh OTP, lưu HASH vào Firebase, gửi code gốc qua mail."""
    if not FIREBASE_OK or event.path == "/":
        return
    mssv = event.path.strip("/").split("/")[0]
    request_data = db.reference(f"otp_requests/{mssv}").get()
    if not request_data:
        return

    email = request_data.get("email", "")
    name  = request_data.get("name", mssv)
    if not email:
        user_data = db.reference(f"users/{mssv}").get() or {}
        email = user_data.get("email", "")
        name  = user_data.get("name", mssv)
    if not email:
        print(f"[OTP] ⚠ Không tìm thấy email cho {mssv}")
        return

    code       = _generate_otp()
    hashed     = _hash_otp(code)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        db.reference(f"otp_tokens/{mssv}").set({
            "hashed_code": hashed,
            "expires_at" : expires_at,
            "attempts"   : 0,
        })
    except Exception as e:
        print(f"[OTP] ✗ Lỗi ghi otp_tokens/{mssv}: {e}")
        return

    send_otp_email(email, name, mssv, code)
    try:
        db.reference(f"otp_requests/{mssv}").delete()
    except Exception:
        pass


def on_verify_attempt(event):
    """
    Lắng nghe /verify_attempts/{mssv}.
    Client ghi code nhập vào đây, server so hash, ghi kết quả vào /verify_results/{mssv}.
    """
    if not FIREBASE_OK or event.path == "/":
        return
    mssv = event.path.strip("/").split("/")[0]
    attempt_data = db.reference(f"verify_attempts/{mssv}").get()
    if not attempt_data:
        return

    entered_code = str(attempt_data.get("code", "")).strip()
    token        = db.reference(f"otp_tokens/{mssv}").get()

    def _write_result(ok: bool, reason: str):
        db.reference(f"verify_results/{mssv}").set({
            "ok"    : ok,
            "reason": reason,
            "ts"    : datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        try:
            db.reference(f"verify_attempts/{mssv}").delete()
        except Exception:
            pass
        def _cleanup():
            time.sleep(15)
            try:
                db.reference(f"verify_results/{mssv}").delete()
            except Exception:
                pass
        threading.Thread(target=_cleanup, daemon=True).start()

    if not token:
        _write_result(False, "no_token")
        return

    try:
        expires_dt = datetime.strptime(token["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_dt:
            db.reference(f"otp_tokens/{mssv}").delete()
            _write_result(False, "expired")
            print(f"[OTP-Verify] ⏰ {mssv}: token hết hạn")
            return
    except Exception:
        _write_result(False, "invalid_token")
        return

    attempts     = int(token.get("attempts", 0))
    MAX_ATTEMPTS = 5
    if attempts >= MAX_ATTEMPTS:
        db.reference(f"otp_tokens/{mssv}").delete()
        _write_result(False, "too_many_attempts")
        print(f"[OTP-Verify] 🚫 {mssv}: vượt quá {MAX_ATTEMPTS} lần thử")
        return

    if _hash_otp(entered_code) == token.get("hashed_code", ""):
        try:
            db.reference(f"otp_tokens/{mssv}").delete()
        except Exception:
            pass
        _write_result(True, "ok")
        print(f"[OTP-Verify] ✅ {mssv}: OTP hợp lệ")
    else:
        try:
            db.reference(f"otp_tokens/{mssv}").update({"attempts": attempts + 1})
        except Exception:
            pass
        remaining = MAX_ATTEMPTS - attempts - 1
        _write_result(False, f"wrong_code:{remaining}_left")
        print(f"[OTP-Verify] ❌ {mssv}: OTP sai — còn {remaining} lần thử")


# ══════════════════════════════════════════════════════════════════════════════
#  FIREBASE LISTENERS
# ══════════════════════════════════════════════════════════════════════════════

def on_user_change(event):
    if event.path == "/":
        return
    mssv = event.path.strip("/").split("/")[0]

    user_data = db.reference(f"users/{mssv}").get()

    if user_data is None:
        with get_conn() as conn:
            conn.execute(
                """UPDATE Lockers SET status='empty', current_mssv=NULL,
                   assigned_date=NULL, last_open=NULL WHERE current_mssv=?""",
                (mssv,)
            )
            conn.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
            conn.commit()
        print(f"[Sync] 🗑 Xóa user {mssv} và thu hồi tủ")
        return

    name        = user_data.get("name", "Unknown")
    email       = user_data.get("email", "")
    password_fb = user_data.get("password")
    has_face_fb = 1 if user_data.get("has_face") else 0
    # None nếu Firebase chưa có field này (đa số trường hợp — kiosk là nguồn
    # xác thực). Chỉ override local khi Firebase có giá trị rõ ràng.
    fb_first_login = user_data.get("is_first_login")
    row = None

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT has_face, password, is_first_login FROM Users WHERE mssv=?", (mssv,))
        row = cur.fetchone()

        if row:
            merged_has_face = max(row[0] or 0, has_face_fb)
            current_password = row[1]
            final_password   = password_fb if password_fb else current_password
            local_first_login = 1 if row[2] is None else int(row[2])
            final_first_login = int(bool(fb_first_login)) if fb_first_login is not None else local_first_login
            cur.execute(
                "UPDATE Users SET name=?, has_face=?, email=?, password=?, is_first_login=? WHERE mssv=?",
                (name, merged_has_face, email, final_password, final_first_login, mssv)
            )
        else:
            new_first_login = int(bool(fb_first_login)) if fb_first_login is not None else 1
            cur.execute(
                "INSERT INTO Users (mssv, name, has_face, email, password, is_first_login) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (mssv, name, has_face_fb, email, password_fb, new_first_login)
            )
        conn.commit()

    print(f"[Sync] 👤 {'Cập nhật' if row else 'Thêm'} user {name} ({mssv})")


# ══════════════════════════════════════════════════════════════════════════════
#  PENDING_CREDENTIALS — Kiosk online tự gửi mail mật khẩu, rồi xóa node
# ══════════════════════════════════════════════════════════════════════════════

def on_pending_credentials(event):
    if event.path == "/":
        return
    mssv = event.path.strip("/").split("/")[0]

    cred = db.reference(f"pending_credentials/{mssv}").get()
    if cred is None:
        return  # đã xử lý/xóa rồi (hoặc bị xóa tay)

    plain_password = cred.get("password")
    locker_id      = cred.get("locker_id", "—")
    expiry_date    = cred.get("expiry_date", "—")

    # Lấy tên + email: ưu tiên SQLite local (đã sync qua on_user_change),
    # fallback sang Firebase users/{mssv} nếu vì lý do gì local chưa kịp cập nhật.
    name, email = None, None
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name, email FROM Users WHERE mssv=?", (mssv,))
        row = cur.fetchone()
        if row:
            name, email = row[0], row[1]

    if not email:
        user_fb = db.reference(f"users/{mssv}").get() or {}
        name  = name or user_fb.get("name", mssv)
        email = email or user_fb.get("email")

    if not email or not plain_password:
        print(f"[Credentials] ✗ Thiếu email hoặc mật khẩu cho {mssv} — bỏ qua")
        return

    ok = send_credentials_email(email, name or mssv, mssv, plain_password, locker_id, expiry_date)

    if ok:
        db.reference(f"pending_credentials/{mssv}").delete()


def on_locker_change(event):
    if event.path == "/":
        return
    lid = event.path.strip("/").split("/")[0]

    locker_data = db.reference(f"lockers/{lid}").get()
    if not locker_data:
        return

    status        = locker_data.get("status", "empty").lower()
    last_open     = locker_data.get("last_open") or ""
    current_mssv  = locker_data.get("current_mssv") or None
    assigned_date = locker_data.get("assigned_date") or None

    with get_conn() as conn:
        if status == "empty":
            conn.execute(
                """UPDATE Lockers SET status='empty', current_mssv=NULL,
                   assigned_date=NULL, last_open=NULL WHERE locker_id=?""",
                (lid,)
            )
            conn.commit()
            print(f"[Sync] 🔓 Trả tủ {lid} (lệnh từ Web)")
            return

        # NOTE: trước đây nhánh này CHỈ cập nhật last_open, không hề ghi
        # current_mssv/status/assigned_date vào SQLite — nghĩa là khi admin
        # gán tủ trên web trong lúc kiosk đang chạy, current_mssv KHÔNG BAO
        # GIỜ được đồng bộ về, khiến check_user_has_locker() luôn báo "không
        # có tủ". Giờ luôn ghi đủ cả status/current_mssv/assigned_date.
        row = conn.execute(
            "SELECT current_mssv, status, assigned_date, last_open FROM Lockers WHERE locker_id=?",
            (lid,)
        ).fetchone()
        sq_mssv      = row[0] if row else None
        sq_status    = (row[1] or "empty").lower() if row else "empty"
        sq_assigned  = row[2] if row else None
        sq_last_open = (row[3] or "") if row else ""

        final_last_open = max(sq_last_open, last_open) if sq_last_open else last_open

        if (sq_mssv != current_mssv or sq_status != status
                or sq_assigned != assigned_date or sq_last_open != final_last_open):
            conn.execute(
                """UPDATE Lockers SET status=?, current_mssv=?, assigned_date=?,
                   last_open=? WHERE locker_id=?""",
                (status, current_mssv, assigned_date, final_last_open, lid)
            )
            conn.commit()
            print(f"[Sync] 📌 Gán tủ {lid} → {current_mssv} (lệnh từ Web)")


# ══════════════════════════════════════════════════════════════════════════════
#  DAEMON THREADS
# ══════════════════════════════════════════════════════════════════════════════

def _heartbeat_loop():
    """Ghi /kiosk_status/last_seen lên Firebase mỗi 30 giây."""
    from app.services.firebase_hooks import push_heartbeat
    while not _stop_event.is_set():
        push_heartbeat()
        _stop_event.wait(30)


def _cleanup_loop():
    """Auto-cleanup tủ idle ≥7 ngày — chạy mỗi 1 giờ."""
    from app.services.cleanup_service import CleanupService
    svc = CleanupService()
    while not _stop_event.is_set():
        try:
            svc.cleanup_users()
        except Exception as e:
            print(f"[CleanupLoop] Lỗi: {e}")
        _stop_event.wait(3_600)


# NOTE: đã xoá _check_pending_expire() và _pending_expire_loop() — toàn bộ
# cơ chế quét/tự xóa/tự cảnh báo tài khoản "chờ duyệt quá hạn" không còn cần
# thiết vì tài khoản chỉ được tạo khi admin đã cấp trực tiếp, không có trạng
# thái chờ duyệt trung gian nữa.


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def start():
    """
    Đăng ký Firebase listeners + khởi động daemon threads.
    Fail-safe: Firebase offline → bỏ qua listeners, daemon threads vẫn chạy.
    """
    if not FIREBASE_OK or db is None:
        print("[SyncListener] ⚠ Firebase offline — chỉ chạy daemon threads")
    else:
        try:
            db.reference("users").listen(on_user_change)
            db.reference("lockers").listen(on_locker_change)
            db.reference("otp_requests").listen(on_otp_request)
            db.reference("verify_attempts").listen(on_verify_attempt)
            db.reference("pending_credentials").listen(on_pending_credentials)
            print("[SyncListener] 📡 Listeners: users / lockers / otp_requests / verify_attempts")
        except Exception as e:
            print(f"[SyncListener] ✗ Lỗi khởi động listeners: {e}")

    threading.Thread(target=_heartbeat_loop,      daemon=True).start()
    threading.Thread(target=_cleanup_loop,        daemon=True).start()
    print("[SyncListener] 🔄 Daemon threads: heartbeat / cleanup")


if __name__ == "__main__":
    start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Dừng lắng nghe.")