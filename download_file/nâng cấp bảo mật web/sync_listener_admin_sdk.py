#!/usr/bin/env python3
"""
sync_listener.py - Firebase Realtime Database Sync (Admin SDK)

Thay thế pyrebase bằng firebase-admin để tương thích với Security Rules mới.
"""

import firebase_admin
from firebase_admin import credentials, db
import sqlite3
import time

# ────────────────────────────────────────────────────────────────────────────────
# 1. KHỞI TẠO FIREBASE ADMIN SDK
# ────────────────────────────────────────────────────────────────────────────────

# Đường dẫn đến file Service Account Key (download từ Firebase Console)
SERVICE_ACCOUNT_KEY = "serviceAccountKey.json"
DATABASE_URL = "https://lockerxmakerspacexhcmute-default-rtdb.firebaseio.com"

cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
firebase_admin.initialize_app(cred, {
    'databaseURL': DATABASE_URL
})

print("✓ Firebase Admin SDK initialized")

# ────────────────────────────────────────────────────────────────────────────────
# 2. KẾT NỐI SQLITE
# ────────────────────────────────────────────────────────────────────────────────

DB_PATH = "IntelligentLocker.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# ────────────────────────────────────────────────────────────────────────────────
# 3. SYNC SQLite → Firebase (1 chiều)
# ────────────────────────────────────────────────────────────────────────────────

def sync_users_to_firebase():
    """Đẩy toàn bộ Users từ SQLite lên Firebase"""
    cursor.execute("SELECT mssv, name, is_approved, rfid, role FROM Users")
    rows = cursor.fetchall()
    
    users_ref = db.reference('users')
    
    for mssv, name, is_approved, rfid, role in rows:
        # Kiểm tra có face_embedding hay không
        cursor.execute("SELECT face_embedding FROM Users WHERE mssv = ?", (mssv,))
        embedding = cursor.fetchone()[0]
        has_face = embedding is not None and len(embedding) > 0
        
        users_ref.child(mssv).set({
            'name': name,
            'mssv': mssv,
            'is_approved': is_approved,
            'has_face': has_face,
            'rfid': rfid or '',
            'role': role or 'student'
        })
    
    print(f"✓ Synced {len(rows)} users to Firebase")


def sync_lockers_to_firebase():
    """Đẩy Lockers từ SQLite lên Firebase"""
    cursor.execute("SELECT locker_id, status, size, current_mssv FROM Lockers")
    rows = cursor.fetchall()
    
    lockers_ref = db.reference('lockers')
    
    for locker_id, status, size, current_mssv in rows:
        key = f"L{str(locker_id).zfill(2)}"
        lockers_ref.child(key).set({
            'status': status.lower(),  # 'Empty' → 'empty'
            'size': size or '',
            'current_mssv': current_mssv or 'Trống'
        })
    
    print(f"✓ Synced {len(rows)} lockers to Firebase")


def push_log_to_firebase(event, mssv, name, locker_id=None):
    """Ghi 1 log event lên Firebase (append-only)"""
    logs_ref = db.reference('logs')
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    logs_ref.push({
        'time': timestamp,
        'event': event,  # OPEN_LOCKER, ASSIGN_LOCKER, RELEASE_LOCKER, FACE_REGISTER
        'mssv': mssv,
        'name': name,
        'locker_id': locker_id or '—'
    })
    
    print(f"✓ Pushed log: {event} | {mssv} | {locker_id}")


# ────────────────────────────────────────────────────────────────────────────────
# 4. MAIN LOOP (Tùy chọn: polling hoặc trigger-based)
# ────────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Sync toàn bộ dữ liệu 1 lần khi khởi động
    print("\n=== Initial Sync ===")
    sync_users_to_firebase()
    sync_lockers_to_firebase()
    
    # Ví dụ: Push log test
    push_log_to_firebase(
        event='FACE_REGISTER',
        mssv='22146436',
        name='Nguyễn Văn A'
    )
    
    print("\n✓ Sync complete. Exiting.")
    
    # Nếu muốn chạy realtime listener (Firebase → SQLite):
    # def on_user_change(event):
    #     print(f"User changed: {event.data}")
    # 
    # db.reference('users').listen(on_user_change)
    # 
    # print("Listening for changes...")
    # while True:
    #     time.sleep(1)
