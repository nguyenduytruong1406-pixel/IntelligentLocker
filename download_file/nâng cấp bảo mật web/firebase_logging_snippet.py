"""
Snippet thêm vào locker_db.py để tự động ghi log lên Firebase
Paste đoạn này vào đầu file và gọi firebase_log() trong các hàm open_locker, assign_locker, etc.
"""

import firebase_admin
from firebase_admin import credentials, db as firebase_db
import time

# ────────────────────────────────────────────────────────────────────────────────
# KHỞI TẠO FIREBASE (chỉ chạy 1 lần)
# ────────────────────────────────────────────────────────────────────────────────

try:
    # Kiểm tra đã init chưa
    firebase_admin.get_app()
except ValueError:
    # Chưa init → init ngay
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://lockerxmakerspacexhcmute-default-rtdb.firebaseio.com'
    })
    print("✓ Firebase Admin SDK initialized in locker_db.py")


# ────────────────────────────────────────────────────────────────────────────────
# HÀM GHI LOG LÊN FIREBASE
# ────────────────────────────────────────────────────────────────────────────────

def firebase_log(event: str, mssv: str, name: str, locker_id: int = None, **kwargs):
    """
    Ghi log lên Firebase Realtime Database
    
    Args:
        event: 'OPEN_LOCKER' | 'ASSIGN_LOCKER' | 'RELEASE_LOCKER' | 'FACE_REGISTER'
        mssv: MSSV sinh viên
        name: Tên sinh viên
        locker_id: ID tủ (1-9)
        **kwargs: thêm field tùy ý (vd: face_dist=0.32)
    """
    try:
        logs_ref = firebase_db.reference('logs')
        
        log_data = {
            'time': time.strftime("%Y-%m-%d %H:%M:%S"),
            'event': event,
            'mssv': mssv,
            'name': name,
            'locker_id': f"L{str(locker_id).zfill(2)}" if locker_id else '—',
            **kwargs  # face_dist, live_result, notes, etc.
        }
        
        logs_ref.push(log_data)
        print(f"[Firebase] Logged: {event} | {mssv}")
    except Exception as e:
        print(f"[Firebase Error] {e}")


# ────────────────────────────────────────────────────────────────────────────────
# CÁCH DÙNG TRONG CÁC HÀM HIỆN CÓ
# ────────────────────────────────────────────────────────────────────────────────

"""
Ví dụ trong hàm open_locker():

def open_locker(locker_id: int, mssv: str):
    # ... code hiện tại ...
    
    # Log vào SQLite
    log_access(mssv, 'OPEN_LOCKER', locker_id=locker_id)
    
    # Log lên Firebase (THÊM DÒNG NÀY)
    name = get_user_name(mssv)  # Giả sử có hàm này
    firebase_log('OPEN_LOCKER', mssv, name, locker_id)
    
    # ... tiếp tục ...


Ví dụ trong hàm assign_locker():

def assign_locker(mssv: str, locker_id: int):
    # ... code hiện tại ...
    
    # THÊM log Firebase
    name = get_user_name(mssv)
    firebase_log('ASSIGN_LOCKER', mssv, name, locker_id)


Ví dụ khi đăng ký khuôn mặt (trong enroll.py hoặc main_gui.py):

# Sau khi lưu embedding thành công
firebase_log('FACE_REGISTER', mssv, name)
"""


# ────────────────────────────────────────────────────────────────────────────────
# HÀM HỖ TRỢ: Lấy tên từ MSSV
# ────────────────────────────────────────────────────────────────────────────────

def get_user_name(mssv: str) -> str:
    """Lấy tên sinh viên từ SQLite"""
    import sqlite3
    conn = sqlite3.connect("IntelligentLocker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM Users WHERE mssv = ?", (mssv,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Unknown"
