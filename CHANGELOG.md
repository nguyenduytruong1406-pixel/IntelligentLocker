# 📅 CHANGELOG — IntelligentLocker

Toàn bộ lịch sử thay đổi theo ngày, mới nhất ở trên.

---

## [17/06/2026] — Chuyển face recognition sang IR · Fix liveness rolling-window

### 🌓 Nhận diện khuôn mặt: RGB → IR

**Vấn đề:** Pipeline cũ chỉ dùng IR cho liveness check, còn `landmarks()` + `embedding()` chạy trên frame màu (RGB/color). Trong điều kiện thiếu sáng (Makerspace ban đêm, ánh sáng không đều), ảnh màu mờ và thiếu chi tiết → embedding kém ổn định → `best_dist` tăng cao → false reject dù đúng người.

**Giải pháp:** Camera của kiosk có sẵn 2 sensor riêng trong cùng cụm (`IR Camera` + `USB2.0 FHD UVC WebCam`, cùng `MediaFrameSourceGroup`). IR illuminator phát sáng riêng, không phụ thuộc ánh sáng phòng → ảnh đồng nhất hơn nhiều giữa các lần chụp.

**`ai/ai_utils.py` — thêm `ir_to_bgr()`:**
```python
def ir_to_bgr(ir_img: np.ndarray) -> np.ndarray:
    """Convert IR grayscale (H,W) → BGR giả (H,W,3) để feed vào dlib/MediaPipe."""
    return cv2.cvtColor(ir_img, cv2.COLOR_GRAY2BGR)
```
3 channel giống nhau vẫn đủ cho dlib 68-landmark và MediaPipe BlazeFace hoạt động — cả 2 model chỉ cần cấu trúc hình học và độ tương phản, không phụ thuộc màu thật.

**`app/controllers/face_worker.py` — đổi nguồn frame cho recognition:**
```python
color, ir = self._camera.get()

if ir is not None:
    recog_frame = ir_to_bgr(ir)     # ưu tiên IR
elif color is not None:
    recog_frame = color              # fallback nếu IR chưa sẵn sàng
```
- `center_face()`, `landmarks()`, `embedding()` đều chạy trên `recog_frame` (IR khi có)
- `liveness()` vẫn chạy trên `ir` gốc (grayscale thật, không qua `ir_to_bgr`)
- UI preview (`frame_ready`) vẫn emit `color` để người dùng thấy ảnh tự nhiên — chỉ pipeline AI chạy trên IR, không đổi gì về mặt hiển thị

> ⚠️ **Breaking change cho dữ liệu cũ:** embedding train trên RGB và embedding train trên IR nằm trong domain khác nhau — không so khớp được dù cùng 1 người. Sau khi deploy, chạy `UPDATE users SET face_embedding = NULL, has_face = 0` rồi enroll lại toàn bộ user.

### 🐛 Fix liveness gate — rolling window thay liên tiếp

**Vấn đề:** `LIVENESS_FRAMES=5` yêu cầu 5 frame liveness REAL **liên tiếp**. Trong môi trường thực tế (đèn nền dao động, góc mặt thay đổi nhẹ), IR liveness check fail rải rác 1 frame mỗi vài frame → counter liên tục bị reset về 0 → không bao giờ đạt 5, auth không bao giờ chạy tới bước match dù liveness tổng thể tốt (qua quan sát log: `REAL` chiếm > 90% frame nhưng counter mãi dao động 1↔2).

**Giải pháp — đổi sang rolling window (`collections.deque`):**
```python
LIVENESS_WINDOW  = 7    # số frame gần nhất để xét
LIVENESS_MIN_OK  = 2    # cần ít nhất 2/7 frame REAL trong window

liveness_window = deque(maxlen=LIVENESS_WINDOW)
...
liveness_window.append(live_ok)
ok_count = liveness_window.count(True)

if self.mode == "auth" and ok_count < LIVENESS_MIN_OK:
    continue   # chưa đủ tỉ lệ REAL trong window gần nhất, không reset toàn bộ
```
Một vài frame fail rải rác (ánh sáng nhiễu, chớp mắt) không còn xóa sạch tiến độ — chỉ cần tỉ lệ REAL đủ trong window trượt gần nhất. Bảo mật thực tế vẫn dựa vào `MATCH_THRESHOLD` + `CONFIRM_FRAMES` ở bước embedding, liveness chỉ là gate sơ bộ chống ảnh phẳng/màn hình.

