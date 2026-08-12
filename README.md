# 🔐 IntelligentLocker — Smart Locker với nhận diện khuôn mặt

> Hệ thống quản lý tủ đồ thông minh cho Makerspace HCMUTE  
> Kiosk nhận diện khuôn mặt · Web Admin · Đồng bộ Firebase realtime  
> 🔗 https://github.com/nguyenduytruong1406-pixel/IntelligentLocker

---

## 🚀 Quickstart

```bash
# 1. Cài thư viện Python
# 1. Cài dlib TRƯỚC bằng wheel dựng sẵn (KHÔNG để pip tự build từ source —
#    sẽ lỗi "Failed building wheel for dlib" trên Windows do thiếu cmake/
#    Visual Studio Build Tools)
py -3.11 -m pip install dlib-bin

# 2. Cài các thư viện còn lại
py -3.11 -m pip install PyQt6 opencv-python numpy mediapipe  
py -3.11 -m pip install firebase-admin scikit-image python-dotenv winsdk
py -3.11 -m pip install face_recognition_models 
# 2. Tạo file môi trường
cp .env.example app_password.env
# → Điền MAIL_SENDER, MAIL_PASSWORD, MAIL_SENDER_NAME

# 3. Khởi động Kiosk (tự chạy sync_tool + sync_listener ngầm)
py -3.11 main.py

# 4. Chạy Web Admin local (tab riêng)
cd public
py -m http.server 5500
# → Mở http://localhost:5500
```

> **dlib trên Windows:** Cài binary wheel tại  
> https://github.com/z-mahmud22/Dlib_Windows_Python3.x (Python 3.11)

---

## 🗂 Cấu trúc dự án

```text
SML/
├── app/
│   ├── controllers/                     ← Tầng UI (PyQt6 QMainWindow)
│   │   ├── begin_controller.py          ← Màn hình chờ (idle)
│   │   ├── login_controller.py          ← Đăng nhập bằng MSSV
│   │   ├── register_controller.py       ← Đăng ký tài khoản sinh viên
│   │   ├── auth_method_controller.py    ← Chọn phương thức xác thực (mặt / mật khẩu)
│   │   ├── face_controller.py           ← Giao diện camera (auth + register mode)
│   │   ├── face_worker.py               ← QThread AI pipeline (liveness · landmark · embed)
│   │   ├── password_controller.py       ← Xác thực bằng mật khẩu
│   │   ├── select_mode.py               ← Menu sau đăng nhập (Mở tủ / Trả tủ / Chọn tủ)
│   │   ├── select_locker_controller.py  ← Giao diện chọn tủ trống
│   │   ├── send_otp_controller.py       ← Gửi OTP qua email
│   │   ├── enter_otp_controller.py      ← Nhập và xác minh OTP
│   │   ├── service_controller.py        ← Màn hình dịch vụ
│   │   ├── menu_service.py              ← Menu dịch vụ
│   │   ├── loading_controller.py        ← Màn hình loading
│   │   └── success_controller.py        ← Màn hình thành công
│   │
│   ├── database/
│   │   ├── database.py                  ← migrate(), kết nối SQLite
│   │   ├── user_repository.py           ← CRUD users, save/load embedding
│   │   └── locker_repository.py         ← CRUD lockers, log
│   │
│   ├── services/
│   │   ├── auth_service.py              ← Xác thực, lưu embedding, get_name_user
│   │   ├── locker_service.py            ← open/assign/return/check_user_has_locker
│   │   ├── cleanup_service.py           ← Cảnh báo + thu hồi tủ (idle, hết hạn — 4 giai đoạn)
│   │   └── firebase_hooks.py            ← Push thay đổi lên Firebase
│   │
│   ├── utils/
│   │   ├── session.py                   ← Session.current_user, Session.user_name
│   │   └── ktv_config.py                ← Cấu hình KTV
│   │
│   └── widgets/
│       ├── virtual_keyboard.py          ← Bàn phím ảo cảm ứng QWERTY
│       ├── locker_button.py             ← Widget nút tủ (sơ đồ tủ)
│       ├── touch_scroll_area.py         ← ScrollArea hỗ trợ cảm ứng
│       └── keyboard_manager.py          ← Quản lý focus bàn phím
│
├── hardware/
│   └── camera.py                        ← CameraBackend (winsdk IR + color)
│
├── ai/
│   ├── models.py                        ← Load dlib singleton (shape_pred, face_encoder)
│   ├── face_utils.py                    ← MediaPipe detect, center_face
│   └── ai_utils.py                      ← liveness(), landmarks(), embedding(), ir_to_bgr()
│
├── public/                              ← Web frontend (giữ nguyên từ backup)
│   ├── login.html                       ← Đăng nhập admin (entry point)
│   ├── index.html                       ← Admin dashboard (5 tab)
│   ├── emailjs_config.js                ← EmailJS credentials (KHÔNG commit git)
│   └── 404.html
│
├── main.py                              ← Entry point — migrate DB + sync + PyQt6 app
├── sync_listener.py                     ← Firebase Websocket listener (realtime)
├── sync_tool.py                         ← Đồng bộ 2 chiều thủ công
├── IntelligentLocker.db                 ← SQLite DB chính
├── blaze_face_short_range.tflite        ← MediaPipe model
├── app_password.env                     ← Gmail credentials (KHÔNG commit git)
└── private_key_lockers.json             ← Firebase Service Account (KHÔNG commit git)
```

