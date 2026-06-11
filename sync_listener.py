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
  _pending_expire_loop — xóa tài khoản pending hết hạn mỗi 6h

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

PENDING_EXPIRE_DAYS = 7
PENDING_WARN_DAYS   = 2


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


def send_approval_email(student_email: str, student_name: str, mssv: str) -> bool:
    """Gửi mail báo tài khoản đã được admin duyệt."""
    subject = f"✅ Tài khoản Smart Locker ({mssv}) đã được phê duyệt"
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
    ok = _send_mail(student_email, subject, html)
    if ok:
        print(f"[SyncListener] ✉ Gửi mail duyệt tới {mssv}")
    return ok


def _mail_warning(name: str, mssv: str, email: str, days_left: int, registered_at: str):
    """Mail cảnh báo tài khoản pending sắp bị xóa."""
    subject = f"⚠️ Tài khoản Smart Locker sắp bị xóa — còn {days_left} ngày"
    html = f"""
    <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;
                border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:#f59e0b;padding:24px 32px">
        <h2 style="color:#fff;margin:0">⚠️ Tài khoản sắp bị xóa tự động</h2>
      </div>
      <div style="padding:28px 32px;color:#374151">
        <p>Xin chào <strong>{name}</strong>,</p>
        <p>Tài khoản <strong>Smart Locker</strong> của bạn (<code>{mssv}</code>)
           đăng ký ngày <strong>{registered_at}</strong> vẫn chưa được admin duyệt.</p>
        <div style="background:#fef3c7;border-left:4px solid #f59e0b;
                    padding:12px 16px;border-radius:6px;margin:20px 0">
          <strong>Tài khoản sẽ bị xóa tự động sau
          <span style="color:#b45309">{days_left} ngày nữa</span>
          nếu không được duyệt.</strong>
        </div>
        <p>Nếu bạn vẫn muốn sử dụng tủ, hãy liên hệ admin để được duyệt sớm.</p>
        <p style="margin-top:28px;color:#9ca3af;font-size:13px">
          Email tự động từ hệ thống Smart Locker — HCMUTE.<br>
          Vui lòng không reply trực tiếp email này.
        </p>
      </div>
    </div>"""
    ok = _send_mail(email, subject, html)
    print(f"[PendingExpire] {'✉ Mail cảnh báo →' if ok else '✗ Gửi thất bại —'} {name} ({mssv}) | còn {days_left} ngày")


def _mail_expired(name: str, mssv: str, email: str):
    """Mail thông báo tài khoản đã bị xóa do pending quá hạn."""
    subject = "❌ Tài khoản Smart Locker đã bị xóa tự động"
    html = f"""
    <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;
                border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:#ef4444;padding:24px 32px">
        <h2 style="color:#fff;margin:0">❌ Tài khoản đã bị xóa</h2>
      </div>
      <div style="padding:28px 32px;color:#374151">
        <p>Xin chào <strong>{name}</strong>,</p>
        <p>Tài khoản Smart Locker <code>{mssv}</code> đã bị <strong>xóa tự động</strong>
           do chờ duyệt quá {PENDING_EXPIRE_DAYS} ngày mà chưa có phản hồi từ admin.</p>
        <p>Nếu bạn vẫn muốn sử dụng dịch vụ, vui lòng
           <a href="https://lockerxmakerspacexhcmute.web.app/register.html"
              style="color:#3b82f6">đăng ký lại tại đây</a>
           và liên hệ admin để được duyệt sớm.</p>
        <p style="margin-top:28px;color:#9ca3af;font-size:13px">
          Email tự động từ hệ thống Smart Locker — HCMUTE.
        </p>
      </div>
    </div>"""
    ok = _send_mail(email, subject, html)
    print(f"[PendingExpire] {'✉ Mail xóa →' if ok else '✗ Gửi thất bại —'} {name} ({mssv})")


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
                "UPDATE Lockers SET status='empty', current_mssv=NULL WHERE current_mssv=?",
                (mssv,)
            )
            conn.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
            conn.commit()
        print(f"[Sync] 🗑 Xóa user {mssv} và thu hồi tủ")
        return

    name        = user_data.get("name", "Unknown")
    is_approved = int(user_data.get("is_approved", 0))
    email       = user_data.get("email", "")
    password_fb = user_data.get("password")
    has_face_fb = 1 if user_data.get("has_face") else 0
    old_is_approved = 0
    row = None

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT has_face, password, is_approved FROM Users WHERE mssv=?", (mssv,))
        row = cur.fetchone()

        if row:
            merged_has_face = max(row[0] or 0, has_face_fb)
            current_password = row[1]
            old_is_approved  = row[2] or 0
            final_password   = password_fb if password_fb else current_password
            cur.execute(
                "UPDATE Users SET name=?, is_approved=?, has_face=?, email=?, password=? WHERE mssv=?",
                (name, is_approved, merged_has_face, email, final_password, mssv)
            )
        else:
            cur.execute(
                "INSERT INTO Users (mssv, name, is_approved, has_face, email, password) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (mssv, name, is_approved, has_face_fb, email, password_fb)
            )
        conn.commit()

    print(f"[Sync] 👤 {'Cập nhật' if row else 'Thêm'} user {name} ({mssv}) | "
          f"{'Đã duyệt' if is_approved else 'Chờ duyệt'}")

    if is_approved == 1 and old_is_approved == 0 and email:
        send_approval_email(email, name, mssv)


