# -*- coding: utf-8 -*-
"""
manga_dl - Tool tai truyen tranh (manga / manhwa / manhua) tong quat.

Cach dung nhanh:
    python manga_dl.py "https://link-bo-truyen"            # tai ca bo
    python manga_dl.py "https://link-1-chuong" --mode chapter
    python manga_dl.py "https://..." --format folder cbz pdf --headful

Y tuong: dung trinh duyet that (Playwright) de mo trang, cuon cho nap het anh
roi doc toan bo source de lay link anh. Vi moi trang co cau truc khac nhau nen
tool dung HEURISTIC (do tim) chu khong dam bao 100%. Neu mot trang khong ra,
xem phan GHI CHU o cuoi file de chinh.
"""

import argparse
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit(
        "Thieu Playwright. Chay:\n"
        "    pip install -r requirements.txt\n"
        "    python -m playwright install chromium"
    )


# --------------------------------------------------------------------------- #
# Tien ich chung
# --------------------------------------------------------------------------- #

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Cac tu cho biet day la link CHUONG (dung de loc khoi danh sach chuong)
CHAPTER_HINTS = re.compile(
    r"(chap|chuong|chapter|episode|ch-\d|/ch\d|tap-\d|/tap/|volume|vol-\d)",
    re.IGNORECASE,
)

# Tu khoa cho biet anh KHONG phai noi dung truyen (logo, banner, quang cao...)
JUNK_IMG = re.compile(
    r"(logo|banner|avatar|icon|favicon|sprite|ads?[-_./]|advert|/ad/|"
    r"qrcode|loading|placeholder|lazy|blank|spacer|button|/btn)",
    re.IGNORECASE,
)


def slugify(text: str, maxlen: int = 80) -> str:
    text = (text or "").strip()
    text = INVALID_CHARS.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return (text or "untitled")[:maxlen]


def natural_key(s: str):
    """Sap xep tu nhien: chuong 2 < chuong 10."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", s)]


def first_number(s: str):
    m = re.search(r"\d+(?:\.\d+)?", s or "")
    return float(m.group()) if m else None


# --------------------------------------------------------------------------- #
# Truy xuat trang bang Playwright
# --------------------------------------------------------------------------- #

class Browser:
    def __init__(self, headful: bool = False, timeout_ms: int = 60000):
        self.headful = headful
        self.timeout_ms = timeout_ms

    def __enter__(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=not self.headful)
        self.context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="vi-VN",
        )
        self.context.set_default_timeout(self.timeout_ms)
        return self

    def __exit__(self, *exc):
        try:
            self.context.close()
            self.browser.close()
        finally:
            self._pw.stop()

    def open(self, url: str):
        page = self.context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        return page

    def scroll_to_load(self, page, max_rounds: int = 60, pause: float = 0.6):
        """Cuon xuong day nhieu lan de kich hoat lazy-load anh."""
        last_count, stable = -1, 0
        for _ in range(max_rounds):
            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(int(pause * 1000))
            count = page.evaluate("document.images.length")
            height_stable = page.evaluate(
                "Math.abs(window.innerHeight + window.scrollY "
                "- document.body.scrollHeight) < 5"
            )
            if count == last_count and height_stable:
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            last_count = count
        # ep trinh duyet tai not anh trong viewport
        page.wait_for_timeout(500)


# --------------------------------------------------------------------------- #
# Trich xuat link chuong va link anh
# --------------------------------------------------------------------------- #

def extract_chapter_links(page, base_url: str):
    """Lay danh sach (tieu_de, url) cac chuong tu trang bo truyen."""
    raw = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]'))
              .map(a => ({href: a.href, text: a.textContent.trim()}))"""
    )
    host = urlparse(base_url).netloc
    seen, items = set(), []
    for a in raw:
        href = a["href"]
        if not href or href in seen:
            continue
        if urlparse(href).netloc != host:
            continue
        text = a["text"]
        if not (CHAPTER_HINTS.search(href) or CHAPTER_HINTS.search(text)):
            continue
        seen.add(href)
        items.append((text or href, href))

    # Sap xep theo so chuong (uu tien so trong text, roi trong url)
    def sort_key(it):
        n = first_number(it[0]) or first_number(it[1])
        return (n if n is not None else 1e9, natural_key(it[1]))

    items.sort(key=sort_key)
    return items


