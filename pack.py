# -*- coding: utf-8 -*-
"""
pack.py - Ham dong goi dung chung: stitch (ghep lien mach).

make_stitch: noi tat ca anh cua MOT chuong thanh 1 anh dai lien (khong con
khe ho giua cac trang). Neu qua dai se tu cat thanh nhieu manh (_p01, _p02...)
de file khong qua nang & trinh xem mo duoc (JPEG gioi han ~65500px).
"""

from pathlib import Path


def make_stitch(files, base_path, max_height=18000, quality=88):
    """Ghep cac file anh (theo thu tu) thanh 1 hoac vai anh dai lien mach.
    base_path: duong dan goc (vd thu muc chuong) -> tao file '<ten>.jpg'
               hoac '<ten>_p01.jpg' canh do. Tra ve danh sach file da tao."""
    try:
        from PIL import Image
    except ImportError:
        print("      [bo qua 'ghep lien'] thieu Pillow: pip install Pillow")
        return []

    base_path = Path(base_path)
    files = [Path(f) for f in files]

    # Pass 1: doc kich thuoc (nhe, khong giai ma toan bo)
    sizes = []
    for f in files:
        try:
            with Image.open(f) as im:
                sizes.append(im.size)        # (w, h)
        except Exception:
            sizes.append(None)
    pairs = [(f, s) for f, s in zip(files, sizes) if s]
    if not pairs:
        return []

    width = max(s[0] for _, s in pairs)
    # chieu cao sau khi scale ve cung be ngang
    scaled_h = [round(s[1] * width / s[0]) for _, s in pairs]

    # gom thanh cac manh duoi max_height
    groups, cur, curh = [], [], 0
    for i, h in enumerate(scaled_h):
        if cur and curh + h > max_height:
            groups.append(cur)
            cur, curh = [], 0
        cur.append(i)
        curh += h
    if cur:
        groups.append(cur)

    out = []
    multi = len(groups) > 1
    for gi, grp in enumerate(groups, 1):
        total_h = sum(scaled_h[i] for i in grp)
        canvas = Image.new("RGB", (width, total_h), (255, 255, 255))
        y = 0
        for i in grp:
            f = pairs[i][0]
            try:
                with Image.open(f) as im:
                    im = im.convert("RGB")
                    if im.width != width:
                        im = im.resize((width, scaled_h[i]))
                    canvas.paste(im, (0, y))
            except Exception:
                pass
            y += scaled_h[i]
        name = f"{base_path.name}_p{gi:02d}.jpg" if multi else f"{base_path.name}.jpg"
        outp = base_path.parent / name
        canvas.save(outp, "JPEG", quality=quality)
        canvas.close()
        out.append(outp)
    return out
