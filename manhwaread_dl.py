# -*- coding: utf-8 -*-
"""
manhwaread_dl - Tai truyen tu manhwaread.com (sau Cloudflare; anh trong chapterData base64).

CACH LACH (xem THUAT_TOAN.md):
  - Cloudflare challenge -> muon cookie cf_clearance qua Chrome 1 lan (tai dung
    `toongod_dl.get_cf_session` + `http`), roi tai HTTP.
  - Danh sach chuong: series HTML co link `/manhwa/<slug>/chapter-NN/`.
  - ANH KHONG nam o <img> ma trong bien JS:
        chapterData = {"data": "<base64>", "base": "https://manread.xyz/<mangaId>"}
    `data` = base64(JSON [{"src":"<chapId>/mr_NNN.jpg","w":..,"h":..}, ...]).
    URL anh = base + "/" + src. Anh webp (du duoi .jpg) -> detect magic bytes.
    CDN manread.xyz CHAN HOTLINK -> can `Referer`.

DUNG:
  python manhwaread_dl.py "https://manhwaread.com/manhwa/<slug>/" --check
  python manhwaread_dl.py "<link>" --limit 5 --out D:/tai_truyen --format folder stitch
"""

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

import truyenqq_dl as tq
import pack
from toongod_dl import get_cf_session, http

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SITE = "https://manhwaread.com"


def parse_slug(url):
    m = re.search(r"/manhwa/([^/?#]+)", url)
    if not m:
        sys.exit("URL khong dung dang /manhwa/<slug>")
    return m.group(1)


def get_series_info(slug, sess):
    html = http(f"{SITE}/manhwa/{slug}/", sess, referer=SITE + "/")
    if "just a moment" in html.lower():
        raise RuntimeError("Van bi Cloudflare (cookie het han?)")
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", (m.group(1) if m else slug)).strip()
    title = re.split(r"\s*-\s*#?\d+\s*-", title)[0].strip()      # bo " - #12474 - Read..."
    title = re.split(r"\s*-\s*Read Manhwa", title)[0].strip() or slug
    # chuong: giu nguyen chuoi so nhu xuat hien (chapter-01, chapter-10.5...)
    rx = re.compile(r"/manhwa/" + re.escape(slug) + r"/chapter-([\d.]+)/?", re.I)
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


def get_images(slug, num_str, sess):
    html = http(f"{SITE}/manhwa/{slug}/chapter-{num_str}/", sess,
                referer=f"{SITE}/manhwa/{slug}/")
    m = re.search(r"chapterData\s*=\s*(\{.*?\})\s*;", html, re.S)
    if not m:
        return []
    obj = json.loads(m.group(1))
    base = (obj.get("base") or "").rstrip("/")
    try:
        arr = json.loads(base64.b64decode(obj["data"]))
    except Exception:
        return []
    urls = []
    for it in arr:
        src = (it.get("src") if isinstance(it, dict) else it) or ""
        src = src.lstrip("/")
        if src:
            urls.append(f"{base}/{src}")
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


def download_chapter(urls, ch_dir, sess, referer):
    return tq.download_images(urls, ch_dir,
                              lambda u: http(u, sess, referer=referer, binary=True))


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
    print("Vuot Cloudflare bang Chrome that (1 lan)...")
    sess = get_cf_session(f"{SITE}/manhwa/{slug}/")
    if not sess["cookie"]:
        sys.exit("Khong lay duoc cookie CF. Thu lai.")
    title, chapters = get_series_info(slug, sess)
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
        imgs = get_images(slug, (sel or chapters)[0][1], sess)
        print("\n================ CHAN DOAN ================")
        print(f"  Ket qua  : {'TAI DUOC (CF cookie + HTTP) ✔' if imgs else 'CHUA LAY DUOC ✘'}")
        print(f"  Truyen   : {title}")
        print(f"  So chuong: {len(chapters)}{rng}")
        if imgs:
            print(f"  Chuong dau: {len(imgs)} trang")
        print("  Cach     : Chrome vuot CF -> cookie -> HTTP; anh tu chapterData(base64), CDN can Referer")
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
            try:
                urls = get_images(slug, ns, sess)
            except RuntimeError:
                print("      (cookie CF het han -> vuot lai...)")
                sess = get_cf_session(f"{SITE}/manhwa/{slug}/")
                urls = get_images(slug, ns, sess)
            if not urls:
                print("      (khong tim thay anh)")
                continue
            saved = download_chapter(urls, ch_dir, sess,
                                     referer=f"{SITE}/manhwa/{slug}/chapter-{ns}/")
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
    p = argparse.ArgumentParser(description="Tai truyen manhwaread.com (CF cookie + chapterData base64).")
    p.add_argument("url", help="Link bo (/manhwa/<slug>/) hoac 1 chuong")
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
