# -*- coding: utf-8 -*-
"""
gui.py - Giao diện chuyên nghiệp (Pro Manga Downloader & Studio) cho bộ tool tải & biên tập truyện tranh.

Tính năng:
  [📥 Tải truyện]:
      Hỗ trợ tải từ mọi nguồn: Tự động (auto_dl) / MangaDex (API + DoH) / TruyenQQ /
      MangaFire (Cloudflare CDP) / Trang bất kỳ (Playwright Heuristic).
      Tự động nhận diện nguồn link khi dán, chẩn đoán link, tải resume thông minh.
  [📚 Thư viện]:
      Quản lý các bộ truyện đã tải trong máy, xem số chương, mở thư mục 1 click,
      đóng gói lại CBZ, xuất Excel review hoặc đẩy lên Google Drive.
  [🎨 Studio Biên tập]:
      Quy trình biên tập truyện 4 bước: OCR đa ngôn ngữ -> Bảng khoanh tay trực quan ->
      Render xóa chữ (inpaint) & chèn lời tiếng Việt -> Đóng gói CBZ thành phẩm.
  [🛠 Công cụ mở rộng]:
      Xuất Excel Review có ảnh thumbnail (to_excel.py), ghép cuộn dài Webtoon (pack.py),
      mở Chrome Debugger port 9222 vượt Cloudflare & TeraBox, dọn file tạm .part.
  [🖥 Terminal Log Pro]:
      Console log phân màu cú pháp (Thành công, Lỗi, Cảnh báo, Lệnh), sao chép log,
      theo dõi tiến trình phần trăm thời gian thực.
"""

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

HERE = Path(__file__).resolve().parent
PY = sys.executable  # Trình thông dịch Python hiện tại (venv)

# ==============================================================================
# BẢNG MÀU GIAO DIỆN HIỆN ĐẠI (DARK SLATE & NEON ACCENTS)
# ==============================================================================
BG_APP       = "#0f111a"  # Nền tổng thể
BG_SIDEBAR   = "#141724"  # Thanh bên / Header
BG_CARD      = "#1a1d2e"  # Thẻ chứa nội dung
BG_INNER     = "#21253a"  # Khung con / Fieldset
BG_INPUT     = "#121422"  # Ô nhập liệu
BORDER_COLOR = "#2c324b"  # Đường viền vi tính

TEXT_MAIN    = "#f1f5f9"  # Chữ tiêu đề / chữ chính
TEXT_MUTED   = "#94a3b8"  # Chữ phụ / chú thích
TEXT_DIM     = "#64748b"  # Chữ mờ

ACCENT_BLUE  = "#3b82f6"  # Xanh lam
ACCENT_INDIGO= "#6366f1"  # Tím indigo chủ đạo
ACCENT_CYAN  = "#06b6d4"  # Xanh ngọc neon
ACCENT_GREEN = "#10b981"  # Xanh lá - Tải / Hoàn thành
GREEN_HOVER  = "#059669"
ACCENT_RED   = "#f43f5e"  # Đỏ - Dừng / Lỗi
RED_HOVER    = "#e11d48"
ACCENT_AMBER = "#f59e0b"  # Cam - Cảnh báo / Resume
ACCENT_PURPLE= "#a855f7"  # Tím Studio

LOG_BG       = "#0b0d14"  # Nền Terminal
LOG_FG       = "#cbd5e1"  # Chữ Terminal

FONT_NAME    = "Segoe UI"
FONT_MONO    = "Consolas"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]
DEBUG_PROFILE = r"C:\chrome-debug-profile"
DEBUG_PORT = "9222"