---

## 🏗 Kiến trúc hệ thống

### Kiosk Stack Index (QStackedWidget)

| Index | Controller | Màn hình |
|---|---|---|
| 0 | `BeginController` | Màn hình chờ (idle) |
| 1 | `LoginController` | Nhập MSSV |
| 2 | `RegisterController` | Đăng ký tài khoản |
| 3 | `SelectModeController` | Menu Mở tủ / Trả tủ |
| 4 | `SelectLockerController` | Chọn tủ trống |
| 5 | `LoadingController` | Loading |
| 6 | `SuccessController` | Thành công |
| 7 | `VideoScreenController` | Video giới thiệu |
| 8 | `AuthMethodController` | Chọn xác thực (mặt / mật khẩu) |
| 9 | `PassWordController` | Nhập mật khẩu |
| 11 | `SendEmailController` | Gửi OTP |
| 12 | `EnterOtpController` | Nhập OTP |
| 13 | `ServiceController` | Dịch vụ |
| 14 | `MenuServiceController` | Menu dịch vụ |
| 15 | `FaceController` | Camera xác thực / đăng ký khuôn mặt |

### Luồng điều hướng Kiosk

```
BeginController (Idle)
  └─ đăng nhập (MSSV + mật khẩu) ──────────────────► LoginController
                                                            │
                                            is_first_login? ──có──► ChangePassController
                                                            │không
                                            có tủ chưa?  ──chưa──► báo lỗi, ở lại Login
                                                            │có
                                                  AuthMethodController
                                                  ┌──────────┴──────────┐
                                             Khuôn mặt                 OTP
                                                  │                      │
                                            FaceController         SendOtpController
                                            (mode=auth)                  │
                                             ┌────┴────┐          EnterOtpController
                                        has_face    no_face              │
                                             │          │                │
                                        xác thực    FaceController       │
                                        khuôn mặt   (mode=register)      │
                                             │          │                │
                                             └──────────┴───────┬────────┘
                                                                 ▼
                                                       SelectModeController
                                                       ┌────────┴────────┐
                                                  Chưa có tủ         Đã có tủ
                                                       │                  │
                                            Ẩn nút Mở/Trả, báo         ┌──┴──┐
                                            liên hệ admin cấp tủ     Mở   Trả
                                            (tự chọn tủ đã bỏ —      tủ    tủ
                                             admin cấp sẵn khi duyệt đơn)
```

> **Lưu ý:** Đăng nhập yêu cầu **cả MSSV lẫn mật khẩu** (`LoginController.login_account()` gọi `auth_service.mssv_pass(user, pw)`), không phải chỉ MSSV. `AuthMethodController` là lớp xác thực **thứ hai**, cho chọn giữa **khuôn mặt hoặc OTP** — không còn lựa chọn "mật khẩu" ở bước này (`PasswordController` đã bị loại khỏi luồng, xem comment trong `auth_method_controller.py`). Nhánh "chưa có tủ" cũng không còn dẫn tới `SelectLockerController` — mô hình tự chọn tủ đã được thay bằng admin cấp tủ sẵn khi duyệt đơn đăng ký (xem `select_mode.py::_update_buttons()`).

### Pipeline AI (FaceWorker — QThread)

```
QThread FaceWorker.run()
    │
    camera.get() → (color, ir)
    │
    recog_frame = ir_to_bgr(ir)  ưu tiên IR · fallback color nếu IR chưa sẵn sàng
    │
    ├─ center_face(recog_frame)
    │       không thấy mặt → box_lost_streak++ · chỉ reset liveness/confirm
    │       khi mất box đủ BOX_LOST_GRACE frame liên tiếp (chịu chập chờn detect)
    │
    ├─ [mode=register]
    │       landmarks() → embedding()  (chạy trên IR)
    │       liveness(ir) chỉ cần 1 frame REAL, không gate chặt
    │       _pose_ok(shape) — bỏ frame nghiêng quá (POSE_MAX_OFFSET), không tính vào ENROLL_FRAMES
    │       Thu thập ENROLL_FRAMES=10 → np.mean() → register_done.emit()
    │
    └─ [mode=auth]
            │
            ├─ liveness(ir) — rolling window LIVENESS_WINDOW=7 frame
            │   cần ≥ LIVENESS_MIN_OK frame REAL trong window gần nhất
            │   (thay cho yêu cầu liên tiếp cũ — chịu nhiễu môi trường tốt hơn)
            │
            ├─ landmarks(recog_frame) → _pose_ok(shape) → embedding(recog_frame, shape)
            │   nghiêng quá (POSE_MAX_OFFSET) → bỏ qua frame, không tính fail/không reset liveness
            │
            └─ So sánh L2 với known_embeddings
               MATCH_THRESHOLD=0.45, CONFIRM_FRAMES=3
               → auth_success.emit(mssv, name)
```

**Lý do chuyển sang IR cho nhận diện (không chỉ liveness):**
Ảnh màu (RGB) phụ thuộc ánh sáng môi trường — trong điều kiện thiếu sáng (Makerspace ban đêm, đèn không đều), embedding tính từ RGB kém ổn định, `best_dist` dao động lớn dẫn đến false reject. IR illuminator phát sáng riêng, không phụ thuộc ánh sáng phòng, nên ảnh IR đồng nhất hơn giữa lúc enroll và lúc verify.

