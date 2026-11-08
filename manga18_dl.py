# -*- coding: utf-8 -*-
"""
manga18_dl - Tai truyen tu manga18.me.

CACH LACH (xem THUAT_TOAN.md, gan giong manhwahub):
  - HTML TINH: danh sach chuong o trang `/manga/<slug>` (link `/manga/<slug>/chapter-N`).
  - Anh nhung san trong HTML chuong (img.pN data-src):
    `img-r2.manga18.me/uploads/<id>/<num>/<page>-<hash>.jpg` (webtoon dai, jpg).
  - KHONG can Referer, KHONG can gzip. Cloudflare bi dong. tq.http dung thang.
  - Lay anh: gom-theo-thu-muc chon folder nhieu anh nhat, sap theo so trang dau ten file.

DUNG:
  python manga18_dl.py "https://manga18.me/manga/<slug>" --check
  python manga18_dl.py "<link>" --limit 5 --out D:/tai_truyen --format folder stitch
"""

import argparse
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import truyenqq_dl as tq
import pack

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SITE = "https://manga18.me"
CDN_IMG = re.compile(
    r"https?://[a-z0-9.-]*manga18\.me/uploads/[^\s\"'<>]+?\.(?:jpe?g|png|webp)", re.I)


def parse_slug(url):
    m = re.search(r"/manga/([^/?#]+)", url)
    if not m:
        sys.exit("URL khong dung dang /manga/<slug>")
    return m.group(1)


def get_series_info(slug):
    html = tq.http(f"{SITE}/manga/{slug}", referer=SITE + "/")
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    t = (m.group(1) if m else slug)
    t = re.sub(r"^\s*Read\s+", "", t, flags=re.I)
    t = re.split(r"\s+at\s+Manga18", t, flags=re.I)[0]
    t = re.sub(r"\s+(?:Manhwa|Manga|Manhua)\s*$", "", t, flags=re.I).strip()
    rx = re.compile(r"/manga/" + re.escape(slug) + r"/chapter-([\d.]+)", re.I)
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
    return (t or slug), items


def _pagenum(url):
    fn = url.rsplit("/", 1)[-1]
    m = re.match(r"(\d+)", fn)
    return int(m.group(1)) if m else 1 << 30


def get_images(slug, num_str):
    html = tq.http(f"{SITE}/manga/{slug}/chapter-{num_str}", referer=f"{SITE}/manga/{slug}")
    groups = defaultdict(list)
    for u in CDN_IMG.findall(html):
        groups[u.rsplit("/", 1)[0]].append(u)
    if not groups:
        return []
    best = max(groups.values(), key=len)
    return sorted(set(best), key=_pagenum)


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
    return ".jpg"


def download_chapter(urls, ch_dir, referer):
    return tq.download_images(urls, ch_dir,
                              lambda u: tq.http(u, referer=referer, binary=True))


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
    slug = parse_slug(args.url)
    title, chapters = get_series_info(slug)
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
        imgs = get_images(slug, (sel or chapters)[0][1])
        print("\n================ CHAN DOAN ================")
        print(f"  Ket qua  : {'TAI DUOC (HTTP thuan) ✔' if imgs else 'CHUA LAY DUOC ✘'}")
        print(f"  Truyen   : {title}")
        print(f"  So chuong: {len(chapters)}{rng}")
        if imgs:
            print(f"  Chuong dau: {len(imgs)} trang (webtoon dai)")
        print("  Cach     : HTML tinh, anh img-r2.manga18.me nhung san, khong xao, khong can Referer")
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
            urls = get_images(slug, ns)
            if not urls:
                print("      (khong tim thay anh)")
                continue
            saved = download_chapter(urls, ch_dir, referer=f"{SITE}/manga/{slug}/chapter-{ns}")
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
    p = argparse.ArgumentParser(description="Tai truyen manga18.me (HTTP tinh).")
    p.add_argument("url", help="Link bo (/manga/<slug>) hoac 1 chuong")
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
