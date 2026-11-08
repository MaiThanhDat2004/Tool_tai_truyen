---
name: strict-logic-guard
description: Quy trình kiểm soát thay đổi logic và can thiệp file: đối chiếu git commit trước khi sửa logic, không tự ý chỉnh sửa file khi chưa được hỏi và cho phép.
---

# Kỹ năng Kiểm soát Logic & Phạm vi Can thiệp (Strict Logic & Scope Guard)

Kỹ năng này áp dụng cho toàn bộ hoạt động lập trình và bảo trì trong dự án.

## 1. Nguyên tắc không tự tiện can thiệp file (No Unauthorized File Edits)
- **Chỉ sửa các file được người dùng trực tiếp yêu cầu**: Nếu người dùng yêu cầu sửa file A, chỉ tập trung vào file A.
- **Không tự ý sửa các file khác**: Nếu nhận thấy cần sửa thêm file B hoặc file cấu hình, quy tắc là:
  1. Dừng lại, không được tự động sửa.
  2. Nêu rõ nguyên nhân vì sao cần sửa file B.
  3. Chờ người dùng xác nhận và đồng ý trước khi can thiệp.

## 2. Quy trình đối chiếu commit trước khi sửa logic (Git Cross-Reference Protocol)
Trước khi thay đổi bất kỳ đoạn logic nào (thuật toán, tham số CLI, routing link, cơ chế resume, xử lý mạng, CDP, v.v.):
1. **Kiểm tra lịch sử commit**:
   - Chạy `git log -p -n 3 <file>` hoặc `git show <commit>:<file>` để xem logic gốc hoạt động như thế nào và tại sao lại được thiết kế như vậy.
2. **Đánh giá rủi ro**:
   - Đối chiếu với tài liệu `THUAT_TOAN.md` và `README.md` xem logic đó có đang giải quyết vấn đề chống bot / chặn DNS / định dạng đặc biệt nào không.
3. **Báo cáo và xin phép**:
   - Giải thích ngắn gọn logic hiện tại là gì, logic dự kiến thay đổi là gì, có rủi ro nào không, và xin ý kiến người dùng trước khi áp dụng.

