# Tool tải truyện tranh (manga / manhwa / manhua)

Có 2 công cụ:

| File | Dùng khi nào | Độ ổn định |
|---|---|---|
| **`auto_dl.py`** | **Đưa link bất kỳ → tự phân tích, tự chẩn đoán.** Tải được thì tải, không thì dừng kèm lý do | ⭐ Điểm vào "mọi trang" |
| **`mangadex_dl.py`** | Tải từ **MangaDex** qua API chính thức (kèm DoH vượt chặn DNS) | ⭐ Rất ổn định — **khuyên dùng** |
| **`truyenqq_dl.py`** | Trang VN kiểu **TruyenQQ / NetTruyen** (HTTP thuần, không cần trình duyệt) | ⭐ Nhanh, ổn định |
| **`kunmanga_dl.py`** | Họ site **zinmanga / kunmanga** (SPA, chương + ảnh qua API) | ⭐ Lấy đủ chương qua API |
| **`comix_dl.py`** | **comix.to** (SPA chống cào: token ký số + mã hóa + xáo ảnh) — điều khiển trình duyệt | Tự thích nghi: ảnh thường **tải thẳng (nhanh)**, ảnh bị xáo thì **chụp màn hình** |
| **`mangafire_dl.py`** | Trang **chặn Cloudflare** (vd mangafire.to) — điều khiển Chrome thật qua CDP | Vượt được CF nếu bạn tự qua, nhưng site có thể rate-limit |
| `manga_dl.py` | Trang bất kỳ khác, quét tổng quát bằng trình duyệt thật (Playwright) | Heuristic, không đảm bảo 100% |

**Có giao diện:** chạy `python gui.py` (hoặc bấm đôi `run_gui.bat`) để dùng bằng cửa sổ, gộp cả 4 nguồn.

> Chỉ dùng cho mục đích cá nhân và tuân thủ điều khoản của từng trang.

---

## 0. `auto_dl.py` — tự động (mọi trang), tự chẩn đoán ⭐

Đưa **link bất kỳ**, tool tự làm: định tuyến (MangaDex → tool riêng), thử đọc
HTML tĩnh, **chẩn đoán** (tìm chương + ảnh, tải thử 1 ảnh thật để kiểm tra). Nếu
ổn → tải cả bộ; nếu **không tải được → in lý do rõ ràng rồi DỪNG** (exit code 2),
không chạy mò ra rác.

```powershell
# Chi CHAN DOAN (khong tai) - xem thu co tai duoc khong
python auto_dl.py "<link>" --check

# Tai (tu nhan dien)
python auto_dl.py "https://truyenqqko.com/truyen-tranh/...-13507"
python auto_dl.py "<link>" --range 1 20 --format folder cbz pdf
```

Kết quả chẩn đoán mẫu:
```
================ CHAN DOAN ================
  Ket qua  : TAI DUOC ✔
  Loai     : series
  Tieu de  : Đại Pháp Sư Toàn Năng
  So chuong: 175
  Anh/chuong dau: 192 | tai thu: 98891 bytes, OK
===========================================
```

**Dự phòng tự động (mặc định bật):** khi HTTP tĩnh thất bại, `auto_dl` **tự chuyển
sang trình duyệt**:
- Trang cần **JavaScript** → tự chạy **Playwright** (`manga_dl.py`), tự mở trình
  duyệt render rồi trích ảnh — không cần thao tác tay.
- Trang **Cloudflare** mà bạn **đã mở sẵn Chrome gỡ lỗi** (cổng 9222, đã vượt CF)
  → tự dùng **CDP** (`mangafire_dl.py`). Nếu chưa, nó mở Playwright ở chế độ hiện
  cửa sổ để bạn tự vượt CF.

Tắt dự phòng: thêm `--browser off` (hoặc bỏ tích ô trong giao diện).

> ⚠️ **Giới hạn thực tế:** vẫn không đảm bảo *mọi* trang — trang chống bot mạnh
> (như mangafire khi bị rate-limit) có thể vẫn bó tay. Khác biệt là `auto_dl`
> **luôn cho biết rõ lý do** thay vì treo/tải rác.

---

## A. `mangadex_dl.py` — tải từ MangaDex (khuyên dùng)

MangaDex có API mở nên tải rất ổn. Nhà mạng VN hay chặn DNS MangaDex → tool **tự
nhúng DNS-over-HTTPS (Cloudflare 1.1.1.1)** để vẫn vào được, **không cần đổi DNS
máy, không cần VPN, không cần trình duyệt**.

### Cài đặt
```powershell
pip install Pillow        # chi can neu muon xuat PDF; CBZ/folder thi khong can gi
```

### Dùng
```powershell
# Tim theo ten roi tai ca bo (mac dinh tieng Anh)
python mangadex_dl.py "search:grapara"

# Tai bang link hoac ID truyen
python mangadex_dl.py https://mangadex.org/title/<id>/...
python mangadex_dl.py c384faed-e34c-4ee0-bd38-70ce5ff146c7

# Chi LIET KE chuong (chua tai) de xem truoc
python mangadex_dl.py <id> --list

# Chon dinh dang, gioi han, ngon ngu
python mangadex_dl.py <id> --format folder cbz pdf --limit 5 --lang en
```

