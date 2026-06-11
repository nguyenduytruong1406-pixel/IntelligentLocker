"""
app/paths.py — Quản lý đường dẫn tập trung.

Tất cả path đều là absolute, tính từ vị trí file này.
Import module này thay vì hardcode string "app/..." ở bất kỳ đâu.

Dùng:
    from app.paths import UI, ASSETS, GIF, QSS, CONFIG
    uic.loadUi(UI("LOGIN.ui"), self)
    open(QSS("locker.qss"))
    QUrl.fromLocalFile(GIF("success.mp4"))
"""

from pathlib import Path

# Root của project = thư mục cha của app/
ROOT = Path(__file__).resolve().parent.parent   # .../SML/
APP  = ROOT / "app"


# ── Helpers ────────────────────────────────────────────────────────────────────
def UI(filename: str) -> str:
    """app/ui/<filename>  →  absolute path string"""
    return str(APP / "ui" / filename)

def ASSETS(filename: str) -> str:
    """app/assets/<filename>  →  absolute path string"""
    return str(APP / "assets" / filename)

def GIF(filename: str) -> str:
    """app/assets/gif/<filename>  →  absolute path string"""
    return str(APP / "assets" / "gif" / filename)

def QSS(filename: str) -> str:
    """app/assets/styles/<filename>  →  absolute path string"""
    return str(APP / "assets" / "styles" / filename)

def CONFIG(filename: str) -> str:
    """config/<filename>  →  absolute path string"""
    return str(ROOT / "config" / filename)

def AI_MODEL(filename: str) -> str:
    """<filename> ở root project  →  absolute path string (cho .tflite, .dat)"""
    return str(ROOT / filename)


# ── Video idle — tìm tự động ──────────────────────────────────────────────────
def find_video() -> str | None:
    """Tìm file video idle theo thứ tự ưu tiên. Trả None nếu không có."""
    candidates = [
        APP  / "assets" / "gif" / "video.mp4",
        APP  / "assets" / "gif" / "Success.mp4",
        APP  / "assets" / "gif" / "success.mp4",
        ROOT / "video.mp4",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None
