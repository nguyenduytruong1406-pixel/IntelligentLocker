"""
gui/kiosk_app.py — Class KioskApp: UI + state machine cho màn hình tủ kiosk.

Tách từ kiosk_gui.py (Bước 5).  Entry point vẫn là kiosk_gui.py:
    from gui.kiosk_app import KioskApp
    KioskApp().mainloop()
"""

import threading
import time
import random
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import messagebox

# ── Cấu hình môi trường cho Gửi Email ─────────────────────────────────────────
load_dotenv(r"D:/DATN/Software/test_db_ver1/app_password.env")

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
#  Hàm gửi OTP & Class OTPDialog (Bàn phím ảo)
# ═════════════════════════════════════════════════════════════════════════════

def send_otp_email(student_email: str, student_name: str, otp_code: str) -> bool:
    """Gửi email chứa mã OTP 6 số cho sinh viên."""
    sender_email = os.getenv("MAIL_SENDER")
    sender_password = os.getenv("MAIL_PASSWORD")
    sender_name = os.getenv("MAIL_SENDER_NAME", "Smart Locker — HCMUTE")

    if not sender_email or not sender_password:
        print("[Mail OTP] ⚠ Chưa cấu hình mail, bỏ qua gửi OTP.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Mã xác thực OTP Smart Locker: {otp_code}"
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = student_email

        html = f"""
        <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:auto;
                    border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
          <div style="background:#4D94FF;padding:24px 32px">
            <h2 style="color:#fff;margin:0">🔒 Mã xác thực đăng nhập</h2>
          </div>
          <div style="padding:28px 32px;color:#374151">
            <p>Xin chào <strong>{student_name}</strong>,</p>
            <p>Hệ thống nhận được yêu cầu đăng nhập vào Kiosk Smart Locker bằng mật khẩu của bạn.</p>
            <div style="background:#f3f4f6;text-align:center;padding:20px;border-radius:8px;margin:20px 0">
              <p style="margin:0;font-size:14px;color:#6b7280">MÃ OTP CỦA BẠN LÀ:</p>
              <h1 style="margin:10px 0 0;font-size:36px;color:#1f2937;letter-spacing:4px;">{otp_code}</h1>
            </div>
            <p style="color:#ef4444;font-size:13px">⚠ Mã này có hiệu lực trong 3 phút. Tuyệt đối không chia sẻ mã này cho bất kỳ ai.</p>
          </div>
        </div>"""
        
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, student_email, msg.as_string())
            
        print(f"[Mail OTP] ✉ Đã gửi OTP tới {student_email}")
        return True
    except Exception as e:
        print(f"[Mail OTP] ✗ Lỗi gửi OTP: {e}")
        return False

