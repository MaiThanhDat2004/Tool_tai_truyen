# -*- coding: utf-8 -*-
"""
zettruyen_dl - Tai truyen tu zettruyen.club (ho zinmanga, URL kieu VN).

BAI TOAN / CACH LACH (xem THUAT_TOAN.md):
  - SPA (Next.js app-router) nhung HTTP THUAN van du:
    * Danh sach chuong: API `/api/comics/<slug>/chapters?per_page=-1`
      -> JSON {data:{chapters:[{chapter_num, chapter_name, ...}]}}.
      (Trang series tinh CHI hien 1-2 chuong -> phai goi API moi du.)
    * Trang chuong `/truyen-tranh/<slug>/chuong-<num>` NHUNG SAN URL anh trong
      HTML (script __next_f): `cdn<N>.zetimage.com/<slug>/<num>/<page>.jpg`.
      CDN shard khac nhau theo chuong -> DOC TU HTML, dung doan host.
  - Anh KHONG xao tron, tai thang + Referer = origin. Cloudflare chi la script bi dong.

DUNG:
  python zettruyen_dl.py "https://www.zettruyen.club/truyen-tranh/<slug>" --check
  python zettruyen_dl.py "<link bo>" --limit 5 --out D:/tai_truyen
  python zettruyen_dl.py "<link bo>" --range 1 10
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import truyenqq_dl as tq      # http, slugify, make_cbz, make_pdf, origin, progress_*, have_page, write_atomic
import pack

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IMG_RE = re.compile(
    r"cdn\d+\.zetimage\.com/[A-Za-z0-9._/-]+?/(\d+)/(\d+)\.(jpe?g|png|webp)", re.I)


def parse_slug(url):
    m = re.search(r"/truyen-tranh/([^/?#]+)", url)
    if not m:
        sys.exit("URL khong dung dang /truyen-tranh/<slug>")
    return m.group(1)


def get_title(origin, slug):
    try:
        html = tq.http(f"{origin}/truyen-tranh/{slug}", referer=origin)
        m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        t = re.sub(r"\s+", " ", (m.group(1) if m else "")).strip()
        t = re.sub(r"^Truyện tranh\s*", "", t, flags=re.I)
        t = re.split(r"\s*[|]\s*", t)[0].strip()
        return t or slug
    except Exception:
        return slug


def get_chapters(origin, slug):
    """API zinmanga -> [(num_int, chapter_num_str, name)] sap tang dan."""
    url = f"{origin}/api/comics/{slug}/chapters?per_page=-1"
    data = json.loads(tq.http(url, referer=origin + "/"))
    chaps = (data.get("data") or {}).get("chapters") or data.get("chapters") or []
    out = []
    for c in chaps:
        num = c.get("chapter_num")
        if num is None:
            continue
        out.append((float(num), str(num), c.get("chapter_name") or f"Chapter {num}"))
    out.sort(key=lambda x: x[0])
    return out


def chapter_url(origin, slug, num_str):
    return f"{origin}/truyen-tranh/{slug}/chuong-{num_str}"


def get_images(origin, slug, num_str):
    """Doc HTML trang chuong -> URL anh dung thu tu trang."""
    html = tq.http(chapter_url(origin, slug, num_str), referer=origin + "/")
    html = html.replace("\\/", "/")
    found = {}     # page_num -> url
    for m in IMG_RE.finditer(html):
        chap_dir, page = m.group(1), int(m.group(2))
        if chap_dir != num_str:          # chi lay dung thu muc chuong nay
            continue
        url = "https://" + m.group(0)
        if page not in found:
            found[page] = url
    return [found[k] for k in sorted(found)]


# --------------------------------------------------------------------------- #
# Tai 1 chuong (resume tung anh)
# --------------------------------------------------------------------------- #

def _ext(data):
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
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
    o = tq.origin(args.url).rstrip("/")
    slug = parse_slug(args.url)
    title = get_title(o, slug)
    chapters = get_chapters(o, slug)
    if not chapters:
        sys.exit("Khong lay duoc danh sach chuong tu API.")
    nums = [n for n, _, _ in chapters]
    rng = f" (chuong {min(nums):g}..{max(nums):g})"

    sel = chapters
    if args.range:
        a, b = args.range
        sel = [c for c in sel if a <= c[0] <= b]
    if args.limit:
        sel = sel[: args.limit]

    if args.list:
        for n, ns, name in sel:
            print(f"  Ch {ns}: {name}")
        return

    if args.check:
        imgs = get_images(o, slug, (sel or chapters)[0][1])
        print("\n================ CHAN DOAN ================")
        print(f"  Ket qua  : {'TAI DUOC (HTTP + API) ✔' if imgs else 'CHUA LAY DUOC ✘'}")
        print(f"  Truyen   : {title}")
        print(f"  So chuong: {len(chapters)}{rng}")
        if imgs:
            print(f"  Chuong dau: {len(imgs)} trang")
        print("  Cach     : API zinmanga + tai anh CDN zetimage (Referer), khong xao tron")
        print("===========================================")
        return

    out_dir = Path(args.out) / tq.slugify(title)
    done = tq.progress_load(out_dir)
    print(f"Truyen: {title} | Tong chuong: {len(chapters)}{rng}")
    print(f"Tai {len(sel)} chuong vao: {out_dir.resolve()}")
    if done:
        print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
    print()

    for i, (n, ns, name) in enumerate(sel, 1):
        label = f"Chuong {ns}"
        ch_dir = out_dir / tq.slugify(f"{i:04d} - {label}")
        cbz = ch_dir.parent / (ch_dir.name + ".cbz")
        if (ch_dir.name in done or cbz.exists()) and not args.overwrite:
            print(f"[{i}/{len(sel)}] (da co) {label}")
            done.add(ch_dir.name)
            continue
        print(f"[{i}/{len(sel)}] {label}")
        try:
            urls = get_images(o, slug, ns)
            if not urls:
                print("      (khong tim thay anh)")
                continue
            saved = download_chapter(urls, ch_dir, referer=o + "/")
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
    p = argparse.ArgumentParser(description="Tai truyen zettruyen.club (HTTP + API zinmanga).")
    p.add_argument("url", help="Link bo (/truyen-tranh/<slug>)")
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
