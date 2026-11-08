# -*- coding: utf-8 -*-
"""
kaynscan_dl - Tai truyen tu kaynscan.org.

CACH LACH (xem THUAT_TOAN.md):
  - SPA (anh hien thi qua lazy-load IntersectionObserver -> tab NEN khong tai,
    de tuong nham "khong co anh"). NHUNG URL anh content NAM SAN trong HTML chuong:
        storage.kaynscan.org/public/upload/series/<slug>/<uuid>/page-NNNN_*.webp
    Dau hieu phan biet anh TRANG vs UI: ten file co `/page-NNNN`. -> tai HTTP thuan,
    sap theo so trang, khoi can trinh duyet. Anh webp, can `Referer`. KHONG xao.
  - Danh sach chuong: series HTML `/series/<slug>/chapter-N`.

DUNG:
  python kaynscan_dl.py "https://kaynscan.org/series/<slug>" --check
  python kaynscan_dl.py "<link>" --limit 5 --out D:/tai_truyen --format folder stitch
"""

import argparse
import re
import sys
import time
from collections import defaultdict
from html import unescape
from pathlib import Path

import truyenqq_dl as tq
import pack

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SITE = "https://kaynscan.org"
# anh content luon nam duoi '.../series/...'. Co 2 kieu dat ten (tuy bo):
#   - Fog Land:  /public/upload/series/<slug>/<uuid>/page-NNNN_*.webp
#   - Sashimi:   /upload/series/<slug2>/<hash>/NNN.jpg
# -> lay MOI anh storage duoi /series/, gom theo thu muc, chon folder nhieu anh nhat,
#    sap theo so trong ten file (page-NNNN hoac NNN). Logo/cover (/upload/<date>/...) bi loai
#    vi khong co '/series/'.
STORAGE_SERIES_IMG = re.compile(
    r"https?://storage\.kaynscan\.org/[^\s\"'<>]*?/series/[^\s\"'<>]+?\.(?:webp|jpe?g|png)", re.I)


def parse_slug(url):
    m = re.search(r"/series/([^/?#]+)", url)
    if not m:
        sys.exit("URL khong dung dang /series/<slug>")
    return m.group(1)


def get_series_info(slug):
    html = tq.http(f"{SITE}/series/{slug}", referer=SITE + "/")
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    title = unescape(re.sub(r"\s+", " ", (m.group(1) if m else slug))).strip()
    title = re.sub(r"\s*Manhwa\s*$", "", title, flags=re.I).strip() or slug
    rx = re.compile(r"/series/" + re.escape(slug) + r"/chapter-([\d.]+)", re.I)
    seen, items = set(), []
    for ns in rx.findall(html):
        if ns in seen:
            continue
        seen.add(ns)
        try:
            items.append((float(ns), ns))
        except ValueError:
            pass
    items.sort(key=lambda x: x[0])
    return title, items


class LockedChapter(Exception):
    """Chuong PREMIUM/early-access (member tra phi) - server khong gui anh."""


# dau hieu chuong bi khoa (premium/early-access) - chi xuat hien khi chuong KHOA that
_LOCK_RE = re.compile(
    r'premium chapter is waiting|"locked"\s*:\s*"Locked Chapter"|statusLocked|Unlock Premium',
    re.I)


def get_images(slug, ns):
    html = tq.http(f"{SITE}/series/{slug}/chapter-{ns}", referer=f"{SITE}/series/{slug}")
    # GIU thu tu xuat hien trong HTML (= thu tu doc), gom theo thu muc
    urls = tq.largest_image_group(STORAGE_SERIES_IMG.findall(html))
    if not urls and _LOCK_RE.search(html):
        raise LockedChapter()
    return urls


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
        locked = False
        try:
            imgs = get_images(slug, (sel or chapters)[0][1])
        except LockedChapter:
            imgs, locked = [], True
        print("\n================ CHAN DOAN ================")
        if locked:
            res = "Chuong dau bi KHOA (premium) - thu chuong free khac"
        else:
            res = "TAI DUOC (HTTP tinh) ✔" if imgs else "CHUA LAY DUOC ✘"
        print(f"  Ket qua  : {res}")
        print(f"  Truyen   : {title}")
        print(f"  So chuong: {len(chapters)}{rng}")
        if imgs:
            print(f"  Chuong dau: {len(imgs)} trang")
        print("  Cach     : HTML tinh, anh storage.kaynscan.org/.../series/ (Referer), khong xao")
        print("  Luu y    : chuong PREMIUM/early-access (member) -> KHONG tai duoc (tra phi).")
        print("===========================================")
        return

    out_dir = Path(args.out) / tq.slugify(title)
    done = tq.progress_load(out_dir)
    print(f"Truyen: {title} | Tong chuong: {len(chapters)}{rng}")
    print(f"Tai {len(sel)} chuong vao: {out_dir.resolve()}")
    if done:
        print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
    print()

    locked = 0
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
            try:
                urls = get_images(slug, ns)
            except LockedChapter:
                print("      🔒 chuong PREMIUM / early-access (member tra phi) - bo qua")
                locked += 1
                continue
            if not urls:
                print("      (khong tim thay anh)")
                continue
            saved = download_chapter(urls, ch_dir, referer=f"{SITE}/series/{slug}/chapter-{ns}")
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
    if locked:
        print(f"\n⚠️  {locked} chuong bi KHOA (premium/early-access cho member tra phi) - "
              f"khong tai duoc (noi dung tra phi, khong ho tro vuot).")
    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(description="Tai truyen kaynscan.org (HTTP tinh, anh /page-NNNN).")
    p.add_argument("url", help="Link bo (/series/<slug>) hoac 1 chuong")
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
