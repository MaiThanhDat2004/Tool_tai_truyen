# -*- coding: utf-8 -*-
"""
to_excel.py - Xuat 1 chuong truyen ra file Excel (.xlsx) dang HANG DOC:
  moi trang 1 hang | cot A: so trang | cot B: ANH (nhung that) | cot C: REVIEW.

- Nhung anh THAT vao o (openpyxl + Pillow thumbnail), khong phai link.
- O Excel cao toi da ~409pt -> tu thu nho anh cho vua (rong <=260px, cao <=480px).
- Review lay tu file JSON (--reviews): {"001.jpg": "loi review", ...} hoac {"1": "..."}.
  Khong co -> cot review de TRONG cho tu dien.

DUNG:
  python to_excel.py "D:/tai_truyen/<bo>/<chuong>"                       # cot review trong
  python to_excel.py "<chuong>" --reviews reviews.json --out review.xlsx
  python to_excel.py "<chuong>" --title "I Love Yoo - Prologue"

  pip install openpyxl Pillow
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

try:
    import openpyxl
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
except ImportError:
    sys.exit("Thieu thu vien: pip install openpyxl")
try:
    from PIL import Image as PILImage
except ImportError:
    sys.exit("Thieu thu vien: pip install Pillow")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
MAX_W = 260            # px - be rong thumbnail trong Excel
MAX_H = 480            # px - cao toi da (de row height < 409pt)
STITCH = re.compile(r"_p\d+$", re.I)     # bo file ghep-lien (_pNN)


def list_pages(folder: Path):
    items = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in IMG_EXT:
            continue
        if STITCH.search(p.stem):           # bo anh stitch
            continue
        items.append(p)
    # sap theo so trong ten file
    def key(p):
        m = re.search(r"\d+", p.stem)
        return (int(m.group()) if m else 1 << 30, p.name)
    items.sort(key=key)
    return items


def thumb_png(path: Path):
    """Tra ve (bytes_png, w, h) da thu nho vua khung."""
    im = PILImage.open(path)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    w, h = im.size
    scale = min(MAX_W / w, MAX_H / h, 1.0)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    im = im.resize((nw, nh))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    buf.seek(0)
    return buf, nw, nh


def load_reviews(path):
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"(khong doc duoc reviews: {e})")
        return {}


def build(folder: Path, reviews: dict, out_path: Path, title: str):
    pages = list_pages(folder)
    if not pages:
        sys.exit(f"Khong thay anh trong: {folder}")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Review"

    head_fill = PatternFill("solid", fgColor="2F2F3A")
    head_font = Font(bold=True, color="FFFFFF", size=12)
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws["A1"], ws["B1"], ws["C1"] = "Trang", "Anh", "Review"
    if title:
        ws["D1"] = title
        ws["D1"].font = Font(italic=True, color="888888")
    for c in ("A1", "B1", "C1"):
        ws[c].fill = head_fill
        ws[c].font = head_font
        ws[c].alignment = Alignment(horizontal="center", vertical="center")

    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = (MAX_W / 7.0) + 2     # ~px/7 don vi Excel
    ws.column_dimensions["C"].width = 72
    ws.freeze_panes = "A2"

    keep = []     # giu BytesIO song den khi save
    row = 2
    for idx, p in enumerate(pages, 1):
        try:
            buf, nw, nh = thumb_png(p)
        except Exception as e:
            print(f"  [bo qua] {p.name}: {e}")
            continue
        keep.append(buf)
        img = XLImage(buf)
        ws.add_image(img, f"B{row}")
        ws.row_dimensions[row].height = nh * 0.75 + 6       # px -> pt

        ws[f"A{row}"] = idx
        ws[f"A{row}"].alignment = Alignment(horizontal="center", vertical="top")
        ws[f"A{row}"].border = border

        rv = reviews.get(p.name) or reviews.get(p.stem) or reviews.get(str(idx)) or ""
        cell = ws[f"C{row}"]
        cell.value = rv
        cell.alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")
        cell.border = border
        ws[f"B{row}"].border = border
        print(f"  trang {idx}: {p.name} ({nw}x{nh})" + ("  [co review]" if rv else ""))
        row += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    print(f"\nXong! {len(pages)} trang -> {out_path}")


def run(args):
    folder = Path(args.folder)
    if not folder.is_dir():
        sys.exit(f"Khong phai thu muc: {folder}")
    out = Path(args.out) if args.out else folder.parent / (folder.name + ".xlsx")
    title = args.title or folder.name
    reviews = load_reviews(args.reviews)
    print(f"Thu muc: {folder}\nReview: {len(reviews)} muc\nXuat: {out}\n")
    build(folder, reviews, out, title)


def build_parser():
    p = argparse.ArgumentParser(description="Xuat chuong truyen ra Excel (anh + cot review).")
    p.add_argument("folder", help="Thu muc 1 chuong (chua cac anh 001.jpg...)")
    p.add_argument("--reviews", help="File JSON {ten_anh: review}")
    p.add_argument("--out", help="File .xlsx xuat ra")
    p.add_argument("--title", help="Tieu de (cot D hang 1)")
    return p


if __name__ == "__main__":
    run(build_parser().parse_args())
