"""
kiosk_gui.py — Entry point cho màn hình tủ kiosk.

Chạy:
    python kiosk_gui.py
"""

import subprocess
import sys
import os
import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from tkinter import messagebox

import firebase_admin
from firebase_admin import db as fdb
from dotenv import load_dotenv

import sync_listener
from core.db import migrate
from core.locker_db import auto_cleanup_inactive
from gui.kiosk_app import KioskApp


# ── Cấu hình gửi mail — đọc từ .env ──────────────────────────────────────────
# Tạo file .env cùng thư mục với kiosk_gui.py, KHÔNG commit lên git
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path)

MAIL_SENDER      = os.getenv("MAIL_SENDER", "")
MAIL_PASSWORD    = os.getenv("MAIL_PASSWORD", "")
MAIL_SENDER_NAME = os.getenv("MAIL_SENDER_NAME", "Smart Locker — HCMUTE")

if not MAIL_SENDER or not MAIL_PASSWORD:
    print("[Mail] ⚠ Chưa cấu hình MAIL_SENDER / MAIL_PASSWORD trong file .env — tính năng gửi mail bị tắt.")

# Số ngày pending trước khi bị xóa (phải khớp với cfg_expire_days trong index.html, mặc định 7)
PENDING_EXPIRE_DAYS = 7
# Cảnh báo trước bao nhiêu ngày (gửi mail warning)
PENDING_WARN_DAYS   = 2


# ── Auto-cleanup: cảnh báo tủ không dùng ─────────────────────────────────────

_warn_queue: list[dict] = []   # thread-safe buffer; drain trên main thread

def _warn_callback(mssv: str, locker_id: str, name: str, last_open: str):
    """Gọi từ background thread → đẩy vào queue, KHÔNG gọi tkinter trực tiếp."""
    _warn_queue.append({
        "mssv": mssv, "locker_id": locker_id,
        "name": name, "last_open": last_open or "chưa dùng lần nào",
    })

def _drain_warn_queue(app: KioskApp):
    """Gọi từ main thread qua app.after() để hiện popup an toàn."""
    while _warn_queue:
        w = _warn_queue.pop(0)
        messagebox.showwarning(
            "Cảnh báo — Tủ không hoạt động",
            f"Tủ {w['locker_id']} của sinh viên {w['name']} ({w['mssv']})\n"
            f"chưa sử dụng kể từ: {w['last_open']}\n\n"
            "⚠  Tủ sẽ tự động thu hồi sau 7 ngày không sử dụng.",
        )
    app.after(5_000, _drain_warn_queue, app)   # kiểm tra lại sau 5 giây

def _cleanup_loop():
    """Background thread — chạy auto-cleanup mỗi 1 giờ."""
    while True:
        try:
            result = auto_cleanup_inactive(
                warn_callback=_warn_callback,
                delete_days=7,
                warn_days=6,
            )
            if result["deleted"]:
                print(f"[AutoCleanup] Đã thu hồi {len(result['deleted'])} tủ: "
                      f"{[d['locker_id'] for d in result['deleted']]}")
            if result["warned"]:
                print(f"[AutoCleanup] Đã cảnh báo {len(result['warned'])} tủ: "
                      f"{[w['locker_id'] for w in result['warned']]}")
        except Exception as e:
            print(f"[AutoCleanup] Lỗi: {e}")
        time.sleep(3_600)   # 1 giờ


# ── Pending expire: gửi mail + xóa tài khoản hết hạn ────────────────────────

def _send_mail(to_email: str, subject: str, html_body: str) -> bool:
    """Gửi mail qua Gmail SMTP. Trả về True nếu thành công."""
    if not MAIL_SENDER or not MAIL_PASSWORD:
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
        print(f"[Mail] Lỗi gửi tới {to_email}: {e}")
        return False


def _mail_warning(name: str, mssv: str, email: str, days_left: int, registered_at: str) -> None:
    """Mail cảnh báo sắp hết hạn — gửi khi còn PENDING_WARN_DAYS ngày."""
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
    print(f"[PendingExpire] {'✉ Mail cảnh báo gửi tới' if ok else '✗ Gửi mail thất bại —'} {name} ({mssv}) | còn {days_left} ngày")


