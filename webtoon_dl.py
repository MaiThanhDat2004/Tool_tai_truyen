# -*- coding: utf-8 -*-
"""
webtoon_dl - Tai truyen tu webtoons.com (LINE/Naver Webtoon) - NGUON CHINH THONG, MIEN PHI.

BAI TOAN (xem THUAT_TOAN.md):
  - Ten mien chinh `www.webtoons.com` bi **RST** (nha mang VN chan SNI / WAF chan
    fingerprint non-browser) -> curl/urllib chet ("Connection reset"). Chap chon
    (luc duoc luc khong) -> CAN RETRY.
  - NHUNG **Chrome that** (van tay browser) vao binh thuong.
  - CDN anh `webtoon-phinf.pstatic.net` KHONG bi chan -> tai thang bang urllib + Referer.

CACH LACH:
  1. Tu mo chrome.exe debug 9222 (ensure_chrome) -> vuot chan ten mien chinh.
  2. CDP + Runtime.evaluate: doc danh sach chuong (phan trang &page=N) + URL anh
     tu DOM (`#_imageList img[data-url]`). webtoons KHONG chong automation kieu
     mangafire nen dung Runtime thoai mai.
  3. Tai anh bang urllib + `Referer: https://www.webtoons.com/` (CDN khong chan, NHANH).
     Anh KHONG xao tron. Truyen cuon doc -> hop format `stitch`.

DUNG:
  python webtoon_dl.py "https://www.webtoons.com/en/drama/ctrl-alt-resign/list?title_no=8384" --check
  python webtoon_dl.py "<link list>" --limit 3 --out D:/tai_truyen --format folder stitch
  python webtoon_dl.py "<link list>" --range 1 10
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("Thieu thu vien: pip install websocket-client")

import truyenqq_dl as tq      # slugify, http, make_cbz, make_pdf
import pack
from mangafire_dl import ensure_chrome   # tu mo chrome.exe debug 9222

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
PORT = 9222
REFERER = "https://www.webtoons.com/"


# --------------------------------------------------------------------------- #
# CDP (co Runtime.evaluate) + nav retry
# --------------------------------------------------------------------------- #

class CDP:
    def __init__(self, port=PORT):
        self.port = port
        self._id = 0

    def _hj(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=8) as r:
            return json.load(r)

    def open_tab(self):
        ver = self._hj("/json/version")
        bws = websocket.create_connection(ver["webSocketDebuggerUrl"],
                                          max_size=None, suppress_origin=True)
        bws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                             "params": {"url": "about:blank"}}))
        while True:
            m = json.loads(bws.recv())
            if m.get("id") == 1:
                self.target_id = m["result"]["targetId"]
                break
        bws.close()
        self.ws = websocket.create_connection(
            f"ws://127.0.0.1:{self.port}/devtools/page/{self.target_id}",
            max_size=None, suppress_origin=True)
        self.ws.settimeout(3)
        self.send("Page.enable")
        self.send("Runtime.enable")
        return self

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/close/{self.target_id}", timeout=5)
        except Exception:
            pass

    def send(self, method, params=None):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        return self._id

    def evaluate(self, expr, timeout=10):
        gid = self.send("Runtime.evaluate",
                        {"expression": expr, "returnByValue": True, "awaitPromise": True})
        end = time.time() + timeout
        while time.time() < end:
            try:
                r = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                continue
            if r.get("id") == gid:
                return r.get("result", {}).get("result", {}).get("value")
        return None

    def navigate(self, url, settle=2.0, retries=3):
        """Navigate + cho load; retry vi ten mien chinh hay bi RST chap chon."""
        for attempt in range(retries):
            self.send("Page.navigate", {"url": url})
            end = time.time() + 25
            ok = False
            while time.time() < end:
                try:
                    msg = json.loads(self.ws.recv())
                except websocket.WebSocketTimeoutException:
                    break
                except Exception:
                    continue
                if msg.get("method") == "Page.loadEventFired":
                    ok = True
                    break
            time.sleep(settle)
            # kiem tra co noi dung khong
            t = self.evaluate("document.title", timeout=5) or ""
            if ok and t and "webtoon" in t.lower() or (ok and self.evaluate(
                    "document.querySelectorAll('#_listUl li a,#_imageList img').length", 5)):
                return True
            time.sleep(1.5 * (attempt + 1))   # mang chap chon -> doi roi thu lai
        return False


# --------------------------------------------------------------------------- #
# Danh sach chuong + anh
# --------------------------------------------------------------------------- #

_JS_EPISODES = (
    "JSON.stringify([...document.querySelectorAll('#_listUl li a')].map(a=>({"
    "no:(a.href.match(/episode_no=(\\d+)/)||[])[1],href:a.href,"
    "subj:(a.querySelector('.subj')?a.querySelector('.subj').innerText:'')})))")

_JS_IMAGES = ("JSON.stringify([...document.querySelectorAll('#_imageList img')]"
              ".map(i=>i.getAttribute('data-url')||i.src).filter(Boolean))")


def base_list_url(url):
    m = re.search(r"(https://www\.webtoons\.com/[^?]+\?title_no=\d+)", url)
    return m.group(1) if m else url.split("&")[0]


def get_episodes(cdp, list_url):
    """Phan trang &page=N, gom het episode. Tra ve (title, [ (no, href, subj) ])."""
    base = base_list_url(list_url)
    title = ""
    seen, items = set(), []
    page = 1
    empty_streak = 0
    while page <= 80:
        if not cdp.navigate(f"{base}&page={page}"):
            empty_streak += 1
            if empty_streak >= 2:
                break
            page += 1
            continue
        if not title:
            t = cdp.evaluate("document.title") or ""
            title = re.split(r"\s*[|]\s*WEBTOON", t)[0].strip() or "webtoon"
        raw = cdp.evaluate(_JS_EPISODES)
        eps = json.loads(raw) if raw else []
        new = 0
        for e in eps:
            no = e.get("no")
            if not no or no in seen:
                continue
            seen.add(no)
            items.append((int(no), e["href"], e.get("subj", "")))
            new += 1
        if new == 0:
            empty_streak += 1
            if empty_streak >= 1:    # het chuong
                break
        else:
            empty_streak = 0
        page += 1
    items.sort(key=lambda x: x[0])
    return title, items


def get_images(cdp, viewer_url):
    if not cdp.navigate(viewer_url, settle=2.5):
        return []
    # cuon 1 chut de chac data-url da gan (webtoons gan san data-url, it can cuon)
    raw = cdp.evaluate(_JS_IMAGES)
    return json.loads(raw) if raw else []


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


def dl_image(url, retries=4):
    last = None
    for k in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep((k + 1) * 1.2)
    raise RuntimeError(str(last))


def download_episode(urls, ch_dir):
    return tq.download_images(urls, ch_dir, dl_image)


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
    ensure_chrome(base_list_url(args.url))
    cdp = CDP().open_tab()
    try:
        print("Dang lay danh sach chuong (phan trang)...")
        title, eps = get_episodes(cdp, args.url)
        if not eps:
            sys.exit("Khong lay duoc danh sach chuong (trang loi? thu lai).")
        nums = [n for n, _, _ in eps]
        rng = f" (chuong {min(nums)}..{max(nums)})"

        sel = eps
        if args.range:
            a, b = args.range
            sel = [(n, h, s) for n, h, s in sel if a <= n <= b]
        if args.limit:
            sel = sel[: args.limit]

        if args.list:
            for n, _, s in sel:
                print(f"  Ep {n}: {s}")
            return

        if args.check:
            imgs = get_images(cdp, (sel or eps)[0][1])
            print("\n================ CHAN DOAN ================")
            print(f"  Ket qua  : {'TAI DUOC (Chrome that + CDN) ✔' if imgs else 'CHUA LAY DUOC ✘'}")
            print(f"  Truyen   : {title}")
            print(f"  So chuong: {len(eps)}{rng}")
            if imgs:
                print(f"  Chuong dau: {len(imgs)} anh (webtoon cuon doc)")
                print("  Cach     : tai thang tu CDN pstatic.net (khong xao tron)")
            print("  Luu y    : ten mien chinh hay bi RST chap chon -> tool tu retry.")
            print("===========================================")
            return

        out_dir = Path(args.out) / tq.slugify(title)
        done = tq.progress_load(out_dir)          # cac chuong DA HOAN TAT (resume)
        print(f"Truyen: {title} | Tong chuong: {len(eps)}{rng}")
        print(f"Tai {len(sel)} chuong vao: {out_dir.resolve()}")
        if done:
            print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
        print()
        for i, (no, href, subj) in enumerate(sel, 1):
            label = subj.strip() or f"Ep {no}"
            ch_dir = out_dir / tq.slugify(f"{no:04d} - {label}")
            cbz = ch_dir.parent / (ch_dir.name + ".cbz")
            # CHUONG da xong (theo dau .progress.json hoac da co .cbz) -> bo qua, KHONG mo trinh duyet
            if (ch_dir.name in done or cbz.exists()) and not args.overwrite:
                print(f"[{i}/{len(sel)}] (da co) {label}")
                done.add(ch_dir.name)
                continue
            print(f"[{i}/{len(sel)}] {label}")
            try:
                urls = get_images(cdp, href)
                if not urls:
                    print("      (khong lay duoc anh - chuong khoa fast-pass? hoac trang loi)")
                    continue
                saved = download_episode(urls, ch_dir)
                if not saved:
                    try:
                        ch_dir.rmdir()
                    except OSError:
                        pass
                    continue
                package(saved, ch_dir, args.format)
                done.add(ch_dir.name)             # danh dau hoan tat
                tq.progress_save(out_dir, done)
            except Exception as e:
                print(f"      LOI: {e}")
            time.sleep(args.delay)
    finally:
        cdp.close()
    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(
        description="Tai truyen webtoons.com (Chrome that vuot RST + tai anh tu CDN).")
    p.add_argument("url", help="Link trang list (…/list?title_no=NNNN)")
    p.add_argument("--range", nargs=2, type=int, metavar=("A", "B"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--list", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--format", nargs="+", default=["folder", "cbz"],
                   choices=["folder", "cbz", "pdf", "stitch"])
    p.add_argument("--out", default="downloads")
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--overwrite", action="store_true")
    return p


if __name__ == "__main__":
    try:
        run(build_parser().parse_args())
    except KeyboardInterrupt:
        print("\nDa dung.")
