# Smart Locker - Admin Dashboard

## Metadata
- **Title**: Smart Locker - Admin Dashboard
- **Icon**: logo_web.jpg
- **Font**: Material Symbols Rounded, Segoe UI

---

## Cấu Trúc Trang

### Layout Chính
- **Sidebar** (260px width, collapsible)
- **Main Content** (flex: 1)
- **Right Bar** (60px width)

---

## 1. Sidebar Navigation

### Logo Container
- Hiển thị logo 100x100px
- Collapse thành 45x45px khi sidebar bị gập

### Menu Items
Các mục điều hướng chính:
- **Dashboard** - Trang chủ
- **Lockers** - Quản lý tủ khóa
- **Users** - Quản lý người dùng
- **Logs** - Xem nhật ký
- **Delete Logs** - Nhật ký xóa
- **Approvals** - Duyệt yêu cầu
- **Notifications** - Thông báo (có badge)

Mỗi mục có:
- Icon từ Material Symbols
- Text label
- Hover effect
- Badge thông báo (optional)
- Active state highlighting

### Sidebar Bottom
- Nút chuyển theme (Light/Dark/System)
- Nút collapse sidebar
- Nút thông báo với badge

---

## 2. Main Content Area

### Top Header
- Tiêu đề trang (H2)
- Khoảng trống trống cho các nút hành động

### Tab Content
Các tab chính:

#### Tab: Dashboard
- **Stats Cards** (4 cột responsive)
  - Total Lockers
  - Occupied
  - Empty
  - Active Users

#### Tab: Lockers
- **Locker Grid** (6 cột)
  - Locker boxes: small (2 col x 110px), large (3 col x 160px)
  - Color coding:
    - **Green**: Empty & Idle
    - **Red**: Occupied
  - Idle warning tags
  - Control box (Blue gradient)

- **Search & Filter**
  - Input search
  - Export CSV button

- **Locker Details Table**
  - Locker ID, Status, Current User, Check-in Time, Check-out Time
  - Action buttons: View Details, Lock, Unlock

#### Tab: Users
- **User Management Table**
  - MSSV, Name, Email, Phone
  - Status (Active/Inactive)
  - Action buttons: Edit, View Details, Deactivate

- **User Search**
  - Filter by MSSV or Name

#### Tab: Logs
- **Activity Logs Table**
  - Time, MSSV, Name, Locker ID, Event Type
  - Sortable by date
  - Export CSV

#### Tab: Delete Logs
- **Deletion History**
  - Delete Time, MSSV, Locker ID, Reason
  - Reason map:
    - ✅ Student returned
    - 🕐 System (7 days idle)
    - 🔒 Admin forced
    - 👤 Account deactivated
  - Search & filter
  - Export CSV

#### Tab: Approvals
- **Pending Requests Table**
  - User info, Request type, Date
  - Action buttons: Approve, Deny

---

## 3. Right Bar (Icons)

- **Notifications Icon** - Mở notification panel
- **Theme Toggle** - Light/Dark/System mode
- **Settings** - Cấu hình tài khoản
- **Logout** - Đăng xuất

---

## 4. Modal Windows

### Locker Detail Modal
- Locker ID, Status, Current User, Check-in/Check-out Time
- Action buttons
- Close button

### User Detail Modal (Wide)
- **User Info Grid** (2 cột)
  - MSSV, Name, Email, Phone
  - Status, Department, Grade
  
- **Current Locker Info**
  - Locker ID, Check-in Time, Status

- **Action Buttons**
  - Edit, Assign Locker, Deactivate, Release Locker

### Approval Modal
- Request details
- User information
- Action buttons: Approve, Deny

---

## 5. Theme System

### Light Mode (Default)
- Background: #f4f7f6
- Surface: #ffffff
- Text: #333
- Primary: #007bff

### Dark Mode
- Background: #18191A
- Surface: #242526
- Text: #E4E6EB
- Primary: #4D94FF

### System Mode
- Tự động theo setting hệ thống

---

## 6. Notification Panel

- **Fixed position**: Top right
- **Width**: 300px
- **Max height**: 400px

- **Header**: "Thông báo"
- **Body**: List of notifications
  - Notification items with hover effect
  - Empty state message

---

## 7. Toast Notification

- **Position**: Bottom right
- **Auto dismiss**: 3 seconds
- Success/Error/Info messages

---

## 8. Key JavaScript Functions

### Locker Management
- `viewLockerDetail(lockerId)` - Xem chi tiết tủ
- `toggleLockStatus(lockerId)` - Khóa/Mở tủ
- `releaseLock(lockerId)` - Buộc thả tủ

### User Management
- `openUserDetail(mssv)` - Xem chi tiết người dùng
- `filterUsers()` - Lọc danh sách người dùng
- `exportUsers()` - Xuất danh sách CSV

### Logs
- `filterLogs()` - Lọc nhật ký
- `exportLogs()` - Xuất nhật ký CSV
- `filterDeleteLogs()` - Lọc nhật ký xóa
- `exportDeleteLogs()` - Xuất nhật ký xóa CSV

### UI Controls
- `switchTab(tabId, el)` - Chuyển tab
- `toggleSidebar()` - Gập/mở sidebar
- `toggleTheme(mode)` - Chuyển theme
- `viewPendingUser(mssv)` - Xem người dùng chờ duyệt

### Utilities
- `showToast(message)` - Hiển thị toast notification
- `downloadCSV(filename, rows, headers)` - Xuất CSV

---

## 9. Firebase Integration

### Real-time Data Sources
- **locker_list** - Danh sách tủ khóa
- **users_list** - Danh sách người dùng
- **access_logs** - Nhật ký truy cập
- **locker_delete_logs** - Nhật ký xóa tủ
- **pending_approvals** - Yêu cầu chờ duyệt
- **notifications** - Thông báo

### Data Sync
- Real-time updates khi có thay đổi
- Auto-refresh UI
- Badge updates cho thông báo mới

---

## 10. Responsive Design

### Mobile Breakpoints
- **Max 768px**: 
  - Sidebar becomes fixed overlay
  - Mobile menu button appears
  - Content area takes full width
  - Grid layouts become stacked

- **Sidebar Mobile**:
  - Position: fixed, left: -260px
  - Toggle with mobile menu button
  - Overlay backdrop

---

## 11. Animations & Transitions

- **Fade In**: Tab content (0.3s)
- **Scale**: Locker boxes on hover (1.05)
- **Color Transitions**: Theme change (0.3s)
- **Slide**: Sidebar collapse (0.3s)
- **Transform**: Toast notification (0.3s)

---

## 12. Accessibility Features

- Semantic HTML structure
- Material Symbols for icons
- High contrast text
- Focus states for inputs
- Keyboard navigation support
- ARIA labels for interactive elements

---

## 13. Color Palette

### Status Colors
- **Empty**: #28a745 (Green)
- **Occupied**: #dc3545 (Red)
- **Idle Warning**: #856404 (Orange)
- **Idle Danger**: #721c24 (Dark Red)

### Action Colors
- **Primary**: #007bff (Blue)
- **Info**: #17a2b8 (Cyan)
- **Assign**: #6f42c1 (Purple)
- **Export**: #17a2b8 (Teal)

---

## Kết Luận

Đây là một **Admin Dashboard** đầy đủ cho hệ thống **Smart Locker** với:
- ✅ Quản lý tủ khóa
- ✅ Quản lý người dùng
- ✅ Xem nhật ký hoạt động
- ✅ Duyệt yêu cầu
- ✅ Theme tối/sáng
- ✅ Responsive mobile
- ✅ Firebase real-time sync
- ✅ Export dữ liệu CSV