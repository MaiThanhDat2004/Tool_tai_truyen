# -*- coding: utf-8 -*-
"""
manga_edit - Engine CHINH SUA trang truyen: XOA chu (clear) + DAT loi thoai moi (typeset).

TRIET LY (xem THUAT_TOAN.md):
  Tach "bo nao" (doc + dinh vi + dich) khoi "doi tay" (sua pixel).
  File nay LA "doi tay": model-agnostic. Nhan 1 trang + 1 "script" JSON:
      [{"box":[x,y,w,h], "text":"loi thoai moi", "fill":"auto|white|#RRGGBB",
        "align":"center|left|right", "upper":true}, ...]
  -> xoa chu cu trong tung box roi ve chu moi. Ai tao script cung duoc:
     Claude API / manga-ocr / chinh Claude trong phien chat.

XOA (clear) theo `fill`:
  - "white"  : to trang (bong bong thoai nen trang -> sach tuyet doi)
  - "#hex"   : to mau chi dinh
  - "auto"   : lay mau nen quanh vien box (bubble mau) ; neu co cv2 -> inpaint
               content-aware (SFX de tren tranh phuc tap dep hon).

TYPESET:
  - Auto-wrap + auto co chu cho vua box. Ve chu co vien (stroke) trang/den
    de noi ro tren moi nen. Font mac dinh Arial (co dau tieng Viet).

DUNG:
  # xem truoc cac box (ve khung do de kiem tra dinh vi)
  python manga_edit.py "trang.webp" --script script.json --preview --out preview.png
  # chinh that
  python manga_edit.py "trang.webp" --script script.json --out out.png
  # ca thu muc chuong (moi trang 1 file <ten>.json cung ten)
  python manga_edit.py "0001 - Chuong 1" --scripts-dir scripts/ --out-dir edited/
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import cv2          # optional: inpaint content-aware
    import numpy as np
    _HAS_CV = True
except Exception:
    _HAS_CV = False

# font co dau tieng Viet (Arial bold uu tien - kieu chu manga hay dung)
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
]


def _font_path(user_font=None):
    if user_font and Path(user_font).exists():
        return user_font
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("Khong tim thay font co dau tieng Viet (Arial/Segoe).")


# --------------------------------------------------------------------------- #
# XOA chu trong 1 box
# --------------------------------------------------------------------------- #

def _edge_color(img, box, pad=3):
    """Mau trung binh vien ngoai box (dung lam nen khi 'auto', khong co cv2)."""
    x, y, w, h = box
    px = img.load()
    W, H = img.size
    samples = []
    for xx in range(max(0, x - pad), min(W, x + w + pad), 4):
        for yy in (max(0, y - pad), min(H - 1, y + h + pad)):
            samples.append(px[xx, yy][:3])
    for yy in range(max(0, y - pad), min(H, y + h + pad), 4):
        for xx in (max(0, x - pad), min(W - 1, x + w + pad)):
            samples.append(px[xx, yy][:3])
    if not samples:
        return (255, 255, 255)
    n = len(samples)
    return tuple(sum(c[i] for c in samples) // n for i in range(3))


def clear_box(img, box, fill="auto"):
    """Xoa chu trong box. Tra ve img (sua tai cho)."""
    x, y, w, h = box
    if fill == "white":
        ImageDraw.Draw(img).rectangle([x, y, x + w, y + h], fill=(255, 255, 255))
        return img
    if isinstance(fill, str) and fill.startswith("#"):
        c = tuple(int(fill[i:i + 2], 16) for i in (1, 3, 5))
        ImageDraw.Draw(img).rectangle([x, y, x + w, y + h], fill=c)
        return img
    # fill == "auto" (chi net chu) hoac "box" (ca o)
    if _HAS_CV:
        return _inpaint_cv(img, box, whole=(fill == "box"))
    # khong co cv2: to mau nen vien (tot cho bubble mau; SFX tren tranh se tho)
    ImageDraw.Draw(img).rectangle([x, y, x + w, y + h], fill=_edge_color(img, box))
    return img


def _inpaint_cv(img, box, pad=8, radius=3, whole=False):
    """Inpaint content-aware (Telea). Mac dinh chi xoa DUNG NET chu (stroke-mask)
    -> giu texture nen xung quanh, dep hon nhieu cho SFX tren tranh. whole=True: ca o."""
    x, y, w, h = box
    arr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    H, W = arr.shape[:2]
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
    full = np.zeros((H, W), np.uint8)
    if whole:
        full[y0:y1, x0:x1] = 255
    else:
        roi = cv2.cvtColor(arr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        med = float(np.median(roi))
        # net chu lech manh khoi nen (bat ca chu den lan vien trang)
        mask = (np.abs(roi.astype(np.int16) - med) > 55).astype(np.uint8) * 255
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
        # bo dom nho (tan lua/hat sang), giu manh chu lon
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        area_min = max(30, (x1 - x0) * (y1 - y0) // 400)
        keep = np.zeros_like(mask)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= area_min:
                keep[lab == i] = 255
        keep = cv2.dilate(keep, k, iterations=2)
        full[y0:y1, x0:x1] = keep
    out = cv2.inpaint(arr, full, radius, cv2.INPAINT_TELEA)
    res = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    img.paste(res)
    return img


# --------------------------------------------------------------------------- #
# TYPESET loi thoai moi vao box
# --------------------------------------------------------------------------- #

def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        test = (cur + " " + wd).strip()
        if draw.textlength(test, font=font) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text, font_path, box_w, box_h, max_size=64, min_size=9):
    """Binary-search co chu lon nhat ma text (da wrap) van vua box."""
    lo, hi, best = min_size, max_size, None
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid)
        lines = _wrap(draw, text, font, box_w)
        lh = (draw.textbbox((0, 0), "Ag", font=font)[3]) + max(2, mid // 6)
        total_h = lh * len(lines)
        widest = max((draw.textlength(ln, font=font) for ln in lines), default=0)
        if total_h <= box_h and widest <= box_w:
            best = (font, lines, lh)
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        font = ImageFont.truetype(font_path, min_size)
        best = (font, _wrap(draw, text, font, box_w),
                draw.textbbox((0, 0), "Ag", font=font)[3] + 2)
    return best


def typeset_box(img, box, text, font_path, align="center", upper=True,
                color=(20, 20, 20), stroke=(255, 255, 255)):
    x, y, w, h = box
    if upper:
        text = text.upper()
    draw = ImageDraw.Draw(img)
    pad = max(4, int(min(w, h) * 0.06))
    font, lines, lh = _fit(draw, text, font_path, w - 2 * pad, h - 2 * pad)
    sw = max(1, font.size // 14)
    total_h = lh * len(lines)
    cy = y + (h - total_h) // 2
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        if align == "left":
            cx = x + pad
        elif align == "right":
            cx = x + w - pad - tw
        else:
            cx = x + (w - tw) // 2
        draw.text((cx, cy), ln, font=font, fill=color,
                  stroke_width=sw, stroke_fill=stroke)
        cy += lh
    return img


# --------------------------------------------------------------------------- #
# Ap 1 script len 1 trang
# --------------------------------------------------------------------------- #

def apply_script(img_path, script, out_path, font_path, preview=False):
    img = Image.open(img_path).convert("RGB")
    if preview:
        d = ImageDraw.Draw(img)
        for i, it in enumerate(script, 1):
            x, y, w, h = it["box"]
            d.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=3)
            d.text((x + 3, y + 3), str(i), fill=(255, 0, 0))
    else:
        for it in script:
            clear_box(img, it["box"], it.get("fill", "auto"))
        for it in script:
            txt = it.get("text", "").strip()
            if txt:
                typeset_box(img, it["box"], txt, font_path,
                            align=it.get("align", "center"),
                            upper=it.get("upper", True))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def pack_cbz(folder):
    """Dong goi 1 thu muc anh (da chinh) thanh <ten>.cbz canh no."""
    import truyenqq_dl as tq
    folder = Path(folder)
    imgs = sorted(p for p in folder.iterdir()
                  if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    if not imgs:
        sys.exit("Khong co anh trong thu muc de dong goi.")
    cbz = folder.parent / (folder.name + ".cbz")
    tq.make_cbz(imgs, cbz)
    print(f"-> {cbz}  ({len(imgs)} trang)")


def run(args):
    if getattr(args, "pack_cbz", False):
        pack_cbz(args.image)
        return
    font_path = _font_path(args.font)
    src = Path(args.image)

    if src.is_dir():
        sd = Path(args.scripts_dir) if args.scripts_dir else src
        out_dir = Path(args.out_dir or (src.parent / (src.name + " (edited)")))
        imgs = sorted(p for p in src.iterdir()
                      if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
        import shutil
        n, copied = 0, 0
        for p in imgs:
            js = sd / (p.stem + ".json")
            has = js.exists() and json.loads(js.read_text(encoding="utf-8"))
            if has:
                apply_script(p, json.loads(js.read_text(encoding="utf-8")),
                             out_dir / (p.stem + ".png"), font_path, args.preview)
                n += 1
                print(f"  [{p.name}] da chinh ({len(has)} box)")
            elif not args.preview:
                # trang tranh (khong co script) -> copy nguyen ban de chuong LIEN MACH
                out_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out_dir / p.name)
                copied += 1
        print(f"\nXong: {n} trang chinh + {copied} trang tranh (copy) -> {out_dir.resolve()}")
        return

    if not args.script:
        sys.exit("Can --script <file.json> khi chinh 1 trang.")
    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    out = args.out or str(src.with_name(src.stem + "_edit.png"))
    apply_script(src, script, out, font_path, args.preview)
    mode = "PREVIEW (khung do)" if args.preview else "da chinh"
    print(f"{mode}: {len(script)} box -> {Path(out).resolve()}")
    print(f"Inpaint: {'cv2 (content-aware)' if _HAS_CV else 'Pillow (to nen vien)'}")


def build_parser():
    p = argparse.ArgumentParser(description="Chinh sua trang truyen: xoa chu + dat loi thoai.")
    p.add_argument("image", help="1 trang anh HOAC thu muc chuong")
    p.add_argument("--script", help="JSON [{box,text,fill,align,upper}] cho 1 trang")
    p.add_argument("--scripts-dir", help="Thu muc chua <ten trang>.json (che do thu muc)")
    p.add_argument("--out", help="File xuat (1 trang)")
    p.add_argument("--out-dir", help="Thu muc xuat (che do thu muc)")
    p.add_argument("--font", help="Font .ttf (mac dinh Arial bold)")
    p.add_argument("--preview", action="store_true", help="Chi ve khung do de kiem tra dinh vi")
    p.add_argument("--pack-cbz", action="store_true",
                   help="Dong goi thu muc anh (da chinh) thanh .cbz roi thoat")
    return p


if __name__ == "__main__":
    run(build_parser().parse_args())