class OTPDialog(tk.Toplevel):
    def __init__(self, parent, email, true_otp):
        super().__init__(parent)
        self.title("Xác thực OTP")
        self.geometry("400x550")
        self.resizable(False, False)
        
        # Bắt buộc người dùng phải thao tác trên cửa sổ này
        self.transient(parent)
        self.grab_set()
        
        self.true_otp = true_otp
        self.result = False  # Trả về True nếu nhập đúng
        self.current_otp = ""

        # Giao diện
        self.configure(bg="#f4f7f6")
        
        tk.Label(self, text="🔒 NHẬP MÃ OTP", font=("Segoe UI", 18, "bold"), bg="#f4f7f6", fg="#007bff").pack(pady=(20, 5))
        tk.Label(self, text=f"Mã 6 số đã được gửi đến:\n{email}", font=("Segoe UI", 11), bg="#f4f7f6", justify="center").pack(pady=5)
        
        # Ô hiển thị mã đang nhập
        self.display_var = tk.StringVar(value="_ _ _ _ _ _")
        self.display_label = tk.Label(self, textvariable=self.display_var, font=("Courier New", 28, "bold"), bg="#ffffff", fg="#333333", width=12, relief="solid", bd=1)
        self.display_label.pack(pady=15)
        
        # Khung chứa bàn phím ảo
        keypad_frame = tk.Frame(self, bg="#f4f7f6")
        keypad_frame.pack(pady=10)
        
        buttons = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('Xóa', 3, 0), ('0', 3, 1), ('OK', 3, 2)
        ]
        
        for (text, row, col) in buttons:
            btn = tk.Button(keypad_frame, text=text, font=("Segoe UI", 16, "bold"), width=5, height=2, 
                            bg="#ffffff" if text not in ('Xóa', 'OK') else ("#dc3545" if text == 'Xóa' else "#28a745"),
                            fg="#333333" if text not in ('Xóa', 'OK') else "#ffffff",
                            relief="raised", command=lambda t=text: self.on_button_click(t))
            btn.grid(row=row, column=col, padx=8, pady=8)
            
        # Nút Hủy
        tk.Button(self, text="Hủy bỏ", font=("Segoe UI", 12), bg="#6c757d", fg="white", width=15, command=self.destroy).pack(pady=15)

        # Lắng nghe sự kiện từ bàn phím vật lý
        self.bind("<Key>", self.on_keyboard_press)
        self.bind("<Return>", lambda e: self.on_button_click('OK'))
        self.bind("<BackSpace>", lambda e: self.on_button_click('Xóa'))

    def update_display(self):
        display_text = " ".join(list(self.current_otp.ljust(6, "_")))
        self.display_var.set(display_text)

    def on_button_click(self, char):
        if char == 'Xóa':
            self.current_otp = self.current_otp[:-1]
        elif char == 'OK':
            self.verify_otp()
            return
        elif len(self.current_otp) < 6 and char.isdigit():
            self.current_otp += char
            
        self.update_display()
        
        # Tự động check khi đủ 6 số
        if len(self.current_otp) == 6:
            self.after(200, self.verify_otp)

    def on_keyboard_press(self, event):
        if event.char.isdigit():
            self.on_button_click(event.char)

    def verify_otp(self):
        if len(self.current_otp) < 6:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập đủ 6 số OTP!", parent=self)
            return
            
        if self.current_otp == self.true_otp:
            self.result = True
            self.destroy()
        else:
            messagebox.showerror("Sai mã", "Mã OTP không chính xác. Vui lòng thử lại!", parent=self)
            self.current_otp = ""
            self.update_display()


# ═════════════════════════════════════════════════════════════════════════════
#  VirtualKeyboard — Bàn phím ảo QWERTY nhúng trong cửa sổ chính (tk.Frame)
# ═════════════════════════════════════════════════════════════════════════════

