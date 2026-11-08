# -*- coding: utf-8 -*-
"""
truyenqq_dl - Tai truyen tu cac trang kieu TruyenQQ / NetTruyen (Viet Nam).

Cac trang nay tra HTML co san link anh (khong can JavaScript) va anh nam trong
<img class="page-chapter">. Anh thuong CHAN HOTLINK -> phai gui kem header
Referer = ten mien trang. Tool xu ly san viec do. KHONG can trinh duyet.

Vi du:
    # Tai ca bo (dua link trang bo truyen)
    python truyenqq_dl.py "https://truyenqqko.com/truyen-tranh/dai-phap-su-toan-nang-13507"

    # Chi tai 1 chuong
    python truyenqq_dl.py "https://truyenqqko.com/.../...-chap-1"

    # Tai 1 day chuong + dinh dang
    python truyenqq_dl.py "<link-bo>" --range 1 20 --format folder cbz pdf

    pip install Pillow   (chi can neu muon xuat PDF)
"""

import argparse
import os
import re
import sys
import time
import urllib.request
import zipfile
from html import unescape as html_unescape
from pathlib import Path
from urllib.parse import urlparse

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(text, maxlen=90):
    text = INVALID.sub("_", (text or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return (text or "untitled")[:maxlen]


def origin(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def http(url, referer=None, retries=4, binary=False):
    last = None
    for attempt in range(retries):
        try:
            h = {"User-Agent": UA, "Accept-Language": "vi,en;q=0.9"}
            if referer:
                h["Referer"] = referer
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep((attempt + 1) * 1.5)
    raise RuntimeError(f"GET that bai: {url} ({last})")


# --------------------------------------------------------------------------- #
# Phan tich trang
# --------------------------------------------------------------------------- #

# Ho TruyenQQ co 2 kieu URL chuong: '...-chap-12.5' VA '/<slug>/chapter-12-5'
# (decimal o kieu sau dung dau '-': chapter-13-5 = chuong 13.5).
CHAP_HREF = re.compile(r'href="([^"]*?(?:-chap-|/chapter-)\d+(?:[.-]\d+)?/?)"', re.I)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
IMG_URL = re.compile(
    r'(?:data-src|data-original|data-cdn|src)\s*=\s*["\'](https?://[^"\']+)["\']', re.I)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
# Anh KHONG phai trang truyen (avatar binh luan, banner, logo...)
JUNK_IMG = re.compile(
    r"(avatar|banner|/logo|favicon|icon|qrcode|loading|sprite|/ad/|/ads/|"
    r"\d+x\d+/avatar|comment)", re.I)


def strip_tags(s):
    return html_unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def is_chapter_url(url):
    return bool(re.search(r"(?:-chap-|/chapter-)\d+(?:[.-]\d+)?/?$",
                          url.split("?")[0], re.I))


def chap_number(url):
    m = re.search(r"(?:-chap-|/chapter-)(\d+(?:[.-]\d+)?)", url, re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace("-", "."))   # 'chapter-13-5' -> 13.5
    except ValueError:
        return None


def parse_title(html, fallback="truyen"):
    # Uu tien <h1> (thuong la dung ten bo), fallback ve <title>
    m = H1_RE.search(html)
    t = strip_tags(m.group(1)) if m else ""
    if not t:
        m = TITLE_RE.search(html)
        t = strip_tags(m.group(1)) if m else ""
    t = re.sub(r"\s+", " ", t).strip()
    # Bo duoi " - TruyenQQ" / " | NetTruyen" ...
    t = re.split(r"\s*[-|]\s*(?:truyenqq|nettruyen|toptruyen|truyentranh)",
                 t, maxsplit=1, flags=re.I)[0].strip()
    # Bo cum "chuong/chap moi nhat N" hoac "chuong N" o duoi ten
    t = re.sub(r"\s*(?:chương|chuong|chap|chapter)\s*(?:mới nhất|moi nhat)?\s*[\d.]+\s*$",
               "", t, flags=re.I).strip(" -|")
    return t or fallback


def get_chapter_links(series_url):
    html = http(series_url, referer=origin(series_url))
    title = parse_title(html, fallback=series_url.rstrip("/").split("/")[-1])
    # slug bo truyen (de loc bo link chuong cua TRUYEN KHAC o sidebar/hot)
    slug = urlparse(series_url).path.strip("/").split("/")[0].lower()
    seen, items, items_all = set(), [], []
    for href in CHAP_HREF.findall(html):
        full = urllib.request.urljoin(series_url, href)
        if full in seen or not is_chapter_url(full):
            continue
        seen.add(full)
        items_all.append(full)
        if slug and ("/" + slug + "/") in (urlparse(full).path.lower() + "/"):
            items.append(full)
    items = items or items_all          # neu loc het sach -> dung tat ca (tuong thich cu)
    items.sort(key=lambda u: (chap_number(u) if chap_number(u) is not None else 1e9))
    return title, items


def get_chapter_images(chapter_url):
    html = http(chapter_url, referer=origin(chapter_url))
    urls, seen = [], set()
    for tag in IMG_TAG.findall(html):
        if "page-chapter" not in tag:        # chi lay anh noi dung, bo quang cao
            continue
        m = IMG_URL.search(tag)
        if not m:
            continue
        u = m.group(1).replace("&amp;", "&").strip()
        if JUNK_IMG.search(u):               # bo avatar binh luan / banner lan vao
            continue
        if u not in seen:
            seen.add(u)
            urls.append(u)
    # Du phong: neu mirror khong dung class page-chapter, lay anh tu CDN pho bien
    if not urls:
        for tag in IMG_TAG.findall(html):
            m = IMG_URL.search(tag)
            if not m:
                continue
            u = m.group(1).replace("&amp;", "&").strip()
            if re.search(r"\.(jpe?g|png|webp)", u, re.I) and not JUNK_IMG.search(u):
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
    return urls


# --------------------------------------------------------------------------- #
# Luu / dong goi
# --------------------------------------------------------------------------- #

def make_cbz(files, cbz_path: Path):
    cbz_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cbz_path.parent / (cbz_path.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, arcname=f.name)
    tmp.replace(cbz_path)


def make_pdf(files, pdf_path: Path):
    try:
        from PIL import Image
    except ImportError:
        print("      [bo qua PDF] thieu Pillow")
        return
    pages = []
    for f in files:
        try:
            pages.append(Image.open(f).convert("RGB"))
        except Exception:
            pass
    if pages:
        pages[0].save(pdf_path, "PDF", save_all=True, append_images=pages[1:])


def ext_of(url):
    m = re.search(r"\.(jpe?g|png|webp|gif)", url, re.I)
    return ("." + m.group(1).lower().replace("jpeg", "jpg")) if m else ".jpg"


# --------------------------------------------------------------------------- #
# RESUME (tiep tuc sau khi dung dot ngot) - dung chung cho cac tool
#   * progress_*: danh dau CHUONG da xong (theo ten thu muc chuong) trong
#     <out_dir>/.progress.json -> bo qua nhanh, KHONG can mo lai trinh duyet.
#   * have_page: ANH thu idx da co tren dia chua -> resume GIUA chuong.
#   * write_atomic: ghi .part roi doi ten -> khong bao gio con file dang do.
# --------------------------------------------------------------------------- #

import json as _json


def _progress_file(out_dir):
    return Path(out_dir) / ".progress.json"


def progress_load(out_dir):
    try:
        return set(_json.loads(_progress_file(out_dir).read_text(encoding="utf-8")))
    except Exception:
        return set()


def progress_save(out_dir, done):
    try:
        f = _progress_file(out_dir)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f.name + ".part")
        tmp.write_text(_json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)
    except Exception:
        pass


def have_page(ch_dir, idx, pad, min_size=500):
    """Tra ve Path cua anh thu idx neu da co (bat ky duoi), du lon. None neu chua."""
    if not ch_dir.exists():
        return None
    stem = str(idx).zfill(pad)
    for p in ch_dir.glob(stem + ".*"):
        if p.suffix.lower() == ".part":
            continue
        try:
            if p.stat().st_size >= min_size:
                return p
        except OSError:
            pass
    return None


def write_atomic(path: Path, data: bytes):
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Thanh tien trinh + tai anh dung chung (icon sach lat trang cho sinh dong)
# --------------------------------------------------------------------------- #

_BOOKS = "📖📗📘📙📕"          # lat trang qua tung anh


def ext_of_bytes(data: bytes):
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".jpg"


def progress_bar(done, total, width=22, prefix="      "):
    """In thanh tien trinh tai cho (0%..100%) voi icon sach lat trang."""
    pct = (done / total) if total else 1.0
    filled = int(round(width * pct))
    bar = "█" * filled + "░" * (width - filled)
    if done >= total:
        icon, tail = "📚", "  ✓"
    else:
        icon, tail = _BOOKS[done % len(_BOOKS)], ""
    try:
        sys.stdout.write(f"\r{prefix}{icon} [{bar}] {pct * 100:5.1f}%  {done}/{total}{tail}   ")
        sys.stdout.flush()
    except Exception:
        pass


def largest_image_group(urls):
    """`urls` theo THU TU XUAT HIEN trong HTML. Gom theo thu muc, chon folder nhieu anh
    nhat (= thu muc trang truyen, loai logo/thumbnail), GIU NGUYEN thu tu xuat hien
    (= thu tu doc cua reader) + dedupe. Robust hon doan so trong ten file
    (vd toongod 'eleceed-chapter-2-001.jpg' co so o CUOI -> sort theo so dau bi loan)."""
    groups = {}
    for u in urls:
        groups.setdefault(u.rsplit("/", 1)[0], []).append(u)
    if not groups:
        return []
    best = max(groups.values(), key=len)
    seen, out = set(), []
    for u in best:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def download_images(urls, ch_dir: Path, getter, min_size=500, pad=None):
    """Tai danh sach anh vao ch_dir voi: resume (have_page) + ghi nguyen tu +
    THANH TIEN TRINH 0->100% (icon sach lat trang). `getter(url)` tra ve bytes anh.
    Terminal: thanh dong (\\r). GUI/pipe: in moc % (tranh spam). Tra ve list Path."""
    ch_dir.mkdir(parents=True, exist_ok=True)
    total = len(urls)
    if pad is None:
        pad = max(3, len(str(total)))
    try:
        istty = sys.stdout.isatty()
    except Exception:
        istty = False
    step = max(1, total // 5)        # GUI: ~5 moc
    saved = []
    if istty:
        progress_bar(0, total)
    for i, u in enumerate(urls, 1):
        have = have_page(ch_dir, i, pad, min_size=min_size)
        if have:
            saved.append(have)
        else:
            try:
                data = getter(u)
                if not data or len(data) < min_size:
                    raise RuntimeError("anh qua nho/rong")
                fp = ch_dir / (str(i).zfill(pad) + ext_of_bytes(data))
                write_atomic(fp, data)
                saved.append(fp)
            except Exception as e:
                print(f"\n      [bo qua] trang {i}: {e}")
        if istty:
            progress_bar(i, total)
        elif i == total or i % step == 0:        # GUI: in moc
            icon = "📚" if i >= total else _BOOKS[(i // step) % len(_BOOKS)]
            print(f"      {icon} {i / total * 100:5.1f}%  {i}/{total}"
                  + ("  ✓" if i >= total else ""), flush=True)
    if istty:
        print()
    return saved


def download_chapter(urls, out_dir: Path, referer):
    return download_images(urls, out_dir,
                           lambda u: http(u, referer=referer, binary=True), min_size=1024)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def run(args):
    ref = origin(args.url)
    fmts = args.format

    if is_chapter_url(args.url):
        title_raw = args.url.rstrip("/").split("/")[-1]
        chapters = [args.url]
    else:
        title_raw, chapters = get_chapter_links(args.url)
        if not chapters:
            print("Khong tim thay chuong nao tren trang bo truyen.")
            return
    title = slugify(title_raw)

    # Loc theo --range (theo so chuong)
    if args.range:
        a, b = args.range
        chapters = [c for c in chapters
                    if (chap_number(c) is not None and a <= chap_number(c) <= b)]
    if args.limit:
        chapters = chapters[: args.limit]

    if getattr(args, "list", False):
        for c in chapters:
            n = chap_number(c)
            print(f"  Ch {n:g}" if n is not None else f"  {c}")
        return

    if getattr(args, "check", False):
        imgs = get_chapter_images(chapters[0]) if chapters else []
        nums = [chap_number(c) for c in chapters if chap_number(c) is not None]
        rng = f" (chuong {min(nums):g}..{max(nums):g})" if nums else ""
        print("\n================ CHAN DOAN ================")
        print(f"  Ket qua  : {'TAI DUOC (HTTP thuan) ✔' if imgs else 'CHUA LAY DUOC ✘'}")
        print(f"  Truyen   : {title_raw}")
        print(f"  So chuong: {len(chapters)}{rng}")
        if imgs:
            print(f"  Chuong dau: {len(imgs)} trang")
        print("  Cach     : HTTP thuan (TruyenQQ/NetTruyen) + Referer, khong xao tron")
        print("===========================================")
        return

    out_dir = Path(args.out) / title
    done = progress_load(out_dir)
    print(f"\nBo truyen: {title}")
    print(f"So chuong se tai: {len(chapters)}")
    print(f"Luu vao: {out_dir.resolve()}")
    if done:
        print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
    print()

    for idx, curl in enumerate(chapters, 1):
        n = chap_number(curl)
        label = f"Chuong {n:g}" if n is not None else f"chuong {idx}"
        ch_dir = out_dir / slugify(f"{idx:04d} - {label}")
        cbz = ch_dir.parent / (ch_dir.name + ".cbz")
        pdf = ch_dir.parent / (ch_dir.name + ".pdf")

        if (ch_dir.name in done or cbz.exists()) and not args.overwrite:
            print(f"[{idx}/{len(chapters)}] (da co) {label}")
            done.add(ch_dir.name)
            continue

        print(f"[{idx}/{len(chapters)}] {label}")
        try:
            imgs = get_chapter_images(curl)
            if not imgs:
                print("      (khong tim thay anh)")
                continue
            print(f"      {len(imgs)} trang")
            files = download_chapter(imgs, ch_dir, referer=ref)
            if not files:
                continue
            if "cbz" in fmts:
                make_cbz(files, cbz)
                print(f"      -> {cbz.name}")
            if "pdf" in fmts:
                make_pdf(files, pdf)
                print(f"      -> {pdf.name}")
            if "stitch" in fmts:
                import pack
                made = pack.make_stitch(files, ch_dir)
                if made:
                    print(f"      -> ghep lien: {len(made)} file")
            if "folder" not in fmts:
                for f in files:
                    f.unlink(missing_ok=True)
                try:
                    ch_dir.rmdir()
                except OSError:
                    pass
            done.add(ch_dir.name)
            progress_save(out_dir, done)
        except Exception as e:
            print(f"      LOI: {e}")
        time.sleep(args.delay)

    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(
        description="Tai truyen tu trang kieu TruyenQQ/NetTruyen (VN).")
    p.add_argument("url", help="Link bo truyen hoac link 1 chuong")
    p.add_argument("--range", nargs=2, type=float, metavar=("A", "B"),
                   help="Chi tai chuong trong khoang so [A..B]")
    p.add_argument("--limit", type=int, default=0, help="Chi tai N chuong dau (0=tat ca)")
    p.add_argument("--format", nargs="+", default=["folder", "cbz"],
                   choices=["folder", "cbz", "pdf", "stitch"])
    p.add_argument("--out", default="downloads", help="Thu muc luu")
    p.add_argument("--delay", type=float, default=1.0, help="Nghi giua cac chuong (giay)")
    p.add_argument("--overwrite", action="store_true", help="Tai lai chuong da co")
    p.add_argument("--check", action="store_true", help="Chi chan doan (so chuong + thu 1 anh)")
    p.add_argument("--list", action="store_true", help="Liet ke chuong")
    return p


if __name__ == "__main__":
    try:
        run(build_parser().parse_args())
    except KeyboardInterrupt:
        print("\nDa dung.")
