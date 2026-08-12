from PyQt6.QtWidgets import QMainWindow
from app.paths import UI, GIF, QSS, find_video
from PyQt6 import uic

from app.utils.session import Session
from app.services.auth_service import AuthService
from app.services.locker_service import LockerService
from app.widgets.virtual_keyboard import VirtualKeyboard
from PyQt6.QtCore import QTimer, QEvent, Qt
from PyQt6.QtWidgets import QMainWindow, QMessageBox
from app.utils.card_builder import build_card_content



class SelectModeController(QMainWindow):

    def __init__(self, stacked_widget, loading_page, success_page):
        super().__init__()
        uic.loadUi(UI("SELECT_MODE.ui"), self)
        self.stacked_widget = stacked_widget
        self.loading_page   = loading_page
        self.success_page   = success_page
        self.locker_service = LockerService()
        self.auth_service   = AuthService()

        build_card_content(self.lay_do, "app/assets/icon/MO_TU.png", "MỞ TỦ", "Có thể lấy/để thêm đồ")
        build_card_content(self.tra_tu, "app/assets/icon/TRA_TU.png", "TRẢ TỦ", "Kết thúc thời hạn mượn tủ")
        self.lay_do.clicked.connect(self.MO_TU)
        self.tra_tu.clicked.connect(self.TRA_TU)


        # ── Trạng thái chờ xác nhận "cửa đã thực sự mở" từ ESP32 ────────────
        # (dùng cho luồng MO_TU — xem _wait_for_locker_opened / _on_locker_opened)
        self._expected_locker_number = None
        self._open_timeout_timer = None
    # ── ESC → về màn hình chính (thay cho nút Home hiển thị — kiosk công khai
    #    không nên có nút thoát rõ ràng, ESC chỉ dành cho người biết bấm) ──────

        # Connect signal locker_closed từ ESP32     
        self.locker_service.esp32.locker_closed.connect(
            self.locker_service.on_door_closed
        )

        
        # 1. Gom danh sách các nút bằng tên biến logic riêng biệt (Không lo bị trùng)
        system_buttons = [self.lay_do, self.tra_tu]
        for btn in system_buttons:
            # Bật tính năng lưu trạng thái cảm ứng
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            
            # 👉 MẸO QUAN TRỌNG: Gán class "systemButton" để nút tự động ăn theo file QSS
            btn.setProperty("class", "systemButton")
            
            # Ép Qt vẽ lại giao diện để nhận thuộc tính class vừa gán
            # btn.style().unpolish(btn)
            # btn.style().polish(btn)
            
            # 2. Cài đặt QTimer giữ màu 120ms chống trơ trên màn Waveshare
            def create_release_handler(b=btn):
                def safe_clear():
                    try:
                        # Nếu nút bấm vẫn còn sống và chưa bị xóa
                        if b and not b.isHidden(): 
                            b.setChecked(False)
                    except RuntimeError:
                        # Nếu nút đã bị xóa bởi build_keyboard(), bỏ qua lỗi này an toàn
                        pass

                # Giữ màu trong 120ms rồi chạy hàm kiểm tra an toàn ở trên
                QTimer.singleShot(150, safe_clear)

            btn.released.connect(create_release_handler)




    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.go_to_begin()
        else:
            super().keyPressEvent(event)

    # ── Mỗi lần màn hình được hiển thị → check trạng thái tủ ────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._update_buttons()

    def _update_buttons(self):
        """
        Chưa có tủ → TẠM THỜI ở lại màn này, ẩn 2 nút Mở/Trả tủ, báo rõ tình
        trạng thay vì điều hướng sai.

        ⚠️ Trước đây gọi go_to_select_locker() → setCurrentIndex(4) để sang
        màn "chọn tủ trống". Nhưng sau khi select_mode được thêm vào PAGES
        (15/07/2026), thứ tự index trong QStackedWidget đã đổi — index 4 giờ
        trỏ NHẦM sang VideoScreenController (màn phát video giới thiệu lặp
        vòng), khiến sinh viên chưa có tủ bị "đá" ra một màn trông như màn
        hình chính ngay sau khi xác thực khuôn mặt thành công. Khôi phục lại
        điều hướng thật (go_to_select_locker) khi có lại mã nguồn
        select_locker_controller.py và đăng ký đúng vào PAGES.

        Đã có tủ → hiện menu Mở/Trả bình thường.
        """
        user       = Session.current_user
        has_locker = bool(self.locker_service.check_user_has_locker(user))

        if not has_locker:
            self.lay_do.setVisible(False)
            self.tra_tu.setVisible(False)
            self.thong_bao_tu.setStyleSheet("color: orange;")
            self.thong_bao_tu.setText("Bạn chưa được gán tủ. Vui lòng liên hệ admin để được cấp tủ.")
        else:
            self.lay_do.setVisible(True)
            self.tra_tu.setVisible(True)
            self.thong_bao_tu.setStyleSheet("")
            self.thong_bao_tu.setText("")

    # ── Mở tủ (user đã có tủ) ────────────────────────────────────────────────

    def MO_TU(self):
        user    = Session.current_user
        name    = self.auth_service.get_name_user(user)
        success, message, locker_number = self.locker_service.open_locker(user, name)

        if not success:
            self.thong_bao_tu.setStyleSheet("color: red;")
            self.thong_bao_tu.setText(message)
            return

        # Lệnh OPEN đã gửi xuống ESP32 thành công — nhưng chưa chắc cửa đã mở
        # thật. Hiện màn hình chờ, và chỉ báo "thành công" khi ESP32 xác nhận
        # ngược lại bằng "OPENED:xx" (xem ESP32LockerClient.locker_opened).
        self.loading_page.set_message("Đang tiến hành mở tủ...")
        self.stacked_widget.setCurrentWidget(self.loading_page)
        self._wait_for_locker_opened(locker_number)

    # ── Chờ ESP32 xác nhận cửa đã mở thật (dựa vào cảm biến hành trình) ─────

    def _wait_for_locker_opened(self, expected_locker_number: int):
        self._expected_locker_number = expected_locker_number

        # Tránh nối trùng signal nếu người dùng bấm "Mở tủ" nhiều lần liên tiếp
        try:
            self.locker_service.esp32.locker_opened.disconnect(self._on_locker_opened)
        except TypeError:
            pass  # chưa từng connect lần nào -> bỏ qua
        self.locker_service.esp32.locker_opened.connect(self._on_locker_opened)

        # An toàn: nếu sau 5s không thấy ESP32 xác nhận (cảm biến lỗi, dây đứt,
        # cửa đã hở sẵn từ trước nên ESP32 không thấy "sườn lên"...) vẫn coi
        # như thành công để giao diện không bị kẹt mãi ở màn hình chờ.
        self._open_timeout_timer = QTimer(self)
        self._open_timeout_timer.setSingleShot(True)
        self._open_timeout_timer.timeout.connect(
            lambda: self._on_locker_opened(expected_locker_number, confirmed=False)
        )
        self._open_timeout_timer.start(5000)

    def _on_locker_opened(self, locker_number: int, confirmed: bool = True):
        # Không phải tủ mình đang chờ (vd tủ khác vừa mở/đóng) -> bỏ qua
        if locker_number != self._expected_locker_number:
            return

        self._open_timeout_timer.stop()
        try:
            self.locker_service.esp32.locker_opened.disconnect(self._on_locker_opened)
        except TypeError:
            pass
        self._expected_locker_number = None

        if not confirmed:
            print(f"[SelectMode] Không nhận được OPENED:{locker_number:02d} sau 5s "
                  f"— kiểm tra lại cảm biến hành trình của tủ này.")

        self._show_success_with_ok("Mở tủ thành công", self.go_to_begin)

    # ── Trả tủ ───────────────────────────────────────────────────────────────

    def TRA_TU(self):
        # ===== CẢNH BÁO TRƯỚC KHI TRẢ TỦ =====
        msg = QMessageBox(self)
        msg.setWindowTitle("Xác nhận trả tủ")
        msg.setText("Bạn có chắc chắn muốn trả tủ không?")
        msg.setInformativeText(
            "⚠️ Lưu ý:\n"
            "- Hãy chắc chắn đã lấy hết đồ ra khỏi tủ\n"
            "- Tủ sẽ được mở khóa sau khi xác nhận\n"
            "- Hành động này không thể hoàn tác!"
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Ok |
            QMessageBox.StandardButton.Cancel
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)


        reply = msg.exec()

        # ===== NẾU NGƯỜI DÙNG NHẤN OK =====
        if reply == QMessageBox.StandardButton.Ok:
            user = Session.current_user
            name = self.auth_service.get_name_user(user)
            success, message = self.locker_service.return_locker(user, name)

            if not success:
                self.thong_bao_tu.setStyleSheet("color: red;")
                self.thong_bao_tu.setText(message)
            else:
                self.loading_page.set_message("Đang tiến hành trả tủ...")
                self.stacked_widget.setCurrentWidget(self.loading_page)
                QTimer.singleShot(2000, lambda: self.show_success(
                    "Trả tủ thành công", self.go_to_begin
                ))
        # ===== NẾU NGƯỜI DÙNG NHẤN CANCEL =====
        # → Không làm gì, giữ nguyên màn hình

    # ── Helpers ───────────────────────────────────────────────────────────────

    def show_success(self, message, next_function, delay=2000):
        self.success_page.set_message(message)
        self.stacked_widget.setCurrentWidget(self.success_page)
        QTimer.singleShot(delay, next_function)
        
    def _show_success_with_ok(self, message, next_function):
        """
        Giống show_success() nhưng KHÔNG tự động chuyển trang sau vài giây —
        chỉ chuyển khi người dùng bấm nút OK. Dùng cho luồng cần xác nhận chắc
        chắn đã hoàn tất (vd MO_TU: chờ ESP32 báo cửa đã mở thật).
        """
        self.success_page.set_message(message)
        self.success_page.set_ok_visible(True)
        self.stacked_widget.setCurrentWidget(self.success_page)

        try:
            self.success_page.ok_button.clicked.disconnect()
        except TypeError:
            pass  # chưa từng connect lần nào -> bỏ qua
        self.success_page.ok_button.clicked.connect(
            lambda: self._on_success_ok(next_function)
        )

    def _on_success_ok(self, next_function):
        self.success_page.set_ok_visible(False)  # trả lại ẩn cho các luồng dùng show_success()
        next_function()

    def go_to_begin_TRATU(self):
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def go_to_begin(self):
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def go_to_select_locker(self):
        self.stacked_widget.setCurrentIndex(4)
        self.reset_form()

    def reset_form(self):
        self.thong_bao_tu.setText("")
