# -*- coding: utf-8 -*-
"""
comix_dl - Adapter cho comix.to (SPA chong cao manh: API ky token + response
ma hoa + CDN anh an danh).

Khong forge token (de gay). Thay vao do DIEU KHIEN TRINH DUYET THAT: de chinh JS
cua trang ky token & giai ma, minh chi thu hoach KET QUA da render:
  - Danh sach chuong: doc tu DOM, bam phan trang ('Next page') de lay het.
  - Anh moi chuong: render + cuon, lay URL anh that tu cac the <img> (trinh duyet
    da giai ma URL CDN). Anh tai duoc truc tiep (khong can Referer).

    python comix_dl.py "https://comix.to/title/yknr-grapara"
    python comix_dl.py "<link>" --range 1 20 --format folder cbz
"""

import argparse
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

import truyenqq_dl as tq          # slugify, make_cbz, make_pdf
import pack

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
JUNK = re.compile(r"(icon|logo|avatar|thumb|/ads?/|banner|favicon|sprite|/static/)", re.I)
JUNK_HOST = re.compile(
    r"(google|analytics|gstatic|sentry|cloudflare|doubleclick|facebook|"
    r"adservice|amazon-adsystem|cdn-cgi|recaptcha|gtag)", re.I)


def is_content_img(u, site_host):
    # Anh truyen nam o CDN KHAC (khong phai comix.to), khong phai analytics/blob/data.
    if not u or u.startswith("data:") or u.startswith("blob:"):
        return False
    if JUNK.search(u) or JUNK_HOST.search(u):
        return False
    h = urlparse(u).netloc
    return bool(h) and site_host not in h


def ext_from(ctype, data):
    ctype = (ctype or "").lower()
    if "webp" in ctype:
        return ".webp"
    if "png" in ctype:
        return ".png"
    if "jpeg" in ctype or "jpg" in ctype:
        return ".jpg"
    if "gif" in ctype:
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    return ".jpg"


def download_img(url):
    # Khong gui Referer: https://comix.to/ vi CDN anh comix se chan 403 Forbidden
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        return data, r.headers.get("content-type", "")


# --------------------------------------------------------------------------- #
# Trinh duyet
# --------------------------------------------------------------------------- #

# Bam 'Next page' cua DUNG pager chua danh sach chuong, bang JS (vuot overlay
# quang cao chan click). Ho tro ca nut Next ro rang lan nut so trang tiep theo.
JS_NEXT = r"""() => {
  const pagers = [...document.querySelectorAll('.npager, [class*="pager"], [class*="pagination"]')];
  for (const pg of pagers) {
    let root = pg;
    for (let i = 0; i < 7 && root.parentElement; i++) root = root.parentElement;
    if (root.querySelector("a[href*='-chapter-']")) {
      // 1. Thu tim nut Next ro rang neu co
      const nxt = pg.querySelector(".npager__nav[aria-label='Next page'], [aria-label*='Next'], [aria-label*='next']");
      if (nxt && !nxt.disabled && !(nxt.className || '').includes('disabled')) {
        nxt.click();
        return { clicked: true };
      }
      // 2. Thu tim nut so trang tiep theo (sibling ngay sau active)
      const act = pg.querySelector('.npager__num.is-active, [aria-current="page"], .is-active, .active');
      if (act) {
        let sib = act.nextElementSibling;
        while (sib && sib.tagName !== 'BUTTON' && sib.tagName !== 'A') {
          sib = sib.nextElementSibling;
        }
        if (sib && !sib.disabled && !(sib.className || '').includes('disabled')) {
          sib.click();
          return { clicked: true };
        }
      }
    }
  }
  return { clicked: false, active: 'no-pager' };
}"""


