import sys

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

    @classmethod
    def clear(cls):
        cls.current_user = None
        cls.user_name = None
        cls.user_email = None
        cls.current_mode = None
        cls.selected_locker = None
        cls.current_otp = None
        cls.otp_expire_time = None