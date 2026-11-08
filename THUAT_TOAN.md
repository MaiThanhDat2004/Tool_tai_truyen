# Thuật toán "lách" cho từng trang truyện

Tài liệu này tổng hợp **bài toán khó của từng trang** và **cách giải quyết** đã dùng
trong bộ tool. Mục đích: nhớ lâu kỹ thuật, lần sau gặp trang tương tự áp dụng ngay.

> **Nguyên tắc vàng:** Khi trang chống cào bằng mã hóa/ký token → **KHÔNG đảo ngược
> thuật toán** (mong manh, họ đổi là gãy). Thay vào đó **để chính trình duyệt chạy
> JS của trang** (nó tự ký/giải mã/giải xáo), mình chỉ **thu hoạch kết quả đã render**.
> Đây là cách yt-dlp và các tool bền vững vẫn làm.

---

## 0. Bộ định tuyến tự động (`auto_dl.py`)

Đưa link bất kỳ → tự phân tích và chọn công cụ:

```
URL vào
 ├─ host chứa "mangadex"      → mangadex_dl.py (API + DoH)
 ├─ có /api/comics/<slug>/... → kunmanga_dl.py (họ zinmanga)
 ├─ host chứa "comix.to"      → comix_dl.py (điều khiển trình duyệt)
 ├─ đọc HTML tĩnh ra ảnh+chương → tải thẳng (kiểu truyenqq)
 └─ không ra gì → CHẨN ĐOÁN → dự phòng Playwright; nếu vẫn bó tay → DỪNG + nêu lý do
```

**Chẩn đoán (probe) trước khi tải:** tìm danh sách chương + ảnh, **tải thử 1 ảnh
thật**, kiểm tra magic bytes (đúng là ảnh). Tải được → tải cả bộ; không → in lý do
(Cloudflare / cần JS / chặn hotlink / không thấy ảnh) rồi dừng (exit 2).

---

## 1. MangaDex — bị nhà mạng chặn DNS

**Bài toán:** ISP Việt Nam đầu độc DNS: `api.mangadex.org` phân giải về `::1`
(localhost) → không vào được. Đổi DNS hệ thống thì phiền/cần admin.

**Giải pháp — DNS-over-HTTPS nhúng trong tool:**
1. Tự phân giải tên miền `*.mangadex.org` / `*.mangadex.network` qua **Cloudflare
   DoH** (`https://1.1.1.1/dns-query`, header `accept: application/dns-json`).
   → DoH server là **IP literal `1.1.1.1`** nên không cần DNS để gọi nó (cert có SAN IP).
2. **Vá `socket.getaddrinfo`**: khi Python phân giải các host MangaDex, trả về IP
   thật lấy từ DoH; host khác giữ nguyên. Nhờ giữ nguyên hostname nên **SNI + chứng
   chỉ TLS vẫn đúng**.
3. Chương: API `/manga/{id}/feed` (paginate 500). Ảnh: `/at-home/server/{chapterId}`
   → `{baseUrl}/data/{hash}/{filename}`.

**Học được:** chặn DNS → DoH + vá resolver, không cần đổi DNS toàn máy.

---

## 2. TruyenQQ / NetTruyen (VN) — HTTP thuần, chặn hotlink

**Bài toán:** ảnh host ở CDN riêng (`hinhhinh.com`), **chặn hotlink** (tải trực
tiếp → 403). Lẫn nhiều ảnh quảng cáo + avatar bình luận.

**Giải pháp:**
1. HTML chương trả **sẵn link ảnh** → không cần trình duyệt.
2. Ảnh nội dung nằm trong `<img class="page-chapter">`; gửi kèm header
   **`Referer: <origin trang>`** → vượt chặn hotlink (403 → 200).
3. **Lọc rác:** bỏ URL chứa `avatar|banner|logo|icon|/ads/|/160x160/avatar`...
   (avatar bình luận hay lẫn vào).
4. Tên bộ lấy từ `<h1>` (sạch hơn `<title>` vì title dính "chương mới nhất N").

**Biến thể đã gặp (cùng `truyenqq_dl.py`):**
- **2 kiểu URL chương:** `...-chap-12.5` (cũ) VÀ `/<slug>/chapter-12-5` (truyenqq.com.vn) —
  ở kiểu sau **decimal dùng dấu `-`**: `chapter-13-5` = chương 13.5. Regex nhận cả hai;
  `chap_number` đổi `-`→`.` để parse.
- **Ảnh lazy `class="lazy"` + `data-src`** (không phải `page-chapter`) → nhánh dự phòng
  của `get_chapter_images` vẫn lấy được (IMG_URL ưu tiên `data-src` http, bỏ qua
  `src="/images/placeholder|loading"` vì là đường dẫn tương đối). CDN vd `s76.static3t.com`.
- **Lọc theo slug bộ** trong `get_chapter_links` → tránh vớ link chương của truyện khác
  ở sidebar (nếu lọc hết sạch thì fallback giữ tất cả, tương thích cũ).
- **Giải mã HTML entity** tên bộ (`strip_tags` dùng `html.unescape`) → `C&#244;` → `Cô`.