def enumerate_chapters(page, base):
    """Lay {so_chuong: url} qua tat ca trang danh sach chuong (phan trang JS)."""
    found = {}

    def collect():
        hrefs = page.eval_on_selector_all(
            "a[href*='-chapter-']", "e => e.map(x => x.getAttribute('href'))")
        for h in hrefs or []:
            m = re.search(r"-chapter-([\d.]+)", h or "")
            if m:
                found[m.group(1)] = urljoin(base, h)

    # Cho trang tai xong danh sach chuong ban dau (toi da 10 giay)
    for _ in range(20):
        collect()
        if found:
            break
        page.wait_for_timeout(500)

    no_growth = 0
    for _ in range(400):                  # an toan
        before = len(found)
        r = page.evaluate(JS_NEXT)
        if not r.get("clicked"):          # het trang (Next bi khoa)
            break
        # Cho trang moi render them chuong (polling nhanh 40ms)
        for _ in range(30):
            page.wait_for_timeout(40)
            collect()
            if len(found) > before:
                break
        if len(found) == before:
            no_growth += 1
            if no_growth >= 3:            # 3 lan lien khong them -> dung
                break
        else:
            no_growth = 0
    return found


# Lay anh truyen LON NHAT dang hien thi (trang hien tai cua reader)
JS_MAIN_IMG = r"""(host) => {
  let best = null, area = 0;
  document.querySelectorAll('img').forEach(im => {
    const u = im.currentSrc || im.src || '';
    if (!u || u.startsWith('data:') || u.includes(host)) return;
    if (/icon|logo|avatar|favicon|sprite|thumb|banner/i.test(u)) return;
    const r = im.getBoundingClientRect();
    const a = r.width * r.height;
    if (a > area && r.width > 100) { best = u; area = a; }
  });
  return best;
}"""

JS_TOTAL = r"""() => {
  const nums = [...document.querySelectorAll('[aria-label]')]
    .map(e => { const m = /^Go to page (\d+)$/.exec(e.getAttribute('aria-label') || ''); return m ? +m[1] : 0; })
    .filter(Boolean);
  return nums.length ? Math.max(...nums) : 0;
}"""


# Phan tu (img/canvas) DANG HIEN GIUA viewport = trang hien tai (da giai xao).
JS_PAGE_EL = r"""() => {
  const cx = innerWidth / 2, cy = innerHeight / 2;
  let best = null, area = 0, fb = null, fa = 0;
  document.querySelectorAll('img,canvas').forEach(e => {
    const r = e.getBoundingClientRect();
    if (r.width < 150 || r.height < 150) return;
    const a = r.width * r.height;
    if (a > fa) { fb = e; fa = a; }
    if (r.left <= cx && r.right >= cx && r.top <= cy && r.bottom >= cy && a > area) {
      best = e; area = a;
    }
  });
  return best || fb;
}"""

_GOTO_PAGE = r"""(n) => {
  // 1. Thu click truc tiep nut tren thanh tien trinh (rpage-progress__seg)
  const direct = document.querySelector('[aria-label="Go to page ' + n + '"]');
  if (direct) {
    direct.click();
    return true;
  }
  // 2. Neu khong co, mo menu Settings roi click (cho phien ban cu)
  const setBtn = [...document.querySelectorAll('button,[role=button],[aria-label]')]
    .find(e => (e.getAttribute('aria-label')||e.textContent||'').trim()==='Settings');
  if (setBtn) {
    setBtn.click();
    const inSet = [...document.querySelectorAll('[aria-label]')]
      .find(e => e.getAttribute('aria-label')==='Go to page '+n);
    if (inSet) inSet.click();
    const closeBtn = [...document.querySelectorAll('[aria-label]')]
      .find(e => (e.getAttribute('aria-label')||'')==='Close settings');
    if (closeBtn) closeBtn.click();
    return true;
  }
  return false;
}"""


