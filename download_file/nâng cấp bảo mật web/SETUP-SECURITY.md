# Setup Bảo mật Firebase

## Bước 1: Cập nhật Security Rules

1. Vào Firebase Console → Realtime Database → Rules
2. Paste nội dung từ `firebase-rules.json`
3. Click **Publish**

---

## Bước 2: Setup Service Account cho Python Backend

### Tại sao cần?
Python (locker_db.py, sync_listener.py) cần ghi logs/lockers mà không có user login → cần Service Account.

### Cách làm:

**1. Tạo Service Account Key**
```
Firebase Console 
→ Project Settings (⚙️) 
→ Service Accounts 
→ Generate New Private Key
→ Lưu file JSON (vd: serviceAccountKey.json)
```

**2. Cài Firebase Admin SDK**
```bash
py -3.11 -m pip install firebase-admin
```

**3. Sửa `sync_listener.py`**

Thay code Firebase cũ:
```python
# CŨ (không an toàn)
import pyrebase
config = {...}
firebase = pyrebase.initialize_app(config)
```

Bằng Admin SDK:
```python
# MỚI (an toàn)
import firebase_admin
from firebase_admin import credentials, db

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://lockerxmakerspacexhcmute-default-rtdb.firebaseio.com'
})

# Dùng như cũ
ref = db.reference('users')
ref.child('22146436').set({...})
```

---

## Bước 3: Ẩn API Key Trong Web

### Vấn đề hiện tại
API key public trong `index.html` và `login.html` → ai cũng thấy được.

### Giải pháp 1: Firebase App Check (Khuyến nghị)
```
Firebase Console → App Check → Register app → reCAPTCHA v3
```

Thêm vào HTML (trước script Firebase):
```html
<script src="https://www.gstatic.com/firebasejs/10.9.0/firebase-app-check.js"></script>
<script type="module">
  import { initializeAppCheck, ReCaptchaV3Provider } from 
    "https://www.gstatic.com/firebasejs/10.9.0/firebase-app-check.js";
  
  const appCheck = initializeAppCheck(app, {
    provider: new ReCaptchaV3Provider('YOUR_RECAPTCHA_SITE_KEY'),
    isTokenAutoRefreshEnabled: true
  });
</script>
```

### Giải pháp 2: Environment Variable (nếu dùng build tool)
```js
// .env
VITE_FIREBASE_API_KEY=AIzaSyD...

// config
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  ...
}
```

⚠️ **Lưu ý**: API key vẫn public ở frontend là BÌNH THƯỜNG. Security Rules mới là tầng bảo vệ thật.

---

## Bước 4: Thêm Admin Role Check (Nâng cao)

Nếu muốn phân quyền chi tiết hơn (vd: chỉ admin@example.com mới sửa được):

**1. Thêm Custom Claims**
```python
# Script chạy 1 lần để set admin
from firebase_admin import auth
auth.set_custom_user_claims('USER_UID_CUA_ADMIN', {'admin': True})
```

**2. Sửa Rules**
```json
{
  "rules": {
    ".read": "auth != null",
    ".write": "auth != null && auth.token.admin === true",
    "logs": {
      ".write": "auth != null"  // Cho phép Python ghi log
    }
  }
}
```

---

## Checklist Bảo Mật

- [ ] Deploy rules mới từ `firebase-rules.json`
- [ ] Setup Service Account cho Python backend
- [ ] Test web admin vẫn login/ghi được
- [ ] Test Python backend vẫn ghi logs/lockers được
- [ ] (Optional) Setup Firebase App Check
- [ ] Xóa file `serviceAccountKey.json` khỏi git (thêm vào `.gitignore`)

---

## Lỗi thường gặp

### "Permission denied" khi Python ghi data
→ Chưa dùng Admin SDK, vẫn dùng pyrebase hoặc REST API không auth

### "Auth token không hợp lệ"
→ File serviceAccountKey.json sai hoặc đường dẫn sai

### Web admin không login được
→ Rules quá chặt, kiểm tra lại auth conditions
