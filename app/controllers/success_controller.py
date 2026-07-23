from PyQt6.QtWidgets import QMainWindow
from PyQt6 import uic
from PyQt6.QtCore import QSize, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from pathlib import Path
from PyQt6.QtGui import QMovie
class SuccessController(QMainWindow):

    # def __init__(self):

    #     super().__init__()

    #     uic.loadUi("app/ui/SUCCESS.ui", self)

    #     # 🎬 Video widget (thay cho QLabel GIF)
    #     self.video_widget = QVideoWidget(self.success_gif)
    #     self.video_widget.setGeometry(0, 0, self.success_gif.width(), self.success_gif.height())

        
        
    #     # 🎞 Player
    #     self.player = QMediaPlayer(self)
    #     self.player.setVideoOutput(self.video_widget)
    #     # self.player.setAudioOutput(self.audio_output)
    #     self.player.mediaStatusChanged.connect(self.loop_video)
    #     # 📼 Load video
        
    #     BASE_DIR = Path(__file__).resolve().parent.parent
    #     self.video_path = BASE_DIR / "assets" / "gif" / "success.mp4"

    #     if self.video_path.exists():
    #         self.player.setSource(QUrl.fromLocalFile(str(self.video_path)))
    #     else:
    #         print(f"[ERROR] Không tìm thấy video: {self.video_path}")


    #     # Nút OK: mặc định ẨN — chỉ luồng nào cần chờ người dùng bấm xác nhận
    #     # (vd MO_TU chờ ESP32 báo OPENED:)xx mới gọi set_ok_visible(True).
    #     # Các luồng khác (đổi mật khẩu, trả tủ...) giữ nguyên hành vi cũ:
    #     # tự động chuyển trang sau vài giây, không cần bấm gì cả.
    #     self.ok_button.setVisible(False)

    # def set_ok_visible(self, visible):
    #     self.ok_button.setVisible(visible)
    # def showEvent(self, event):
    #     super().showEvent(event)

    #     if self.video_path.exists():
    #         self.player.setPosition(0)
    #         self.player.play()

    # # =========================================================

    # def hideEvent(self, event):
    #     super().hideEvent(event)

    #     self.player.stop()

    # # =========================================================

    # def resizeEvent(self, event):
    #     super().resizeEvent(event)

    #     self.video_widget.setGeometry(self.success_gif.rect())

    # def loop_video(self, status):
    #     if status == QMediaPlayer.MediaStatus.EndOfMedia:
    #         self.player.setPosition(0)
    #         self.player.play()

    # def set_message(self, text):
    #     self.success_text.setText(text)
    def __init__(self):
        super().__init__()

        uic.loadUi("app/ui/SUCCESS.ui", self)

        BASE_DIR = Path(__file__).resolve().parent.parent
        gif_path = BASE_DIR / "assets" / "gif" / "success.gif"

        self.movie = QMovie(str(gif_path))

        if not self.movie.isValid():
            print(f"[ERROR] Không tìm thấy GIF: {gif_path}")

        self.movie.setScaledSize(QSize(180, 180))
        self.success_gif.setMovie(self.movie)
        # Nút OK: mặc định ẨN — chỉ luồng nào cần chờ người dùng bấm xác nhận
        # (vd MO_TU chờ ESP32 báo OPENED:)xx mới gọi set_ok_visible(True).
        # Các luồng khác (đổi mật khẩu, trả tủ...) giữ nguyên hành vi cũ:
        # tự động chuyển trang sau vài giây, không cần bấm gì cả.
        self.ok_button.setVisible(False)

    def set_ok_visible(self, visible):
        self.ok_button.setVisible(visible)

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
        self.success_text.setText(text)