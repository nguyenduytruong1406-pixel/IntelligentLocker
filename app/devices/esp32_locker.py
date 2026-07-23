"""
app/devices/esp32_locker.py — Giao tiếp Serial 2 CHIỀU với board ESP32.

Gửi xuống ESP32  : "OPEN:<so tu>\\n"    → yêu cầu mở khóa (xem main.cpp / openLock()).
                    "LIGHT:ON\\n" / "LIGHT:OFF\\n" → bật/tắt đèn hỗ trợ nhận
                    diện khuôn mặt (relay qua GPIO14).
Nhận từ ESP32    : "OPENED:<so tu>\\n"  → board xác nhận cửa ĐÃ THỰC SỰ mở, dựa
                                          vào cảm biến hành trình (xem main.cpp /
                                          updateLEDs()), KHÔNG phải chỉ vì lệnh
                                          OPEN đã gửi đi thành công.

Luồng sử dụng:
    Giao diện bấm "Mở tủ" (MO_TU)
        → SelectModeController.MO_TU()
        → LockerService.open_locker() → ESP32LockerClient.send_open(so_tu)
        → ... (ESP32 kích relay, người dùng mở cửa lấy đồ) ...
        → ESP32 phát hiện cửa mở → gửi "OPENED:xx" lên
        → ESP32LockerClient (thread đọc nền) nhận được → emit signal locker_opened(so_tu)
        → SelectModeController đang lắng nghe signal này → hiện màn hình
          "Mở tủ thành công" kèm nút OK → bấm OK mới quay về trang begin.

Việc đọc Serial chạy trên 1 thread nền riêng (không phải thread chính của Qt),
nên phải dùng pyqtSignal để đẩy an toàn qua thread GUI — không được gọi thẳng
hàm cập nhật giao diện từ thread nền.
"""

import re
import time
import threading
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import serial  # pip install pyserial
except ImportError:
    serial = None

from app.config import SERIAL_PORT, SERIAL_BAUDRATE

_OPENED_PATTERN = re.compile(r"^OPENED:(\d+)$")

