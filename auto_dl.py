# -*- coding: utf-8 -*-
"""
auto_dl - Tai truyen "tu dong": dua link BAT KY, tool tu phan tich & chan doan.

Quy trinh:
  1. Dinh tuyen: mangadex.org -> goi mangadex_dl.py.
  2. Voi trang khac: thu HTTP TINH (doc thang HTML, khong can trinh duyet).
  3. CHAN DOAN (probe) trc khi tai that:
       - tim danh sach chuong + anh noi dung
       - TAI THU 1 anh that, kiem tra dung la anh (magic bytes) & du lon
  4. Quyet dinh:
       - probe OK  -> tai ca bo / chuong.
       - probe HONG -> in LY DO ro rang roi DUNG (exit code != 0).

LUU Y: khong dam bao moi trang. Trang can JavaScript de nap anh, hoac chan
Cloudflare -> tool se BAO va dung, goi y dung mangafire_dl.py (Chrome go loi).

Vi du:
    python auto_dl.py "https://truyenqqko.com/truyen-tranh/...-13507"
    python auto_dl.py "https://.../...-chap-1"
    python auto_dl.py "<link>" --range 1 20 --format folder cbz pdf
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

import truyenqq_dl as tq          # tai dung lai: http, slugify, origin, dong goi, download_chapter
import pack                       # ghep lien mach

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PY = sys.executable
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

A_TAG = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
IMG_ATTR = re.compile(
    r'(?:data-src|data-original|data-cdn|data-lazy-src|data-pagespeed-lazy-src|'
    r'data-echo|data-url|src)\s*=\s*["\']([^"\']+)["\']', re.I)
CHAP_PAT = re.compile(r"(chap|chuong|chương|chapter|episode|tap[-_/])", re.I)
JUNK = re.compile(
    r"(avatar|banner|/logo|logo\.|favicon|sprite|qrcode|loading|placeholder|"
    r"/ads?/|advert|/icon|icon\.|thumb|comment|\d+x\d+/)", re.I)
NUM = re.compile(r"(\d+(?:\.\d+)?)")
IMG_EXT = re.compile(r"\.(jpe?g|png|webp|gif|avif|bmp)", re.I)


# --------------------------------------------------------------------------- #
# HTTP tra ve ca status + headers (de chan doan)
# --------------------------------------------------------------------------- #

def fetch(url, referer=None, timeout=40):
    h = {"User-Agent": UA, "Accept-Language": "vi,en;q=0.9"}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, dict(e.headers or {}), body


def is_image_bytes(b: bytes) -> bool:
    if not b or len(b) < 100:
        return False
    if b[:3] == b"\xff\xd8\xff":                       # JPEG
        return True
    if b[:8] == b"\x89PNG\r\n\x1a\n":                  # PNG
        return True
    if b[:6] in (b"GIF87a", b"GIF89a"):               # GIF
        return True
    if b[:2] == b"BM":                                 # BMP
        return True
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":        # WEBP
        return True
    if b"ftypavif" in b[:32] or b"ftypheic" in b[:32]: # AVIF/HEIC
        return True
    return False


def detect_block(status, headers, body_text):
    """Tra ve chuoi ly do bi chan, hoac None neu khong."""
    server = (headers.get("Server") or headers.get("server") or "").lower()
    low = body_text[:3000].lower()
    if status == 429 or "error 1015" in low or "rate limited" in low:
        return "rate-limit (bi gioi han toc do / ban IP tam thoi)"
    if "just a moment" in low or "cf-browser-verification" in low \
            or "attention required" in low or "challenge-platform" in low:
        return "Cloudflare challenge (can trinh duyet that de vuot)"
    if status in (403, 503) and "cloudflare" in server:
        return f"Cloudflare chan (HTTP {status})"
    if status >= 400:
        return f"may chu tra loi HTTP {status}"
    return None


# --------------------------------------------------------------------------- #
# Trich xuat tong quat
# --------------------------------------------------------------------------- #

def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def num_of(s):
    m = NUM.search(s or "")
    return float(m.group(1)) if m else None


CHAP_NUM = re.compile(
    r"(?:chap|chuong|chương|chapter|episode|tap)[-_/]?(\d+(?:\.\d+)?)", re.I)


def chapter_num(href, text):
    """Lay so chuong: uu tien so ngay sau 'chap/chuong/chapter' trong URL,
    roi den so trong text. Tranh vo phai ID truyen nam trong URL."""
    m = CHAP_NUM.search(href or "")
    if m:
        return float(m.group(1))
    m = NUM.search(text or "")
    if m:
        return float(m.group(1))
    return None


def extract_chapter_links(html, base_url):
    host = urlparse(base_url).netloc
    seen, items = set(), []
    for href, text in A_TAG.findall(html):
        full = urljoin(base_url, unescape(href.strip()))
        if full.split("#")[0] in seen:
            continue
        if urlparse(full).netloc != host:
            continue
        t = strip_tags(text)
        if not (CHAP_PAT.search(href) or CHAP_PAT.search(t)):
            continue
        seen.add(full.split("#")[0])
        n = chapter_num(full, t)
        items.append({"url": full, "text": t, "num": n})
    items.sort(key=lambda it: (it["num"] if it["num"] is not None else 1e9, it["url"]))
    return items


def extract_images(html, base_url):
    """Tra ve danh sach URL anh noi dung (theo thu tu xuat hien)."""
    cands = []
    for tag in IMG_TAG.findall(html):
        m = IMG_ATTR.search(tag)
        if not m:
            continue
        u = unescape(m.group(1).strip()).replace("&amp;", "&")
        if u.startswith("data:"):
            continue
        u = urljoin(base_url, u)
        if JUNK.search(u):
            continue
        cands.append(u)
    if not cands:
        return []
    # Chon "host noi dung": host co nhieu anh nhat (thuong la CDN chua truyen)
    hosts = Counter(urlparse(u).netloc for u in cands)
    top_host, top_n = hosts.most_common(1)[0]
    if top_n >= 3:
        keep_hosts = {h for h, n in hosts.items() if n >= max(3, top_n * 0.5)}
    else:
        keep_hosts = set(hosts)            # it anh -> giu het, de probe quyet dinh
    out, seen = [], set()
    for u in cands:
        if urlparse(u).netloc in keep_hosts and u not in seen:
            seen.add(u)
            out.append(u)
    return out


# --------------------------------------------------------------------------- #
# Chan doan
# --------------------------------------------------------------------------- #

class Diag:
    def __init__(self):
        self.ok = False
        self.can_browser = True      # co the thu lai bang trinh duyet khong
        self.reason = ""
        self.suggest = ""
        self.kind = ""        # series | chapter
        self.title = ""
        self.chapters = []    # [{url,text,num}]
        self.first_imgs = []  # anh cua chuong dau (de tai luon)
        self.test = ""


def analyze(url):
    d = Diag()
    status, headers, body = fetch(url, referer=tq.origin(url))
    html = body.decode("utf-8", "replace")

    blk = detect_block(status, headers, html)
    if blk:
        d.reason = blk
        # 404/410 = trang khong ton tai -> trinh duyet cung vo ich
        d.can_browser = not ("HTTP 404" in blk or "HTTP 410" in blk)
        if "Cloudflare" in blk or "rate-limit" in blk:
            d.suggest = ("Trang chan bot. Dung: mangafire_dl.py voi Chrome go loi "
                         "(tu vuot Cloudflare), hoac doi IP/cho het ban.")
        return d

    d.title = tq.parse_title(html, fallback=url.rstrip("/").split("/")[-1])
    imgs_here = extract_images(html, url)
    chapters = extract_chapter_links(html, url)

    # Phan loai: nhieu anh noi dung -> day la TRANG CHUONG
    if len(imgs_here) >= 8:
        d.kind = "chapter"
        test_url, test_imgs = url, imgs_here
    elif chapters:
        d.kind = "series"
        d.chapters = chapters
        # probe = chuong dau tien
        test_url = chapters[0]["url"]
        s2, h2, b2 = fetch(test_url, referer=tq.origin(test_url))
        blk2 = detect_block(s2, h2, b2.decode("utf-8", "replace"))
        if blk2:
            d.reason = f"Vao chuong dau bi chan: {blk2}"
            d.suggest = "Co the trang chan khi tai nhieu. Thu mangafire_dl.py."
            return d
        test_imgs = extract_images(b2.decode("utf-8", "replace"), test_url)
    elif imgs_here:
        d.kind = "chapter"
        test_url, test_imgs = url, imgs_here
    else:
        d.reason = ("Khong tim thay ANH noi dung lan DANH SACH CHUONG trong HTML "
                    "(rat co the trang nap anh bang JavaScript).")
        d.suggest = ("Thu manga_dl.py (Playwright) hoac mangafire_dl.py "
                     "(Chrome go loi) cho trang dung JavaScript.")
        return d

    if not test_imgs:
        d.reason = "Tim thay trang nhung khong loc ra duoc anh noi dung."
        d.suggest = "Trang co the nap anh bang JavaScript -> dung tool trinh duyet."
        return d

    # TAI THU 1 anh that
    test = test_imgs[0]
    ts, th, tb = fetch(test, referer=tq.origin(test_url))
    if ts != 200:
        # thu lai khong referer de biet co phai chan hotlink
        ts2, _, tb2 = fetch(test)
        if ts2 == 200 and is_image_bytes(tb2):
            d.ok = True  # tai duoc khi khong referer
        else:
            d.reason = f"Tai thu anh that bai (HTTP {ts})."
            d.suggest = "Anh co the can header dac biet hoac bi chan hotlink."
            return d
    elif not is_image_bytes(tb):
        d.reason = "Tai duoc nhung KHONG phai anh hop le (co the bi ma hoa/scramble)."
        d.suggest = "Anh bi xao tron -> can buoc ghep canh (chua ho tro tu dong)."
        return d

    d.ok = True
    d.first_imgs = test_imgs
    d.test = f"{len(tb)} bytes, OK"
    if d.kind == "chapter":
        d.chapters = [{"url": url, "text": d.title, "num": chapter_num(url, "")}]
    return d


def print_diag(d):
    print("\n================ CHAN DOAN ================")
    if d.ok:
        print(f"  Ket qua  : TAI DUOC ✔")
        print(f"  Loai     : {d.kind}")
        print(f"  Tieu de  : {d.title}")
        if d.kind == 'series':
            print(f"  So chuong: {len(d.chapters)}")
        print(f"  Anh/chuong dau: {len(d.first_imgs)} | tai thu: {d.test}")
    else:
        print(f"  Ket qua  : KHONG TAI DUOC (X)")
        print(f"  Ly do    : {d.reason}")
        if d.suggest:
            print(f"  Goi y    : {d.suggest}")
    print("===========================================\n")


# --------------------------------------------------------------------------- #
# Tai
# --------------------------------------------------------------------------- #

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
            print(f"      -> ghep lien: {len(made)} file ({made[0].name}...)")
    if "folder" not in formats:
        for f in files:
            f.unlink(missing_ok=True)
        try:
            ch_dir.rmdir()
        except OSError:
            pass


def download_chapter_url(url, ch_dir, formats):
    cbz = ch_dir.parent / (ch_dir.name + ".cbz")
    if cbz.exists():
        print("      (da co, bo qua)")
        return
    s, h, b = fetch(url, referer=tq.origin(url))
    imgs = extract_images(b.decode("utf-8", "replace"), url)
    if not imgs:
        print("      (khong tim thay anh)")
        return
    print(f"      {len(imgs)} trang")
    files = tq.download_chapter(imgs, ch_dir, referer=tq.origin(url))
    if files:
        package(files, ch_dir, formats)


def debug_chrome_up(port=9222):
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=3):
            return True
    except Exception:
        return False


def browser_fallback(url, args, reason):
    """Du phong: chuyen sang cong cu trinh duyet khi HTTP tinh that bai."""
    cf = ("Cloudflare" in reason) or ("rate-limit" in reason)

    # Trang chan Cloudflare + da co Chrome go loi (user da vuot CF) -> CDP
    if cf and debug_chrome_up():
        print(">> Du phong: phat hien Chrome go loi -> dung CDP (mangafire_dl.py)")
        cmd = [PY, str(HERE / "mangafire_dl.py"), "--url", url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(int(args.range[0])), str(int(args.range[1]))]
        return subprocess.call(cmd, cwd=str(HERE))

    # Con lai: Playwright (tu mo trinh duyet, render JavaScript)
    note = " [hien cua so de ban vuot Cloudflare]" if cf else ""
    print(f">> Du phong: chuyen sang trinh duyet Playwright (manga_dl.py){note}")
    cmd = [PY, str(HERE / "manga_dl.py"), url, "--out", args.out,
           "--format", *args.format, "--mode", "auto"]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if cf:
        cmd.append("--headful")          # CF de vuot hon khi co cua so that
    return subprocess.call(cmd, cwd=str(HERE))


def detect_zinmanga(url):
    """Site SPA ho zinmanga/kunmanga: co API /api/comics/<slug>/chapters."""
    m = re.search(r"/manga/([^/]+)", url)
    if not m:
        return False
    o = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    api = f"{o}/api/comics/{m.group(1)}/chapters?per_page=1"
    try:
        st, _, body = fetch(api, referer=o + "/")
        return st == 200 and b'"chapters"' in body
    except Exception:
        return False


def zinmanga_info(url):
    """Lay so chuong that qua API. Tra ve dict {count,min,max} hoac None."""
    m = re.search(r"/manga/([^/]+)", url)
    if not m:
        return None
    o = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    api = f"{o}/api/comics/{m.group(1)}/chapters?per_page=-1&order=asc"
    try:
        st, _, body = fetch(api, referer=o + "/")
        if st != 200:
            return None
        chs = json.loads(body.decode("utf-8", "replace"))["data"]["chapters"]
        nums = [c.get("chapter_num") for c in chs if c.get("chapter_num") is not None]
        return {"count": len(chs),
                "min": min(nums) if nums else None,
                "max": max(nums) if nums else None}
    except Exception:
        return None


def run(args):
    url = args.url
    host = urlparse(url).netloc.lower()

    # 1) MangaDex -> tool chuyen dung
    if "mangadex" in host:
        print("Phat hien MangaDex -> chuyen sang mangadex_dl.py")
        return subprocess.call(
            [PY, str(HERE / "mangadex_dl.py"), url, "--out", args.out,
             "--format", *args.format])

    # 1b) Site kieu zinmanga/kunmanga (chuong + anh qua API) -> adapter rieng
    if detect_zinmanga(url):
        print("Phat hien site kieu zinmanga/kunmanga -> dung kunmanga_dl.py")
        cmd = [PY, str(HERE / "kunmanga_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b2) mangafire.to (chan CF + chong bot) -> Chrome that + CDP, hung API da ky vrf
    if "mangafire.to" in host:
        print("Phat hien mangafire.to -> dung mangafire_dl.py (Chrome that + CDP)")
        cmd = [PY, str(HERE / "mangafire_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b3) webtoons.com (nguon chinh thong; ten mien chinh bi RST) -> Chrome that + CDN
    if "webtoons.com" in host:
        print("Phat hien webtoons.com -> dung webtoon_dl.py (Chrome that vuot RST)")
        cmd = [PY, str(HERE / "webtoon_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(int(args.range[0])), str(int(args.range[1]))]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b4) zettruyen.club (ho zinmanga, URL kieu VN) -> HTTP + API
    if "zettruyen" in host:
        print("Phat hien zettruyen.club -> dung zettruyen_dl.py (HTTP + API zinmanga)")
        cmd = [PY, str(HERE / "zettruyen_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b5) ho TruyenQQ / NetTruyen (VN, HTTP thuan) -> tool chuyen
    if "truyenqq" in host or "nettruyen" in host:
        print("Phat hien TruyenQQ/NetTruyen -> dung truyenqq_dl.py (HTTP thuan)")
        cmd = [PY, str(HERE / "truyenqq_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b6) dilib.vn (Angular SPA, anh nhung san; server bat buoc gzip) -> tool chuyen
    if "dilib.vn" in host:
        print("Phat hien dilib.vn -> dung dilib_dl.py (HTTP gzip)")
        cmd = [PY, str(HERE / "dilib_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b7) manhwahub.net (HTML tinh, anh CDN nhung san) -> tool chuyen
    if "manhwahub.net" in host:
        print("Phat hien manhwahub.net -> dung manhwahub_dl.py (HTTP tinh)")
        cmd = [PY, str(HERE / "manhwahub_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b8) manga18.me (HTML tinh, anh CDN nhung san) -> tool chuyen
    if "manga18.me" in host:
        print("Phat hien manga18.me -> dung manga18_dl.py (HTTP tinh)")
        cmd = [PY, str(HERE / "manga18_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b9) toongod.org (Madara sau Cloudflare) -> Chrome vuot CF 1 lan + HTTP cookie
    if "toongod.org" in host:
        print("Phat hien toongod.org -> dung toongod_dl.py (Chrome vuot CF + HTTP)")
        cmd = [PY, str(HERE / "toongod_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b10) manhwaread.com (CF + anh chapterData base64) -> Chrome vuot CF + HTTP
    if "manhwaread.com" in host:
        print("Phat hien manhwaread.com -> dung manhwaread_dl.py (Chrome vuot CF + HTTP)")
        cmd = [PY, str(HERE / "manhwaread_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b11) asurascans.com (HTML tinh, anh CDN nhung san, du phong CF) -> tool chuyen
    if "asurascans.com" in host or "asuracomic" in host:
        print("Phat hien Asura Scans -> dung asurascans_dl.py (HTTP tinh)")
        cmd = [PY, str(HERE / "asurascans_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b12) lagoonscans.com (Madara ts_reader, anh trong JS) -> tool chuyen
    if "lagoonscans.com" in host:
        print("Phat hien lagoonscans.com -> dung lagoonscans_dl.py (Madara ts_reader)")
        cmd = [PY, str(HERE / "lagoonscans_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1b13) kaynscan.org (SPA nhung anh /page-NNNN nhung san HTML) -> tool chuyen
    if "kaynscan.org" in host:
        print("Phat hien kaynscan.org -> dung kaynscan_dl.py (HTTP tinh)")
        cmd = [PY, str(HERE / "kaynscan_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 1c) comix.to (SPA chong cao manh) -> adapter dieu khien trinh duyet
    if "comix.to" in host:
        print("Phat hien comix.to -> dung comix_dl.py (dieu khien trinh duyet)")
        cmd = [PY, str(HERE / "comix_dl.py"), url,
               "--out", args.out, "--format", *args.format]
        if args.range:
            cmd += ["--range", str(args.range[0]), str(args.range[1])]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        return subprocess.call(cmd, cwd=str(HERE))

    # 2) Phan tich + chan doan
    print("Dang phan tich trang...")
    d = analyze(url)
    print_diag(d)
    if not d.ok:
        if args.browser != "off" and d.can_browser:
            sys.exit(browser_fallback(url, args, d.reason))
        print(">> DUNG: khong the tai tu trang nay"
              + (" (da tat du phong trinh duyet)." if args.browser == "off" else "."))
        sys.exit(2)

    # 3) Tai
    chapters = d.chapters
    if args.range:
        a, b = args.range
        chapters = [c for c in chapters
                    if c["num"] is not None and a <= c["num"] <= b]
    if args.limit:
        chapters = chapters[: args.limit]

    out_dir = Path(args.out) / tq.slugify(d.title)
    done = tq.progress_load(out_dir)
    print(f"Tai {len(chapters)} chuong vao: {out_dir.resolve()}")
    if done:
        print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
    print()
    for i, c in enumerate(chapters, 1):
        n = c["num"]
        label = f"Chuong {n:g}" if n is not None else f"chuong {i}"
        ch_dir = out_dir / tq.slugify(f"{i:04d} - {label}")
        cbz = ch_dir.parent / (ch_dir.name + ".cbz")
        if (ch_dir.name in done or cbz.exists()):
            print(f"[{i}/{len(chapters)}] (da co) {label}")
            done.add(ch_dir.name)
            continue
        print(f"[{i}/{len(chapters)}] {label}")
        try:
            download_chapter_url(c["url"], ch_dir, args.format)
            done.add(ch_dir.name)
            tq.progress_save(out_dir, done)
        except Exception as e:
            print(f"      LOI: {e}")
        time.sleep(args.delay)
    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(
        description="Tai truyen tu dong (tu phan tich & chan doan).")
    p.add_argument("url", help="Link bat ky (bo truyen hoac 1 chuong)")
    p.add_argument("--range", nargs=2, type=float, metavar=("A", "B"),
                   help="Chi tai chuong trong khoang so [A..B]")
    p.add_argument("--limit", type=int, default=0, help="Chi tai N chuong (0=tat ca)")
    p.add_argument("--format", nargs="+", default=["folder", "cbz"],
                   choices=["folder", "cbz", "pdf", "stitch"])
    p.add_argument("--out", default="downloads", help="Thu muc luu")
    p.add_argument("--delay", type=float, default=1.0, help="Nghi giua cac chuong (giay)")
    p.add_argument("--browser", choices=["auto", "off"], default="auto",
                   help="auto = tu chuyen sang trinh duyet khi HTTP tinh that bai")
    p.add_argument("--check", action="store_true",
                   help="Chi chan doan (khong tai, khong du phong)")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        if args.check:
            host = urlparse(args.url).netloc.lower()
            if "mangadex" in host:
                print("MangaDex -> dung mangadex_dl.py (TAI DUOC)")
                sys.exit(0)
            elif "comix.to" in host:
                # Giao cho comix_dl tu chan doan (so chuong that + co bi xao khong)
                print("Phan tich comix.to (mo trinh duyet, doi chut)...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "comix_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "mangafire.to" in host:
                # Giao cho mangafire_dl tu chan doan (Chrome that + CDP)
                print("Phan tich mangafire.to (mo Chrome that, doi chut)...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "mangafire_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "webtoons.com" in host:
                # Giao cho webtoon_dl tu chan doan (Chrome that vuot RST)
                print("Phan tich webtoons.com (mo Chrome that, doi chut)...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "webtoon_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "zettruyen" in host:
                print("Phan tich zettruyen.club...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "zettruyen_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "truyenqq" in host or "nettruyen" in host:
                print("Phan tich TruyenQQ/NetTruyen...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "truyenqq_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "dilib.vn" in host:
                print("Phan tich dilib.vn...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "dilib_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "manhwahub.net" in host:
                print("Phan tich manhwahub.net...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "manhwahub_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "manga18.me" in host:
                print("Phan tich manga18.me...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "manga18_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "toongod.org" in host:
                print("Phan tich toongod.org (mo Chrome vuot CF, doi chut)...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "toongod_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "manhwaread.com" in host:
                print("Phan tich manhwaread.com (mo Chrome vuot CF, doi chut)...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "manhwaread_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "asurascans.com" in host or "asuracomic" in host:
                print("Phan tich Asura Scans...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "asurascans_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "lagoonscans.com" in host:
                print("Phan tich lagoonscans.com...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "lagoonscans_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif "kaynscan.org" in host:
                print("Phan tich kaynscan.org...")
                sys.exit(subprocess.call(
                    [PY, str(HERE / "kaynscan_dl.py"), args.url, "--check"], cwd=str(HERE)))
            elif detect_zinmanga(args.url):
                info = zinmanga_info(args.url)
                print("\n================ CHAN DOAN ================")
                print("  Ket qua  : TAI DUOC (qua API zinmanga/kunmanga) ✔")
                if info:
                    rng = (f" (chuong {info['min']:g}..{info['max']:g})"
                           if info["min"] is not None else "")
                    print(f"  So chuong: {info['count']}{rng}")
                print("  Cach     : adapter kunmanga_dl.py - lay du chuong qua API")
                print("===========================================")
                sys.exit(0)
            else:
                d = analyze(args.url)
                print_diag(d)
                sys.exit(0 if d.ok else 2)
        else:
            run(args)
    except KeyboardInterrupt:
        print("\nDa dung.")
