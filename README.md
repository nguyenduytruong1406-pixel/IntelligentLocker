# 🔐 IntelligentLocker — Smart Locker với nhận diện khuôn mặt

> Hệ thống quản lý tủ đồ thông minh cho Makerspace HCMUTE  
> Kiosk nhận diện khuôn mặt · Web Admin · Đồng bộ Firebase realtime  
> 🔗 https://github.com/nguyenduytruong1406-pixel/IntelligentLocker

---

## 🚀 Quickstart

```bash
# 1. Cài thư viện Python
py -3.11 -m pip install PyQt6 opencv-python numpy dlib mediapipe \
    firebase-admin scikit-image python-dotenv winsdk

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
│   │   ├── cleanup_service.py           ← Thu hồi tủ idle, pending expire
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
│   ├── landing.html                     ← Entry point (3 portal)
│   ├── login.html                       ← Đăng nhập admin
│   ├── index.html                       ← Admin dashboard (5 tab)
│   ├── register.html                    ← Sinh viên đăng ký tài khoản
│   ├── user-dashboard.html              ← Sinh viên tra cứu tủ + yêu cầu trả tủ (OTP)
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
  └─ nhập MSSV ──────────────────────────────────► LoginController
                                                        │
                                              AuthMethodController
                                              ┌──────────┴──────────┐
                                         Khuôn mặt            Mật khẩu
                                              │                     │
                                        FaceController      PasswordController
                                        (mode=auth)               │
                                         ┌────┴────┐              │
                                    has_face    no_face           │
                                         │          │             │
                                    xác thực    FaceController    │
                                    khuôn mặt  (mode=register)   │
                                         │                        │
                                         └──────────┬─────────────┘
                                                    ▼
                                           SelectModeController
                                           ┌────────┴────────┐
                                      Chưa có tủ        Đã có tủ
                                           │                 │
                                  SelectLockerController  ┌──┴──┐
                                  (chọn tủ trống)       Mở   Trả
                                           │             tủ    tủ
                                     gán tủ → open
```

### Pipeline AI (FaceWorker — QThread)

```
QThread FaceWorker.run()
    │
    camera.get() → (color, ir)
    │
    recog_frame = ir_to_bgr(ir)  ưu tiên IR · fallback color nếu IR chưa sẵn sàng
    │
    ├─ [mode=register]
    │       center_face(recog_frame) → landmarks() → embedding()  (chạy trên IR)
    │       liveness(ir) chỉ cần 1 frame REAL, không gate chặt
    │       Thu thập ENROLL_FRAMES=10 → np.mean() → register_done.emit()
    │
    └─ [mode=auth]
            center_face(recog_frame)
                │
                ├─ liveness(ir) — rolling window LIVENESS_WINDOW=7 frame
                │   cần ≥ LIVENESS_MIN_OK frame REAL trong window gần nhất
                │   (thay cho yêu cầu liên tiếp cũ — chịu nhiễu môi trường tốt hơn)
                │
                ├─ landmarks(recog_frame) → embedding(recog_frame, shape)
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
   Lắng nghe: /users · /lockers · /otp_requests · /verify_attempts

Firebase ◄──────────────────────────────────────► SQLite
   (sync_tool.py — chạy 1 lần khi boot hoặc sau mất mạng)
```

### Luồng OTP trả tủ (server-side verify)

```
Web client              Firebase              sync_listener.py
    │                      │                        │
    │── otp_requests/{m} ──►│                        │
    │                      │──── on_otp_request ───►│
    │                      │                        │ sinh OTP
    │                      │                        │ lưu SHA-256(OTP) → otp_tokens
    │                      │                        │ gửi OTP gốc qua email
    │                      │                        │
    │  [user nhập OTP]     │                        │
    │── verify_attempts ───►│                        │
    │                      │──── on_verify_attempt ►│
    │                      │                        │ so sánh hash
    │                      │                        │ rate limit (max 5 lần)
    │                      │◄── verify_results ─────│
    │◄── onValue ──────────│                        │
    │   {ok, reason}       │                        │
```

> Client **không bao giờ đọc** `otp_tokens` — chỉ server biết hash.

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
      ├─► Ghi /users/{mssv} (is_approved:1, has_face:false)
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
landing.html
  ├─► register.html       (sinh viên đăng ký)
  ├─► login.html          (admin)
  │     └─► index.html    (dashboard 5 tab)
  └─► user-dashboard.html (tra cứu tủ, yêu cầu trả tủ)
```

---

## 🌐 Web Admin

### Các trang

| Trang | Mô tả | Auth |
|---|---|---|
| `landing.html` | Entry point — điều hướng 3 portal | Không |
| `login.html` | Đăng nhập admin | Không |
| `index.html` | Dashboard admin (6 tab) | Bắt buộc |
| `register.html` | *(Không còn dùng trong luồng chính)* — đăng ký đã chuyển sang Google Form + QR tại Kiosk | Không |
| `user-dashboard.html` | Tra cứu tủ, idle warning, yêu cầu trả tủ | Không |

### 6 Tab trong index.html

| Tab | Nội dung |
|---|---|
| 🏠 Trang Chủ | 5 stat cards: Đã duyệt · Chờ duyệt · Tủ trống · Tủ đang dùng · **Kiosk status** |
| 👥 Sinh Viên | Bảng users · tìm kiếm · duyệt/khóa · gán tủ · xóa thẻ thủ công |
| 🗄 Tủ | Sơ đồ tủ realtime · gán/trả thủ công |
| 🔄 Trả Tủ | Bảng yêu cầu trả tủ pending · xác nhận trả |
| 📋 Lịch Sử | Log LOCKER_DELETE_LOG · search · export CSV |
| 📝 Đơn Đăng Ký | Đơn từ Google Form (`locker_requests`) · tìm theo MSSV/tên · nút "➕ Thêm tài khoản" cấp tài khoản sau khi đã nhận đơn giấy ký tay |

---

## 🗄 Database Schema (SQLite)

```sql
Users (
    mssv          TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,         -- SHA-256
    is_approved   INTEGER DEFAULT 0,     -- 0 | 1
    has_face      INTEGER DEFAULT 0,     -- 0 | 1
    face_embedding BLOB,                 -- pickle(np.ndarray 128-D)
    role          TEXT DEFAULT 'student',
    email         TEXT DEFAULT ''
)

