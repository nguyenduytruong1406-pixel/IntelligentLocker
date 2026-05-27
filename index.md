# Smart Locker - Admin Dashboard

**Logo:** `logo_web.jpg`  
**Icons:** Material Symbols Rounded

---

## 📋 Layout Structure

### Sidebar (260px, collapsible to 75px)
- **Logo Container** (160px height)
  - Responsive logo image (100x100px → 45x45px collapsed)
- **Navigation Menu**
  - Items with icons + text labels
  - Active state highlight (left border + background)
  - Badge for notifications (visible when count > 0)
- **Bottom Controls** (icons row)
  - Theme toggle button
  - Firebase sync toggle
  - Logout button

### Right Bar (60px fixed)
- Vertical scrollable icon bar
- Notification panel (300px, fixed position, top-right)
  - Header with title
  - Notification items (scrollable)
  - "No notifications" message when empty

### Main Content (flex: 1)
- **Top Header**
  - Page title
  - Mobile menu button
  - Right-side controls
- **Tab Content** (4 tabs)
  - Users (tab-users)
  - Lockers (tab-lockers)
  - Logs (tab-logs)
  - Settings (tab-settings)

---

## 🎨 Color Scheme

### Light Mode (default)
```css
--bg: #f4f7f6
--surface: #ffffff
--border: #ddd
--text: #333
--text2: #555
--primary: #007bff
--btn-export-bg: #17a2b8
--locker-empty-bg: #e6ffec (green)
--locker-occ-bg: #ffe6e6 (red)
```

### Dark Mode
```css
--bg: #18191A
--surface: #242526
--text: #E4E6EB
--primary: #4D94FF
--locker-empty-bg: #1e3a23
--locker-occ-bg: #3a1e1e
```

### Locker Status Colors
| Status | Background | Border | Text |
|--------|-----------|--------|------|
| Empty | Green | #28a745 | Dark green |
| Occupied | Red | #dc3545 | Dark red |

---

## 📱 Responsive Breakpoints

**Mobile:** max-width 768px
- Sidebar slides out from left (fixed position)
- Main content: reduced padding (12px)
- Locker grid: single column
- Top header: collapsed

---

## 🗂 Tab Structure

### 1️⃣ Users Tab (tab-users)
- **Stats Grid** (auto-fit cards)
  - Total users count
  - Approved count
  - Pending count
- **Search Box** (max-width 400px)
- **Users Table**
  - Columns: MSSV | Tên | Email | Khuôn Mặt | Trạng Thái | Actions
  - Actions: Approve btn | Lock btn
- **User Detail Modal** (wide variant, 500px)
  - User info grid (2 columns)
  - MSSV, Name, Email, Role, Status, Face data

### 2️⃣ Lockers Tab (tab-lockers)
- **Control Box** (blue gradient, 220x110px)
  - Release all lockers button
- **Locker Grid** (6 columns, 20px gap)
  - Small boxes (2 col span, 110px height)
  - Large boxes (3 col span, 160px height)
  - Hover effect: scale 1.05
  - Click to open locker detail modal

### 3️⃣ Logs Tab (tab-logs)
- **Export Button** (cyan background)
- **Logs Table** (scrollable)
  - Columns: Thời Gian | MSSV | Tên | Tủ | Sự Kiện
  - Event colors: Green (OPEN), Blue (ASSIGN), Red (RELEASE)
  - Reverse chronological order (newest first)

### 4️⃣ Settings Tab (tab-settings)
- Placeholder for future settings

---

## 🎛 Key UI Components

### Buttons
| Type | Style | Usage |
|------|-------|-------|
| `btn-export` | Cyan, small | Export CSV |
| `btn-approve` | Green | Approve user |
| `btn-lock` | Red | Lock/release locker |
| `btn-info` | Teal | View details |
| `btn-assign` | Purple | Assign locker |

### Search Input
- Icon on left (magnifying glass)
- Max-width 400px
- Focus: primary color border + subtle blue shadow

### Modal
- Centered, semi-transparent dark overlay
- Animation: fade-in 0.2s
- Close button: top-right X
- Detail rows: dashed separator lines

### Toast Notifications
- Fixed bottom-right position (24px margin)
- Dark background, white text
- Slide-up animation on show

### Badges
- Red circle badge for counts (notifications, pending approvals)
- Positioned on nav icons

---

## 🔧 JavaScript Functions

### Theme Management
```js
window.toggleTheme(mode)     // 'light' | 'dark' | 'system'
```
- Saves selection to localStorage
- Updates CSS variables dynamically

### Tab Navigation
```js
window.switchTab(tabId, el)  // Switch active tab + close sidebar on mobile
```

### User Actions
```js
window.approveUser(mssv)     // Set is_approved = 1 in Firebase
window.lockUser(mssv)        // Lock user account
window.viewUserDetail(mssv)  // Open user detail modal
window.filterUsers()         // Filter by search input
window.viewPendingUser(mssv) // Jump to users tab + open detail
```

### Locker Actions
```js
window.releaseLocker(lockerId)    // Set status = 'empty'
window.releaseAllLockers()        // Release all occupied lockers
window.viewLockerDetail(lockerId) // Open locker modal
```

### Export Functions
```js
window.exportUsers()  // Download users_YYYY-MM-DD.csv
window.exportLogs()   // Download logs_YYYY-MM-DD.csv
```

