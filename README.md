# 📋 Claude.md — Intelligent Locker Face Recognition
> Tổng hợp toàn bộ công việc  
> Dự án: https://github.com/nguyenduytruong1406-pixel/IntelligentLocker

---

## 🗂 Cấu trúc file hiện tại (FINAL — cập nhật 22/05/2026)

```text
test_db_ver1/
├── core/                         ← Database layer (phân tách từ locker_db.py gốc thành các module nhỏ)
│   ├── __init__.py
│   ├── db.py                     ← _conn(), migrate(), constants
│   ├── user_db.py                ← register_user, get_user, load/save_embedding
│   ├── locker_db.py              ← open_locker, assign_locker, get_all_lockers
│   ├── log_db.py                 ← log_access, export_csv, rate_limit
│   └── firebase.py               ← sync_all_to_firebase, push_log
│
├── hardware/                     ← Phần cứng
│   ├── __init__.py
│   └── camera.py                 ← CameraBackend (winsdk), parse_bgr/gray
│
├── ai/                           ← AI / Face recognition
│   ├── __init__.py
│   ├── models.py                 ← Load dlib singleton (shape_pred, face_encoder)
│   ├── face_utils.py             ← Detection MediaPipe (detect_faces_bgr, center_face) — chuyển từ root vào đây
│   └── ai_utils.py               ← liveness(), landmarks(), embedding(), hash_password()
│
├── gui/                          ← Giao diện kiosk
│   ├── __init__.py
│   ├── kiosk_app.py              ← Class KioskApp (UI + state machine)
│   └── theme.py                  ← C{}, fonts, SCREEN_W/H, VERIFY_FRAMES, ...
│
├── public/                       ← Web frontend (giữ nguyên)
│   ├── landing.html              ← Trang chủ điều hướng (entry point)
│   ├── login.html                ← Đăng nhập admin
│   ├── index.html                ← Admin dashboard (4 tab)
│   ├── register.html             ← Sinh viên đăng ký tài khoản
│   ├── user-dashboard.html       ← Sinh viên tra cứu tủ
│   ├── 404.html                  ← Trang lỗi Not Found
│   
│
├── kiosk_gui.py                  ← Entry point kiosk (24 dòng, gọi KioskApp)
├── main_gui.py                   ← ⚠️ GUI tkinter nhận diện khuôn mặt ban đầu (prototype cũ) — ĐÃ được thay thế hoàn toàn bởi gui/kiosk_app.py, giữ lại để tham chiếu, KHÔNG dùng trong production
├── sync_listener.py              ← Lắng nghe Firebase realtime (Websocket Push)
├── sync_tool.py                  ← Tool đồng bộ thủ công
├── IntelligentLocker.db          ← DB chính (Users, Lockers, Logs)
├── blaze_face_short_range.tflite ← MediaPipe model
├── private_key_lockers.json      ← Service Account Key (KHÔNG commit git)
├── firebase.json / .firebaserc   ← Cấu hình Firebase Hosting



### ✅ File gốc đã xóa (22/05/2026)
| File | Thay bởi |
|---|---|
| `locker_db.py` (root) | Phân tách thành `core/db.py`, `core/user_db.py`, `core/locker_db.py`, `core/log_db.py`, `core/firebase.py` |
| `face_utils.py` (root) | Chuyển vào `ai/face_utils.py` |

### ❌ Files đã dư thừa — có thể xóa
| File | Lý do |
|---|---|
| `secure_db.py` | Thay bởi `locker_db.py` |
| `verify.py` | Thay bởi `verify_with_liveness.py` |
| `face_db.enc` | Đã migrate sang `IntelligentLocker.db` |
| `db.key` | Key cho `face_db.enc` cũ |
| `audit.db` | Log cũ → đã có LockerLog + FaceLog trong DB chính |
| `face_db_pkl.bak` | Backup file gốc ban đầu |
| `collect_liveness.py` | Chỉ dùng khi training, không cần production |
Các file liveness_check.py, enroll.py, verify_with_liveness.py đã được gộp luồng trực tiếp vào hệ thống chính để tối ưu hiệu suất.
---

## 🏗 Kiến trúc hệ thống

### Pipeline xác thực (verify_with_liveness.py)
```
Thread 1 — Camera (asyncio + winsdk)
    ↓ Frame Queue (maxsize=1, luôn frame mới nhất)
