from PyQt6.QtWidgets import (
    QWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer


class VirtualKeyboard(QWidget):
    def __init__(self):
        super().__init__()
        self.target = None
        self.mode = "ABC"
        self.is_upper = False

        # ===== MAIN LAYOUT =====
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setFixedWidth(1000)

        # ===== STYLE nền =====
        # self.load_style()

        self.build_keyboard()

    # ================= BUILD KEYBOARD =================
    def build_keyboard(self):
        # Xóa layout cũ
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()

        # ===== LAYOUT CHUẨN GIỐNG HÌNH =====
        if self.mode == "ABC":
            rows = [
                ['q','w','e','r','t','y','u','i','o','p','←'],
                ['a','s','d','f','g','h','j','k','l','ENTER'],
                ['SHIFT','z','x','c','v','b','n','m','?'],
                ['123','/','SPACE','.com','OK']
            ]
        else:
            rows = [
                ['1','2','3','4','5','6','7','8','9','0','←'],
                ['-','/',';',':','(',')','$','&','@','ENTER'],
                ['ABC','.','?','!'],
                ['SPACE','OK']
            ]

        for row_index, row_keys in enumerate(rows):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(5)
            row_layout.setContentsMargins(0, 0, 0, 0)

            row_layout.addStretch()

            for key in row_keys:
                btn = QPushButton()
                btn.setText(self.get_display_text(key))

                # ===== SIZE =====
                btn.setMinimumHeight(70)

                if key == "SPACE":
                    # btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                    btn.setFixedSize(300, 70)

                elif key == "SHIFT":
                    btn.setMinimumWidth(150)

                elif key == "ENTER":
                    btn.setMinimumWidth(150)

                elif key == "←":
                    btn.setMinimumWidth(150)

                elif key in ["123", ".com", "OK"]:
                    btn.setMinimumWidth(110)

                else:
                    btn.setMinimumWidth(70)

                # ===== STYLE =====
                if key in ["SHIFT", "←", "OK", "123", "ENTER"]:
                    btn.setObjectName("specialButton")
                else:
                    btn.setObjectName("normalButton")
                btn.style().unpolish(btn)
                btn.style().polish(btn)



                # =======================================================
                # =======================================================
                # 👉 CODE MỚI: TẠO ĐỘ TRỄ GIỮ MÀU CHO MÀN CẢM ỨNG WAVESHARE
                # =======================================================
# =======================================================
                # 👉 CODE ĐÃ SỬA: CHỐNG LỖI CRASH KHI XÓA NÚT (SHIFT/123)
                # =======================================================
                btn.setCheckable(True)
                btn.setAutoExclusive(False)

                def handle_released(b=btn):
                    # Định nghĩa một hàm an toàn để kiểm tra trước khi setChecked
                    def safe_clear():
                        try:
                            # Nếu nút bấm vẫn còn sống và chưa bị xóa
                            if b and not b.isHidden(): 
                                b.setChecked(False)
                        except RuntimeError:
                            # Nếu nút đã bị xóa bởi build_keyboard(), bỏ qua lỗi này an toàn
                            pass

                    # Giữ màu trong 120ms rồi chạy hàm kiểm tra an toàn ở trên
                    QTimer.singleShot(120, safe_clear)

                btn.released.connect(handle_released)
                # =======================================================
                # =======================================================
                # =======================================================



                # ===== EVENT =====
                btn.clicked.connect(lambda _, k=key: self.key_pressed(k))

                row_layout.addWidget(btn)

            # 👉 CĂN GIỮA HÀNG (đặt ở đây mới đúng)
            row_layout.addStretch()

            self.main_layout.addLayout(row_layout)

    # ================= STYLE =================
    # def load_style(self):
    #     # Thêm encoding='utf-8' vào đây
    #     with open("app/assets/styles/keyboard.qss", "r", encoding="utf-8") as file:
    #         self.setStyleSheet(file.read())


    # ================= HIỂN THỊ CHỮ HOA =================
    def get_display_text(self, key):

        if key == '&':
            return '&&'
        
        if len(key) == 1 and self.is_upper:
            return key.upper()
        return key

    # ================= SET TARGET =================
    def set_target(self, widget):
        self.target = widget

    # ================= XỬ LÝ PHÍM =================
    def key_pressed(self, key):
        if not self.target:
            return

        if key == '←':
            self.target.backspace()

        elif key == 'SPACE':
            self.target.insert(" ")

# ===== ĐOẠN XỬ LÝ ENTER VÀ OK TỰ ĐỘNG CHUYỂN HOẶC NHẤN REGISTER =====
        elif key in ['ENTER', 'OK']:
            parent = self.target.parentWidget()
            if parent:
                next_widget = self.target.nextInFocusChain()
                has_next_input = False
                
                # Vòng lặp 1: Kiểm tra xem phía sau có còn ô nhập liệu (QLineEdit) nào nữa không
                while next_widget and next_widget != self.target:
                    if next_widget.isEnabled() and next_widget.isVisible():
                        if next_widget.__class__.__name__ in ['QLineEdit', 'QTextEdit', 'QPlainTextEdit']:
                            # Tìm thấy ô nhập liệu tiếp theo! Chuyển focus sang đó ngay
                            next_widget.setFocus()
                            self.set_target(next_widget)
                            has_next_input = True
                            return # Kết thúc hàm, tiếp tục gõ ô mới
                    next_widget = next_widget.nextInFocusChain()
                
                     

                        
            
            # Nếu không tìm thấy nút bấm, ẩn bàn phím như bình thường
            self.hide()
        # ====================================================================

        elif key == 'SHIFT':
            self.is_upper = not self.is_upper
            self.build_keyboard()

        elif key == '123':
            self.mode = "NUM"
            self.build_keyboard()

        elif key == 'ABC':
            self.mode = "ABC"
            self.build_keyboard()

        else:
            if self.mode == "NUM" and not key.isdigit():

                return
            
            if self.is_upper:
                key = key.upper()
            self.target.insert(key)

    