def find_chrome():
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def format_size(bytes_num):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_num < 1024.0:
            return f"{bytes_num:.1f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.1f} PB"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Manga Downloader Pro — Bộ công cụ Tải & Biên tập Truyện tranh")
        self.geometry("1060x780")
        self.minsize(880, 660)
        self.configure(bg=BG_APP)

        self.proc = None
        self.log_q = queue.Queue()
        self._chain_upload = False

        self._setup_style()
        self._build_ui()
        self._on_source_change()

        # Timer vòng lặp cập nhật
        self.after(60, self._drain_log)
        self.after(100, self._bring_front)

        # Quét thư viện lần đầu
        self.after(500, self._refresh_library)

    def _setup_style(self):
        st = ttk.Style(self)
        st.theme_use("clam")

        # Cấu hình gốc
        st.configure(".", background=BG_APP, foreground=TEXT_MAIN,
                     fieldbackground=BG_INPUT, bordercolor=BORDER_COLOR,
                     lightcolor=BORDER_COLOR, darkcolor=BORDER_COLOR,
                     font=(FONT_NAME, 10))

        st.configure("TFrame", background=BG_APP)
        st.configure("Card.TFrame", background=BG_CARD)
        st.configure("Inner.TFrame", background=BG_INNER)

        st.configure("TLabel", background=BG_APP, foreground=TEXT_MAIN)
        st.configure("Card.TLabel", background=BG_CARD, foreground=TEXT_MAIN)
        st.configure("Inner.TLabel", background=BG_INNER, foreground=TEXT_MAIN)

        st.configure("Header.TLabel", background=BG_SIDEBAR, foreground=TEXT_MAIN,
                     font=(FONT_NAME, 15, "bold"))
        st.configure("HeaderSub.TLabel", background=BG_SIDEBAR, foreground=TEXT_MUTED,
                     font=(FONT_NAME, 9))

        st.configure("Section.TLabel", background=BG_CARD, foreground=ACCENT_CYAN,
                     font=(FONT_NAME, 11, "bold"))
        st.configure("Muted.TLabel", background=BG_APP, foreground=TEXT_MUTED,
                     font=(FONT_NAME, 9))
        st.configure("CardMuted.TLabel", background=BG_CARD, foreground=TEXT_MUTED,
                     font=(FONT_NAME, 9))
        st.configure("Badge.TLabel", background=BG_INNER, foreground=ACCENT_AMBER,
                     font=(FONT_NAME, 9, "bold"), padding=(6, 2))

        # Khung viền LabelFrame
        st.configure("TLabelframe", background=BG_CARD, bordercolor=BORDER_COLOR, relief="solid")
        st.configure("TLabelframe.Label", background=BG_CARD, foreground=ACCENT_CYAN,
                     font=(FONT_NAME, 10, "bold"))

        # Radio & Checkbutton
        st.configure("TRadiobutton", background=BG_CARD, foreground=TEXT_MAIN)
        st.map("TRadiobutton",
               foreground=[("selected", ACCENT_CYAN), ("active", "#ffffff")],
               background=[("active", BG_CARD)])

        st.configure("TCheckbutton", background=BG_CARD, foreground=TEXT_MAIN)
        st.map("TCheckbutton",
               foreground=[("selected", ACCENT_CYAN), ("active", "#ffffff")],
               background=[("active", BG_CARD)])

        # Entry & Combobox
        st.configure("TEntry", fieldbackground=BG_INPUT, foreground=TEXT_MAIN,
                     insertcolor=TEXT_MAIN, bordercolor=BORDER_COLOR, padding=6)
        st.map("TEntry", bordercolor=[("focus", ACCENT_INDIGO)])

        st.configure("TCombobox", fieldbackground=BG_INPUT, foreground=TEXT_MAIN,
                     background=BG_INNER, arrowcolor=TEXT_MAIN, bordercolor=BORDER_COLOR, padding=5)

        # Progressbar
        st.configure("TProgressbar", background=ACCENT_CYAN, troughcolor=BG_INPUT,
                     bordercolor=BG_APP, lightcolor=ACCENT_CYAN, darkcolor=ACCENT_CYAN)

        # Notebook tabs
        st.configure("TNotebook", background=BG_APP, bordercolor=BORDER_COLOR, tabmargins=[6, 4, 6, 0])
        st.configure("TNotebook.Tab", background=BG_SIDEBAR, foreground=TEXT_MUTED,
                     padding=(16, 8), font=(FONT_NAME, 10, "bold"), bordercolor=BORDER_COLOR)
        st.map("TNotebook.Tab",
               background=[("selected", BG_CARD), ("active", BG_INNER)],
               foreground=[("selected", ACCENT_CYAN), ("active", TEXT_MAIN)])

        # Treeview (Bảng thư viện)
        st.configure("Treeview", background=BG_CARD, foreground=TEXT_MAIN,
                     fieldbackground=BG_CARD, bordercolor=BORDER_COLOR,
                     rowheight=28, font=(FONT_NAME, 9))
        st.configure("Treeview.Heading", background=BG_INNER, foreground=ACCENT_CYAN,
                     relief="flat", font=(FONT_NAME, 9, "bold"), padding=6)
        st.map("Treeview", background=[("selected", ACCENT_INDIGO)],
               foreground=[("selected", "#ffffff")])

        # Button styles
        st.configure("TButton", background=BG_INNER, foreground=TEXT_MAIN, bordercolor=BORDER_COLOR,
                     relief="flat", padding=(10, 6), font=(FONT_NAME, 9, "bold"))
        st.map("TButton",
               background=[("active", "#2e3452"), ("disabled", "#191c2b")],
               foreground=[("disabled", TEXT_DIM)])

        # Nút Tải chính (Emerald Green)
        st.configure("Primary.TButton", background=ACCENT_GREEN, foreground="#042115",
                     font=(FONT_NAME, 10, "bold"), padding=(14, 8))
        st.map("Primary.TButton",
               background=[("active", GREEN_HOVER), ("disabled", "#173829")],
               foreground=[("disabled", "#44705c")])

        # Nút Dừng (Rose Red)
        st.configure("Danger.TButton", background=ACCENT_RED, foreground="#ffffff",
                     font=(FONT_NAME, 9, "bold"), padding=(10, 6))
        st.map("Danger.TButton",
               background=[("active", RED_HOVER), ("disabled", "#3b1e25")],
               foreground=[("disabled", "#75454e")])

        # Nút Chẩn đoán / Nổi bật (Indigo/Cyan)
        st.configure("Accent.TButton", background=ACCENT_INDIGO, foreground="#ffffff",
                     font=(FONT_NAME, 9, "bold"), padding=(10, 6))
        st.map("Accent.TButton",
               background=[("active", "#4f46e5"), ("disabled", "#292a4a")],
               foreground=[("disabled", "#5e608a")])

        # Nút Nhẹ nhàng (Ghost)
        st.configure("Ghost.TButton", background=BG_CARD, foreground=TEXT_MUTED,
                     bordercolor=BORDER_COLOR, font=(FONT_NAME, 9))
        st.map("Ghost.TButton",
               background=[("active", BG_INNER)],
               foreground=[("active", TEXT_MAIN)])

    def _bring_front(self):
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.after(600, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    # ==============================================================================
    # KHỞI DỰNG GIAO DIỆN CHÍNH
    # ==============================================================================
    def _build_ui(self):
        # 1. TOP HEADER BAR
        self._build_header()

        # 2. MAIN TABS NOTEBOOK
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(6, 4))

        # Tab 1: Tải truyện
        self.tab_dl = ttk.Frame(self.nb)
        self.nb.add(self.tab_dl, text="  📥  TẢI TRUYỆN (DOWNLOADER)  ")
        self._build_download_tab(self.tab_dl)

        # Tab 2: Thư viện
        self.tab_lib = ttk.Frame(self.nb)
        self.nb.add(self.tab_lib, text="  📚  THƯ VIỆN ĐÃ TẢI (LIBRARY)  ")
        self._build_library_tab(self.tab_lib)

        # Tab 3: Studio biên tập
        self.tab_edit = ttk.Frame(self.nb)
        self.nb.add(self.tab_edit, text="  🎨  STUDIO BIÊN TẬP & DỊCH  ")
        self._build_edit_tab(self.tab_edit)

        # Tab 4: Công cụ mở rộng
        self.tab_tools = ttk.Frame(self.nb)
        self.nb.add(self.tab_tools, text="  🛠  CÔNG CỤ NÂNG CAO (TOOLS)  ")
        self._build_tools_tab(self.tab_tools)

        # 3. BOTTOM CONSOLE & METRICS
        self._build_console()

    def _build_header(self):
        h_frame = tk.Frame(self, bg=BG_SIDEBAR, height=52)
        h_frame.pack(fill="x", side="top", padx=0, pady=0)

        # Tiêu đề & Logo
        left = tk.Frame(h_frame, bg=BG_SIDEBAR)
        left.pack(side="left", padx=14, pady=8)

        lbl_logo = tk.Label(left, text="⚡ MANGA PRO DL", font=(FONT_NAME, 13, "bold"),
                            bg=BG_SIDEBAR, fg=ACCENT_CYAN)
        lbl_logo.pack(side="left")

        lbl_ver = tk.Label(left, text="v2.5 Professional Archiver & Studio",
                           font=(FONT_NAME, 9), bg=BG_SIDEBAR, fg=TEXT_MUTED)
        lbl_ver.pack(side="left", padx=(10, 0), pady=(2, 0))

        # Thanh trạng thái động (Status Pill Badge) & Nút nhanh
        right = tk.Frame(h_frame, bg=BG_SIDEBAR)
        right.pack(side="right", padx=14, pady=8)

        self.lbl_engine_pill = tk.Label(right, text="● SẴN SÀNG", font=(FONT_NAME, 9, "bold"),
                                        bg=BG_INNER, fg=ACCENT_GREEN, padx=10, pady=4)
        self.lbl_engine_pill.pack(side="left", padx=(0, 10))

        ttk.Button(right, text="📂 Thư mục tải", style="Ghost.TButton",
                   command=self._open_outdir).pack(side="left", padx=3)
        ttk.Button(right, text="🌐 Chrome CDP", style="Ghost.TButton",
                   command=self.open_debug_chrome).pack(side="left", padx=3)
        ttk.Button(right, text="↻ Làm mới", style="Ghost.TButton",
                   command=self.reset).pack(side="left", padx=3)

    # ==============================================================================
    # TAB 1: TẢI TRUYỆN (DOWNLOADER)
    # ==============================================================================
    def _build_download_tab(self, root):
        pad = {"padx": 10, "pady": 4}

        # --- Card 1: Nhập link & Auto Detection ---
        card_input = ttk.LabelFrame(root, text=" 🎯 Nhập Link Truyện Tranh ")
        card_input.pack(fill="x", **pad)

        row_target = ttk.Frame(card_input)
        row_target.pack(fill="x", padx=10, pady=(8, 4))

        self.lbl_target = ttk.Label(row_target, text="Link / ID truyện:",
                                    font=(FONT_NAME, 9, "bold"))
        self.lbl_target.pack(side="left")

        # Badge tự động nhận dạng site
        self.site_badge = tk.Label(row_target, text="[Chế độ: Tự động phát hiện]",
                                   font=(FONT_NAME, 8, "bold"), bg=BG_INNER, fg=ACCENT_CYAN,
                                   padx=6, pady=2)
        self.site_badge.pack(side="left", padx=10)

        # Hàng Entry + Nút Paste / Clear
        inp_box = ttk.Frame(card_input)
        inp_box.pack(fill="x", padx=10, pady=(0, 6))

        self.target = tk.StringVar()
        self.target.trace_add("write", self._on_target_typed)

        self.entry_target = ttk.Entry(inp_box, textvariable=self.target, font=(FONT_NAME, 10))
        self.entry_target.pack(side="left", fill="x", expand=True, ipady=3)

        ttk.Button(inp_box, text="📋 Dán", width=5, command=self._paste_target).pack(
            side="left", padx=(6, 2))
        ttk.Button(inp_box, text="✖ Xóa", width=5, style="Ghost.TButton",
                   command=lambda: self.target.set("")).pack(side="left", padx=2)

        self.hint = ttk.Label(card_input, text="Dán bất kỳ link manga, manhwa, manhua (TruyenQQ, MangaDex, MangaFire, ToonGod, Webtoon...)",
                              style="CardMuted.TLabel")
        self.hint.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Card 2: Chọn nguồn tải (Engine Selector) ---
        card_engine = ttk.LabelFrame(root, text=" ⚙ Bộ máy Tải (Engine) ")
        card_engine.pack(fill="x", **pad)

        engine_box = ttk.Frame(card_engine)
        engine_box.pack(fill="x", padx=10, pady=6)

        self.source = tk.StringVar(value="Tu dong (moi trang)")
        sources = [
            ("⭐ Tự động chẩn đoán (auto_dl)", "Tu dong (moi trang)"),
            ("🌐 MangaDex (API + DoH 1.1.1.1)", "MangaDex"),
            ("⚡ TruyenQQ / NetTruyen (VN)", "TruyenQQ/NetTruyen (VN)"),
            ("🛡 MangaFire (Cloudflare CDP)", "mangafire (Cloudflare)"),
            ("🎭 Quét toàn diện (Playwright)", "Trang bat ky"),
        ]
        for i, (label, val) in enumerate(sources):
            ttk.Radiobutton(engine_box, text=label, value=val, variable=self.source,
                            command=self._on_source_change).grid(
                row=i // 3, column=i % 3, padx=8, pady=4, sticky="w")

        # Khung tùy chọn đặc thù theo Engine
        self.opt_container = ttk.Frame(card_engine)
        self.opt_container.pack(fill="x", padx=10, pady=(4, 8))

        self.lang = tk.StringVar(value="en")
        self.limit = tk.StringVar(value="0")
        self.data_saver = tk.BooleanVar(value=False)
        self.mf_name = tk.StringVar(value="")
        self.mf_r1 = tk.StringVar(value="")
        self.mf_r2 = tk.StringVar(value="")
        self.auto_r1 = tk.StringVar(value="")
        self.auto_r2 = tk.StringVar(value="")
        self.auto_browser = tk.BooleanVar(value=True)
        self.qq_r1 = tk.StringVar(value="")
        self.qq_r2 = tk.StringVar(value="")
        self.mode = tk.StringVar(value="auto")
        self.headful = tk.BooleanVar(value=False)

        self._auto_frame = self._make_auto_opts()
        self._mangadex_frame = self._make_mangadex_opts()
        self._truyenqq_frame = self._make_truyenqq_opts()
        self._mangafire_frame = self._make_mangafire_opts()
        self._generic_frame = self._make_generic_opts()

        # --- Card 3: Định dạng xuất & Thư mục lưu ---
        card_out = ttk.LabelFrame(root, text=" 📦 Định dạng & Lưu trữ ")
        card_out.pack(fill="x", **pad)

        row_fmt = ttk.Frame(card_out)
        row_fmt.pack(fill="x", padx=10, pady=(6, 4))

        ttk.Label(row_fmt, text="Định dạng xuất:", font=(FONT_NAME, 9, "bold")).pack(side="left")
        self.f_folder = tk.BooleanVar(value=True)
        self.f_cbz = tk.BooleanVar(value=True)
        self.f_pdf = tk.BooleanVar(value=False)
        self.f_stitch = tk.BooleanVar(value=False)

        ttk.Checkbutton(row_fmt, text="📁 Thư mục ảnh", variable=self.f_folder).pack(side="left", padx=10)
        ttk.Checkbutton(row_fmt, text="📚 File CBZ (Chuẩn đọc)", variable=self.f_cbz).pack(side="left", padx=10)
        ttk.Checkbutton(row_fmt, text="📄 File PDF", variable=self.f_pdf).pack(side="left", padx=10)
        ttk.Checkbutton(row_fmt, text="📜 Ghép cuộn dài (Stitch)", variable=self.f_stitch).pack(side="left", padx=10)

        row_dir = ttk.Frame(card_out)
        row_dir.pack(fill="x", padx=10, pady=(4, 6))

        ttk.Label(row_dir, text="Thư mục tải:", font=(FONT_NAME, 9, "bold")).pack(side="left")
        self.outdir = tk.StringVar(value=str(HERE / "downloads"))
        ttk.Entry(row_dir, textvariable=self.outdir).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row_dir, text="Chọn...", width=8, command=self._pick_dir).pack(side="left", padx=2)
        ttk.Button(row_dir, text="📂 Mở", width=6, style="Ghost.TButton",
                   command=self._open_outdir).pack(side="left", padx=2)

        # Tùy chọn Google Drive
        row_gdrive = ttk.Frame(card_out)
        row_gdrive.pack(fill="x", padx=10, pady=(0, 6))

        self.gdrive_up = tk.BooleanVar(value=False)
        self.gdrive_remote = tk.StringVar(value="drive")
        self.gdrive_dest = tk.StringVar(value="Manga")

        ttk.Checkbutton(row_gdrive, text="☁ Tự động hỏi đẩy lên Drive khi tải xong",
                        variable=self.gdrive_up).pack(side="left")
        ttk.Label(row_gdrive, text="Remote:", style="CardMuted.TLabel").pack(side="left", padx=(12, 4))
        ttk.Entry(row_gdrive, textvariable=self.gdrive_remote, width=8).pack(side="left")
        ttk.Label(row_gdrive, text="Thư mục:", style="CardMuted.TLabel").pack(side="left", padx=(8, 4))
        ttk.Entry(row_gdrive, textvariable=self.gdrive_dest, width=10).pack(side="left")

        # --- Card 4: Thanh nút Hành động Chính ---
        card_actions = tk.Frame(root, bg=BG_APP)
        card_actions.pack(fill="x", padx=10, pady=(8, 2))

        self.btn_run = ttk.Button(card_actions, text="▶  BẮT ĐẦU TẢI",
                                  style="Primary.TButton", command=self.start_download)
        self.btn_run.pack(side="left", padx=(0, 6))

        self.btn_check = ttk.Button(card_actions, text="🔍 Chẩn đoán",
                                    style="Accent.TButton", command=self.start_check)
        self.btn_check.pack(side="left", padx=4)

        self.btn_resume = ttk.Button(card_actions, text="⏩ Tiếp tục (Resume)",
                                     command=self.start_resume)
        self.btn_resume.pack(side="left", padx=4)

        self.btn_list = ttk.Button(card_actions, text="📋 Liệt kê chương",
                                   command=self.start_list)
        self.btn_list.pack(side="left", padx=4)

        self.btn_chrome = ttk.Button(card_actions, text="🌐 Chrome gỡ lỗi",
                                     command=self.open_debug_chrome)
        self.btn_chrome.pack(side="left", padx=4)

        self.btn_stop = ttk.Button(card_actions, text="■  Dừng",
                                   style="Danger.TButton", command=self.stop, state="disabled")
        self.btn_stop.pack(side="right", padx=(6, 0))

    def _make_auto_opts(self):
        f = ttk.Frame(self.opt_container)
        ttk.Label(f, text="Dãy chương (từ - đến):").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.auto_r1, width=7).grid(row=0, column=1, padx=4)
        ttk.Entry(f, textvariable=self.auto_r2, width=7).grid(row=0, column=2, padx=4)

        ttk.Label(f, text="Giới hạn (0 = hết):").grid(row=0, column=3, sticky="w", padx=(14, 0))
        ttk.Entry(f, textvariable=self.limit, width=6).grid(row=0, column=4, padx=4)

        ttk.Checkbutton(f, text="Dự phòng trình duyệt (Playwright/CDP) khi gặp JavaScript/Cloudflare",
                        variable=self.auto_browser).grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))
        return f

    def _make_mangadex_opts(self):
        f = ttk.Frame(self.opt_container)
        ttk.Label(f, text="Ngôn ngữ:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.lang, width=6).grid(row=0, column=1, padx=4)

        ttk.Label(f, text="Giới hạn chương:").grid(row=0, column=2, sticky="w", padx=(14, 0))
        ttk.Entry(f, textvariable=self.limit, width=6).grid(row=0, column=3, padx=4)

        ttk.Checkbutton(f, text="Ảnh nén tiết kiệm (data-saver)",
                        variable=self.data_saver).grid(row=0, column=4, padx=(14, 0))
        ttk.Button(f, text="Kiểm tra ngôn ngữ", command=self.start_langs).grid(
            row=0, column=5, padx=(14, 0))
        return f

    def _make_truyenqq_opts(self):
        f = ttk.Frame(self.opt_container)
        ttk.Label(f, text="Dãy chương (từ - đến):").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.qq_r1, width=7).grid(row=0, column=1, padx=4)
        ttk.Entry(f, textvariable=self.qq_r2, width=7).grid(row=0, column=2, padx=4)

        ttk.Label(f, text="Giới hạn chương:").grid(row=0, column=3, sticky="w", padx=(14, 0))
        ttk.Entry(f, textvariable=self.limit, width=6).grid(row=0, column=4, padx=4)
        return f

    def _make_mangafire_opts(self):
        f = ttk.Frame(self.opt_container)
        ttk.Label(f, text="Tên bộ:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.mf_name, width=16).grid(row=0, column=1, padx=4)

        ttk.Label(f, text="Dãy chương:").grid(row=0, column=2, sticky="w", padx=(14, 0))
        ttk.Entry(f, textvariable=self.mf_r1, width=6).grid(row=0, column=3, padx=2)
        ttk.Entry(f, textvariable=self.mf_r2, width=6).grid(row=0, column=4, padx=2)

        ttk.Label(f, text="Yêu cầu: Bấm 'Chrome gỡ lỗi' vượt Cloudflare trước",
                  style="CardMuted.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))
        return f

    def _make_generic_opts(self):
        f = ttk.Frame(self.opt_container)
        ttk.Label(f, text="Chế độ quét:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.mode, width=9, state="readonly",
                     values=["auto", "series", "chapter"]).grid(row=0, column=1, padx=4)

        ttk.Label(f, text="Giới hạn:").grid(row=0, column=2, sticky="w", padx=(14, 0))
        ttk.Entry(f, textvariable=self.limit, width=6).grid(row=0, column=3, padx=4)

        ttk.Checkbutton(f, text="Hiện cửa sổ Chromium thật (Headful)",
                        variable=self.headful).grid(row=0, column=4, padx=(14, 0))
        return f

    def _paste_target(self):
        try:
            txt = self.clipboard_get().strip()
            if txt:
                self.target.set(txt)
        except Exception:
            pass

    def _on_target_typed(self, *args):
        url = self.target.get().strip().lower()
        if not url:
            self.site_badge.config(text="[Chế độ: Tự động phát hiện]", fg=ACCENT_CYAN)
            return

        if "mangadex.org" in url or url.startswith("search:"):
            self.site_badge.config(text="[MangaDex API]", fg=ACCENT_GREEN)
            if self.source.get() != "MangaDex":
                self.source.set("MangaDex")
                self._on_source_change()
        elif "truyenqq" in url or "nettruyen" in url:
            self.site_badge.config(text="[TruyenQQ / NetTruyen]", fg=ACCENT_GREEN)
            if not self.source.get().startswith("TruyenQQ"):
                self.source.set("TruyenQQ/NetTruyen (VN)")
                self._on_source_change()
        elif "mangafire" in url:
            self.site_badge.config(text="[MangaFire CDP]", fg=ACCENT_AMBER)
            if not self.source.get().startswith("mangafire"):
                self.source.set("mangafire (Cloudflare)")
                self._on_source_change()
        elif "toongod" in url:
            self.site_badge.config(text="[ToonGod (Cloudflare)]", fg=ACCENT_AMBER)
        elif "webtoons.com" in url:
            self.site_badge.config(text="[Webtoons Naver]", fg=ACCENT_CYAN)
        elif "terabox" in url or "1024tera" in url:
            self.site_badge.config(text="[TeraBox Cloud]", fg=ACCENT_PURPLE)
        else:
            self.site_badge.config(text="[Auto DL - Mọi Trang]", fg=ACCENT_CYAN)

    # ==============================================================================
    # TAB 2: THƯ VIỆN ĐÃ TẢI (LIBRARY MANAGER)
    # ==============================================================================
    def _build_library_tab(self, root):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(root)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="📂 Danh sách truyện đã tải trong thư mục:",
                  font=(FONT_NAME, 10, "bold")).pack(side="left")

        ttk.Button(top, text="↻ Quét lại thư viện", style="Accent.TButton",
                   command=self._refresh_library).pack(side="right")
        ttk.Button(top, text="📁 Mở thư mục chứa", style="Ghost.TButton",
                   command=self._open_outdir).pack(side="right", padx=6)

        # Bảng Treeview
        tree_frame = ttk.Frame(root)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        cols = ("name", "chapters", "cbz", "pdf", "size", "modified")
        self.lib_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.lib_tree.heading("name", text="Tên bộ truyện")
        self.lib_tree.heading("chapters", text="Số chương")
        self.lib_tree.heading("cbz", text="CBZ")
        self.lib_tree.heading("pdf", text="PDF")
        self.lib_tree.heading("size", text="Dung lượng")
        self.lib_tree.heading("modified", text="Lần sửa cuối")

        self.lib_tree.column("name", width=340, anchor="w")
        self.lib_tree.column("chapters", width=90, anchor="center")
        self.lib_tree.column("cbz", width=80, anchor="center")
        self.lib_tree.column("pdf", width=80, anchor="center")
        self.lib_tree.column("size", width=110, anchor="center")
        self.lib_tree.column("modified", width=140, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.lib_tree.yview)
        self.lib_tree.configure(yscrollcommand=sb.set)
        self.lib_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.lib_tree.bind("<Double-1>", lambda e: self._open_selected_series_dir())

        # Action toolbar cho thư viện
        act = ttk.Frame(root)
        act.pack(fill="x", padx=10, pady=(0, 8))

        ttk.Button(act, text="📂 Mở thư mục truyện", command=self._open_selected_series_dir).pack(side="left", padx=2)
        ttk.Button(act, text="📦 Đóng gói lại thành CBZ", command=self._pack_selected_series_cbz).pack(side="left", padx=4)
        ttk.Button(act, text="📊 Xuất Excel Review", command=self._excel_selected_series).pack(side="left", padx=4)
        ttk.Button(act, text="☁ Đẩy bộ này lên Drive", style="Ghost.TButton",
                   command=self._upload_selected_series).pack(side="left", padx=4)
        ttk.Button(act, text="🧹 Dọn file .part dở dang", style="Ghost.TButton",
                   command=self._cleanup_temp).pack(side="right", padx=2)

    def _refresh_library(self):
        for item in self.lib_tree.get_children():
            self.lib_tree.delete(item)

        out = Path(self.outdir.get().strip() or str(HERE / "downloads"))
        if not out.exists():
            return

        series_dirs = sorted([d for d in out.iterdir() if d.is_dir()],
                             key=lambda d: d.name.lower())

        for d in series_dirs:
            chapters = [c for c in d.iterdir() if c.is_dir() and not c.name.endswith("(scripts)") and not c.name.endswith("(edited)")]
            cbzs = list(d.glob("*.cbz"))
            pdfs = list(d.glob("*.pdf"))

            # Tính sơ bộ dung lượng
            total_size = 0
            for root, _, files in os.walk(d):
                for f in files:
                    try:
                        total_size += (Path(root) / f).stat().st_size
                    except OSError:
                        pass

            try:
                mtime = datetime.fromtimestamp(d.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            except Exception:
                mtime = "N/A"

            self.lib_tree.insert("", "end", values=(
                d.name,
                f"{len(chapters)} chương",
                f"{len(cbzs)} file" if cbzs else "—",
                f"{len(pdfs)} file" if pdfs else "—",
                format_size(total_size),
                mtime
            ))

    def _get_selected_series_path(self):
        sel = self.lib_tree.selection()
        if not sel:
            messagebox.showinfo("Chưa chọn", "Hãy nhấp chọn một bộ truyện trong bảng.")
            return None
        item = self.lib_tree.item(sel[0])
        name = item["values"][0]
        out = Path(self.outdir.get().strip() or str(HERE / "downloads"))
        target = out / name
        if not target.exists():
            messagebox.showwarning("Không tìm thấy", f"Thư mục '{name}' không tồn tại.")
            return None
        return target

    def _open_selected_series_dir(self):
        p = self._get_selected_series_path()
        if p:
            os.startfile(p)

    def _pack_selected_series_cbz(self):
        p = self._get_selected_series_path()
        if not p:
            return
        # Tìm các thư mục chương chưa có file .cbz tương ứng
        chaps = [d for d in p.iterdir() if d.is_dir() and not d.name.endswith("(scripts)") and not d.name.endswith("(edited)")]
        if not chaps:
            messagebox.showinfo("Trống", "Không tìm thấy thư mục chương nào trong bộ này.")
            return

        cmd = [PY, "-c",
               f"from truyenqq_dl import make_cbz; from pathlib import Path; "
               f"p = Path(r'{p}'); "
               f"[make_cbz(list(c.glob('*.*')), c.parent / (c.name + '.cbz')) for c in p.iterdir() if c.is_dir()]"]
        self._spawn(cmd, clear=True, status=f"Đang đóng gói CBZ cho bộ '{p.name}'...")

    def _excel_selected_series(self):
        p = self._get_selected_series_path()
        if not p:
            return
        chaps = sorted([d for d in p.iterdir() if d.is_dir() and not d.name.endswith("(scripts)") and not d.name.endswith("(edited)")])
        if not chaps:
            messagebox.showinfo("Trống", "Bộ truyện chưa có chương nào để xuất Excel.")
            return
        # Chọn chương đầu tiên hoặc hỏi
        first_ch = chaps[0]
        cmd = [PY, "to_excel.py", str(first_ch), "--title", f"{p.name} - {first_ch.name}"]
        self._spawn(cmd, clear=True, status=f"Xuất Excel Review cho '{first_ch.name}'...")

    def _upload_selected_series(self):
        p = self._get_selected_series_path()
        if not p:
            return
        cmd = [PY, "upload_drive.py", str(p),
               "--remote", self.gdrive_remote.get().strip() or "drive",
               "--dest", self.gdrive_dest.get().strip() or "Manga"]
        self._spawn(cmd, clear=True, status=f"Đang đẩy bộ '{p.name}' lên Google Drive...")

    # ==============================================================================
    # TAB 3: STUDIO BIÊN TẬP & DỊCH (MANGA STUDIO)
    # ==============================================================================
    def _build_edit_tab(self, root):
        pad = {"padx": 10, "pady": 5}
        self.ed_path = tk.StringVar()
        self.ed_lang = tk.StringVar(value="ja")
        self.ed_to = tk.StringVar(value="vi")
        self.ed_auto = tk.BooleanVar(value=False)

        # Header hướng dẫn quy trình
        card_guide = ttk.LabelFrame(root, text=" 📖 Quy trình dịch & Biên tập truyện 4 bước ")
        card_guide.pack(fill="x", **pad)

        ttk.Label(card_guide, text="① OCR tạo Script  ➔  ② Khoanh vùng & Dịch thoại  ➔  ③ Render xóa chữ & chèn lời  ➔  ④ Đóng gói CBZ",
                  font=(FONT_NAME, 9, "bold"), foreground=ACCENT_CYAN).pack(anchor="w", padx=10, pady=(6, 2))
        ttk.Label(card_guide, text="Sử dụng OpenCV Content-aware Inpainting để làm sạch bong bóng thoại và EasyOCR đa ngôn ngữ offline.",
                  style="CardMuted.TLabel").pack(anchor="w", padx=10, pady=(0, 6))

        # Chọn tệp nguồn
        card_file = ttk.LabelFrame(root, text=" 📁 Bước 1: Chọn Chương hoặc Trang ảnh nguồn ")
        card_file.pack(fill="x", **pad)

        p = ttk.Frame(card_file)
        p.pack(fill="x", padx=10, pady=8)
        ttk.Label(p, text="Đường dẫn nguồn:", font=(FONT_NAME, 9, "bold")).pack(side="left")
        ttk.Entry(p, textvariable=self.ed_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(p, text="📁 Chọn Thư mục", command=self._pick_edit_dir).pack(side="left", padx=2)
        ttk.Button(p, text="🖼 Chọn Ảnh lẻ", command=self._pick_edit_file).pack(side="left", padx=2)

        # Cấu hình OCR & Dịch thuật
        card_trans = ttk.LabelFrame(root, text=" 🌐 Bước 2: Thiết lập OCR & Ngôn ngữ dịch ")
        card_trans.pack(fill="x", **pad)

        row_t = ttk.Frame(card_trans)
        row_t.pack(fill="x", padx=10, pady=8)

        ttk.Label(row_t, text="Ngôn ngữ gốc:", font=(FONT_NAME, 9, "bold")).pack(side="left")
        ttk.Combobox(row_t, textvariable=self.ed_lang, width=9, state="readonly",
                     values=["ja", "ko", "ch_sim", "ch_tra", "en", "vi"]).pack(side="left", padx=6)

        ttk.Checkbutton(row_t, text="🤖 Tự động dịch máy (Argos/Google)",
                        variable=self.ed_auto).pack(side="left", padx=(14, 4))
        ttk.Label(row_t, text="Sang:").pack(side="left")
        ttk.Entry(row_t, textvariable=self.ed_to, width=6).pack(side="left", padx=4)

        ttk.Label(card_trans, text="(Nếu bỏ chọn 'Tự động dịch': Tool chỉ OCR lấy khung; bạn có thể khoanh sửa tay hoặc chỉnh file .json rồi Render)",
                  style="CardMuted.TLabel").pack(anchor="w", padx=10, pady=(0, 6))

        # Bộ phím hành động Studio
        card_studio_act = ttk.LabelFrame(root, text=" 🎨 Bước 3 & 4: Bộ công cụ Thao tác ")
        card_studio_act.pack(fill="x", **pad)

        a = ttk.Frame(card_studio_act)
        a.pack(fill="x", padx=10, pady=8)

        b1 = ttk.Button(a, text="①  🔍 OCR → Tạo Script", command=self.start_edit_ocr)
        b1.pack(side="left", padx=2)

        ttk.Button(a, text="✎ Mở Bảng Khoanh Tay (Box Editor)", style="Accent.TButton",
                   command=self.start_box_editor).pack(side="left", padx=4)

        b2 = ttk.Button(a, text="②  👁 Xem trước Khung", command=self.start_edit_preview)
        b2.pack(side="left", padx=4)

        b3 = ttk.Button(a, text="③  ✏️ Render (Xóa + Chèn chữ)", style="Primary.TButton",
                        command=self.start_edit_render)
        b3.pack(side="left", padx=4)

        b4 = ttk.Button(a, text="④  📦 Đóng gói CBZ", command=self.start_edit_cbz)
        b4.pack(side="left", padx=4)

        self._edit_btns = [b1, b2, b3, b4]

        # Nút mở thư mục kết quả
        res_row = ttk.Frame(card_studio_act)
        res_row.pack(fill="x", padx=10, pady=(0, 8))

        ttk.Button(res_row, text="📂 Mở thư mục Ảnh Đã Sửa", style="Ghost.TButton",
                   command=self._open_edited).pack(side="left", padx=2)
        ttk.Button(res_row, text="📝 Mở thư mục Script JSON", style="Ghost.TButton",
                   command=self._open_scripts).pack(side="left", padx=4)

    def _pick_edit_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get() or str(HERE))
        if d:
            self.ed_path.set(d)

    def _pick_edit_file(self):
        f = filedialog.askopenfilename(
            initialdir=self.outdir.get() or str(HERE),
            filetypes=[("Ảnh", "*.jpg *.jpeg *.png *.webp"), ("Tất cả", "*.*")])
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
            messagebox.showinfo("Chưa có", "Chưa tạo script. Bấm '① OCR' trước.")

    def _open_edited(self):
        d = self._edited_dir()
        if d.exists():
            os.startfile(d)
        else:
            messagebox.showinfo("Chưa có", "Chưa render. Bấm '③ Render' trước.")

    def start_edit_ocr(self):
        p = self.ed_path.get().strip()
        if not p:
            messagebox.showwarning("Thiếu", "Hãy chọn thư mục chương hoặc 1 file ảnh.")
            return
        path = Path(p)
        cmd = [PY, "manga_translate.py", p, "--lang", self.ed_lang.get()]
        if path.is_dir():
            cmd += ["--out-dir", str(self._scripts_dir())]
        else:
            cmd += ["--out", str(path.with_suffix(".json"))]
        if self.ed_auto.get():
            cmd += ["--auto", "--to", self.ed_to.get().strip() or "vi"]
        self._spawn(cmd, clear=True, status="Đang OCR và tạo script JSON...")

    def start_edit_preview(self):
        self._edit_render(preview=True)

    def start_edit_render(self):
        self._edit_render(preview=False)

    def _edit_render(self, preview):
        p = self.ed_path.get().strip()
        if not p:
            messagebox.showwarning("Thiếu", "Hãy chọn thư mục chương hoặc 1 file ảnh.")
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
                    status="Đang tạo ảnh xem trước khung..." if preview else "Đang render (xóa chữ & chèn lời)...")

    def start_edit_cbz(self):
        p = self.ed_path.get().strip()
        if not p:
            messagebox.showwarning("Thiếu", "Hãy chọn thư mục chương hoặc 1 file ảnh.")
            return
        ed = self._edited_dir()
        if not ed.exists():
            messagebox.showinfo("Chưa có", "Chưa render trang nào. Bấm '③ Render' trước.")
            return
        self._spawn([PY, "manga_edit.py", str(ed), "--pack-cbz"], clear=True,
                    status="Đang đóng gói CBZ thành phẩm...")

    def start_box_editor(self):
        p = self.ed_path.get().strip()
        if not p:
            messagebox.showwarning("Thiếu", "Hãy chọn thư mục chương hoặc 1 file ảnh.")
            return
        path = Path(p)
        cmd = [PY, "manga_box_editor.py", p]
        if path.is_dir():
            cmd += ["--scripts-dir", str(self._scripts_dir())]
        else:
            cmd += ["--out", str(path.with_suffix(".json"))]
        try:
            subprocess.Popen(cmd, cwd=str(HERE))
            self._log("[Đã mở Manga Box Editor trong cửa sổ riêng biệt]\n"
                      "Vẽ bong bóng -> Gõ lời thoại -> Bấm Lưu. Xong quay lại đây bấm '③ Render'.\n", tag="ok")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không mở được Box Editor: {e}")

    # ==============================================================================
    # TAB 4: CÔNG CỤ NÂNG CAO (TOOLS & UTILITIES)
    # ==============================================================================
    def _build_tools_tab(self, root):
        pad = {"padx": 10, "pady": 6}

        # Tool 1: Xuất Excel Review
        card_excel = ttk.LabelFrame(root, text=" 📊 Xuất Chương Truyện ra Excel Review (.xlsx) ")
        card_excel.pack(fill="x", **pad)

        re_row = ttk.Frame(card_excel)
        re_row.pack(fill="x", padx=10, pady=8)

        self.tool_chap_path = tk.StringVar()
        ttk.Label(re_row, text="Chương truyện:").pack(side="left")
        ttk.Entry(re_row, textvariable=self.tool_chap_path).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(re_row, text="Chọn chương...", command=self._pick_tool_chap).pack(side="left", padx=2)
        ttk.Button(re_row, text="Xuất File Excel", style="Accent.TButton",
                   command=self._run_tool_excel).pack(side="left", padx=4)

        ttk.Label(card_excel, text="Nhúng ảnh thumbnail thật vào từng hàng, kèm cột số trang và ghi chú đánh giá cho dịch giả/biên tập.",
                  style="CardMuted.TLabel").pack(anchor="w", padx=10, pady=(0, 6))

        # Tool 2: Ghép dài Webtoon Stitcher
        card_stitch = ttk.LabelFrame(root, text=" 📜 Ghép ảnh Cuộn Dài Webtoon (Long-strip Stitcher) ")
        card_stitch.pack(fill="x", **pad)

        st_row = ttk.Frame(card_stitch)
        st_row.pack(fill="x", padx=10, pady=8)

        self.tool_stitch_path = tk.StringVar()
        ttk.Label(st_row, text="Thư mục ảnh:").pack(side="left")
        ttk.Entry(st_row, textvariable=self.tool_stitch_path).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(st_row, text="Chọn thư mục...", command=self._pick_tool_stitch).pack(side="left", padx=2)
        ttk.Button(st_row, text="Ghép Liền Mạch", style="Primary.TButton",
                   command=self._run_tool_stitch).pack(side="left", padx=4)

        # Tool 3: Chrome CDP & Google Drive
        card_extra = ttk.LabelFrame(root, text=" 🌐 Trình điều khiển Chrome Debugger & Google Drive Sync ")
        card_extra.pack(fill="x", **pad)

        ex_row = ttk.Frame(card_extra)
        ex_row.pack(fill="x", padx=10, pady=8)

        ttk.Button(ex_row, text="🌐 Khởi chạy Chrome Debug (Cổng 9222)",
                   command=self.open_debug_chrome).pack(side="left", padx=2)
        ttk.Button(ex_row, text="☁ Đồng bộ hàng loạt lên Google Drive",
                   command=self.start_upload).pack(side="left", padx=8)
        ttk.Button(ex_row, text="🧹 Dọn sạch file rác .part",
                   command=self._cleanup_temp).pack(side="left", padx=2)

    def _pick_tool_chap(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get() or str(HERE))
        if d:
            self.tool_chap_path.set(d)

    def _run_tool_excel(self):
        p = self.tool_chap_path.get().strip()
        if not p:
            messagebox.showwarning("Thiếu", "Hãy chọn một thư mục chương truyện.")
            return
        cmd = [PY, "to_excel.py", p]
        self._spawn(cmd, clear=True, status="Đang xuất file Excel...")

    def _pick_tool_stitch(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get() or str(HERE))
        if d:
            self.tool_stitch_path.set(d)

    def _run_tool_stitch(self):
        p = self.tool_stitch_path.get().strip()
        if not p:
            messagebox.showwarning("Thiếu", "Hãy chọn một thư mục ảnh chương.")
            return
        cmd = [PY, "-c",
               f"import pack, glob; from pathlib import Path; "
               f"p = Path(r'{p}'); "
               f"imgs = sorted([f for f in p.iterdir() if f.suffix.lower() in ('.jpg','.jpeg','.png','.webp')]); "
               f"print(f'Dang ghep {{len(imgs)}} anh...'); "
               f"res = pack.make_stitch(imgs, p); "
               f"print('Da ghep thanh cong:', res)"]
        self._spawn(cmd, clear=True, status="Đang ghép ảnh dải dài...")

    # ==============================================================================
    # BOTTOM CONSOLE LOG & STATUS
    # ==============================================================================
    def _build_console(self):
        # Progress & Status Ticker
        self.status = tk.StringVar(value="Sẵn sàng.")
        bar_frame = tk.Frame(self, bg=BG_APP)
        bar_frame.pack(fill="x", padx=12, pady=(4, 2))

        self.pb = ttk.Progressbar(bar_frame, mode="indeterminate")
        self.pb.pack(side="left", fill="x", expand=True)

        self.lbl_status = tk.Label(bar_frame, textvariable=self.status,
                                   font=(FONT_NAME, 9, "bold"), bg=BG_APP, fg=ACCENT_CYAN)
        self.lbl_status.pack(side="right", padx=(10, 0))

        # Log Frame
        log_frame = ttk.LabelFrame(self, text=" 🖥 Nhật ký Điều khiển (Terminal Log) ")
        log_frame.pack(fill="both", expand=True, padx=12, pady=(2, 10))

        # Toolbar trên log
        log_tools = tk.Frame(log_frame, bg=BG_CARD)
        log_tools.pack(fill="x", padx=6, pady=(2, 2))

        self.auto_scroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_tools, text="Tự cuộn xuống", variable=self.auto_scroll).pack(side="left", padx=4)

        ttk.Button(log_tools, text="📋 Sao chép Log", style="Ghost.TButton",
                   command=self._copy_log).pack(side="right", padx=2)
        ttk.Button(log_tools, text="🧹 Xóa sạch", style="Ghost.TButton",
                   command=self._clear_log).pack(side="right", padx=2)

        # Text Console
        txt_box = tk.Frame(log_frame, bg=LOG_BG)
        txt_box.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.log = tk.Text(txt_box, height=8, wrap="word", bg=LOG_BG, fg=LOG_FG,
                           insertbackground=TEXT_MAIN, selectbackground=ACCENT_INDIGO,
                           relief="flat", borderwidth=0, padx=10, pady=6,
                           font=(FONT_MONO, 9))
        self.log.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(txt_box, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set, state="disabled")

        # Cấu hình màu cho log
        self.log.tag_configure("ok", foreground="#4ade80")       # Xanh lá sáng
        self.log.tag_configure("err", foreground="#f87171")      # Đỏ san hô
        self.log.tag_configure("warn", foreground="#fbbf24")     # Vàng cam
        self.log.tag_configure("cmd", foreground="#38bdf8")      # Xanh lam
        self.log.tag_configure("accent", foreground="#c084fc")   # Tím neon
        self.log.tag_configure("muted", foreground="#94a3b8")

    # ==============================================================================
    # ĐIỀU KHIỂN SỰ KIỆN NGUỒN & HÀNH ĐỘNG
    # ==============================================================================
    def _on_source_change(self):
        for fr in (self._auto_frame, self._mangadex_frame, self._truyenqq_frame,
                   self._mangafire_frame, self._generic_frame):
            fr.pack_forget()

        s = self.source.get()
        self.btn_check.config(state="normal" if s.startswith("Tu dong") else "disabled")

        if s.startswith("Tu dong"):
            self._auto_frame.pack(fill="x", padx=4, pady=4)
            self.lbl_target.config(text="Link bất kỳ (bộ truyện / 1 chương):")
            self.hint.config(text="Tool tự phân tích trang & chọn phương thức tối ưu (MangaDex, TruyenQQ, ToonGod, Webtoon...).")
            self.btn_list.config(state="disabled")
            self.btn_chrome.config(state="disabled")
        elif s == "MangaDex":
            self._mangadex_frame.pack(fill="x", padx=4, pady=4)
            self.lbl_target.config(text="Link / ID / 'search:tên':")
            self.hint.config(text="Vd: search:grapara  hoặc  https://mangadex.org/title/<id>/... (tích hợp sẵn DoH 1.1.1.1).")
            self.btn_list.config(state="normal")
            self.btn_chrome.config(state="disabled")
        elif s.startswith("TruyenQQ"):
            self._truyenqq_frame.pack(fill="x", padx=4, pady=4)
            self.lbl_target.config(text="Link bộ truyện / 1 chương:")
            self.hint.config(text="Vd: https://truyenqqko.com/truyen-tranh/<ten>-<id> (HTTP thuần tốc độ cao).")
            self.btn_list.config(state="disabled")
            self.btn_chrome.config(state="disabled")
        elif s.startswith("mangafire"):
            self._mangafire_frame.pack(fill="x", padx=4, pady=4)
            self.lbl_target.config(text="Link bộ (/manga/...) hoặc 1 chương (/read/...):")
            self.hint.config(text="Cần bấm 'Chrome gỡ lỗi' mở cổng 9222 vượt Cloudflare trước.")
            self.btn_list.config(state="disabled")
            self.btn_chrome.config(state="normal")
        else:
            self._generic_frame.pack(fill="x", padx=4, pady=4)
            self.lbl_target.config(text="Link bộ truyện / 1 chương:")
            self.hint.config(text="Trình duyệt Chromium tự động (Playwright) quét và trích xuất ảnh.")
            self.btn_list.config(state="disabled")
            self.btn_chrome.config(state="disabled")

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get() or str(HERE))
        if d:
            self.outdir.set(d)
            self._refresh_library()

    def _open_outdir(self):
        d = self.outdir.get().strip() or str(HERE / "downloads")
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

    # ==============================================================================
    # BUILD & EXECUTE SUBPROCESS COMMANDS
    # ==============================================================================
    def _build_cmd(self, action="download"):
        s = self.source.get()
        target = self.target.get().strip()
        out = self.outdir.get().strip() or "downloads"
        fmts = self._formats()

        if s.startswith("Tu dong"):
            if not target:
                raise ValueError("Hãy nhập hoặc dán link truyện vào ô phía trên.")
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
                raise ValueError("Hãy nhập link, UUID hoặc 'search:tên truyện'.")
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
                raise ValueError("Hãy nhập link bộ truyện hoặc link 1 chương.")
            cmd = [PY, "truyenqq_dl.py", target, "--out", out, "--format", *fmts]
            r1, r2 = self.qq_r1.get().strip(), self.qq_r2.get().strip()
            if r1 and r2:
                cmd += ["--range", r1, r2]
            if self.limit.get().strip() not in ("", "0"):
                cmd += ["--limit", self.limit.get().strip()]
            return cmd

        if s.startswith("mangafire"):
            if not target:
                raise ValueError("Hãy nhập link bộ (/manga/...) hoặc 1 chương (/read/...).")
            cmd = [PY, "mangafire_dl.py", target, "--out", out, "--format", *fmts]
            r1, r2 = self.mf_r1.get().strip(), self.mf_r2.get().strip()
            if r1 and r2:
                cmd += ["--range", r1, r2]
            if self.limit.get().strip() not in ("", "0"):
                cmd += ["--limit", self.limit.get().strip()]
            return cmd

        # Trang bất kỳ
        if not target:
            raise ValueError("Hãy nhập link trang web.")
        cmd = [PY, "manga_dl.py", target, "--out", out, "--format", *fmts,
               "--mode", self.mode.get()]
        if self.limit.get().strip() not in ("", "0"):
            cmd += ["--limit", self.limit.get().strip()]
        if self.headful.get():
            cmd.append("--headful")
        return cmd

    def start_download(self):
        self._run("download")

    def start_resume(self):
        self._run("download", status="Đang tiếp tục tải các phần còn thiếu...")

    def start_list(self):
        self._run("list")

    def start_langs(self):
        self._run("langs")

    def start_check(self):
        self._run("check", status="Đang phân tích và chẩn đoán link...")

    def _run(self, action, status="Đang chạy tác vụ..."):
        try:
            cmd = self._build_cmd(action=action)
        except ValueError as e:
            messagebox.showwarning("Thiếu thông tin", str(e))
            return

        self._chain_upload = (action == "download" and self.gdrive_up.get())
        self._spawn(cmd, clear=True, status=status)

    def _spawn(self, cmd, clear=True, status="Đang chạy..."):
        if self.proc is not None:
            messagebox.showinfo("Đang chạy", "Đang có một tác vụ đang chạy. Hãy bấm 'Dừng' trước.")
            return

        if clear:
            self._clear_log()

        self._log("> " + " ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n", tag="cmd")
        self.status.set(status)
        self.lbl_engine_pill.config(text="⚡ ĐANG CHẠY...", fg=ACCENT_CYAN)
        self.pb.start(10)

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
            self.log_q.put(("line", f"LỖI khởi chạy: {e}\n"))
            self.log_q.put(("done", -1))
            return

        for line in self.proc.stdout:
            self.log_q.put(("line", line))

        code = self.proc.wait()
        self.log_q.put(("done", code))

    def stop(self):
        """Dừng tác vụ an toàn, diệt sạch tiến trình con và dọn file .part."""
        self._chain_upload = False
        if self.proc and self.proc.poll() is None:
            pid = self.proc.pid
            try:
                if os.name == "nt":
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
            self._log("\n[Đã dừng tác vụ theo yêu cầu]\n", tag="warn")

        self._cleanup_temp()
        self.lbl_engine_pill.config(text="⏹ ĐÃ DỪNG", fg=ACCENT_AMBER)

    def _cleanup_temp(self):
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
            self._log(f"[Đã dọn dẹp {n} file tạm .part]\n", tag="ok")
        else:
            self._log("[Không còn file tạm .part nào tồn đọng]\n", tag="muted")

    def reset(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Đang chạy", "Tác vụ đang chạy. Dừng và làm mới?"):
                return
            self.stop()
        else:
            self._cleanup_temp()

        self.target.set("")
        self.mf_name.set("")
        self.mf_r1.set("")
        self.mf_r2.set("")
        self._clear_log()
        self.status.set("Sẵn sàng.")
        self.lbl_engine_pill.config(text="● SẴN SÀNG", fg=ACCENT_GREEN)
        self.pb.stop()
        self._refresh_library()

    def open_debug_chrome(self):
        chrome = find_chrome()
        if not chrome:
            messagebox.showerror("Không thấy Chrome",
                                 "Không tìm thấy file chrome.exe ở vị trí mặc định.")
            return

        url = self.target.get().strip() or "https://mangafire.to/"
        try:
            subprocess.Popen([chrome, f"--remote-debugging-port={DEBUG_PORT}",
                              f"--user-data-dir={DEBUG_PROFILE}", url])
            self._log(f"[Đã khởi chạy Chrome Debugger cổng {DEBUG_PORT}]\n"
                      f"Vui lòng hoàn thành xác thực Cloudflare/reCAPTCHA trên Chrome, sau đó quay lại bấm Tải.\n", tag="ok")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở Chrome: {e}")

    # ==============================================================================
    # GOOGLE DRIVE SYNC DIALOG
    # ==============================================================================
    def start_upload(self):
        self._chain_upload = False
        if self.proc is not None:
            messagebox.showinfo("Đang chạy", "Đang có tác vụ chạy. Hãy chờ hoàn thành.")
            return

        out = Path(self.outdir.get().strip() or "downloads")
        if not out.exists():
            messagebox.showwarning("Chưa có dữ liệu", f"Chưa thấy thư mục '{out}'.")
            return

        series = sorted([d for d in out.iterdir() if d.is_dir()],
                        key=lambda d: d.name.lower())
        if not series:
            messagebox.showinfo("Trống", f"Không thấy bộ truyện nào trong '{out}'.")
            return

        self._upload_dialog(series)

    def _upload_dialog(self, series):
        dlg = tk.Toplevel(self)
        dlg.title("Chọn bộ truyện để đẩy lên Google Drive")
        dlg.configure(bg=BG_CARD)
        dlg.geometry("480x440")
        dlg.transient(self)

        ttk.Label(dlg, text="Tích chọn các bộ truyện muốn đẩy lên Drive:",
                  font=(FONT_NAME, 10, "bold")).pack(anchor="w", padx=14, pady=(14, 4))
        ttk.Label(dlg, text="(Chỉ đồng bộ các thư mục ảnh — tự bỏ qua file .cbz/.pdf)",
                  style="CardMuted.TLabel").pack(anchor="w", padx=14)

        box = tk.Frame(dlg, bg=BG_INPUT)
        box.pack(fill="both", expand=True, padx=14, pady=8)

        lb = tk.Listbox(box, selectmode="extended", bg=BG_INPUT, fg=TEXT_MAIN,
                        selectbackground=ACCENT_INDIGO, selectforeground="#fff",
                        relief="flat", highlightthickness=0, activestyle="none",
                        font=(FONT_NAME, 10))
        lb.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(box, command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.config(yscrollcommand=sb.set)

        for d in series:
            lb.insert("end", "  " + d.name)
        lb.select_set(0, "end")

        btns = ttk.Frame(dlg)
        btns.pack(fill="x", padx=14, pady=(0, 14))

        def do_upload():
            idxs = lb.curselection()
            if not idxs:
                messagebox.showinfo("Chưa chọn", "Hãy tích chọn ít nhất 1 bộ truyện.", parent=dlg)
                return
            chosen = [str(series[i]) for i in idxs]
            dlg.destroy()
            cmd = [PY, "upload_drive.py", *chosen,
                   "--remote", self.gdrive_remote.get().strip() or "drive",
                   "--dest", self.gdrive_dest.get().strip() or "Manga"]
            self._spawn(cmd, clear=False,
                        status=f"Đang đẩy {len(chosen)} bộ truyện lên Drive...")

        ttk.Button(btns, text="Bỏ chọn hết",
                   command=lambda: lb.select_clear(0, "end")).pack(side="left")
        ttk.Button(btns, text="Hủy", style="Ghost.TButton",
                   command=dlg.destroy).pack(side="right")
        ttk.Button(btns, text="☁ Đẩy lên Drive", style="Primary.TButton",
                   command=do_upload).pack(side="right", padx=6)

        dlg.after(60, lambda: (dlg.lift(), dlg.focus_force()))

    # ==============================================================================
    # TERMINAL LOG MANAGEMENT
    # ==============================================================================
    def _log(self, text, tag=None):
        self.log.config(state="normal")

        # Tự động gán màu nếu chưa có tag
        if not tag:
            low = text.lower()
            if any(k in low for k in ["lỗi", "error", "failed", "thất bại", "exception"]):
                tag = "err"
            elif any(k in low for k in ["ok", "✔", "hoàn tất", "thành công", "[đã xong]", "100%"]):
                tag = "ok"
            elif any(k in low for k in ["cảnh báo", "warning", "[bỏ qua]"]):
                tag = "warn"
            elif text.startswith(">"):
                tag = "cmd"
            elif any(k in text for k in ["===", "---", "###"]):
                tag = "accent"

        if tag:
            self.log.insert("end", text, tag)
        else:
            self.log.insert("end", text)

        if self.auto_scroll.get():
            self.log.see("end")

        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _copy_log(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.log.get("1.0", "end"))
            messagebox.showinfo("Đã chép", "Toàn bộ nội dung Log đã được sao chép vào bộ nhớ tạm.")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không sao chép được: {e}")

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

                    if payload == 0:
                        self.status.set("Hoàn tất thành công.")
                        self.lbl_engine_pill.config(text="● HOÀN TẤT ✔", fg=ACCENT_GREEN)
                        self._refresh_library()
                    else:
                        self.status.set(f"Kết thúc với mã {payload}.")
                        self.lbl_engine_pill.config(text=f"● LỖI ({payload})", fg=ACCENT_RED)

                    if payload == 0 and self._chain_upload:
                        self._chain_upload = False
                        self._log("\n--- Tải xong: Mở hộp thoại chọn truyện để đồng bộ lên Google Drive ---\n", tag="accent")
                        self.after(300, self.start_upload)
        except queue.Empty:
            pass

        self.after(60, self._drain_log)


if __name__ == "__main__":
    App().mainloop()