Thread 2 — AI
    • IR liveness check (liveness_check.py)
    • MediaPipe face detect (face_utils.py)
    • dlib ResNet embedding
    ↓ Result Queue (maxsize=1)
Thread 3 — UI (main thread)
    • cv2.imshow luôn ~30 FPS
    • Draw overlay + consecutive counter
    • Rate limit check
    → PASS → open_locker() → ghi LockerLog + push Firebase
```

Firebase Sync Architecture (Tối ưu Chi phí & Tốc độ)
Local → Firebase: Trực tiếp qua locker_db.py khi có sự kiện ở tủ đồ (mở/gán/trả tủ).

Firebase → Local (Realtime): Sử dụng sync_listener.py (Websocket push). Firebase tự đẩy event về Local khi Web Admin duyệt user (~0ms delay). Tuyệt đối không dùng polling để tiết kiệm tài nguyên và chi phí đọc dữ liệu.

Firebase ↔ Local (Khởi động): Sử dụng sync_tool.py để kéo/đẩy đối chiếu dữ liệu toàn diện khi hệ thống vừa khởi động lại hoặc mất mạng lâu.

### Luồng điều hướng Web
```
Truy cập web (index.html)
    → chưa login  → landing.html (3 card)
    → đã login    → index.html (dashboard)

landing.html
    → Đăng ký     → register.html
    → Admin       → login.html → index.html
    → Tra cứu     → user-dashboard.html
    → Đã login    → hiện admin bar (Vào Dashboard / Đăng xuất)
```

### Tech Stack
| Tầng | Công nghệ | Lý do chọn |
|---|---|---|
| Face Detection | Google MediaPipe BlazeFace | 5-15ms/frame trên CPU, góc rộng |
| Face Embedding | dlib ResNet 128-D | Tương thích DB hiện có |
| IR Liveness | Rule-based (mean/std) | Không cần train, không cần GPU |
| Database | SQLite (IntelligentLocker.db) | Nhẹ, offline, đủ dùng |
| Cloud Sync | Firebase Realtime DB + Admin SDK | Realtime, không cần pyrebase |
| GUI | tkinter + PIL | Có sẵn, nhẹ, mượt |
| Camera | winsdk (Windows Media Capture) | Truy cập IR camera Intel RealSense |

---

## 📐 Schema IntelligentLocker.db (FINAL)

```sql
Users (
    mssv           TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    role           TEXT DEFAULT 'student',   -- 'student' | 'admin'
    is_approved    INTEGER DEFAULT 0,        -- 0 | 1
    has_face       INTEGER DEFAULT 0,        -- 0 | 1
    face_embedding BLOB                      -- numpy array pickle'd (128-D float64)
)

Lockers (
    locker_id    TEXT PRIMARY KEY,           -- 'L01'...'L09'
    size         TEXT NOT NULL,              -- 'small' | 'big'
    status       TEXT DEFAULT 'empty',       -- 'empty' | 'occupied'
    current_mssv TEXT REFERENCES Users(mssv)
)

-- Sync lên Firebase /logs
LockerLog (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event     TEXT NOT NULL,                 -- OPEN_LOCKER | ASSIGN_LOCKER | RELEASE_LOCKER
    locker_id TEXT,
    mssv      TEXT,
    name      TEXT
)