class VirtualKeyboard:
    """
    Bàn phím ảo tk.Frame nhúng trong cửa sổ chính.
    - Ẩn mặc định, chỉ hiện khi người dùng CLICK vào Entry
    - Có title bar để kéo ra chỗ khác
    - takefocus=False trên tất cả nút → entry không mất focus
    - Đóng bằng nút ✕ trên title bar hoặc nút OK
    """

    _ROWS_LOWER = [
        ["1","2","3","4","5","6","7","8","9","0","⌫"],
        ["q","w","e","r","t","y","u","i","o","p"],
        ["a","s","d","f","g","h","j","k","l","@","."],
        ["⇧","z","x","c","v","b","n","m","_","-","⌫"],
        ["SPACE","CLR","OK"],
    ]
    _ROWS_UPPER = [
        ["1","2","3","4","5","6","7","8","9","0","⌫"],
        ["Q","W","E","R","T","Y","U","I","O","P"],
        ["A","S","D","F","G","H","J","K","L","@","."],
        ["⇩","Z","X","C","V","B","N","M","_","-","⌫"],
        ["SPACE","CLR","OK"],
    ]

    KB_W    = 422
    KB_H    = 272   # 24px title bar + 248px keys

    _BG_FRAME  = "#0d1021"
    _BG_TITLE  = "#1a1d27"
    _BG_KEY    = "#252a3d"
    _BG_SPACE  = "#1a1f30"
    _BG_SHIFT  = "#3b4fd4"
    _BG_DEL    = "#7f1d1d"
    _BG_OK     = "#14532d"
    _BG_CLR    = "#374151"
    _FG        = "#e2e8f0"
    _FG_MUTED  = "#64748b"

    def __init__(self, root: tk.Tk):
        self._root    = root
        self._target: tk.Entry | None = None
        self._shift   = False
        self._visible = False
        self._enabled = False   # True sau khi app render xong
        # Vị trí mặc định — góc dưới phải, trên footer
        self._x = SCREEN_W - self.KB_W - 2
        self._y = SCREEN_H - self.KB_H - 36
        # Drag
        self._drag_ox = 0
        self._drag_oy = 0

        self._frame = tk.Frame(
            root, bg=self._BG_FRAME,
            highlightthickness=1, highlightbackground="#2e3150",
        )
        self._build()
        # KHÔNG gọi place() → frame không hiển thị cho đến khi _on_click

    # ──────────────────────────────────────── enable / attach
    def enable(self):
        """Gọi sau khi app render xong (dùng root.after(200, ...))."""
        self._enabled = True

    def attach(self, entry: tk.Entry):
        """Gắn bàn phím — chỉ phản hồi Button-1 (click/chạm), không FocusIn."""
        entry.bind("<Button-1>", lambda e, en=entry: self._on_click(en), add="+")

    # ──────────────────────────────────────── show / hide
    def _on_click(self, entry: tk.Entry):
        if not self._enabled:
            return
        self._target = entry
        self._shift  = False
        self._build_keys()
        self._frame.place(x=self._x, y=self._y, width=self.KB_W, height=self.KB_H)
        self._frame.lift()
        self._visible = True

    def hide(self):
        self._frame.place_forget()
        self._visible = False
        self._target  = None

    # ──────────────────────────────────────── build
    def _build(self):
        """Build toàn bộ (title bar + keys) — gọi một lần."""
        for w in self._frame.winfo_children():
            w.destroy()

        # Title bar
        self._title_bar = tk.Frame(self._frame, bg=self._BG_TITLE, height=24)
        self._title_bar.pack(fill="x")
        self._title_bar.pack_propagate(False)

        tk.Label(
            self._title_bar, text="⌨  Bàn phím",
            bg=self._BG_TITLE, fg=self._FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=8)

        tk.Button(
            self._title_bar, text="✕",
            bg=self._BG_TITLE, fg=self._FG_MUTED,
            activebackground="#ef4444", activeforeground="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat", bd=0, padx=8,
            takefocus=False, cursor="hand2",
            command=self.hide,
        ).pack(side="right")

        # Bind drag trên toàn bộ title bar và các child
        for w in (self._title_bar, *self._title_bar.winfo_children()):
            w.bind("<ButtonPress-1>", self._drag_start, add="+")
            w.bind("<B1-Motion>",     self._drag_move,  add="+")

        # Vùng phím
        self._keys_frame = tk.Frame(self._frame, bg=self._BG_FRAME)
        self._keys_frame.pack(fill="both", expand=True)
        self._build_keys()

    def _build_keys(self):
        """Rebuild chỉ phần phím (sau shift toggle)."""
        for w in self._keys_frame.winfo_children():
            w.destroy()

        outer = tk.Frame(self._keys_frame, bg=self._BG_FRAME, padx=3, pady=2)
        outer.pack(fill="both", expand=True)

        rows = self._ROWS_UPPER if self._shift else self._ROWS_LOWER

        for row_keys in rows:
            row_f = tk.Frame(outer, bg=self._BG_FRAME)
            row_f.pack(fill="x", pady=1)

            for key in row_keys:
                is_space = key == "SPACE"
                is_ok    = key == "OK"
                is_clr   = key == "CLR"
                is_del   = key == "⌫"
                is_shift = key in ("⇧", "⇩")

                bg = (self._BG_SHIFT if is_shift
                      else self._BG_DEL   if is_del
                      else self._BG_OK    if is_ok
                      else self._BG_CLR   if is_clr
                      else self._BG_SPACE if is_space
                      else self._BG_KEY)

                label = ("⇧" if key == "⇩" else "SPACE" if is_space else key)
                font  = (("Segoe UI", 11, "bold")
                         if (is_ok or is_shift or is_del or is_clr)
                         else ("Segoe UI", 12))

                btn = tk.Button(
                    row_f, text=label,
                    bg=bg, fg=self._FG,
                    activebackground="#4f6ef7", activeforeground="white",
                    font=font, relief="flat", bd=0,
                    takefocus=False, cursor="hand2",
                    command=lambda k=key: self._press(k),
                )

                kw: dict = {"side": "left", "pady": 1, "padx": 1, "ipady": 8}
                if is_space:
                    kw.update({"expand": True, "fill": "x"})
                elif is_ok:
                    kw.update({"ipadx": 14})
                elif is_clr:
                    kw.update({"ipadx": 8})
                elif is_shift or is_del:
                    kw.update({"ipadx": 7})
                else:
                    kw.update({"ipadx": 6})

                btn.pack(**kw)

    # ──────────────────────────────────────── drag
    def _drag_start(self, event):
        self._drag_ox = event.x_root - self._x
        self._drag_oy = event.y_root - self._y

    def _drag_move(self, event):
        nx = max(0, min(event.x_root - self._drag_ox, SCREEN_W - self.KB_W))
        ny = max(0, min(event.y_root - self._drag_oy, SCREEN_H - self.KB_H))
        self._x, self._y = nx, ny
        self._frame.place(x=nx, y=ny, width=self.KB_W, height=self.KB_H)
        self._frame.lift()

    # ──────────────────────────────────────── press
    def _press(self, key: str):
        if self._target is None or not self._target.winfo_exists():
            self.hide()
            return

        entry = self._target

        if key in ("⇧", "⇩"):
            self._shift = not self._shift
            self._build_keys()
            self._frame.lift()
            return

        if key == "⌫":
            try:
                pos = entry.index(tk.INSERT)
                if pos > 0:
                    entry.delete(pos - 1, pos)
            except Exception:
                pass
            return

        if key == "CLR":
            entry.delete(0, tk.END)
            return

        if key == "OK":
            self.hide()
            return

        char = " " if key == "SPACE" else key
        try:
            pos = entry.index(tk.INSERT)
            entry.insert(pos, char)
        except Exception:
            entry.insert(tk.END, char)

        if self._shift and key.isalpha():
            self._shift = False
            self._build_keys()
            self._frame.lift()


