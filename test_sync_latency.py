# test_exp3_interleaved.py — Thí nghiệm 3 (bản đan xen OPEN/RETURN)
#
# Ý tưởng: chia 9 tủ thành 2 nhóm — 1 nhóm chỉ OPEN, 1 nhóm chỉ RETURN.
# Mỗi tủ chỉ nhận ĐÚNG 1 loại hành động -> khi sync_tool.py push trạng thái
# cuối cùng của từng tủ lên Firebase, trạng thái đó khớp chính xác với hành
# động đã ghi ở SQLite -> không bị hiện tượng "OPEN bị RETURN ghi đè" như khi
# test cả 2 hành động trên cùng 1 tủ. Nhờ vậy chỉ cần 1 lượt offline -> sync,
# không cần tách 2 lượt riêng.
#
# Thứ tự chạy CỐ Ý xen kẽ OPEN/RETURN theo thời gian (không chạy hết OPEN rồi
# mới RETURN) để mô phỏng sát hành vi thực tế: nhiều sinh viên dùng kiosk xen
# kẽ nhau trong lúc mất mạng.
#
# QUAN TRỌNG: chạy khi mạng ĐANG TẮT.
# Sau khi chạy xong:
#   1. Bật mạng lại
#   2. Chạy: python sync_tool.py --sync
#   3. Đối chiếu 9 dòng A_sqlite_write (5 OPEN + 4 RETURN) với B_firebase_push
#      trong experiment_log.csv theo đúng locker_id + action.

import time
from app.database.locker_repository import LockerRepository
from exp_log import log_experiment

repo = LockerRepository()
TEST_MSSV = "TEST001"  # mssv giả, không cần tồn tại thật trong Users

# (locker_id, action) — thứ tự đã xen kẽ OPEN/RETURN
PLAN = [
    ("L01", "OPEN"),
    ("L02", "RETURN"),
    ("L03", "OPEN"),
    ("L04", "RETURN"),
    ("L05", "OPEN"),
    ("L06", "RETURN"),
    ("L07", "OPEN"),
    ("L08", "RETURN"),
    ("L09", "OPEN"),
]

N = len(PLAN)
success_count = 0

for i, (locker_id, action) in enumerate(PLAN):
    if action == "OPEN":
        # Setup: gán tủ trước (không tính vào N, không log) để OPEN có
        # current_mssv hợp lý, giống thực tế OPEN luôn sau khi đã có tủ.
        repo.set_status_locker(TEST_MSSV, locker_id, "Test User")
        # insert_access_log() tự ghi A_sqlite_write bên trong -> không gọi thêm
        repo.insert_access_log(locker_id, TEST_MSSV, "OPEN", "Test User")
        success_count += 1
        print(f"[OFFLINE] {i+1}/{N} — tủ {locker_id} OPEN đã ghi SQLite")
    else:  # RETURN
        # Setup: gán tủ trước để có gì mà trả (không tính vào N, không log)
        repo.set_status_locker(TEST_MSSV, locker_id, "Test User")
        # return_locker() CHƯA tự ghi A_sqlite_write -> gọi thủ công
        ok = repo.return_locker(TEST_MSSV, locker_id, "Test User", reason="student_release")
        if ok:
            log_experiment("A_sqlite_write", locker_id, "RETURN")
            success_count += 1
            print(f"[OFFLINE] {i+1}/{N} — tủ {locker_id} RETURN đã ghi SQLite")
        else:
            print(f"[OFFLINE] ⚠ {i+1}/{N} — tủ {locker_id} RETURN thất bại — không ghi log A")

    time.sleep(2)  # nghỉ giữa các lần để log không chồng nhau khi đọc CSV

print(f"\nXong {success_count}/{N} thao tác offline (đan xen OPEN/RETURN).")
print("Giờ hãy BẬT MẠNG rồi chạy: python sync_tool.py --sync")