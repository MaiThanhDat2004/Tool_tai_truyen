# -*- coding: utf-8 -*-
"""
kunmanga_dl - Adapter cho ho site "zinmanga" (vd kunmanga.co.uk).

Cac site nay la SPA:
  - Danh sach chuong qua API:  /api/comics/<slug>/chapters?per_page=-1
  - URL anh moi chuong NHUNG SAN trong HTML trang chuong (bi escape \/), tai CDN
    zinmanga, CAN header Referer (thieu -> 403).

Cach lam: lay chuong qua API; voi moi chuong, doc HTML va trich thang URL anh
(khong can trinh duyet, khong doan mau - moi bo mot kieu ten file khac nhau:
01.webp / 0.webp / chap_0_1.jpg ...). Bo qua trang placeholder rong.

    python kunmanga_dl.py "https://www.kunmanga.co.uk/manga/absolute-regression"
    python kunmanga_dl.py "<link>" --range 1 20 --format folder cbz
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import truyenqq_dl as tq          # slugify, make_cbz, make_pdf
import pack

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
JUNK = re.compile(r"(icon|logo|avatar|thumb|/ads?/|banner|sprite|favicon)", re.I)


def origin(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def manga_slug(url):
    m = re.search(r"/manga/([^/]+)", url)
    return m.group(1) if m else url.rstrip("/").split("/")[-1]


def http(url, referer=None, binary=False, timeout=40, retries=3):
    last = None
    for a in range(retries):
        try:
            h = {"User-Agent": UA, "Accept": "*/*"}
            if referer:
                h["Referer"] = referer
            r = urllib.request.urlopen(
                urllib.request.Request(url, headers=h), timeout=timeout)
            return r.status, (r.read() if binary else r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            return e.code, b"" if binary else ""
        except Exception as e:
            last = e
            time.sleep(1.2 * (a + 1))
    raise RuntimeError(f"GET that bai: {url} ({last})")


# --------------------------------------------------------------------------- #
# API chuong
# --------------------------------------------------------------------------- #

def get_chapters(base, slug):
    url = f"{base}/api/comics/{slug}/chapters?per_page=-1&order=asc"
    st, body = http(url, referer=base + "/")
    if st != 200:
        return []
    try:
        chs = json.loads(body)["data"]["chapters"]
    except Exception:
        return []
    out = []
    for c in chs:
        out.append({
            "slug": c.get("chapter_slug") or f"chapter-{c.get('chapter_num')}",
            "num": c.get("chapter_num"),
            "name": c.get("chapter_name") or "",
        })
    # sap xep theo so chuong
    def key(c):
        try:
            return float(c["num"])
        except (TypeError, ValueError):
            return 1e9
    out.sort(key=key)
    return out


# --------------------------------------------------------------------------- #
# Lay anh tu HTML trang chuong (khong can trinh duyet, khong doan mau)
# --------------------------------------------------------------------------- #

def extract_images(html):
    """Doc thang URL anh tu HTML chuong. Moi bo dung quy uoc khac nhau
    (thu muc theo slug/so/hash; ten file 01.webp / 0.webp / chap_0_1.jpg ...)
    nen ta KHONG doan: lay tat ca URL anh, chon thu muc co NHIEU anh nhat
    (= thu muc trang truyen), roi sap theo so trong ten file."""
    h = html.replace("\\/", "/")                  # bo escape \/ trong JSON nhung
    urls = re.findall(r'https?://[^\s"\'<>\\)]+?\.(?:jpe?g|png|webp)', h, re.I)
    cands = [u for u in dict.fromkeys(urls) if not JUNK.search(u)]
    if not cands:
        return []
    from collections import Counter
    bydir = Counter(u.rsplit("/", 1)[0] for u in cands)
    top_dir = bydir.most_common(1)[0][0]
    sel = [u for u in cands if u.rsplit("/", 1)[0] == top_dir]

    def order(u):
        nums = re.findall(r"\d+", u.rsplit("/", 1)[1])
        return int(nums[-1]) if nums else 0

    sel.sort(key=order)
    return sel


def download_chapter(chapter_url, out_dir, referer):
    st, html = http(chapter_url, referer=referer)
    if st != 200 or not html:
        return []
    urls = extract_images(html)
    if not urls:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    saved, idx = [], 1
    for u in urls:
        try:
            st2, data = http(u, referer=referer, binary=True)
        except Exception:
            st2, data = 0, b""
        if st2 != 200 or len(data) < 800:         # bo trang loi / placeholder rong
            continue
        m = re.search(r"\.(jpe?g|png|webp)", u, re.I)
        ext = m.group(1).lower().replace("jpeg", "jpg") if m else "jpg"
        fp = out_dir / f"{str(idx).zfill(3)}.{ext}"
        fp.write_bytes(data)
        saved.append(fp)
        idx += 1
        print(f"\r      trang {idx - 1}", end="", flush=True)
        time.sleep(0.03)
    print()
    return saved


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


def run(args):
    base = origin(args.url)
    slug = manga_slug(args.url)
    ref = base + "/"

    chapters = get_chapters(base, slug)
    if not chapters:
        print("Khong lay duoc danh sach chuong qua API (co the khong phai site zinmanga).")
        sys.exit(2)
    print(f"\nTruyen: {slug}")
    print(f"Tong chuong (qua API): {len(chapters)}")

    # Loc range/limit
    sel = chapters
    if args.range:
        a, b = args.range
        sel = [c for c in sel if c["num"] is not None and a <= float(c["num"]) <= b]
    if args.limit:
        sel = sel[: args.limit]

    if args.list:
        for c in sel:
            print(f"  Ch {c['num']}  {c['name']}  ({c['slug']})")
        return

    out_dir = Path(args.out) / tq.slugify(slug)
    done = tq.progress_load(out_dir)
    print(f"Tai {len(sel)} chuong vao: {out_dir.resolve()}")
    if done:
        print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
    print()

    for i, c in enumerate(sel, 1):
        label = f"Chuong {c['num']}"
        print(f"[{i}/{len(sel)}] {label}")
        ch_dir = out_dir / tq.slugify(f"{i:04d} - {label}")
        cbz = ch_dir.parent / (ch_dir.name + ".cbz")
        if (ch_dir.name in done or cbz.exists()) and not args.overwrite:
            print("      (da co, bo qua)")
            done.add(ch_dir.name)
            continue
        try:
            ch_url = f"{base}/manga/{slug}/{c['slug']}"
            files = download_chapter(ch_url, ch_dir, ref)
            if not files:
                print("      (khong co anh)")
                continue
            print(f"      {len(files)} trang")
            package(files, ch_dir, args.format)
            done.add(ch_dir.name)
            tq.progress_save(out_dir, done)
        except Exception as e:
            print(f"      LOI: {e}")
        time.sleep(args.delay)
    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(description="Tai truyen ho site zinmanga/kunmanga.")
    p.add_argument("url", help="Link bo truyen kunmanga/zinmanga")
    p.add_argument("--range", nargs=2, type=float, metavar=("A", "B"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--list", action="store_true", help="Chi liet ke chuong")
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
