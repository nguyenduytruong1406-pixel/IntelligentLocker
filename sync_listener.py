"""
sync_listener.py — Firebase Websocket Realtime listener (SML edition).
 
Lắng nghe thay đổi từ Firebase → SQLite (realtime ~0ms):
  /users           → on_user_change
  /lockers         → on_locker_change
  /otp_requests    → on_otp_request   (sinh OTP trả tủ, gửi mail)
  /verify_attempts → on_verify_attempt (server-side SHA-256 verify)
 
Daemon threads:
  _heartbeat_loop      — ghi /kiosk_status/last_seen mỗi 30s
  _watchdog_loop        — mỗi 20s, tự đăng ký lại listener bị chết do mất mạng;
                           sau khi khôi phục, tự chạy sync_tool.py --sync (bù
                           users/lockers/locker_delete_logs) và quét bù
                           pending_credentials (mail mật khẩu bị lỡ lúc offline)
 
NOTE: cleanup tủ idle (cleanup_idle_lockers) KHÔNG chạy ở đây nữa — đã có
CleanupWorker (QThread) trong main.py đảm nhiệm, tránh chạy trùng 2 nơi
cùng lúc gây race condition / gửi email thu hồi tủ 2 lần.
 
Chạy từ main.py:
    import sync_listener
    sync_listener.start()
"""

import os
import sys
import time
import random
import string
import hashlib
import smtplib
import subprocess
import threading
import traceback


def _safe_listener(fn):
    """Bọc callback .listen() — exception trong thread nền Firebase SDK trước
    đây bị nuốt âm thầm (không in gì, không crash), khiến sự kiện bị bỏ qua
    hoàn toàn mà không ai biết (đăng ký/gán tủ 'biến mất'). Giờ luôn in
    traceback ra console để thấy được lỗi thật."""
    def wrapper(event):
        try:
            return fn(event)
        except Exception:
            print(f"[SyncListener] ✗ Lỗi xử lý {fn.__name__} (path={getattr(event, 'path', '?')}):")
            traceback.print_exc()
    wrapper.__name__ = fn.__name__
    return wrapper

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

@_safe_listener
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
    # locker_expiry_date: web ghi field này ngay khi admin cấp tài khoản/tủ —
    # cần kéo về SQLite realtime để kiosk tính được ngày quá hạn tại chỗ,
    # không phải chờ tới lần chạy sync_tool.py kế tiếp.
    expiry_fb   = user_data.get("locker_expiry_date", "") or ""
    # None nếu Firebase chưa có field này (đa số trường hợp — kiosk là nguồn
    # xác thực). Chỉ override local khi Firebase có giá trị rõ ràng.
    fb_first_login = user_data.get("is_first_login")
    row = None

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT has_face, password, is_first_login, locker_expiry_date FROM Users WHERE mssv=?", (mssv,))
        row = cur.fetchone()

        if row:
            merged_has_face = max(row[0] or 0, has_face_fb)
            current_password = row[1]
            final_password   = password_fb if password_fb else current_password
            local_first_login = 1 if row[2] is None else int(row[2])
            final_first_login = int(bool(fb_first_login)) if fb_first_login is not None else local_first_login
            # Firebase là nguồn xác thực cho hạn tủ — chỉ ghi đè khi có giá trị
            final_expiry = expiry_fb if expiry_fb else (row[3] or "")
            cur.execute(
                "UPDATE Users SET name=?, has_face=?, email=?, password=?, is_first_login=?, "
                "locker_expiry_date=? WHERE mssv=?",
                (name, merged_has_face, email, final_password, final_first_login, final_expiry, mssv)
            )
        else:
            new_first_login = int(bool(fb_first_login)) if fb_first_login is not None else 1
            cur.execute(
                "INSERT INTO Users (mssv, name, has_face, email, password, is_first_login, locker_expiry_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mssv, name, has_face_fb, email, password_fb, new_first_login, expiry_fb)
            )
        conn.commit()

    print(f"[Sync] 👤 {'Cập nhật' if row else 'Thêm'} user {name} ({mssv})")


# ══════════════════════════════════════════════════════════════════════════════
#  PENDING_CREDENTIALS — Kiosk online tự gửi mail mật khẩu, rồi xóa node
# ══════════════════════════════════════════════════════════════════════════════

