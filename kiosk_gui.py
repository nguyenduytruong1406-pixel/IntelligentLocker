"""
kiosk_gui.py — Entry point cho màn hình tủ kiosk.

Chạy:
    python kiosk_gui.py
"""

import subprocess
import sys
import os
import threading
import time
from tkinter import messagebox

import sync_listener
from core.db import migrate
from core.locker_db import auto_cleanup_inactive
from gui.kiosk_app import KioskApp


# ── Auto-cleanup: cảnh báo tủ không dùng ─────────────────────────────────────

_warn_queue: list[dict] = []   # thread-safe buffer; drain trên main thread

def _warn_callback(mssv: str, locker_id: str, name: str, last_open: str):
    """Gọi từ background thread → đẩy vào queue, KHÔNG gọi tkinter trực tiếp."""
    _warn_queue.append({
        "mssv": mssv, "locker_id": locker_id,
        "name": name, "last_open": last_open or "chưa dùng lần nào",
    })

def _drain_warn_queue(app: KioskApp):
    """Gọi từ main thread qua app.after() để hiện popup an toàn."""
    while _warn_queue:
        w = _warn_queue.pop(0)
        messagebox.showwarning(
            "Cảnh báo — Tủ không hoạt động",
            f"Tủ {w['locker_id']} của sinh viên {w['name']} ({w['mssv']})\n"
            f"chưa sử dụng kể từ: {w['last_open']}\n\n"
            "⚠  Tủ sẽ tự động thu hồi sau 7 ngày không sử dụng.",
        )
    app.after(5_000, _drain_warn_queue, app)   # kiểm tra lại sau 5 giây

def _cleanup_loop():
    """Background thread — chạy auto-cleanup mỗi 1 giờ."""
    while True:
        try:
            result = auto_cleanup_inactive(
                warn_callback=_warn_callback,
                delete_days=7,
                warn_days=6,
            )
            if result["deleted"]:
                print(f"[AutoCleanup] Đã thu hồi {len(result['deleted'])} tủ: "
                      f"{[d['locker_id'] for d in result['deleted']]}")
            if result["warned"]:
                print(f"[AutoCleanup] Đã cảnh báo {len(result['warned'])} tủ: "
                      f"{[w['locker_id'] for w in result['warned']]}")
        except Exception as e:
            print(f"[AutoCleanup] Lỗi: {e}")
        time.sleep(3_600)   # 1 giờ


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[Boot] Đang đồng bộ dữ liệu...")
    subprocess.run(
        [sys.executable, "sync_tool.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    migrate()
    sync_listener.start()

    app = KioskApp()

    # Khởi động auto-cleanup ngay sau khi app tạo xong
    threading.Thread(target=_cleanup_loop, daemon=True).start()
    app.after(5_000, _drain_warn_queue, app)   # bắt đầu drain sau 5 giây

    app.mainloop()