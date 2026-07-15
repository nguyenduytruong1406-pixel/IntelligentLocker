from PyQt6.QtWidgets import QMainWindow
from PyQt6 import uic
from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from pathlib import Path

class SuccessController(QMainWindow):

    def __init__(self):

        super().__init__()

        uic.loadUi("app/ui/SUCCESS.ui", self)

        # 🎬 Video widget (thay cho QLabel GIF)
        self.video_widget = QVideoWidget(self.success_gif)
        self.video_widget.setGeometry(0, 0, self.success_gif.width(), self.success_gif.height())

        # # 🔊 Audio (bắt buộc trong PyQt6)
        # self.audio_output = QAudioOutput(self)
        
        # 🎞 Player
        self.player = QMediaPlayer(self)
        self.player.setVideoOutput(self.video_widget)
        # self.player.setAudioOutput(self.audio_output)

        # 📼 Load video
        from pathlib import Path
        BASE_DIR = Path(__file__).parent.parent
        video_path = str(BASE_DIR / "assets/gif/success.mp4")
        self.player.setSource(QUrl.fromLocalFile(video_path))


        # 🔁 loop video
        self.player.mediaStatusChanged.connect(self.loop_video)

        self.player.play()

    def loop_video(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def set_message(self, text):
        self.success_text.setText(text)