### Tùy chọn chính
| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `--lang` | Ngôn ngữ bản dịch (`en`, `vi`, `ja`...) | `en` |
| `--format` | `folder` `cbz` `pdf` (chọn nhiều) | `folder cbz` |
| `--out` | Thư mục lưu | `downloads` |
| `--list` | Chỉ liệt kê chương, không tải | |
| `--limit` | Chỉ tải N chương (0 = tất cả) | `0` |
| `--start` | Bắt đầu từ chương thứ mấy (0-based) | `0` |
| `--pick` | Chọn kết quả thứ mấy khi `search:` | `0` |
| `--all-groups` | Giữ cả các bản dịch trùng (nhiều nhóm) | tắt |
| `--data-saver` | Tải ảnh nén nhẹ (nhỏ hơn) | tắt |
| `--overwrite` | Tải lại chương đã có | tắt |

Tải lại lần sau sẽ **tự bỏ qua chương đã tải** (resume được).

---

## B. `truyenqq_dl.py` — trang Việt Nam (TruyenQQ / NetTruyen)

Các trang kiểu TruyenQQ/NetTruyen trả HTML có sẵn link ảnh nên tải bằng **HTTP
thuần, không cần trình duyệt**. Tool tự gửi `Referer` để vượt chặn hotlink và
lọc bỏ ảnh quảng cáo / avatar bình luận.

### Cài đặt
```powershell
pip install Pillow      # chi can neu muon xuat PDF
```

### Dùng
```powershell
# Tai ca bo (dan link trang bo truyen)
python truyenqq_dl.py "https://truyenqqko.com/truyen-tranh/dai-phap-su-toan-nang-13507"

# Chi tai 1 chuong
python truyenqq_dl.py "https://truyenqqko.com/.../...-chap-1"

# Tai 1 day chuong (theo so chuong) + xuat them PDF
python truyenqq_dl.py "<link-bo>" --range 1 20 --format folder cbz pdf
```

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `--range A B` | Chỉ tải chương trong khoảng số [A..B] | |
| `--limit` | Chỉ tải N chương đầu (0 = tất cả) | `0` |
| `--format` | `folder` `cbz` `pdf` | `folder cbz` |
| `--overwrite` | Tải lại chương đã có | tắt |

> Hoạt động tốt với truyenqqko.com và các bản sao/đổi tên miền cùng cấu trúc.
> Trang khác cấu trúc có thể cần chỉnh — báo mình link cụ thể.

---

## C. `mangafire_dl.py` — trang chặn Cloudflare (điều khiển Chrome thật qua CDP)

Dùng cho trang như **mangafire.to** mà bot bị Cloudflare chặn. Ý tưởng: **chính
trình duyệt thật của bạn** vượt Cloudflare (cookie `cf_clearance` + TLS thật),
tool nối vào Chrome đó qua CDP và **lấy body ảnh từ Network domain của Chrome**
(bỏ qua được CORS, ít tạo request lạ).

### Cài đặt
```powershell
pip install websocket-client      # Pillow neu muon PDF
```

### Chuẩn bị (mỗi lần dùng)
1. Đóng hết Chrome đang mở.
2. Mở Chrome kèm cổng gỡ lỗi (PowerShell):
   ```powershell
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" `
     --remote-debugging-port=9222 --user-data-dir=C:\chrome-debug-profile
   ```
3. Trong cửa sổ đó, vào trang truyện và **tự vượt Cloudflare** đến khi thấy ảnh.

### Dùng
```powershell
# Tai dung chuong dang mo trong tab
python mangafire_dl.py

# Navigate toi 1 chuong roi tai
python mangafire_dl.py --url "https://mangafire.to/read/grapara.9jlp8/en/chapter-1"

# Tai 1 DAY chuong (URL co dang .../chapter-1 -> tu tang so)
python mangafire_dl.py --url ".../chapter-1" --range 1 20 --name "GraPara"
```

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `--url` | Link chương để mở (bỏ trống = dùng tab hiện tại) | |
| `--range A B` | Tải dãy chương, tự tăng số trong `.../chapter-N` | |
| `--name` | Tên thư mục bộ truyện | |
| `--format` | `folder` `cbz` `pdf` | `folder cbz` |
| `--delay` | Nghỉ giữa các chương (giây) — tránh rate-limit | `3.0` |
| `--port` | Cổng gỡ lỗi Chrome | `9222` |

> ⚠️ **Giới hạn:** nhiều trang (mangafire) cố tình **rate-limit (lỗi 1015)** để
> chặn tải hàng loạt. Nếu bị, hãy tăng `--delay`, tải ít chương mỗi lần, hoặc
> đổi IP (4G/VPN) rồi vượt lại Cloudflare. Nếu ảnh bị **xáo trộn (scramble)** thì
> cần thêm bước chụp canvas — báo mình nếu gặp.

---

## D. `manga_dl.py` — quét tổng quát trang bất kỳ (Playwright)

Dùng cho trang ngoài MangaDex. Mở link bằng Chromium thật, tự cuộn nạp hết ảnh,
đọc source lấy link ảnh. **Heuristic — không đảm bảo mọi trang.** Nhiều trang
(vd mangafire) chặn Cloudflare / rate-limit nên có thể không tải hàng loạt được.

### Cài đặt
```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

