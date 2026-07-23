from PyQt6 import QtCore, QtGui, QtWidgets, uic
from PyQt6.QtWidgets import *
from PyQt6.QtCore import QTimer, pyqtSignal, QUrl, QObject
from PyQt6.uic import loadUi
import sys
import random
import secrets
import smtplib
import os
import sqlite3
from datetime import datetime
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtCore import Qt

from app.utils.session import Session
from app.services.locker_service import LockerService
from app.services.auth_service import AuthService
from app.widgets.virtual_keyboard import VirtualKeyboard
from app.widgets.touch_scroll_area import TouchScrollArea
from app.nav import PAGES

class ChangePassController(QMainWindow):

    def __init__(self,stacked_widget, loading_page, success_page):

        super().__init__()

        uic.loadUi("app/ui/Change_Password.ui", self)
        # self.load_style()
        self.stacked_widget = stacked_widget
        self.loading_page = loading_page
        self.success_page = success_page

        self.auth_service = AuthService()

        ########### SETUP BÀN PHÍM ###########
        self.keyboard = VirtualKeyboard()
        # self.keyboard_container.layout().addWidget(self.keyboard,alignment=Qt.AlignmentFlag.AlignCenter)
        self.keyboard_container.layout().addWidget(
            self.keyboard,
            alignment=Qt.AlignmentFlag.AlignTop
        )


        ########### SETUP BUTTON ###########
        for btn in [self.back_begin, self.register_b]:
            btn.setCheckable(True)
            btn.setAutoExclusive(False)

            def create_release_handler(b=btn):
                def safe_clear():
                    try:
                        if b and not b.isHidden():
                            b.setChecked(False)
                    except RuntimeError:
                        pass
                QTimer.singleShot(150, safe_clear)

            btn.released.connect(create_release_handler)



        ############ EVENT  #################
        self.old_pass.installEventFilter(self)
        self.new_pass.installEventFilter(self)
        self.verifi_pass.installEventFilter(self)
        self.back_begin.clicked.connect(self.go_to_login)
        self.register_b.clicked.connect(self.change_pass)

    def go_to_nextcam(self):
        QTimer.singleShot(150, lambda: (self.reset_form(), self.stacked_widget.setCurrentIndex(PAGES["next_cam"])))
        

    def go_to_login(self):
        QTimer.singleShot(150, lambda: self.stacked_widget.setCurrentIndex(PAGES["login"]))
        self.reset_form()


    def reset_form(self):
        self.old_pass.clear()
        self.new_pass.clear()
        self.verifi_pass.clear()
        self.thong_bao_reg.setText("")

    # def load_style(self):
    #     # Thêm encoding='utf-8' vào đây
    #     with open("app/assets/styles/keyboard.qss", "r", encoding="utf-8") as file:
    #         self.setStyleSheet(file.read())

    def change_pass(self):

        old_p = self.old_pass.text()
        new_p = self.new_pass.text()
        ver_p = self.verifi_pass.text()
        mssv = Session.current_user
        

        success, message = self.auth_service.change_password(mssv, old_p, new_p, ver_p)
        if not success:

            self.thong_bao_reg.setStyleSheet(
                "color: red;"
            )

            self.thong_bao_reg.setText(message)

        # ===== HIỆN LOADING =====
        else:
            self.loading_page.set_message(
                "Đang đổi mật khẩu !!"
            )

            self.stacked_widget.setCurrentWidget(
                self.loading_page
            )

            # ===== SAU 1 GIÂY =====

            QTimer.singleShot(2000,lambda: self.show_success(
                "Đổi mật khẩu thành công",
                self.go_to_nextcam
                )
            )


    def eventFilter(self, source, event):

        if (event.type() == QEvent.Type.MouseButtonPress):

            # ===== FULLNAME =====
            if source == self.old_pass:
                self.keyboard.mode = "ABC"
                self.keyboard.build_keyboard()
                self.keyboard.set_target(self.old_pass)
                self.keyboard.confirm_button = None

            # ===== MSSV =====
            elif source == self.new_pass:
                self.keyboard.mode = "NUM"
                self.keyboard.build_keyboard()
                self.keyboard.set_target(self.new_pass)
                self.keyboard.confirm_button = None

            # ===== EMAIL =====
            elif source == self.verifi_pass:
                self.keyboard.mode = "ABC"
                self.keyboard.build_keyboard()
                self.keyboard.set_target(self.verifi_pass)
                self.keyboard.confirm_button = self.register_b  # ← Click register khi OK


        return super().eventFilter(source, event)
    
    def showEvent(self, event):
        self.keyboard.show()
        self.keyboard.set_target(self.old_pass)
        self.keyboard.mode = "ABC"
        self.keyboard.build_keyboard()
        self.keyboard.confirm_button = None
        super().showEvent(event)

    def hideEvent(self, event):
        self.keyboard.hide()
        self.keyboard.confirm_button = None
        super().hideEvent(event)

    def show_success(
        self,
        message,
        next_function,
        delay= 2000
    ):

        self.success_page.set_message(
            message
        )

        self.stacked_widget.setCurrentWidget(
            self.success_page
        )

        QTimer.singleShot(
            delay,
            next_function
        )