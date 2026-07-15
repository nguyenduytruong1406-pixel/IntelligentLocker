# 📅 CHANGELOG — IntelligentLocker

Toàn bộ lịch sử thay đổi theo ngày, mới nhất ở trên.

---

## [15/07/2026] — Bỏ hẳn "chờ duyệt", fallback gửi mật khẩu qua EmailJS, đồng bộ `is_first_login`, vá loạt bug sync tủ

### 🌐 Web Admin (`index.html`)

**Fallback gửi mật khẩu qua EmailJS khi Kiosk offline:**
- Trước đây tài khoản + mật khẩu chỉ gửi được qua `/pending_credentials` → `sync_listener.py` (yêu cầu Kiosk online). Nếu Kiosk offline lúc admin duyệt đơn, mật khẩu **không đến được** sinh viên.
- Thêm nhánh dự phòng: nếu `kiosk_status.last_seen` quá 90s → gửi thẳng qua EmailJS từ trình duyệt admin (`emailjs.send()`), dùng template riêng (`templateIdCredentials`, khác template OTP).
- Ghi log audit vào node mới `/credential_email_log/{mssv}` (`sent_via`, `sent_at`) — **không** dùng lại `/pending_credentials` nên `sync_listener.py` không đọc/gửi trùng khi Kiosk online lại.
- Nếu cả 2 đường đều fail (EmailJS cũng lỗi) → rơi lại `/pending_credentials` làm backstop cuối.
- Tab "Đơn Đăng Ký" thêm cột **"Gửi Mail"** hiển thị realtime: `📡 Chờ Kiosk gửi` / `✉️ Đã gửi (EmailJS)` — admin biết chắc email đã đi, không còn tình trạng "duyệt xong không biết có gửi được không".

**Bỏ hẳn tính năng "chờ duyệt" (`is_approved`):**
- Xóa card "Chờ duyệt", nút "Duyệt thẻ/Khóa thẻ" trong tab Sinh Viên, cột "Trạng Thái" trong bảng + modal chi tiết + CSV export.
- Xóa cấu hình "Tự xóa thẻ chờ duyệt sau N ngày" trong Settings modal + hàm `autoExpirePendingCards()` (không còn khái niệm tài khoản "chờ duyệt" nữa — tài khoản chỉ tồn tại khi admin đã tạo trực tiếp, luôn active ngay).
- **`confirmApproveAccount()` không còn ghi field `is_approved` khi tạo tài khoản mới** — thay bằng `is_first_login:true` (đánh dấu tài khoản dùng mật khẩu do admin cấp, chưa tự đổi).
- Card thống kê "Sinh viên đã duyệt" → đổi thành **"Tổng sinh viên"** (đếm tổng, vì is_approved không còn tồn tại).

**Chuông thông báo góc phải — đổi mục đích hoàn toàn:**
- Không còn liên quan "chờ duyệt sinh viên" (tính năng đã bỏ). Giờ chỉ hiện **1 chấm đỏ** (không số) khi có yêu cầu trả tủ đang chờ HOẶC đơn đăng ký mới đang chờ cấp tài khoản — click từng mục nhảy thẳng tới tab tương ứng.
- Bỏ hẳn badge số ở mục "Nhật Ký" (trước đây luôn hiện sai số dù chưa có log mới — do logic đếm bị lỗi ngay từ đầu, quyết định bỏ badge thay vì vá).

**Ghi log khi gán tủ mới (`new_assignment`):** `confirmApproveAccount()` và `confirmAssignLocker()` giờ đều push thêm 1 entry vào `/locker_delete_logs` với `reason:'new_assignment'` mỗi khi gán tủ — phục vụ so sánh thời gian trong `sync_tool.py` (xem phần Kiosk bên dưới) để phân biệt "tủ vừa gán lại hợp lệ" với "tủ còn sót lại state cũ chưa dọn".

> ⚠️ **Cần theo dõi:** `delete_time` trong `locker_delete_logs` cần **thống nhất định dạng ISO sortable** (`YYYY-MM-DD HH:MM:SS`) ở TẤT CẢ các chỗ ghi, vì `sync_tool.py` giờ so sánh `assigned_date` với `delete_time` bằng string so sánh trực tiếp — 2 chỗ (`deleteUserCard()`, `handleRelease()`) hiện đang dùng lại `toLocaleString('vi-VN')` (không sort được), cần đổi về `toISOString().slice(0,19).replace('T',' ')` để tránh vá lại đúng bug `[FIX LOCKER]` bên dưới.

### 🖥 Kiosk (Python)

**Fix bug thu hồi tủ sót `last_open`/`assigned_date`:** 3 câu SQL (`sync_listener.py::on_user_change`, `sync_tool.py::pull()` và `push()` nhánh `admin_deleted`) khi xóa tài khoản chỉ clear `status` + `current_mssv`, quên `assigned_date`/`last_open` — gây hiển thị sai thông tin gán tủ cũ dù tủ đã trống. Đã đồng nhất cả 3 chỗ.

