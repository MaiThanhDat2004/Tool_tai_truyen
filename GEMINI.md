# QUY TẮC BẮT BUỘC KHI PHÁT TRIỂN DỰ ÁN (PROJECT GOVERNANCE RULES)

## 1. TUÂN THỦ NGHIÊM NGẶT PHẠM VI YÊU CẦU (STRICT SCOPE)
- Chỉ thực hiện chính xác những việc người dùng chỉ định.
- **TUYỆT ĐỐI KHÔNG TỰ TIỆN CHỈNH SỬA BẤT KỲ FILE NÀO** khi chưa có sự yêu cầu hoặc cho phép của người dùng.
- Nếu phát hiện vấn đề cần chỉnh sửa file khác, **BẮT BUỘC PHẢI HỎI Ý KIẾN VÀ ĐƯỢC NGƯỜI DÙNG ĐỒNG Ý TRƯỚC** rồi mới được can thiệp.

## 2. NGUYÊN TẮC BẢO TOÀN VÀ ĐỐI CHIẾU LOGIC (STRICT LOGIC GUARD)
- Khi muốn hoặc được yêu cầu thay đổi bất kỳ logic nào trong code:
  1. **BẮT BUỘC ĐỐI CHIẾU VỚI LỊCH SỬ COMMIT**: Dùng `git log`, `git show`, `git diff` kiểm tra lại logic gốc ban đầu thật kỹ càng.
  2. Xem xét kỹ sự tương thích với các module khác (crawler, anti-bot, headless browser, CDP, parser).
  3. Tuyệt đối không tự ý viết lại hoặc xóa bỏ logic sẵn có khi chưa đối chiếu và chưa được người dùng phê duyệt.