# Dòng banner ESP32 in ra MỖI KHI setup() chạy — nếu dòng này xuất hiện lại
# giữa chừng (không phải lúc mới bật app) tức là ESP32 vừa TỰ RESET (thường do
# relay gây sụt áp -> brownout). Dùng để phát hiện và log cảnh báo rõ ràng.
_BOOT_BANNER = "He thong Smart Locker Twin-Bus I2C da san sang!"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class ESP32LockerClient(QObject):

    # Phát ra khi nhận được "OPENED:xx" hợp lệ từ ESP32 — tham số là số tủ (int)
    locker_opened = pyqtSignal(int)

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # Đảm bảo toàn bộ app dùng chung 1 instance (1 cổng Serial duy nhất)
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, port: str = None, baudrate: int = None, timeout: float = 0.2):
        if self._initialized:
            return
        self._initialized = True
        super().__init__()

        self.port = port or SERIAL_PORT
        self.baudrate = baudrate or SERIAL_BAUDRATE
        # Timeout NGẮN: đây là timeout đọc (readline) của thread nền, phải nhỏ
        # để thread có thể kiểm tra cờ dừng thường xuyên, không phải timeout chờ ghi.
        self.timeout = timeout

        self._ser = None
        self._io_lock = threading.Lock()
        self._reader_thread = None
        self._stop_reader = threading.Event()

        if serial is None:
            print("[ESP32] Chưa cài pyserial! Chạy: pip install pyserial")
            return

        self._connect()
        self._start_reader()

    # ── Kết nối ──────────────────────────────────────────────────────────────

    def _connect(self):
        try:
            self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"[{_ts()}] [ESP32] Đã kết nối cổng {self.port} @ {self.baudrate} baud")
        except Exception as e:
            self._ser = None
            print(f"[{_ts()}] [ESP32] Không kết nối được cổng {self.port}: {e}")

    def _ensure_connected(self) -> bool:
        if self._ser is not None and self._ser.is_open:
            return True
        self._connect()
        return self._ser is not None and self._ser.is_open

    # ── Gửi lệnh mở tủ ───────────────────────────────────────────────────────

    def send_open(self, locker_number) -> tuple[bool, str]:
        """
        Gửi lệnh mở tủ xuống ESP32, định dạng "OPEN:<2 chữ số>\\n" (vd OPEN:07).
        Trả về (thành công: bool, thông báo lỗi nếu có: str).
        LƯU Ý: trả về True chỉ có nghĩa là ĐÃ GỬI LỆNH THÀNH CÔNG, không đảm bảo
        cửa đã thực sự mở — muốn biết cửa mở thật, phải lắng nghe signal
        `locker_opened`.
        """
        try:
            locker_number = int(locker_number)
        except (TypeError, ValueError):
            return False, f"Số tủ không hợp lệ: {locker_number}"

        if not (1 <= locker_number <= 9):
            return False, f"Số tủ ngoài phạm vi cho phép (1-9): {locker_number}"

        return self._send_line(f"OPEN:{locker_number:02d}")

    # ── Bật/tắt đèn hỗ trợ nhận diện khuôn mặt (relay qua GPIO14 trên ESP32) ──

    def send_light(self, on: bool) -> tuple[bool, str]:
        """
        Bật/tắt đèn hỗ trợ nhận diện. Gửi "LIGHT:ON" hoặc "LIGHT:OFF".
        ESP32 xuất mức thấp ra GPIO14 để kích relay đèn khi nhận "LIGHT:ON".
        """
        return self._send_line("LIGHT:ON" if on else "LIGHT:OFF")

    # ── Gửi 1 dòng lệnh bất kỳ xuống ESP32 (dùng chung cho mọi lệnh) ─────────

    def _send_line(self, cmd: str) -> tuple[bool, str]:
        if serial is None:
            return False, "Chưa cài thư viện pyserial (pip install pyserial)"

        with self._io_lock:
            if not self._ensure_connected():
                return False, f"Không kết nối được board điều khiển (cổng {self.port})"

            line = f"{cmd}\n"
            try:
                self._ser.write(line.encode("utf-8"))
                self._ser.flush()
                print(f"[{_ts()}] [ESP32] Đã gửi lệnh: {cmd}")
                return True, ""
            except Exception as e:
                print(f"[{_ts()}] [ESP32] Lỗi khi gửi lệnh: {e}")
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
                return False, f"Lỗi giao tiếp Serial: {e}"

    # ── Đọc phản hồi từ ESP32 (chạy trên thread nền) ─────────────────────────

    def _start_reader(self):
        if self._reader_thread is not None:
            return
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="ESP32SerialReader"
        )
        self._reader_thread.start()

    def _reader_loop(self):
        while not self._stop_reader.is_set():
            if not self._ensure_connected():
                time.sleep(1.0)  # chưa kết nối được -> chờ rồi thử lại
                continue

            try:
                raw = self._ser.readline()  # tự trả về b"" khi hết timeout, không chặn lâu
            except Exception as e:
                print(f"[{_ts()}] [ESP32] Lỗi khi đọc Serial: {e}")
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
                continue

            if not raw:
                continue  # hết timeout, chưa có dòng dữ liệu nào mới

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            if line == _BOOT_BANNER:
                print(f"[{_ts()}] [ESP32] ⚠️  ESP32 VỪA TỰ KHỞI ĐỘNG LẠI (nhận lại banner "
                      f"boot giữa phiên làm việc) — có thể do relay gây sụt áp/brownout. "
                      f"Nếu lệnh mở tủ/đèn vừa gửi trước đó không thấy phản hồi, đây là "
                      f"nguyên nhân — kiểm tra lại nguồn cấp cho các relay.")
                continue

            match = _OPENED_PATTERN.match(line)
            if match:
                locker_number = int(match.group(1))
                print(f"[{_ts()}] [ESP32] Nhận xác nhận: OPENED:{locker_number:02d}")
                self.locker_opened.emit(locker_number)
            else:
                # Log MỌI dòng khác (log debug, lỗi lệnh...) để dễ chẩn đoán —
                # trước đây bị bỏ qua âm thầm nên không biết ESP32 có gửi gì không.
                print(f"[{_ts()}] [ESP32] (debug) Nhận: {line}")

    def close(self):
        self._stop_reader.set()
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
