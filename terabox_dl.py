# -*- coding: utf-8 -*-
"""
terabox_dl - Tai 1 file tu link share Terabox / 1024tera.com.

BAI TOAN (xem THUAT_TOAN.md):
  - Bam tai AN DANH -> trang nap Google reCAPTCHA + tuong dang nhap, KHONG co
    request tai that. File lon (>~50MB) bat buoc DANG NHAP. Link tai that (`dlink`)
    duoc ky bang `sign` (RC4 client-side) -> KHONG giai ma.
  - CACH LACH: mo chrome.exe THAT (debug 9222), nguoi dung dang nhap 1 lan trong
    cua so do -> tool hung cookie `ndus` + UA, de chinh JS cua trang ky `sign`,
    HUNG `dlink` qua CDP (Network.getResponseBody cua /share/download hoac CDN url),
    roi tai thang HTTP (cookie + UA) -> ne cai app, do bi bop toc do.

DUNG:
  # 1) mo trang + cho dang nhap (giu cua so), in danh sach file
  python terabox_dl.py "<link share>" --check
  # 2) sau khi da dang nhap trong cua so Chrome:
  python terabox_dl.py "<link share>" --out D:/tai_truyen
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

import truyenqq_dl as tq
from mangafire_dl import ensure_chrome, PORT

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("Thieu 'websocket-client': pip install websocket-client")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HOST = "https://www.1024tera.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def parse_surl(url):
    m = re.search(r"surl=([0-9A-Za-z_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/s/1?([0-9A-Za-z_-]+)", url)
    if m:
        return m.group(1)
    sys.exit("Khong nhan ra surl trong link Terabox.")


# --------------------------------------------------------------------------- #
# HTTP thuan (kem cookie) cho share/list + tai file
# --------------------------------------------------------------------------- #

def _http(url, referer=HOST + "/", cookie="", binary=False, rng=None):
    headers = {"User-Agent": UA, "Referer": referer,
               "Accept": "application/json, text/plain, */*"}
    if cookie:
        headers["Cookie"] = cookie
    if rng:
        headers["Range"] = f"bytes={rng}-"
    req = urllib.request.Request(url, headers=headers)
    r = urllib.request.urlopen(req, timeout=60)
    data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def _jstoken(html):
    m = (re.search(r'fn%28%22([0-9A-Fa-f]{20,})%22%29', html)
         or re.search(r'"jsToken"\s*:\s*"([0-9A-Fa-f]{20,})"', html)
         or re.search(r'([0-9A-Fa-f]{120,})', html))
    return m.group(1) if m else ""


def share_list(surl, cookie=""):
    """Tra ve (jstoken, page_url, [file,...]). Moi file: dict server_filename/size/fs_id."""
    page_url = f"{HOST}/sharing/link?surl={surl}"
    html = _http(page_url, cookie=cookie)
    jt = _jstoken(html)
    if not jt:
        sys.exit("Khong lay duoc jsToken (trang doi cau truc?).")
    q = urllib.parse.urlencode({
        "app_id": "250528", "web": "1", "channel": "dubox", "clienttype": "0",
        "jsToken": jt, "page": "1", "num": "200", "by": "name", "order": "asc",
        "site_referer": page_url, "shorturl": surl, "root": "1"})
    j = json.loads(_http(f"{HOST}/share/list?{q}", referer=page_url, cookie=cookie))
    if j.get("errno") != 0:
        sys.exit(f"share/list errno={j.get('errno')} (link het han / sai surl?).")
    return jt, page_url, j.get("list", [])


# --------------------------------------------------------------------------- #
# CDP: noi vao tab Chrome dang mo trang share
# --------------------------------------------------------------------------- #

class Tab:
    def __init__(self):
        self.ws = None
        self._id = 0

    def attach(self):
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=8))
        t = next((x for x in tabs if x.get("type") == "page"
                  and "1024tera" in (x.get("url") or "")), None)
        if not t:
            sys.exit("Khong thay tab Terabox trong Chrome. Chay --check truoc de mo trang.")
        self.ws = websocket.create_connection(t["webSocketDebuggerUrl"],
                                               max_size=None, suppress_origin=True)
        self.ws.settimeout(2)
        self.send("Network.enable")
        self.send("Runtime.enable")
        return self

    def send(self, method, params=None):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        return self._id

    def wait_id(self, i, to=8):
        end = time.time() + to
        while time.time() < end:
            try:
                r = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                continue
            if r.get("id") == i:
                return r
        return None

    def evaluate(self, expr, to=8):
        i = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        r = self.wait_id(i, to)
        if r:
            return r.get("result", {}).get("result", {}).get("value")
        return None

    def cookies(self):
        i = self.send("Network.getCookies", {"urls": [HOST]})
        r = self.wait_id(i)
        cks = r["result"]["cookies"] if r else []
        return {c["name"]: c["value"] for c in cks}

    def is_logged_in(self):
        cks = self.cookies()
        return "ndus" in cks, cks

    def harvest_dlink(self, wait=20):
        """Bam tai -> hung dlink tu /share/download (hoac CDN url)."""
        # click nut tai (qua JS, ne overlay)
        self.evaluate(
            "(function(){var b=Array.from(document.querySelectorAll('a,button,div,span'))"
            ".find(e=>/download/i.test(e.className||'')||/^\\s*(download|t\\u1ea3i)/i"
            ".test((e.textContent||'').trim()));if(b)b.click();return !!b})()")
        end = time.time() + wait
        cand = {}
        while time.time() < end:
            try:
                m = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                continue
            if m.get("method") == "Network.responseReceived":
                u = m["params"]["response"]["url"]
                rid = m["params"]["requestId"]
                if "/share/download" in u or "sharedownload" in u:
                    cand[rid] = u
                # CDN tai thang
                if re.search(r"https?://[^/]*(1024tera|terabox|teraboxapp|dubox)\.com/file/", u):
                    return u
            elif m.get("method") == "Network.loadingFinished":
                rid = m["params"].get("requestId")
                if rid in cand:
                    body = self._body(rid)
                    try:
                        j = json.loads(body)
                        if j.get("dlink"):
                            return j["dlink"]
                        if isinstance(j.get("list"), list) and j["list"]:
                            d = j["list"][0].get("dlink")
                            if d:
                                return d
                    except Exception:
                        pass
        return None

    def _body(self, rid):
        gid = self.send("Network.getResponseBody", {"requestId": rid})
        r = self.wait_id(gid, 6)
        if r and "body" in r.get("result", {}):
            import base64
            res = r["result"]
            if res.get("base64Encoded"):
                return base64.b64decode(res["body"]).decode("utf-8", "replace")
            return res["body"]
        return None


def _cookie_str(cks):
    return "; ".join(f"{k}={v}" for k, v in cks.items())


# --------------------------------------------------------------------------- #
# Tai file (resume theo Range)
# --------------------------------------------------------------------------- #

def download_file(dlink, dest: Path, cookie, referer, total=0):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if total and have >= total:
        part.rename(dest)
        return dest
    mode = "ab" if have else "wb"
    headers = {"User-Agent": UA, "Referer": referer, "Cookie": cookie}
    if have:
        headers["Range"] = f"bytes={have}-"
        print(f"   (tiep tuc tu {have/1048576:.1f} MB)")
    req = urllib.request.Request(dlink, headers=headers)
    r = urllib.request.urlopen(req, timeout=120)
    if not total:
        total = have + int(r.headers.get("Content-Length", 0))
    done = have
    t0 = time.time()
    with open(part, mode) as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 / total
                spd = (done - have) / max(time.time() - t0, 0.1) / 1048576
                bar = int(pct / 4)
                sys.stdout.write(
                    f"\r   \U0001F4E5 [{'#'*bar}{'.'*(25-bar)}] {pct:5.1f}% "
                    f"{done/1048576:.1f}/{total/1048576:.1f} MB  {spd:.2f} MB/s   ")
                sys.stdout.flush()
    sys.stdout.write("\n")
    part.rename(dest)
    return dest


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def run(args):
    surl = parse_surl(args.url)
    page_url = f"{HOST}/sharing/link?surl={surl}"

    # luon dam bao Chrome that mo dung trang (de user dang nhap)
    ensure_chrome(page_url)
    time.sleep(2)
    tab = Tab().attach()
    logged, cks = tab.is_logged_in()

    # danh sach file (dung cookie hien tai - share/list khong can login)
    _, _, files = share_list(surl, cookie=_cookie_str(cks))
    files = [f for f in files if str(f.get("isdir")) == "0"]
    if not files:
        sys.exit("Link nay chi co thu muc/khong co file tai thang (chua ho tro folder).")

    if args.check or args.list:
        print("\n================ TERABOX ================")
        print(f"  Dang nhap: {'CO (ndus)' if logged else 'CHUA -> hay dang nhap trong cua so Chrome'}")
        print(f"  So file  : {len(files)}")
        for i, f in enumerate(files, 1):
            print(f"   [{i}] {f.get('server_filename')}  "
                  f"({int(f.get('size', 0))/1048576:.1f} MB)")
        if not logged:
            print("  -> Dang nhap xong, chay lai KHONG --check de tai.")
        print("========================================")
        return

    if not logged:
        print("CHUA dang nhap. Hay dang nhap tai khoan Terabox trong cua so Chrome vua mo,")
        print("cho toi khi vao duoc (thay danh sach file), roi cho 'xong'...")
        # cho login toi da 5 phut
        for _ in range(150):
            time.sleep(2)
            logged, cks = tab.is_logged_in()
            if logged:
                print("=> Da dang nhap! Tien hanh tai...")
                break
        else:
            sys.exit("Het thoi gian cho dang nhap.")

    # chon file
    idx = (args.index - 1) if args.index else 0
    if idx >= len(files):
        sys.exit(f"--index ngoai pham vi (chi co {len(files)} file).")
    f = files[idx]
    name = f.get("server_filename")
    size = int(f.get("size", 0))
    print(f"\nFile: {name}  ({size/1048576:.1f} MB)")

    print("Dang lay link tai truc tiep (hung tu Chrome)...")
    dlink = tab.harvest_dlink()
    if not dlink:
        sys.exit("Khong hung duoc dlink. Thu bam nut Download trong cua so Chrome 1 lan roi chay lai.")
    print(f"dlink: {dlink[:70]}...")

    cookie = _cookie_str(tab.cookies())
    out = Path(args.out) / name
    download_file(dlink, out, cookie, referer=page_url, total=size)
    print(f"\nXong! -> {out.resolve()}")


def build_parser():
    p = argparse.ArgumentParser(description="Tai 1 file tu link share Terabox/1024tera.")
    p.add_argument("url", help="Link share (vd .../sharing/link?surl=...)")
    p.add_argument("--check", action="store_true", help="Liet ke file + trang thai login")
    p.add_argument("--list", action="store_true")
    p.add_argument("--index", type=int, default=0, help="Chon file thu may (mac dinh 1)")
    p.add_argument("--out", default="downloads")
    return p


if __name__ == "__main__":
    try:
        run(build_parser().parse_args())
    except KeyboardInterrupt:
        print("\nDa dung.")