**UI hiển thị tiến độ rõ hơn:** `liveness_status` emit kèm tỉ lệ, ví dụ `✅ REAL (4/7)` thay vì chỉ `✅ REAL`.

---

## [10/06/2026] — Migrate GUI Tkinter → PyQt6 · Fix face enroll/verify

### 🖥 Migrate toàn bộ Kiosk GUI từ Tkinter sang PyQt6

**Kiến trúc mới (`SML/`):**

```
main.py  ←  Entry point duy nhất
  ├─ migrate DB + Firebase init
  ├─ sync_tool.py --sync (subprocess)
  ├─ sync_listener.start()
  └─ QApplication + QStackedWidget (17 màn hình)
```

**Controllers mới (thay thế state machine Tkinter):**

| Controller | Màn hình |
|---|---|
| `BeginController` | Idle |
| `LoginController` | Nhập MSSV |
| `RegisterController` | Đăng ký tài khoản |
| `AuthMethodController` | Chọn xác thực (mặt / mật khẩu) |
| `FaceController` | Camera auth + register (cùng widget, đổi mode) |
| `FaceWorker` (QThread) | AI pipeline tách biệt hoàn toàn khỏi GUI thread |
| `SelectModeController` | Menu sau đăng nhập |
| `SelectLockerController` | Chọn tủ trống (sơ đồ tủ) |
| `PassWordController` | Xác thực mật khẩu |
| `SendEmailController` | Gửi OTP |
| `EnterOtpController` | Nhập OTP |

---

### 🤖 FaceWorker — AI pipeline cải tiến

**File:** `app/controllers/face_worker.py`

**Multi-frame enroll (thay vì 1 frame cũ):**
- Thu thập `ENROLL_FRAMES=10` embedding liên tiếp
- Tính `np.mean()` → embedding chất lượng cao hơn, ít nhiễu
- Signal mới `enroll_progress(int, int)` — hiển thị tiến độ `📸 3/10`

**Tách liveness theo mode:**
- `mode="register"` — **bỏ qua** `LIVENESS_FRAMES` gate (camera bật `use_ir=True`, liveness vẫn chạy nhưng không chặn)
- `mode="auth"` — phải đạt đủ 5 frame liveness OK liên tiếp mới bắt đầu match

**Guard `has_face` đầu `run()`:**
- Kiểm tra `user["has_face"]` từ DB ngay trước khi bật camera
- `no_face_registered.emit()` → `FaceController` redirect sang register tự động
- Tránh bypass qua `auth_method_controller`

**Signals:**
```python
frame_ready        = pyqtSignal(object)     # np.ndarray BGR
face_detected      = pyqtSignal(bool)
liveness_status    = pyqtSignal(bool, str)
auth_success       = pyqtSignal(str, str)   # mssv, name
auth_failed        = pyqtSignal(str)
register_done      = pyqtSignal(object)     # avg embedding (10 frames)
enroll_progress    = pyqtSignal(int, int)   # current, total
face_log           = pyqtSignal(str, str, str)
no_face_registered = pyqtSignal()
```

---

### 🐛 Bug fixes

**`user_repository.save_embedding()` — không có `return`:**
- Cũ: hàm lưu thành công vào DB nhưng không `return True` → `auth_service` nhận `None` → UI báo "❌ Lưu thất bại" dù đã lưu xong
- Fix: thêm `return True` / `return False` trong try/except

**`sqlite3.Row.get()` không tồn tại:**
- Cũ: `user.get("has_face")` → `AttributeError` âm thầm → check bypass
- Fix: đổi thành `user["has_face"]` ở tất cả chỗ

**`select_mode.py` — không check trạng thái tủ khi vào màn hình:**
- Cũ: sau đăng nhập luôn hiện menu Mở tủ + Trả tủ dù chưa có tủ
- Fix: thêm `showEvent()` → `check_user_has_locker()`:
  - Chưa có tủ → `go_to_select_locker()` ngay lập tức
  - Đã có tủ → hiện Mở tủ + Trả tủ bình thường

**`auth_method_controller.go_to_face()` — mode check:**
- Đã dùng `user["has_face"]` đúng (fix cùng với `sqlite3.Row` bug)

## [05/06/2026] — OTP trả tủ server-side · Kiosk Status realtime

### 🔐 Bảo mật OTP — Server-side verify (sync_listener.py + user-dashboard.html)

**Vấn đề cũ:** Client đọc `otp_tokens` trực tiếp từ Firebase để so sánh — bất kỳ ai biết MSSV đều có thể đọc mã OTP.

**Kiến trúc mới:**

