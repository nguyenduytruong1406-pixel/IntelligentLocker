from PyQt6.QtWidgets import QMainWindow, QVBoxLayout
from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from pathlib import Path


class VideoScreenController(QMainWindow):

    touched = pyqtSignal()

    def __init__(self, stacked_widget):
        super().__init__()

        uic.loadUi('app/ui/vd.ui', self)
        self.stacked_widget = stacked_widget

        # ===== VIDEO WIDGET =====
        self.videoWidget = QVideoWidget()
        layout = QVBoxLayout(self.video_begin)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.videoWidget)

        # ===== PLAYER =====
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.videoWidget)

        # ===== LOAD VIDEO =====
        BASE_DIR = Path(__file__).parent.parent
        video_path = str(BASE_DIR / "assets/gif/video.mp4")
        self.player.setSource(QUrl.fromLocalFile(video_path))

        self.player.play()

        self.player.mediaStatusChanged.connect(self.handle_loop)

    def handle_loop(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def mousePressEvent(self, event):
        self.touched.emit()