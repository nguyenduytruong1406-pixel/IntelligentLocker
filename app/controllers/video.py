from PyQt6 import QtCore, QtGui, QtWidgets, uic
from app.paths import UI, GIF, QSS, find_video
from PyQt6.QtWidgets import *
from PyQt6.QtCore import QTimer, pyqtSignal, QUrl, QObject
from PyQt6.uic import loadUi
import sys
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, QUrl
from PyQt6.QtMultimediaWidgets import *
from pathlib import Path

class VideoScreenController(QMainWindow):

    touched = pyqtSignal()

    def __init__(self, stacked_widget):
        super(VideoScreenController,self).__init__()
        uic.loadUi(UI("vd.ui"),self)

        self.stacked_widget = stacked_widget
        self.videoWidget = QVideoWidget()

        layout = QVBoxLayout(self.video_begin)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.videoWidget)

        self.player = QMediaPlayer()
        self.audio = QAudioOutput()

        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.videoWidget)

        self.player.setSource(
            QUrl.fromLocalFile(find_video() or "")
        )

        self.player.play()

        self.player.mediaStatusChanged.connect(
            self.handle_loop
        )

    def handle_loop(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.play()

    def mousePressEvent(self, event):
        self.touched.emit()