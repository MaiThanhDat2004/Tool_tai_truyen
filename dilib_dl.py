# -*- coding: utf-8 -*-
"""
dilib_dl - Tai truyen tu dilib.vn (Thu Vien So).

BAI TOAN / CACH LACH (xem THUAT_TOAN.md):
  - AngularJS SPA NHUNG HTML trang chuong NHUNG SAN URL anh (server-render):
    `https://dilib.vn/img/comic/<TenComic>/img_NNNNN.webp` (so trang 5 chu so).
  - CAM BAY: server CHI tra noi dung khi co header `Accept-Encoding: gzip`
    (thieu -> tra body RONG, HTTP 200 size 0). -> phai gui gzip + tu giai nen.
    (truyenqq_dl.tq.http KHONG gui gzip nen khong dung duoc -> http rieng o day.)
  - Anh can `Referer`. KHONG xao tron.
  - Danh sach chuong: trang series `/<slug>-<id>.html` liet ke link
    `/truyen-tranh/<slug>-<id>-chap-N.html`.

DUNG:
  python dilib_dl.py "<link bo hoac 1 chuong>" --check
  python dilib_dl.py "<link>" --limit 5 --out D:/tai_truyen
"""

import argparse
import gzip
import re
import sys
import time
import urllib.request
import zlib
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import truyenqq_dl as tq      # slugify, make_cbz, make_pdf, progress_*, have_page, write_atomic
import pack

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
ORIGIN = "https://dilib.vn"
IMG_RE = re.compile(r"/img/comic/[^\"'\s]+?/img_(\d+)\.(webp|jpe?g|png)", re.I)