### UI Helpers
```js
window.showToast(message)      // Show toast notification (3s auto-hide)
updateBadge(count)             // Show/hide notification badge
clearBadge()                   // Hide badge when logs tab opened
```

### Firebase Integration
```js
window.toggleFirebaseSync()    // Start/stop sync_listener daemon
```

### Sidebar
```js
window.toggleSidebar()         // Collapse/expand sidebar
window.toggleMobileMenu()      // Mobile: show/hide sidebar overlay
```

---

## 🔌 Firebase Data Binding

### Real-time Listeners

**Users Collection:**
```js
db.ref('users').on('value', snapshot => {
  // Update users table + stats
})
```

**Lockers Collection:**
```js
db.ref('lockers').on('value', snapshot => {
  // Update locker grid + detail modal
})
```

**Logs Collection:**
```js
db.ref('logs').on('value', snapshot => {
  // Update logs table + notification badge
})
```

### Event Mapping
```js
EVENT_MAP = {
  'OPEN_LOCKER': { label: '🔓 Mở', color: '#28a745' },
  'ASSIGN_LOCKER': { label: '🔒 Gán', color: '#007bff' },
  'RELEASE_LOCKER': { label: '🔑 Trả', color: '#dc3545' },
  'FACE_REGISTER': { label: '👤 Đăng ký', color: '#17a2b8' },
  // ... more events
}
```

---

## 📊 Data Models

### User Object
```json
{
  "mssv": "22146436",
  "name": "Nguyễn Duy Trưởng",
  "email": "22146436@student.hust.edu.vn",
  "has_face": 1,
  "is_approved": 1,
  "role": "student"
}
```

### Locker Object
```json
{
  "locker_id": "L01",
  "size": "small",
  "status": "empty",
  "current_mssv": null,
  "last_open_time": "2026-05-27T10:30:00"
}
```

### Log Object
```json
{
  "time": "2026-05-27 10:30:45",
  "event": "OPEN_LOCKER",
  "mssv": "22146436",
  "name": "Nguyễn Duy Trưởng",
  "locker_id": "L01"
}
```

### Notification Object
```json
{
  "type": "face_register",
  "mssv": "22146436",
  "name": "Nguyễn Duy Trưởng",
  "timestamp": "2026-05-27T10:30:00"
}
```

---

## 🛠 CSS Classes Quick Reference

### Layout
- `.sidebar`, `.sidebar.collapsed` — sidebar + collapsed state
- `.main-content` — main area
- `.right-bar` — right icon bar
- `.logo-container`, `.sidebar-logo` — logo section
- `.nav-menu`, `.nav-item`, `.nav-item.active` — navigation

### Content
- `.top-header` — page title area
- `.tab-content`, `.tab-content.active` — tab visibility
- `.section-header` — section title + action buttons
- `.stats-grid`, `.stat-card` — statistics cards

### Tables
- `.table-responsive` — scrollable table container
- `table`, `th`, `td` — standard table
- `.action-btns` — button group in rows

### Lockers
- `.locker-grid` — 6-column grid
- `.locker-box`, `.locker-box.occupied` — locker item
- `.box-small`, `.box-large` — size variants
- `.control-box` — release button

### Modals
- `.modal`, `.modal.active` — modal overlay + visible state
- `.modal-content` — centered content box
- `.modal-wide` — wider variant (500px)
- `.close-btn` — top-right X button
- `.modal-detail-row`, `.user-info-grid` — content layout

### Forms & Input
- `.search-box` — search wrapper with icon
- `.search-box input` — input field
- `.search-box .ms` — search icon

### Buttons
- `.btn`, `.btn-sm` — base + small
- `.btn-export`, `.btn-approve`, `.btn-lock`, `.btn-info`, `.btn-assign` — color variants

### Notifications
- `#toast` — toast notification
- `#toast.show` — visible state
- `.notif-panel`, `.notif-panel.open` — notification dropdown
- `.notif-header`, `.notif-body`, `.notif-item`, `.notif-empty` — structure
- `.badge`, `.badge.visible` — icon badge
- `.notif-badge`, `.notif-badge.visible` — modal badge

### Theme
- `.theme-menu`, `.theme-menu.open` — theme selector
- `.theme-option`, `.theme-option.selected` — theme items

### Mobile
- `.mobile-menu-btn` — hamburger button
- `.sidebar-overlay`, `.sidebar-overlay.show` — mobile overlay

---

## ⌨️ Keyboard Navigation

- **Tab**: Move between interactive elements
- **Enter**: Activate button/link
- **Escape**: Close modal or sidebar (mobile)

---

## ♿ Accessibility Features

- Semantic HTML structure
- ARIA labels on icon buttons
- Color contrast meets WCAG AA standards
- Keyboard focus indicators
- Theme respects `prefers-color-scheme` media query

---

## 📦 Dependencies

- **Google Fonts:** Material Symbols Rounded
- **Firebase:** Real-time database + Authentication
- **Vanilla JavaScript:** No framework required

---

## 🔒 Security Notes

- Firebase Security Rules restrict access (auth required for logs, write)
- User roles distinguish between admin and student access
- Sensitive data (embeddings) stored on local machine, not Firebase
- CSV exports sanitize quotes in CSV fields

---

**Generated from index.html — 27/05/2026**
