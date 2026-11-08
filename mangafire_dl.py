# -*- coding: utf-8 -*-
"""
mangafire_dl - Tai truyen tu mangafire.to (chan Cloudflare + chong bot manh).

CACH LACH (xem THUAT_TOAN.md):
  mangafire da tat ca cong cu tu dong "that" (Playwright/Selenium) bang cach:
    - Trang doc (/read/...) phat hien CDP/automation -> DA NGUOC ve trang chu.
    - API anh /ajax/read/chapter/<id> doi tham so ?vrf=<token> ky client-side.
  NHUNG: chrome.exe THAT mo binh thuong (khong co co automation cua Playwright)
  thi KHONG bi da. Ta:
    1) Tu mo chrome.exe voi --remote-debugging-port=9222 (v!an tay that -> lot).
    2) Dieu khien no qua CDP THUAN (websocket), CHI dung Page.navigate + Network.
       TUYET DOI khong Runtime.evaluate (chay JS trang -> bi phat hien -> da ve home).
    3) Khi mo 1 chuong, trinh duyet TU KY vrf va goi /ajax/read/chapter/<id>?vrf=...
       -> ta HUNG response body (Network.getResponseBody): JSON danh sach anh DUNG
       THU TU. KHONG can reverse vrf.
    4) Tai anh bang HTTP thuong + Referer (anh KHONG bi xao tron, khong can cookie).

  Danh sach chuong lay tu HTML tinh trang /manga/<slug> (curl thuong, khong vrf).

DUNG:
  python mangafire_dl.py "https://mangafire.to/manga/grapara.9jlp8" --check
  python mangafire_dl.py "https://mangafire.to/manga/grapara.9jlp8" --limit 5 --out D:/tai_truyen
  python mangafire_dl.py "https://mangafire.to/read/grapara.9jlp8/en/chapter-1" --range 1 10

  pip install websocket-client    (Pillow neu muon PDF)
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("Thieu thu vien: pip install websocket-client")

import truyenqq_dl as tq      # slugify, http, make_cbz, make_pdf, origin
import pack

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
PORT = 9222
PROFILE = r"C:\chrome-debug-profile"
SITE = "https://mangafire.to/"
IMGLIST_RE = re.compile(r"/ajax/read/chapter/\d+")     # endpoint anh (khac endpoint list)


# --------------------------------------------------------------------------- #
# Mo / tim Chrome that
# --------------------------------------------------------------------------- #

def _chrome_exe():
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(p):
            return p
    return "chrome"   # hy vong co trong PATH


def _debug_alive():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=3):
            return True
    except Exception:
        return False


def ensure_chrome(open_url=SITE):
    """Bao dam co chrome.exe THAT chay debug port 9222. Tu mo neu chua."""
    if _debug_alive():
        return
    exe = _chrome_exe()
    print(f"Dang mo Chrome that (debug 9222, profile {PROFILE})...")
    subprocess.Popen(
        [exe, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}",
         "--no-first-run", "--no-default-browser-check", open_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(1)
        if _debug_alive():
            time.sleep(2)
            return
    sys.exit("Khong mo duoc Chrome debug. Hay tu mo:\n"
             f'  "{exe}" --remote-debugging-port={PORT} --user-data-dir={PROFILE}')


# --------------------------------------------------------------------------- #
# CDP toi gian (KHONG Runtime.evaluate)
# --------------------------------------------------------------------------- #

class CDP:
    def __init__(self, port=PORT):
        self.port = port
        self._id = 0

    def _http_json(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=8) as r:
            return json.load(r)

    def open_tab(self):
        """Tao 1 tab rieng (khong dung tab user) qua Target.createTarget."""
        ver = self._http_json("/json/version")
        bws = websocket.create_connection(ver["webSocketDebuggerUrl"],
                                          max_size=None, suppress_origin=True)
        bws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                             "params": {"url": "about:blank"}}))
        tid = None
        while True:
            m = json.loads(bws.recv())
            if m.get("id") == 1:
                tid = m["result"]["targetId"]
                break
        bws.close()
        self.target_id = tid
        url = f"ws://127.0.0.1:{self.port}/devtools/page/{tid}"
        self.ws = websocket.create_connection(url, max_size=None, suppress_origin=True)
        self.ws.settimeout(2)
        self.send("Page.enable")
        self.send("Network.enable")
        return self

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        # dong tab
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/close/{self.target_id}", timeout=5)
        except Exception:
            pass

    def send(self, method, params=None):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        return self._id

    def capture_imagelist(self, read_url, wait=14):
        """Navigate toi 1 chuong, hung body cua /ajax/read/chapter/<id>?vrf.
        Tra ve (images_list, final_url). images_list = [[url, a, b], ...] dung thu tu."""
        self.send("Page.navigate", {"url": read_url})
        rid = None
        end = time.time() + wait
        while time.time() < end:
            try:
                msg = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                if rid:
                    break
                continue
            except Exception:
                continue
            if msg.get("method") == "Network.responseReceived":
                u = msg["params"]["response"]["url"]
                if IMGLIST_RE.search(u):
                    rid = msg["params"]["requestId"]
                    # cho loadingFinished de chac body co san
            elif msg.get("method") == "Network.loadingFinished" and rid:
                if msg["params"].get("requestId") == rid:
                    break
        if not rid:
            return None, self._tab_url()
        body = self._get_body(rid)
        if not body:
            return None, self._tab_url()
        try:
            data = json.loads(body)
            return data["result"]["images"], self._tab_url()
        except Exception:
            return None, self._tab_url()

    def _get_body(self, rid):
        gid = self.send("Network.getResponseBody", {"requestId": rid})
        end = time.time() + 6
        while time.time() < end:
            try:
                r = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                continue
            if r.get("id") == gid:
                res = r.get("result", {})
                if "body" not in res:
                    return None
                if res.get("base64Encoded"):
                    return base64.b64decode(res["body"]).decode("utf-8", "replace")
                return res["body"]
        return None

    def _tab_url(self):
        try:
            for t in self._http_json("/json"):
                if t.get("id") == self.target_id:
                    return t.get("url", "?")
        except Exception:
            pass
        return "?"


# --------------------------------------------------------------------------- #
# Phan tich trang manga (HTML tinh, khong can vrf)
# --------------------------------------------------------------------------- #

def parse_slug_lang(url):
    m = re.search(r"mangafire\.to/(?:manga|read)/([^/]+)(?:/([a-z]{2}))?", url)
    slug = m.group(1) if m else url.rstrip("/").split("/")[-1]
    lang = (m.group(2) if m and m.group(2) else "en")
    return slug, lang


def get_manga_info(slug, lang):
    """Tra ve (title, [(num_str, read_url)]) tu HTML tinh trang /manga/<slug>."""
    murl = f"https://mangafire.to/manga/{slug}"
    html = tq.http(murl, referer=SITE)
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    title = (m.group(1) if m else slug)
    title = re.split(r"\s+Manga\b", title)[0].strip() or slug
    # cac link doc dung ngon ngu
    rx = re.compile(r'href="(/read/' + re.escape(slug) + r'/' + lang + r'/chapter-([\d.]+))"', re.I)
    seen, items = set(), []
    for href, num in rx.findall(html):
        if num in seen:
            continue
        seen.add(num)
        items.append((num, "https://mangafire.to" + href))
    items.sort(key=lambda kv: float(kv[0]))
    return title, items


# --------------------------------------------------------------------------- #
# Tai
# --------------------------------------------------------------------------- #

def _ext(data):
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".jpg"


def download_chapter(images, ch_dir):
    urls = [it[0] if isinstance(it, list) else it for it in images]
    return tq.download_images(urls, ch_dir,
                              lambda u: tq.http(u, referer=SITE, binary=True), min_size=800)


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


# Luu y: moi anh trong "images" la [url, a, b]. Cac so a/b la metadata cua reader
# (cap/zoom), KHONG phai co xao tron - da kiem chung 3 bo (GraPara (1,0), Dandadan,
# Witch Hat (khac) deu tai thang ra anh SACH). Vi vay khong dung chung de doan xao.


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def run(args):
    slug, lang = parse_slug_lang(args.url)
    print(f"mangafire | slug={slug} lang={lang}")
    title, chapters = get_manga_info(slug, lang)
    if not chapters:
        sys.exit("Khong lay duoc danh sach chuong tu HTML tinh.")
    nums = [float(n) for n, _ in chapters]
    rng = f" (chuong {min(nums):g}..{max(nums):g})" if nums else ""

    sel = chapters
    if args.range:
        a, b = args.range
        sel = [(n, u) for n, u in sel if a <= float(n) <= b]
    if args.limit:
        sel = sel[: args.limit]

    if args.list:
        for n, _ in sel:
            print(f"  Ch {n}")
        return

    # --- CHAN DOAN ---
    if args.check:
        ensure_chrome(f"https://mangafire.to/manga/{slug}")
        cdp = CDP().open_tab()
        try:
            imgs, furl = cdp.capture_imagelist((sel or chapters)[0][1])
            ok = bool(imgs)
            npages = len(imgs) if imgs else 0
        finally:
            cdp.close()
        print("\n================ CHAN DOAN ================")
        print(f"  Ket qua  : {'TAI DUOC (Chrome that + CDP) ✔' if ok else 'CHUA LAY DUOC ✘'}")
        print(f"  Truyen   : {title}")
        print(f"  So chuong: {len(chapters)}{rng}")
        if ok:
            print(f"  Chuong dau: {npages} trang")
            print("  Cach     : tai thang anh tu CDN (khong xao tron)")
        else:
            print("  Luu y: mo trang doc bi chan? Thu chay lai (Chrome can vuot Cloudflare 1 lan).")
        print("===========================================")
        return

    ensure_chrome(f"https://mangafire.to/manga/{slug}")
    out_dir = Path(args.out) / tq.slugify(title)
    done = tq.progress_load(out_dir)              # chuong DA HOAN TAT (resume)
    print(f"Truyen: {title} | Tong chuong: {len(chapters)}{rng}")
    print(f"Tai {len(sel)} chuong vao: {out_dir.resolve()}")
    if done:
        print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
    print()

    cdp = CDP().open_tab()
    try:
        for i, (num, read_url) in enumerate(sel, 1):
            label = f"Chuong {num}"
            ch_dir = out_dir / tq.slugify(f"{i:04d} - {label}")
            cbz = ch_dir.parent / (ch_dir.name + ".cbz")
            # CHUONG da xong (dau .progress.json hoac da co .cbz) -> bo qua, KHONG mo trinh duyet
            if (ch_dir.name in done or cbz.exists()) and not args.overwrite:
                print(f"[{i}/{len(sel)}] (da co) {label}")
                done.add(ch_dir.name)
                continue
            print(f"[{i}/{len(sel)}] {label}")
            try:
                imgs, furl = cdp.capture_imagelist(read_url)
                if not imgs:
                    print(f"      (khong lay duoc danh sach anh; tab={furl[:50]})")
                    continue
                saved = download_chapter(imgs, ch_dir)
                if not saved:
                    try:
                        ch_dir.rmdir()
                    except OSError:
                        pass
                    continue
                package(saved, ch_dir, args.format)
                done.add(ch_dir.name)            # danh dau hoan tat
                tq.progress_save(out_dir, done)
            except Exception as e:
                print(f"      LOI: {e}")
            time.sleep(args.delay)
    finally:
        cdp.close()
    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(
        description="Tai truyen mangafire.to (Chrome that + CDP, hung API da ky vrf).")
    p.add_argument("url", help="Link bo (/manga/<slug>) hoac 1 chuong (/read/...)")
    p.add_argument("--range", nargs=2, type=float, metavar=("A", "B"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--list", action="store_true")
    p.add_argument("--check", action="store_true",
                   help="Chi chan doan: so chuong + co bi xao tron khong")
    p.add_argument("--format", nargs="+", default=["folder", "cbz"],
                   choices=["folder", "cbz", "pdf", "stitch"])
    p.add_argument("--out", default="downloads")
    p.add_argument("--delay", type=float, default=1.0,
                   help="Nghi giua cac chuong (giay) - tranh rate-limit")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--port", type=int, default=PORT)
    return p


if __name__ == "__main__":
    try:
        run(build_parser().parse_args())
    except KeyboardInterrupt:
        print("\nDa dung.")