**`ir_to_bgr()` (`ai/ai_utils.py`):** convert IR grayscale (H, W) → BGR giả (H, W, 3) bằng `cv2.cvtColor(..., COLOR_GRAY2BGR)` — 3 channel giống nhau, đủ để dlib/MediaPipe hoạt động vì các model này chỉ cần cấu trúc hình học và độ tương phản, không cần màu thật.

> **Lưu ý migration:** embedding train trên RGB (cũ) và embedding train trên IR (mới) không tương thích — nằm trong domain khác nhau dù cùng 1 người. Sau khi deploy bản IR, cần xóa `face_embedding` cũ trong DB (`UPDATE users SET face_embedding = NULL, has_face = 0`) và enroll lại toàn bộ user.


### Firebase Sync Architecture

```
Kiosk / SQLite ──────────────────────────────────► Firebase
   (firebase_hooks.py — inline khi open/assign/release)

Firebase ────────────────────────────────────────► SQLite
   (sync_listener.py — Websocket push, ~0ms delay)
   Lắng nghe: /users · /lockers · /otp_requests · /verify_attempts ·
              /pending_credentials · /locker_delete_logs

Firebase ◄──────────────────────────────────────► SQLite
   (sync_tool.py — chạy 1 lần khi boot hoặc sau mất mạng)
```

> **`/locker_delete_logs` (từ 25/07/2026):** trước đây chỉ 1 chiều (Kiosk ghi
> SQLite `LOCKER_DELETE_LOG` rồi đẩy lên Firebase) — log tạo từ Web (admin ép
> trả, xóa thẻ, gán tủ từ web, `sync_auto_fix`) chỉ nằm trên Firebase, SQLite
> local của Kiosk không bao giờ có. Giờ đồng bộ 2 chiều: `sync_tool.py` (lúc
> boot) kéo bù toàn bộ lịch sử cũ, `sync_listener.py` (`on_delete_log_added`)
> đồng bộ realtime các log mới phát sinh trong lúc Kiosk đang chạy. Dedup theo
> bộ (MSSV, LOCKER_ID, DELETE_TIME, REASON), không cần lưu Firebase push-key.

> **Reconnect watchdog + catch-up (từ 31/07/2026):** trước đây các listener
> `.listen()` chỉ đăng ký đúng 1 lần lúc boot — mất mạng (lúc khởi động hoặc
> giữa lúc chạy) làm thread nền chết âm thầm, sync "biến mất" cho tới khi
> restart app. `sync_listener.py` giờ có `_watchdog_loop()` (daemon, mỗi 20s)
> tự phát hiện + đăng ký lại listener chết. Mỗi lần vừa khôi phục sau mất
> mạng, tự chạy thêm 2 bước bù (vì `.listen()` chỉ báo sự kiện *mới* kể từ
> lúc reconnect, không "phát lại" những gì đã xảy ra lúc offline):
> - `sync_tool.py --sync` (subprocess riêng) — bù `users`/`lockers`/
>   `locker_delete_logs` bị lỡ.
> - `_catchup_pending_credentials()` — quét lại toàn bộ `pending_credentials`
>   còn treo, gửi mail mật khẩu bị lỡ lúc offline (khác `sync_tool.py`,
>   không xử lý node này).


### Luồng đăng ký tài khoản mới (QR → Google Form → PDF ký tay → admin duyệt)

**Thay đổi mô hình (từ 09/07/2026):** Sinh viên không còn tự đăng ký trực tiếp trên Kiosk/Web nữa. Quy trình mới:

```
Sinh viên quét QR tại Kiosk
      │
      ▼
Điền Google Form (thông tin nhóm, MSSV, GVHD, kích thước tủ...)
      │
      ▼
Google Apps Script (Trigger: On form submit)
      │
      ├─► Tạo file PDF "Đơn xin mượn tủ" từ template Google Docs
      ├─► Gửi PDF qua email cho trưởng nhóm
      └─► Đẩy dữ liệu lên Firebase /locker_requests/{mssv} (status: "pending")
                (qua OAuth2 Service Account — Bearer token, không lộ quyền ghi)
      │
      ▼
Sinh viên in PDF, xin đủ chữ ký (thành viên + GVHD)
      │
      ▼
Nộp bản giấy cho quản lý Makerspace
      │
      ▼
Admin vào Web Dashboard → tab "Đơn Đăng Ký" → tìm theo MSSV/tên
      │
      ▼
Bấm "➕ Thêm tài khoản" (chỉ sau khi đã kiểm tra đơn giấy)
      │
      ├─► Ghi /users/{mssv} (has_face:false)
      └─► Đánh dấu /locker_requests/{mssv}.status = "approved" (giữ lại lịch sử)
      │
      ▼
sync_listener.py (on_user_change — đã có sẵn, lắng nghe /users) bắt sự kiện
      │
      ├─► Đẩy user mới xuống SQLite kiosk ngay lập tức (realtime)
      └─► Gửi mail "Tài khoản đã được duyệt" cho sinh viên
      │
      ▼
Sinh viên ra Kiosk, nhập MSSV → has_face=false → tự động vào luồng enroll khuôn mặt
```