def _process_pending_credential(mssv: str):
    """Xử lý gửi mail mật khẩu cho 1 mssv trong /pending_credentials.
    Dùng chung cho on_pending_credentials (event realtime) VÀ
    _catchup_pending_credentials (quét bù lúc vừa khôi phục mạng) — cùng 1
    logic, tránh lệch nhau giữa 2 đường gọi."""
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
        # Ghi lại để web (index.html/_mailStatusFor) biết mail ĐÃ gửi — nếu không
        # ghi bước này, sau khi pending_credentials bị xóa, cột "Gửi Mail" trên
        # web sẽ không khớp điều kiện nào (không còn trong pending_credentials,
        # cũng chưa có trong credential_email_log) và hiển thị trống dù mail đã
        # gửi thành công.
        db.reference(f"credential_email_log/{mssv}").set({
            "locker_id": locker_id,
            "expiry_date": expiry_date,
            "sent_via": "kiosk_sync_listener",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })


@_safe_listener
def on_pending_credentials(event):
    if event.path == "/":
        return
    mssv = event.path.strip("/").split("/")[0]
    _process_pending_credential(mssv)


def _catchup_pending_credentials():
    """
    VẤN ĐỀ: nếu web ghi /pending_credentials/{mssv} ĐÚNG LÚC kiosk mất mạng,
    node đó vẫn nằm nguyên trên Firebase, chưa gửi mail. Khi mạng có lại và
    listener .listen() được đăng ký lại, event ĐẦU TIÊN nhận được là snapshot
    toàn bộ (event.path == "/") — bị on_pending_credentials cố tình bỏ qua.
    Vì node không có ghi (write) MỚI nào sau khi kết nối lại, sẽ KHÔNG có
    event nào khác bắn ra cho mssv đó nữa → mail bị treo vĩnh viễn nếu không
    quét bù.

    Khác với otp_requests/verify_attempts (có hạn 5 phút — xử lý trễ vô
    nghĩa, không cần bù), pending_credentials KHÔNG có hạn — xử lý trễ vẫn
    đúng, nên an toàn để đọc lại toàn bộ node 1 lần và xử lý những gì còn sót.
    Idempotent: _process_pending_credential tự return sớm nếu mssv đã được
    xử lý/xóa từ trước, gọi lại nhiều lần không sao.
    """
    if not FIREBASE_OK or db is None:
        return
    try:
        snap = db.reference("pending_credentials").get() or {}
    except Exception as e:
        print(f"[Credentials] ✗ Không đọc được pending_credentials để quét bù: {e}")
        return
    if not snap:
        return
    print(f"[Credentials] 🔄 Phát hiện {len(snap)} pending_credentials còn treo — xử lý bù...")
    for mssv in list(snap.keys()):
        _process_pending_credential(mssv)


@_safe_listener
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


@_safe_listener
def on_delete_log_added(event):
    """
    Đồng bộ realtime locker_delete_logs (Firebase) → LOCKER_DELETE_LOG
    (SQLite local). Bù cho sync_tool.py chỉ chạy 1 lần lúc boot — nếu
    Kiosk chạy nhiều giờ không restart, log admin tạo từ web trong lúc đó
    (admin_force, admin_delete_card, new_assignment từ web, sync_auto_fix)
    sẽ không vào SQLite local kịp nếu chỉ trông vào sync_tool.py.

    event.path == "/" là snapshot ban đầu lúc mới .listen() — bỏ qua vì
    sync_tool.py đã lo phần lịch sử cũ lúc boot, ở đây chỉ xử lý entry MỚI
    thêm sau đó (event.path = "/{firebase_push_key}").
    """
    if event.path == "/":
        return
    entry = event.data
    if not isinstance(entry, dict):
        return

    mssv   = entry.get("mssv", "") or ""
    lid    = entry.get("locker_id", "") or ""
    dtime  = entry.get("delete_time", "") or ""
    reason = entry.get("reason", "") or ""
    if not dtime or not reason:
        return

    with get_conn() as conn:
        # Dedup theo (MSSV, LOCKER_ID, DELETE_TIME, REASON) — nếu log này do
        # chính Kiosk tạo (locker_repository._log_delete ghi SQLite rồi mới
        # push lên Firebase), nó đã có sẵn ở đây, tránh ghi trùng.
        exists = conn.execute(
            """SELECT 1 FROM LOCKER_DELETE_LOG
               WHERE MSSV=? AND LOCKER_ID=? AND DELETE_TIME=? AND REASON=?""",
            (mssv, lid, dtime, reason),
        ).fetchone()
        if exists:
            return
        conn.execute(
            """INSERT INTO LOCKER_DELETE_LOG (MSSV, LOCKER_ID, DELETE_TIME, REASON)
               VALUES (?, ?, ?, ?)""",
            (mssv, lid, dtime, reason),
        )
        conn.commit()
        print(f"[Sync] 📜 Đồng bộ log thu hồi (từ Web): {mssv}/{lid} — {reason}")


