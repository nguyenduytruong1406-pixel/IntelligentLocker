import sys
import time

class Session:

    current_user = None

    user_name = None
    user_email = None

    current_mode = None

    selected_locker = None


    current_otp = None
    otp_expire_time = None
    
    ktv_pin = None          # PIN của KTV đã xác thực
    ktv_name = None         # Tên KTV (ví dụ: "Kỹ Thuật Viên")
    ktv_id = None           # ID KTV (ví dụ: "KTV001")

    # mssv -> timestamp (time.time()) hết khóa xác thực khuôn mặt.
    # Đặt ở cấp Session (không phải biến local trong FaceWorker) để khóa
    # KHÔNG bị mất khi người dùng bấm "Quay lại" rồi vào lại trang camera
    # (worker cũ bị hủy, nếu lưu local thì fail_count/lockout mất theo).
    face_lockout = {}

    @classmethod
    def get_face_lockout_remaining(cls, mssv: str) -> float:
        """Số giây còn lại bị khóa xác thực khuôn mặt của 1 mssv (0 nếu không khóa)."""
        key   = mssv or "__anonymous__"
        until = cls.face_lockout.get(key)
        if not until:
            return 0.0
        remaining = until - time.time()
        if remaining <= 0:
            cls.face_lockout.pop(key, None)
            return 0.0
        return remaining

    @classmethod
    def set_face_lockout(cls, mssv: str, seconds: float):
        key = mssv or "__anonymous__"
        cls.face_lockout[key] = time.time() + seconds

    @classmethod
    def clear(cls):
        cls.current_user = None
        cls.user_name = None
        cls.user_email = None
        cls.current_mode = None
        cls.selected_locker = None
        cls.current_otp = None
        cls.otp_expire_time = None
        # KHÔNG xóa face_lockout ở đây — khóa phải sống sót qua việc
        # logout/clear session, nếu không sinh viên có thể né khóa bằng
        # cách thoát ra rồi đăng nhập lại ngay.