**Vì sao tách `locker_requests` khỏi `users`:** sinh viên vừa điền form chỉ nằm ở `locker_requests` với `status: "pending"` — không được tạo trong `/users`, nên **không thể thao tác gì ở Kiosk** cho tới khi admin xác nhận đã nhận đủ chữ ký và bấm duyệt thủ công. Điều này giữ nguyên tính chặt chẽ của hệ thống phần cứng: chỉ tài khoản đã qua duyệt giấy mới vào được `/users`.

**Bảo mật ghi Firebase từ Apps Script:** Private Key của Service Account **không hardcode trong code** — được lưu trong Script Properties của Apps Script (`PropertiesService.getScriptProperties()`), chỉ đọc ra lúc runtime để tạo Access Token (Bearer) gọi REST API Firebase.

### Luồng điều hướng Web

```
login.html (entry point, admin)
  └─► index.html (dashboard 6 tab)
```

> Đăng ký sinh viên đã chuyển sang Google Form + QR tại Kiosk. Landing page 3-portal, `register.html` và `user-dashboard.html` đã bị loại bỏ khỏi luồng chính.

---

## 🌐 Web Admin

### Các trang

| Trang | Mô tả | Auth |
|---|---|---|
| `login.html` | Đăng nhập admin (entry point) | Không |
| `index.html` | Dashboard admin (6 tab) | Bắt buộc |

> **Phiên đăng nhập (từ 25/07/2026):** dùng `setPersistence(auth,
> browserSessionPersistence)` thay vì mặc định `browserLocalPersistence` của
> Firebase Auth. Trước đây phiên lưu vĩnh viễn trong trình duyệt — vào thẳng
> `index.html` (bookmark/URL cũ) sẽ tự động vào dashboard mà không qua
> `login.html`, kể cả sau khi đóng trình duyệt rất lâu. Giờ đóng trình
> duyệt/tab là mất phiên, lần sau bắt buộc đăng nhập lại. Áp dụng ở cả
> `login.html` và `index.html` (đồng nhất, đề phòng phiên cũ kiểu local còn sót).

### 6 Tab trong index.html

| Tab | Nội dung |
|---|---|
| 🏠 Trang Chủ | 5 stat cards: Đã duyệt · Chờ duyệt · Tủ trống · Tủ đang dùng · **Kiosk status** |
| 👥 Sinh Viên | Bảng users · tìm kiếm · duyệt/khóa · gán tủ · xóa thẻ thủ công |
| 🗄 Tủ | Sơ đồ tủ realtime · gán/trả thủ công |
| 📋 Lịch Sử | Log LOCKER_DELETE_LOG · search · export CSV |
| 📝 Đơn Đăng Ký | Đơn từ Google Form (`locker_requests`) · tìm theo MSSV/tên · nút "➕ Thêm tài khoản" cấp tài khoản sau khi đã nhận đơn giấy ký tay |

---

## 🗄 Database Schema (SQLite)

> Nguồn sự thật duy nhất là dict `SCHEMA` trong `app/database/database.py` — bảng dưới
> đây chỉ là bản phản ánh lại để đọc nhanh. Đổi cấu trúc DB thì sửa ở đó rồi chạy
> lại file, không sửa tay ở đây.

```sql
Users (
    mssv               TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    has_face           INTEGER NOT NULL DEFAULT 0,   -- 0 | 1
    face_embedding     BLOB,                         -- pickle(np.ndarray 128-D)
    password           TEXT,                         -- hash SHA-256
    email              TEXT NOT NULL DEFAULT '',
    locker_expiry_date TEXT NOT NULL DEFAULT '',      -- hạn mượn tủ tối đa, từ đơn đăng ký
    OTP                NUMERIC,
    is_first_login     INTEGER NOT NULL DEFAULT 1     -- 1 = chưa đổi mật khẩu random do admin cấp
)

Lockers (
    locker_id        TEXT PRIMARY KEY,      -- 'L01'...'L09'
    size             TEXT NOT NULL,         -- 'small' | 'big'
    status           TEXT NOT NULL DEFAULT 'empty',  -- 'empty' | 'occupied'
    current_mssv     TEXT REFERENCES Users(mssv) ON DELETE SET NULL,
    assigned_date    TEXT,                  -- 'YYYY-MM-DD HH:MM:SS' | '' | NULL
    last_open        TEXT,                  -- 'YYYY-MM-DD HH:MM:SS' | NULL
    idle_warned_at   TEXT DEFAULT NULL,     -- đã cảnh báo idle (ngày 14) cho lượt mượn hiện tại chưa
    expiry_warned_at TEXT DEFAULT NULL      -- đã cảnh báo sắp hết hạn (trước 2 ngày) chưa
)                                           -- cả 2 cột *_warned_at reset về NULL khi BORROW/RETURN;
                                            -- idle_warned_at còn reset khi OPEN (mở tủ = hết idle)

LockerLog (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    event          TEXT NOT NULL,             -- OPEN_LOCKER
    locker_id      TEXT REFERENCES Lockers(locker_id),
    mssv           TEXT,
    name           TEXT,
    door_closed_at TEXT DEFAULT NULL,     -- ESP32 xác nhận cửa đã đóng thật (CLOSED:xx) cho lượt mở này
    warned_door    TEXT DEFAULT NULL      -- đã gửi mail cảnh báo quên đóng tủ cho lượt mở này chưa
)                                         -- local-only — không đồng bộ lên Firebase, xem Sync Rules

FaceLog (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event     TEXT NOT NULL,
    mssv      TEXT,
    name      TEXT
)

LOCKER_DELETE_LOG (
    ID          INTEGER PRIMARY KEY AUTOINCREMENT,
    MSSV        TEXT NOT NULL,
    LOCKER_ID   TEXT NOT NULL,
    DELETE_TIME TEXT NOT NULL,
    REASON      TEXT NOT NULL            -- student_release | auto_idle_locker | auto_expired
)                                        -- | admin_force | admin_delete_card
                                         -- | sync_auto_fix  ngoài ra còn new_assignment do được đồng bộ từ web
```

