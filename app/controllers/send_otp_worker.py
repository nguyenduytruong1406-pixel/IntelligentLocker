from PyQt6.QtCore import QThread, pyqtSignal


class SendOtpWorker(QThread):

    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        auth_service,
        email
    ):
        super().__init__()

        self.auth_service = auth_service
        self.email = email

    def run(self):

        success, message = (
            self.auth_service.send_otp_to_email(
                self.email
            )
        )

        self.finished.emit(
            success,
            message
        )