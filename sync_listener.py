import sqlite3
import firebase_admin
from firebase_admin import credentials, db
import time
import smtplib
import os
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
    
    # Xử lý: Admin xóa User trên Web
    if user_data is None:
        with get_conn() as conn:
            conn.execute("UPDATE Lockers SET status='empty', current_mssv=NULL WHERE current_mssv=?", (mssv,))
            conn.execute("DELETE FROM Users WHERE mssv=?", (mssv,))
        print(f"[Sync] 🗑 Đã xóa user {mssv} và thu hồi tủ (nếu có)")
        return

    name        = user_data.get('name', 'Unknown')
    is_approved = int(user_data.get('is_approved', 0))
    email       = user_data.get('email', '')
    password_fb = user_data.get('password')  # <-- Lấy password từ Web
    has_face_fb = 1 if user_data.get('has_face') else 0

    old_is_approved = 0  # Biến lưu trạng thái duyệt cũ để kiểm tra gửi mail

    with get_conn() as conn:
        cur = conn.cursor()
        # BỔ SUNG: Lấy thêm trường is_approved hiện tại ở Local
        cur.execute("SELECT has_face, password, is_approved FROM Users WHERE mssv=?", (mssv,))
        row = cur.fetchone()

        if row:
            merged_has_face = max(row[0] or 0, has_face_fb)
            current_password = row[1]
            old_is_approved = row[2] or 0
            
            # Ưu tiên password từ web nếu có, nếu không thì giữ password cũ ở máy Kiosk
            final_password = password_fb if password_fb else current_password

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

    # --- KIỂM TRA & GỬI MAIL DUYỆT THÀNH CÔNG ---
    # Chỉ gửi khi: Trạng thái mới là 1 (Đã duyệt) VÀ Trạng thái cũ là 0 (Chưa duyệt) VÀ user có email
    if is_approved == 1 and old_is_approved == 0 and email:
        send_approval_email(email, name, mssv)

# ── 2. LẮNG NGHE THAY ĐỔI TỦ (TRẢ TỦ TỪ WEB) ──────────────────────────────────
def on_locker_change(event):
    if event.path == '/': return
    lid = event.path.strip('/').split('/')[0]

    locker_data = db.reference(f'lockers/{lid}').get()
    if not locker_data: return

    status    = locker_data.get('status', 'empty').lower()
    last_open = locker_data.get('last_open') or ''

    with get_conn() as conn:
        # Trả tủ từ web — xử lý TRƯỚC, xóa luôn assigned_date & last_open
        if status == 'empty':
            conn.execute(
                """UPDATE Lockers
                   SET status='empty', current_mssv=NULL,
                       assigned_date=NULL, last_open=NULL
                   WHERE locker_id=?""",
                (lid,)
            )
            print(f"[Sync] 🔓 Trả tủ {lid} (Lệnh từ Web)")
            return  # Không sync last_open của tủ vừa được trả

        # Sync last_open — chỉ chạy khi tủ đang occupied
        if last_open:
            row = conn.execute(
                "SELECT last_open FROM Lockers WHERE locker_id=?", (lid,)
            ).fetchone()
            sq_last_open = (row[0] or '') if row else ''
            # Chỉ update nếu Firebase mới hơn (tránh ghi đè khi kiosk vừa ghi)
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

if __name__ == "__main__":
    start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Dừng lắng nghe.")