def on_locker_change(event):
    if event.path == "/":
        return
    lid = event.path.strip("/").split("/")[0]

    locker_data = db.reference(f"lockers/{lid}").get()
    if not locker_data:
        return

    status    = locker_data.get("status", "empty").lower()
    last_open = locker_data.get("last_open") or ""

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

        if last_open:
            row = conn.execute(
                "SELECT last_open FROM Lockers WHERE locker_id=?", (lid,)
            ).fetchone()
            sq_last_open = (row[0] or "") if row else ""
            if last_open > sq_last_open:
                conn.execute(
                    "UPDATE Lockers SET last_open=? WHERE locker_id=?",
                    (last_open, lid)
                )
                conn.commit()
                print(f"[Sync] 🕐 last_open tủ {lid} → {last_open}")


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


def _check_pending_expire():
    """Quét Firebase /users, xử lý tài khoản pending quá hạn."""
    if not FIREBASE_OK:
        return
    try:
        users: dict = db.reference("users").get() or {}
    except Exception as e:
        print(f"[PendingExpire] Lỗi đọc Firebase: {e}")
        return

    now_date = datetime.now().strftime("%Y-%m-%d")

    for mssv, u in users.items():
        approved = u.get("is_approved", 0)
        if str(approved) in ("1", "true", "True") or approved is True:
            continue
        registered_at = u.get("registered_at", "")
        if not registered_at:
            continue

        name  = u.get("name", mssv)
        email = u.get("email", "")
        try:
            dt   = datetime.strptime(registered_at.strip(), "%Y-%m-%d %H:%M:%S")
            days = (datetime.now() - dt).days
        except Exception:
            continue

        days_left = PENDING_EXPIRE_DAYS - days

        if days >= PENDING_EXPIRE_DAYS:
            # Hết hạn → xóa
            print(f"[PendingExpire] Xóa {name} ({mssv}) — chờ {days} ngày")
            try:
                db.reference("locker_delete_logs").push({
                    "mssv"       : mssv,
                    "locker_id"  : "",
                    "delete_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "reason"     : "auto_expired_pending",
                    "name"       : name,
                })
                db.reference(f"users/{mssv}").delete()
            except Exception as e:
                print(f"[PendingExpire] Lỗi xóa {mssv}: {e}")
                continue
            if email:
                _mail_expired(name, mssv, email)

        elif days_left <= PENDING_WARN_DAYS and email:
            # Sắp hết hạn → cảnh báo (1 lần/ngày)
            flag_dir  = BASE_DIR / ".warn_flags"
            flag_path = flag_dir / f"warn_{mssv}_{now_date}"
            if not flag_path.exists():
                flag_dir.mkdir(exist_ok=True)
                flag_path.touch()
                _mail_warning(name, mssv, email, days_left, registered_at)
                # Dọn flag cũ > 3 ngày
                for f in flag_dir.iterdir():
                    if f.is_file() and (time.time() - f.stat().st_mtime) > 3 * 86400:
                        f.unlink(missing_ok=True)


def _pending_expire_loop():
    """Daemon — chạy check pending expire mỗi 6 giờ."""
    _stop_event.wait(30)  # chờ Firebase init xong
    while not _stop_event.is_set():
        try:
            _check_pending_expire()
        except Exception as e:
            print(f"[PendingExpire] Lỗi không xử lý được: {e}")
        _stop_event.wait(6 * 3_600)


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
            print("[SyncListener] 📡 Listeners: users / lockers / otp_requests / verify_attempts")
        except Exception as e:
            print(f"[SyncListener] ✗ Lỗi khởi động listeners: {e}")

    threading.Thread(target=_heartbeat_loop,      daemon=True).start()
    threading.Thread(target=_cleanup_loop,        daemon=True).start()
    threading.Thread(target=_pending_expire_loop, daemon=True).start()
    print("[SyncListener] 🔄 Daemon threads: heartbeat / cleanup / pending_expire")


if __name__ == "__main__":
    start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Dừng lắng nghe.")