def _mail_expired(name: str, mssv: str, email: str) -> None:
    """Mail thông báo tài khoản đã bị xóa."""
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
    print(f"[PendingExpire] {'✉ Mail xóa gửi tới' if ok else '✗ Gửi mail thất bại —'} {name} ({mssv})")


def _days_since(registered_at: str) -> int:
    """Tính số ngày kể từ registered_at (ISO string: '2025-05-20 14:30:00')."""
    try:
        dt = datetime.strptime(registered_at.strip(), "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - dt).days
    except Exception:
        return 0


def _check_pending_expire() -> None:
    """
    Quét Firebase /users, tìm tài khoản pending quá hạn:
      - Còn đúng PENDING_WARN_DAYS ngày → gửi mail warning (1 lần/ngày nhờ flag)
      - Hết hạn (>= PENDING_EXPIRE_DAYS ngày) → gửi mail expired + xóa Firebase
    """
    try:
        users: dict = fdb.reference("users").get() or {}
    except Exception as e:
        print(f"[PendingExpire] Lỗi đọc Firebase: {e}")
        return

    now_date = datetime.now().strftime("%Y-%m-%d")  # dùng làm flag gửi mail 1 lần/ngày

    for mssv, u in users.items():
        # Chỉ xử lý tài khoản chưa được duyệt
        approved = u.get("is_approved", 0)
        if str(approved) in ("1", "true", "True") or approved is True:
            continue

        registered_at = u.get("registered_at", "")
        if not registered_at:
            continue

        name  = u.get("name", mssv)
        email = u.get("email", "")
        days  = _days_since(registered_at)
        days_left = PENDING_EXPIRE_DAYS - days

        # ── Hết hạn → xóa ────────────────────────────────────────────────────
        if days >= PENDING_EXPIRE_DAYS:
            print(f"[PendingExpire] Xóa {name} ({mssv}) — chờ {days} ngày")
            try:
                # Ghi log vào locker_delete_logs trước khi xóa
                fdb.reference("locker_delete_logs").push({
                    "mssv"       : mssv,
                    "locker_id"  : "",
                    "delete_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "reason"     : "auto_expired_pending",
                    "name"       : name,
                })
                fdb.reference(f"users/{mssv}").delete()
            except Exception as e:
                print(f"[PendingExpire] Lỗi xóa Firebase {mssv}: {e}")
                continue

            if email:
                _mail_expired(name, mssv, email)

        # ── Sắp hết hạn → cảnh báo (chỉ gửi 1 lần/ngày) ─────────────────────
        elif days_left <= PENDING_WARN_DAYS and email:
            warn_flag_key = f"warn_{mssv}_{now_date}"
            # Dùng file flag đơn giản để tránh gửi lặp trong ngày
            flag_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f".warn_flags/{warn_flag_key}"
            )
            if not os.path.exists(flag_path):
                os.makedirs(os.path.dirname(flag_path), exist_ok=True)
                open(flag_path, "w").close()
                _mail_warning(name, mssv, email, days_left, registered_at)

                # Dọn flag cũ (> 3 ngày) để tránh thư mục phình to
                flag_dir = os.path.dirname(flag_path)
                for f in os.listdir(flag_dir):
                    fp = os.path.join(flag_dir, f)
                    if os.path.isfile(fp) and (time.time() - os.path.getmtime(fp)) > 3 * 86400:
                        os.remove(fp)


def _pending_expire_loop() -> None:
    """Background daemon — chạy check pending expire mỗi 6 giờ."""
    # Chờ 30 giây sau boot để Firebase init xong
    time.sleep(30)
    while True:
        try:
            _check_pending_expire()
        except Exception as e:
            print(f"[PendingExpire] Lỗi không xử lý được: {e}")
        time.sleep(6 * 3_600)   # 6 giờ


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[Boot] Đang đồng bộ dữ liệu...")
    subprocess.run(
        [sys.executable, "sync_tool.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    migrate()
    sync_listener.start()

    app = KioskApp()

    # Khởi động auto-cleanup ngay sau khi app tạo xong
    threading.Thread(target=_cleanup_loop,        daemon=True).start()
    threading.Thread(target=_pending_expire_loop, daemon=True).start()
    app.after(5_000, _drain_warn_queue, app)   # bắt đầu drain sau 5 giây

    app.mainloop()