**Học được:** trang VN thường dễ — HTML tĩnh + chỉ cần `Referer`. Cùng "engine" nhưng mỗi
mirror đổi chút (URL chương, class ảnh, entity) → nới regex + nhánh dự phòng thay vì viết tool mới.

### 2c. dilib.vn (`dilib_dl.py`) — SPA Angular nhưng ảnh nhúng sẵn + **bắt buộc gzip**
- **Cạm bẫy lớn:** server **chỉ trả nội dung khi request có `Accept-Encoding: gzip`** —
  thiếu → **HTTP 200 nhưng body RỖNG** (size 0). `tq.http` không gửi gzip nên KHÔNG dùng được
  → `dilib_dl.http` riêng: gửi `Accept-Encoding: gzip, deflate` rồi **tự giải nén**
  (`gzip.decompress` / `zlib`). (Bài học: gặp "200 mà rỗng" → thử gzip + headers browser.)
- Tuy là **AngularJS SPA** (`ng-app`) nhưng HTML trang chương **nhúng sẵn** URL ảnh
  `https://dilib.vn/img/comic/<TenComic>/img_NNNNN.webp` (5 chữ số, mỗi chương 1 dải số riêng)
  → đọc thẳng từ HTML, không cần trình duyệt. Cần `Referer`. **Không xáo trộn** (webp ~1000px).
- **URL:** series `/<slug>-<id>.html`; chương `/truyen-tranh/<slug>-<id>-chap-N.html`.
  `<slug>-<id>` lấy bằng regex `/([a-z0-9-]+?-\d+)(?:-chap-…)?\.html`. Danh sách chương từ
  series page (link `-chap-N.html`). (Test "Until Your Bones Rot": 96 chương, ch1=14 trang, sạch.)

### 2d. manhwahub.net (`manhwahub_dl.py`) — HTML tĩnh, dễ
- Chương: HTML tĩnh trang `/webtoon/<slug>` liệt kê `/webtoon/<slug>/chapter-N` (có chương lẻ 102.5).
- Ảnh: nhúng sẵn trong HTML chương — `cdn.manhwahub.net/<id>/<num>/<NN>a.jpg` (webtoon dài, webp).
  **Server trả webp DÙ đuôi URL là `.jpg`** → detect ext bằng magic bytes, đừng tin đuôi URL.
  Lấy ảnh kiểu **gom-theo-thư-mục chọn folder nhiều ảnh nhất** (bỏ thumbnail lạc), sắp theo số trang.
- **Không cần Referer, không cần gzip** (`tq.http` chạy thẳng). Cloudflare bị động.
  (Test "Secret Class": 316 chương, ch1=16 lát, sạch.)

### 2e. manga18.me (`manga18_dl.py`) — gần như y hệt 2d
Cùng kiểu: chương tĩnh `/manga/<slug>/chapter-N`; ảnh nhúng sẵn (img.pN data-src)
`img-r2.manga18.me/uploads/<id>/<num>/<page>-<hash>.jpg` (webtoon dài, jpg); gom-theo-thư-mục
chọn folder nhiều ảnh nhất, sắp theo số trang đầu tên file; không Referer/gzip; `tq.http` chạy thẳng.
(Test "A Dangerous Deal...": 54 chương, ch1=14 lát, sạch.) → 2 site (manhwahub/manga18) gần như
chung một khuôn; nếu gặp site tương tự nữa cân nhắc gộp 1 tool generic "ảnh-nhúng-sẵn".

### 2f. asurascans.com (`asurascans_dl.py`) — cùng khuôn 2d/2e + dự phòng CF
Chương tĩnh `/comics/<slug>/chapter/N`; ảnh nhúng sẵn `cdn.asurascans.com/asura-images/chapters/
<baseslug>/<num>/NNN.webp` (webp; baseslug = slug **bỏ hậu tố hash** `-fc4c7eba`, nhưng cứ đọc
URL thẳng từ HTML là xong); gom-theo-thư-mục, sắp theo số trang; không Referer/cookie. **Khác:**
Asura thi thoảng bật Cloudflare → `fetch()` tự dò "Just a moment", nếu dính thì **mượn cookie qua
`toongod_dl.get_cf_session`** rồi tải lại (dự phòng, hiện chưa cần). (Test "Margrave's Bastard Son":
113 chương, ch1=17 lát, sạch.) → Giờ đã **3 site** chung khuôn "ảnh-nhúng-sẵn" (manhwahub/manga18/asura).