```
Web client → /otp_requests/{mssv}
sync_listener → sinh OTP → lưu SHA-256(OTP) vào /otp_tokens → gửi code gốc qua mail
Web client → /verify_attempts/{mssv} (ghi code nhập vào)
sync_listener → so hash → ghi kết quả vào /verify_results/{mssv}
Web client → onValue /verify_results → nhận {ok, reason}
```

**Thay đổi `sync_listener.py`:**
- `on_otp_request()` — lưu `hashed_code = SHA-256(code)` thay vì code gốc; thêm field `attempts: 0`
- `on_verify_attempt()` — handler mới lắng nghe `/verify_attempts/{mssv}`:
  - Rate limit: tối đa 5 lần thử sai → hủy token
  - Kiểm tra hết hạn server-side
  - Ghi kết quả `{ok, reason, ts}` vào `/verify_results/{mssv}`
  - Tự dọn `verify_attempts` và `verify_results` (sau 15s) sau khi xử lý
- Thêm `import hashlib`
- `start()` — đăng ký thêm listener `verify_attempts`

**Thay đổi `user-dashboard.html`:**
- `confirmReleaseOtp()` online mode — không còn đọc `otp_tokens`; ghi vào `verify_attempts`, lắng nghe `verify_results` với timeout 10s
- Thêm `attemptTs` để lọc kết quả cũ (tránh `onValue` fire ngay với data từ lần trước)
- `_onOtpVerified()` — tách ra hàm riêng, dùng chung cho online và offline mode
- `closeReleaseModal()` — hủy `_verifyUnsub`
- Bỏ tất cả `remove(ref(db, 'verify_results/...'))` phía client

**Firebase Rules — thêm 3 node mới:**
```json
"otp_tokens":      { "$mssv": { ".read": "auth != null", ".write": "auth != null" } },
"verify_attempts": { "$mssv": { ".read": "auth != null", ".write": true } },
"verify_results":  { "$mssv": { ".read": true,           ".write": "auth != null" } }
```

---

### 📡 Kiosk Status realtime (index.html)

**Stat card "Kiosk" (Home tab):**
- Card thứ 5 trong stats-grid
- Dot xanh/đỏ + text "Online" / "Offline" + dòng "last seen: Xs trước"
- Viền card đổi màu tương ứng
- Logic: Online nếu `connected=true` **hoặc** `last_seen < 90 giây`

**Badge trên header:**
- "Kiosk Online 🟢" / "Kiosk Offline 🔴" — hiển thị trên mọi tab

**Stat card "Yêu cầu trả tủ":**
- Số pending realtime, màu vàng, animation pulse khi có pending
- Click vào card → chuyển sang tab Trả Tủ
- Toast + Browser notification khi count tăng (không fire lúc load trang lần đầu)

---

## [04/06/2026] — Fix đồng bộ tủ · Bàn phím ảo 1024×600

### 🔧 Fix đồng bộ assigned_date / last_open (sync_tool.py + sync_listener.py)

**Mục tiêu:** Sửa triệt để mất field khi sync Firebase ↔ SQLite.

**`sync_tool.py`:**
- `get_sqlite_lockers()` — thêm `assigned_date` vào SELECT (trước bỏ sót)
- `push()` lockers — đổi `.set()` → `.update()` để không xóa field ngoài payload
- Thêm `assigned_date` vào payload; merge `last_open` lấy giá trị mới hơn
- Nhánh FIX LOCKER — thêm `assigned_date: ''` khi reset tủ đã trả

**`sync_listener.py` — `on_locker_change()`:**
- Đảo thứ tự: check `status='empty'` trước, sync `last_open` sau
- Thêm `assigned_date=NULL, last_open=NULL` vào UPDATE khi reset tủ
- `return` sớm sau khi reset — tránh sync `last_open` cũ vào tủ vừa trả

**`core/locker_db.py`:**
- `release_locker()` — thêm `last_open=NULL` vào UPDATE

**`index.html`:**

| Hàm | Fix |
|---|---|
| `confirmAssignLocker()` | Đổi `last_open_time` → `last_open`, format ISO |
| `releaseUserLocker()` | Thêm `last_open:'', last_open_time:''` + ghi `admin_force` log |
| `handleRelease()` | Thêm `last_open:'', last_open_time:''` |
| `deleteCard()` | Thêm `last_open:'', last_open_time:''` |
| `autoExpirePendingCards()` | Thêm `last_open:'', last_open_time:''` |
| Render grid | Đọc `last_open \|\| last_open_time` — tương thích ngược |