def extract_image_urls(page, page_url: str):
    """Lay link anh noi dung cua mot trang chuong (da loc rac)."""
    imgs = page.evaluate(
        """() => Array.from(document.images).map(img => ({
              src: img.currentSrc || img.src
                   || img.getAttribute('data-src')
                   || img.getAttribute('data-original') || '',
              w: img.naturalWidth, h: img.naturalHeight,
           }))"""
    )
    out, seen = [], set()
    for im in imgs:
        src = (im["src"] or "").strip()
        if not src or src.startswith("data:"):
            continue
        src = urljoin(page_url, src)
        if src in seen or JUNK_IMG.search(src):
            continue
        # Anh truyen thuong to: rong >= 300px hoac cao >= 400px.
        # Neu trinh duyet chua bao kich thuoc (0) van giu lai de khong sot.
        w, h = im["w"], im["h"]
        if (w and w < 300) and (h and h < 400):
            continue
        seen.add(src)
        out.append(src)
    return out


# --------------------------------------------------------------------------- #
# Tai va luu
# --------------------------------------------------------------------------- #

def guess_ext(url: str, content_type: str | None) -> str:
    if content_type:
        ct = content_type.lower()
        for key, ext in (("jpeg", ".jpg"), ("jpg", ".jpg"), ("png", ".png"),
                         ("webp", ".webp"), ("gif", ".gif"), ("avif", ".avif")):
            if key in ct:
                return ext
    m = re.search(r"\.(jpe?g|png|webp|gif|avif)(?:\?|$)", url, re.IGNORECASE)
    return ("." + m.group(1).lower().replace("jpeg", "jpg")) if m else ".jpg"


def download_chapter(ctx, title: str, urls, out_dir: Path,
                     referer: str, retries: int = 3):
    out_dir.mkdir(parents=True, exist_ok=True)
    pad = max(3, len(str(len(urls))))
    saved = []
    for i, url in enumerate(urls, 1):
        ok = False
        for attempt in range(retries):
            try:
                resp = ctx.request.get(url, headers={"referer": referer})
                if not resp.ok:
                    raise RuntimeError(f"HTTP {resp.status}")
                body = resp.body()
                if len(body) < 1024:        # < 1KB thuong la anh loi/placeholder
                    raise RuntimeError("anh qua nho")
                ext = guess_ext(url, resp.headers.get("content-type"))
                fp = out_dir / f"{str(i).zfill(pad)}{ext}"
                fp.write_bytes(body)
                saved.append(fp)
                ok = True
                break
            except Exception as e:
                if attempt == retries - 1:
                    print(f"      [bo qua] anh {i}: {e}")
                else:
                    time.sleep(1.5)
        if ok:
            print(f"\r      tai anh {i}/{len(urls)}", end="", flush=True)
    print()
    return saved


def make_cbz(image_files, cbz_path: Path):
    cbz_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_STORED) as z:
        for fp in image_files:
            z.write(fp, arcname=fp.name)
    return cbz_path


def make_pdf(image_files, pdf_path: Path):
    try:
        from PIL import Image
    except ImportError:
        print("      [bo qua PDF] Thieu Pillow: pip install Pillow")
        return None
    pages = []
    for fp in image_files:
        try:
            im = Image.open(fp)
            pages.append(im.convert("RGB"))
        except Exception as e:
            print(f"      [PDF] loi anh {fp.name}: {e}")
    if not pages:
        return None
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(pdf_path, "PDF", save_all=True, append_images=pages[1:])
    return pdf_path


# --------------------------------------------------------------------------- #
# Luong chinh
# --------------------------------------------------------------------------- #

def process_one_chapter(bro, ctx, title, url, ch_dir, formats, max_scroll):
    print(f"   -> {title}")
    page = bro.open(url)
    try:
        bro.scroll_to_load(page, max_rounds=max_scroll)
        urls = extract_image_urls(page, url)
    finally:
        page.close()

    if not urls:
        print("      (khong tim thay anh - co the trang dung ky thuat dac biet)")
        return

    print(f"      tim thay {len(urls)} anh")
    files = download_chapter(ctx, title, urls, ch_dir, referer=url)
    if not files:
        return
    if "cbz" in formats:
        cbz = make_cbz(files, ch_dir.with_suffix(".cbz"))
        print(f"      da tao {cbz.name}")
    if "pdf" in formats:
        pdf = make_pdf(files, ch_dir.with_suffix(".pdf"))
        if pdf:
            print(f"      da tao {pdf.name}")
    if "stitch" in formats:
        import pack
        made = pack.make_stitch(files, ch_dir)
        if made:
            print(f"      ghep lien: {len(made)} file")
    if "folder" not in formats:
        for f in files:
            f.unlink(missing_ok=True)
        try:
            ch_dir.rmdir()
        except OSError:
            pass