def capture_chapter(page, chapter_url, site_host, sink, ch_dir):
    """Lat qua tung trang nhanh chong (40ms polling), thu thap URL anh va
    tai song song da luong (ThreadPoolExecutor). Neu la anh xao tron (canvas/blob),
    tu dong fallback sang chup screenshot hoac fetch blob in-page."""
    import base64
    from concurrent.futures import ThreadPoolExecutor

    sink.clear()
    try:
        page.goto(chapter_url, wait_until="networkidle", timeout=30000)
    except Exception:
        try:
            page.goto(chapter_url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
    page.wait_for_timeout(1500)
    total = page.evaluate(JS_TOTAL) or 1
    ch_dir.mkdir(parents=True, exist_ok=True)

    # 1. Quet nhanh URL va loai anh tung trang (40ms polling)
    page_items = []  # list of [n, kind, src, data, ext]
    for n in range(1, total + 1):
        if total > 1:
            page.evaluate(_GOTO_PAGE, n)

        info = {}
        for _ in range(25):
            page.wait_for_timeout(40)
            info = page.evaluate(JS_MAIN_INFO) or {}
            src = info.get("src", "")
            tag = info.get("tag", "")
            if tag == "canvas":
                break
            if src and (src.startswith("http") or src.startswith("blob:")):
                break

        tag = info.get("tag", "")
        src = info.get("src", "")

        # Truong hop blob: fetch truc tiep in-page
        if src.startswith("blob:"):
            try:
                b64 = page.evaluate(_JS_FETCH_BLOB, src)
                data = base64.b64decode(b64) if b64 else b""
                page_items.append([n, "bytes", None, data, ".webp"])
            except Exception:
                page_items.append([n, "canvas", None, b"", None])
        # Truong hop canvas (bi xao tron) hoac khong co src -> chup man hinh
        elif tag == "canvas" or not src:
            page.wait_for_timeout(200)
            try:
                el = page.evaluate_handle(JS_PAGE_EL).as_element()
                data = el.screenshot() if el else b""
                page_items.append([n, "bytes", None, data, ".png"])
            except Exception:
                page_items.append([n, "error", None, b"", ".jpg"])
        else:
            # Anh HTTP CDN truc tiep -> danh dau de tai song song
            page_items.append([n, "http", src, b"", None])

        print(f"\r      quet trang {n}/{total}", end="", flush=True)
    print()

    # 2. Tai song song da luong tat ca anh HTTP CDN
    def _fetch_worker(item):
        n, kind, src, _, _ = item
        if kind != "http" or not src:
            return n, b"", ""
        try:
            data, ct = download_img(src)
            return n, data, ct
        except Exception:
            return n, b"", ""

    http_items = [it for it in page_items if it[1] == "http"]
    dl_map = {}
    if http_items:
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = ex.map(_fetch_worker, http_items)
            for n, data, ct in results:
                dl_map[n] = (data, ct)

    # 3. Ghi file theo thu tu va xu ly fallback neu tai loi
    saved = []
    for idx, it in enumerate(page_items, 1):
        n, kind, src, data, ext = it
        ct = ""
        if kind == "http":
            data, ct = dl_map.get(n, (b"", ""))
            ext = ext_from(ct, data) if data else ".webp"

        # Fallback 1: Neu download HTTP bi loi -> thu fetch in-page
        if len(data or b"") < 800 and src and src.startswith("http"):
            try:
                b64 = page.evaluate(_JS_FETCH_BLOB, src)
                if b64:
                    data = base64.b64decode(b64)
                    ext = ".webp"
            except Exception:
                pass

        # Fallback 2: Neu van chua co anh -> chuyen toi trang do va chup man hinh
        if len(data or b"") < 800:
            try:
                page.evaluate(_GOTO_PAGE, n)
                page.wait_for_timeout(300)
                el = page.evaluate_handle(JS_PAGE_EL).as_element()
                if el:
                    data = el.screenshot()
                    ext = ".png"
            except Exception:
                pass

        if len(data or b"") < 800:
            continue

        fp = ch_dir / f"{str(idx).zfill(3)}{ext or '.webp'}"
        fp.write_bytes(data)
        saved.append(fp)
        print(f"\r      luu trang {idx}/{total}", end="", flush=True)

    print()
    return saved


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
            print(f"      -> ghep lien: {len(made)} file")
    if "folder" not in formats:
        for f in files:
            f.unlink(missing_ok=True)
        try:
            ch_dir.rmdir()
        except OSError:
            pass


_JS_FETCH_BLOB = (
    "async (u) => { const r = await fetch(u); const b = await r.arrayBuffer();"
    " let s=''; const a=new Uint8Array(b); for (let i=0;i<a.length;i++) s+=String.fromCharCode(a[i]);"
    " return btoa(s); }")


# Phan tu dang hien giua viewport la gi: canvas / img(blob) / img(CDN truc tiep).
JS_MAIN_INFO = r"""() => {
  const cx = innerWidth / 2, cy = innerHeight / 2;
  let best = null, a = 0, fb = null, fa = 0;
  document.querySelectorAll('img,canvas').forEach(e => {
    const r = e.getBoundingClientRect();
    if (r.width < 150 || r.height < 150) return;
    const ar = r.width * r.height;
    if (ar > fa) { fb = e; fa = ar; }
    if (r.left <= cx && r.right >= cx && r.top <= cy && r.bottom >= cy && ar > a) { best = e; a = ar; }
  });
  const el = best || fb;
  if (!el) return null;
  if (el.tagName === 'CANVAS') return { tag: 'canvas' };
  return { tag: 'img', src: el.currentSrc || el.src || '' };
}"""


def is_chapter_scrambled(page, chapter_url, site_host, sink):
    """Anh hien ra bang gi? canvas / blob = trinh duyet DA GIAI XAO -> bi xao.
    img src CDN truc tiep = khong xao (tai thang duoc)."""
    sink.clear()
    try:
        page.goto(chapter_url, wait_until="networkidle", timeout=30000)
    except Exception:
        try:
            page.goto(chapter_url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
    page.wait_for_timeout(2200)
    total = page.evaluate(JS_TOTAL) or 1
    target = min(3, total)                        # trang noi dung (tranh bia)
    before = {u for u in sink if is_content_img(u, site_host)}
    if total > 1:
        page.evaluate(_GOTO_PAGE, target)
        page.wait_for_timeout(250)
    for _ in range(25):                           # cho trang noi dung tai
        page.wait_for_timeout(200)
        if any(is_content_img(u, site_host) and u not in before for u in sink):
            break
    page.wait_for_timeout(1100)                   # cho giai xao xong
    info = page.evaluate(JS_MAIN_INFO)
    if not info:
        return False
    if info.get("tag") == "canvas":
        return True
    src = info.get("src", "")
    if src.startswith("blob:") or src.startswith("data:"):
        return True
    return False                                  # img CDN truc tiep -> khong xao


PROFILE_DIR = Path.home() / ".tool_tai_truyen" / "comix_profile"


def run(args):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Can Playwright: pip install playwright; python -m playwright install chromium")

    base = f"{urlparse(args.url).scheme}://{urlparse(args.url).netloc}"
    site_host = urlparse(args.url).netloc

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    is_headless = bool(getattr(args, "headless", False))

    with sync_playwright() as p:
        # Uu tien dung Google Chrome that tren may + profile luu tru de vuot Cloudflare Turnstile
        launch_kwargs = {
            "user_data_dir": str(PROFILE_DIR),
            "headless": is_headless,
            "viewport": {"width": 1400, "height": 1000},
            "device_scale_factor": 2,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        try:
            ctx = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
        except Exception:
            ctx = p.chromium.launch_persistent_context(**launch_kwargs)

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        sink = []
        # Bat MOI request (anh tai qua 'image' LAN 'fetch'->blob deu can)
        page.on("request", lambda r: sink.append(r.url))

        print("Dang mo trang & lay danh sach chuong...")
        try:
            page.goto(args.url, wait_until="networkidle", timeout=30000)
        except Exception:
            try:
                page.goto(args.url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
        page.wait_for_timeout(2000)

        # Cho toi da 20 giay de Cloudflare Turnstile tu xac minh xong tren cua so Chrome
        for i in range(20):
            if page.query_selector("a[href*='-chapter-']"):
                break
            if page.query_selector('.wafcap__frame, iframe[src*="@waf/challenge"]'):
                if i == 0:
                    print("  Dang cho Cloudflare Turnstile xac minh tren cua so Chrome (3-5 giay)...")
            page.wait_for_timeout(1000)

        title = re.sub(r"\s*[-|].*$", "", page.title()).strip() or tq.slugify(args.url)

        chmap = enumerate_chapters(page, base)
        if not chmap:
            print("Khong lay duoc danh sach chuong.")
            ctx.close()
            sys.exit(2)

        chapters = sorted(chmap.items(), key=lambda kv: float(kv[0]))
        nums = [float(n) for n, _ in chapters]
        rng = f" (chuong {min(nums):g}..{max(nums):g})" if nums else ""

        sel = chapters
        if args.range:
            a, b = args.range
            sel = [(n, u) for n, u in sel if a <= float(n) <= b]
        if args.limit:
            sel = sel[: args.limit]

        # --- CHAN DOAN ---
        if args.check:
            scr = is_chapter_scrambled(page, (sel or chapters)[0][1], site_host, sink)
            print("\n================ CHAN DOAN ================")
            print("  Ket qua  : TAI DUOC (qua trinh duyet) ✔")
            print(f"  Truyen   : {title}")
            print(f"  So chuong: {len(chapters)}{rng}")
            print(f"  Anh bi xao tron: {'CO -> phai CHUP (cham hon)' if scr else 'KHONG -> tai thang (nhanh)'}")
            print("===========================================")
            ctx.close()
            return

        if args.list:
            for n, u in sel:
                print(f"  Ch {n}")
            ctx.close()
            return

        out_dir = Path(args.out) / tq.slugify(title)
        done = tq.progress_load(out_dir)
        print(f"Truyen: {title} | Tong chuong: {len(chapters)}{rng}")
        print(f"Tai {len(sel)} chuong vao: {out_dir.resolve()}")
        if done:
            print(f"(Tiep tuc: da co {len(done)} chuong hoan tat tu lan truoc)")
        print()

        for i, (num, curl) in enumerate(sel, 1):
            label = f"Chuong {num}"
            ch_dir = out_dir / tq.slugify(f"{i:04d} - {label}")
            cbz = ch_dir.parent / (ch_dir.name + ".cbz")
            if (ch_dir.name in done or cbz.exists()) and not args.overwrite:
                print(f"[{i}/{len(sel)}] (da co) {label}")
                done.add(ch_dir.name)
                continue
            print(f"[{i}/{len(sel)}] {label}")
            try:
                # 1 ham tu thich nghi: trang img CDN -> tai thang; canvas/blob -> chup/fetch
                saved = capture_chapter(page, curl, site_host, sink, ch_dir)
                if not saved:
                    print("      (khong lay duoc trang)")
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

        ctx.close()
    print("\nXong!")


def build_parser():
    p = argparse.ArgumentParser(description="Tai truyen comix.to (dieu khien trinh duyet).")
    p.add_argument("url", help="Link bo truyen comix.to")
    p.add_argument("--range", nargs=2, type=float, metavar=("A", "B"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--list", action="store_true")
    p.add_argument("--check", action="store_true",
                   help="Chi chan doan: so chuong + co bi xao tron khong")
    p.add_argument("--format", nargs="+", default=["folder", "cbz"],
                   choices=["folder", "cbz", "pdf", "stitch"])
    p.add_argument("--out", default="downloads")
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--headful", action="store_true", default=True,
                   help="Hien trinh duyet (mac dinh: giup vuot Cloudflare)")
    p.add_argument("--headless", action="store_true",
                   help="Chay an (khong hien cua so, co the bi Cloudflare WAF chan)")
    p.add_argument("--overwrite", action="store_true")
    return p


if __name__ == "__main__":
    try:
        run(build_parser().parse_args())
    except KeyboardInterrupt:
        print("\nDa dung.")