### 2g. lagoonscans.com (`lagoonscans_dl.py`) — Madara reader `ts_reader.run`
WordPress/Madara. Ảnh KHÔNG ở `<img>` mà trong lời gọi JS **`ts_reader.run({...})`** — một mẫu
**rất phổ biến ở các theme Madara**:
```js
ts_reader.run({"sources":[{"images":["url1","url2",...]}], "defaultSource":0, ...});
```
→ regex bắt `ts_reader\.run\((\{.*?\})\);`, `json.loads`, lấy `sources[defaultSource].images`.
Ảnh `wp-content/uploads/...webp` (cần `Referer`), không xáo. Chương: series HTML link **phẳng**
`<slug>-chapter-N/` (KHÁC kiểu `/manga/<slug>/chapter-N`). **Bẫy:** site này chỉ host **chương 97–125**
(yêu cầu chương không tồn tại → 301 về chương khác). (Test "Star-Embracing Swordmaster": 29 chương
(97..125), ch97=16 lát, sạch.) → `ts_reader` đáng nhớ: gặp Madara mà `<img>` rỗng thì **soi
`ts_reader.run`**.

### 2h. kaynscan.org (`kaynscan_dl.py`) — SPA nhưng URL ảnh nằm sẵn HTML; bẫy "tab nền"
- Ảnh content nằm sẵn trong **HTML tĩnh** chương, luôn dưới `storage.kaynscan.org/.../`**`/series/`**`...`.
  **2 KIỂU đặt tên tuỳ bộ** (đừng hard-code 1 kiểu!):
  - `/public/upload/series/<slug>/<uuid>/page-NNNN_*.webp` (Fog Land)
  - `/upload/series/<slug2>/<hash>/NNN.jpg` (Sashimi — KHÔNG có `page-`, không `/public`, slug viết khác)
  → cách robust: lấy **mọi** ảnh storage có `/series/`, **gom theo thư mục, chọn folder nhiều ảnh nhất**
  (= folder trang truyện; logo/cover ở `/public/upload/<date>/` không có `/series/` nên tự loại), sắp
  theo số trong tên (`page-(\d+)` hoặc số đầu `(\d+)`). Cần `Referer`.
- (Bài học chốt: site cùng engine vẫn **đổi quy ước tên file giữa các bộ** → dùng gom-theo-thư-mục
  thay vì regex cứng một mẫu. Lỗi thật đã gặp: bộ Sashimi báo "CHƯA LẤY ĐƯỢC" vì regex chỉ bắt `page-`.)
- **Thứ tự ảnh:** dùng `tq.largest_image_group()` — **giữ NGUYÊN thứ tự xuất hiện trong HTML** (= thứ tự
  reader), KHÔNG đoán số trong tên file (số có thể ở đầu `001` hoặc cuối `...-2-001` → sort theo số dễ loạn).
- **Chương PREMIUM / early-access (member trả phí):** vài bộ (vd Reborn as the Heavenly Demon) khoá
  chương mới cho member → HTML chương **không có ảnh `/series/`** + có marker `"premium chapter is
  waiting"`/`"locked":"Locked Chapter"`/`statusLocked`. Tool **phát hiện (`LockedChapter`) → báo
  `🔒 premium` và BỎ QUA** (KHÔNG vượt paywall — nội dung trả phí). Trước khi sửa: chương khoá thất bại
  âm thầm + xoá thư mục → thư mục nhảy số (0001→0003) trông như "sai thứ tự". (← lỗi user báo, đã fix.)
- Chương: series HTML `/series/<slug>/chapter-N` (có `chapter-0`).
- ⚠️ **2 cú lừa tốn thời gian (đã rút kinh nghiệm):** (1) ban đầu lọc nhầm path nên tưởng "ảnh không
  ở HTML"; (2) thử dùng **tab CDP nền** để render → ảnh **KHÔNG lazy-load** (IntersectionObserver chỉ
  fire khi tab **foreground/visible**) → tưởng nhầm "cần login/bị chặn". Playwright **headed** (cửa sổ
  thật) thì load đủ. **Bài học:** trước khi nghĩ tới browser, GREP kỹ HTML tĩnh cho **mọi** mẫu URL ảnh
  (đừng tin một filter); và tab nền KHÔNG kích hoạt lazy-load. (Test "Fog Land": 21 chương, ch25=33 trang, sạch.)

---

## 3. Họ zinmanga / kunmanga — SPA, API + ảnh nhúng escaped

**Bài toán:** SPA, HTML tĩnh chỉ có 2 link (chương đầu/cuối). Danh sách chương thật
nạp bằng JS. Cảnh báo: link "chương" trong sidebar là của **truyện khác**.

**Giải pháp:**
1. **Chương qua API:** `GET /api/comics/<slug>/chapters?per_page=-1&order=asc`
   → lấy **hết** một lần (per_page=-1). `slug` = phần sau `/manga/`.
2. **Ảnh nằm sẵn trong HTML trang chương** nhưng bị **escape `\/`** (nên regex
   thường trượt). Cách lấy **không đoán mẫu** (vì mỗi bộ một kiểu tên file):
   - `html.replace('\\/', '/')` rồi regex mọi URL ảnh.
   - **Gom theo thư mục, chọn thư mục có NHIỀU ảnh nhất** = thư mục trang truyện.
   - Sắp theo số trong tên file.
