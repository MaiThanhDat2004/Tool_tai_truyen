# -*- coding: utf-8 -*-
"""
mangadex_dl - Tai tron bo truyen tu MangaDex qua API chinh thuc.

Diem dac biet: NHUNG san DNS-over-HTTPS (Cloudflare 1.1.1.1) nen chay duoc
ngay ca khi nha mang chan DNS toi mangadex (khong can doi DNS he thong,
khong can VPN, khong can trinh duyet).

Vi du:
    # Tim theo ten roi tai ca bo (tieng Anh)
    python mangadex_dl.py "search:grapara"

    # Tai bang link hoac ID truyen
    python mangadex_dl.py https://mangadex.org/title/<id>/...
    python mangadex_dl.py c384faed-e34c-4ee0-bd38-70ce5ff146c7

    # Chi liet ke chuong (khong tai)
    python mangadex_dl.py <id> --list

    # Chon ngon ngu, dinh dang, gioi han
    python mangadex_dl.py <id> --lang en --format folder cbz pdf --limit 5
"""

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

# Console Windows hay dung cp1252 -> ep UTF-8 de in duoc ten chuong co emoji/ky tu la
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

API = "https://api.mangadex.org"
UA = "manga-dl/1.0 (personal use; +https://github.com/)"
DOH_SERVER = "https://1.1.1.1/dns-query"

# --------------------------------------------------------------------------- #
# DNS-over-HTTPS: vuot chan DNS cho *.mangadex.org va *.mangadex.network
# --------------------------------------------------------------------------- #
_orig_getaddrinfo = socket.getaddrinfo
_doh_cache = {}


def _doh_resolve(host: str):
    if host in _doh_cache:
        return _doh_cache[host]
    url = f"{DOH_SERVER}?name={urllib.parse.quote(host)}&type=A"
    req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        ips = [a["data"] for a in d.get("Answer", []) if a.get("type") == 1]
    except Exception:
        ips = []
    _doh_cache[host] = ips
    return ips


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and (
        host == "mangadex.org"
        or host.endswith(".mangadex.org")
        or host.endswith(".mangadex.network")
    ):
        ips = _doh_resolve(host)
        if ips:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
                    for ip in ips]
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _patched_getaddrinfo


# --------------------------------------------------------------------------- #
# HTTP tien ich (chi dung stdlib)
# --------------------------------------------------------------------------- #

def http_get(url: str, as_json: bool = True, retries: int = 5):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read()
            return json.loads(body) if as_json else body
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:                       # bi gioi han toc do
                wait = int(e.headers.get("Retry-After", 0) or
                           e.headers.get("X-RateLimit-Retry-After", 0) or 0)
                wait = wait if wait else (attempt + 1) * 5
                print(f"      (429 - cho {wait}s)")
                time.sleep(wait)
            elif e.code in (500, 502, 503, 504):
                time.sleep((attempt + 1) * 2)
            else:
                raise
        except Exception as e:
            last = e
            time.sleep((attempt + 1) * 2)
    raise RuntimeError(f"GET that bai: {url} ({last})")


