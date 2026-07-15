# app/controllers/cleanup_worker.py
from PyQt6.QtCore import QThread, pyqtSignal

class CleanupWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, cleanup_service):
        super().__init__()
        self.cleanup_service = cleanup_service

    def run(self):
        self.cleanup_service.cleanup_users()
        self.finished.emit()