from pathlib import Path
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

# image.py nằm ở app/utils/image.py
# => .parent (utils) → .parent (app) → .parent (project root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def set_image(label, relative_path):
    full_path = BASE_DIR / relative_path

    if not full_path.exists():
        print(f"Không tìm thấy ảnh: {full_path}")
        return

    pixmap = QPixmap(str(full_path))

    if pixmap.isNull():
        print(f"File tồn tại nhưng QPixmap không đọc được: {full_path}")
        return

    label.setPixmap(
        pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )