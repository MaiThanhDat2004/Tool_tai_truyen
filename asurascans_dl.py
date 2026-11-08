# -*- coding: utf-8 -*-
"""
asurascans_dl - Tai truyen tu asurascans.com (Asura Scans).

CACH LACH (xem THUAT_TOAN.md):
  - HTTP TINH du dung: danh sach chuong o trang `/comics/<slug>` (link `/chapter/N`),
    anh nhung san trong HTML chuong: `cdn.asurascans.com/asura-images/chapters/<baseslug>/<num>/NNN.webp`.
    KHONG can Referer/cookie cho anh. tq.http chay thang.
  - DU PHONG Cloudflare: Asura thi thoang bat CF challenge. Neu HTML tra "Just a moment"
    -> tu muon cookie qua Chrome (toongod_dl.get_cf_session) roi tai lai. Anh khong xao.

DUNG:
  python asurascans_dl.py "https://asurascans.com/comics/<slug>" --check
  python asurascans_dl.py "<link>" --limit 5 --out D:/tai_truyen --format folder stitch
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

SITE = "https://asurascans.com"
CDN_IMG = re.compile(
    r"https?://cdn\.asurascans\.com/[^\s\"'<>]+?/\d+/\d+\.(?:jpe?g|png|webp)", re.I)

_sess = None       # phien Cloudflare (chi tao khi can)


def fetch(url, referer=None, binary=False):
    """tq.http truoc; neu dinh Cloudflare -> muon cookie qua Chrome roi tai lai."""
    global _sess
    if _sess is None:
        try:
            txt = tq.http(url, referer=referer, binary=binary)
            if binary or "just a moment" not in txt.lower():
                return txt
        except Exception:
            pass
        # -> CF: tao phien
        from toongod_dl import get_cf_session
        print("      (gap Cloudflare -> vuot bang Chrome 1 lan...)")
        _sess = get_cf_session(SITE + "/")
    from toongod_dl import http as cf_http
    return cf_http(url, _sess, referer=referer, binary=binary)


def parse_slug(url):
    m = re.search(r"/comics/([^/?#]+)", url)
    if not m:
        sys.exit("URL khong dung dang /comics/<slug>")
    return m.group(1)


def get_series_info(slug):
    html = fetch(f"{SITE}/comics/{slug}", referer=SITE + "/")
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    title = unescape(re.sub(r"\s+", " ", (m.group(1) if m else slug))).strip()
    title = re.split(r"\s*[|]\s*Asura", title)[0].strip() or slug
    rx = re.compile(r"/comics/" + re.escape(slug) + r"/chapter/([\d.]+)", re.I)
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


def _pagenum(url):
    fn = url.rsplit("/", 1)[-1]
    m = re.match(r"(\d+)", fn)
    return int(m.group(1)) if m else 1 << 30


def get_images(slug, num_str):
    html = fetch(f"{SITE}/comics/{slug}/chapter/{num_str}", referer=f"{SITE}/comics/{slug}")
    groups = defaultdict(list)
    for u in CDN_IMG.findall(html):
        groups[u.rsplit("/", 1)[0]].append(u.strip())
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
    return ".webp"


def download_chapter(urls, ch_dir, referer):
    return tq.download_images(urls, ch_dir,
                              lambda u: fetch(u, referer=referer, binary=True))


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
        print("  Cach     : HTML tinh, anh cdn.asurascans.com nhung san (du phong CF), khong xao")
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
            saved = download_chapter(urls, ch_dir, referer=f"{SITE}/comics/{slug}/chapter/{ns}")
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
    p = argparse.ArgumentParser(description="Tai truyen asurascans.com (HTTP tinh + du phong CF).")
    p.add_argument("url", help="Link bo (/comics/<slug>) hoac 1 chuong")
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
