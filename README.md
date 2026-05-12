# Hướng dẫn cài đặt & sử dụng

## 1. Cài thư viện

```bash
pip install face_recognition opencv-python numpy winsdk
```

> Nếu cài `face_recognition` gặp lỗi build, cài `cmake` và `dlib` trước:
> ```bash
> pip install cmake
> pip install dlib
> pip install face_recognition
> ```
> Hoặc dùng binary wheel: https://github.com/z-mahmud22/Dlib_Windows_Python3.x

---

## 2. Đăng ký khuôn mặt (chạy 1 lần)

```bash
python enroll.py
```

- Cửa sổ camera mở ra → nhìn thẳng vào camera
- Nhấn **SPACE** để chụp (cần 5 lần)
- Khung xanh = phát hiện được mặt
- Tự động lưu vào `face_db.pkl`

---

## 3. Xác thực đăng nhập

```bash
python verify.py
```

- Nhìn vào camera
- Thanh dưới cùng hiển thị độ tương đồng
- Cần khớp **3 frame liên tiếp** → PASS
- Kết quả in ra terminal: ✅ PASS hoặc ❌ FAIL

---

## 4. Tích hợp vào project của bạn

```python
from verify import verify_once, init_camera, load_db
import asyncio

async def my_login():
    db = load_db()
    mc, source = await init_camera()
    loop = asyncio.get_running_loop()
    
    ok = await verify_once(mc, source, db["owner"], loop, show_window=False)
    if ok:
        # mở session, unlock, v.v.
        pass

asyncio.run(my_login())
```

---

## 5. Tinh chỉnh độ nhạy

| Tham số | File | Mặc định | Ý nghĩa |
|---|---|---|---|
| `THRESHOLD` | verify.py | 0.45 | Nhỏ hơn = chặt hơn (0.6 = mặc định thư viện) |
| `VERIFY_FRAMES` | verify.py | 3 | Số frame liên tiếp cần khớp |
| `ENROLL_SHOTS` | enroll.py | 5 | Số ảnh dùng để tính embedding |

---

## 6. Bước tiếp theo (Hướng 2 — IR Liveness)

Sau khi Hướng 1 chạy ổn, thêm IR anti-spoofing:
- Dùng `img_ir` từ camera để kiểm tra texture mặt
- Ảnh in / màn hình phản xạ IR khác mặt người thật
- Chỉ PASS khi cả RGB khớp VÀ IR xác nhận người thật