**Quy ước `last_open` chuẩn hóa:**

| Nguồn | Format |
|---|---|
| Python | `strftime("%Y-%m-%d %H:%M:%S")` |
| JavaScript | `new Date().toISOString().slice(0,19).replace('T',' ')` |
| Field name | `last_open` — bỏ hoàn toàn `last_open_time` |

---

### 📡 Heartbeat Kiosk (kiosk_gui.py)

- `_heartbeat_loop()` — daemon thread mới, ghi `/kiosk_status/last_seen` lên Firebase mỗi 30 giây

---

### 🖥 Giao diện Kiosk — Màn hình Waveshare 7" 1024×600

**`gui/theme.py` — điều chỉnh kích thước:**

| Tham số | Cũ | Mới |
|---|---|---|
| `SCREEN_W` | 1280 | 1024 |
| `SCREEN_H` | 720 | 600 |
| `CAM_W` | 680 | 560 |
| `CAM_H` | 510 | 430 |
| Font `title` | 26 | 22 |
| Font `head` | 16 | 14 |
| Font `body` | 13 | 12 |
| Font `small` | 10 | 9 |

**`gui/kiosk_app.py` — Bàn phím ảo QWERTY (class `VirtualKeyboard`):**
- Layout QWERTY đầy đủ + hàng số + ký tự đặc biệt (`@`, `.`, `_`, `-`)
- Chế độ thường / HOA (nút ⇧ toggle, tự tắt sau 1 ký tự hoa)
- Nút ⌫ xóa từng ký tự, CLR xóa hết, OK đóng
- Title bar kéo được — di chuyển bàn phím tùy ý; vị trí ghi nhớ trong phiên
- `takefocus=False` trên tất cả nút → entry không mất focus
- Mặc định ẩn hoàn toàn khi app khởi động
- Chỉ mở khi user **click/chạm trực tiếp** vào ô nhập (`Button-1`)
- Cờ `_enabled = False` → bật sau 300ms (tránh trigger khi render)
- Tự ẩn khi chuyển màn hình (`_go()` gọi `self._vkb.hide()`)
- `self._vkb.attach(entry)` — gắn vào entry MSSV, mật khẩu, OTP, đăng ký

**Fix layout:**
- Header: `70px → 60px`
- `lbl_time.place(y=24 → y=18)`
- Camera: `y=85 → y=65`

---

## [03/06/2026] — 2FA OTP Kiosk · Fix JS Date Trap · Firebase Rules

### 🔐 2FA OTP đăng nhập Kiosk (gui/kiosk_app.py)

- Tích hợp luồng gửi OTP 6 số qua email khi sinh viên đăng nhập bằng mật khẩu
- Gộp khung MSSV, mật khẩu, OTP trên cùng giao diện (inline numpad)
- Nút "Gửi mã" riêng biệt thay popup cũ

**Fix luồng "Bỏ qua" khuôn mặt:**
- Cũ: nhấn bỏ qua → văng ra `S_IDLE`
- Mới: điều hướng đúng → `_show_locker_menu` (có tủ) hoặc `_show_locker_picker` (chưa có tủ)

---

### 📧 Gửi mail tự động khi duyệt thẻ (sync_listener.py)

- `on_user_change()` — detect `is_approved: 0 → 1` → gọi `send_approval_email()`
- Không ảnh hưởng luồng sync nếu mail chưa cấu hình

---

### 🐛 Fix JS Date Trap (index.html + user-dashboard.html)

**Vấn đề:** `new Date("3/6/2026")` được JS parse là 03 tháng 6 (MM/dd/yyyy — chuẩn Mỹ), trong khi hệ thống lưu theo dd/MM/yyyy (chuẩn Việt). Hậu quả: idle báo sai 89 ngày, auto-expire xóa thẻ ngay lập tức.

**Fix:** Viết lại `calcIdleDays()` và `autoExpirePendingCards()` dùng Regex bóc tách `dd/MM/yyyy` thủ công — không dùng `new Date(string)` trực tiếp.

---

### 🔑 Fix Firebase Permission Denied — register.html

**Vấn đề:** Rule cũ yêu cầu `auth != null` để ghi `/users/$mssv` → sinh viên không tự đăng ký được.

**Fix:** Đổi rule thành `"auth != null || !data.exists()"` — cho phép tạo node mới không cần auth, nhưng không thể ghi đè node đã tồn tại.

---

### 🗄 Fix sync_users_to_firebase (core/user_db.py)

