from PyQt6.QtWidgets import QVBoxLayout, QLabel
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


def build_card_content(btn, icon_path, title, subtitle):
    layout = QVBoxLayout(btn)
    layout.setContentsMargins(16, 20, 16, 20)
    layout.setSpacing(4)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # ===== ICON =====
    icon_label = QLabel()
    pixmap = QPixmap(icon_path)
    if not pixmap.isNull():
        icon_label.setPixmap(
            pixmap.scaled(
                300, 300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
    icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # để click xuyên qua tới nút
    layout.addWidget(icon_label)

    # ===== TIÊU ĐỀ =====
    title_label = QLabel(title)
    title_label.setObjectName("card_title")
    title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    layout.addWidget(title_label)

    # ===== MÔ TẢ =====
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("card_subtitle")
    subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle_label.setWordWrap(True)
    subtitle_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    layout.addWidget(subtitle_label)