def http(url, referer=None, binary=False, retries=4):
    """HTTP co Accept-Encoding gzip + tu giai nen (dilib bat buoc)."""
    last = None
    for k in range(retries):
        try:
            h = {"User-Agent": UA,
                 "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
                 "Accept-Encoding": "gzip, deflate",
                 "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
            if referer:
                h["Referer"] = referer
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
                enc = (r.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                data = gzip.decompress(data)
            elif "deflate" in enc:
                try:
                    data = zlib.decompress(data)
                except zlib.error:
                    data = zlib.decompress(data, -zlib.MAX_WBITS)
            return data if binary else data.decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep((k + 1) * 1.2)
    raise RuntimeError(f"GET that bai: {url} ({last})")


# --------------------------------------------------------------------------- #
# Phan tich
# --------------------------------------------------------------------------- #

def parse_slugid(url):
    """Lay '<slug>-<id>' tu URL chuong hoac series."""
    m = re.search(r"/([a-z0-9-]+?-\d+)(?:-chap-[\d.]+)?\.html", url, re.I)
    if not m:
        sys.exit("URL dilib khong hop le (can dang <slug>-<id>.html).")
    return m.group(1)


def series_url(slugid):
    return f"{ORIGIN}/{slugid}.html"


def chapter_url(slugid, num):
    return f"{ORIGIN}/truyen-tranh/{slugid}-chap-{num}.html"


def get_title(html, fallback):
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    t = unescape(re.sub(r"\s+", " ", (m.group(1) if m else ""))).strip()
    t = re.sub(r"^Truyện Tranh\s*", "", t, flags=re.I)
    t = re.split(r"\s*,\s*Thư Viện Số", t)[0].strip()
    t = re.sub(r"\s*Tiếng Việt\s*$", "", t, flags=re.I).strip()
    return t or fallback


def get_chapters(slugid):
    """Tra ve (title, [(num_float, num_str)]) sap tang dan."""
    html = http(series_url(slugid), referer=ORIGIN + "/")
    title = get_title(html, slugid)
    rx = re.compile(re.escape(slugid) + r"-chap-([\d.]+)\.html", re.I)
    seen, items = set(), []
    for num in rx.findall(html):
        if num in seen:
            continue
        seen.add(num)
        try:
            items.append((float(num), num))
        except ValueError:
            pass
    items.sort(key=lambda x: x[0])
    return title, items


def get_images(slugid, num_str):
    html = http(chapter_url(slugid, num_str), referer=series_url(slugid))
    found = {}
    for m in IMG_RE.finditer(html):
        page = int(m.group(1))
        if page not in found:
            found[page] = ORIGIN + m.group(0)
    return [found[k] for k in sorted(found)]


# --------------------------------------------------------------------------- #
# Tai (resume)
# --------------------------------------------------------------------------- #

def _ext(data):
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return ".webp"


def download_chapter(urls, ch_dir, referer):
    return tq.download_images(urls, ch_dir,
                              lambda u: http(u, referer=referer, binary=True))


def package(files, ch_dir, formats):
    cbz = ch_dir.parent / (ch_dir.name + ".cbz")
    pdf = ch_dir.parent / (ch_dir.name + ".pdf")
    if "cbz" in formats:
        tq.make_cbz(files, cbz)
        print(f"      -> {cbz.name}")
    if "pdf" in formats:
        tq.make_pdf(files, pdf)
        print(f"      -> {pdf.name}")
    if "stitch" in formats:
        made = pack.make_stitch(files, ch_dir)
        if made:
            print(f"      -> ghep lien: {len(made)} file")
    if "folder" not in formats:
        for f in files:
            f.unlink(missing_ok=True)
        try:
            ch_dir.rmdir()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def run(args):
    slugid = parse_slugid(args.url)
    title, chapters = get_chapters(slugid)
    if not chapters:
        sys.exit("Khong lay duoc danh sach chuong.")
    nums = [n for n, _ in chapters]
    rng = f" (chuong {min(nums):g}..{max(nums):g})"

    sel = chapters
    if args.range:
        a, b = args.range
        sel = [c for c in sel if a <= c[0] <= b]
    if args.limit:
        sel = sel[: args.limit]

    if args.list:
        for n, ns in sel:
            print(f"  Ch {ns}")
        return

    if args.check:
        imgs = get_images(slugid, (sel or chapters)[0][1])
        print("\n================ CHAN DOAN ================")
        print(f"  Ket qua  : {'TAI DUOC (HTTP gzip) ✔' if imgs else 'CHUA LAY DUOC ✘'}")
        print(f"  Truyen   : {title}")
        print(f"  So chuong: {len(chapters)}{rng}")
        if imgs:
            print(f"  Chuong dau: {len(imgs)} trang")
        print("  Cach     : HTTP + Accept-Encoding gzip, anh /img/comic nhung san, khong xao")
        print("===========================================")
        return

    out_dir = Path(args.out) / tq.slugify(title)
    done = tq.progress_load(out_dir)
    print(f"Truyen: {title} | Tong chuong: {len(chapters)}{rng}")
    print(f"Tai {len(sel)} chuong vao: {out_dir.resolve()}")
    if done:
        print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
    print()

    for i, (n, ns) in enumerate(sel, 1):
        label = f"Chuong {ns}"
        ch_dir = out_dir / tq.slugify(f"{i:04d} - {label}")
        cbz = ch_dir.parent / (ch_dir.name + ".cbz")
        if (ch_dir.name in done or cbz.exists()) and not args.overwrite:
            print(f"[{i}/{len(sel)}] (da co) {label}")
            done.add(ch_dir.name)
            continue
        print(f"[{i}/{len(sel)}] {label}")
        try:
            urls = get_images(slugid, ns)
            if not urls:
                print("      (khong tim thay anh)")
                continue
            saved = download_chapter(urls, ch_dir, referer=chapter_url(slugid, ns))
            if not saved:
                try:
                    ch_dir.rmdir()
                except OSError:
                    pass
                continue
            package(saved, ch_dir, args.format)
            done.add(ch_dir.name)
            tq.progress_save(out_dir, done)
        except Exception as e:
            print(f"      LOI: {e}")
        time.sleep(args.delay)
    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(description="Tai truyen dilib.vn (HTTP gzip + anh nhung san).")
    p.add_argument("url", help="Link bo (/<slug>-<id>.html) hoac 1 chuong")
    p.add_argument("--range", nargs=2, type=float, metavar=("A", "B"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--list", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--format", nargs="+", default=["folder", "cbz"],
                   choices=["folder", "cbz", "pdf", "stitch"])
    p.add_argument("--out", default="downloads")
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--overwrite", action="store_true")
    return p


if __name__ == "__main__":
    try:
        run(build_parser().parse_args())
    except KeyboardInterrupt:
        print("\nDa dung.")