# ══════════════════════════════════════════════════════════════════════════════
#  DAEMON THREADS
# ══════════════════════════════════════════════════════════════════════════════

def _heartbeat_loop():
    """Ghi /kiosk_status/last_seen lên Firebase mỗi 30 giây."""
    from app.services.firebase_hooks import push_heartbeat
    while not _stop_event.is_set():
        push_heartbeat()
        _stop_event.wait(30)


# ── Reconnect watchdog ─────────────────────────────────────────────────────────
# VẤN ĐỀ: db.Reference.listen() chạy 1 thread nền đọc SSE stream. Khi mạng đứt
# giữa chừng, SDK tự bắt lỗi và gọi lại self._connect() để nối lại — nhưng nếu
# NGAY LÚC ĐÓ mạng vẫn chưa có, self._connect() tự nó ném exception, và
# exception này không được bắt ở đâu cả (xem _sseclient.py / db.py của
# firebase-admin) → thread nền chết âm thầm, không log gì. Từ đó sync im luôn,
# kể cả khi mạng có lại sau đó, vì không còn ai gọi lại .listen(). Cùng lỗi này
# xảy ra nếu mất mạng NGAY LÚC start() chạy lần đầu (listen() đầu tiên ném lỗi
# → toàn bộ khối try trong start() dừng giữa chừng, các listener sau đó không
# được đăng ký luôn, không chỉ riêng 1 cái).
#
# _LISTENER_SPECS liệt kê mọi listener cần có. _listener_regs giữ
# ListenerRegistration hiện tại của từng cái (hoặc None nếu chưa từng đăng ký
# thành công). _watchdog_loop() chạy mỗi 20s, kiểm tra thread nền
# (registration._thread) của từng listener còn sống hay không — nếu chết
# (hoặc chưa từng đăng ký được) thì gọi lại .listen() để hồi phục, không cần
# restart app / chạy lại file.
_LISTENER_SPECS = [
    ("users",               "users",               "on_user_change"),
    ("lockers",             "lockers",             "on_locker_change"),
    ("otp_requests",        "otp_requests",        "on_otp_request"),
    ("verify_attempts",     "verify_attempts",     "on_verify_attempt"),
    ("pending_credentials", "pending_credentials", "on_pending_credentials"),
    ("locker_delete_logs",  "locker_delete_logs",  "on_delete_log_added"),
]
_listener_regs: dict = {}  # name -> ListenerRegistration | None


def _listener_alive(name: str) -> bool:
    reg = _listener_regs.get(name)
    if reg is None:
        return False
    thread = getattr(reg, "_thread", None)
    return thread is not None and thread.is_alive()