Lockers (
    locker_id     TEXT PRIMARY KEY,      -- 'L01'...'L09'
    size          TEXT NOT NULL,         -- 'small' | 'big'
    status        TEXT DEFAULT 'empty',  -- 'empty' | 'occupied'
    current_mssv  TEXT REFERENCES Users(mssv),
    assigned_date TEXT DEFAULT '',       -- 'YYYY-MM-DD HH:MM:SS' | ''
    last_open     TEXT DEFAULT ''        -- 'YYYY-MM-DD HH:MM:SS' | ''
)

LockerLog (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event     TEXT NOT NULL,             -- OPEN_LOCKER | ASSIGN_LOCKER | RELEASE_LOCKER
    locker_id TEXT REFERENCES Lockers(locker_id),
    mssv      TEXT,
    name      TEXT
)

LOCKER_DELETE_LOG (
    ID          INTEGER PRIMARY KEY AUTOINCREMENT,
    MSSV        TEXT NOT NULL,
    LOCKER_ID   TEXT NOT NULL,
    DELETE_TIME TEXT NOT NULL,
    REASON      TEXT NOT NULL            -- student_release | auto_inactive_7days
)                                        -- | admin_force | admin_deactivate
                                         -- | admin_delete_card | auto_expired_pending
```

---

## 🔥 Firebase Structure

```
/users/{mssv}                    → name, is_approved, has_face, role, email, registered_at
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
```

### Security Rules (cập nhật 09/07/2026)

```json
{
  "rules": {
    "users": {
      ".read": "auth != null",
      ".write": "auth != null",
      "$mssv": {
        ".read": true,
        ".write": "auth != null || !data.exists()"
      }
    },
    "lockers":           { ".read": true, ".write": "auth != null" },
    "logs":              { ".read": "auth != null", ".write": "auth != null" },
    "locker_delete_logs":{ ".read": "auth != null", ".write": "auth != null" },
    "kiosk_status":      { ".read": true, ".write": "auth != null" },
    "release_requests": {
      ".read": "auth != null",
      "$mssv": { ".read": true, ".write": true }
    },
    "locker_requests": {
      ".read": "auth != null",
      ".write": "auth != null"
    },
    "otp_requests":  { "$mssv": { ".read": "auth != null", ".write": true } },
    "otp_tokens":    { "$mssv": { ".read": "auth != null", ".write": "auth != null" } },
    "verify_attempts":{ "$mssv": { ".read": "auth != null", ".write": true } },
    "verify_results": { "$mssv": { ".read": true, ".write": "auth != null" } }
  }
}
```

> Ghi chú: Google Apps Script ghi `locker_requests` bằng **Bearer token của Service Account** (Firebase Admin SDK qua OAuth2) — Admin SDK **luôn bỏ qua toàn bộ Security Rules** theo mặc định, nên dù rule yêu cầu `auth != null`, Apps Script vẫn ghi được bình thường. Rule `auth != null` ở đây chỉ áp dụng cho client Web thông thường (admin đã đăng nhập qua Firebase Auth mới đọc/duyệt được đơn).

### Sync Rules ưu tiên

| Trường | Quy tắc |
|---|---|
| `name`, `is_approved`, `role` | Firebase thắng |
| `has_face`, `face_embedding` | Local thắng (biometric không bị ghi đè từ web) |
| `Lockers.last_open` | Lấy giá trị **mới hơn** (ISO string compare) |
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
| `LIVENESS_MIN_OK` | `face_worker.py` | `2` | Số frame REAL tối thiểu trong window để pass (auth) |
| `ENROLL_FRAMES` | `face_worker.py` | `10` | Số frame thu thập khi đăng ký mặt |
| `MAX_FAILS` | `face_worker.py` | `5` | Số lần fail trước khi lockout |
| `LOCKOUT_SECS` | `face_worker.py` | `60` | Thời gian lockout (giây) |
| `KIOSK_ONLINE_SECS` | `user-dashboard.html` | `90` | last_seen < 90s → Kiosk ONLINE |
| `OTP_MAX_ATTEMPTS` | `sync_listener.py` | `5` | Số lần thử OTP sai tối đa |
| `PENDING_EXPIRE_DAYS` | `cleanup_service.py` | `7` | Ngày tự xóa tài khoản chờ duyệt |
| `PENDING_WARN_DAYS` | `cleanup_service.py` | `2` | Ngày gửi mail cảnh báo trước khi xóa |

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

> Chi tiết từng thay đổi xem tại [`CHANGELOG.md`](./CHANGELOG.md)

---

*Smart Locker — HCMUTE Makerspace · Python 3.11 · Firebase Realtime DB*