> **Đã bỏ khỏi `Users`** (từng có ở bản cũ, không còn dùng): `role`, `is_approved`,
> `registered_at`, `warned_at`, `account_status`, `last_active_time`. Các cột này
> thuộc về khái niệm "chờ duyệt" và luồng "cảnh báo idle phiên đăng nhập" (2h/5h)
> kiểu SML cũ — cả hai đã bị bỏ.
>
> **Cleanup hiện tại xử lý ở cấp tủ, 4 giai đoạn** (`cleanup_service.py`, chạy qua
> `CleanupWorker` mỗi 60s — xem `main.py`):
>
> | Giai đoạn | Điều kiện | Hành động |
> |---|---|---|
> | `cleanup_idle_warning` | không mở tủ ≥ `IDLE_WARN_DAYS` (14) ngày, chưa cảnh báo | gửi mail, đánh dấu `idle_warned_at` |
> | `cleanup_idle_lockers` | không mở tủ ≥ `IDLE_REVOKE_DAYS` (16) ngày | **thu hồi thật** (`auto_idle_locker`) |
> | `cleanup_expiry_warning` | còn ≤ `EXPIRY_WARN_DAYS` (2) ngày tới `locker_expiry_date`, chưa cảnh báo | gửi mail, đánh dấu `expiry_warned_at` |
> | `cleanup_expired_lockers` | đã qua `locker_expiry_date` | **thu hồi thật** (`auto_expired`) |
>
> Cả 2 mốc thu hồi thật đều không phụ thuộc đã cảnh báo hay chưa — tới hạn cứng là
> thu hồi. Nếu 1 tủ vừa idle quá hạn vừa hết hạn mượn cùng lúc, `cleanup_idle_lockers`
> chạy trước sẽ thu hồi trước nên không bị xử lý/gửi mail 2 lần.
>
> **Tủ mới cấp nhưng chưa từng mở cũng được tính vào idle:** `set_status_locker()`
> (`locker_repository.py`, chạy lúc admin duyệt đơn / BORROW) set `last_open = now`
> ngay tại thời điểm cấp tủ, không để `NULL`. Vì `get_lockers_needing_idle_warning()`
> / `get_idle_lockers()` đều tính mốc idle dựa trên `last_open`, nên nếu sinh viên
> được cấp tủ nhưng không bao giờ ra kiosk mở tủ lần nào, đồng hồ idle vẫn tự chạy
> từ đúng thời điểm cấp — sau `IDLE_WARN_DAYS` (14 ngày) sẽ nhận cảnh báo, sau
> `IDLE_REVOKE_DAYS` (16 ngày) sẽ bị thu hồi, y hệt một tủ đã dùng rồi bỏ quên.
> Không cần cơ chế riêng cho trường hợp "cấp tủ lần đầu không dùng" — nó tự động
> rơi vào đúng luồng cảnh báo/thu hồi idle sẵn có.
>
> **Cảnh báo quên đóng tủ** (`door_closed_at`/`warned_door` ở `LockerLog`, timer nền
> riêng, kiểm tra mỗi 1 phút): khi mở tủ ghi 3 điều kiện — đã mở > 5 phút, chưa
> nhận tín hiệu `CLOSED:xx` từ ESP32 (`door_closed_at` còn NULL), chưa gửi mail
> (`warned_door` còn NULL) — thì gửi mail sinh viên và đánh dấu `warned_door`. Sau
> 15 phút kể từ lúc đánh dấu mà vẫn chưa đóng thì gửi thêm mail cho quản lý tủ.
>
> **`Service_engineer_log`** (log kỹ thuật viên) không còn được `database.py`
> quản lý (không tự tạo/sửa cột nữa) — nếu DB cũ còn bảng này thì vẫn giữ nguyên,
> chỉ là không có schema chính thức cho nó nữa.
>
> **`current_mssv` giờ là `ON DELETE SET NULL`** — xoá một `Users` sẽ tự trả tủ
> của người đó về trống thay vì bị chặn bởi lỗi `FOREIGN KEY constraint failed`.

---

## 🔥 Firebase Structure

