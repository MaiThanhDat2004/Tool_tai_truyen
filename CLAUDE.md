# CLAUDE.md

Hướng dẫn cho Claude Code khi làm việc trong dự án này.

## Dự án là gì
Bộ công cụ Python tải truyện tranh (manga/manhwa/manhua) từ nhiều nguồn, có GUI.
Trọng tâm là **các kỹ thuật "lách" rào cản** của từng trang (chặn DNS, Cloudflare,
SPA chống cào, xáo trộn ảnh...).

- Đọc [THUAT_TOAN.md](THUAT_TOAN.md) trước khi sửa logic tải của một trang — nó tổng
  hợp bài toán + cách giải cho từng site. **Cập nhật file đó khi thêm/sửa kỹ thuật.**
- [README.md](README.md) là hướng dẫn cho người dùng cuối.

## NGUYÊN TẮC BẮT BUỘC (QUAN TRỌNG NHẤT)
1. **Tuân thủ đúng yêu cầu chỉ định**: Tuyệt đối KHÔNG tự tiện can thiệp hoặc chỉnh sửa bất kỳ file nào khi chưa được phép; nếu thấy cần sửa phải hỏi trước.
2. **Đối chiếu commit trước khi sửa logic**: Khi cần sửa logic, bắt buộc phải xem lại commit lịch sử (`git log`, `git diff`) để đối chiếu thật kỹ rồi mới chỉnh sửa.

## Môi trường (QUAN TRỌNG)
- **Windows**, shell PowerShell. Chạy Python qua **venv**:
  `./.venv/Scripts/python.exe ...` (Bash dùng `/`, PowerShell dùng `.\.venv\Scripts\python.exe`).
- venv đã có: `websocket-client`, `Pillow`, `playwright` (+ chromium đã `playwright install`).
- DNS hệ thống đã đổi sang **Cloudflare 1.1.1.1** (interface index 12). Khôi phục:
  `Set-DnsClientServerAddress -InterfaceIndex 12 -ResetServerAddresses` (cần admin).
- **Console cp1252** không in được tiếng Việt/emoji → mọi tool tự `sys.stdout.reconfigure(utf-8)`.
  Khi test bằng `python -c`, in tên file tiếng Việt sẽ lỗi — né bằng cách in ASCII/độ dài.
- Chrome debug (cho mangafire/CDP): profile `C:\chrome-debug-profile`, cổng `9222`.
- Truyện người dùng lưu ở `D:\tai_truyen` (không phải `downloads/` mặc định).

