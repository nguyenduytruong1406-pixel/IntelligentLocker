from pathlib import Path

from PyQt6 import uic
from PyQt6.QtGui import QMovie
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QMainWindow


class LoadingController(QMainWindow):

    def __init__(self):
        super().__init__()

        uic.loadUi("app/ui/LOADING.ui", self)

        BASE_DIR = Path(__file__).resolve().parent.parent
        gif_path = BASE_DIR / "assets" / "gif" / "loading.gif"

        self.movie = QMovie(str(gif_path))

        if not self.movie.isValid():
            print(f"[ERROR] Không tìm thấy GIF: {gif_path}")

        self.movie.setScaledSize(QSize(180, 180))
        self.loading_gif.setMovie(self.movie)

    # =========================================================

    def showEvent(self, event):
        super().showEvent(event)

        self.movie.start()

    # =========================================================

    def hideEvent(self, event):
        super().hideEvent(event)

        self.movie.stop()

    # =========================================================

    def set_message(self, text):
        self.loading_text.setText(text)