3. **Mỗi bộ một quy ước tên file khác nhau** — đó là lý do "đoán mẫu" thất bại:
   - `.../chapter-1/01.webp` (đệm 2 số, bắt đầu 1)
   - `.../0/0.webp` (thư mục theo số chương, bắt đầu 0, không đệm)
   - `.../manga_<hash>/chapter_0/chap_0_1.jpg` (mã băm + tên `chap_N_M`)
   → đọc thẳng URL từ HTML thì khỏi lo khác kiểu.
4. **Bỏ trang placeholder rỗng** (200 nhưng < ~800 byte).
5. **Bug đã sửa:** chỉ giữ link chương **thuộc đúng slug** (tránh đếm sidebar truyện khác);
   số chương lấy qua regex `chap/chuong/chapter[-_/](\d+)` để **không vớ phải ID truyện**.

**Học được:** SPA thường có HTML chương chứa sẵn data (đôi khi escaped); ưu tiên
đọc thẳng thay vì đoán; gom-theo-thư-mục để tìm ảnh nội dung bất kể cách đặt tên.

### 3b. zettruyen.club (`zettruyen_dl.py`) — biến thể zinmanga URL tiếng Việt
Cùng họ mục 3 nhưng **URL kiểu VN** nên kunmanga_dl không khớp → tách riêng:
- **Chương:** API `GET /api/comics/<slug>/chapters?per_page=-1` → JSON
  `{data:{chapters:[{chapter_num, chapter_name}]}}`. `slug` lấy từ `/truyen-tranh/<slug>`.
  (Series HTML tĩnh chỉ hiện 1-2 chương — **phải gọi API**.)
- **URL chương:** `/truyen-tranh/<slug>/chuong-<chapter_num>` (KHÔNG phải `chapter-slug`
  của API — API trả slug `chapter-26` nhưng trang dùng `chuong-26`; build từ `chapter_num`).
- **Ảnh:** nằm sẵn trong HTML chương (script `__next_f`):
  `cdn<N>.zetimage.com/<slug>/<num>/<page>.(jpg|webp)`. **CDN shard khác nhau theo chương**
  (ch0=cdn4, ch26=cdn1) → đọc host từ HTML, đừng đoán. Lọc đúng `/<slug>/<num>/`, sắp theo
  số trang. Cần `Referer = origin`. **Không xáo trộn**. Webtoon dài (1 chương = vài trăm lát)
  → format `stitch` hợp. (Test "Cánh Đồng Bị Lãng Quên": 27 chương, ch1=244 lát, sạch.)

---

## 4. mangafire — chống bot CDP + API ký token `vrf` (ĐÃ PHÁ)

**Bài toán (nhiều lớp):**
1. **Cloudflare** trước trang (challenge JS).
2. **Chống automation:** trang đọc `/read/...` phát hiện trình duyệt bị tự động hóa
   (Playwright/Selenium dù đã `--disable-blink-features=AutomationControlled` + vá
   `navigator.webdriver`, **kể cả Chrome thật do Playwright lái**) → **đá ngược về
   trang chủ** `mangafire.to/`. Trang manga + read đều bị; trang chủ thì không.
3. **API ảnh ký token:** `/ajax/read/chapter/<id>?vrf=<token>` đòi `vrf` ký
   client-side. Gọi thiếu/sai → `{"status":403,"message":"Request is invalid."}`.
   (Endpoint danh sách chương `/ajax/read/<slugSuffix>/chapter/en?vrf=...` cũng vậy —
   **slug ở đây là phần SAU dấu chấm**, vd `grapara.9jlp8` → `9jlp8`, KHÔNG phải manga-id.)

**Chìa khóa nhận ra:** cú đá-về-home do **JS trang phát hiện CDP/automation**, KHÔNG phải
rate-limit (curl tĩnh vẫn 200). Mọi cách lái qua **Playwright đều bị đá**. NHƯNG
**`chrome.exe` mở bình thường** (không có ~40 cờ automation của Playwright, không
`navigator.webdriver`) thì **KHÔNG bị đá** — kể cả khi gắn CDP vào sau.

**Giải pháp (`mangafire_dl.py`) — Chrome thật + CDP thuần, hứng API đã ký:**
1. **Tự mở `chrome.exe`** với `--remote-debugging-port=9222 --user-data-dir=C:\chrome-debug-profile`
   (vân tay thật → lọt anti-bot; tự vượt CF như người dùng). `ensure_chrome()` tự mở nếu chưa chạy.
2. Điều khiển qua **CDP WebSocket THUẦN** (`suppress_origin=True`), **CHỈ** dùng
   `Page.navigate` + `Network.*`. **TUYỆT ĐỐI không `Runtime.evaluate`** (chạy JS trong
   trang = bị phát hiện = đá về home). ⚠️ Đây là lý do bản cũ (đọc DOM bằng
   `SCROLL_AND_COLLECT`) chỉ lấy được 1 trang rồi bị đá.
3. Mở mỗi chương bằng `Page.navigate` tới `/read/<slug>/<lang>/chapter-N` → **trình duyệt
   TỰ KÝ `vrf`** và gọi `/ajax/read/chapter/<id>?vrf=...`. Ta **hứng response body**
   (`Network.getResponseBody`, đợi `loadingFinished`) → JSON `{"result":{"images":[[url,1,0],...]}}`
   **đúng thứ tự đọc**. → **KHÔNG cần reverse `vrf`** (để trình duyệt làm hộ).