-- Chỉ local, KHÔNG sync Firebase
FaceLog (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event     TEXT NOT NULL,                 -- FACE_REGISTER | FACE_VERIFY | FACE_FAIL
    mssv      TEXT,
    name      TEXT
)
```

> ⚠️ FaceLog trong DB thực tế còn cột `face_dist`, `live_result`, `notes` (cũ, NULL) — code mới không dùng.

---

## 🔥 Firebase Structure

```
/users/{mssv}     → name, is_approved, has_face, role, email, registered_at
/lockers/{L01}    → status, current_mssv, size, last_open_time
/logs/{push_id}   → time, event, locker_id, mssv, name
```

### Security Rules (FINAL)
```json
{
  "rules": {
    "users": {
      ".read": true,
      "$mssv": {
        ".write": "!data.exists() || auth != null"
      }
    },
    "lockers": {
      ".read": true,
      ".write": "auth != null"
    },
    "logs": {
      ".read": "auth != null",
      ".write": "auth != null"
    }
  }
}
```

**Giải thích:**
- `/users` — ai cũng đọc được (tra cứu, dashboard); chỉ tạo mới khi chưa login, sửa/xóa cần auth
- `/lockers` — ai cũng đọc được; chỉ admin ghi
- `/logs` — chỉ admin đọc/ghi

### Firebase Sync — 2 chiều
| Chiều | Trigger | Code |
|---|---|---|
| Local → Firebase | open/assign/release locker | `locker_db.py` (inline) |
| Firebase → Local | web admin duyệt user, trả tủ | `sync_listener.py` (daemon thread) |

`sync_listener.py` lắng nghe:
- `/users/{mssv}/is_approved` → `UPDATE Users SET is_approved`
- `/lockers/{lid}/status = 'empty'` → `UPDATE Lockers SET status='empty', current_mssv=NULL`

Khởi động từ `main_gui.py`:
```python
import sync_listener
sync_listener.start()   # trước mainloop()
```

---

## 🌐 Web Admin — Các trang

| Trang | Mô tả | Auth |
|---|---|---|
| `landing.html` | Entry point, điều hướng 3 portal | Không |
| `login.html` | Đăng nhập admin | Không |
| `index.html` | Dashboard: Users, Lockers, Logs, Export CSV | Bắt buộc |
| `register.html` | Sinh viên đăng ký tài khoản mới | Không |
| `user-dashboard.html` | Tra cứu tủ theo MSSV, xem tiến trình | Không |

### Tính năng Web Admin (index.html)
- Export CSV logs/users
- Dark mode toggle (Light / Dark / Device Default) — lưu localStorage
- Badge số trên icon Nhật Ký khi có log mới
- Browser notification khi sinh viên đăng ký khuôn mặt
- Material Symbols Rounded icons

### Lưu ý kỹ thuật Web
- **Chạy qua HTTP**, không mở file:// trực tiếp (Firebase Auth không hoạt động)
- Local dev: `py -m http.server 5500` → `http://localhost:5500`
- Hàm trong `<script type="module">` cần gán vào `window.xxx` để HTML inline event gọi được
- `logs` yêu cầu auth → `user-dashboard.html` bọc riêng try/catch, không block phần còn lại
# 1. Chạy Web Local
cd public
py -m http.server 5500

# 2. Đồng bộ dữ liệu toàn diện (Chỉ chạy 1 lần lúc bật máy)
py -3.11 sync_tool.py

# 3. Khởi chạy GUI tủ đồ (Tự động kích hoạt sync_listener.py chạy ngầm)
py -3.11 main_gui.py
---

## 🖥 GUI tkinter (main_gui.py) — 4 Tab

| Tab | Chức năng |
|---|---|
| 🔍 Xác thực | Camera live + IR thumbnail + verify |
| ⚙ Đăng ký | Form MSSV + camera + chụp shot + lưu embedding |
| 👥 Quản lý | Danh sách user + search + trả tủ |
| 📋 Log | LockerLog + FaceLog + filter + xuất CSV |

---

## 🐛 Lỗi đã fix

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `dlib compute_face_descriptor` TypeError | dlib 20.x đổi API | Dùng `dlib.get_face_chip()` trước |
| `mp.solutions` AttributeError | MediaPipe >= 0.10 bỏ API cũ | Dùng `mediapipe.tasks.python.vision` |
| Camera timeout `wait_both` | asyncio.Event deadlock | Đổi sang polling |
| `no such column: rfid` | DB đã bỏ rfid | Bỏ khỏi query + unpack |
| Firebase 404 Not Found | Database ở region Asia | Đổi URL sang `asia-southeast1` |
| Locker tạo thành `LL01` | `locker_id` đã là `"L01"`, code thêm `"L"` prefix | Bỏ format string thừa |
| `tab-title` null | `<h2>` thiếu `id="tab-title"` | Thêm id vào HTML |
| `lookup is not defined` | Hàm trong module không expose ra global | Đổi thành named function + `window.lookup=lookup` |
| Firebase không đọc được `/users` | Rule `$mssv.read:true` chỉ cho đọc node lẻ | Chuyển `.read:true` lên cấp `/users` |
| Web không kết nối Firebase | Chạy qua `file://` protocol | Dùng local HTTP server |
| `ModuleNotFoundError: No module named face_utils` | `ai/ai_utils.py` import kiểu root sau khi refactor | Đổi thành `from ai.face_utils import center_face` |
| `db_verify_password is not defined` | Tên hàm cũ sau khi tách `core/user_db.py` | Đổi thành `get_user_by_password()` |
| `db_register_user is not defined` | Tên hàm cũ sau khi tách `core/user_db.py` | Đổi thành `register_user()` |
| `AttributeError: pose_predictor_68_point_model_location` | Tên hàm sai trong `face_recognition_models` | Đổi thành `pose_predictor_model_location()` |
| Lambda closure bug trong locker grid picker | `lambda: assign_locker(lid)` capture `lid` của vòng lặp cuối | Đổi thành `lambda l=lid: ...` |