```
/users/{mssv}                    → name, has_face, email
/lockers/{L01}                   → status, current_mssv, size, last_open, assigned_date
/logs/{push_id}                  → time, event, locker_id, mssv, name
/locker_delete_logs/{push_id}    → mssv, locker_id, delete_time, reason
/release_requests/{mssv}         → mssv, locker_id, requested_at, status
/locker_requests/{mssv}          → mssv, name, email, khoa, size_requested,
                                    requested_at, status ("pending"|"approved"), approved_at
                                    (ghi bởi Google Apps Script qua OAuth2 Bearer token)
/kiosk_status/last_seen          → ISO timestamp (heartbeat mỗi 30s)
/kiosk_status/connected          → bool
/otp_requests/{mssv}             → email, name, requested (web → kiosk)
/otp_tokens/{mssv}               → hashed_code, expires_at, attempts (kiosk only)
/verify_attempts/{mssv}          → code, ts (web → kiosk)
/verify_results/{mssv}           → ok, reason, ts (kiosk → web)
/pending_credentials/{mssv}      → password, locker_id, expiry_date, created_at
                                    (web ghi lúc cấp tài khoản nếu Kiosk online;
                                    sync_listener.py đọc, gửi mail, rồi tự xóa node)
/credential_email_log/{mssv}     → locker_id, expiry_date, sent_via
                                    ("kiosk_sync_listener"|"emailjs_offline"), sent_at
                                    (audit — web dùng để hiện trạng thái cột "Gửi Mail")
```

### Security Rules (cập nhật 23/07/2026 — siết toàn bộ về `auth != null`)

```json
{
  "rules": {
    "users": {
      ".read": "auth != null",
      ".write": "auth != null",
      "$mssv": {
        ".read": "auth != null",
        ".write": "auth != null"
      }
    },
    "lockers":           { ".read": "auth != null", ".write": "auth != null" },
    "logs":              { ".read": "auth != null", ".write": "auth != null" },
    "locker_delete_logs":{ ".read": "auth != null", ".write": "auth != null" },
    "kiosk_status":      { ".read": "auth != null", ".write": "auth != null" },
    "release_requests": {
      ".read": "auth != null",
      "$mssv": { ".read": "auth != null", ".write": "auth != null" }
    },
    "locker_requests": {
      ".read": "auth != null",
      ".write": "auth != null"
    },
    "otp_requests":  { "$mssv": { ".read": "auth != null", ".write": "auth != null" } },
    "otp_tokens":    { "$mssv": { ".read": "auth != null", ".write": "auth != null" } },
    "verify_attempts":{ "$mssv": { ".read": "auth != null", ".write": "auth != null" } },
    "verify_results": { "$mssv": { ".read": "auth != null", ".write": "auth != null" } }
  }
}
```

> **Vì sao siết:** các rule public (`.read: true` / `.write: true`) trước đây tồn tại riêng để `register.html` (tự tạo tài khoản không cần đăng nhập) và `user-dashboard.html` (tra cứu tủ, gửi OTP, yêu cầu trả tủ không cần đăng nhập) hoạt động. Hai file này đã bị xóa khỏi luồng chính (xem CHANGELOG 23/07/2026) và không còn trang web nào cần truy cập ẩn danh. Kiosk (`main.py`, `sync_listener.py`, `sync_tool.py`) và Google Apps Script đều ghi qua **Service Account (Firebase Admin SDK)**, luôn bỏ qua Security Rules, nên không bị ảnh hưởng bởi việc siết `auth != null`. Rule `auth != null` giờ chỉ áp dụng cho client Web (admin đã đăng nhập qua `login.html`).

### Sync Rules ưu tiên

| Trường | Quy tắc |
|---|---|
| `name` | Firebase thắng |
| `has_face`, `face_embedding` | Local thắng (biometric không bị ghi đè từ web) |
| `Lockers.last_open` | Lấy giá trị **mới hơn** (ISO string compare) |
| `LockerLog.door_closed_at`, `warned_door` | Local-only — không đồng bộ lên Firebase (trạng thái ESP32/timer chỉ có ý nghĩa tại chỗ) |
| Xóa tài khoản | Firebase thắng → xóa SQLite + trả tủ liên quan |

---

## ⚙️ Cấu hình

### app_password.env

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `MAIL_SENDER` | Không | Gmail dùng để gửi OTP và mail thông báo |
| `MAIL_PASSWORD` | Không | Gmail App Password (16 ký tự) |
| `MAIL_SENDER_NAME` | Không | Tên hiển thị trong email |

> Nếu chưa cấu hình → tính năng mail tắt im lặng, hệ thống vẫn hoạt động bình thường.

### emailjs_config.js (public/)

```js
window.EMAILJS_CONFIG = {
  publicKey : "YOUR_PUBLIC_KEY",
  serviceId : "YOUR_SERVICE_ID",
  templateId: "YOUR_TEMPLATE_ID"
};
```

> Dùng làm fallback gửi OTP khi Kiosk offline (`last_seen > 90s`).

### .gitignore

```
app_password.env
private_key_lockers.json
emailjs_config.js
.warn_flags/
IntelligentLocker.db
```

---

## 📌 Tham số quan trọng