- Sửa lỗi query gọi nhầm cột `last_open` (của bảng `Lockers`) trong SELECT của bảng `Users`
- Cập nhật `get_user()` và `get_user_by_password()` lấy thêm field `email` (phục vụ OTP)

---

## [29/05/2026] — Pending Expire · Hủy yêu cầu trả tủ · Sync last_open

### ⏰ Pending expire daemon (kiosk_gui.py)

- `_pending_expire_loop()` — daemon thread mới, chạy mỗi 6 giờ
- Gửi mail warning khi tài khoản pending còn ≤ `PENDING_WARN_DAYS` ngày (mặc định 2)
- Gửi mail thông báo đã xóa sau `PENDING_EXPIRE_DAYS` ngày (mặc định 7)
- File flag `.warn_flags/` — tránh gửi mail warning lặp trong ngày
- Ghi `locker_delete_logs` với reason `auto_expired_pending` trước khi xóa Firebase

---

### 🔙 Hủy yêu cầu trả tủ (user-dashboard.html)

- Nút "Yêu cầu trả tủ" có 2 trạng thái: Chưa gửi → Đã gửi + "Hủy yêu cầu"
- `cancelRelease()` — xóa node `release_requests/{mssv}` + reset nút
- Trạng thái restore đúng khi reload trang

---

### 🔄 Sync last_open 2 chiều

**`core/db.py`:** `migrate()` tự thêm cột `last_open` và `assigned_date` nếu thiếu (idempotent)

**`core/locker_db.py` — `open_locker()`:** Ghi `last_open` vào cả SQLite và Firebase

**`sync_tool.py`:**
- `get_sqlite_lockers()` — thêm `last_open` vào SELECT
- `pull_locker_last_open()` — hàm mới, kéo `last_open` từ Firebase, merge lấy giá trị mới hơn
- `push()` — thêm `last_open` vào payload

**`sync_listener.py` — `on_locker_change()`:** Sync `last_open` nếu Firebase mới hơn SQLite

**`sync_tool.py` — Fix push logic:**
- `get_delete_logs()` — đọc `locker_delete_logs`, tách `admin_deleted_mssv` và `released_lockers`
- `push()` users — nếu user có trong SQLite nhưng không có Firebase → check `admin_deleted_mssv` → xóa SQLite, không push ngược
- `push()` lockers — nếu tủ occupied trong SQLite nhưng đã released theo log → dọn SQLite + push empty lên Firebase

---

## [28/05/2026] — Web Admin: Xóa thẻ · Auto-expire · Modal Cài Đặt · Tab Trả Tủ

### 🗑 Xóa thẻ sinh viên thủ công (index.html)

- Nút 🗑️ Xóa mỗi hàng trong bảng Sinh Viên, có confirm dialog
- Nếu đang mượn tủ → tự trả tủ trước khi xóa
- Ghi `/locker_delete_logs` với `reason: admin_delete_card`
- Xóa node `users/{mssv}` khỏi Firebase

---

### ⏳ Auto-expire thẻ chờ duyệt (index.html)

- Thẻ `is_approved: false` quá N ngày → tự xóa (chạy khi load + mỗi 1 giờ)
- N ngày cấu hình được qua Modal Cài Đặt
- Ghi log `reason: auto_expired_pending`

---

### ⚙️ Modal Cài Đặt tập trung (index.html)

Thay thế thanh inline cũ. Truy cập qua icon ⚙️:

| Cài đặt | Mặc định | Lưu vào |
|---|---|---|
| Cảnh báo idle sau | 5 ngày | `localStorage:cfg_idle_warn` |
| Tự động thu hồi tủ sau | 7 ngày | `localStorage:cfg_idle_auto` |
| Tự xóa thẻ pending sau | 7 ngày | `localStorage:cfg_expire_days` |

Validation: idle warn < idle auto. Áp dụng ngay sau khi lưu.

---

### 🔄 Tab Trả Tủ (index.html)

- Badge đỏ số yêu cầu đang chờ
- Bảng: MSSV, tủ, thời gian gửi, trạng thái (⏳/✅)
- Hàng pending tô vàng nhạt
- Nút "Xác nhận trả" → giải phóng tủ + ghi log + đánh dấu `status: done`
- Listeners bọc trong `startDataListeners()` — chỉ gọi sau `onAuthStateChanged`

---

### 📊 Nâng cấp user-dashboard.html