---

## ⚙ Cài đặt thư viện

```bash
py -3.11 -m pip install opencv-python numpy dlib mediapipe Pillow firebase-admin scikit-image scikit-learn winsdk
```

> **dlib:** Cài binary wheel từ https://github.com/z-mahmud22/Dlib_Windows_Python3.x (Python 3.11 + Windows)


## 📌 Tham số quan trọng

| Tham số | File | Giá trị | Ý nghĩa |
|---|---|---|---|
| `THRESHOLD` | verify_with_liveness.py | `0.45` | Ngưỡng khoảng cách embedding |
| `VERIFY_FRAMES` | verify_with_liveness.py | `3` | Số frame liên tiếp cần PASS |
| `MAX_FAILS` | locker_db.py | `5` | Số lần fail trước khi khóa |
| `LOCKOUT_SECS` | locker_db.py | `60` | Thời gian khóa (giây) |
| `BRIGHT_THRESHOLD` | liveness_check.py | `220` | IR mean > → FAKE |
| `DARK_THRESHOLD` | liveness_check.py | `30` | IR mean < → FAKE |
| `TEXTURE_MIN` | liveness_check.py | `8.0` | IR std < → FAKE |
| `TARGET_ENROLL_SHOTS` | main_gui.py | `5` | Số ảnh chụp khi enroll |

---

## 🗺 Bước tiếp theo

### Ưu tiên 2 — Ngắn hạn
- [ ] **Multi-user enroll**: hướng dẫn 5 góc mặt khác nhau
- [ ] **Feedback âm thanh**: beep khi PASS/FAIL
- [ ] **Xóa node LL01–LL09** trên Firebase Console (bug cũ)
- [ ] **Deploy Firebase Hosting** thay local server

### Ưu tiên 3 — Dài hạn
- [ ] **ArcFace** thay dlib ResNet (cần re-enroll)
- [ ] **Đóng gói .exe** với PyInstaller
- [ ] **REST API** (FastAPI) để web admin trigger verify

---

*Được tổng hợp bởi Claude Sonnet 4.6 — Ngày làm việc: 19–22/05/2026*


---

## 🔄 Sync Tool (sync_tool.py) — Đồng bộ 2 chiều thủ công

### Mục đích
Bổ sung cho `sync_listener.py` (realtime khi GUI đang chạy) — dùng để đối chiếu và bổ sung dữ liệu cho nhau khi 2 bên đã có thay đổi độc lập trước đó.

### Cách dùng
```bash
py -3.11 sync_tool.py          # Full sync 2 chiều (khuyến nghị khi khởi động)
py -3.11 sync_tool.py --pull   # Chỉ Firebase → SQLite
py -3.11 sync_tool.py --push   # Chỉ SQLite → Firebase
```

### Quy tắc ưu tiên
| Trường | Quyền |
|---|---|
| `name`, `is_approved`, `role` | Firebase thắng |
| Xóa tài khoản | Firebase thắng (xóa SQLite + trả tủ liên quan) |
| `has_face`, `face_embedding` | Local thắng (biometric không bị ghi đè) |
| `Lockers` status/size | SQLite → push lên Firebase |

