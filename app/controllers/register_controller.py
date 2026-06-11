from PyQt6 import QtCore, QtGui, QtWidgets, uic
from app.paths import UI, GIF, QSS, find_video
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

class RegisterController(QMainWindow):

    def __init__(self,stacked_widget, loading_page, success_page):

        super().__init__()

        uic.loadUi(UI("test_keyboard.ui"), self)
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
        self.fullname.installEventFilter(self)
        self.mssv_reg.installEventFilter(self)
        self.email_reg.installEventFilter(self)
        self.pass_reg.installEventFilter(self)
        self.back_begin.clicked.connect(self.go_to_begin)
        self.register_b.clicked.connect(self.register_account)

    def go_to_begin(self):
        self.stacked_widget.setCurrentIndex(0)
        self.reset_form()

    def go_to_login(self):
        self.stacked_widget.setCurrentIndex(1)
        self.reset_form()


    def reset_form(self):
        self.fullname.clear()
        self.mssv_reg.clear()
        self.email_reg.clear()
        self.pass_reg.clear()
        self.thong_bao_reg.setText("")

    # def load_style(self):
    #     # Thêm encoding='utf-8' vào đây
    #     with open(QSS("keyboard.qss"), "r", encoding="utf-8") as file:
    #         self.setStyleSheet(file.read())

    def register_account(self):

        name = self.fullname.text()
        mssv = self.mssv_reg.text()
        email = self.email_reg.text()
        password = self.pass_reg.text()

        success, message = self.auth_service.register(mssv, name, email, password)

        if not success:

            self.thong_bao_reg.setStyleSheet(
                "color: red;"
            )

            self.thong_bao_reg.setText(message)

        # ===== HIỆN LOADING =====
        else:
            self.loading_page.set_message(
                "Đang tiến hành đăng kí !!"
            )

            self.stacked_widget.setCurrentWidget(
                self.loading_page
            )

            # ===== SAU 1 GIÂY =====

            QTimer.singleShot(2000,lambda: self.show_success(
                "Đăng kí thành công",
                self.go_to_begin
                )
            )


    def eventFilter(self, source, event):

        if (event.type() == QEvent.Type.MouseButtonPress):

            # ===== FULLNAME =====
            if source == self.fullname:

                self.keyboard.show()

                self.keyboard.mode = "ABC"

                self.keyboard.build_keyboard()

                self.keyboard.set_target(
                    self.fullname
                )


            # ===== MSSV =====
            elif source == self.mssv_reg:

                self.keyboard.show()

                self.keyboard.mode = "NUM"

                self.keyboard.build_keyboard()

                self.keyboard.set_target(
                    self.mssv_reg
                )


            # ===== EMAIL =====
            elif source == self.email_reg:

                self.keyboard.show()

                self.keyboard.mode = "ABC"

                self.keyboard.build_keyboard()

                self.keyboard.set_target(
                    self.email_reg
                )

            # ===== PASS =====
            elif source == self.pass_reg:

                self.keyboard.show()

                self.keyboard.mode = "ABC"

                self.keyboard.build_keyboard()

                self.keyboard.set_target(
                    self.pass_reg
                )

        return super().eventFilter(
            source,
            event
        )


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