def _run_catchup_sync():
    """
    VẤN ĐỀ: khi 1 listener vừa được đăng ký lại sau khi mất mạng, event đầu
    tiên SDK gửi là 1 snapshot toàn bộ dữ liệu (event.path == "/") — nhưng
    MỌI callback on_*_change đều cố tình `return` ngay khi gặp event này
    (đúng cho lúc khởi động bình thường, để khỏi xử lý lại y hệt dữ liệu cũ).
    Hệ quả: .listen() chỉ báo sự kiện MỚI kể từ lúc kết nối lại — những thay
    đổi diễn ra TRONG khoảng thời gian mất mạng (web gán tủ, admin xóa tài
    khoản, sinh viên trả tủ...) sẽ không có event nào bắn ra cả, nên bị bỏ
    lỡ vĩnh viễn nếu không có bước bù riêng.

    FIX: chạy lại đúng logic đối soát 2 chiều mà sync_tool.py vẫn dùng lúc
    boot (`python sync_tool.py --sync` = pull Firebase→SQLite rồi push
    SQLite→Firebase) trong 1 subprocess riêng — không import trực tiếp vì
    sync_tool.py có code chạy ngay ở module-level (mở connection SQLite
    riêng, có thể sys.exit(0)), an toàn hơn khi để nó chạy độc lập như 1
    tool, đúng như thiết kế ban đầu của nó.
    """
    def _worker():
        try:
            print("[SyncListener] 🔄 Vừa khôi phục mạng — chạy sync_tool.py --sync để bù dữ liệu bị lỡ...")
            # QUAN TRỌNG (Windows): khi stdout bị capture_output=True redirect
            # sang pipe (không còn là console thật), Python trên Windows mặc
            # định encode theo codepage hệ thống (thường là cp1252) thay vì
            # UTF-8 — mà firebase_config.py/sync_tool.py có in ký tự ✅/✗/⚠,
            # không tồn tại trong cp1252 → UnicodeEncodeError, crash ngay từ
            # bước import. Ép PYTHONIOENCODING=utf-8 cho process con để nó
            # luôn ghi stdout/stderr bằng UTF-8 bất kể console cha là gì.
            child_env = os.environ.copy()
            child_env["PYTHONIOENCODING"] = "utf-8"
            child_env["PYTHONUTF8"] = "1"
            result = subprocess.run(
                [sys.executable, str(BASE_DIR / "sync_tool.py"), "--sync"],
                cwd=str(BASE_DIR),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env=child_env, timeout=120,
            )
            if result.returncode == 0:
                print("[SyncListener] ✅ sync_tool --sync hoàn tất (đã bù dữ liệu bị lỡ lúc mất mạng)")
            else:
                tail = (result.stderr or result.stdout)[-2000:]
                print(f"[SyncListener] ✗ sync_tool --sync lỗi (exit {result.returncode}):\n{tail}")
        except Exception as e:
            print(f"[SyncListener] ✗ Không chạy được sync_tool --sync: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def _register_missing_listeners():
    """Đăng ký (hoặc đăng ký lại) mọi listener hiện đang thiếu/chết. An toàn để
    gọi lặp lại nhiều lần — listener đang sống bình thường sẽ được bỏ qua.

    - Có listener nào vừa được đăng ký (lần đầu HOẶC khôi phục) → quét bù
      pending_credentials (_catchup_pending_credentials) — rẻ, idempotent,
      nên chạy cả lúc khởi động lần đầu cho chắc, không chỉ lúc khôi phục.
    - Có listener nào vừa được KHÔI PHỤC (chứ không phải lần đăng ký đầu
      tiên) → coi như vừa trải qua 1 lần mất mạng → tự chạy catch-up sync
      (xem _run_catchup_sync) để bù dữ liệu Users/Lockers bị lỡ lúc offline."""
    if not FIREBASE_OK or db is None:
        return
    g = globals()
    recovered_from_outage = False
    registered_this_cycle = False
    for name, path, callback_name in _LISTENER_SPECS:
        if _listener_alive(name):
            continue
        callback = g[callback_name]
        was_registered_before = name in _listener_regs
        try:
            _listener_regs[name] = db.reference(path).listen(callback)
            verb = "🔁 Đã khôi phục" if was_registered_before else "📡 Đã đăng ký"
            print(f"[SyncListener] {verb} listener '{name}'")
            registered_this_cycle = True
            if was_registered_before:
                recovered_from_outage = True
        except Exception as e:
            _listener_regs[name] = None
            print(f"[SyncListener] ✗ Chưa kết nối được listener '{name}' ({e}) — thử lại sau")

    if registered_this_cycle:
        threading.Thread(target=_catchup_pending_credentials, daemon=True).start()
    if recovered_from_outage:
        _run_catchup_sync()


def _watchdog_loop():
    """Vòng lặp nền: định kỳ kiểm tra + tự đăng ký lại listener bị chết do mất
    mạng. Đây là cơ chế thay thế cho việc phải tắt/mở lại app (chạy lại file)
    mỗi khi mạng chập chờn."""
    while not _stop_event.is_set():
        _register_missing_listeners()
        _stop_event.wait(20)


# NOTE: đã xoá _cleanup_loop() — trước đây gọi cleanup_idle_lockers() mỗi 1h
# song song với CleanupWorker (QThread) trong main.py, gây race condition
# (2 thread cùng đọc/ghi Lockers gần như đồng thời -> có thể gửi email thu
# hồi tủ 2 lần cho cùng 1 sinh viên). Giữ đúng 1 nơi cleanup duy nhất là
# CleanupWorker trong main.py.

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

    Việc đăng ký listener lúc khởi động và việc TỰ ĐĂNG KÝ LẠI khi mất mạng
    dùng chung 1 đường code (_register_missing_listeners / _watchdog_loop) —
    tránh trường hợp mất mạng giữa chừng làm listener chết mà không ai hồi
    phục lại (xem giải thích chi tiết ở phần "Reconnect watchdog" phía trên).
    """
    if not FIREBASE_OK or db is None:
        print("[SyncListener] ⚠ Firebase offline — chỉ chạy daemon threads")
    else:
        _register_missing_listeners()

    threading.Thread(target=_watchdog_loop, daemon=True).start()
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    print("[SyncListener] 🔄 Daemon threads: heartbeat + reconnect watchdog")


if __name__ == "__main__":
    start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Dừng lắng nghe.")