### So sánh với sync_listener.py
| | sync_listener.py | sync_tool.py |
|---|---|---|
| Kiểu | Realtime daemon thread | Chạy 1 lần theo lệnh |
| Khi nào | GUI đang mở | Trước/sau phiên làm việc |
| Chiều | Firebase → SQLite | 2 chiều |
| Dữ liệu quá khứ | Không bắt được | ✅ Đối chiếu toàn bộ |

### Tích hợp vào main_gui.py (tùy chọn)
```python
import subprocess
subprocess.Popen(["py", "-3.11", "sync_tool.py"],
                 creationflags=subprocess.CREATE_NO_WINDOW)
```

---

## 🔄 Changelog Refactor — 22/05/2026

### Mục tiêu
Tách `kiosk_gui.py` monolith (~300 dòng) thành cấu trúc module rõ ràng để dễ bảo trì, test từng phần độc lập, và tránh import vòng tròn.

### Các bước đã thực hiện

#### Bước 4 — Tách `gui/theme.py`
- Tách toàn bộ bảng màu `C{}` (10 key), hằng số kích thước màn hình, hằng số runtime, và `make_fonts()` ra file riêng
- Mọi widget chỉ import từ đây; không hardcode màu/font ở nơi khác
- `make_fonts()` trả về dict thay vì 4 biến rời — gọi 1 lần trong `KioskApp.__init__()` sau `super().__init__()`

#### Bước 5 — Tách `gui/kiosk_app.py`
- Toàn bộ class `KioskApp` chuyển vào `gui/kiosk_app.py`
- `kiosk_gui.py` còn đúng 24 dòng: sync → `migrate()` → `sync_listener.start()` → `KioskApp().mainloop()`
- `migrate()` giữ ở entry point (side-effect khởi động hệ thống, không phải trách nhiệm UI class)

**3 bug được fix trong quá trình tách:**
1. `db_verify_password` / `db_register_user` → đổi thành `get_user_by_password()` / `register_user()` cho khớp với `core/user_db.py`
2. Lambda closure trong grid picker: `lambda: assign_locker(lid)` → `lambda l=lid: assign_locker(l)` (mọi nút đều gọi đúng tủ)
3. `_do_enroll_bg` reset state trước khi spawn thread để tránh double-trigger

#### Bước — Sửa `ai/models.py` (hardcoded path)
- Xóa đường dẫn tuyệt đối `C:\Users\ASUS\...`
- Thêm `_resolve_model_paths()` với 3 tầng ưu tiên:
  1. Biến môi trường `FACE_MODELS_DIR`
  2. Package `face_recognition_models` (dùng `pose_predictor_model_location()`)
  3. Fallback thư mục `ai/`
- Thêm `FileNotFoundError` rõ ràng thay vì crash tối nghĩa

#### Bước — Sửa `ai/face_utils.py`
- Xóa toàn bộ logic dlib (trùng với `models.py`)
- `.tflite` tìm theo thứ tự: `ai/` → root project → tự tải về root
- Chỉ còn 2 hàm public: `detect_faces_bgr()` và `center_face()`

### Import map sau refactor
```
kiosk_gui.py
    └── gui.kiosk_app.KioskApp
            ├── gui.theme          (C, SCREEN_W/H, CAM_W/H, VERIFY_FRAMES, ...)
            ├── hardware.camera    (CameraBackend)
            ├── ai.ai_utils        (liveness, landmarks, embedding, hash_password)
            │       ├── ai.models  (shape_pred, face_encoder)
            │       └── ai.face_utils (center_face)
            ├── core.user_db       (get_user_by_password, register_user, get_user,
            │                       load_all_embeddings, save_embedding)
            ├── core.locker_db     (open_locker, assign_locker, get_all_lockers)
            └── core.log_db        (log_access)
```

### Thư mục/file đã xóa sau refactor
| Đường dẫn | Lý do |
|---|---|
| `locker_db.py` (root) ✅ | Đã vào `core/locker_db.py` |
| `face_utils.py` (root) ✅ | Đã vào `ai/face_utils.py` |
| `download_file/` | File tải về tạm thời, không thuộc source |
| `File backup/` | Backup thủ công cũ |
| `file test database/` | Test data lẻ |
| `file test faceid/` | Test ảnh khuôn mặt |

*Cập nhật bởi Claude Sonnet 4.6 — 22/05/2026*