**Đồng bộ 2 chiều `is_first_login`:**
- `sync_listener.py::on_user_change` + `sync_tool.py::pull()`: đọc `is_first_login` từ Firebase, merge với SQLite (Firebase chỉ override khi có giá trị rõ ràng — Kiosk vẫn là nguồn xác thực chính vì field này đổi khi sinh viên tự đổi mật khẩu tại Kiosk).
- `sync_tool.py::push()`: đẩy `is_first_login` lên Firebase cả khi tạo mới lẫn khi update diff.
- (`firebase_hooks.py::push_password_changed()` đã tự set `is_first_login=False` sẵn từ trước — không cần sửa thêm.)

**Fix false-positive `[FIX LOCKER]` trong `sync_tool.py::push()`:** trước đây so khớp `(mssv, locker_id)` với log `student_release` để "tự dọn" SQLite còn sót — nhưng log này **tồn tại vĩnh viễn**, nên khi 1 locker được **gán lại hợp lệ** cho đúng sinh viên đó sau này, sync vẫn tưởng nhầm là "còn sót" và **xóa mất lần gán mới**. Sửa bằng cách so sánh `assigned_date` hiện tại với `delete_time` của lần trả gần nhất — chỉ tự dọn khi `assigned_date` **cũ hơn hoặc bằng** lần trả (thật sự là state cũ), bỏ qua nếu đã gán lại sau đó. Đồng thời ghi log audit `reason:'sync_auto_fix'` mỗi khi tự dọn (trước đây bước này không để lại dấu vết gì).

**Nối `SelectModeController` vào luồng chính:** `select_mode.py` (màn hình Mở tủ/Trả tủ) trước đây tồn tại nhưng **chưa từng được `main.py` import/đăng ký** — `face_controller.py` điều hướng tới bằng `setCurrentIndex(3)` (số cứng, trỏ sai trang). Đã:
- Đăng ký `select_mode` vào `PAGES` qua `add_page()` trong `main.py`.
- Sửa `face_controller.py` dùng `PAGES["select_mode"]` thay vì số cứng.
- Thêm phím tắt **ESC** trong `select_mode.py` → về màn hình chính (không dùng nút bấm hiển thị — kiosk công khai không nên có nút thoát lộ liễu).

**Xác nhận: luồng đăng ký + xác thực bằng mật khẩu tại Kiosk đã bị bỏ hẳn.** `RegisterController`, `PassWordController`, `SendEmailController`, `EnterOtpController`, `ServiceController`, `MenuServiceController` không còn được đăng ký trong `main.py`. `AuthMethodController` giờ chỉ còn 1 lựa chọn duy nhất (khuôn mặt) — nút chọn mật khẩu bị ẩn (`pass_select.hide()`) nếu còn sót trong file `.ui`. README mục "Kiosk Stack Index" và sơ đồ "Luồng điều hướng Kiosk" đã cập nhật lại theo đúng `main.py` hiện tại.

> ⚠️ **Known issue chưa xử lý:** `select_locker_controller.py` (màn hình chọn tủ trống — `SelectLockerController`) hiện **chỉ có file `.pyc` biên dịch sẵn, không có mã nguồn `.py`** trong dự án. Khi sinh viên chưa có tủ, `select_mode.py` gọi `go_to_select_locker()` → `setCurrentIndex(4)` nhưng trang này **chưa được đăng ký vào `PAGES`**, có thể dẫn sai màn hình. Cần cấp lại mã nguồn file này để nối đúng vào `main.py` (tương tự cách đã xử lý với `select_mode.py`).

---

## [09/07/2026] — Đổi mô hình đăng ký: QR → Google Form → PDF ký tay → Admin duyệt

### 🔄 Đổi luồng đăng ký tài khoản

**Vấn đề:** Mô hình cũ (sinh viên tự đăng ký qua `register.html` hoặc kiosk) không có bước xác nhận giấy tờ — GVHD yêu cầu chuyển sang quy trình có chữ ký xác nhận trước khi cấp tài khoản.

**Luồng mới:**
```
Sinh viên quét QR tại Kiosk → điền Google Form → nhận PDF qua email
→ in, xin chữ ký (thành viên + GVHD) → nộp bản giấy cho quản lý
→ Admin tra cứu trên Web (tab "Đơn Đăng Ký") → xác nhận đơn giấy → bấm "Thêm tài khoản"
→ Tài khoản được tạo trong /users → sync_listener.py đẩy xuống SQLite kiosk ngay
→ Sinh viên ra kiosk đăng ký khuôn mặt
```

Trong lúc chờ duyệt, sinh viên **chỉ tồn tại trong `/locker_requests`** (`status: "pending"`) — chưa có trong `/users` nên không thể thao tác gì tại Kiosk. Tách biệt 2 node này giữ nguyên tính chặt chẽ của hệ thống phần cứng.

### 📄 Google Apps Script — tự động tạo PDF + gửi mail + ghi Firebase

**Trigger:** `onFormSubmitAndSendEmail(e)` — chạy khi có submit mới trên Google Form (`Trigger - On form submit`).

