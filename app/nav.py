"""
app/nav.py — Bảng tra index trang dùng chung cho toàn bộ app.

main.py sẽ điền PAGES khi khởi động (add_page("ten_trang", widget)).
Mọi controller chỉ cần:

    from app.nav import PAGES
    self.stacked_widget.setCurrentIndex(PAGES["login"])

KHÔNG bao giờ dùng số index cứng (setCurrentIndex(3)) nữa — khi thêm/bớt
trang trong main.py, mọi nơi dùng PAGES["ten_trang"] sẽ tự động đúng,
không cần sửa lại từng file controller.
"""

PAGES: dict[str, int] = {}
