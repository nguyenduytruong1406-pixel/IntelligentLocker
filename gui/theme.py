"""
gui/theme.py — Màu sắc, font, và hằng số giao diện cho Smart Locker Kiosk.

Tất cả widget chỉ import từ đây; không hardcode màu/font ở nơi khác.
"""

from tkinter import font as tkfont

# ─────────────────────────────────────────────────────────────────────────────
#  BẢNG MÀU  (Dark-navy theme)
# ─────────────────────────────────────────────────────────────────────────────
C: dict[str, str] = {
    # Nền
    "bg":       "#0f1117",   # nền chính — sáng hơn slate-900
    "surface":  "#1a1d27",   # header / footer
    "card":     "#1a1d27",   # card / input field
    "border":   "#2e3150",   # viền nhạt

    # Chữ
    "text":     "#e2e8f0",   # chữ chính
    "muted":    "#64748b",   # chữ phụ / placeholder

    # Nhấn mạnh
    "accent":   "#4f6ef7",   # xanh dương sáng — nút Đăng nhập
    "accent2":  "#06b6d4",   # cyan — nút Đăng ký
    "green":    "#22c55e",   # xanh lá sáng — khuôn mặt / tủ trống
    "yellow":   "#fbbf24",   # vàng sáng — mật khẩu
    "red":      "#ef4444",   # đỏ — lỗi / thất bại
}

# ─────────────────────────────────────────────────────────────────────────────
#  KÍCH THƯỚC MÀN HÌNH & CAMERA
# ─────────────────────────────────────────────────────────────────────────────
SCREEN_W: int = 1024
SCREEN_H: int = 600
CAM_W:    int = 560   # ~55% chiều rộng màn hình
CAM_H:    int = 460   # 600 - header(70) - footer(36) - margin

# ─────────────────────────────────────────────────────────────────────────────
#  HẰNG SỐ RUNTIME
# ─────────────────────────────────────────────────────────────────────────────
VERIFY_FRAMES: int   = 5      # số frame liên tiếp khớp để xác thực thành công
ENROLL_FRAMES: int   = 20     # số frame cần thu thập khi đăng ký khuôn mặt
THRESHOLD:     float = 0.45   # ngưỡng khoảng cách embedding (càng nhỏ càng nghiêm)
IDLE_TIMEOUT:  int   = 60     # giây không tương tác → tự về màn hình chờ


# ─────────────────────────────────────────────────────────────────────────────
#  FONT FACTORY  (phải gọi sau khi Tk() đã khởi tạo)
# ─────────────────────────────────────────────────────────────────────────────
def make_fonts():
    return {
        "title": tkfont.Font(family="Segoe UI", size=22, weight="bold"),  # 26→22
        "head":  tkfont.Font(family="Segoe UI", size=14, weight="bold"),  # 16→14
        "body":  tkfont.Font(family="Segoe UI", size=12),                 # 13→12
        "small": tkfont.Font(family="Segoe UI", size=9),                  # 10→9
    }