## Bản đồ file
| File | Vai trò |
|---|---|
| `auto_dl.py` | **Điểm vào "mọi trang"**: định tuyến + chẩn đoán + dự phòng Playwright |
| `mangadex_dl.py` | MangaDex qua API, **nhúng DoH** vượt chặn DNS |
| `truyenqq_dl.py` | Trang VN (TruyenQQ/NetTruyen), HTTP thuần. **Cũng là thư viện** (auto/kunmanga/comix import `make_cbz/make_pdf/slugify/http/origin`) |
| `kunmanga_dl.py` | Họ zinmanga/kunmanga (SPA, chương+ảnh qua API/HTML) |
| `zettruyen_dl.py` | zettruyen.club (zinmanga, URL VN `/truyen-tranh/<slug>/chuong-N`): chương qua API `/api/comics/<slug>/chapters`, ảnh `cdn*.zetimage.com/<slug>/<num>/<page>` đọc từ HTML chương. HTTP thuần |
| `dilib_dl.py` | dilib.vn (Angular SPA, ảnh `/img/comic/...` nhúng sẵn trong HTML). **Server bắt buộc `Accept-Encoding: gzip`** (thiếu → body rỗng) → có `http()` gzip riêng |
| `manhwahub_dl.py` | manhwahub.net (HTML tĩnh): chương `/webtoon/<slug>/chapter-N`, ảnh `cdn.manhwahub.net/<id>/<num>/<NN>a` nhúng sẵn (webp dù URL .jpg → detect magic bytes). HTTP thuần |
| `manga18_dl.py` | manga18.me (HTML tĩnh, ~y hệt manhwahub): chương `/manga/<slug>/chapter-N`, ảnh `img-r2.manga18.me/uploads/<id>/<num>/<page>-<hash>.jpg` nhúng sẵn. HTTP thuần. **18+** |
| `toongod_dl.py` | toongod.org (Madara sau **Cloudflare**): Chrome thật vượt CF **1 lần** → hứng cookie `cf_clearance`+UA → **tải HTTP** (cookie tái dùng được). Ảnh `i.tngcdn.com` chỉ cần Referer. Import `ensure_chrome`+`CDP`. Export `get_cf_session`+`http` cho site CF khác |
| `manhwaread_dl.py` | manhwaread.com (CF, dùng `get_cf_session`/`http` của toongod). Ảnh nhúng trong biến JS `chapterData={data:base64([{src}]),base:...}` → URL=base+/+src; webp dù .jpg; CDN `manread.xyz` cần Referer |
| `asurascans_dl.py` | asurascans.com (HTML tĩnh, ~khuôn manhwahub): chương `/comics/<slug>/chapter/N`, ảnh `cdn.asurascans.com/asura-images/...` nhúng sẵn. HTTP thuần + **dự phòng CF** (tự mượn cookie nếu gặp "Just a moment") |
| `lagoonscans_dl.py` | lagoonscans.com (WordPress/Madara): chương phẳng `<slug>-chapter-N/`, ảnh trong JS **`ts_reader.run({sources:[{images:[...]}]})`** → parse JSON. webp, cần Referer. HTTP thuần |
| `kaynscan_dl.py` | kaynscan.org (SPA): chương `/series/<slug>/chapter-N`, ảnh nằm sẵn HTML tĩnh `storage.kaynscan.org/.../page-NNNN_*.webp` (phân biệt ảnh trang = có `/page-`). HTTP thuần, Referer. Bẫy: tab CDP nền KHÔNG lazy-load |
| `mangafire_dl.py` | mangafire.to: chống bot đá-về-home + API ký `vrf` → **chrome.exe mở tay** + CDP thuần (KHÔNG `Runtime.evaluate`), hứng response API đã ký. Có `ensure_chrome` |
| `webtoon_dl.py` | webtoons.com (chính thống): tên miền chính bị **RST/SNI** → Chrome thật vượt; ảnh tải thẳng CDN + retry. Import `ensure_chrome` từ mangafire_dl |
| `comix_dl.py` | comix.to (chống cào nặng + xáo ảnh) → điều khiển trình duyệt |
| `manga_dl.py` | Quét tổng quát trang bất kỳ (Playwright) |
| `pack.py` | `make_stitch` — ghép ảnh 1 chương thành ảnh dài liền mạch |
| `to_excel.py` | Xuất 1 chương ra `.xlsx`: mỗi trang 1 hàng (cột A số trang, B ảnh nhúng-thumbnail, C review). Review từ JSON `--reviews`. openpyxl + Pillow |
| `terabox_dl.py` | Tải 1 file từ link share Terabox/1024tera. File lớn bắt buộc **đăng nhập** (reCAPTCHA+tường login). Mở chrome.exe thật (debug 9222) cho user đăng nhập 1 lần → hứng cookie `ndus`+UA, hứng `dlink` qua CDP, tải HTTP resume theo `Range`. Import `ensure_chrome` |
| `manga_edit.py` | **"Đôi tay"** chỉnh sửa trang: xóa chữ (clear) + đặt lời thoại (typeset). Model-agnostic, nhận script JSON `[{box,text,fill,align,upper}]`. Clear: `white`(bong bóng) / `#hex`(vd `#000000` chữ trắng nền đen) / `auto`(inpaint đúng nét chữ) / `box`(inpaint cả ô). Typeset: auto-wrap+auto cỡ+viền trắng. Cần OpenCV cho inpaint content-aware. Font Arial (có dấu VN). Chế độ thư mục: **copy trang không có script (trang tranh) → chương liền mạch**. `--pack-cbz` đóng gói thư mục đã sửa thành `.cbz` |
| `manga_translate.py` | **"Bộ não"**: OCR đa ngôn ngữ (EasyOCR offline: ja/ko/ch_sim/ch_tra/en/vi) → gộp box theo bong bóng → xuất script JSON cho `manga_edit.py`. Dịch `--manual`(sửa tay) / `--auto`. **`translate_text()` dùng chung — dịch MIỄN PHÍ không cần Claude: argos-translate (OFFLINE) → deep-translator (Google free) dự phòng**. Đoán `fill` theo độ sáng vùng |
| `manga_box_editor.py` | **Khoanh vùng BẰNG TAY** (Tkinter canvas): kéo vẽ box + gõ thoại, nạp sẵn box OCR để chỉnh. **Kéo trong ô = di chuyển, kéo góc = resize; tự đoán `fill` theo độ sáng vùng; Space = live-preview render (import `manga_edit`); nút 🌐 Dịch ô/cả trang (gọi `manga_translate.translate_text` — offline, không cần Claude)**. Fit-width + cuộn dọc cho webtoon cao. Tọa độ lưu theo **ảnh gốc** (qua `scale`). Xuất script JSON như `manga_translate`. Prev/Next cả chương. Dùng `ImageTk` |
| `upload_drive.py` | Đẩy truyện lên Google Drive qua rclone (để đọc bằng TruyenDrive) |
| `gui.py` + `run_gui.bat` | Giao diện Tkinter, gọi các tool CLI qua subprocess |