| Tham số | Module | Giá trị | Ý nghĩa |
|---|---|---|---|
| `MATCH_THRESHOLD` | `face_worker.py` | `0.45` | Ngưỡng L2 distance embedding |
| `CONFIRM_FRAMES` | `face_worker.py` | `3` | Số frame liên tiếp match mới xác nhận |
| `LIVENESS_WINDOW` | `face_worker.py` | `7` | Số frame gần nhất để xét liveness (rolling window) |
| `LIVENESS_MIN_OK` | `face_worker.py` | `4` | Số frame REAL tối thiểu trong window để pass (auth) |
| `ENROLL_FRAMES` | `face_worker.py` | `10` | Số frame thu thập khi đăng ký mặt |
| `BOX_LOST_GRACE` | `face_worker.py` | `3` | Số frame liên tiếp không thấy mặt trước khi reset liveness/confirm (chịu detect chập chờn) |
| `POSE_MAX_OFFSET` | `face_worker.py` | `0.35` | Lệch mũi/tâm 2 mắt (tỉ lệ theo khoảng cách 2 mắt) — vượt ngưỡng coi là nghiêng quá, bỏ qua embedding/match |
| `MAX_FAILS` | `face_worker.py` | `20` | Số lần fail trước khi lockout |
| `LOCKOUT_SECS` | `face_worker.py` | `60` | Thời gian lockout (giây) — lưu ở `Session.face_lockout` (keyed theo mssv), không phải biến local nên vẫn còn hiệu lực dù thoát/vào lại trang camera |
| `OTP_MAX_ATTEMPTS` | `sync_listener.py` | `5` | Số lần thử OTP sai tối đa |
| `IDLE_WARN_DAYS` | `cleanup_service.py` | `14` | Số ngày tủ không mở trước khi gửi mail cảnh báo (`cleanup_idle_warning`) |
| `IDLE_REVOKE_DAYS` | `cleanup_service.py` | `16` | Số ngày tủ không mở trước khi tự thu hồi (`cleanup_idle_lockers`) |
| `EXPIRY_WARN_DAYS` | `cleanup_service.py` | `2` | Số ngày trước `locker_expiry_date` để gửi mail cảnh báo (`cleanup_expiry_warning`) |
| `DOOR_CHECK_INTERVAL` | *(door-warning timer)* | `1 phút` | Chu kỳ quét tủ mở quá lâu chưa đóng |
| `DOOR_OPEN_WARN_MINUTES` | *(door-warning timer)* | `5 phút` | Thời gian mở tủ tối đa trước khi bị coi là quên đóng, gửi mail sinh viên |
| `DOOR_MANAGER_ESCALATE_MINUTES` | *(door-warning timer)* | `15 phút` | Thời gian tính từ lúc gửi mail sinh viên mà vẫn chưa đóng → gửi thêm mail quản lý tủ |

---

## 🔄 Sync Tool

```bash
py -3.11 sync_tool.py           # Full sync 2 chiều (chạy tự động khi main.py start)
py -3.11 sync_tool.py --pull    # Chỉ Firebase → SQLite
py -3.11 sync_tool.py --push    # Chỉ SQLite → Firebase
```

| | `sync_listener.py` | `sync_tool.py` |
|---|---|---|
| Kiểu | Realtime daemon (Websocket) | Chạy 1 lần theo lệnh |
| Khi nào dùng | Luôn chạy cùng Kiosk | Lúc boot / sau mất mạng lâu |
| Chiều | Firebase → SQLite | 2 chiều |
| Bắt dữ liệu quá khứ | ❌ | ✅ |

---

## 🛠 Tech Stack

| Tầng | Công nghệ | Lý do chọn |
|---|---|---|
| GUI Kiosk | **PyQt6** + QStackedWidget | Native, thread-safe signals, dễ tích hợp AI |
| Face Detection | Google MediaPipe BlazeFace | 5–15ms/frame trên CPU, góc rộng |
| Face Embedding | dlib ResNet 128-D | Tương thích DB hiện có, threshold 0.45 |
| IR Liveness | Rule-based (mean/std) | Không cần train, không cần GPU |
| Database | SQLite | Nhẹ, hoạt động offline |
| Cloud Sync | Firebase Realtime DB + Admin SDK | Realtime push, không cần pyrebase |
| Camera | winsdk (Windows Media Capture) | Truy cập IR stream Intel RealSense |
| OTP Email | Gmail SMTP (primary) + EmailJS (fallback) | Không cần backend server |
| Hardware | Waveshare 7" 1024×600 cảm ứng | Màn hình kiosk nhúng |
| Đăng ký tài khoản | Google Forms + Google Apps Script (serverless) | Không cần backend riêng, tự xuất PDF + gửi mail + ghi Firebase qua Trigger "On form submit" |

---

## 🐛 Known Issues & Limitations

| Hạn chế | Chi tiết |
|---|---|
| Windows only | `winsdk` chỉ hỗ trợ Windows — không chạy được trên Linux/macOS |
| 9 tủ cố định | `L01–L09` hardcode trong DB seed; mở rộng cần sửa migration |
| 1 kiosk | Kiến trúc hiện tại giả định 1 kiosk duy nhất |
| Offline EmailJS | OTP mode offline sinh code phía client — kém bảo mật hơn online mode |

---

## 📅 Changelog tóm tắt

