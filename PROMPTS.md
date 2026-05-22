# PROMPTS.md — Thư viện Prompt Cá Nhân

---

## 🗣 Style mặc định (dán đầu mọi chat)

```
Trả lời súc tích nhất có thể. Bỏ lời chào, tóm tắt câu hỏi, cụm "Rất vui được...", "Để giải thích...". Dùng câu ngắn. Nếu cần gọi công cụ, gọi trước rồi chỉ hiển thị kết quả.
```

---

## 📄 Tóm tắt tài liệu

```
Đọc tài liệu này từ đầu đến cuối. Xuất ra văn bản thuần súc tích, giữ lại:
(1) mọi dữ kiện, con số, ngày tháng, tên
(2) mọi hướng dẫn hoặc khuyến nghị
(3) cấu trúc tài liệu dưới dạng tiêu đề ngắn
Bỏ câu dẫn, ngữ cảnh lặp, ngôn ngữ marketing, dấu trang và chân trang.
Mục tiêu 20–30% độ dài gốc.
```

---

## 🔁 Tóm tắt ngữ cảnh cuộc trò chuyện

```
Tóm tắt toàn bộ cuộc trò chuyện này để dán vào chat mới mà không mất ngữ cảnh. Gồm:
(1) mục tiêu ban đầu
(2) các quyết định đã đưa ra và lý do
(3) code / cấu hình / dữ liệu đã chốt
(4) câu hỏi còn mở và bước tiếp theo
Dùng tiêu đề ngắn.
```

---

## 🐛 Debug

```
Debug:
- Lỗi: [paste error]
- File: [tên file]
- Đã thử: [nếu có]
```

---

## ✏️ Refactor

```
Refactor: [tên hàm / đoạn code]
- [yêu cầu 1]
- [yêu cầu 2]
Constraint: [ngôn ngữ / framework]

[paste code]
```

---

## ➕ Thêm tính năng

```
Thêm vào [file]:
- [tính năng]
- Input: [mô tả]
- Output: [mô tả]
Không thay đổi logic hiện có.
```

---

## 📝 Review code

```
Review đoạn code này:
- Tìm bug tiềm ẩn
- Gợi ý tối ưu performance
- Chỉ ra code smell nếu có
Trả về danh sách ngắn, không rewrite toàn bộ.

[paste code]
```
## 📊 Kiểm tra dung lượng
Đánh giá độ dài ngữ cảnh cuộc trò chuyện hiện tại. Đã đến mức quá tải và cần tóm tắt chưa? Chỉ trả lời "Cần backup ngay" hoặc "Chưa cần".