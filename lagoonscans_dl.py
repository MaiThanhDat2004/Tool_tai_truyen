# -*- coding: utf-8 -*-
"""
lagoonscans_dl - Tai truyen tu lagoonscans.com (WordPress/Madara, reader 'ts_reader').

CACH LACH (xem THUAT_TOAN.md):
  - HTTP TINH du dung. Danh sach chuong o trang series `/manga/<slug>/`
    (link phang `<slug>-chapter-N/`).
  - Anh KHONG o <img> ma trong loi goi JS:
        ts_reader.run({... "sources":[{"images":["url1","url2",...]}] ...});
    -> trich JSON, lay sources[0].images. Anh webp o `wp-content/uploads/...`, can `Referer`.
  - KHONG xao tron. (Madara 'ts_reader' pattern - nhieu site dung chung.)

DUNG:
  python lagoonscans_dl.py "https://lagoonscans.com/manga/<slug>/" --check
  python lagoonscans_dl.py "<link>" --limit 5 --out D:/tai_truyen --format folder stitch
"""

import argparse
import json
import re
import sys
import time
from html import unescape
from pathlib import Path

import truyenqq_dl as tq
import pack

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SITE = "https://lagoonscans.com"
TS_READER = re.compile(r"ts_reader\.run\((\{.*?\})\);", re.S)


def parse_slug(url):
    m = re.search(r"/manga/([^/?#]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"lagoonscans\.com/([a-z0-9-]+?)-chapter-[\d.]+", url, re.I)
    if m:
        return m.group(1)
    sys.exit("URL khong dung dang /manga/<slug>/")


def get_series_info(slug):
    html = tq.http(f"{SITE}/manga/{slug}/", referer=SITE + "/")
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    title = unescape(re.sub(r"\s+", " ", (m.group(1) if m else slug))).strip()
    title = re.split(r"\s*-\s*Lagoon Scans", title)[0].strip() or slug
    rx = re.compile(re.escape(slug) + r"-chapter-([\d.]+)/", re.I)
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


def chapter_url(slug, ns):
    return f"{SITE}/{slug}-chapter-{ns}/"


def get_images(slug, ns):
    html = tq.http(chapter_url(slug, ns), referer=f"{SITE}/manga/{slug}/")
    m = TS_READER.search(html)
    if not m:
        return []
    try:
        obj = json.loads(m.group(1))
    except Exception:
        return []
    srcs = obj.get("sources") or []
    if not srcs:
        return []
    # defaultSource (neu co) hoac source dau
    di = obj.get("defaultSource", 0)
    try:
        imgs = srcs[int(di)].get("images", [])
    except Exception:
        imgs = srcs[0].get("images", [])
    return [u.strip() for u in imgs if u and u.strip()]


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
        imgs = get_images(slug, (sel or chapters)[0][1])
        print("\n================ CHAN DOAN ================")
        print(f"  Ket qua  : {'TAI DUOC (HTTP tinh) ✔' if imgs else 'CHUA LAY DUOC ✘'}")
        print(f"  Truyen   : {title}")
        print(f"  So chuong: {len(chapters)}{rng}")
        if imgs:
            print(f"  Chuong dau: {len(imgs)} trang")
        print("  Cach     : HTML tinh, anh tu ts_reader.run (Madara), can Referer, khong xao")
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
            saved = download_chapter(urls, ch_dir, referer=chapter_url(slug, ns))
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
    p = argparse.ArgumentParser(description="Tai truyen lagoonscans.com (Madara ts_reader).")
    p.add_argument("url", help="Link bo (/manga/<slug>/) hoac 1 chuong")
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
