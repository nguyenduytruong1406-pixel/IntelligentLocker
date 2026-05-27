"""
gui/kiosk_app.py — Class KioskApp: UI + state machine cho màn hình tủ kiosk.

Tách từ kiosk_gui.py (Bước 5).  Entry point vẫn là kiosk_gui.py:
    from gui.kiosk_app import KioskApp
    KioskApp().mainloop()
"""

import threading
import time

import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import messagebox

# ── Internal modules ──────────────────────────────────────────────────────────
from gui.theme import (
    C, SCREEN_W, SCREEN_H, CAM_W, CAM_H,
    VERIFY_FRAMES, ENROLL_FRAMES, THRESHOLD, IDLE_TIMEOUT,
    make_fonts,
)
from hardware.camera import CameraBackend
from ai.ai_utils import liveness, landmarks, embedding, hash_password
from core.user_db import get_user_by_password, register_user, get_user, load_all_embeddings, save_embedding
from core.locker_db import open_locker, assign_locker, get_all_lockers, release_locker, get_user_locker
from core.log_db import log_access


# ═════════════════════════════════════════════════════════════════════════════
#  KioskApp
# ═════════════════════════════════════════════════════════════════════════════

class KioskApp(tk.Tk):

    # ── States ─────────────────────────────────────────────────────────────
    S_IDLE          = "idle"
    S_LOGIN_CHOOSE  = "login_choose"
    S_VERIFY_FACE   = "verify_face"
    S_LOGIN_PASS    = "login_pass"
    S_REGISTER      = "register"
    S_ENROLL_ASK    = "enroll_ask"
    S_ENROLL_FACE   = "enroll_face"
    S_CHOOSE_LOCKER = "choose_locker"
    S_LOCKER_MENU   = "locker_menu"   # NEW: menu Gửi đồ / Trả tủ
    S_SUCCESS       = "success"
    S_FAIL          = "fail"

    # ── Init ───────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        self.title("Smart Locker Kiosk")
        self.configure(bg=C["bg"])
        self.geometry(f"{SCREEN_W}x{SCREEN_H}")
        self.resizable(False, False)

        self.fonts = make_fonts()

        self.state          = self.S_IDLE
        self.cam            = CameraBackend()
        self.db_map         = {}
        self._current_user  = None
        self._consec        = 0
        self._enroll_mssv   = None
        self._enroll_frames = []
        self._idle_timer    = time.time()
        self._warmup_frames = 0

        self._build_ui()
        self._reload_db()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._loop()

    def _on_closing(self):
        print("\n[System] Đang dọn dẹp và tắt hệ thống...")
        self.cam.stop()
        self.destroy()
        import os; os._exit(0)

    # ── BUILD UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        f = self.fonts

        # Header
        hdr = tk.Frame(self, bg=C["surface"], height=70)
        hdr.place(x=0, y=0, width=SCREEN_W)
        tk.Label(hdr, text="🔐  SMART LOCKER",
                 bg=C["surface"], fg=C["text"], font=f["title"]).place(x=24, y=14)
        self.lbl_time = tk.Label(hdr, bg=C["surface"], fg=C["muted"], font=f["body"])
        self.lbl_time.place(x=SCREEN_W - 200, y=24)

        # Camera area
        self.placeholder = tk.Frame(
            self, bg=C["surface"], width=CAM_W, height=CAM_H,
            highlightthickness=1, highlightbackground=C["border"],
        )
        tk.Label(
            self.placeholder,
            text="ĐẠI HỌC SƯ PHẠM KỸ THUẬT TP.HCM\nMakerspace - Smart Locker",
            bg=C["surface"], fg=C["muted"],
            font=("Segoe UI", 16, "bold"), justify="center",
        ).place(relx=0.5, rely=0.5, anchor="center")
        self.placeholder.place(x=20, y=85)

        self.cam_canvas = tk.Canvas(
            self, width=CAM_W, height=CAM_H, bg="black", highlightthickness=0,
        )

        # Footer
        ftr = tk.Frame(self, bg=C["surface"], height=36)
        ftr.place(x=0, y=SCREEN_H - 36, width=SCREEN_W)
        tk.Label(ftr, text="Makerspace HCMUTE · Smart Locker System",
                 bg=C["surface"], fg=C["muted"], font=f["small"]).place(x=16, y=8)

        # Right panel geometry
        px, pw = CAM_W + 40, SCREEN_W - (CAM_W + 40) - 20
        self._px, self._pw = px, pw

        # Status card
        self.card_status = tk.Frame(
            self, bg=C["card"],
            highlightbackground=C["border"], highlightthickness=1,
        )
        self.card_status.place(x=px, y=85, width=pw, height=110)
        self.lbl_status_icon = tk.Label(
            self.card_status, text="👋", bg=C["card"],
            font=tk.font.Font(size=28) if hasattr(tk, "font") else ("Segoe UI", 28),
        )
        self.lbl_status_icon.place(x=14, y=16)
        self.lbl_status_title = tk.Label(
            self.card_status, bg=C["card"], fg=C["text"],
            font=f["head"], text="Xin chào!",
        )
        self.lbl_status_title.place(x=72, y=14)
        self.lbl_status_sub = tk.Label(
            self.card_status, bg=C["card"], fg=C["muted"],
            font=f["body"], wraplength=pw - 90,
        )
        self.lbl_status_sub.place(x=72, y=50)

        # Progress bar
        self.progress_bar = tk.Canvas(
            self, bg=C["surface"], highlightthickness=0, height=6,
        )
        self.progress_bar.place(x=px, y=202, width=pw)
        self._prog_rect = self.progress_bar.create_rectangle(
            0, 0, 0, 6, fill=C["accent"], width=0,
        )

        # Screen frames (right panel)
        base_y = 215
        self._base_y = base_y

        self.frame_idle = tk.Frame(self, bg=C["bg"])
        self._build_idle_frame(self.frame_idle, pw)
        self.frame_idle.place(x=px, y=base_y, width=pw)

        self.frame_login_choose = tk.Frame(self, bg=C["bg"])
        self._build_login_choose_frame(self.frame_login_choose, pw)

        self.frame_login_pass = tk.Frame(self, bg=C["bg"])
        self._build_login_pass_frame(self.frame_login_pass, pw)

        self.frame_register = tk.Frame(self, bg=C["bg"])
        self._build_register_frame(self.frame_register, pw)

        self.frame_enroll_ask = tk.Frame(self, bg=C["bg"])
        self._build_enroll_ask_frame(self.frame_enroll_ask, pw)

        self.frame_locker = tk.Frame(self, bg=C["bg"])

        # NEW: frame menu Gửi đồ / Trả tủ
        self.frame_locker_menu = tk.Frame(self, bg=C["bg"])

    # ── SCREEN BUILDERS ────────────────────────────────────────────────────

    def _build_idle_frame(self, parent, pw):
        tk.Label(parent, text="Chọn hành động",
                 bg=C["bg"], fg=C["muted"], font=("Segoe UI", 11)).pack(pady=(4, 10))
        self._make_big_btn(
            parent, "🔓  ĐĂNG NHẬP", C["accent"], "#1a2f5f",
            lambda: self._go(self.S_LOGIN_CHOOSE),
        ).pack(fill="x", pady=6, ipady=18)
        self._make_big_btn(
            parent, "📝  ĐĂNG KÝ", C["accent2"], "#0a2f38",
            lambda: self._go(self.S_REGISTER),
        ).pack(fill="x", pady=6, ipady=18)

    def _build_login_choose_frame(self, parent, pw):
        tk.Label(parent, text="Chọn cách đăng nhập",
                 bg=C["bg"], fg=C["muted"], font=("Segoe UI", 11)).pack(pady=(4, 12))
        self._make_big_btn(
            parent, "👁  KHUÔN MẶT", C["green"], "#0a2f20",
            lambda: self._go(self.S_VERIFY_FACE),
        ).pack(fill="x", pady=6, ipady=14)
        self._make_big_btn(
            parent, "🔑  MẬT KHẨU", C["yellow"], "#2a1f00",
            lambda: self._go(self.S_LOGIN_PASS),
        ).pack(fill="x", pady=6, ipady=14)
        self._make_back_btn(parent).pack(fill="x", pady=(10, 0))

    def _build_login_pass_frame(self, parent, pw):
        tk.Label(parent, text="Đăng nhập bằng mật khẩu",
                 bg=C["bg"], fg=C["muted"], font=("Segoe UI", 11)).pack(pady=(4, 8))
        self.lp_mssv_var = tk.StringVar()
        self.lp_pw_var   = tk.StringVar()
        for lbl, var, show in [
            ("MSSV",     self.lp_mssv_var, ""),
            ("Mật khẩu", self.lp_pw_var,   "●"),
        ]:
            tk.Label(parent, text=lbl, bg=C["bg"], fg=C["text"],
                     font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=4)
            tk.Entry(parent, textvariable=var, show=show,
                     font=("Segoe UI", 13), bg=C["card"], fg=C["text"],
                     insertbackground=C["text"], relief="flat",
                     ).pack(fill="x", padx=4, pady=(2, 8))
        self.lp_msg = tk.Label(parent, text="", bg=C["bg"],
                               fg=C["red"], font=("Segoe UI", 11))
        self.lp_msg.pack()
        self._make_big_btn(
            parent, "✓  ĐĂNG NHẬP", C["accent"], "#1a2f5f",
            self._do_login_password,
        ).pack(fill="x", pady=(6, 4), ipady=10)
        self._make_back_btn(parent, lambda: self._go(self.S_LOGIN_CHOOSE)).pack(fill="x")

    def _build_register_frame(self, parent, pw):
        tk.Label(parent, text="Tạo tài khoản mới",
                 bg=C["bg"], fg=C["muted"], font=("Segoe UI", 11)).pack(pady=(2, 6))
        fields = [
            ("MSSV *",              "reg_mssv_var",       False),
            ("Họ và tên *",         "reg_name_var",       False),
            ("Email",               "reg_email_var",      False),
            ("Mật khẩu *",          "reg_pw_var",         True),
            ("Nhập lại mật khẩu *", "reg_pw_confirm_var", True),
        ]
        for lbl, attr, is_pw in fields:
            setattr(self, attr, tk.StringVar())
            tk.Label(parent, text=lbl, bg=C["bg"], fg=C["text"],
                     font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=4)
            tk.Entry(parent, textvariable=getattr(self, attr),
                     show="●" if is_pw else "",
                     font=("Segoe UI", 12), bg=C["card"], fg=C["text"],
                     insertbackground=C["text"], relief="flat",
                     ).pack(fill="x", padx=4, pady=(1, 5))
        self.reg_msg = tk.Label(parent, text="", bg=C["bg"],
                                fg=C["red"], font=("Segoe UI", 11))
        self.reg_msg.pack()
        self._make_big_btn(
            parent, "✓  TẠO TÀI KHOẢN", C["accent2"], "#0a2f38",
            self._do_register,
        ).pack(fill="x", pady=(4, 4), ipady=8)
        self._make_back_btn(parent).pack(fill="x")

    def _build_enroll_ask_frame(self, parent, pw):
        self.enroll_ask_name = tk.Label(
            parent, text="", bg=C["bg"], fg=C["text"],
            font=("Segoe UI", 13, "bold"),
        )
        self.enroll_ask_name.pack(pady=(6, 4))
        tk.Label(
            parent,
            text="Bạn có muốn đăng ký khuôn mặt\nđể đăng nhập nhanh hơn?",
            bg=C["bg"], fg=C["muted"], font=("Segoe UI", 12), justify="center",
        ).pack(pady=(0, 14))
        self._make_big_btn(
            parent, "👁  CÓ, ĐĂNG KÝ NGAY", C["green"], "#0a2f20",
            self._start_face_enroll,
        ).pack(fill="x", pady=4, ipady=12)
        self._make_big_btn(
            parent, "⏭  BỎ QUA", C["muted"], "#1a2235",
            lambda: self._go(self.S_IDLE),
        ).pack(fill="x", pady=4, ipady=12)

    # ── WIDGET HELPERS ─────────────────────────────────────────────────────

    def _make_big_btn(self, parent, text, fg, bg, cmd):
        return tk.Button(
            parent, text=text, fg=fg, bg=bg,
            activeforeground=fg, activebackground=bg,
            font=("Segoe UI", 13, "bold"), relief="flat", cursor="hand2",
            command=cmd, highlightthickness=1, highlightbackground=C["border"],
        )

    def _make_back_btn(self, parent, cmd=None):
        return tk.Button(
            parent, text="← Quay lại",
            fg=C["muted"], bg=C["bg"],
            activeforeground=C["text"], activebackground=C["bg"],
            font=("Segoe UI", 11), relief="flat", cursor="hand2",
            command=cmd or (lambda: self._go(self.S_IDLE)),
        )

    # ── NAVIGATION / STATE MACHINE ─────────────────────────────────────────

    def _hide_all_frames(self):
        for attr in [
            "frame_idle", "frame_login_choose", "frame_login_pass",
            "frame_register", "frame_enroll_ask", "frame_locker",
            "frame_locker_menu",
        ]:
            getattr(self, attr).place_forget()

    def _go(self, state: str):
        self.state = state
        self._idle_timer = time.time()
        self._hide_all_frames()

        # Camera On-Demand
        if state in (self.S_VERIFY_FACE, self.S_ENROLL_FACE):
            self.placeholder.place_forget()
            self.cam_canvas.place(x=20, y=85)
            self.cam.start(use_ir=(state == self.S_VERIFY_FACE))
            self._warmup_frames = 10
        else:
            self.cam.stop()
            self.cam_canvas.place_forget()
            self.placeholder.place(x=20, y=85)

        # Per-state setup
        if state == self.S_IDLE:
            self._current_user = None
            self._consec = 0
            self._enroll_mssv = None
            self._set_status("👋", "Xin chào!", "Chọn hành động bên dưới")
            self._set_progress(0)
            self.frame_idle.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_LOGIN_CHOOSE:
            self._set_status("🔓", "Đăng nhập", "Chọn phương thức")
            self._set_progress(0)
            self.frame_login_choose.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_VERIFY_FACE:
            self._consec = 0
            self._set_status("👁", "Đang xác thực...", "Hãy nhìn thẳng vào camera")
            self._set_progress(0)

        elif state == self.S_LOGIN_PASS:
            self.lp_msg.config(text="")
            self._set_status("🔑", "Đăng nhập", "Nhập MSSV và mật khẩu")
            self.frame_login_pass.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_REGISTER:
            self.reg_msg.config(text="")
            self._set_status("📝", "Đăng ký tài khoản", "Điền đầy đủ thông tin")
            self._set_progress(0)
            self.frame_register.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_ENROLL_ASK:
            mssv, name = self._current_user
            self.enroll_ask_name.config(text=f"Chào {name}! Tài khoản đã tạo.")
            self._set_status("✅", "Đăng ký thành công!", "Tài khoản đang chờ duyệt")
            self.frame_enroll_ask.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_ENROLL_FACE:
            self._enroll_frames = []
            self._enroll_mssv   = self._current_user[0]
            self._set_status(
                "📸", f"Đăng ký khuôn mặt — {self._current_user[1]}",
                "Nhìn thẳng vào camera",
            )
            self._set_progress(0)

        elif state == self.S_SUCCESS:
            name = self._current_user[1] if self._current_user else ""
            self._set_status("✅", f"Chào {name}!", "Tủ của bạn đã được mở")
            self._set_progress(100, C["green"])
            self.after(4000, lambda: self._go(self.S_IDLE))

        elif state == self.S_FAIL:
            self._set_status("❌", "Xác thực thất bại", "Vui lòng thử lại")
            self._set_progress(0, C["red"])
            self.after(2500, lambda: self._go(self.S_VERIFY_FACE))

    # ── BUSINESS LOGIC ─────────────────────────────────────────────────────

    def _do_login_password(self):
        mssv = self.lp_mssv_var.get().strip()
        pw   = self.lp_pw_var.get()
        if not mssv or not pw:
            self.lp_msg.config(text="Vui lòng nhập đầy đủ")
            return
        user = get_user_by_password(mssv, hash_password(pw))
        if not user:
            self.lp_msg.config(text="MSSV hoặc mật khẩu sai")
            return
        if not user.get("is_approved"):
            self.lp_msg.config(text="Tài khoản chưa duyệt")
            return
        self._current_user = (mssv, user["name"])
        self._after_login(mssv, user["name"])

    def _on_verify_frame(self, color, ir):
        live_ok, reason = liveness(ir)
        if not live_ok:
            self._set_status("👁", "Đang xác thực...", reason)
            self._consec = 0
            return

        shape, det = landmarks(color)
        if not shape:
            self._set_status("👁", "Đang xác thực...", "Không thấy khuôn mặt")
            self._consec = 0
            return

        mssv, name = self._match(embedding(color, shape))
        if mssv:
            self._consec += 1
            self._set_progress(int(self._consec / VERIFY_FRAMES * 100))
            self._set_status("✅", name, f"Xác thực... {self._consec}/{VERIFY_FRAMES}")
            if self._consec >= VERIFY_FRAMES:
                user = get_user(mssv)
                if not user.get("is_approved"):
                    self._set_status("⏳", name, "Chưa duyệt")
                    self.after(3000, lambda: self._go(self.S_IDLE))
                    return
                self._current_user = (mssv, name)
                self._after_login(mssv, name)
        else:
            self._consec = 0
            self._set_status("👁", "Đang xác thực...", "Không nhận ra — thử lại")

    def _after_login(self, mssv: str, name: str):
        """
        Sau khi xác thực thành công:
        - Chưa có tủ  → hiện sơ đồ chọn tủ
        - Đã có tủ    → hiện menu Gửi đồ / Trả tủ
        """
        lockers   = get_all_lockers()
        my_locker = next(
            (lid for lid, info in lockers.items()
             if info.get("current_mssv") == mssv), None,
        )
        if my_locker:
            self._show_locker_menu(mssv, name, my_locker, lockers)
        else:
            self._show_locker_picker(mssv, name, lockers)

    def _do_register(self):
        mssv  = self.reg_mssv_var.get().strip()
        name  = self.reg_name_var.get().strip()
        pw    = self.reg_pw_var.get()
        email = self.reg_email_var.get().strip()
        if not mssv or not name:
            self.reg_msg.config(text="Vui lòng nhập đủ thông tin")
            return
        if len(pw) < 6:
            self.reg_msg.config(text="Pass tối thiểu 6 ký tự")
            return
        if not register_user(mssv, name, email, hash_password(pw)):
            self.reg_msg.config(text="Lỗi tạo user")
            return
        self._current_user = (mssv, name)
        self._go(self.S_ENROLL_ASK)

    def _start_face_enroll(self):
        self._go(self.S_ENROLL_FACE)

    def _on_enroll_frame(self, color):
        shape, det = landmarks(color)
        if not shape:
            return
        self._enroll_frames.append((color.copy(), shape))
        self._set_progress(int(len(self._enroll_frames) / ENROLL_FRAMES * 100))
        self._set_status("📸", "Đang chụp...",
                         f"{len(self._enroll_frames)}/{ENROLL_FRAMES} ảnh")
        if len(self._enroll_frames) >= ENROLL_FRAMES:
            frames = self._enroll_frames[:]
            mssv   = self._enroll_mssv
            self._enroll_mssv   = None
            self._enroll_frames = []
            threading.Thread(
                target=self._do_enroll_bg, args=(mssv, frames), daemon=True,
            ).start()

    def _do_enroll_bg(self, mssv: str, frames: list):
        avg_emb = np.mean([embedding(f, s) for f, s in frames], axis=0)
        save_embedding(mssv, avg_emb)
        self._reload_db()
        self.after(0, lambda: (
            self._set_status("✅", "Thành công!", "Khuôn mặt đã được lưu"),
            self._set_progress(100, C["green"]),
            self.after(3000, lambda: self._go(self.S_IDLE)),
        ))

    # ── LOCKER MENU (Gửi đồ / Trả tủ) ─────────────────────────────────────

    def _show_locker_menu(self, mssv: str, name: str, locker_id: str, lockers: dict):
        """
        Sinh viên đã có tủ → hiện 2 lựa chọn:
          📦 Gửi đồ  → mở tủ (open_locker)
          🔓 Trả tủ  → giải phóng tủ (release_locker) + xác nhận
        """
        self.state = self.S_LOCKER_MENU
        self._idle_timer = time.time()
        self._hide_all_frames()
        self.cam.stop()
        self.cam_canvas.place_forget()
        self.placeholder.place(x=20, y=85)

        locker_info = lockers.get(locker_id, {})
        size_label  = locker_info.get("size", "").capitalize()

        # Xóa nội dung cũ
        for w in self.frame_locker_menu.winfo_children():
            w.destroy()

        # Tiêu đề
        tk.Label(
            self.frame_locker_menu,
            text=f"Chào {name}!",
            bg=C["bg"], fg=C["text"],
            font=("Segoe UI", 15, "bold"),
        ).pack(pady=(8, 2))

        tk.Label(
            self.frame_locker_menu,
            text=f"Tủ của bạn:  {locker_id}  ({size_label})",
            bg=C["bg"], fg=C["muted"],
            font=("Segoe UI", 12),
        ).pack(pady=(0, 16))

        # Nút Gửi đồ
        self._make_big_btn(
            self.frame_locker_menu,
            "📦  GỬI ĐỒ  (Mở tủ)",
            C["accent"], "#1a2f5f",
            lambda: self._do_open_locker(mssv, name, locker_id),
        ).pack(fill="x", pady=6, ipady=18)

        # Nút Trả tủ
        self._make_big_btn(
            self.frame_locker_menu,
            "🔓  TRẢ TỦ  (Không dùng nữa)",
            C["red"], "#3b0a0a",
            lambda: self._confirm_release(mssv, name, locker_id),
        ).pack(fill="x", pady=6, ipady=18)

        self._make_back_btn(self.frame_locker_menu).pack(fill="x", pady=(10, 0))

        self.frame_locker_menu.place(x=self._px, y=self._base_y, width=self._pw)
        self._set_status("🗄", f"Tủ {locker_id}", "Chọn hành động")
        self._set_progress(100, C["green"])

    def _do_open_locker(self, mssv: str, name: str, locker_id: str):
        """Mở tủ và chuyển sang màn hình thành công."""
        self._current_user = (mssv, name)
        ok, msg = open_locker(mssv)
        if ok:
            self._go(self.S_SUCCESS)
        else:
            messagebox.showerror("Lỗi", f"Không thể mở tủ: {msg}")

    def _confirm_release(self, mssv: str, name: str, locker_id: str):
        """Xác nhận trước khi trả tủ."""
        confirmed = messagebox.askyesno(
            "Xác nhận trả tủ",
            f"Bạn có chắc muốn trả tủ {locker_id}?\n"
            "Sau khi trả, tủ sẽ được giải phóng cho người khác.\n\n"
            "⚠ Hành động này không thể hoàn tác.",
        )
        if not confirmed:
            return

        ok, msg = release_locker(mssv)
        if ok:
            messagebox.showinfo(
                "Đã trả tủ",
                f"Tủ {locker_id} đã được giải phóng.\nCảm ơn bạn đã sử dụng dịch vụ!",
            )
            self._go(self.S_IDLE)
        else:
            messagebox.showerror("Lỗi", f"Không thể trả tủ: {msg}")

    # ── LOCKER GRID PICKER ─────────────────────────────────────────────────

    def _show_locker_picker(self, mssv: str, name: str, lockers: dict):
        """Sinh viên chưa có tủ → hiện sơ đồ chọn tủ."""
        self._go(self.S_CHOOSE_LOCKER)
        for w in self.frame_locker.winfo_children():
            w.destroy()

        tk.Label(self.frame_locker, text=f"Chọn tủ cho {name}",
                 bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 14, "bold")).pack(pady=(0, 10))

        grid = tk.Frame(self.frame_locker, bg=C["bg"])
        grid.pack(fill="x")
        for i in range(6):
            grid.columnconfigure(i, weight=1)

        # Sơ đồ vật lý
        layout = [
            {"id": 1, "r": 0, "c": 0, "w": 2, "t": "small"},
            {"id": 2, "r": 0, "c": 2, "w": 2, "t": "small"},
            {"id": 3, "r": 0, "c": 4, "w": 2, "t": "small"},
            {"id": 4, "r": 1, "c": 0, "w": 2, "t": "small"},
            {"id": 0, "r": 1, "c": 2, "w": 2, "t": "ctrl"},
            {"id": 5, "r": 1, "c": 4, "w": 2, "t": "small"},
            {"id": 6, "r": 2, "c": 0, "w": 3, "t": "large"},
            {"id": 7, "r": 2, "c": 3, "w": 3, "t": "large"},
            {"id": 8, "r": 3, "c": 0, "w": 3, "t": "large"},
            {"id": 9, "r": 3, "c": 3, "w": 3, "t": "large"},
        ]

        has_empty = False
        for it in layout:
            if it["t"] == "ctrl":
                tk.Label(grid, text="🎛\nMain Controller",
                         bg="#1e3a8a", fg="white",
                         font=("Segoe UI", 11, "bold"),
                         ).grid(row=it["r"], column=it["c"], columnspan=it["w"],
                                sticky="nsew", padx=4, pady=4, ipady=10)
                continue

            lid      = f"L{it['id']:02d}"
            info     = lockers.get(lid, {})
            st       = info.get("status", "empty").lower()
            is_empty = st == "empty" and not info.get("current_mssv")
            if is_empty:
                has_empty = True

            ipady = 12 if it["t"] == "small" else 18

            def _on_pick(l=lid):
                assign_locker(mssv, l)
                open_locker(mssv)
                self._current_user = (mssv, name)
                self._go(self.S_SUCCESS)

            tk.Button(
                grid,
                text=f"Tủ {lid}\n{'Trống' if is_empty else 'Đang dùng'}",
                bg=C["green"] if is_empty else C["card"],
                fg="white"    if is_empty else C["muted"],
                activebackground="#059669",
                font=("Segoe UI", 11, "bold"),
                relief="flat",
                state=tk.NORMAL if is_empty else tk.DISABLED,
                command=_on_pick,
            ).grid(row=it["r"], column=it["c"], columnspan=it["w"],
                   sticky="nsew", padx=4, pady=4, ipady=ipady)

        if not has_empty:
            tk.Label(self.frame_locker, text="Không còn tủ trống!",
                     bg=C["bg"], fg=C["red"],
                     font=("Segoe UI", 12, "bold")).pack(pady=10)

        self._make_back_btn(self.frame_locker).pack(pady=15)
        self.frame_locker.place(x=self._px, y=self._base_y, width=self._pw)
        self._set_status("🗄", f"Chào {name}!", "Vui lòng click chọn tủ trên sơ đồ")

    # ── MAIN LOOP ──────────────────────────────────────────────────────────

    def _loop(self):
        # Auto-idle timeout (không timeout ở màn hình locker_menu để tránh mất lựa chọn)
        if (self.state not in (self.S_IDLE, self.S_SUCCESS, self.S_LOCKER_MENU)
                and time.time() - self._idle_timer > IDLE_TIMEOUT):
            self._go(self.S_IDLE)

        color, ir = self.cam.get()
        if color is not None:
            if self._warmup_frames > 0:
                self._warmup_frames -= 1
                self.after(30, self._loop)
                return

            frame = color.copy()

            if self.state == self.S_VERIFY_FACE:
                self._on_verify_frame(frame, ir)
                shape, det = landmarks(frame)
                if shape:
                    hex_c = "#22c55e" if self._consec >= VERIFY_FRAMES - 1 else "#ef4444"
                    self._draw_landmarks(frame, shape, det, hex_c)

            elif self.state == self.S_ENROLL_FACE:
                self._on_enroll_frame(frame)
                shape, det = landmarks(frame)
                if shape:
                    self._draw_landmarks(frame, shape, det, "#4f6ef7")

            else:
                shape, det = landmarks(frame)
                if shape:
                    self._draw_landmarks(frame, shape, det, "#64748b")

            rgb = cv2.cvtColor(cv2.resize(frame, (CAM_W, CAM_H)), cv2.COLOR_BGR2RGB)
            img = ImageTk.PhotoImage(Image.fromarray(rgb))
            if not hasattr(self, "_cam_img"):
                self._cam_img = self.cam_canvas.create_image(0, 0, anchor="nw", image=img)
            else:
                self.cam_canvas.itemconfig(self._cam_img, image=img)
            self.cam_canvas.image = img

        self.lbl_time.config(text=time.strftime("%H:%M  %d/%m/%Y"))
        self.after(30, self._loop)

    # ── UI HELPERS ─────────────────────────────────────────────────────────

    def _set_status(self, icon: str, title: str, sub: str = ""):
        self.lbl_status_icon.config(text=icon)
        self.lbl_status_title.config(text=title)
        self.lbl_status_sub.config(text=sub)

    def _set_progress(self, percent: int, color: str | None = None):
        self.progress_bar.coords(
            self._prog_rect, 0, 0, int(self._pw * percent / 100), 6,
        )
        self.progress_bar.itemconfig(
            self._prog_rect, fill=color or C["accent"],
        )

    def _match(self, emb: np.ndarray) -> tuple[str | None, str | None]:
        best_mssv, best_name, best_dist = None, None, 1.0
        for mssv, (e, name) in self.db_map.items():
            d = np.linalg.norm(emb - e)
            if d < best_dist:
                best_mssv, best_name, best_dist = mssv, name, d
        return (best_mssv, best_name) if best_dist < THRESHOLD else (None, None)

    def _draw_landmarks(self, frame, shape, det, hex_color: str):
        """Vẽ 68 landmark points + bounding box lên frame."""
        c = hex_color.lstrip("#")
        bgr = tuple(int(c[i:i+2], 16) for i in (4, 2, 0))
        for i in range(68):
            cv2.circle(frame, (shape.part(i).x, shape.part(i).y), 2, bgr, -1)
        cv2.rectangle(frame, (det.left(), det.top()),
                      (det.right(), det.bottom()), bgr, 2)

    def _reload_db(self):
        self.db_map = load_all_embeddings()