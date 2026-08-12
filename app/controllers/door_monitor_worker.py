from PyQt6.QtCore import QThread, pyqtSignal

class DoorMonitorWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, door_monitor_service):
        super().__init__()
        self.door_monitor_service = door_monitor_service

    def run(self):
        self.door_monitor_service.check_open_doors()
        self.finished.emit()