### Dùng
```powershell
python manga_dl.py "https://link-bo-truyen"             # tai ca bo
python manga_dl.py "https://link-mot-chuong" --mode chapter
python manga_dl.py "https://..." --format folder cbz pdf --limit 5 --headful
```

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `--mode` | `auto` / `series` / `chapter` | `auto` |
| `--format` | `folder` `cbz` `pdf` | `folder cbz` |
| `--limit` | Chỉ tải N chương đầu (0 = tất cả) | `0` |
| `--headful` | Hiện trình duyệt (xem / vượt captcha) | tắt |
| `--overwrite` | Tải lại chương đã có | tắt |

---

## Đọc truyện trên Google Drive (TruyenDrive)

Tool có thể **tự đẩy truyện đã tải lên Google Drive** để đọc mọi nơi bằng
[TruyenDrive](https://github.com/zennomi/truyendrive) (userscript biến thư mục
Drive thành trình đọc truyện). Cấu trúc `folder` mà tool xuất ra đã đúng chuẩn
TruyenDrive cần.

### Thiết lập 1 lần
```powershell
winget install Rclone.Rclone          # cai rclone (neu chua co)
# Mo terminal MOI roi cau hinh remote Google Drive:
rclone config
#  n  -> ten: gdrive  -> chon 'drive' -> Enter qua client_id/secret
#  scope: 1 (full)    -> Enter... -> y (dang nhap trinh duyet) -> dang nhap Google
#  -> n (khong phai team drive) -> y -> q (thoat)
```

### Dùng
- **Giao diện:** bấm **"☁ Chọn truyện đẩy lên..."** → hiện danh sách bộ truyện, **tích
  chọn bộ muốn đẩy** (không đẩy hết) → **Đẩy lên**. Hoặc tích **"Tải xong thì hỏi đẩy
  lên Drive"** để sau khi tải tự mở hộp chọn.
- **Dòng lệnh** (đẩy một hoặc nhiều bộ):
  ```powershell
  python upload_drive.py "downloads/Tên Truyện A" "downloads/Tên Truyện B" --remote drive --dest Manga
  ```

**Chỉ đẩy định dạng đọc được:** tool tự **bỏ qua `.cbz/.pdf`** và **ảnh ghép liền**,
chỉ đẩy **thư mục chương chứa ảnh** — đúng thứ TruyenDrive cần. (Nên tải với định
dạng **`folder`** nếu định đọc trên Drive.)

rclone **chỉ đẩy phần mới** (đã có thì bỏ qua), nên chạy lại nhiều lần rất nhanh.

Sau đó: mở thư mục đó trên Google Drive → bấm nút **TruyenDrive** → đọc.

---

## Các định dạng xuất (`--format`)

Mỗi chương trên web vốn là **nhiều ảnh trang rời** — tool tải hết rồi đóng gói theo
kiểu bạn chọn (chọn được nhiều kiểu cùng lúc):

| Kiểu | Kết quả | Dùng khi |
|---|---|---|
| `folder` | nhiều ảnh rời `001.jpg, 002.jpg...` | muốn lấy/sửa từng trang |
| `cbz` | **1 file/chương** (zip ảnh) | đọc bằng app truyện, gọn gàng |
| `pdf` | 1 file/chương (mỗi ảnh 1 trang) | đọc/in mọi thiết bị, không cần app |
| `stitch` | **ghép liền mạch** thành ảnh dài (chương dài tự cắt thành vài mảnh `_p01, _p02`) | manhwa/webtoon cuộn dọc — **bỏ khoảng trắng giữa các trang** |

### CBZ là gì?
`.cbz` chỉ là **file nén (zip) chứa ảnh các trang theo thứ tự**. Mở bằng app đọc
truyện (CDisplayEx, YACReader, Tachiyomi/MIHON...) hoặc **đổi đuôi `.cbz` → `.zip`**
rồi giải nén để xem ảnh bình thường.

### Bị "khoảng trắng" giữa các trang?
Đó là chỗ nối giữa các ảnh trang (web chia chương thành mảnh). Hai cách bỏ:
1. **Trong app đọc:** bật chế độ **Webtoon / Continuous / cuộn liền** (CDisplayEx,
   YACReader, MIHON/Tachiyomi đều có) — app dán các trang sát nhau.
2. **Xuất kiểu `stitch`** (ô "Ghép liền" trong giao diện): nối sẵn thành ảnh dài
   liền mạch, không còn khe.