- Thanh cảnh báo idle 3 mức: 🟢 Bình thường · 🟡 Sắp đến hạn · 🔴 Quá hạn
- Progress bar idle trực quan
- Chip "Chờ duyệt" hiện số ngày đã chờ
- Nút "Yêu cầu trả tủ" với modal xác nhận mật khẩu

**Bug fix:**
- Fix crash tra cứu MSSV có tủ: `onValue(lockers)` throw exception do rules, không có try/catch
- Fix `ReferenceError` hoisting: `_currentMssv`, `_currentLockerId` khai báo sau auto-fill gọi `lookup()`
- Fix `is_approved` check: hỗ trợ `1`, `'1'`, `true`, `'true'`

---

## [27/05/2026] — Trả tủ · Auto-cleanup 7 ngày · LOCKER_DELETE_LOG

### 🔓 Tính năng Trả tủ (kiosk_app.py)

- **State mới `S_LOCKER_MENU`** — sau đăng nhập: có tủ → menu, chưa có tủ → picker
- `_show_locker_menu()` — 2 nút: 📦 Gửi đồ / 🔓 Trả tủ
- `_confirm_release()` — xác nhận 2 bước → `release_locker()` → `LOCKER_DELETE_LOG`
- Fix indent bug — tất cả state handlers đúng scope class
- `release_locker()` — sửa return type → `(bool, str)` tuple

---

### 🧹 Auto-cleanup tủ 7 ngày idle (kiosk_gui.py + core/locker_db.py)

- `get_inactive_lockers(days)` — query JOIN tủ không OPEN_LOCKER ≥ N ngày
- `auto_cleanup_inactive()` — ngày 6: warn_callback; ngày 7: release + log `auto_inactive_7days`
- `_warn_callback()` — buffer queue (thread-safe, không gọi tkinter từ daemon)
- `_drain_warn_queue()` — drain trên main thread qua `app.after()`
- `_cleanup_loop()` — daemon thread, mỗi 1 giờ

---

### 📋 LOCKER_DELETE_LOG (core/db.py + core/locker_db.py)

- `migrate()` — thêm `CREATE TABLE LOCKER_DELETE_LOG`
- `log_locker_delete(mssv, locker_id, reason)` — ghi local + push Firebase `/locker_delete_logs`

**Reasons:**

| Reason | Trigger |
|---|---|
| `student_release` | Sinh viên tự trả từ kiosk |
| `auto_inactive_7days` | Hệ thống thu hồi sau 7 ngày idle |
| `admin_force` | Admin ép trả từ web |
| `admin_deactivate` | Admin vô hiệu hóa tài khoản |
| `admin_delete_card` | Admin xóa thẻ thủ công |
| `auto_expired_pending` | Tài khoản pending hết hạn |

---

### 🌐 Tab Lịch Sử Tủ (index.html)

- Tab mới (tab 4): đọc `/locker_delete_logs` realtime
- Search MSSV / locker_id · Export CSV

---

## [19–27/05/2026] — Khởi tạo · Refactor module hóa

### 🏗 Kiến trúc ban đầu

- Phân tách `locker_db.py` gốc thành `core/` (db, user_db, locker_db, log_db)
- Chuyển `face_utils.py` vào `ai/`
- Tách `ai/models.py` — dlib singleton
- `hardware/camera.py` — CameraBackend winsdk

### 🤖 Pipeline AI

- MediaPipe BlazeFace detect (5–15ms CPU)
- dlib ResNet 128-D embedding (threshold 0.45)
- IR liveness rule-based (mean/std — không cần GPU)
- 3-thread pipeline: Camera → AI → UI (~30 FPS)

### 🌐 Web Admin ban đầu

- `landing.html` · `login.html` · `index.html` (4 tab) · `register.html` · `user-dashboard.html`
- Firebase Auth + Realtime DB
- Dark mode · Export CSV · Material Symbols Rounded

### 🐛 Bug fix anh hưởng lớn

| Lỗi | Fix |
|---|---|
| `dlib compute_face_descriptor` TypeError | Dùng `dlib.get_face_chip()` trước |
| `mp.solutions` AttributeError | Dùng `mediapipe.tasks.python.vision` |
| Camera asyncio deadlock | Đổi sang polling |
| Firebase 404 Not Found | Đổi URL sang `asia-southeast1` |
| Locker tạo thành `LL01` | Bỏ prefix `"L"` thừa trong format string |
| Lambda closure bug | `lambda l=lid: assign_locker(l)` |
| `ModuleNotFoundError: face_utils` | Đổi thành `from ai.face_utils import ...` |

---

*IntelligentLocker — HCMUTE Makerspace*