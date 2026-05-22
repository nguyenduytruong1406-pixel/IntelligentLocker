"""
kiosk_gui.py — Entry point cho màn hình tủ kiosk.

Chạy:
    python kiosk_gui.py
"""

import subprocess
import sys
import os

import sync_listener
from core.db import migrate
from gui.kiosk_app import KioskApp

if __name__ == "__main__":
    print("[Boot] Đang đồng bộ dữ liệu...")
    subprocess.run(
        [sys.executable, "sync_tool.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    migrate()
    sync_listener.start()
    KioskApp().mainloop()