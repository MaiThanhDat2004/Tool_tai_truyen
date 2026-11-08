# -*- coding: utf-8 -*-
"""
upload_drive.py - Day thu muc truyen da tai len Google Drive (qua rclone).

Cau truc tren Drive se la <dest>/<Ten truyen>/<chuong>/<anh> - dung chuan ma
TruyenDrive (userscript doc truyen tren Google Drive) can.

Chuan bi 1 lan:
    1) Cai rclone (da xong neu dung winget): winget install Rclone.Rclone
    2) Cau hinh remote Google Drive: mo PowerShell go  rclone config
       -> n (new) -> ten: gdrive -> chon "drive" -> Enter qua client_id/secret
       -> scope: 1 (full) -> Enter... -> y (dang nhap bang trinh duyet) -> dang nhap Google.

Dung:
    python upload_drive.py "downloads" --remote gdrive --dest Manga
    python upload_drive.py "downloads/Ten Truyen" --remote gdrive --dest Manga
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent


def find_rclone():
    exe = shutil.which("rclone")
    if exe:
        return exe
    la = os.environ.get("LOCALAPPDATA", "")
    cands = [
        Path(la) / "Microsoft/WinGet/Links/rclone.exe",
        HERE / "rclone" / "rclone.exe",
    ]
    for c in cands:
        if c.exists():
            return str(c)
    # winget Packages (ten phien ban thay doi)
    pkg = Path(la) / "Microsoft/WinGet/Packages"
    if pkg.exists():
        hits = list(pkg.glob("Rclone.Rclone*/**/rclone.exe"))
        if hits:
            return str(hits[0])
    return None


def list_remotes(rclone):
    try:
        out = subprocess.run([rclone, "listremotes"], capture_output=True,
                             text=True, timeout=15).stdout
        return [r.strip().rstrip(":") for r in out.splitlines() if r.strip()]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser(description="Day truyen len Google Drive (rclone).")
    ap.add_argument("src", nargs="+",
                    help="Mot hoac NHIEU thu muc bo truyen can day")
    ap.add_argument("--remote", default="drive", help="Ten remote rclone (mac dinh drive)")
    ap.add_argument("--dest", default="Manga", help="Thu muc dich tren Drive")
    ap.add_argument("--rclone", default="", help="Duong dan rclone.exe (neu can chi ro)")
    args = ap.parse_args()

    rclone = args.rclone or find_rclone()
    if not rclone:
        sys.exit("Khong tim thay rclone. Cai: winget install Rclone.Rclone")

    remotes = list_remotes(rclone)
    if args.remote not in remotes:
        print(f"!! Chua co remote '{args.remote}'. Hien co: {remotes or 'khong co'}")
        print("   Cau hinh 1 lan: mo PowerShell, go  rclone config")
        print("   (new -> dat ten -> chon 'drive' -> dang nhap Google).")
        sys.exit(3)

    # Chi day dinh dang TruyenDrive doc duoc = THU MUC CHUONG (anh trong subfolder).
    # Bo: cbz/pdf/zip; va ca anh GHEP LIEN nam o GOC bo (/*.jpg... - dau / = goc).
    excludes = []
    for pat in ("*.cbz", "*.pdf", "*.zip", "*.cbz.part", "*.part",
                ".progress.json",
                "/*.jpg", "/*.jpeg", "/*.png", "/*.webp", "/*.gif", "/*.avif"):
        excludes += ["--exclude", pat]

    srcs = [Path(s) for s in args.src]
    missing = [s for s in srcs if not s.exists()]
    if missing:
        print("Bo qua (khong ton tai): " + ", ".join(str(m) for m in missing))
    srcs = [s for s in srcs if s.exists()]
    if not srcs:
        sys.exit("Khong co thu muc hop le de day.")

    fail = 0
    for i, src in enumerate(srcs, 1):
        target = f"{args.remote}:{args.dest}/{src.name}"
        print(f"\n[{i}/{len(srcs)}] Day '{src.name}' -> {target}")
        print("   (chi anh; bo qua cbz/pdf; phan da co thi khong tai lai)")
        cmd = [rclone, "copy", str(src), target,
               "--transfers", "4", "--checkers", "8",
               "--drive-chunk-size", "32M",
               "--stats", "3s", "--stats-one-line", "-v"] + excludes
        code = subprocess.call(cmd)
        if code != 0:
            fail += 1
            print(f"   !! Loi bo nay (ma {code})")
    print("\nXong! Da day len Google Drive." if fail == 0
          else f"\nHoan tat, co {fail} bo loi.")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