4. Tải ảnh bằng **HTTP thường + `Referer: https://mangafire.to/`** — ảnh **không xáo trộn**,
   không cần cookie. Tạo tab riêng qua `Target.createTarget` (không đụng tab người dùng).

**Bẫy hay quên:**
- **Network preload thiếu trang:** reader chỉ preload ~6 ảnh đầu; nếu gom URL từ
  `Network.responseReceived` sẽ **mất phần lớn trang** (GraPara ch1 thật ra **40 trang**).
  → Phải lấy từ **danh sách ajax**, không phải từ ảnh đã preload.
- **Thứ tự trang:** KHÔNG suy từ URL (đoạn hex trong `/mf/<hash>` không phải số trang) —
  dùng đúng thứ tự mảng `images` của ajax. Verify: trang 01 = ảnh credit nhóm dịch.
- **Danh sách chương** lấy từ **HTML tĩnh** `/manga/<slug>` (regex link `/read/<slug>/<lang>/chapter-N`)
  — curl thường, không cần vrf/trình duyệt.

**Xáo trộn:** mỗi phần tử `images` là `[url, a, b]`. Các số `a/b` là **metadata reader
(cặp/zoom), KHÔNG phải cờ xáo trộn** — đã kiểm chứng 3 bộ: GraPara `(1,0)`, Dandadan &
Witch Hat có giá trị khác nhưng **tải thẳng ra ảnh đều SẠCH**. Vì vậy **không** dùng `a/b`
để đoán xáo (lúc đầu tưởng `(1,0)`=sạch → báo nhầm, đã bỏ). Nếu sau này gặp bộ ảnh raw thật
sự xáo → khi đó mới cần chụp element đã render như comix.to.

**Trạng thái:** ✅ ĐÃ TẢI ĐƯỢC trọn bộ. Test 3 bộ khác thể loại đều sạch + đúng thứ tự:
GraPara! (ch1=40, ch2=28, ch120=19), Dandadan (250 chương, ch1=62), Witch Hat Atelier
(122 chương, ch1=63, trang màu).
**Học được:** (a) `chrome.exe` mở tay << Playwright về độ "tàng hình"; (b) đừng reverse token —
để trình duyệt ký rồi **hứng response**; (c) lấy danh sách trang từ **API**, đừng tin preload.

---

## 5. comix.to — TRÙM CUỐI (nhiều lớp phòng thủ)

Đây là trang khó nhất, dồn nhiều kỹ thuật.

### Các lớp phòng thủ
| Lớp | Mô tả |
|---|---|
| API ký token | `?_=<token>` theo từng request, đổi tham số → 403 ("Missing token") |
| Response mã hóa | server trả `{"e":"<blob mã hóa>"}`, JS tự giải mã |
| CDN ảnh ẩn danh | `ek10.wowpic4.store/i5/<token>`, **không có đuôi file** |
| Overlay quảng cáo | `<a href="#">` chặn pointer-events → click thường bị nuốt |
| Reader lật trang | chỉ giữ ~3 ảnh trong DOM (ảo hóa) |
| **Xáo trộn ảnh** | ảnh CDN bị chia ô vuông + đảo; trình duyệt giải xáo bằng canvas/blob |

### Thuật toán giải quyết (`comix_dl.py`)
**Không forge token/giải mã** — để JS của trang làm, mình thu hoạch:

1. **Danh sách chương:** đọc từ DOM (link `-chapter-N`), **bấm phân trang bằng JS**
   (`element.click()` xuyên qua overlay quảng cáo). Hỗ trợ cả nút "Next page" lẫn nút số trang
   kế tiếp (`nextElementSibling` của `.is-active`), có vòng lặp chờ động (polling tối đa 3s)
   cho Vue/Nuxt render xong. Dừng khi hết trang hoặc 3 lần không thêm chương mới. Sau đó Python
   tự sắp xếp tăng dần từ Chapter 1..N.

2. **Đi qua từng trang reader:** click trực tiếp nút `[aria-label="Go to page N"]` trên thanh tiến
   trình (`.rpage-progress__seg`), có fallback mở menu Settings đối với các phiên bản reader cũ.

3. **Nhận biết trang đã sẵn sàng:** chờ xuất hiện **1 request ảnh CDN mới** (bắt
   **MỌI** request, vì có trang tải qua `image` lẫn `fetch`→blob — chỉ nghe `image`
   sẽ sót các trang blob).