| Ngày | Nội dung |
|---|---|
| 19–27/05 | Khởi tạo dự án, refactor module hóa, face enroll/verify pipeline (Tkinter) |
| 27/05 | Thêm Trả tủ (S_LOCKER_MENU), auto-cleanup 7 ngày, LOCKER_DELETE_LOG |
| 28/05 | Web: xóa thẻ thủ công, auto-expire pending, modal Cài Đặt tập trung |
| 29/05 | Pending expire daemon, gửi mail warning, sync `last_open` 2 chiều |
| 03/06 | 2FA OTP email khi đăng nhập kiosk, fix JS Date Trap, fix Firebase rules |
| 04/06 | Fix đồng bộ `assigned_date`/`last_open`, heartbeat kiosk, bàn phím ảo 1024×600 |
| 05/06 | Kiosk status realtime trên admin, OTP trả tủ server-side verify (SHA-256 hash) |
| 10/06 | **Migrate GUI Tkinter → PyQt6** · FaceWorker QThread · multi-frame enroll (10 frames) · fix `select_mode` check has_locker · fix `save_embedding` return value |
| 17/06 | **Chuyển nhận diện sang IR** (`ir_to_bgr()`) thay RGB · liveness rolling-window (7 frame, ≥2 REAL) thay liên tiếp · fix false-reject trong điều kiện thiếu sáng |
| 09/07 | **Đổi mô hình đăng ký tài khoản**: QR tại Kiosk → Google Form → PDF xin chữ ký GVHD → admin duyệt thủ công · thêm node Firebase `locker_requests` · thêm tab Web "Đơn Đăng Ký" (tìm kiếm + cấp tài khoản) · Google Apps Script tự xuất PDF + gửi mail + ghi Firebase qua OAuth2 Service Account · fix rò rỉ private key (chuyển sang Script Properties) |
| 22/07 | **Fix lockout xác thực khuôn mặt không có tác dụng thật**: `lockout_until` được gán nhưng không bao giờ đọc lại → chuyển sang lưu ở `Session.face_lockout` (theo mssv, sống ngoài vòng đời `FaceWorker`) · dừng hẳn worker + tự quay về màn chọn hình thức xác thực khi bị khóa (`lockout_active` signal) thay vì chờ tại chỗ · fix `UnboundLocalError` do import `Session` cục bộ thừa làm shadow biến module-level |
| 25/07 | **Web Admin — hàng loạt fix nhỏ đi kèm cảnh báo/thu hồi 4 giai đoạn**: `index.html` — fix `delete_time` lệch giờ UTC (`toISOString()`) và sai định dạng `vi-VN` không sort được → đồng nhất `toLocaleString('sv-SE')` (giờ VN, sortable); `_reasonMap` khớp đúng reason thật + bỏ field chết; login/dashboard đổi `browserSessionPersistence`; nhãn "Gửi Mail" phân biệt Kiosk/EmailJS · `sync_listener.py` — ghi `credential_email_log` khi Kiosk tự gửi mật khẩu (trước đây không ghi, cột "Gửi Mail" luôn trống); thêm listener `on_delete_log_added` đồng bộ realtime `locker_delete_logs` Firebase → SQLite · `sync_tool.py` — thêm `pull_delete_logs()` kéo bù lịch sử cũ lúc boot, `_RELEASE_REASONS` bổ sung `admin_force`/`auto_idle_locker`/`auto_expired` (trước chỉ có `student_release`) · **`face_worker.py`** — thêm `BOX_LOST_GRACE` (không reset liveness/confirm khi mất box chỉ 1 frame chập chờn) và `_pose_ok()` pose gate (bỏ qua embedding/match khi mặt nghiêng quá `POSE_MAX_OFFSET`, tránh cộng oan `fail_count`); thử rồi revert CLAHE + tỉ lệ std/mean trong `ai_utils.liveness()` (vấn đề thực tế không nằm ở ngưỡng liveness) |
| 31/07 | **`sync_listener.py` — tự khôi phục sau mất mạng**: fix root cause (thread nền SSE chết âm thầm khi reconnect thất bại lúc mạng vẫn chưa có, không log/không tự phục hồi) · thêm `_watchdog_loop()` (daemon, 20s) tự đăng ký lại listener chết · sau khi khôi phục, tự chạy `sync_tool.py --sync` (subprocess) bù `users`/`lockers`/`locker_delete_logs` bị lỡ · thêm `_catchup_pending_credentials()` quét lại `pending_credentials` còn treo, gửi mail mật khẩu bị lỡ lúc offline (node này `sync_tool.py` không xử lý) · fix `UnicodeEncodeError` (cp1252) khi subprocess con in ký tự `✅/✗/⚠` trên Windows — ép `PYTHONIOENCODING=utf-8` |
| 05/08 | Fix `sync_tool.py::pull_lockers()` — tủ trả/xóa trên Firebase (`status='empty'`, `last_open` đã xóa) nhưng SQLite local còn `last_open` cũ: logic cũ luôn lấy `max(local, firebase)`, mà chuỗi rỗng luôn "nhỏ hơn" nên giữ nhầm giá trị cũ, rồi `push()` kế tiếp đẩy ngược giá trị rác đó lên lại Firebase — giờ khi Firebase báo `empty` thì xóa thẳng `last_open`, không so sánh, khớp đúng logic `on_locker_change()` bên `sync_listener.py` · **Cảnh báo quên đóng tủ**: thêm `door_closed_at`/`warned_door` vào `LockerLog` (`app/database/database.py`), migrate tự động qua `ensure_schema()` |

> Chi tiết từng thay đổi xem tại [`CHANGELOG.md`](./CHANGELOG.md)

---

*Smart Locker — HCMUTE Makerspace · Python 3.11 · Firebase Realtime DB*