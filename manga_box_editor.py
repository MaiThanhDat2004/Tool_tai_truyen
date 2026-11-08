# -*- coding: utf-8 -*-
"""
manga_box_editor - Khoanh vung BANG TAY tren trang truyen (Tkinter canvas).

Ly do: OCR (manga_translate) khoanh vung doi khi lech. Cong cu nay cho ban:
  - Keo chuot ve o (box) dung vi tri.
  - Go loi thoai + chon kieu xoa (fill) cho tung o.
  - Nap san box OCR co san (.json) de CHINH lai thay vi ve tu dau.
  - Luu ra dung SCRIPT JSON cho manga_edit.py.

Toa do box luu theo ANH GOC (khong theo ti le hien thi) -> render chuan.

DUNG:
  python manga_box_editor.py "trang.webp"                 # luu <trang>.json
  python manga_box_editor.py "trang.webp" --out t.json
  python manga_box_editor.py "0001 - Chuong 1" --scripts-dir "scripts"   # ca chuong, Prev/Next

Ban phim/chuot:
  - Keo chuot tren anh  : ve o moi
  - Chon o trong danh sach ben phai -> sua text / fill / xoa
  - Ctrl+S luu | mui ten Trai/Phai chuyen trang (che do thu muc)
"""

import argparse
import json
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

import manga_edit   # dung chung engine de "Xem thu" render ngay trong trinh khoanh

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BG = "#1e1f2b"; PANEL = "#262838"; FIELD = "#2f3147"; LINE = "#3a3c54"
TEXT = "#e7e8f2"; MUTED = "#9aa0bd"; ACCENT = "#8b7cff"; RUN = "#3ecf8e"
FONT = "Segoe UI"
MAX_DISP_W = 900   # be rong hien thi (fit theo CHIEU RONG); anh cao -> cuon doc
MAX_VIEW_H = 900   # chieu cao khung nhin; anh cao hon -> cuon
EXTS = (".jpg", ".jpeg", ".png", ".webp")
FILLS = ["white", "auto", "box", "#000000", "#ffffff"]


