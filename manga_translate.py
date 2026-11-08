# -*- coding: utf-8 -*-
"""
manga_translate - "Bo nao": doc chu tren trang (OCR da ngon ngu) -> xuat SCRIPT JSON
cho manga_edit.py. Ho tro DICH thu cong (tu go) HOAC tu dong.

LUONG:
  1) OCR (EasyOCR, offline, da ngon ngu: Nhat/Han/Trung/Anh/Viet...) -> cac box + chu goc.
  2) Gop cac dong gan nhau thanh 1 bong bong (box lon).
  3) Xuat JSON [{box, orig, text, fill}]:
       - orig : chu goc doc duoc
       - text : loi thoai se ve (mac dinh = orig; SUA tay hoac --auto de dich)
       - fill : "white" neu vung gan trang (bong bong thoai) / "auto" (inpaint net) neu tren tranh

DICH:
  --manual (mac dinh): text = orig, ban tu sua trong JSON.
  --auto            : dich text sang --to (mac dinh vi) bang backend offline/online.

DUNG:
  # OCR ca chuong -> moi trang 1 file script .json (de sua tay roi render)
  python manga_translate.py "0001 - Chuong 1" --lang ja --out-dir scripts/
  # 1 trang, tu dong dich sang tieng Viet
  python manga_translate.py "trang.webp" --lang ko --auto --to vi --out trang.json
  # sau do render:
  python manga_edit.py "0001 - Chuong 1" --scripts-dir scripts/ --out-dir edited/
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# EasyOCR: 1 ngon ngu CJK chi ghep duoc voi 'en'. Map lua chon -> danh sach Reader.
_LANG_SETS = {
    "ja": ["ja", "en"], "ko": ["ko", "en"],
    "ch_sim": ["ch_sim", "en"], "ch_tra": ["ch_tra", "en"],
    "en": ["en"], "vi": ["vi", "en"],
}

_READER = None
_READER_KEY = None


def _reader(lang):
    global _READER, _READER_KEY
    langs = _LANG_SETS.get(lang, [lang, "en"])
    if _READER is None or _READER_KEY != lang:
        import easyocr  # lazy: chi nap khi can
        print(f"Nap EasyOCR {langs} (lan dau tai model, hoi lau)...")
        _READER = easyocr.Reader(langs, gpu=False, verbose=False)
        _READER_KEY = lang
    return _READER


# --------------------------------------------------------------------------- #
# OCR + gop box
# --------------------------------------------------------------------------- #

def _quad_to_box(quad):
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    x, y = int(min(xs)), int(min(ys))
    return [x, y, int(max(xs)) - x, int(max(ys)) - y]


def _merge_boxes(items, gap=18):
    """Gop cac box chong nhau khi no rong them `gap` px (gom dong cung 1 bong bong)."""
    boxes = [list(it["box"]) for it in items]
    texts = [it["orig"] for it in items]
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            if boxes[i] is None:
                continue
            for j in range(i + 1, len(boxes)):
                if boxes[j] is None:
                    continue
                if _overlap(boxes[i], boxes[j], gap):
                    boxes[i] = _union(boxes[i], boxes[j])
                    texts[i] = texts[i] + " " + texts[j]
                    boxes[j] = None
                    changed = True
    out = []
    for b, t in zip(boxes, texts):
        if b is not None:
            out.append({"box": b, "orig": t.strip()})
    out.sort(key=lambda it: (it["box"][1], it["box"][0]))
    return out


def _overlap(a, b, gap):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax - gap > bx + bw or bx - gap > ax + aw or
                ay - gap > by + bh or by - gap > ay + ah)


def _union(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x, y = min(ax, bx), min(ay, by)
    return [x, y, max(ax + aw, bx + bw) - x, max(ay + ah, by + bh) - y]


def _guess_fill(img, box):
    """Neu vung box sang & it mau (bong bong thoai trang) -> 'white', nguoc lai 'auto'."""
    x, y, w, h = box
    crop = img.crop((x, y, x + w, y + h)).convert("L")
    px = list(crop.getdata())
    if not px:
        return "auto"
    bright = sum(1 for p in px if p > 200) / len(px)
    return "white" if bright > 0.5 else "auto"


def ocr_page(img_path, lang, min_conf=0.3, gap=18):
    import numpy as np
    reader = _reader(lang)
    img = Image.open(img_path).convert("RGB")
    res = reader.readtext(np.array(img))
    items = []
    for quad, text, conf in res:
        if conf < min_conf or not text.strip():
            continue
        items.append({"box": _quad_to_box(quad), "orig": text.strip()})
    merged = _merge_boxes(items, gap)
    for it in merged:
        it["fill"] = _guess_fill(img, it["box"])
        it["text"] = it["orig"]   # mac dinh; --auto hoac sua tay se thay
    return merged


# --------------------------------------------------------------------------- #
# Dich (KHONG phu thuoc Claude/API tra phi -> chay duoc ca khi khong con tro giup)
#   1) argos-translate : dich HOAN TOAN OFFLINE (khong can internet)
#   2) deep-translator : Google free (can internet), du phong
# --------------------------------------------------------------------------- #

def _argos_translate(text, src, to):
    import argostranslate.translate as at
    s = "en" if src in ("auto", "") else src
    res = at.translate(text, s, to)
    if not res or not res.strip():
        raise RuntimeError("argos rong")
    if res.strip().lower() == text.strip().lower():
        raise RuntimeError("argos chua co goi ngon ngu nay")  # tra nguyen -> coi nhu fail
    return res


def _deep_translate(text, src, to):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=src, target=to).translate(text) or text


def translate_text(text, to="vi", src="auto"):
    """Dich 1 chuoi. Uu tien OFFLINE (argos), roi Google-free (deep-translator).
    Deu MIEN PHI, khong can Claude/API tra phi."""
    text = (text or "").strip()
    if not text:
        return text
    for fn in (_argos_translate, _deep_translate):
        try:
            return fn(text, src, to)
        except Exception:
            continue
    return text   # het cach -> giu nguyen goc


def translate_items(items, to="vi", src="auto"):
    """Dich orig -> text cho ca danh sach (dung translate_text)."""
    for it in items:
        it["text"] = translate_text(it["orig"], to=to, src=src)
    return items


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def _process(img_path, args, out_json):
    items = ocr_page(img_path, args.lang, args.min_conf, args.gap)
    if args.auto and items:
        translate_items(items, to=args.to, src=args.src)
    Path(out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(out_json).write_text(json.dumps(items, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    return len(items)


def run(args):
    src = Path(args.image)
    if src.is_dir():
        out_dir = Path(args.out_dir or (src.parent / (src.name + " (scripts)")))
        imgs = sorted(p for p in src.iterdir()
                      if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
        tot = 0
        for i, p in enumerate(imgs, 1):
            n = _process(p, args, out_dir / (p.stem + ".json"))
            tot += n
            print(f"  [{i}/{len(imgs)}] {p.name}: {n} vung chu")
        print(f"\nXong {len(imgs)} trang, {tot} vung -> {out_dir.resolve()}")
        print("Sua 'text' trong cac .json (neu dich tay) roi chay manga_edit.py --scripts-dir")
    else:
        out = args.out or str(src.with_suffix(".json"))
        n = _process(src, args, out)
        print(f"{n} vung chu -> {Path(out).resolve()}")
        if not args.auto:
            print("Sua 'text' trong JSON roi: python manga_edit.py \"%s\" --script \"%s\""
                  % (src.name, out))


def build_parser():
    p = argparse.ArgumentParser(description="OCR da ngon ngu -> script JSON cho manga_edit.")
    p.add_argument("image", help="1 trang HOAC thu muc chuong")
    p.add_argument("--lang", default="ja", choices=list(_LANG_SETS),
                   help="Ngon ngu goc chinh (ja/ko/ch_sim/ch_tra/en/vi)")
    p.add_argument("--auto", action="store_true", help="Tu dong dich (khong thi giu chu goc de sua tay)")
    p.add_argument("--to", default="vi", help="Dich sang (mac dinh vi)")
    p.add_argument("--src", default="auto", help="Ngon ngu nguon cho may dich (mac dinh auto)")
    p.add_argument("--min-conf", type=float, default=0.3, help="Nguong tin cay OCR")
    p.add_argument("--gap", type=int, default=18, help="Khoang cach gop dong thanh bong bong (px)")
    p.add_argument("--out", help="File JSON (1 trang)")
    p.add_argument("--out-dir", help="Thu muc JSON (che do thu muc)")
    return p


if __name__ == "__main__":
    run(build_parser().parse_args())
