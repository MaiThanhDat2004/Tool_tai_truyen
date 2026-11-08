# -*- coding: utf-8 -*-
"""
gui.py - Giao dien cua so (Tkinter) cho bo tool tai truyen.

2 TAB:
  [Tai truyen] gop cac nguon: Tu dong (auto_dl) / MangaDex / TruyenQQ /
     mangafire (Cloudflare) / Trang bat ky (Playwright).
  [Chinh sua] xoa chu + lettering lai: OCR tao script (manga_translate.py) ->
     sua tay hoac tu dong dich -> Render (manga_edit.py). Ket qua ra thu muc
     '<chuong> (scripts)' va '<chuong> (edited)' canh chuong goc.

App chay cac tool CLI bang chinh Python dang chay (uu tien venv), va do log
ra cua so theo thoi gian thuc. Rieng tab Chinh sua can OpenCV + EasyOCR (da cai venv).

Chay:
  python gui.py
  (hoac bam dung file run_gui.bat)
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

HERE = Path(__file__).resolve().parent
PY = sys.executable  # python dang chay app (neu mo bang venv thi la venv)

# ----- Bang mau (dark theme hien dai) -----
BG     = "#1e1f2b"   # nen chinh
PANEL  = "#262838"   # khung
FIELD  = "#2f3147"   # o nhap / nut thuong
LINE   = "#3a3c54"   # vien
TEXT   = "#e7e8f2"   # chu chinh
MUTED  = "#9aa0bd"   # chu phu
ACCENT = "#8b7cff"   # tim - nhan
ACC2   = "#5b8cff"   # xanh duong - nhan phu
RUN    = "#3ecf8e"   # xanh la - nut Tai
RUNH   = "#33b87d"
STOP   = "#ff5c6c"   # do - nut Dung
STOPH  = "#e84a5a"
LOGBG  = "#15161f"
LOGFG  = "#cdd1e6"
FONT   = "Segoe UI"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
DEBUG_PROFILE = r"C:\chrome-debug-profile"
DEBUG_PORT = "9222"


def find_chrome():
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tool tai truyen tranh")
        self.geometry("900x700")
        self.minsize(760, 600)
        self.configure(bg=BG)

        self.proc = None
        self.log_q = queue.Queue()
        self._chain_upload = False

        self._setup_style()
        self._build()
        self._on_source_change()
        self.after(80, self._drain_log)
        self.after(120, self._bring_front)

    def _setup_style(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=TEXT,
                     fieldbackground=FIELD, bordercolor=LINE,
                     lightcolor=LINE, darkcolor=LINE, font=(FONT, 10))
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
        st.configure("Title.TLabel", background=BG, foreground=TEXT,
                     font=(FONT, 16, "bold"))
        st.configure("Sub.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
        st.configure("TLabelframe", background=BG, bordercolor=LINE, relief="solid")
        st.configure("TLabelframe.Label", background=BG, foreground=ACCENT,
                     font=(FONT, 10, "bold"))
        st.configure("TRadiobutton", background=BG, foreground=TEXT)
        st.map("TRadiobutton", foreground=[("selected", ACCENT), ("active", ACC2)],
               background=[("active", BG)])
        st.configure("TCheckbutton", background=BG, foreground=TEXT)
        st.map("TCheckbutton", foreground=[("active", ACC2)], background=[("active", BG)])
        st.configure("TEntry", fieldbackground=FIELD, foreground=TEXT,
                     insertcolor=TEXT, bordercolor=LINE, padding=5)
        st.map("TEntry", bordercolor=[("focus", ACCENT)])
        st.configure("TCombobox", fieldbackground=FIELD, foreground=TEXT,
                     background=FIELD, arrowcolor=TEXT, bordercolor=LINE, padding=4)
        st.configure("TProgressbar", background=ACCENT, troughcolor=FIELD,
                     bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

        # --- Nut ---
        st.configure("TButton", background=FIELD, foreground=TEXT, bordercolor=LINE,
                     relief="flat", padding=(12, 7), font=(FONT, 10))
        st.map("TButton",
               background=[("active", "#3a3c58"), ("disabled", "#23242f")],
               foreground=[("disabled", "#666b82")])
        st.configure("Accent.TButton", background=RUN, foreground="#0b2018",
                     font=(FONT, 10, "bold"))
        st.map("Accent.TButton",
               background=[("active", RUNH), ("disabled", "#2b4a3d")],
               foreground=[("disabled", "#6c8f80")])
        st.configure("Stop.TButton", background=STOP, foreground="#2a0c10",
                     font=(FONT, 10, "bold"))
        st.map("Stop.TButton",
               background=[("active", STOPH), ("disabled", "#4a2a2e")],
               foreground=[("disabled", "#8a6166")])
        st.configure("Ghost.TButton", background=PANEL, foreground=MUTED)
        st.map("Ghost.TButton", background=[("active", "#33354c")],
               foreground=[("active", TEXT)])

    def _bring_front(self):
        """Ep cua so noi len truoc (tranh bi an sau cua so khac)."""
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.after(700, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    # ------------------------------------------------------------------ UI
    def _build(self):
        pad = {"padx": 12, "pady": 5}

        # --- Header ---
        head = ttk.Frame(self)
        head.pack(fill="x", padx=12, pady=(12, 2))
        ttk.Label(head, text="📚  Tool tải truyện", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="manga · manhwa · manhua",
                  style="Sub.TLabel").pack(side="left", padx=(10, 0), pady=(8, 0))

        # --- Notebook: 2 tab (Tai / Chinh sua) ---
        self._edit_btns = []
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="x", padx=12, pady=(6, 0))
        dl = ttk.Frame(self.nb)
        ed = ttk.Frame(self.nb)
        self.nb.add(dl, text="   📥  Tải truyện   ")
        self.nb.add(ed, text="   ✏️  Chỉnh sửa   ")
        self._build_edit_tab(ed)

        # --- Nguon ---
        top = ttk.LabelFrame(dl, text="Nguồn")
        top.pack(fill="x", **pad)
        self.source = tk.StringVar(value="Tu dong (moi trang)")
        for i, s in enumerate(["Tu dong (moi trang)", "MangaDex",
                               "TruyenQQ/NetTruyen (VN)", "mangafire (Cloudflare)",
                               "Trang bat ky"]):
            ttk.Radiobutton(top, text=s, value=s, variable=self.source,
                            command=self._on_source_change).grid(
                row=i // 3, column=i % 3, padx=10, pady=4, sticky="w")

        # --- O nhap chinh ---
        inp = ttk.Frame(dl)
        inp.pack(fill="x", **pad)
        self.lbl_target = ttk.Label(inp, text="Link / ID / search:")
        self.lbl_target.grid(row=0, column=0, sticky="w")
        self.target = tk.StringVar()
        ttk.Entry(inp, textvariable=self.target).grid(
            row=0, column=1, sticky="we", padx=6)
        inp.columnconfigure(1, weight=1)
        self.hint = ttk.Label(inp, text="", style="Muted.TLabel")
        self.hint.grid(row=1, column=1, sticky="w", padx=6)

        # --- Tuy chon dac thu theo nguon ---
        self.opt = ttk.LabelFrame(dl, text="Tuy chon")
        self.opt.pack(fill="x", **pad)

        # MangaDex
        self.lang = tk.StringVar(value="en")
        self.limit = tk.StringVar(value="0")
        self.data_saver = tk.BooleanVar(value=False)
        # mangafire
        self.mf_name = tk.StringVar(value="")
        self.mf_r1 = tk.StringVar(value="")
        self.mf_r2 = tk.StringVar(value="")
        # tu dong
        self.auto_r1 = tk.StringVar(value="")
        self.auto_r2 = tk.StringVar(value="")
        self.auto_browser = tk.BooleanVar(value=True)
        # truyenqq
        self.qq_r1 = tk.StringVar(value="")
        self.qq_r2 = tk.StringVar(value="")
        # generic
        self.mode = tk.StringVar(value="auto")
        self.headful = tk.BooleanVar(value=False)

        self._auto_frame = self._make_auto_opts()
        self._mangadex_frame = self._make_mangadex_opts()
        self._truyenqq_frame = self._make_truyenqq_opts()
        self._mangafire_frame = self._make_mangafire_opts()
        self._generic_frame = self._make_generic_opts()

        # --- Dinh dang + thu muc luu ---
        out = ttk.Frame(dl)
        out.pack(fill="x", **pad)
        ttk.Label(out, text="Dinh dang:").grid(row=0, column=0, sticky="w")
        self.f_folder = tk.BooleanVar(value=True)
        self.f_cbz = tk.BooleanVar(value=True)
        self.f_pdf = tk.BooleanVar(value=False)
        self.f_stitch = tk.BooleanVar(value=False)
        ttk.Checkbutton(out, text="Thu muc anh", variable=self.f_folder).grid(row=0, column=1)
        ttk.Checkbutton(out, text="CBZ", variable=self.f_cbz).grid(row=0, column=2)
        ttk.Checkbutton(out, text="PDF", variable=self.f_pdf).grid(row=0, column=3)
        ttk.Checkbutton(out, text="Ghep lien (1 anh dai)",
                        variable=self.f_stitch).grid(row=0, column=4)

        ttk.Label(out, text="Luu vao:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.outdir = tk.StringVar(value=str(HERE / "downloads"))
        ttk.Entry(out, textvariable=self.outdir).grid(
            row=1, column=1, columnspan=3, sticky="we", padx=6, pady=(6, 0))
        ttk.Button(out, text="Chọn...", command=self._pick_dir).grid(
            row=1, column=4, pady=(6, 0))
        out.columnconfigure(1, weight=1)

        # --- Google Drive ---
        self.gdrive_up = tk.BooleanVar(value=False)
        self.gdrive_remote = tk.StringVar(value="drive")
        self.gdrive_dest = tk.StringVar(value="Manga")
        drv = ttk.Frame(dl)
        drv.pack(fill="x", **pad)
        ttk.Checkbutton(drv, text="☁ Tải xong thì hỏi đẩy lên Drive",
                        variable=self.gdrive_up).grid(row=0, column=0, sticky="w")
        ttk.Label(drv, text="remote:", style="Muted.TLabel").grid(
            row=0, column=1, padx=(12, 2))
        ttk.Entry(drv, textvariable=self.gdrive_remote, width=8).grid(row=0, column=2)
        ttk.Label(drv, text="thư mục Drive:", style="Muted.TLabel").grid(
            row=0, column=3, padx=(12, 2))
        ttk.Entry(drv, textvariable=self.gdrive_dest, width=10).grid(row=0, column=4)
        ttk.Button(drv, text="☁ Chọn truyện đẩy lên...", style="Ghost.TButton",
                   command=self.start_upload).grid(row=0, column=5, padx=(12, 0))

        # --- Nut hanh dong ---
        act = ttk.Frame(dl)
        act.pack(fill="x", **pad)
        self.btn_run = ttk.Button(act, text="▶  Tải", style="Accent.TButton",
                                  command=self.start_download)
        self.btn_run.pack(side="left")
        self.btn_resume = ttk.Button(act, text="⏩ Tiếp tục", command=self.start_resume)
        self.btn_resume.pack(side="left", padx=6)
        self.btn_check = ttk.Button(act, text="Chẩn đoán", command=self.start_check)
        self.btn_check.pack(side="left", padx=6)
        self.btn_list = ttk.Button(act, text="Liệt kê chương", command=self.start_list)
        self.btn_list.pack(side="left", padx=6)
        self.btn_chrome = ttk.Button(act, text="Mở Chrome gỡ lỗi",
                                     command=self.open_debug_chrome)
        self.btn_chrome.pack(side="left", padx=6)
        self.btn_stop = ttk.Button(act, text="■  Dừng", style="Stop.TButton",
                                   command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        self.btn_reset = ttk.Button(act, text="↻ Làm mới", style="Ghost.TButton",
                                    command=self.reset)
        self.btn_reset.pack(side="left", padx=6)
        ttk.Button(act, text="📂 Mở thư mục", style="Ghost.TButton",
                   command=self._open_outdir).pack(side="right")
        ttk.Button(act, text="Xóa log", style="Ghost.TButton",
                   command=self._clear_log).pack(side="right", padx=6)

        # --- Trang thai + log ---
        self.status = tk.StringVar(value="Sẵn sàng.")
        bar = ttk.Frame(self)
        bar.pack(fill="x", **pad)
        self.pb = ttk.Progressbar(bar, mode="indeterminate")
        self.pb.pack(side="left", fill="x", expand=True)
        ttk.Label(bar, textvariable=self.status, style="Muted.TLabel").pack(
            side="right", padx=8)

        logf = ttk.LabelFrame(self, text="Nhật ký")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=12, wrap="word", bg=LOGBG, fg=LOGFG,
                           insertbackground=TEXT, selectbackground=ACCENT,
                           relief="flat", borderwidth=0, padx=10, pady=8,
                           font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set, state="disabled")

    def _make_auto_opts(self):
        f = ttk.Frame(self.opt)
        ttk.Label(f, text="Day chuong (tu - den, de trong = tat ca):").grid(
            row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.auto_r1, width=6).grid(row=0, column=1, padx=2)
        ttk.Entry(f, textvariable=self.auto_r2, width=6).grid(row=0, column=2, padx=2)
        ttk.Label(f, text="Gioi han:").grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Entry(f, textvariable=self.limit, width=6).grid(row=0, column=4, padx=4)
        ttk.Checkbutton(f, text="Tu dung trinh duyet khi can (Playwright)",
                        variable=self.auto_browser).grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))
        ttk.Label(f, text="Tool tu phan tich link; bam 'Chan doan' de thu truoc.",
                  style="Muted.TLabel").grid(row=2, column=0, columnspan=5, sticky="w")
        return f

    def _make_mangadex_opts(self):
        f = ttk.Frame(self.opt)
        ttk.Label(f, text="Ngon ngu:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.lang, width=6).grid(row=0, column=1, padx=4)
        ttk.Label(f, text="Gioi han chuong (0=tat ca):").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(f, textvariable=self.limit, width=6).grid(row=0, column=3, padx=4)
        ttk.Checkbutton(f, text="Anh nhe (data-saver)", variable=self.data_saver).grid(
            row=0, column=4, padx=(12, 0))
        ttk.Button(f, text="Xem ngon ngu co san", command=self.start_langs).grid(
            row=0, column=5, padx=(12, 0))
        return f

    def _make_truyenqq_opts(self):
        f = ttk.Frame(self.opt)
        ttk.Label(f, text="Day chuong (tu - den, de trong = tat ca):").grid(
            row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.qq_r1, width=6).grid(row=0, column=1, padx=2)
        ttk.Entry(f, textvariable=self.qq_r2, width=6).grid(row=0, column=2, padx=2)
        ttk.Label(f, text="Gioi han chuong:").grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Entry(f, textvariable=self.limit, width=6).grid(row=0, column=4, padx=4)
        return f

    def _make_mangafire_opts(self):
        f = ttk.Frame(self.opt)
        ttk.Label(f, text="Ten bo:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.mf_name, width=18).grid(row=0, column=1, padx=4)
        ttk.Label(f, text="Day chuong (tu - den):").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(f, textvariable=self.mf_r1, width=5).grid(row=0, column=3, padx=2)
        ttk.Entry(f, textvariable=self.mf_r2, width=5).grid(row=0, column=4, padx=2)
        ttk.Label(f, text="(can mo Chrome go loi & vuot Cloudflare truoc)",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))
        return f

    def _make_generic_opts(self):
        f = ttk.Frame(self.opt)
        ttk.Label(f, text="Che do:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.mode, width=8, state="readonly",
                     values=["auto", "series", "chapter"]).grid(row=0, column=1, padx=4)
        ttk.Label(f, text="Gioi han chuong:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(f, textvariable=self.limit, width=6).grid(row=0, column=3, padx=4)
        ttk.Checkbutton(f, text="Hien trinh duyet", variable=self.headful).grid(
            row=0, column=4, padx=(12, 0))
        return f

    # ----------------------------------------------------------- tab Chinh sua
    def _build_edit_tab(self, root):
        pad = {"padx": 12, "pady": 6}
        self.ed_path = tk.StringVar()
        self.ed_lang = tk.StringVar(value="ja")
        self.ed_to = tk.StringVar(value="vi")
        self.ed_auto = tk.BooleanVar(value=False)

        ttk.Label(root, text="Xóa chữ gốc & chèn lời thoại mới. Quy trình 3 bước:  "
                  "①  OCR tạo script  →  ②  (sửa tay hoặc để máy dịch)  →  ③  Render.",
                  style="Muted.TLabel").pack(anchor="w", **pad)

        p = ttk.Frame(root)
        p.pack(fill="x", **pad)
        ttk.Label(p, text="Thư mục chương / 1 ảnh:").grid(row=0, column=0, sticky="w")
        ttk.Entry(p, textvariable=self.ed_path).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(p, text="📁 Thư mục", command=self._pick_edit_dir).grid(row=0, column=2)
        ttk.Button(p, text="🖼 Ảnh", command=self._pick_edit_file).grid(row=0, column=3, padx=(6, 0))
        p.columnconfigure(1, weight=1)

        o = ttk.LabelFrame(root, text="Tùy chọn dịch")
        o.pack(fill="x", **pad)
        ttk.Label(o, text="Ngôn ngữ gốc:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(o, textvariable=self.ed_lang, width=9, state="readonly",
                     values=["ja", "ko", "ch_sim", "ch_tra", "en", "vi"]).grid(
            row=0, column=1, padx=4)
        ttk.Checkbutton(o, text="Tự động dịch", variable=self.ed_auto).grid(
            row=0, column=2, padx=(16, 4))
        ttk.Label(o, text="→ sang:").grid(row=0, column=3, sticky="w")
        ttk.Entry(o, textvariable=self.ed_to, width=6).grid(row=0, column=4, padx=4)
        ttk.Label(o, text="(bỏ 'Tự động dịch' = chỉ OCR; bạn mở .json sửa 'text' rồi Render)",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=5,
                                             sticky="w", padx=8, pady=(0, 6))

        a = ttk.Frame(root)
        a.pack(fill="x", **pad)
        b1 = ttk.Button(a, text="①  🔍 OCR → tạo script", command=self.start_edit_ocr)
        b1.pack(side="left")
        ttk.Button(a, text="✎ Khoanh tay", command=self.start_box_editor).pack(
            side="left", padx=6)
        b2 = ttk.Button(a, text="②  👁 Xem trước khung", command=self.start_edit_preview)
        b2.pack(side="left", padx=6)
        b3 = ttk.Button(a, text="③  ✏️ Render", style="Accent.TButton",
                        command=self.start_edit_render)
        b3.pack(side="left", padx=6)
        b4 = ttk.Button(a, text="④  📦 Đóng gói CBZ", command=self.start_edit_cbz)
        b4.pack(side="left", padx=6)
        self._edit_btns += [b4]
        ttk.Button(a, text="📂 Ảnh đã sửa", style="Ghost.TButton",
                   command=self._open_edited).pack(side="right")
        ttk.Button(a, text="📝 Thư mục script", style="Ghost.TButton",
                   command=self._open_scripts).pack(side="right", padx=6)
        self._edit_btns += [b1, b2, b3]

        ttk.Label(root, text="Mẹo: OCR đọc font manga đôi khi sai — mở .json sửa lại 'text' "
                  "cho chuẩn trước khi Render. Bong bóng thoại trắng cho kết quả sạch nhất. "
                  "Cần OpenCV + EasyOCR (đã cài trong venv).",
                  style="Muted.TLabel").pack(anchor="w", **pad)

    def _pick_edit_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get() or str(HERE))
        if d:
            self.ed_path.set(d)

    def _pick_edit_file(self):
        f = filedialog.askopenfilename(
            initialdir=self.outdir.get() or str(HERE),
            filetypes=[("Anh", "*.jpg *.jpeg *.png *.webp"), ("Tat ca", "*.*")])
        if f:
            self.ed_path.set(f)

    def _scripts_dir(self):
        p = Path(self.ed_path.get().strip())
        return p.parent / (p.name + " (scripts)") if p.is_dir() else p.parent

    def _edited_dir(self):
        p = Path(self.ed_path.get().strip())
        return p.parent / (p.name + " (edited)") if p.is_dir() else p.parent

    def _open_scripts(self):
        d = self._scripts_dir()
        if d.exists():
            os.startfile(d)
        else:
            messagebox.showinfo("Chua co", "Chua tao script. Bam '① OCR' truoc.")

    def _open_edited(self):
        d = self._edited_dir()
        if d.exists():
            os.startfile(d)
        else:
            messagebox.showinfo("Chua co", "Chua render. Bam '③ Render' truoc.")

    def start_edit_ocr(self):
        p = self.ed_path.get().strip()
        if not p:
            messagebox.showwarning("Thieu", "Hay chon thu muc chuong hoac 1 anh.")
            return
        path = Path(p)
        cmd = [PY, "manga_translate.py", p, "--lang", self.ed_lang.get()]
        if path.is_dir():
            cmd += ["--out-dir", str(self._scripts_dir())]
        else:
            cmd += ["--out", str(path.with_suffix(".json"))]
        if self.ed_auto.get():
            cmd += ["--auto", "--to", self.ed_to.get().strip() or "vi"]
        self._spawn(cmd, clear=True, status="OCR + tao script...")

    def start_edit_preview(self):
        self._edit_render(preview=True)

    def start_edit_render(self):
        self._edit_render(preview=False)

    def _edit_render(self, preview):
        p = self.ed_path.get().strip()
        if not p:
            messagebox.showwarning("Thieu", "Hay chon thu muc chuong hoac 1 anh.")
            return
        path = Path(p)
        cmd = [PY, "manga_edit.py", p]
        if path.is_dir():
            cmd += ["--scripts-dir", str(self._scripts_dir()),
                    "--out-dir", str(self._edited_dir())]
        else:
            cmd += ["--script", str(path.with_suffix(".json")),
                    "--out", str(self._edited_dir() / (path.stem + "_edit.png"))]
        if preview:
            cmd.append("--preview")
        self._spawn(cmd, clear=True,
                    status="Xem truoc khung..." if preview else "Render (xoa+chen)...")

    def start_edit_cbz(self):
        """Dong goi thu muc '<chuong> (edited)' thanh .cbz."""
        p = self.ed_path.get().strip()
        if not p:
            messagebox.showwarning("Thieu", "Hay chon thu muc chuong hoac 1 anh.")
            return
        ed = self._edited_dir()
        if not ed.exists():
            messagebox.showinfo("Chua co", "Chua render trang nao. Bam '③ Render' truoc.")
            return
        self._spawn([PY, "manga_edit.py", str(ed), "--pack-cbz"], clear=True,
                    status="Dong goi CBZ...")

    def start_box_editor(self):
        """Mo trinh khoanh vung tay (cua so rieng, khong chan GUI chinh)."""
        p = self.ed_path.get().strip()
        if not p:
            messagebox.showwarning("Thieu", "Hay chon thu muc chuong hoac 1 anh.")
            return
        path = Path(p)
        cmd = [PY, "manga_box_editor.py", p]
        if path.is_dir():
            cmd += ["--scripts-dir", str(self._scripts_dir())]
        else:
            cmd += ["--out", str(path.with_suffix(".json"))]
        try:
            subprocess.Popen(cmd, cwd=str(HERE))
            self._log("[Da mo trinh khoanh vung tay - cua so rieng]\n"
                      "Ve o -> go loi thoai -> Luu. Xong quay lai bam '③ Render'.\n")
        except Exception as e:
            messagebox.showerror("Loi", f"Khong mo duoc: {e}")

    # --------------------------------------------------------------- events
    def _on_source_change(self):
        for fr in (self._auto_frame, self._mangadex_frame, self._truyenqq_frame,
                   self._mangafire_frame, self._generic_frame):
            fr.pack_forget()
        s = self.source.get()
        self.btn_check.config(state="normal" if s.startswith("Tu dong") else "disabled")
        if s.startswith("Tu dong"):
            self._auto_frame.pack(fill="x", padx=8, pady=6)
            self.lbl_target.config(text="Link bat ky (bo truyen / 1 chuong):")
            self.hint.config(text="Tool tu nhan dien trang. Vd link truyenqq, mangadex...")
            self.btn_list.config(state="disabled")
            self.btn_chrome.config(state="disabled")
        elif s == "MangaDex":
            self._mangadex_frame.pack(fill="x", padx=8, pady=6)
            self.lbl_target.config(text="Link / ID / 'search:ten':")
            self.hint.config(text="Vd: search:grapara  hoac  https://mangadex.org/title/<id>/...")
            self.btn_list.config(state="normal")
            self.btn_chrome.config(state="disabled")
        elif s.startswith("TruyenQQ"):
            self._truyenqq_frame.pack(fill="x", padx=8, pady=6)
            self.lbl_target.config(text="Link bo truyen / 1 chuong:")
            self.hint.config(text="Vd: https://truyenqqko.com/truyen-tranh/<ten>-<id>")
            self.btn_list.config(state="disabled")
            self.btn_chrome.config(state="disabled")
        elif s.startswith("mangafire"):
            self._mangafire_frame.pack(fill="x", padx=8, pady=6)
            self.lbl_target.config(text="Link bo (/manga/...) hoac 1 chuong (/read/...):")
            self.hint.config(text="Tu mo Chrome that. Vd: https://mangafire.to/manga/grapara.9jlp8")
            self.btn_list.config(state="disabled")
            self.btn_chrome.config(state="normal")
        else:
            self._generic_frame.pack(fill="x", padx=8, pady=6)
            self.lbl_target.config(text="Link bo truyen / 1 chuong:")
            self.hint.config(text="Trang bat ky. Can cai Playwright.")
            self.btn_list.config(state="disabled")
            self.btn_chrome.config(state="disabled")

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get() or str(HERE))
        if d:
            self.outdir.set(d)

    def _open_outdir(self):
        d = self.outdir.get()
        Path(d).mkdir(parents=True, exist_ok=True)
        os.startfile(d)

    def _formats(self):
        fs = []
        if self.f_folder.get():
            fs.append("folder")
        if self.f_cbz.get():
            fs.append("cbz")
        if self.f_pdf.get():
            fs.append("pdf")
        if self.f_stitch.get():
            fs.append("stitch")
        return fs or ["folder"]

    # --------------------------------------------------------------- build cmd
    def _build_cmd(self, action="download"):
        s = self.source.get()
        target = self.target.get().strip()
        out = self.outdir.get().strip() or "downloads"
        fmts = self._formats()

        if s.startswith("Tu dong"):
            if not target:
                raise ValueError("Hay nhap link.")
            cmd = [PY, "auto_dl.py", target, "--out", out]
            if action == "check":
                cmd.append("--check")
            else:
                cmd += ["--format", *fmts]
                r1, r2 = self.auto_r1.get().strip(), self.auto_r2.get().strip()
                if r1 and r2:
                    cmd += ["--range", r1, r2]
                if self.limit.get().strip() not in ("", "0"):
                    cmd += ["--limit", self.limit.get().strip()]
                if not self.auto_browser.get():
                    cmd += ["--browser", "off"]
            return cmd

        if s == "MangaDex":
            if not target:
                raise ValueError("Hay nhap link / ID / 'search:ten'.")
            cmd = [PY, "mangadex_dl.py", target, "--out", out,
                   "--lang", self.lang.get().strip() or "en"]
            if action == "list":
                cmd.append("--list")
            elif action == "langs":
                cmd.append("--langs")
            else:
                cmd += ["--format", *fmts]
                if self.limit.get().strip() not in ("", "0"):
                    cmd += ["--limit", self.limit.get().strip()]
                if self.data_saver.get():
                    cmd.append("--data-saver")
            return cmd

        if s.startswith("TruyenQQ"):
            if not target:
                raise ValueError("Hay nhap link bo truyen hoac 1 chuong.")
            cmd = [PY, "truyenqq_dl.py", target, "--out", out, "--format", *fmts]
            r1, r2 = self.qq_r1.get().strip(), self.qq_r2.get().strip()
            if r1 and r2:
                cmd += ["--range", r1, r2]
            if self.limit.get().strip() not in ("", "0"):
                cmd += ["--limit", self.limit.get().strip()]
            return cmd

        if s.startswith("mangafire"):
            if not target:
                raise ValueError("Hay nhap link bo (/manga/...) hoac 1 chuong (/read/...).")
            cmd = [PY, "mangafire_dl.py", target, "--out", out, "--format", *fmts]
            r1, r2 = self.mf_r1.get().strip(), self.mf_r2.get().strip()
            if r1 and r2:
                cmd += ["--range", r1, r2]
            if self.limit.get().strip() not in ("", "0"):
                cmd += ["--limit", self.limit.get().strip()]
            return cmd

        # Trang bat ky
        if not target:
            raise ValueError("Hay nhap link.")
        cmd = [PY, "manga_dl.py", target, "--out", out, "--format", *fmts,
               "--mode", self.mode.get()]
        if self.limit.get().strip() not in ("", "0"):
            cmd += ["--limit", self.limit.get().strip()]
        if self.headful.get():
            cmd.append("--headful")
        return cmd

    # --------------------------------------------------------------- run
    def start_download(self):
        self._run("download")

    def start_resume(self):
        """Tiep tuc tai sau khi dung dot ngot. Resume la TU DONG: chay lai cung lenh
        tai (cung link + cung thu muc) -> tool bo qua chuong/anh DA CO, tai tiep phan con
        thieu. Nut nay = nut Tai, chi khac thong bao cho ro."""
        self._run("download", status="Dang tiep tuc tu cho da dung...")

    def start_list(self):
        self._run("list")

    def start_langs(self):
        self._run("langs")

    def start_check(self):
        self._run("check")

    def start_upload(self):
        """Mo hop chon bo truyen de day len Drive (khong day het)."""
        self._chain_upload = False
        if self.proc is not None:
            messagebox.showinfo("Dang chay", "Co tac vu dang chay. Cho xong da.")
            return
        out = Path(self.outdir.get().strip() or "downloads")
        if not out.exists():
            messagebox.showwarning("Chua co du lieu",
                                   f"Chua thay thu muc '{out}'.")
            return
        series = sorted([d for d in out.iterdir() if d.is_dir()],
                        key=lambda d: d.name.lower())
        if not series:
            messagebox.showinfo("Trong",
                                f"Khong thay bo truyen nao trong '{out}'.")
            return
        self._upload_dialog(series)

    def _upload_dialog(self, series):
        dlg = tk.Toplevel(self)
        dlg.title("Chon truyen day len Google Drive")
        dlg.configure(bg=BG)
        dlg.geometry("460x420")
        dlg.transient(self)

        ttk.Label(dlg, text="Tích chọn bộ truyện muốn đẩy lên Drive:",
                  style="TLabel").pack(anchor="w", padx=12, pady=(12, 4))
        ttk.Label(dlg, text="(chỉ đẩy thư mục ảnh — tự bỏ qua .cbz/.pdf)",
                  style="Muted.TLabel").pack(anchor="w", padx=12)

        box = tk.Frame(dlg, bg=BG)
        box.pack(fill="both", expand=True, padx=12, pady=8)
        lb = tk.Listbox(box, selectmode="extended", bg=FIELD, fg=TEXT,
                        selectbackground=ACCENT, selectforeground="#fff",
                        relief="flat", highlightthickness=0, activestyle="none",
                        font=(FONT, 10))
        lb.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(box, command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.config(yscrollcommand=sb.set)
        for d in series:
            lb.insert("end", "  " + d.name)
        lb.select_set(0, "end")          # mac dinh chon het, user bo bot

        btns = ttk.Frame(dlg)
        btns.pack(fill="x", padx=12, pady=(0, 12))

        def do_upload():
            idxs = lb.curselection()
            if not idxs:
                messagebox.showinfo("Chua chon", "Hay tich it nhat 1 bo.", parent=dlg)
                return
            chosen = [str(series[i]) for i in idxs]
            dlg.destroy()
            cmd = [PY, "upload_drive.py", *chosen,
                   "--remote", self.gdrive_remote.get().strip() or "drive",
                   "--dest", self.gdrive_dest.get().strip() or "Manga"]
            self._spawn(cmd, clear=False,
                        status=f"Dang day {len(chosen)} bo len Drive...")

        ttk.Button(btns, text="Bỏ chọn hết",
                   command=lambda: lb.select_clear(0, "end")).pack(side="left")
        ttk.Button(btns, text="Hủy", style="Ghost.TButton",
                   command=dlg.destroy).pack(side="right")
        ttk.Button(btns, text="☁ Đẩy lên", style="Accent.TButton",
                   command=do_upload).pack(side="right", padx=6)
        dlg.after(50, lambda: (dlg.lift(), dlg.focus_force()))

    def _run(self, action, status="Dang chay..."):
        try:
            cmd = self._build_cmd(action=action)
        except ValueError as e:
            messagebox.showwarning("Thieu thong tin", str(e))
            return
        # chi tu day len Drive sau khi TAI xong thanh cong
        self._chain_upload = (action == "download" and self.gdrive_up.get())
        self._spawn(cmd, clear=True, status=status)

    def _spawn(self, cmd, clear=True, status="Dang chay..."):
        if self.proc is not None:
            messagebox.showinfo("Dang chay", "Co tac vu dang chay. Bam Dung truoc.")
            return
        if clear:
            self._clear_log()
        self._log("> " + " ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n")
        self.status.set(status)
        self.pb.start(12)
        self.btn_run.config(state="disabled")
        self.btn_resume.config(state="disabled")
        self.btn_list.config(state="disabled")
        self.btn_check.config(state="disabled")
        self.btn_stop.config(state="normal")
        for b in getattr(self, "_edit_btns", []):
            b.config(state="disabled")
        threading.Thread(target=self._worker, args=(cmd,), daemon=True).start()

    def _worker(self, cmd):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=str(HERE), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1, env=env, creationflags=flags)
        except Exception as e:
            self.log_q.put(("line", f"LOI khoi chay: {e}\n"))
            self.log_q.put(("done", -1))
            return
        for line in self.proc.stdout:
            self.log_q.put(("line", line))
        code = self.proc.wait()
        self.log_q.put(("done", code))

    def stop(self):
        """Dung dot ngot: kill ca cay tien trinh (ke ca trinh duyet con) + don file tam."""
        self._chain_upload = False
        if self.proc and self.proc.poll() is None:
            pid = self.proc.pid
            try:
                if os.name == "nt":
                    # /T: kill ca tien trinh con (vd Chromium do Playwright mo)
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                   capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    self.proc.terminate()
            except Exception:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
            self._log("\n[Da dung]\n")
        self._cleanup_temp()

    def _cleanup_temp(self):
        """Xoa cac file tam .part con sot lai khi bi ngat giua chung."""
        out = Path(self.outdir.get().strip() or "downloads")
        n = 0
        if out.exists():
            for f in out.rglob("*.part"):
                try:
                    f.unlink()
                    n += 1
                except OSError:
                    pass
        if n:
            self._log(f"[Da don {n} file tam .part]\n")

    def reset(self):
        """Lam moi de chuyen sang bo/trang khac: dung tac vu, xoa o nhap + log."""
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno(
                    "Dang chay", "Co tac vu dang chay. Dung va lam moi?"):
                return
            self.stop()
        else:
            self._cleanup_temp()
        self.target.set("")
        self.mf_name.set("")
        self.mf_r1.set("")
        self.mf_r2.set("")
        self._clear_log()
        self.status.set("San sang.")
        self.pb.stop()

    # --------------------------------------------------------------- chrome
    def open_debug_chrome(self):
        chrome = find_chrome()
        if not chrome:
            messagebox.showerror("Khong thay Chrome",
                                 "Khong tim thay chrome.exe o thu muc mac dinh.")
            return
        url = self.target.get().strip() or "https://mangafire.to/"
        try:
            subprocess.Popen([chrome, f"--remote-debugging-port={DEBUG_PORT}",
                              f"--user-data-dir={DEBUG_PROFILE}", url])
            self._log(f"[Da mo Chrome go loi cong {DEBUG_PORT}]\n"
                      "Vuot Cloudflare trong cua so do den khi thay anh, roi bam Tai.\n")
        except Exception as e:
            messagebox.showerror("Loi", f"Khong mo duoc Chrome: {e}")

    # --------------------------------------------------------------- log
    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _drain_log(self):
        try:
            while True:
                kind, payload = self.log_q.get_nowait()
                if kind == "line":
                    self._log(payload)
                elif kind == "done":
                    self.pb.stop()
                    self.proc = None
                    self.btn_run.config(state="normal")
                    self.btn_resume.config(state="normal")
                    self.btn_list.config(
                        state="normal" if self.source.get() == "MangaDex" else "disabled")
                    self.btn_check.config(
                        state="normal" if self.source.get().startswith("Tu dong") else "disabled")
                    self.btn_stop.config(state="disabled")
                    for b in getattr(self, "_edit_btns", []):
                        b.config(state="normal")
                    self.status.set("Xong." if payload == 0 else f"Ket thuc (ma {payload}).")
                    # Tai xong thanh cong + co bat -> tu day len Google Drive
                    if payload == 0 and self._chain_upload:
                        self._chain_upload = False
                        self._log("\n--- Tai xong: mo hop chon truyen de day len Drive ---\n")
                        self.after(400, self.start_upload)
        except queue.Empty:
            pass
        self.after(80, self._drain_log)


if __name__ == "__main__":
    App().mainloop()