4. **Lấy ảnh — TỰ THÍCH NGHI VÀ TẢI SONG SONG SIÊU TỐC**:
   - **Giai đoạn 1 - Lật trang siêu tốc (40ms polling):** lật qua các trang để thu thập URL ảnh
     ngay khi `<img> src` xuất hiện (chỉ mất ~40-60ms mỗi trang, toàn bộ chapter ~100 trang quét
     xong trong ~4-5s).
   - **Giai đoạn 2 - Tải đa luồng song song (`ThreadPoolExecutor` 8 luồng):** tải đồng thời
     8 ảnh WebP từ CDN (không gửi Referer comix.to). Toàn bộ ảnh của chapter tải xong trong ~1-2s.
   - **Fallback tự thích nghi:**
     + `blob:` → fetch nhị phân in-page (`fetch(url)` → arrayBuffer → base64).
     + `<canvas>` / lỗi → chụp màn hình phần tử (`element.screenshot()`) bản giải xáo.
     + Nếu tải HTTP fail → fallback sang in-page fetch hoặc chụp màn hình.
   - **Kết quả:** Giảm thời gian tải từ ~65-70s xuống chỉ còn **~7-8s / chapter** (nhanh hơn gấp 10 lần).

5. **Phát hiện xáo trộn (cho `--check`):** xem phần tử hiển thị là **canvas/blob**
   (trình duyệt đã giải xáo → bị xáo) hay **img CDN trực tiếp** (không xáo). Tin cậy
   hơn nhiều so với cách so ảnh raw-vs-render (cách đó hay nhầm vì lệch trang/độ phân giải).

### Vì sao ảnh ra "ô vuông" lúc đầu?
Tải URL CDN gốc = **bản đã xáo**. Phải lấy **bản trình duyệt đã render** (canvas/blob).
→ screenshot phần tử đang hiển thị là cách chắc ăn cho **mọi kiểu xáo**.

### Đánh đổi
- Trang **không xáo** → chủ yếu tải thẳng → **nhanh, nhẹ** (vd 19 trang = 15 webp + 4 png).
- Trang **bị xáo** → chụp từng trang → **đúng ảnh** nhưng chậm + file PNG to.

**Học được:**
- Click bị overlay chặn → **click bằng JS** (bỏ qua pointer-events).
- Response/ảnh mã hóa → **đọc kết quả đã render** (DOM/screenshot), đừng giải mã.
- Reader ảo hóa → **lật từng trang**, bắt **mọi loại request** (image + fetch).
- Ảnh xáo trộn → **screenshot phần tử đã render** = bản giải xáo, universal.
- Tối ưu tốc độ: **tự thích nghi mỗi trang** (tải thẳng khi được, chụp khi buộc).

---

## 5b. webtoons.com — nguồn chính thống bị nhà mạng chặn SNI (`webtoon_dl.py`)

**Bài toán:** webtoons.com là nguồn **miễn phí chính thống** (LINE/Naver), KHÔNG chống
bot kiểu lậu. Rào cản nằm ở **tầng mạng**: tên miền chính `www.webtoons.com` bị
**RST (reset kết nối) chập chờn** — nhà mạng VN chặn theo **SNI** (hoặc WAF chặn
fingerprint non-browser). `curl`/`urllib` → `Connection reset`, **lúc được lúc không**.

**Chẩn đoán phân biệt:** DNS resolve **được** (IP Hàn thật); CDN ảnh
`webtoon-phinf.pstatic.net` **vào được** (chỉ tên miền chính bị RST). → chặn theo SNI,
không phải chặn IP.

**Giải pháp:**
1. **Chrome thật** (`ensure_chrome`, dùng lại của mangafire) vượt được chặn tên miền
   chính (vân tay browser thật). webtoons **không** chống automation → dùng
   `Runtime.evaluate` thoải mái (khác mangafire).
2. CDP đọc DOM: danh sách chương **phân trang** `&page=N` (`#_listUl li a`, lấy
   `episode_no` + tiêu đề), ảnh từ viewer (`#_imageList img[data-url]` — webtoons gắn
   sẵn `data-url`, **không cần cuộn** lazy-load).
3. Tải ảnh bằng **`urllib` + `Referer: https://www.webtoons.com/`** — CDN **không bị
   chặn** nên nhanh, không cần qua trình duyệt. Ảnh **không xáo trộn**.
4. **RST chập chờn → RETRY:** `navigate()` thử lại 3 lần (kiểm tra có `#_listUl`/`#_imageList`
   mới coi là thành công); `dl_image()` retry 4 lần.

**Định dạng:** webtoon **cuộn dọc liền** → format `stitch` (`pack.make_stitch`) ghép
thành dải dài (≤18000px/mảnh) là hợp nhất.

**Trạng thái:** ✅ test Ctrl+Alt+Resign: 46 chương, ch1=120 ảnh → 9 dải ghép, sạch & đúng thứ tự.
**Học được:** chặn ở **tầng mạng (SNI/RST)** ≠ chặn ở tầng app. Browser thật vượt SNI-RST;
ảnh thì tải thẳng CDN. Phân biệt bằng: *cùng IP/DNS nhưng chỉ 1 host bị reset*.

---

## 5c. toongod.org (`toongod_dl.py`) — Cloudflare challenge + LAI cookie→HTTP

**Bài toán:** Cloudflare **challenge thật** ("Just a moment", curl → 403). Trang là
**Madara/wp-manga**. Mở trình duyệt cho mọi chương thì **rất chậm** (bộ vài trăm chương).