**Xử lý:**
1. Đọc toàn bộ câu trả lời form (`e.response.getItemResponses()`), map vào object `data` theo tên câu hỏi (khoa, đề tài, GVHD, kích thước tủ, ngày mượn/trả, thông tin tối đa 3 thành viên)
2. Copy file Google Docs template (`TEMPLATE_DOC_ID`) vào thư mục đích (`TARGET_FOLDER_ID`), thay các placeholder dạng `{{key}}` bằng dữ liệu thật (kể cả điền tự động số thứ tự `{{01}}/{{02}}/{{03}}` nếu có thành viên)
3. Xuất file Docs vừa điền thành PDF (`tempFile.getAs(MimeType.PDF)`)
4. Gửi PDF qua email cho trưởng nhóm (`MailApp.sendEmail`), kèm hướng dẫn in — ký — nộp cho Ban quản lý
5. Dọn file Docs nháp (`tempFile.setTrashed(true)`), chỉ giữ email + PDF đã gửi
6. Đẩy dữ liệu lên Firebase `/locker_requests/{mssv}` với `status: "pending"`

### 🔐 Ghi Firebase bằng OAuth2 Service Account (Admin SDK)

**Vấn đề cũ (nếu dùng REST API thường):** phải mở `.write: true` lỏng lẻo trên node hoặc lộ API key trên URL.

**Giải pháp:** dùng thư viện `OAuth2` cho Apps Script, tạo Access Token (Bearer) từ Service Account key theo chuẩn JWT:
```javascript
function getFirebaseService() {
  return OAuth2.createService('Firebase')
      .setTokenUrl('https://oauth2.googleapis.com/token')
      .setPrivateKey(privateKey)
      .setIssuer(clientEmail)
      .setPropertyStore(PropertiesService.getScriptProperties())
      .setScope('https://www.googleapis.com/auth/firebase.database ...');
}
```
Token được gắn vào header `Authorization: Bearer ...` khi gọi REST API Firebase (`PUT /locker_requests/{mssv}.json`) — không lộ quyền ghi trên URL.

**Fix bảo mật quan trọng:** ban đầu private key bị hardcode trực tiếp trong code `.gs` — đã chuyển sang lưu trong **Script Properties** (`PropertiesService.getScriptProperties()`), đồng thời **thu hồi (revoke) key cũ đã lộ và tạo key mới** trên Google Cloud Console. Code đọc key runtime thay vì hardcode:
```javascript
var props = PropertiesService.getScriptProperties();
var clientEmail = props.getProperty('FIREBASE_CLIENT_EMAIL');
var privateKey  = props.getProperty('FIREBASE_PRIVATE_KEY').replace(/\\n/g, '\n');
```
Lỗi `Invalid argument: key` gặp phải trong lúc setup do định dạng `\n` trong private key bị escape sai khi dán vào Script Properties — fix bằng `.replace(/\\n/g, '\n')` để đảm bảo ký tự xuống dòng đúng chuẩn PEM.

### 🌐 Web Admin — Tab mới "Đơn Đăng Ký" (`index.html`)

- Bảng hiển thị: MSSV, Họ tên, Email, Kích thước tủ, Ngày đăng ký, Trạng thái — **ẩn trường `khoa` khỏi UI** (vẫn lưu trong Firebase để tra cứu sau nếu cần, không hiển thị dư thừa)
- Ô tìm kiếm theo MSSV hoặc tên (lọc client-side trên dữ liệu cache `_allLockerRequests`)
- Badge đỏ trên sidebar đếm số đơn `status: "pending"`, realtime qua `onValue(ref(db,'locker_requests'))`
- Nút **"➕ Thêm tài khoản"** cho từng đơn `pending` → `approveLockerRequest(mssv)`:
  - `update(ref(db, users/{mssv}), {...})` — tạo tài khoản với `is_approved:1`, `has_face:false`, `role:'student'`
  - `update(ref(db, locker_requests/{mssv}), {status:'approved', approved_at:...})` — giữ lại lịch sử, không xóa node
  - Có `confirm()` nhắc admin chỉ bấm sau khi đã kiểm tra đơn giấy có đủ chữ ký

### 🔥 Firebase — node mới `/locker_requests/{mssv}`

```
/locker_requests/{mssv} → mssv, name, email, khoa, size_requested,
                           requested_at, status ("pending"|"approved"), approved_at
```
Thêm rule: `"locker_requests": { ".read": "auth != null", "$mssv": { ".write": true } }` — Apps Script ghi bằng Bearer token của Admin SDK nên không bị chặn bởi rule client thường.

### ✅ Không cần sửa `sync_listener.py`

`on_user_change` (lắng nghe `/users`) đã có sẵn từ trước và tự động:
- Đẩy user mới xuống SQLite kiosk ngay khi admin duyệt (realtime, không cần chờ `sync_tool.py`)
- Gửi mail "Tài khoản đã được phê duyệt" khi `is_approved` chuyển 0 → 1 (`send_approval_email()`)

Vì vậy toàn bộ luồng mới hoạt động ngay mà không cần thay đổi gì ở tầng kiosk.

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