# --------------------------------------------------------------------------- #
# Tien ich file
# --------------------------------------------------------------------------- #

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(text, maxlen=90):
    text = INVALID.sub("_", (text or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return (text or "untitled")[:maxlen]


def make_cbz(files, cbz_path: Path):
    cbz_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cbz_path.parent / (cbz_path.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, arcname=f.name)
    tmp.replace(cbz_path)


def make_pdf(files, pdf_path: Path):
    try:
        from PIL import Image
    except ImportError:
        print("      [bo qua PDF] thieu Pillow: pip install Pillow")
        return
    pages = []
    for f in files:
        try:
            pages.append(Image.open(f).convert("RGB"))
        except Exception as e:
            print(f"      [PDF] loi {f.name}: {e}")
    if pages:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pages[0].save(pdf_path, "PDF", save_all=True, append_images=pages[1:])


# --------------------------------------------------------------------------- #
# MangaDex API
# --------------------------------------------------------------------------- #

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def resolve_manga_id(arg: str, pick: int):
    """Tra ve (manga_id, title). Chap nhan id / link / 'search:tu khoa'."""
    if arg.startswith("search:"):
        q = arg[len("search:"):].strip()
        url = (f"{API}/manga?title={urllib.parse.quote(q)}&limit=10"
               "&contentRating[]=safe&contentRating[]=suggestive"
               "&contentRating[]=erotica&contentRating[]=pornographic")
        data = http_get(url)["data"]
        if not data:
            sys.exit(f"Khong tim thay truyen nao voi tu khoa: {q}")
        print(f"Tim thay {len(data)} ket qua:")
        for i, m in enumerate(data):
            t = m["attributes"]["title"]
            title = t.get("en") or next(iter(t.values()), "?")
            print(f"  [{i}] {title}  ({m['attributes']['originalLanguage']})")
        if pick >= len(data):
            sys.exit(f"--pick {pick} ngoai pham vi (0..{len(data)-1})")
        chosen = data[pick]
        t = chosen["attributes"]["title"]
        return chosen["id"], (t.get("en") or next(iter(t.values()), "manga"))

    m = UUID_RE.search(arg)
    if not m:
        sys.exit("Khong nhan ra ID/link. Dung 'search:ten' hoac dan link MangaDex.")
    mid = m.group(0)
    info = http_get(f"{API}/manga/{mid}")["data"]
    t = info["attributes"]["title"]
    return mid, (t.get("en") or next(iter(t.values()), "manga"))


def get_chapters(manga_id: str, lang: str):
    """Lay toan bo chuong theo ngon ngu, da phan trang."""
    chapters, offset = [], 0
    while True:
        url = (f"{API}/manga/{manga_id}/feed"
               f"?translatedLanguage[]={lang}&limit=500&offset={offset}"
               "&order[volume]=asc&order[chapter]=asc"
               "&includes[]=scanlation_group"
               "&contentRating[]=safe&contentRating[]=suggestive"
               "&contentRating[]=erotica&contentRating[]=pornographic")
        resp = http_get(url)
        chapters.extend(resp["data"])
        offset += 500
        if offset >= resp["total"]:
            break
        time.sleep(0.3)
    return chapters


def dedupe_chapters(chapters, all_groups: bool):
    """Bo chuong external (khong tai duoc) va trung so chuong."""
    items, seen = [], set()
    for c in chapters:
        a = c["attributes"]
        if a.get("externalUrl"):          # chuong dan ra trang ngoai -> bo
            continue
        num = a.get("chapter")
        key = num if num is not None else f"oneshot-{c['id']}"
        if not all_groups and key in seen:
            continue
        seen.add(key)
        grp = ""
        for rel in c.get("relationships", []):
            if rel["type"] == "scanlation_group":
                grp = rel.get("attributes", {}).get("name", "")
        items.append({
            "id": c["id"],
            "num": num,
            "title": a.get("title") or "",
            "group": grp,
            "pages": a.get("pages", 0),
        })

    def sortkey(it):
        try:
            return (0, float(it["num"]))
        except (TypeError, ValueError):
            return (1, 0.0)

    items.sort(key=sortkey)
    return items


def get_image_urls(chapter_id: str, data_saver: bool):
    info = http_get(f"{API}/at-home/server/{chapter_id}")
    base = info["baseUrl"]
    h = info["chapter"]["hash"]
    mode = "data-saver" if data_saver else "data"
    files = info["chapter"]["dataSaver" if data_saver else "data"]
    return [f"{base}/{mode}/{h}/{fn}" for fn in files]


# --------------------------------------------------------------------------- #
# Luong chinh
# --------------------------------------------------------------------------- #

def download_chapter(urls, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    pad = max(3, len(str(len(urls))))
    saved = []
    for i, url in enumerate(urls, 1):
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".jpg"
        fp = out_dir / f"{str(i).zfill(pad)}{ext}"
        if fp.exists() and fp.stat().st_size > 1024:
            saved.append(fp)
            print(f"\r      anh {i}/{len(urls)} (da co)", end="", flush=True)
            continue
        try:
            body = http_get(url, as_json=False)
            fp.write_bytes(body)
            saved.append(fp)
        except Exception as e:
            print(f"\n      [bo qua] anh {i}: {e}")
        print(f"\r      anh {i}/{len(urls)}      ", end="", flush=True)
        time.sleep(0.15)
    print()
    return saved


def run(args):
    manga_id, title = resolve_manga_id(args.manga, args.pick)
    title_slug = slugify(title)
    print(f"\nTruyen: {title}  ({manga_id})")

    if args.langs:
        from collections import Counter
        cnt, off = Counter(), 0
        while True:
            r = http_get(f"{API}/manga/{manga_id}/feed?limit=500&offset={off}"
                         "&contentRating[]=safe&contentRating[]=suggestive"
                         "&contentRating[]=erotica&contentRating[]=pornographic")
            for c in r["data"]:
                l = c["attributes"].get("translatedLanguage")
                if l:
                    cnt[l] += 1
            off += 500
            if off >= r["total"]:
                break
            time.sleep(0.3)
        if not cnt:
            print("Khong tim thay chuong nao.")
            return
        print("Ngon ngu co san (dung ma nay cho --lang):")
        for l, n in cnt.most_common():
            print(f"  {l:<6}: {n} chuong")
        return

    chapters = dedupe_chapters(get_chapters(manga_id, args.lang), args.all_groups)
    if not chapters:
        print(f"Khong co chuong nao o ngon ngu '{args.lang}'. "
              "Thu --lang ja / vi / ... hoac kiem tra lai.")
        return

    print(f"Ngon ngu: {args.lang} | So chuong: {len(chapters)}")

    if args.list:
        for i, c in enumerate(chapters, 1):
            n = c["num"] if c["num"] is not None else "oneshot"
            print(f"  {i:>4}. Ch {n:<8} {c['title']}  [{c['group']}]")
        return

    sel = chapters[args.start:]
    if args.limit:
        sel = sel[: args.limit]

    out_dir = Path(args.out) / title_slug
    print(f"Se tai {len(sel)} chuong vao: {out_dir.resolve()}\n")

    for idx, c in enumerate(sel, start=args.start + 1):
        n = c["num"] if c["num"] is not None else "oneshot"
        label = f"Ch {n}" + (f" - {c['title']}" if c["title"] else "")
        ch_dir = out_dir / slugify(f"{idx:04d} - {label}")
        # KHONG dung with_suffix vi ten chuong co the chua dau cham (vd "Ch 3.5")
        cbz = ch_dir.parent / (ch_dir.name + ".cbz")
        pdf = ch_dir.parent / (ch_dir.name + ".pdf")

        if cbz.exists() and not args.overwrite:
            print(f"[{idx}/{len(chapters)}] (da co) {label}")
            continue

        print(f"[{idx}/{len(chapters)}] {label}  [{c['group']}]")
        try:
            urls = get_image_urls(c["id"], args.data_saver)
            if not urls:
                print("      (khong co anh)")
                continue
            print(f"      {len(urls)} trang")
            files = download_chapter(urls, ch_dir)
            if not files:
                continue
            if "cbz" in args.format:
                make_cbz(files, cbz)
                print(f"      -> {cbz.name}")
            if "pdf" in args.format:
                make_pdf(files, pdf)
                print(f"      -> {pdf.name}")
            if "stitch" in args.format:
                import pack
                made = pack.make_stitch(files, ch_dir)
                if made:
                    print(f"      -> ghep lien: {len(made)} file")
            if "folder" not in args.format:
                for f in files:
                    f.unlink(missing_ok=True)
                try:
                    ch_dir.rmdir()
                except OSError:
                    pass
        except Exception as e:
            print(f"      LOI: {e}")
        time.sleep(args.delay)

    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(
        description="Tai tron bo truyen tu MangaDex (co DoH vuot chan DNS).")
    p.add_argument("manga", help="ID, link MangaDex, hoac 'search:tu khoa'")
    p.add_argument("--lang", default="en", help="Ngon ngu ban dich (mac dinh en)")
    p.add_argument("--format", nargs="+", default=["folder", "cbz"],
                   choices=["folder", "cbz", "pdf", "stitch"], help="Dinh dang xuat")
    p.add_argument("--out", default="downloads", help="Thu muc luu")
    p.add_argument("--list", action="store_true", help="Chi liet ke chuong")
    p.add_argument("--langs", action="store_true",
                   help="Chi liet ke cac ngon ngu co san cua bo truyen")
    p.add_argument("--limit", type=int, default=0, help="Chi tai N chuong (0=tat ca)")
    p.add_argument("--start", type=int, default=0, help="Bat dau tu chuong thu may (0-based)")
    p.add_argument("--pick", type=int, default=0, help="Chon ket qua thu may khi search")
    p.add_argument("--all-groups", action="store_true",
                   help="Giu ca cac ban dich trung (nhieu nhom dich)")
    p.add_argument("--data-saver", action="store_true",
                   help="Tai anh nen nhe (nho hon, chat luong thap hon)")
    p.add_argument("--delay", type=float, default=0.8, help="Nghi giua cac chuong (giay)")
    p.add_argument("--overwrite", action="store_true", help="Tai lai chuong da co")
    return p


if __name__ == "__main__":
    try:
        run(build_parser().parse_args())
    except KeyboardInterrupt:
        print("\nDa dung.")