**Giải pháp LAI (browser 1 lần → HTTP nhiều lần):**
1. **Chrome thật vượt CF MỘT lần** (`ensure_chrome`), rồi qua CDP **hứng cookie
   `cf_clearance`** (`Network.getCookies`) + **UA của Chrome** (`/json/version`).
2. **Dùng cookie + UA đó cho HTTP thuần** (`urllib`) tải toàn bộ series/chương — **NHANH**.
   ⚠️ Mấu chốt: cf_clearance của site này **TÁI DÙNG ĐƯỢC ngoài browser** (không bị buộc
   TLS-fingerprint) → đã test curl với cookie → 200. (Không phải site nào cũng vậy; site
   buộc JA3 thì cookie HTTP sẽ vô dụng, khi đó phải đi CDP hẳn.)
3. **Phải khớp UA** với UA Chrome đã tạo clearance; gửi kèm `Accept-Encoding: gzip`.
4. Cookie hết hạn giữa chừng (HTML trả "Just a moment") → **tự vượt CF lại** rồi retry.

**Ảnh:** Madara `class="wp-manga-chapter-img"` → host **`i.tngcdn.com`** (CDN riêng,
**chỉ cần `Referer`**, KHÔNG cần cookie CF). Lấy kiểu gom-theo-thư-mục, sắp theo số cuối
tên file. **Không xáo trộn**. (Test "Eleceed": 407 chương, ch1=107 trang, sạch.)

**Học được:** CF challenge KHÔNG nhất thiết phải lái browser cho từng request — nếu
`cf_clearance` tái dùng được thì **mượn cookie 1 lần rồi HTTP** (nhanh hơn nhiều). Trang
nội dung sau CF, ảnh ở CDN riêng thường không bị CF.

## 5d. manhwaread.com (`manhwaread_dl.py`) — CF + ảnh trong biến JS **base64**

**Giống 5c** (Cloudflare → mượn cookie qua `toongod_dl.get_cf_session`/`http` rồi HTTP),
**khác ở chỗ lấy ảnh:** ảnh KHÔNG ở `<img>` mà nhúng trong biến JS:
```js
chapterData = {"data":"<base64>", "base":"https://manread.xyz/<mangaId>"}
```
- `data` = **base64** của JSON `[{"src":"<chapId>/mr_NNN.jpg","w":..,"h":..}, ...]`.
- URL ảnh = **`base + "/" + src`** (vd `https://manread.xyz/12474/130981/mr_001.jpg`).
- Ảnh **webp dù đuôi `.jpg`** → detect magic bytes. CDN `manread.xyz` **chặn hotlink → cần `Referer`**.
- Danh sách chương: series HTML có link `/manhwa/<slug>/chapter-NN/` (số đệm `01`, `02`...; giữ
  nguyên chuỗi để dựng URL). (Test "My Bias Gets on the Last Train": 71 chương, ch1=40 trang, sạch.)

**Học được:** ảnh có thể giấu trong **biến JS đã mã hoá base64** (không phải `<img>`) — soi
script tìm `chapterData`/`window.__...`, decode rồi ghép `base + src`. Đây là "mã hoá" nhẹ
(chỉ base64, không phải crypto) → giải thẳng, khỏi cần trình duyệt render.

---

## 6. Trang bất kỳ — Playwright tổng quát (`manga_dl.py`)

Dự phòng cuối: mở Chromium thật, **cuộn để kích hoạt lazy-load**, đọc `<img>`
(src/data-src), lọc rác theo kích thước + từ khóa. Heuristic, không đảm bảo 100%.

---

## 7. Terabox / 1024tera — tải file share bị tường đăng nhập (`terabox_dl.py`)

**Bài toán:** bấm Download **ẩn danh** → trang nạp Google reCAPTCHA + tường login,
KHÔNG có request tải thật. File > ~50MB **bắt buộc đăng nhập**. Link tải thật (`dlink`)
được ký bằng `sign` (RC4 client-side) → không nên reverse.

**Cách lách (đúng triết lý "không giải mã, hứng kết quả"):**
1. `share/list?shorturl=<surl>` (lấy `jsToken` từ HTML: `fn(%22<hex>%22)`) → liệt kê file
   (server_filename/size/fs_id) — **không cần login**.
2. Mở `chrome.exe` thật (debug 9222) tại trang share → **người dùng đăng nhập 1 lần**.
3. Poll `Network.getCookies` tới khi có cookie **`ndus`** (= đã login).
4. Hứng `dlink` (từ `/share/download` hoặc URL CDN `*/file/…`) qua CDP → tải HTTP với
   `Cookie`(ndus…)+UA mượn từ Chrome. Resume theo header `Range`.

→ Né cài app + đỡ bị bóp tốc độ. **KHÔNG** áp dụng cho nội dung trả phí hợp pháp.

## 8. Chỉnh sửa trang truyện — xóa chữ + lettering lại (`manga_edit.py` + `manga_translate.py`)

Tách **"bộ não"** (đọc + dịch) khỏi **"đôi tay"** (sửa pixel) qua 1 **script JSON**
`[{box:[x,y,w,h], text, fill, align, upper}]` — ai tạo script cũng được (đa model).

