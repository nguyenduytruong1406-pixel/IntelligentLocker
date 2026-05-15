import sqlite3
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import time

# ─────────────────────────────────────────────────────────────────────────────
# Kết nối
# ─────────────────────────────────────────────────────────────────────────────
conn = None
try:
    # 1. Khởi tạo Firebase
    cred = credentials.Certificate(r'D:/DATN/Software/test_db_ver1/private_key_lockers.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://lockerxmakerspacexhcmute-default-rtdb.asia-southeast1.firebasedatabase.app'
    })
    print('[Cloud] Connected successfully!')

    # 2. Kết nối SQLite
    conn = sqlite3.connect(
        'D:/DATN/Software/test_db_ver1/IntelligentLocker.db',
        check_same_thread=False
    )
    cursor = conn.cursor()
    print("[Local] Database ready!")

# ─────────────────────────────────────────────────────────────────────────────
# Handler: Firebase → SQLite
# Lắng nghe node /users, đồng bộ xuống bảng Users (không đụng face_embedding)
# ─────────────────────────────────────────────────────────────────────────────

    def on_firebase_change(event):
        print(f"\n[Alert] Firebase thay đổi tại: {event.path}")

        # Bỏ qua sự kiện khởi tạo ban đầu (path="/")
        if event.path == '/':
            return

        try:
            # Lấy mssv từ path "/22146436/..." → "22146436"
            mssv = event.path.strip('/').split('/')[0]

            # Kéo toàn bộ dữ liệu user từ Firebase
            user_data = db.reference(f'users/{mssv}').get()
            print(f"[Debug] Firebase data: {user_data}")

            if user_data is None:
                print(f"[Sync] User {mssv} đã bị xóa khỏi Firebase, bỏ qua.")
                return

            name        = user_data.get('name', 'Unknown')
            is_approved = user_data.get('is_approved', 0)
            # has_face chỉ đọc từ Firebase, KHÔNG ghi đè nếu đã có embedding local
            has_face_fb = 1 if user_data.get('has_face') else 0

            # Kiểm tra user đã tồn tại trong SQLite chưa
            cursor.execute("SELECT mssv, has_face FROM Users WHERE mssv=?", (mssv,))
            row = cursor.fetchone()

            if row:
                # Đã tồn tại → cập nhật name, is_approved
                # has_face: lấy giá trị lớn hơn (local embedding > Firebase flag)
                # để tránh ghi đè mất trạng thái đã đăng ký khuôn mặt
                current_has_face = row[1] if row[1] is not None else 0
                merged_has_face  = max(current_has_face, has_face_fb)

                cursor.execute(
                    "UPDATE Users SET name=?, is_approved=?, has_face=? WHERE mssv=?",
                    (name, is_approved, merged_has_face, mssv)
                )
                action = "Cập nhật"
            else:
                # User mới hoàn toàn → thêm mới (face_embedding để NULL)
                cursor.execute(
                    "INSERT INTO Users (mssv, name, is_approved, has_face) "
                    "VALUES (?, ?, ?, ?)",
                    (mssv, name, is_approved, has_face_fb)
                )
                action = "Thêm mới"

            conn.commit()

            status_text = "Approved" if str(is_approved) == '1' else "Pending/Locked"
            face_text   = "Có khuôn mặt" if has_face_fb else "Chưa đăng ký"
            print(f"[Sync] {action} | {name} ({mssv}) | {status_text} | {face_text}")

        except Exception as e:
            print(f"[Error] Không xử lý được dữ liệu: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Bắt đầu lắng nghe
# ─────────────────────────────────────────────────────────────────────────────

    users_ref = db.reference('users')
    print("\n[System] Đang lắng nghe thay đổi từ Cloud... Nhấn Ctrl+C để dừng.")

    listener = users_ref.listen(on_firebase_change)

    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\n[System] Người dùng dừng chương trình.")

except Exception as e:
    print(f"[Error] Hệ thống gặp lỗi: {e}")

finally:
    if conn:
        conn.close()
        print("[Local] Đã đóng kết nối SQLite an toàn.")