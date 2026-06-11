import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "ktv_settings.json"

DEFAULT_SETTINGS = {
    "pin": "0000",
    "next_page_index": 0,
}


def load_ktv_settings() -> dict:
    """Đọc cấu hình PIN KTV từ config/ktv_settings.json."""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_SETTINGS, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return DEFAULT_SETTINGS.copy()

    with CONFIG_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    return {
        "pin": str(data.get("pin", DEFAULT_SETTINGS["pin"])),
        "next_page_index": int(
            data.get("next_page_index", DEFAULT_SETTINGS["next_page_index"])
        ),
    }


def verify_ktv_pin(entered: str) -> tuple[bool, str]:
    settings = load_ktv_settings()
    if entered.strip() == settings["pin"]:
        return True, "Xác thực thành công"
    return False, "Mã PIN không đúng, vui lòng thử lại"