**Đôi tay `manga_edit.py`:**
- *Xóa chữ (`fill`):* `white` (bong bóng thoại nền trắng → sạch tuyệt đối) / `#hex` /
  `auto` (OpenCV inpaint **chỉ đúng nét chữ**: mask = pixel lệch mạnh khỏi median vùng,
  lọc đốm nhỏ qua connected-components, giãn nở → giữ nền tranh) / `box` (inpaint cả ô).
  Không có OpenCV → tô màu nền viền (thô, chỉ hợp bong bóng).
- *Typeset:* binary-search cỡ chữ lớn nhất vừa box + word-wrap; vẽ chữ **viền trắng**
  (stroke) nổi trên mọi nền. Font Arial (có dấu tiếng Việt).
- `--preview` vẽ khung đỏ để soi định vị trước khi sửa.

**Bộ não `manga_translate.py`:** EasyOCR (offline, đa ngôn ngữ: ja/ko/ch_sim/ch_tra/en/vi —
1 CJK chỉ ghép với `en`) → box + chữ gốc → gộp dòng gần nhau thành bong bóng (nới box `gap`
px rồi hợp nhất chồng lấn) → đoán `fill` theo độ sáng vùng (sáng >50% = `white`).
Dịch: `--manual` (giữ chữ gốc, sửa tay) hoặc `--auto` (deep-translator, online).

**BÀI HỌC then chốt — "kết hợp model":** EasyOCR giỏi **dò box** nhưng **đọc chữ** trên
font manga cách điệu thì sai nhiều (vd "MÌNH NÊN NÓI…" → "MeNH NEN NÓl…"), và **không**
bắt được SFX vẽ tay. Chất lượng cao nhất = EasyOCR dò vị trí + **Claude vision đọc/dịch**
(nhìn trang đọc chuẩn) → điền `text` vào script rồi render. SFX to là ca khó nhất (inpaint
Telea còn để vệt) — bong bóng thoại mới là ca "ăn chắc".

---

## Bảng tra nhanh kỹ thuật

| Bài toán | Kỹ thuật |
|---|---|
| Chặn DNS (ISP) | DNS-over-HTTPS + vá `socket.getaddrinfo` |
| Chặn hotlink ảnh | gửi header `Referer = origin` |
| Cloudflare/chống bot | mượn Chrome thật qua CDP (`suppress_origin`), lấy ảnh từ Network domain |
| Đá-về-home khi tự động hóa (mangafire) | **`chrome.exe` mở tay** (KHÔNG Playwright) + CDP **chỉ** `Page.navigate`+`Network` (KHÔNG `Runtime.evaluate`) |
| API ảnh ký `vrf` (mangafire) | **không reverse** — navigate trang đọc để trình duyệt tự ký, **hứng response** `/ajax/read/chapter/<id>` |
| Reader chỉ preload vài trang | lấy danh sách đầy đủ + đúng thứ tự từ **API**, đừng tin ảnh đã preload |
| Nhà mạng chặn SNI/RST (webtoons) | **Chrome thật** vượt tên miền chính; ảnh tải thẳng **CDN** (không bị chặn) + retry vì reset chập chờn |
| Webtoon cuộn dọc | format `stitch` ghép dải dài; ảnh `data-url` có sẵn, không cần cuộn |
| SPA, chương qua API | gọi thẳng API (per_page=-1); slug từ `/manga/<slug>` |
| Ảnh nhúng escaped | `replace('\\/','/')` + gom-theo-thư-mục chọn folder nhiều ảnh nhất |
| Tên file mỗi bộ một kiểu | đọc thẳng URL từ HTML, đừng đoán mẫu |
| API ký token / response mã hóa | để JS trang xử lý, đọc kết quả render (DOM) |
| Click bị overlay chặn | `element.click()` qua `page.evaluate` |
| Reader ảo hóa (3 ảnh/DOM) | lật từng trang; bắt MỌI request (image + fetch) |
| Ảnh xáo trộn (tile shuffle) | screenshot phần tử đã render (bản giải xáo) |
| Tối ưu tốc độ | tự thích nghi: img CDN→tải thẳng; blob→fetch; canvas→chụp |
| Trang placeholder rỗng | bỏ ảnh < ~800 byte |
| Phát hiện xáo | xem phần tử hiển thị là canvas/blob (xáo) hay img CDN (không) |
| Tường login tải file (Terabox) | liệt kê qua `share/list`; user login Chrome thật 1 lần → hứng cookie `ndus`+`dlink` qua CDP → tải HTTP |
| Xóa chữ trên tranh | OpenCV inpaint **chỉ nét chữ** (mask lệch-median + lọc CC); bong bóng trắng thì tô trắng |
| Đọc chữ manga chính xác | EasyOCR dò box + **Claude vision đọc/dịch** (OCR thường sai font cách điệu, trượt SFX vẽ tay) |
| Chèn thoại vừa bong bóng | binary-search cỡ chữ + word-wrap + viền trắng (stroke) |