def attach_keyboard(root: tk.Tk, entry: tk.Entry):
    """Stub giữ lại để tránh lỗi nếu còn gọi ở đâu đó."""
    pass


# ═════════════════════════════════════════════════════════════════════════════
#  KioskApp
# ═════════════════════════════════════════════════════════════════════════════

class KioskApp(tk.Tk):

    # ── States ─────────────────────────────────────────────────────────────
    S_IDLE          = "idle"
    S_LOGIN_CHOOSE  = "login_choose"
    S_FACE_MSSV     = "face_mssv"      
    S_VERIFY_FACE   = "verify_face"
    S_LOGIN_PASS    = "login_pass"
    S_REGISTER      = "register"
    S_ENROLL_ASK    = "enroll_ask"
    S_ENROLL_FACE   = "enroll_face"
    S_CHOOSE_LOCKER = "choose_locker"
    S_LOCKER_MENU   = "locker_menu"
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
        self._face_mssv     = None        
        self._consec        = 0
        self._enroll_mssv   = None
        self._enroll_frames = []
        self._idle_timer    = time.time()

        self._vkb = VirtualKeyboard(self)   # tạo trước _build_ui vì các frame builder dùng attach()
        self._build_ui()
        self._reload_db()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._verify_done = False
        # Bật bàn phím sau 300ms — đảm bảo app render xong, tránh FocusIn giả
        self.after(300, self._vkb.enable)
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
        hdr = tk.Frame(self, bg=C["surface"], height=60)
        hdr.place(x=0, y=0, width=SCREEN_W)
        tk.Label(hdr, text="🔐  SMART LOCKER",
                 bg=C["surface"], fg=C["text"], font=f["title"]).place(x=24, y=14)
        self.lbl_time = tk.Label(hdr, bg=C["surface"], fg=C["muted"], font=f["body"])
        self.lbl_time.place(x=SCREEN_W - 200, y=18)

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
        self.placeholder.place(x=20, y=65)

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
        self.card_status.place(x=px, y=65, width=pw, height=90)
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
        self.progress_bar.place(x=px, y=167, width=pw)
        self._prog_rect = self.progress_bar.create_rectangle(
            0, 0, 0, 6, fill=C["accent"], width=0,
        )

        # Screen frames (right panel)
        base_y = 178
        self._base_y = base_y

        self.frame_idle = tk.Frame(self, bg=C["bg"])
        self._build_idle_frame(self.frame_idle, pw)
        self.frame_idle.place(x=px, y=base_y, width=pw)

        self.frame_login_choose = tk.Frame(self, bg=C["bg"])
        self._build_login_choose_frame(self.frame_login_choose, pw)

        self.frame_face_mssv = tk.Frame(self, bg=C["bg"])   
        self._build_face_mssv_frame(self.frame_face_mssv, pw)

        self.frame_login_pass = tk.Frame(self, bg=C["bg"])
        self._build_login_pass_frame(self.frame_login_pass, pw)

        self.frame_register = tk.Frame(self, bg=C["bg"])
        self._build_register_frame(self.frame_register, pw)

        self.frame_enroll_ask = tk.Frame(self, bg=C["bg"])
        self._build_enroll_ask_frame(self.frame_enroll_ask, pw)

        self.frame_locker = tk.Frame(self, bg=C["bg"])
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
            lambda: self._go(self.S_FACE_MSSV),  
        ).pack(fill="x", pady=6, ipady=14)
        self._make_big_btn(
            parent, "🔑  MẬT KHẨU", C["yellow"], "#2a1f00",
            lambda: self._go(self.S_LOGIN_PASS),
        ).pack(fill="x", pady=6, ipady=14)
        self._make_back_btn(parent).pack(fill="x", pady=(10, 0))

    def _build_face_mssv_frame(self, parent, pw):
        tk.Label(parent, text="Nhập MSSV để xác thực khuôn mặt",
                 bg=C["bg"], fg=C["muted"], font=("Segoe UI", 11)).pack(pady=(4, 10))
        tk.Label(parent, text="MSSV", bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=4)
        self.face_mssv_var = tk.StringVar()
        _face_entry = tk.Entry(parent, textvariable=self.face_mssv_var,
                 font=("Segoe UI", 14), bg=C["card"], fg=C["text"],
                 insertbackground=C["text"], relief="flat",
                 )
        _face_entry.pack(fill="x", padx=4, pady=(2, 10))
        self._vkb.attach(_face_entry)
        self.face_mssv_msg = tk.Label(parent, text="", bg=C["bg"],
                                      fg=C["red"], font=("Segoe UI", 11))
        self.face_mssv_msg.pack()
        self._make_big_btn(
            parent, "✓  TIẾP TỤC", C["green"], "#0a2f20",
            self._do_face_mssv_submit,
        ).pack(fill="x", pady=(6, 4), ipady=12)
        self._make_back_btn(parent, lambda: self._go(self.S_LOGIN_CHOOSE)).pack(fill="x")

    def _build_login_pass_frame(self, parent, pw):
        tk.Label(parent, text="Đăng nhập bằng mật khẩu & OTP",
                 bg=C["bg"], fg=C["muted"], font=("Segoe UI", 11)).pack(pady=(4, 8))
        
        self.lp_mssv_var = tk.StringVar()
        self.lp_pw_var   = tk.StringVar()
        self.lp_otp_var  = tk.StringVar()

        for lbl, var, show in [
            ("MSSV",     self.lp_mssv_var, ""),
            ("Mật khẩu", self.lp_pw_var,   "●"),
        ]:
            tk.Label(parent, text=lbl, bg=C["bg"], fg=C["text"],
                     font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=4)
            _lp_e = tk.Entry(parent, textvariable=var, show=show,
                     font=("Segoe UI", 13), bg=C["card"], fg=C["text"],
                     insertbackground=C["text"], relief="flat",
                     )
            _lp_e.pack(fill="x", padx=4, pady=(2, 8))
            self._vkb.attach(_lp_e)

        # Khung chứa ô OTP và nút Gửi mã
        tk.Label(parent, text="Mã OTP", bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 11), anchor="w").pack(fill="x", padx=4)
        
        otp_frame = tk.Frame(parent, bg=C["bg"])
        otp_frame.pack(fill="x", padx=4, pady=(2, 8))
        
        _otp_e = tk.Entry(otp_frame, textvariable=self.lp_otp_var,
                 font=("Segoe UI", 13), bg=C["card"], fg=C["text"],
                 insertbackground=C["text"], relief="flat", width=12
                 )
        _otp_e.pack(side="left", fill="x", expand=True)
        self._vkb.attach(_otp_e)
                 
        tk.Button(otp_frame, text="Gửi mã", bg=C["accent2"], fg="white",
                  font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2",
                  command=self._do_send_otp).pack(side="right", padx=(8, 0), ipady=2, ipadx=10)

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
            _reg_e = tk.Entry(parent, textvariable=getattr(self, attr),
                     show="●" if is_pw else "",
                     font=("Segoe UI", 12), bg=C["card"], fg=C["text"],
                     insertbackground=C["text"], relief="flat",
                     )
            _reg_e.pack(fill="x", padx=4, pady=(1, 5))
            if not is_pw:   # chỉ gắn keyboard cho field text; field password dùng numpad riêng
                self._vkb.attach(_reg_e)
            else:
                self._vkb.attach(_reg_e)  # password cũng cần gõ
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
            self._skip_face_enroll,  # <-- Đổi lệnh ở đây
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
            "frame_idle", "frame_login_choose", "frame_face_mssv",
            "frame_login_pass", "frame_register", "frame_enroll_ask",
            "frame_locker", "frame_locker_menu",
        ]:
            getattr(self, attr).place_forget()

    def _go(self, state: str):
        self.state = state
        self._idle_timer = time.time()
        self._hide_all_frames()
        self._vkb.hide()   # ẩn bàn phím khi chuyển màn hình

        if state in (self.S_VERIFY_FACE, self.S_ENROLL_FACE):
            self.placeholder.place_forget()
            self.cam_canvas.place(x=20, y=65)
            self.cam.start(use_ir=(state == self.S_VERIFY_FACE))
        else:
            self.cam.stop()
            self.cam_canvas.place_forget()
            self.placeholder.place(x=20, y=65)

        if state == self.S_IDLE:
            self._current_user = None
            self._face_mssv    = None
            self._consec = 0
            self._enroll_mssv = None
            self._set_status("👋", "Xin chào!", "Chọn hành động bên dưới")
            self._set_progress(0)
            self.frame_idle.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_LOGIN_CHOOSE:
            self._set_status("🔓", "Đăng nhập", "Chọn phương thức")
            self._set_progress(0)
            self.frame_login_choose.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_FACE_MSSV:
            self.face_mssv_var.set("")
            self.face_mssv_msg.config(text="")
            self._set_status("👁", "Đăng nhập khuôn mặt", "Nhập MSSV trước")
            self._set_progress(0)
            self.frame_face_mssv.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_VERIFY_FACE:
            self._consec = 0
            self._verify_done = False
            name = self._face_mssv or ""
            self._set_status("👁", "Đang xác thực...", f"MSSV: {name} — Nhìn thẳng vào camera")
            self._set_progress(0)

        elif state == self.S_LOGIN_PASS:
            self.lp_msg.config(text="")
            self.lp_mssv_var.set("")
            self.lp_pw_var.set("")
            self.lp_otp_var.set("")
            self._current_otp = None  # Xóa mã OTP cũ (nếu có)
            self._otp_mssv = None     # Xóa MSSV xin mã cũ (nếu có)
            
            self._set_status("🔑", "Đăng nhập", "Nhập MSSV, mật khẩu và lấy OTP")
            self.frame_login_pass.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_REGISTER:
            self.reg_msg.config(text="")
            self._set_status("📝", "Đăng ký tài khoản", "Điền đầy đủ thông tin")
            self._set_progress(0)
            self.frame_register.place(x=self._px, y=self._base_y, width=self._pw)

        elif state == self.S_ENROLL_ASK:
            mssv, name = self._current_user
            self.enroll_ask_name.config(text=f"Chào {name}!")
            self._set_status("✅", "Tài khoản đã được duyệt!", "Đăng ký khuôn mặt để đăng nhập nhanh hơn")
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

    def _do_face_mssv_submit(self):
        mssv = self.face_mssv_var.get().strip()
        if not mssv:
            self.face_mssv_msg.config(text="Vui lòng nhập MSSV")
            return

        user = get_user(mssv)
        if not user:
            self.face_mssv_msg.config(text="MSSV không tồn tại — vui lòng đăng ký trước")
            return

        if not user.get("is_approved"):
            self.face_mssv_msg.config(text="Tài khoản chưa được admin duyệt")
            return

        self._face_mssv    = mssv
        self._current_user = (mssv, user["name"])

        if not user.get("has_face"):
            self._go(self.S_ENROLL_FACE)
        else:
            self._go(self.S_VERIFY_FACE)

    def _do_send_otp(self):
        """Xử lý khi người dùng nhấn nút Gửi mã OTP"""
        mssv = self.lp_mssv_var.get().strip()
        pw   = self.lp_pw_var.get()
        
        if not mssv or not pw:
            self.lp_msg.config(text="Vui lòng nhập MSSV và mật khẩu trước", fg=C["red"])
            return
            
        user = get_user_by_password(mssv, hash_password(pw))
        if not user:
            self.lp_msg.config(text="MSSV hoặc mật khẩu sai", fg=C["red"])
            return
            
        if not user.get("is_approved"):
            self.lp_msg.config(text="Tài khoản chưa duyệt", fg=C["red"])
            return
            
        email = user.get('email', '')
        if not email:
            self.lp_msg.config(text="Tài khoản của bạn chưa cập nhật Email.", fg=C["red"])
            return
            
        self.lp_msg.config(text="Đang gửi mã OTP đến email...", fg=C["text"])
        self.update() 
        
        otp_code = str(random.randint(100000, 999999))
        success = send_otp_email(email, user["name"], otp_code)
        
        if success:
            self._current_otp = otp_code
            self._otp_mssv = mssv
            self.lp_msg.config(text=f"Đã gửi OTP đến: {email}", fg=C["green"])
        else:
            self.lp_msg.config(text="Lỗi mạng. Không thể gửi OTP.", fg=C["red"])

    def _do_login_password(self):
        """Xử lý khi người dùng nhấn nút Đăng nhập"""
        mssv = self.lp_mssv_var.get().strip()
        pw   = self.lp_pw_var.get()
        entered_otp = self.lp_otp_var.get().strip()
        
        if not mssv or not pw:
            self.lp_msg.config(text="Vui lòng nhập MSSV và mật khẩu", fg=C["red"])
            return
            
        if not entered_otp:
            self.lp_msg.config(text="Vui lòng nhấn 'Gửi mã' và nhập OTP", fg=C["red"])
            return
            
        # Kiểm tra mã OTP và MSSV phải khớp với lúc gửi
        if not hasattr(self, "_current_otp") or entered_otp != self._current_otp or mssv != getattr(self, "_otp_mssv", ""):
            self.lp_msg.config(text="Mã OTP không chính xác hoặc chưa gửi!", fg=C["red"])
            return
            
        # Kiểm tra lại password lần cuối để bảo mật tuyệt đối
        user = get_user_by_password(mssv, hash_password(pw))
        if not user:
            self.lp_msg.config(text="MSSV hoặc mật khẩu sai", fg=C["red"])
            return
            
        # Đăng nhập thành công -> Xóa mã OTP đã dùng
        self._current_otp = None
        self._otp_mssv = None
        
        name = user["name"]
        self._current_user = (mssv, name)
        self._after_login(mssv, name)

    def _on_verify_frame(self, color, ir):
        if self._verify_done:
            return
        shape, det = landmarks(color)
        if not shape:
            self._set_status("👁", "Đang xác thực...", "Không thấy khuôn mặt")
            self._consec = 0
            return
        live_ok, reason = liveness(ir)
        if not live_ok:
            self._set_status("👁", "Đang xác thực...", reason)
            self._consec = 0
            return

        mssv = self._face_mssv
        if not mssv or mssv not in self.db_map:
            self._set_status("❌", "Lỗi", "Không tìm thấy dữ liệu khuôn mặt")
            self.after(2000, lambda: self._go(self.S_IDLE))
            return

        stored_emb, name = self.db_map[mssv]
        dist = np.linalg.norm(embedding(color, shape) - stored_emb)

        if dist < THRESHOLD:
            self._consec += 1
            self._set_progress(int(self._consec / VERIFY_FRAMES * 100))
            self._set_status("✅", name, f"Xác thực... {self._consec}/{VERIFY_FRAMES}")
            if self._consec >= VERIFY_FRAMES:
                self._verify_done  = True
                self._current_user = (mssv, name)
                self._after_login(mssv, name)
        else:
            self._consec = 0
            self._set_status("👁", f"MSSV: {mssv}", "Khuôn mặt không khớp — thử lại")

    def _after_login(self, mssv: str, name: str):
        user = get_user(mssv)
        if not user or not user.get("is_approved"):
            self._set_status("⏳", name, "Tài khoản chưa được admin duyệt")
            self.after(3000, lambda: self._go(self.S_IDLE))
            return

        if not user.get("has_face"):
            self._current_user = (mssv, name)
            self._go(self.S_ENROLL_ASK)
            return

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
        pw_c  = self.reg_pw_confirm_var.get()
        email = self.reg_email_var.get().strip()
        if not mssv or not name:
            self.reg_msg.config(text="Vui lòng nhập đủ thông tin")
            return
        if pw != pw_c:
            self.reg_msg.config(text="Mật khẩu nhập lại không khớp")
            return
        if len(pw) < 6:
            self.reg_msg.config(text="Pass tối thiểu 6 ký tự")
            return
        if not register_user(mssv, name, email, hash_password(pw)):
            self.reg_msg.config(text="MSSV đã tồn tại")
            return
        self._set_status(
            "⏳", "Đăng ký thành công!",
            f"Chào {name}! Chờ admin duyệt rồi đăng nhập để đăng ký khuôn mặt.",
        )
        self._set_progress(50, C["yellow"])
        self.after(4000, lambda: self._go(self.S_IDLE))

    def _start_face_enroll(self):
        self._go(self.S_ENROLL_FACE)

    def _skip_face_enroll(self):
            """Bỏ qua đăng ký khuôn mặt, tiến thẳng vào menu tủ đồ."""
            if not self._current_user:
                self._go(self.S_IDLE)
                return
                
            mssv, name = self._current_user
            lockers = get_all_lockers()
            
            # Kiểm tra xem sinh viên đã có tủ chưa (giống hệt logic ở _after_login)
            my_locker = next(
                (lid for lid, info in lockers.items()
                if info.get("current_mssv") == mssv), None,
            )
            
            if my_locker:
                self._show_locker_menu(mssv, name, my_locker, lockers)
            else:
                self._show_locker_picker(mssv, name, lockers)

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
        self.state = self.S_LOCKER_MENU
        self._idle_timer = time.time()
        self._hide_all_frames()
        self.cam.stop()
        self.cam_canvas.place_forget()
        self.placeholder.place(x=20, y=65)

        locker_info = lockers.get(locker_id, {})
        size_label  = locker_info.get("size", "").capitalize()

        for w in self.frame_locker_menu.winfo_children():
            w.destroy()

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

        self._make_big_btn(
            self.frame_locker_menu,
            "📦  GỬI ĐỒ  (Mở tủ)",
            C["accent"], "#1a2f5f",
            lambda: self._do_open_locker(mssv, name, locker_id),
        ).pack(fill="x", pady=6, ipady=18)

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
        self._current_user = (mssv, name)
        ok, msg = open_locker(mssv)
        if ok:
            self._go(self.S_SUCCESS)
        else:
            messagebox.showerror("Lỗi", f"Không thể mở tủ: {msg}")

    def _confirm_release(self, mssv: str, name: str, locker_id: str):
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
        if (self.state not in (self.S_IDLE, self.S_SUCCESS, self.S_LOCKER_MENU)
                and time.time() - self._idle_timer > IDLE_TIMEOUT):
            self._go(self.S_IDLE)

        color, ir = self.cam.get()
        if color is not None:
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
        c = hex_color.lstrip("#")
        bgr = tuple(int(c[i:i+2], 16) for i in (4, 2, 0))
        for i in range(68):
            cv2.circle(frame, (shape.part(i).x, shape.part(i).y), 2, bgr, -1)
        cv2.rectangle(frame, (det.left(), det.top()),
                      (det.right(), det.bottom()), bgr, 2)

    def _reload_db(self):
        self.db_map = load_all_embeddings()