def run(args):
    out_root = Path(args.out)
    formats = args.format

    with Browser(headful=args.headful, timeout_ms=args.timeout * 1000) as bro:
        ctx = bro.context

        # --- Xac dinh che do ---
        mode = args.mode
        chapters = []
        series_title = "truyen"

        if mode in ("auto", "series"):
            page = bro.open(args.url)
            try:
                bro.scroll_to_load(page, max_rounds=args.max_scroll)
                series_title = slugify(page.title())
                chapters = extract_chapter_links(page, args.url)
            finally:
                page.close()
            if mode == "auto" and not chapters:
                print("Khong thay danh sach chuong -> coi day la 1 chuong don.")
                mode = "chapter"

        if mode == "chapter":
            chapters = [("chuong", args.url)]
            series_title = slugify(urlparse(args.url).path.rstrip("/").split("/")[-1]
                                   or "chuong")

        if not chapters:
            print("Khong tim thay chuong nao. Thu --mode chapter neu day la 1 chuong.")
            return

        # Gioi han pham vi neu can
        if args.limit:
            chapters = chapters[: args.limit]

        series_dir = out_root / series_title
        print(f"\nBo truyen: {series_title}")
        print(f"So chuong se tai: {len(chapters)}")
        print(f"Luu vao: {series_dir.resolve()}\n")

        for idx, (title, url) in enumerate(chapters, 1):
            ch_name = slugify(f"{idx:04d} - {title}")
            ch_dir = series_dir / ch_name
            # Bo qua neu da tai (co cbz hoac folder co anh)
            done = (ch_dir.with_suffix(".cbz").exists()
                    or (ch_dir.exists() and any(ch_dir.iterdir())))
            if done and not args.overwrite:
                print(f"[{idx}/{len(chapters)}] (da co, bo qua) {title}")
                continue
            print(f"[{idx}/{len(chapters)}]")
            try:
                process_one_chapter(bro, ctx, title, url, ch_dir,
                                    formats, args.max_scroll)
            except Exception as e:
                print(f"   LOI chuong nay: {e}")
            time.sleep(args.delay)

    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(
        description="Tool tai truyen tranh tong quat (Playwright).")
    p.add_argument("url", help="Link bo truyen hoac link mot chuong")
    p.add_argument("--mode", choices=["auto", "series", "chapter"],
                   default="auto", help="auto (mac dinh) / series / chapter")
    p.add_argument("--out", default="downloads", help="Thu muc luu")
    p.add_argument("--format", nargs="+", default=["folder", "cbz"],
                   choices=["folder", "cbz", "pdf", "stitch"],
                   help="Dinh dang xuat (co the chon nhieu)")
    p.add_argument("--limit", type=int, default=0,
                   help="Chi tai N chuong dau (0 = tat ca)")
    p.add_argument("--headful", action="store_true",
                   help="Hien trinh duyet (de xem / vuot captcha thu cong)")
    p.add_argument("--max-scroll", type=int, default=60,
                   help="So lan cuon toi da moi trang")
    p.add_argument("--delay", type=float, default=1.0,
                   help="Nghi giua cac chuong (giay)")
    p.add_argument("--timeout", type=int, default=60,
                   help="Timeout tai trang (giay)")
    p.add_argument("--overwrite", action="store_true",
                   help="Tai lai ca chuong da co")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nDa dung.")


# --------------------------------------------------------------------------- #
# GHI CHU (khi mot trang khong tai duoc):
#   1. Chay voi --headful de xem trinh duyet lam gi (captcha? cần login?).
#   2. Neu khong ra anh: trang co the dung <canvas> hoac ten thuoc tinh la
#      (vd data-srcset). Mo DevTools xem the chua anh roi sua extract_image_urls.
#   3. Neu khong ra danh sach chuong: link chuong co the khong chua tu khoa
#      trong CHAPTER_HINTS -> them tu khoa, hoac dung --mode chapter cho tung link.
#   4. Mot so trang chong bot manh -> tang --delay, dung --headful.
# --------------------------------------------------------------------------- #