## Quy ước chung (giữ nhất quán khi sửa)
- **Cấu trúc xuất:** `<out>/<Tên bộ>/<NNNN - Chuong X>/<NNN>.<ext>` + đóng gói `.cbz/.pdf`.
  Thư mục chương đệm 4 số, ảnh đệm 3 số → sắp xếp A→Z đúng (hợp TruyenDrive).
- **Định dạng (`--format`):** `folder` `cbz` `pdf` `stitch` (chọn nhiều). `stitch` = `pack.make_stitch`.
- **Đặt tên file CẨN THẬN với dấu chấm:** tên chương có thể chứa `.` (vd "Ch 3.5") →
  **KHÔNG dùng `Path.with_suffix(".cbz")`** (nó cắt sai). Dùng `dir.parent / (dir.name + ".cbz")`.
- **Resume (tiếp tục sau khi dừng đột ngột) — 2 tầng, dùng chung qua `truyenqq_dl`:**
  - *Cấp chương:* `<out>/<bộ>/.progress.json` ghi tên thư mục các chương ĐÃ XONG →
    bỏ qua nhanh, KHÔNG mở lại trình duyệt. (`tq.progress_load/progress_save`; vẫn nhận
    `.cbz` tồn tại làm dấu tương thích cũ.) Đánh dấu CHỈ sau khi đóng gói xong.
  - *Cấp ảnh (giữa chương):* trước khi tải ảnh i, `tq.have_page(ch_dir, i, pad)` kiểm tra
    ảnh đã có chưa → bỏ qua. Ghi ảnh bằng `tq.write_atomic` (`.part`→rename) nên không
    bao giờ còn file dở. `--overwrite` để tải lại từ đầu.
  - `.progress.json`/`.part` được loại khỏi upload Drive.
- **CLI thống nhất:** mỗi tool có `--out --format --limit --range A B`; nhiều tool có `--check`, `--list`.
- **Số chương:** lấy qua regex `chap/chuong/chapter[-_/](\d+)` để **tránh vớ phải ID truyện** trong URL.
- **Tải ảnh:** thường cần header `Referer = origin`. Kiểm tra ảnh hợp lệ bằng magic bytes / `len > 800`.
- **Tải 1 chương dùng chung `tq.download_images(urls, ch_dir, getter, min_size=…)`** — lo resume
  (have_page) + ghi nguyên tử + ext theo magic bytes + **thanh tiến trình 0→100% (icon sách lật trang
  📖📗📘📙📕 → 📚✓)**. `getter(url)` trả bytes (mỗi tool truyền lambda với http riêng). Terminal: thanh
  động `\r`; GUI/pipe (`isatty()` False): in ~5 mốc %. Mọi tool download_chapter chỉ là wrapper gọi nó.

## Cách chạy nhanh
```bash
# CHẨN ĐOÁN (không tải) — nên chạy trước với trang lạ
./.venv/Scripts/python.exe auto_dl.py "<link>" --check

# Tải
./.venv/Scripts/python.exe auto_dl.py "<link>" --limit 5 --out "D:/tai_truyen"
./.venv/Scripts/python.exe mangadex_dl.py "search:tên" --list

# GUI
./.venv/Scripts/python.exe gui.py
```

## Lưu ý khi test (các tool dùng trình duyệt thì CHẬM)
- comix.to / mangafire / manga_dl render từng trang → **chạy nền** (`run_in_background`)
  rồi dùng Monitor đợi, đừng chặn.
- Verify ảnh đúng: lưu 1 ảnh ra rồi **dùng Read (xem ảnh)** để mắt thường kiểm tra —
  đặc biệt với trang nghi bị xáo trộn.
- Sau khi test: **xóa thư mục/log tạm** (`_t*`, `*.log`, `test_*`).

## comix.to — cạm bẫy hay quên (xem THUAT_TOAN.md mục 5)
- Click bị overlay quảng cáo chặn → click bằng JS (`page.evaluate`), không dùng `.click()`.
- Reader ảo hóa (3 ảnh/DOM) + nút "Go to page N" trong menu Settings (đóng sau mỗi click).
- Bắt **MỌI** request (image + fetch) vì vài trang là blob.
- `capture_chapter` **tự thích nghi từng trang**: img CDN→tải thẳng; blob→fetch; canvas/lỗi→**screenshot**
  (bản đã giải xáo). Có fallback chụp → không sót trang.
- `--check` báo số chương thật + bộ có bị xáo không (xem phần tử hiển thị là canvas/blob hay img).

## Khi thêm một trang mới
1. `--check`/soi thử: HTML tĩnh có chương+ảnh không? Có API? Có Cloudflare? Ảnh có cần Referer?
2. Ưu tiên HTTP tĩnh > API > trình duyệt (chậm nhất).
3. Nếu cần trình duyệt và ảnh bị mã hóa/xáo → **đọc kết quả render**, đừng giải mã.
4. Thêm định tuyến trong `auto_dl.py` (host hoặc dấu hiệu API).
5. **Ghi kỹ thuật mới vào THUAT_TOAN.md.**
