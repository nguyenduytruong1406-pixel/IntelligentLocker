import sqlite3
import firebase_admin
from firebase_admin import credentials, db
import time

# --- KHỞI TẠO FIREBASE (Chống lỗi gọi 2 lần) ---
if not firebase_admin._apps:
    cred = credentials.Certificate(r'D:/DATN/Software/test_db_ver1/private_key_lockers.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app'
    })

DB_PATH = r'D:/DATN/Software/test_db_ver1/IntelligentLocker.db'

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

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

    with get_conn() as conn:
        cur = conn.cursor()
        # Lấy thêm trường password hiện tại ở Local
        cur.execute("SELECT has_face, password FROM Users WHERE mssv=?", (mssv,))
        row = cur.fetchone()

        if row:
            merged_has_face = max(row[0] or 0, has_face_fb)
            current_password = row[1]
            
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

# ── 2. LẮNG NGHE THAY ĐỔI TỦ (TRẢ TỦ TỪ WEB) ──────────────────────────────────
def on_locker_change(event):
    if event.path == '/': return
    lid = event.path.strip('/').split('/')[0]

    locker_data = db.reference(f'lockers/{lid}').get()
    if not locker_data: return

    status = locker_data.get('status', 'empty').lower()
    
    if status == 'empty':
        with get_conn() as conn:
            conn.execute("UPDATE Lockers SET status='empty', current_mssv=NULL WHERE locker_id=?", (lid,))
        print(f"[Sync] 🔓 Trả tủ {lid} (Lệnh từ Web)")

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