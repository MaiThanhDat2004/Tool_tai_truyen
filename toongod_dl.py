# -*- coding: utf-8 -*-
"""
toongod_dl - Tai truyen tu toongod.org (Madara/wp-manga sau Cloudflare).

CACH LACH (xem THUAT_TOAN.md):
  - Cloudflare CHALLENGE THAT ("Just a moment", 403 voi curl). NHUNG cf_clearance
    cua trang nay TAI DUNG DUOC ngoai trinh duyet -> chien luoc LAI:
    1) Chrome THAT vuot CF 1 lan (ensure_chrome) -> hung cookie cf_clearance + Chrome UA
       qua CDP (Network.getCookies, /json/version).
    2) Tu do tai bang HTTP THUAN (urllib) + Cookie + dung UA Chrome (+gzip).
  - Trang chuong/series tren www.toongod.org (can cookie). ANH tren i.tngcdn.com
    (CDN rieng, CHI can Referer, khong can cookie). KHONG xao tron.
  - Madara: anh class="wp-manga-chapter-img"; lay kieu gom-theo-thu-muc.

DUNG:
  python toongod_dl.py "https://www.toongod.org/webtoon/<slug>/" --check
  python toongod_dl.py "<link>" --limit 5 --out D:/tai_truyen --format folder stitch
"""

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
import zlib
from collections import defaultdict
from html import unescape
from pathlib import Path

import truyenqq_dl as tq
import pack
from mangafire_dl import ensure_chrome
from webtoon_dl import CDP

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SITE = "https://www.toongod.org"
PORT = 9222
CDN_IMG = re.compile(r"https?://i\.tngcdn\.com/[^\s\"'<>]+?\.(?:jpe?g|png|webp)", re.I)


# --------------------------------------------------------------------------- #
# Phien Cloudflare (Chrome that vuot 1 lan -> cookie + UA)
# --------------------------------------------------------------------------- #

def get_cf_session(url):
    ensure_chrome(url)
    ua = json.load(urllib.request.urlopen(
        f"http://127.0.0.1:{PORT}/json/version", timeout=8))["User-Agent"]
    cdp = CDP().open_tab()
    try:
        cdp.send("Page.navigate", {"url": url})
        for _ in range(25):
            time.sleep(2)
            t = cdp.evaluate("document.title") or ""
            if t and "moment" not in t.lower():
                break
        cdp.send("Network.enable")
        gid = cdp.send("Network.getCookies", {"urls": [url]})
        cookies, end = [], time.time() + 8
        while time.time() < end:
            try:
                m = json.loads(cdp.ws.recv())
            except Exception:
                continue
            if m.get("id") == gid:
                cookies = m.get("result", {}).get("cookies", [])
                break
        cookie = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        return {"cookie": cookie, "ua": ua}
    finally:
        cdp.close()


def http(url, sess, referer=None, binary=False, retries=4):
    last = None
    for k in range(retries):
        try:
            h = {"User-Agent": sess["ua"],
                 "Accept-Language": "en-US,en;q=0.9",
                 "Accept-Encoding": "gzip, deflate",
                 "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,*/*;q=0.8"}
            if sess.get("cookie"):
                h["Cookie"] = sess["cookie"]
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

def parse_slug(url):
    m = re.search(r"/webtoon/([^/?#]+)", url)
    if not m:
        sys.exit("URL khong dung dang /webtoon/<slug>")
    return m.group(1)


def get_series_info(slug, sess):
    html = http(f"{SITE}/webtoon/{slug}/", sess, referer=SITE + "/")
    if "just a moment" in html.lower():
        raise RuntimeError("Van bi Cloudflare (cookie het han?)")
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", unescape(tq.strip_tags(m.group(1)) if m else "")).strip()
    if not title or len(title) > 80:
        title = slug.replace("-manhwa", "").replace("-", " ").title()
    rx = re.compile(r"/webtoon/" + re.escape(slug) + r"/chapter-([\d.]+)/?", re.I)
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


def _pagenum(url):
    fn = url.rsplit("/", 1)[-1]
    nums = re.findall(r"\d+", fn)
    return int(nums[-1]) if nums else 1 << 30


def get_images(slug, num_str, sess):
    html = http(f"{SITE}/webtoon/{slug}/chapter-{num_str}/", sess,
                referer=f"{SITE}/webtoon/{slug}/")
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
    return ".jpg"


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
    sess = get_cf_session(f"{SITE}/webtoon/{slug}/")
    if not sess["cookie"]:
        sys.exit("Khong lay duoc cookie CF. Thu lai (Chrome can vuot 'Just a moment' 1 lan).")
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
        print("  Cach     : Chrome vuot CF 1 lan -> cookie -> tai HTTP; anh i.tngcdn.com (Referer)")
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
                sess = get_cf_session(f"{SITE}/webtoon/{slug}/")
                urls = get_images(slug, ns, sess)
            if not urls:
                print("      (khong tim thay anh)")
                continue
            saved = download_chapter(urls, ch_dir, sess,
                                     referer=f"{SITE}/webtoon/{slug}/chapter-{ns}/")
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
    p = argparse.ArgumentParser(description="Tai truyen toongod.org (Chrome vuot CF + HTTP cookie).")
    p.add_argument("url", help="Link bo (/webtoon/<slug>/) hoac 1 chuong")
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
