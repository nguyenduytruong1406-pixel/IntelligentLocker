from PyQt6.QtWidgets import QMainWindow
from PyQt6 import uic
from PyQt6.QtGui import QMovie
from PyQt6.QtCore import QSize


class LoadingController(QMainWindow):

    def __init__(self):

        super().__init__()

        uic.loadUi(
            "app/ui/LOADING.ui",
            self
        )

        from pathlib import Path
        BASE_DIR = Path(__file__).parent.parent  # trỏ về thư mục SML/app
        self.movie = QMovie(str(BASE_DIR / "assets/gif/loading.gif"))

        self.movie.setScaledSize(
            QSize(180, 180)
        )

        self.loading_gif.setMovie(
            self.movie
        )

        self.movie.start()

    def set_message(self, text):

        self.loading_text.setText(text)