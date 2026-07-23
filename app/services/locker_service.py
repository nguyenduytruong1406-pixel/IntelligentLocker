import re

from app.database.locker_repository import LockerRepository
from app.database.user_repository import UserRepository
from app.services.firebase_hooks import push_borrow, push_open, push_return
from app.devices.esp32_locker import ESP32LockerClient

class LockerService:

    def __init__(self):
        self.locker_repo = LockerRepository()
        self.user_repo   = UserRepository()
        self.esp32       = ESP32LockerClient() 

    @staticmethod
    def _locker_number(locker_id: str):
        """Tách số tủ từ mã locker_id kiểu 'L07' -> 7. Trả None nếu không parse được."""
        match = re.search(r"(\d+)$", str(locker_id))
        return int(match.group(1)) if match else None

    # ── Truy vấn ──────────────────────────────────────────────────────────────

    def check_user_has_locker(self, mssv: str):
        return self.locker_repo.get_user_locker(mssv)

    def get_all_lockers(self):
        return self.locker_repo.get_all_lockers()

    def get_locker_status(self, locker_id: str):
        lockers = self.get_all_lockers()
        for id_, status, holder in lockers:
            if id_ == locker_id:
                return status
        return None

    # ── Gán tủ (BORROW) ───────────────────────────────────────────────────────

    def set_status_locker(self, mssv: str, locker_id: str, name: str):
        """Gán tủ cụ thể cho sinh viên (gọi từ SelectLockerController)."""
        print(f"[DEBUG] set_status_locker mssv={mssv} locker={locker_id} name={name}")
        ok = self.locker_repo.set_status_locker(mssv, locker_id, name)
        print(f"[DEBUG] repo.set_status_locker ok={ok}")
        if ok:
            print(f"[DEBUG] goi push_borrow...")
            push_borrow(mssv, locker_id, name)
            print(f"[DEBUG] push_borrow xong")
        else:
            print(f"[DEBUG] ok=False -> khong push!")
        return ok

    # ── Mở tủ (đã có tủ, muốn OPEN lại lấy đồ) ──────────────────────────────

    def open_locker(self, mssv: str, name: str):
        """
        Mở tủ đang giữ — gửi lệnh Serial mở khóa + ghi OPEN log + update last_open.
        Trả về (thành công, thông báo, số_tủ). số_tủ dùng để controller biết
        đang chờ xác nhận "OPENED:xx" của tủ nào từ ESP32 (None nếu thất bại
        trước khi xác định được số tủ).
        """
        locker_id = self.check_user_has_locker(mssv)
        if not locker_id:
            return False, "Bạn chưa sử dụng tủ nào!", None

        locker_number = self._locker_number(locker_id)
        if locker_number is None:
            return False, f"Mã tủ không hợp lệ: {locker_id}", None

        # Gửi lệnh "OPEN:<so tu>" xuống ESP32 qua Serial TRƯỚC khi ghi log —
        # nếu phần cứng không mở được thì không nên báo "thành công" cho user.
        # LƯU Ý: đây chỉ là gửi lệnh thành công, KHÔNG đảm bảo cửa đã thực sự
        # mở — việc đó do controller lắng nghe signal `locker_opened` xác nhận.
        ok_serial, err = self.esp32.send_open(locker_number)
        if not ok_serial:
            print(f"[LockerService] Gửi lệnh mở tủ thất bại: {err}")
            return False, "Không thể kết nối tới khóa tủ, vui lòng thử lại hoặc báo nhân viên!", None

        self.user_repo.update_account_status(mssv)
        self.locker_repo.insert_access_log(locker_id, mssv, "OPEN", name)
        push_open(mssv, locker_id, name)
        return True, f"Mở tủ {locker_id} thành công!", locker_number

    # ── Trả tủ ────────────────────────────────────────────────────────────────

    def return_locker(self, mssv: str, name: str):
        """Sinh viên trả tủ — reset Lockers + ghi log + push Firebase."""
        locker_id = self.check_user_has_locker(mssv)
        if not locker_id:
            return False, "Không tìm thấy tủ!"

        self.user_repo.update_account_status(mssv)
        ok = self.locker_repo.return_locker(mssv, locker_id, name)
        if ok:
            push_return(mssv, locker_id, name, reason="student_release")
        return (True, f"Trả tủ {locker_id} thành công!") if ok else (False, "Lỗi khi trả tủ")

    # ── Service Engineer ───────────────────────────────────────────────────────

    def insert_service_log(self, locker_id: str, ktv_id: str,
                           ktv_name: str, action: str, notes: str = ""):
        return self.locker_repo.insert_service_log(
            locker_id, ktv_id, ktv_name, action, notes
        )

    def update_locker_maintenance(self, locker_id: str, status: str):
        """Cập nhật trạng thái bảo trì + push Firebase."""
        ok = self.locker_repo.update_locker_maintenance(locker_id, status)
        if ok:
            try:
                from app.firebase_config import FIREBASE_OK
                if FIREBASE_OK:
                    from firebase_admin import db as fdb
                    fdb.reference(f"lockers/{locker_id}").update({"status": status})
            except Exception as e:
                print(f"[Firebase] ✗ update_locker_maintenance {locker_id}: {e}")
        return ok

    # ── Kiểm tra tủ trống (dùng cho GUI_DO trước khi chọn tủ) ────────────────

    def borrow_locker(self, mssv: str):
        """Kiểm tra user hợp lệ và có tủ trống để mượn."""
        # Kiểm tra user đã có tủ chưa
        existing = self.check_user_has_locker(mssv)
        if existing:
            return False, f"Bạn đang giữ tủ {existing}, vui lòng trả trước!"

        # Kiểm tra có tủ trống không
        all_lockers = self.locker_repo.get_all_lockers()
        empty = [l for l in all_lockers if l["status"] == "empty"]
        if not empty:
            return False, "Hiện không có tủ trống!"

        return True, "OK"