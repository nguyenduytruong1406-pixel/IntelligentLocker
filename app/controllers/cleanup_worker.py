# app/controllers/cleanup_worker.py
from PyQt6.QtCore import QThread, pyqtSignal

class CleanupWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, cleanup_service):
        super().__init__()
        self.cleanup_service = cleanup_service

    def run(self):
        self.cleanup_service.cleanup_idle_warning()     # ngày 14 — cảnh báo idle
        self.cleanup_service.cleanup_idle_lockers()      # ngày 16 — thu hồi idle
        self.cleanup_service.cleanup_expiry_warning()    # trước 2 ngày hết hạn — cảnh báo
        self.cleanup_service.cleanup_expired_lockers()   # đã qua hạn — thu hồi
        self.finished.emit()