class BoxEditor(tk.Tk):
    def __init__(self, pages, scripts_dir, single_out=None):
        super().__init__()
        self.title("Khoanh vung tay - manga box editor")
        self.configure(bg=BG)
        self.geometry("1200x940")
        self.minsize(700, 500)
        self.pages = pages                 # list[Path]
        self.scripts_dir = Path(scripts_dir) if scripts_dir else None
        self.single_out = Path(single_out) if single_out else None
        self.idx = 0
        self.boxes = []                    # [{box,text,fill,align,upper,_rect,_num}]
        self.scale = 1.0
        self.photo = None
        self.orig_img = None               # PIL anh goc trang hien tai
        self.orig_size = (0, 0)
        self._mode = None                  # "draw" | "move" | "resize"
        self._start = None                 # (x,y) canvas luc bam
        self._orig_box = None              # box truoc khi keo (de tinh delta)
        self._drag_rect = None             # rect tam khi ve box moi
        self.preview_on = False            # dang xem ban render?
        self.sel = None                    # index dang chon
        try:
            self.font_path = manga_edit._font_path()
        except Exception:
            self.font_path = None

        self._style()
        self._build()
        self._load_page()
        self.bind("<Control-s>", lambda e: self.save())
        self.bind("<Left>", lambda e: self.prev())
        self.bind("<Right>", lambda e: self.next())
        self.bind("<Delete>", lambda e: self.del_box())
        self.bind("<space>", lambda e: self.toggle_preview())

    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure(".", background=BG, foreground=TEXT, font=(FONT, 10))
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
        st.configure("TButton", background=FIELD, foreground=TEXT, relief="flat",
                     padding=(10, 6))
        st.map("TButton", background=[("active", "#3a3c58")])
        st.configure("Accent.TButton", background=RUN, foreground="#0b2018",
                     font=(FONT, 10, "bold"))
        st.configure("TCombobox", fieldbackground=FIELD, foreground=TEXT,
                     background=FIELD, arrowcolor=TEXT)

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        self.lbl_page = ttk.Label(top, text="", style="Muted.TLabel")
        self.lbl_page.pack(side="left")
        ttk.Button(top, text="◀ Trang", command=self.prev).pack(side="left", padx=(12, 2))
        ttk.Button(top, text="Trang ▶", command=self.next).pack(side="left", padx=2)
        ttk.Button(top, text="💾 Lưu (Ctrl+S)", style="Accent.TButton",
                   command=self.save).pack(side="right")
        self.btn_prev = ttk.Button(top, text="👁 Xem thử (Space)",
                                   command=self.toggle_preview)
        self.btn_prev.pack(side="right", padx=6)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # canvas anh (cuon duoc - anh webtoon rat cao)
        cwrap = ttk.Frame(body)
        cwrap.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(cwrap, bg="#111219", highlightthickness=0,
                                cursor="crosshair")
        vsb = ttk.Scrollbar(cwrap, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(cwrap, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_wheel_h)

        # panel phai
        side = ttk.Frame(body, width=270)
        side.pack(side="right", fill="y", padx=(8, 0))
        side.pack_propagate(False)
        ttk.Label(side, text="Các ô đã khoanh:", style="Muted.TLabel").pack(anchor="w")
        self.lb = tk.Listbox(side, height=12, bg=FIELD, fg=TEXT,
                             selectbackground=ACCENT, relief="flat",
                             highlightthickness=0, activestyle="none", font=(FONT, 9))
        self.lb.pack(fill="x", pady=4)
        self.lb.bind("<<ListboxSelect>>", self._on_select)

        ttk.Label(side, text="Lời thoại (text):", style="Muted.TLabel").pack(anchor="w")
        self.txt = tk.Text(side, height=4, bg=FIELD, fg=TEXT, insertbackground=TEXT,
                           relief="flat", font=(FONT, 10), wrap="word")
        self.txt.pack(fill="x", pady=4)
        self.txt.bind("<KeyRelease>", self._on_text_edit)

        row = ttk.Frame(side)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Xóa nền:", style="Muted.TLabel").pack(side="left")
        self.fill = tk.StringVar(value="white")
        cb = ttk.Combobox(row, textvariable=self.fill, values=FILLS, width=9,
                          state="readonly")
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", self._on_fill)
        self.upper = tk.BooleanVar(value=True)
        tk.Checkbutton(row, text="HOA", variable=self.upper, bg=BG, fg=TEXT,
                       selectcolor=FIELD, activebackground=BG, activeforeground=ACCENT,
                       command=self._on_upper).pack(side="left")

        ttk.Button(side, text="🌐 Dịch ô này (miễn phí)", command=self.translate_box).pack(
            fill="x", pady=(6, 2))
        ttk.Button(side, text="🌐 Dịch cả trang", command=self.translate_page).pack(fill="x")
        ttk.Separator(side, orient="horizontal").pack(fill="x", pady=6)
        ttk.Button(side, text="🗑 Xóa ô này (Del)", command=self.del_box).pack(fill="x", pady=2)
        ttk.Button(side, text="🧹 Xóa hết ô", command=self.clear_all).pack(fill="x")
        ttk.Label(side, text="• Kéo vùng TRỐNG để vẽ ô mới (tự đoán kiểu xóa nền).\n"
                  "• Kéo TRONG ô để di chuyển; kéo GÓC dưới-phải để đổi cỡ.\n"
                  "• Space: xem thử bản render. Tọa độ lưu theo ảnh gốc.",
                  style="Muted.TLabel", wraplength=250, justify="left").pack(
            anchor="w", pady=8)

    # --------------------------------------------------------------- trang
    def _script_path(self, page):
        if self.single_out:
            return self.single_out
        d = self.scripts_dir or page.parent
        return d / (page.stem + ".json")

    def _show(self, pil_img):
        """Hien 1 anh (goc hoac ban render) len canvas, fit theo chieu rong."""
        W, H = pil_img.size
        self.scale = min(MAX_DISP_W / W, 1.0)
        dispW, dispH = max(1, int(W * self.scale)), max(1, int(H * self.scale))
        self.photo = ImageTk.PhotoImage(pil_img.resize((dispW, dispH)))
        self.canvas.config(width=dispW, height=min(dispH, MAX_VIEW_H))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.configure(scrollregion=(0, 0, dispW, dispH))

    def _load_page(self):
        page = self.pages[self.idx]
        self.preview_on = False
        self.btn_prev.config(text="👁 Xem thử (Space)")
        self.orig_img = Image.open(page).convert("RGB")
        self.orig_size = self.orig_img.size
        W, H = self.orig_size
        self._show(self.orig_img)
        self.canvas.yview_moveto(0)
        self.lbl_page.config(
            text=f"[{self.idx + 1}/{len(self.pages)}]  {page.name}   ({W}x{H})")
        self.boxes = []
        self.sel = None
        sp = self._script_path(page)
        if sp.exists():
            try:
                for it in json.loads(sp.read_text(encoding="utf-8")):
                    self.boxes.append({
                        "box": list(it["box"]),
                        "text": it.get("text", it.get("orig", "")),
                        "orig": it.get("orig", it.get("text", "")),
                        "fill": it.get("fill", "white"),
                        "align": it.get("align", "center"),
                        "upper": it.get("upper", True),
                        "_rect": None, "_num": None})
            except Exception as e:
                print("Loi doc script cu:", e)
        self._redraw()

    def prev(self):
        if self.idx > 0:
            self._autosave()
            self.idx -= 1
            self._load_page()

    def next(self):
        if self.idx < len(self.pages) - 1:
            self._autosave()
            self.idx += 1
            self._load_page()

    # --------------------------------------------------------------- ve box
    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_wheel_h(self, e):
        self.canvas.xview_scroll(int(-e.delta / 120), "units")

    def _hit(self, x, y):
        """Tra ve (index, 'resize'|'move') neu (x,y) canvas trung 1 o co san."""
        H = 12  # kich thuoc tay cam goc (px canvas)
        for i in reversed(range(len(self.boxes))):   # o ve sau = tren cung
            bx, by, bw, bh = self.boxes[i]["box"]
            cx, cy = bx * self.scale, by * self.scale
            cw, ch = bw * self.scale, bh * self.scale
            if abs(x - (cx + cw)) <= H and abs(y - (cy + ch)) <= H:
                return i, "resize"
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                return i, "move"
        return None

    def _guess_fill(self, box):
        """Doan kieu xoa nen theo do sang trung binh vung (tren ANH GOC)."""
        try:
            x, y, w, h = box
            crop = self.orig_img.crop((x, y, x + w, y + h)).convert("L")
            px = list(crop.getdata())
            if not px:
                return "white"
            avg = sum(px) / len(px)
            bright = sum(1 for p in px if p > 200) / len(px)
            if bright > 0.5:
                return "white"          # bong bong thoai nen trang
            if avg < 60:
                return "#000000"        # chu trang tren nen den
            return "auto"               # chu tren tranh -> inpaint net
        except Exception:
            return "white"

    def _on_press(self, e):
        if self.preview_on:
            return
        x, y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        self._start = (x, y)
        hit = self._hit(x, y)
        if hit:
            self.sel, self._mode = hit
            self._orig_box = list(self.boxes[self.sel]["box"])
            self._sync_panel()
            self._redraw()
        else:
            self._mode = "draw"
            self._drag_rect = self.canvas.create_rectangle(
                x, y, x, y, outline=ACCENT, width=2)

    def _on_move(self, e):
        if not self._mode:
            return
        x, y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        if self._mode == "draw":
            self.canvas.coords(self._drag_rect, self._start[0], self._start[1], x, y)
        elif self._mode == "move":
            ox, oy, ow, oh = self._orig_box
            dx = int((x - self._start[0]) / self.scale)
            dy = int((y - self._start[1]) / self.scale)
            self.boxes[self.sel]["box"] = [max(0, ox + dx), max(0, oy + dy), ow, oh]
            self._redraw()
        elif self._mode == "resize":
            ox, oy, _, _ = self._orig_box
            nw = max(12, int(x / self.scale - ox))
            nh = max(12, int(y / self.scale - oy))
            self.boxes[self.sel]["box"] = [ox, oy, nw, nh]
            self._redraw()

    def _on_release(self, e):
        mode, self._mode = self._mode, None
        if mode != "draw":
            return
        self.canvas.delete(self._drag_rect)
        self._drag_rect = None
        x1, y1 = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        x0, y0 = self._start
        if abs(x1 - x0) < 8 or abs(y1 - y0) < 8:
            return  # qua nho -> bo (coi nhu click nham)
        ox = int(min(x0, x1) / self.scale)
        oy = int(min(y0, y1) / self.scale)
        ow = int(abs(x1 - x0) / self.scale)
        oh = int(abs(y1 - y0) / self.scale)
        box = [ox, oy, ow, oh]
        self.boxes.append({"box": box, "text": "", "orig": "",
                           "fill": self._guess_fill(box),
                           "align": "center", "upper": True, "_rect": None, "_num": None})
        self.sel = len(self.boxes) - 1
        self._redraw()
        self._sync_panel()
        self.txt.focus_set()

    def toggle_preview(self):
        """Space / nut: render trang hien tai bang manga_edit va xem ngay tai cho."""
        if self.preview_on:
            self.preview_on = False
            self.btn_prev.config(text="👁 Xem thử (Space)")
            self._show(self.orig_img)
            self._redraw()
            return
        if not self.boxes:
            messagebox.showinfo("Trong", "Chua co o nao de xem thu.")
            return
        try:
            tmp = Path(tempfile.gettempdir()) / "_mbe_preview.png"
            manga_edit.apply_script(self.pages[self.idx], self._clean(), tmp,
                                    self.font_path, preview=False)
            rendered = Image.open(tmp).convert("RGB")
        except Exception as ex:
            messagebox.showerror("Loi render", str(ex))
            return
        # xoa overlay o roi hien ban render
        for b in self.boxes:
            for k in ("_rect", "_num"):
                if b.get(k) is not None:
                    self.canvas.delete(b[k])
                    b[k] = None
        self.preview_on = True
        self.btn_prev.config(text="✏️ Sửa tiếp (Space)")
        self._show(rendered)

    def _redraw(self):
        # xoa rect+so+tay cam cu
        self.canvas.delete("handle")
        for b in self.boxes:
            for k in ("_rect", "_num"):
                if b[k] is not None:
                    self.canvas.delete(b[k])
                    b[k] = None
        self.lb.delete(0, "end")
        if self.preview_on:
            return
        for i, b in enumerate(self.boxes):
            x, y, w, h = b["box"]
            cx, cy = x * self.scale, y * self.scale
            cw, ch = w * self.scale, h * self.scale
            col = RUN if i == self.sel else ACCENT
            b["_rect"] = self.canvas.create_rectangle(cx, cy, cx + cw, cy + ch,
                                                      outline=col, width=2)
            b["_num"] = self.canvas.create_text(cx + 3, cy + 3, anchor="nw",
                                                text=str(i + 1), fill=col,
                                                font=(FONT, 10, "bold"))
            if i == self.sel:   # tay cam resize goc duoi-phai
                self.canvas.create_rectangle(cx + cw - 6, cy + ch - 6,
                                             cx + cw + 6, cy + ch + 6,
                                             fill=RUN, outline="white", tags="handle")
            preview = (b["text"] or "(trong)").replace("\n", " ")[:22]
            self.lb.insert("end", f" {i + 1}. [{b['fill']}] {preview}")
        if self.sel is not None:
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(self.sel)

    # --------------------------------------------------------------- chon/sua
    def _on_select(self, e):
        s = self.lb.curselection()
        if s:
            self.sel = s[0]
            self._sync_panel()
            self._redraw()

    def _sync_panel(self):
        if self.sel is None:
            return
        b = self.boxes[self.sel]
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", b["text"])
        self.fill.set(b["fill"])
        self.upper.set(b["upper"])

    def _on_text_edit(self, e):
        if self.sel is not None:
            self.boxes[self.sel]["text"] = self.txt.get("1.0", "end").strip()
            preview = (self.boxes[self.sel]["text"] or "(trong)").replace("\n", " ")[:22]
            self.lb.delete(self.sel)
            self.lb.insert(self.sel, f" {self.sel + 1}. [{self.boxes[self.sel]['fill']}] {preview}")
            self.lb.selection_set(self.sel)

    def _on_fill(self, e=None):
        if self.sel is not None:
            self.boxes[self.sel]["fill"] = self.fill.get()
            self._redraw()

    def _on_upper(self):
        if self.sel is not None:
            self.boxes[self.sel]["upper"] = self.upper.get()

    def del_box(self):
        if self.sel is not None:
            self.boxes.pop(self.sel)
            self.sel = None
            self.txt.delete("1.0", "end")
            self._redraw()

    def clear_all(self):
        if self.boxes and messagebox.askyesno("Xoa het", "Xoa tat ca o tren trang nay?"):
            self.boxes = []
            self.sel = None
            self._redraw()

    # --------------------------------------------------------------- dich (mien phi)
    def _translate_one(self, b):
        """Dich 1 o sang tieng Viet (argos offline -> Google free). KHONG can Claude."""
        import manga_translate as mt
        src = (b.get("orig") or b.get("text") or "").strip()
        if not src:
            return
        b["text"] = mt.translate_text(src, to="vi", src="auto")

    def translate_box(self):
        if self.sel is None:
            messagebox.showinfo("Chua chon", "Hay chon 1 o truoc.")
            return
        self.config(cursor="watch")
        self.update()
        try:
            self._translate_one(self.boxes[self.sel])
        finally:
            self.config(cursor="")
        self._sync_panel()
        self._redraw()

    def translate_page(self):
        if not self.boxes:
            return
        self.config(cursor="watch")
        self.update()
        try:
            for b in self.boxes:
                self._translate_one(b)
        finally:
            self.config(cursor="")
        self._sync_panel()
        self._redraw()

    # --------------------------------------------------------------- luu
    def _clean(self):
        return [{"box": b["box"], "text": b["text"], "fill": b["fill"],
                 "align": b["align"], "upper": b["upper"]} for b in self.boxes]

    def _autosave(self):
        sp = self._script_path(self.pages[self.idx])
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(self._clean(), ensure_ascii=False, indent=1),
                      encoding="utf-8")

    def save(self):
        self._autosave()
        sp = self._script_path(self.pages[self.idx])
        self.lbl_page.config(text=f"Da luu: {sp.name}  ({len(self.boxes)} o)")
        print(f"Luu {len(self.boxes)} o -> {sp}")


def _collect(path):
    p = Path(path)
    if p.is_dir():
        pages = sorted(q for q in p.iterdir() if q.suffix.lower() in EXTS)
        if not pages:
            sys.exit("Thu muc khong co anh.")
        return pages
    if p.suffix.lower() not in EXTS:
        sys.exit("Can 1 anh hoac 1 thu muc chuong.")
    return [p]


def main():
    ap = argparse.ArgumentParser(description="Khoanh vung tay -> script JSON cho manga_edit.")
    ap.add_argument("path", help="1 anh hoac thu muc chuong")
    ap.add_argument("--out", help="File JSON (che do 1 anh)")
    ap.add_argument("--scripts-dir", help="Thu muc luu .json (che do thu muc)")
    args = ap.parse_args()
    pages = _collect(args.path)
    single_out = args.out if (len(pages) == 1 and args.out) else None
    scripts_dir = args.scripts_dir
    if len(pages) == 1 and not single_out and not scripts_dir:
        single_out = str(Path(pages[0]).with_suffix(".json"))
    BoxEditor(pages, scripts_dir, single_out).mainloop()


if __name__ == "__main__":
    main()
