from PyQt6.QtCore import QObject
from PyQt6.QtCore import QEvent


class KeyboardManager(QObject):

    def __init__(self, keyboard):

        super().__init__()

        self.keyboard = keyboard

    def register(self, line_edit):

        line_edit.installEventFilter(self)

    def eventFilter(self, obj, event):

        if event.type() == QEvent.Type.FocusIn:

            self.keyboard.set_target(obj)

            self.keyboard.show()

        return False