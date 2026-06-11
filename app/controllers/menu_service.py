from PyQt6.QtWidgets import QMainWindow, QMessageBox
from app.paths import UI, GIF, QSS, find_video
from PyQt6 import uic

from app.utils.session import Session
from app.services.locker_service import LockerService
from app.services.auth_service import AuthService
from app.widgets.locker_button import LockerButton
from datetime import datetime
from PyQt6.QtCore import QTimer



class MenuServiceController(QMainWindow):

    def __init__(self, stacked_widget, loading_page, success_page):

        super().__init__()

        uic.loadUi(UI("MENU_SE.ui"), self)

        self.loading_page = loading_page
        self.success_page = success_page
        self.stacked_widget = stacked_widget
        self.locker_service = LockerService()
        self.auth_service = AuthService()

        Session.selected_locker = None
        self.locker_buttons = []
        self.load_style()
        self.setup_locker_buttons()

        # self.load_locker_status()

        self.back.clicked.connect(self.go_back)
        self.chon_tu.clicked.connect(self.confirm_action)
        self.lock.clicked.connect(self.maintenance_action)

    # ================= STYLE =================
    def load_style(self):
        with open(QSS("locker.qss"), "r") as file:
            self.setStyleSheet(file.read())
    # ================= SETUP BUTTONS =================
    def setup_locker_buttons(self):
    # Loop từ 1 tới 9
        for i in range(1, 10):
            
            # 1. Lấy nút cũ từ UI (old_btn = self.tu1, self.tu2, ...)
            old_btn = getattr(self, f"tu{i}")
            
            # 2. Tạo LockerButton mới
            new_btn = LockerButton(i)
            
            # 3. Copy properties từ nút cũ sang nút mới
            #    - setParent()
            #    - setGeometry()
            #    - setFont()
            new_btn.setParent(old_btn.parent())
            new_btn.setGeometry(old_btn.geometry())
            new_btn.setFont(old_btn.font())
            new_btn.show()
            
            # 4. Xóa nút cũ
            old_btn.deleteLater()
            
            # 5. Gắn nút mới vào self (self.tu1 = new_btn)
            setattr(self, f"tu{i}", new_btn)
            
            # 6. Thêm vào danh sách
            self.locker_buttons.append(new_btn)
            
            # 7. Kết nối signal click
            new_btn.clicked.connect(
                lambda _, btn=new_btn:
                self.highlight_locker(btn.locker_id, btn)
            )
    # ================= LOAD STATUS =================
    def load_locker_status(self):
        """
        Load trạng thái tủ từ database
        Hiển thị màu tương ứng: xanh (available) hoặc vàng (maintenance)
        """
        # Lấy danh sách tủ từ database
        lockers = self.locker_service.get_all_lockers()
        
        for button in self.locker_buttons:
            # Tìm trạng thái của tủ này
            for locker_id, status, holder in lockers:
                try:
                    ui_index = int(locker_id[1:])
                    if ui_index == button.locker_id.split('L')[1] or ui_index == int(button.locker_id[1:]):
                        
                        if status == "maintenance":
                            # Tủ đang bảo trì → màu vàng
                            button.set_my_locker()  # ✅ Dùng set_my_locker() để thành vàng
                        else:
                            # Tủ bình thường → màu xanh
                            button.set_available()
                        break
                except:
                    # Nếu lỗi, mặc định set available
                    button.set_available()
    # ================= EVENT =================
    def showEvent(self, event):
        """
        Gọi tự động khi trang được hiển thị
        """
        # Setup các tủ để test
        self.load_locker_status()
        
        # Gọi parent showEvent
        super().showEvent(event)


    def highlight_locker(self, locker_id, button_obj):
        """
        Xử lý khi user click chọn tủ
        """
        if not button_obj.isEnabled():
            return
        
        # Reset tất cả button
        self.load_locker_status()
        
        # Highlight tủ được chọn
        Session.selected_locker = locker_id
        
        # ========== THÊM: Check xem tủ maintenance không ==========
        current_status, _ = self.locker_service.get_locker_status(locker_id)
        
        if current_status == "maintenance":
            # Nếu là maintenance → set màu cam đậm
            button_obj.set_selected_maintenance()
        else:
            # Ngược lại → set màu xanh bình thường
            button_obj.set_selected()
        # =========================================================
        
        # Update thông báo
        self.thong_bao_tu.setText(f"Đã chọn tủ {locker_id}")
        self.thong_bao_tu.setStyleSheet("color: #00796B;")
    
    def confirm_action(self):
        """
        Khi user nhấn nút OPEN - mở tủ ngay
        """
        
        # 1. Validation: Có chọn tủ chưa?
        if not Session.selected_locker:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn tủ!")
            return
        
        # 2. ========== SỬAT CÁCH LẤY THÔNG TIN ==========
        # Dùng thông tin KTV từ Session (không phải user thường)
        locker_id = Session.selected_locker
        ktv_id = Session.ktv_id  # ✅ ID KTV (ví dụ: "KTV001")
        ktv_name = Session.ktv_name  # ✅ Tên KTV (ví dụ: "Kỹ Thuật Viên")
        
        try:
            # Gọi service để mở tủ
            #self.locker_service.set_status_locker(ktv_id, locker_id, ktv_name)
            
            # ========== THÊM: GHI LOG ==========
            self.locker_service.insert_service_log(
                locker_id=locker_id,
                ktv_id=ktv_id,
                ktv_name=ktv_name,
                action="OPEN_TEST"  # ✅ Ghi hành động
            )
            # ===================================
            
            # Show MessageBox thành công
            QMessageBox.information(
                self,
                "Thành công",
                f"Mở tủ {locker_id} thành công!"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Lỗi khi mở tủ: {str(e)}")
        
        finally:
            # Reset form
            self.reset_form()
            self.load_locker_status()
    
    def maintenance_action(self):
        """
        Khi user nhấn nút LOCK/UNLOCK - chuyển trạng thái bảo trì
        """
        
        # 1. Validation: Có chọn tủ chưa?
        if not Session.selected_locker:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn tủ!")
            return
        
        # 2. Lấy thông tin
        locker_id = Session.selected_locker
        ktv_id = Session.ktv_id
        ktv_name = Session.ktv_name
        
        # 3. Kiểm tra trạng thái hiện tại để quyết định action
        # TODO: Lấy trạng thái tủ từ database
        # Để check xem nó là available hay maintenance
        # Nếu available → lock (chuyển sang maintenance)
        # Nếu maintenance → unlock (chuyển sang available)
        
        current_status, _ = self.locker_service.get_locker_status(locker_id)
        
        try:
            if current_status == "empty" or current_status == "Busy":
                # Chuyển sang MAINTENANCE (LOCK)
                new_status = "maintenance"
                action = "LOCK"
                message = f"Tủ {locker_id} đã chuyển sang bảo trì!"
                
            elif current_status == "maintenance":
                # Chuyển sang AVAILABLE (UNLOCK)
                new_status = "empty"
                action = "UNLOCK"
                message = f"Tủ {locker_id} trở lại bình thường!"
                
            else:
                QMessageBox.warning(self, "Lỗi", f"Trạng thái tủ không xác định: {current_status}")
                return
            
            # 4. Cập nhật database
            self.locker_service.update_locker_maintenance(locker_id, new_status)
            
            # 5. Ghi log
            self.locker_service.insert_service_log(
                locker_id=locker_id,
                ktv_id=ktv_id,
                ktv_name=ktv_name,
                action=action
            )
            
            # 6. Show thông báo thành công
            QMessageBox.information(self, "Thành công", message)
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Lỗi: {str(e)}")
        
        finally:
            # 7. Reset và reload
            self.reset_form()
            self.load_locker_status()


    def go_to_begin(self):
        """Quay lại trang BEGIN"""
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def go_back(self):
        """Quay lại trang SERVICE (hoặc trang trước)"""
        # TODO: Điều chỉnh index tùy theo flow của bạn
        self.stacked_widget.setCurrentIndex(0)  # Xác định index
        self.reset_form()

    def reset_form(self):
        """Xóa dữ liệu khi thoát trang"""
        Session.selected_locker = None
        self.thong_bao_tu.clear()