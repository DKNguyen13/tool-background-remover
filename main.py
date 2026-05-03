"""
main.py  –  ImgTool BG Remover
Dark industrial GUI for game-dev sprite processing.
Run: python main.py
"""

from __future__ import annotations
import io
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional
from PIL import Image, ImageTk, ImageDraw

# ── Local modules ─────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from remover   import remove_background, RemoverConfig, collect_images
from processor import preprocess,       PreprocessConfig
from refiner  import postprocess,      PostprocessConfig
from optimizer   import save_optimized,   OptimizeConfig


# ═════════════════════════════════════════════════════════════════════════════
#  THEME
# ═════════════════════════════════════════════════════════════════════════════

BG       = "#0d0f14"
BG2      = "#161920"
BG3      = "#1e2230"
PANEL    = "#222636"
BORDER   = "#2e3450"
ACCENT   = "#4f9cff"
ACCENT2  = "#ff5f6d"
SUCCESS  = "#39d98a"
WARN     = "#ffc107"
TEXT     = "#e8eaf6"
TEXT_DIM = "#6b7399"
MONO     = ("Consolas", 9)
FONT_H   = ("Segoe UI", 11, "bold")
FONT_B   = ("Segoe UI", 9)
FONT_S   = ("Segoe UI", 8)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ═════════════════════════════════════════════════════════════════════════════
#  CHECKERBOARD (alpha preview background)
# ═════════════════════════════════════════════════════════════════════════════

def make_checker(w: int, h: int, cell: int = 12) -> Image.Image:
    img = Image.new("RGB", (w, h))
    dark, light = (60, 60, 60), (90, 90, 90)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            c = light if ((x // cell + y // cell) % 2 == 0) else dark
            ImageDraw.Draw(img).rectangle([x, y, x+cell-1, y+cell-1], fill=c)
    return img


def composite_on_checker(rgba: Image.Image, w: int, h: int) -> Image.Image:
    checker = make_checker(w, h)
    rgba_fit = rgba.copy()
    rgba_fit.thumbnail((w, h), Image.LANCZOS)
    ox = (w - rgba_fit.width) // 2
    oy = (h - rgba_fit.height) // 2
    checker.paste(rgba_fit, (ox, oy), rgba_fit)
    return checker


# ═════════════════════════════════════════════════════════════════════════════
#  STYLED WIDGETS
# ═════════════════════════════════════════════════════════════════════════════

class DarkStyle:
    @staticmethod
    def apply(root: tk.Tk):
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".",
            background=BG2, foreground=TEXT,
            fieldbackground=BG3, troughcolor=BG3,
            selectbackground=ACCENT, selectforeground="#000",
            insertcolor=TEXT, borderwidth=0, relief="flat",
        )
        style.configure("TFrame",        background=BG2)
        style.configure("TLabel",        background=BG2, foreground=TEXT, font=FONT_B)
        style.configure("TButton",
            background=PANEL, foreground=TEXT,
            font=FONT_B, padding=(10, 6), relief="flat",
        )
        style.map("TButton",
            background=[("active", BG3), ("pressed", BORDER)],
            foreground=[("active", TEXT)],
        )
        style.configure("Accent.TButton",
            background=ACCENT, foreground="#000",
            font=("Segoe UI", 9, "bold"), padding=(12, 7),
        )
        style.map("Accent.TButton",
            background=[("active", "#6aaeff"), ("pressed", "#3a7fe0")],
        )
        style.configure("Danger.TButton",
            background=ACCENT2, foreground="#fff",
            font=FONT_B, padding=(10, 6),
        )
        style.configure("TEntry",
            background=BG3, fieldbackground=BG3,
            foreground=TEXT, insertcolor=TEXT, relief="flat",
        )
        style.configure("TCombobox",
            background=BG3, fieldbackground=BG3,
            foreground=TEXT, selectbackground=ACCENT,
        )
        style.configure("TCheckbutton",
            background=BG2, foreground=TEXT, font=FONT_B,
        )
        style.map("TCheckbutton",
            background=[("active", BG2)],
            foreground=[("active", ACCENT)],
        )
        style.configure("TScale", background=BG2, troughcolor=BG3, sliderthickness=14)
        style.configure("TProgressbar", background=ACCENT, troughcolor=BG3, thickness=6)
        style.configure("TNotebook",        background=BG, tabmargins=[2, 4, 2, 0])
        style.configure("TNotebook.Tab",    background=BG3, foreground=TEXT_DIM, padding=(14, 6))
        style.map("TNotebook.Tab",
            background=[("selected", BG2)],
            foreground=[("selected", ACCENT)],
        )
        style.configure("TScrollbar", background=BG3, troughcolor=BG, arrowcolor=TEXT_DIM)
        style.configure("Heading.TLabel",   foreground=ACCENT, font=FONT_H)
        style.configure("Dim.TLabel",       foreground=TEXT_DIM, font=FONT_S)
        style.configure("Success.TLabel",   foreground=SUCCESS, font=FONT_B)
        style.configure("Warn.TLabel",      foreground=WARN, font=FONT_B)
        style.configure("Separator.TFrame", background=BORDER)


def sep(parent, vertical=False):
    f = ttk.Frame(parent, style="Separator.TFrame",
                  width=1 if vertical else 0, height=0 if vertical else 1)
    return f


def section_label(parent, text: str) -> ttk.Label:
    return ttk.Label(parent, text=text.upper(), style="Dim.TLabel")


# ═════════════════════════════════════════════════════════════════════════════
#  PREVIEW PANEL
# ═════════════════════════════════════════════════════════════════════════════

class PreviewPanel(tk.Frame):
    def __init__(self, parent, label: str, **kw):
        super().__init__(parent, bg=BG3, **kw)
        tk.Label(self, text=label, bg=BG3, fg=TEXT_DIM,
                 font=FONT_S).pack(side="top", anchor="w", padx=6, pady=(4, 0))
        self.canvas = tk.Canvas(self, bg="#3c3c3c", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=(2, 4))
        self._photo: Optional[ImageTk.PhotoImage] = None

    def show(self, img: Image.Image | None):
        self.canvas.update_idletasks()
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 2 or ch < 2:
            cw, ch = 300, 300
        self.canvas.delete("all")
        if img is None:
            self.canvas.create_text(cw//2, ch//2, text="No image", fill=TEXT_DIM, font=FONT_S)
            return
        if img.mode == "RGBA":
            display = composite_on_checker(img, cw, ch)
        else:
            display = img.copy()
            display.thumbnail((cw, ch), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(display)
        ox = (cw - display.width) // 2
        oy = (ch - display.height) // 2
        self.canvas.create_image(ox, oy, anchor="nw", image=self._photo)


# ═════════════════════════════════════════════════════════════════════════════
#  SETTINGS PANEL
# ═════════════════════════════════════════════════════════════════════════════

class SettingsPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=(12, 8))
        self._build()

    def _build(self):
        row = 0

        # ── AI Model ─────────────────────────────────────────────────────────
        section_label(self, "🧠  AI Model").grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        row += 1
        ttk.Label(self, text="Model").grid(row=row, column=0, sticky="w")
        self.model_var = tk.StringVar(value="u2net")
        cb = ttk.Combobox(self, textvariable=self.model_var, width=24, state="readonly",
                          values=["u2net", "u2netp", "u2net_human_seg", "isnet-general-use", "silueta"])
        cb.grid(row=row, column=1, sticky="ew", padx=(6, 0))
        row += 1

        ttk.Label(self, text="", font=("", 4)).grid(row=row, column=0); row += 1

        # ── Alpha Matting ────────────────────────────────────────────────────
        section_label(self, "✂️  Alpha Matting (sharp edges)").grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))
        row += 1
        self.alpha_matting_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Enable alpha matting", variable=self.alpha_matting_var,
                        command=self._toggle_matting).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        self._matting_widgets = []

        lbl, w = self._slider_row("FG threshold", 0, 255, 240, row)
        self.fg_thresh = w; self._matting_widgets += [lbl, w]; row += 1

        lbl, w = self._slider_row("BG threshold", 0, 255, 10, row)
        self.bg_thresh = w; self._matting_widgets += [lbl, w]; row += 1

        lbl, w = self._slider_row("Erode size", 1, 30, 10, row)
        self.erode = w; self._matting_widgets += [lbl, w]; row += 1

        ttk.Label(self, text="", font=("", 4)).grid(row=row, column=0); row += 1

        # ── White / Solid BG Cleanup ─────────────────────────────────────────
        section_label(self, "🧹  White/Solid BG Cleanup  ←  FIX viền trắng").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(4, 2))
        row += 1
        self.white_cleanup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Kill residual BG pixels (by colour distance)",
                        variable=self.white_cleanup_var).grid(
            row=row, column=0, columnspan=2, sticky="w"); row += 1

        self.auto_bg_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Auto-detect BG colour from corners",
                        variable=self.auto_bg_var).grid(
            row=row, column=0, columnspan=2, sticky="w"); row += 1

        self.white_kill_semi_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Also kill bright semi-transparent pixels",
                        variable=self.white_kill_semi_var).grid(
            row=row, column=0, columnspan=2, sticky="w"); row += 1

        _, self.white_thresh = self._slider_row("Brightness threshold", 150, 255, 220, row)
        row += 1

        self.despill_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Despill: recover true sprite colours",
                        variable=self.despill_var).grid(
            row=row, column=0, columnspan=2, sticky="w"); row += 1

        _, self.despill_strength = self._slider_row("Despill strength", 0, 1, 85, row, resolution=0.01)
        row += 1

        # BG colour picker (manual override)
        ttk.Label(self, text="BG Colour (hex)", style="Dim.TLabel").grid(row=row, column=0, sticky="w")
        self.bg_color_var = tk.StringVar(value="#ffffff")
        bg_entry = ttk.Entry(self, textvariable=self.bg_color_var, width=10)
        bg_entry.grid(row=row, column=1, sticky="w", padx=(6, 0)); row += 1
        ttk.Label(self, text="(overridden by auto-detect when checked)",
                  style="Dim.TLabel").grid(row=row, column=0, columnspan=2, sticky="w"); row += 1

        ttk.Label(self, text="", font=("", 4)).grid(row=row, column=0); row += 1

        # ── Edge Refinement ──────────────────────────────────────────────────
        section_label(self, "🔬  Edge Refinement").grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))
        row += 1
        self.edge_refine_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Enable edge refinement", variable=self.edge_refine_var).grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1

        _, self.edge_blur = self._slider_row("Edge feather", 0, 5, 1, row, resolution=0.1)
        row += 1
        _, self.edge_contract = self._slider_row("Contract (px)", 0, 10, 0, row)
        row += 1
        _, self.edge_expand = self._slider_row("Expand (px)", 0, 10, 0, row)
        row += 1

        ttk.Label(self, text="", font=("", 4)).grid(row=row, column=0); row += 1

        # ── Decontaminate ────────────────────────────────────────────────────
        section_label(self, "🎨  Colour Cleanup").grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))
        row += 1
        self.decontam_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="Decontaminate edge colours", variable=self.decontam_var).grid(
            row=row, column=0, columnspan=2, sticky="w")
        row += 1
        _, self.decontam_strength = self._slider_row("Strength", 0, 1, 50, row, resolution=0.01)
        row += 1

        ttk.Label(self, text="", font=("", 4)).grid(row=row, column=0); row += 1

        # ── Pre/Post ─────────────────────────────────────────────────────────
        section_label(self, "⚙️  Pre / Post Process").grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))
        row += 1
        self.upscale_var    = tk.BooleanVar(value=True)
        self.sharpen_var    = tk.BooleanVar(value=True)
        self.trim_var       = tk.BooleanVar(value=True)
        self.pow2_var       = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Auto-upscale small images (≥512px)", variable=self.upscale_var).grid(
            row=row, column=0, columnspan=2, sticky="w"); row += 1
        ttk.Checkbutton(self, text="Pre-sharpen before removal",         variable=self.sharpen_var).grid(
            row=row, column=0, columnspan=2, sticky="w"); row += 1
        ttk.Checkbutton(self, text="Auto-trim transparent border",       variable=self.trim_var).grid(
            row=row, column=0, columnspan=2, sticky="w"); row += 1
        ttk.Checkbutton(self, text="Resize to power-of-two (game engines)", variable=self.pow2_var).grid(
            row=row, column=0, columnspan=2, sticky="w"); row += 1

        _, self.padding_slider = self._slider_row("Padding (px)", 0, 32, 2, row)
        row += 1

        ttk.Label(self, text="", font=("", 4)).grid(row=row, column=0); row += 1

        # ── Output ───────────────────────────────────────────────────────────
        section_label(self, "💾  Output").grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 4))
        row += 1
        ttk.Label(self, text="Format").grid(row=row, column=0, sticky="w")
        self.fmt_var = tk.StringVar(value="PNG")
        ttk.Combobox(self, textvariable=self.fmt_var, width=10, state="readonly",
                     values=["PNG", "WEBP"]).grid(row=row, column=1, sticky="w", padx=(6, 0))
        row += 1

        self.columnconfigure(1, weight=1)
        self._toggle_matting()

    def _slider_row(self, label, from_, to, init, row, resolution=1):
        lbl = ttk.Label(self, text=label)
        lbl.grid(row=row, column=0, sticky="w", pady=1)
        var = tk.DoubleVar(value=init)
        frame = ttk.Frame(self)
        frame.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=1)
        scale = ttk.Scale(frame, from_=from_, to=to, variable=var,
                          orient="horizontal", length=140)
        scale.pack(side="left", fill="x", expand=True)
        val_lbl = ttk.Label(frame, textvariable=var, width=5, style="Dim.TLabel")
        val_lbl.pack(side="left", padx=(4, 0))
        # Round display
        def _fmt(*_):
            v = var.get()
            val_lbl.config(text=f"{v:.1f}" if resolution < 1 else f"{int(v)}")
        var.trace_add("write", _fmt)
        _fmt()
        return lbl, var

    def _toggle_matting(self):
        state = "normal" if self.alpha_matting_var.get() else "disabled"
        for w in self._matting_widgets:
            try:
                w.configure(state=state)
            except Exception:
                pass

    def build_configs(self):
        # Parse manual bg color hex
        try:
            hx = self.bg_color_var.get().lstrip("#")
            manual_bg = tuple(int(hx[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            manual_bg = (255, 255, 255)

        rem = RemoverConfig(
            model=self.model_var.get(),
            alpha_matting=self.alpha_matting_var.get(),
            alpha_matting_foreground_threshold=int(self.fg_thresh.get()),
            alpha_matting_background_threshold=int(self.bg_thresh.get()),
            alpha_matting_erode_size=int(self.erode.get()),
            edge_refine=self.edge_refine_var.get(),
            edge_blur_radius=self.edge_blur.get(),
            edge_contract=int(self.edge_contract.get()),
            edge_expand=int(self.edge_expand.get()),
            # White BG cleanup
            white_bg_cleanup=self.white_cleanup_var.get(),
            white_bg_threshold=int(self.white_thresh.get()),
            white_bg_kill_semi=self.white_kill_semi_var.get(),
            despill=self.despill_var.get(),
            despill_bg_color=manual_bg,
            despill_strength=self.despill_strength.get(),
            auto_detect_bg_color=self.auto_bg_var.get(),
            # Generic decontam
            decontaminate=self.decontam_var.get(),
            decontaminate_strength=self.decontam_strength.get(),
            output_format=self.fmt_var.get(),
        )
        pre = PreprocessConfig(
            upscale=self.upscale_var.get(),
            pre_sharpen=self.sharpen_var.get(),
        )
        post = PostprocessConfig(
            auto_trim=self.trim_var.get(),
            padding=int(self.padding_slider.get()),
            power_of_two=self.pow2_var.get(),
        )
        opt = OptimizeConfig(format=self.fmt_var.get())
        return rem, pre, post, opt


# ═════════════════════════════════════════════════════════════════════════════
#  LOG PANEL
# ═════════════════════════════════════════════════════════════════════════════

class LogPanel(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        self.text = tk.Text(self, bg=BG, fg=TEXT_DIM, font=MONO,
                            relief="flat", height=6, wrap="word",
                            state="disabled", insertbackground=TEXT)
        sb = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        self.text.tag_config("ok",   foreground=SUCCESS)
        self.text.tag_config("err",  foreground=ACCENT2)
        self.text.tag_config("info", foreground=ACCENT)
        self.text.tag_config("warn", foreground=WARN)

    def log(self, msg: str, tag: str = ""):
        self.text.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] {msg}\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═════════════════════════════════════════════════════════════════════════════

class ImgToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ImgTool  ·  BG Remover  ·  Game Dev Edition")
        self.geometry("1280x820")
        self.minsize(960, 640)
        self.configure(bg=BG)
        DarkStyle.apply(self)

        self._input_paths: list[Path] = []
        self._current_idx: int = 0
        self._current_input_img:  Optional[Image.Image] = None
        self._current_output_img: Optional[Image.Image] = None
        self._output_dir: Optional[Path] = None
        self._batch_thread: Optional[threading.Thread] = None
        self._cancel_flag = threading.Event()

        self._build_ui()
        self._update_status()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self, bg=BG2, height=52)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⬛ IMGTOOL", bg=BG2, fg=ACCENT,
                 font=("Consolas", 16, "bold")).pack(side="left", padx=16, pady=12)
        tk.Label(hdr, text="Background Remover  ·  Game Dev Edition", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side="left", pady=16)

        sep(self).pack(fill="x")

        # ── Toolbar ──
        tb = tk.Frame(self, bg=BG3, pady=6)
        tb.pack(fill="x")
        ttk.Button(tb, text="📂  Open Images",  command=self._open_images).pack(side="left", padx=(8, 4))
        ttk.Button(tb, text="📁  Open Folder",  command=self._open_folder).pack(side="left", padx=4)
        ttk.Button(tb, text="🗂️  Set Output",   command=self._set_output).pack(side="left", padx=4)
        sep(tb, vertical=True).pack(side="left", fill="y", padx=8)
        ttk.Button(tb, text="▶  Process Single", command=self._process_single,
                   style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(tb, text="⚡  Batch Process",  command=self._start_batch,
                   style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(tb, text="⛔  Cancel",         command=self._cancel_batch,
                   style="Danger.TButton").pack(side="left", padx=4)
        sep(tb, vertical=True).pack(side="left", fill="y", padx=8)
        ttk.Button(tb, text="💾  Save Current",   command=self._save_current).pack(side="left", padx=4)

        # ── Status bar ──
        self._status_var = tk.StringVar(value="Ready.")
        self._status_lbl = tk.Label(self, textvariable=self._status_var,
                                    bg=BG, fg=TEXT_DIM, font=FONT_S, anchor="w")
        self._status_lbl.pack(fill="x", side="bottom", padx=8, pady=2)

        # ── Progress ──
        self._progress_var = tk.DoubleVar(value=0)
        self._progress = ttk.Progressbar(self, variable=self._progress_var,
                                         maximum=100, mode="determinate")
        self._progress.pack(fill="x", side="bottom")

        # ── Log ──
        self.log_panel = LogPanel(self, height=120)
        self.log_panel.pack(fill="x", side="bottom", padx=0)

        sep(self).pack(fill="x", side="bottom")

        # ── Main area ──
        main = tk.PanedWindow(self, orient="horizontal", bg=BG,
                               sashwidth=6, sashrelief="flat", sashpad=2)
        main.pack(fill="both", expand=True)

        # Left: settings
        settings_scroll_frame = tk.Frame(main, bg=BG2, width=310)
        canvas = tk.Canvas(settings_scroll_frame, bg=BG2, highlightthickness=0, width=306)
        vsb = ttk.Scrollbar(settings_scroll_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.settings = SettingsPanel(canvas)
        win_id = canvas.create_window((0, 0), window=self.settings, anchor="nw")
        def _on_conf(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        self.settings.bind("<Configure>", _on_conf)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        # Mouse wheel scroll
        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _wheel)
        main.add(settings_scroll_frame, minsize=260)

        # Right: preview + file list
        right = tk.PanedWindow(main, orient="vertical", bg=BG,
                                sashwidth=6, sashrelief="flat")

        # Preview area
        preview_area = tk.Frame(right, bg=BG)
        prev_pane = tk.PanedWindow(preview_area, orient="horizontal", bg=BG,
                                    sashwidth=4, sashrelief="flat")
        self.preview_in  = PreviewPanel(prev_pane, "INPUT")
        self.preview_out = PreviewPanel(prev_pane, "OUTPUT  (checkerboard = transparent)")
        prev_pane.add(self.preview_in,  minsize=200)
        prev_pane.add(self.preview_out, minsize=200)
        prev_pane.pack(fill="both", expand=True)
        right.add(preview_area)

        # File list + nav
        list_frame = tk.Frame(right, bg=BG2)
        nav = tk.Frame(list_frame, bg=BG2)
        nav.pack(fill="x", padx=6, pady=4)
        ttk.Button(nav, text="◀", width=3, command=self._prev_file).pack(side="left")
        self._file_lbl = ttk.Label(nav, text="No files loaded", style="Dim.TLabel")
        self._file_lbl.pack(side="left", padx=8)
        ttk.Button(nav, text="▶", width=3, command=self._next_file).pack(side="left")

        list_container = tk.Frame(list_frame, bg=BG2)
        list_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.file_list = tk.Listbox(
            list_container,
            bg=BG3, fg=TEXT, selectbackground=ACCENT, selectforeground="#000",
            font=MONO, relief="flat", borderwidth=0, activestyle="none",
        )
        lsb = ttk.Scrollbar(list_container, command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.file_list.pack(fill="both", expand=True)
        self.file_list.bind("<<ListboxSelect>>", self._on_list_select)
        right.add(list_frame, minsize=80)

        main.add(right, minsize=600)

        # Drop target hint
        self.drop_label = tk.Label(
            self, text="Drag & Drop images or folder here",
            bg=BG, fg=BORDER, font=("Segoe UI", 10),
        )
        # (tkinterdnd2 optional – hint shown only)

    # ── File management ───────────────────────────────────────────────────────

    def _open_images(self):
        paths = filedialog.askopenfilenames(
            title="Select images",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All", "*.*")]
        )
        if paths:
            self._load_paths([Path(p) for p in paths])

    def _open_folder(self):
        folder = filedialog.askdirectory(title="Select input folder")
        if folder:
            paths = collect_images(Path(folder))
            self._load_paths(paths)

    def _set_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self._output_dir = Path(folder)
            self.log_panel.log(f"Output folder: {folder}", "info")
            self._update_status()

    def _load_paths(self, paths: list[Path]):
        self._input_paths = paths
        self._current_idx = 0
        self.file_list.delete(0, "end")
        for p in paths:
            self.file_list.insert("end", p.name)
        if paths:
            self.file_list.selection_set(0)
            self._load_preview(0)
        self.log_panel.log(f"Loaded {len(paths)} image(s).", "info")
        self._update_status()

    def _load_preview(self, idx: int):
        if not self._input_paths or idx >= len(self._input_paths):
            return
        try:
            img = Image.open(self._input_paths[idx]).convert("RGBA")
            self._current_input_img = img
            self._current_output_img = None
            self.preview_in.show(img)
            self.preview_out.show(None)
            self._file_lbl.config(
                text=f"{idx+1} / {len(self._input_paths)}  –  {self._input_paths[idx].name}"
            )
        except Exception as e:
            self.log_panel.log(f"Cannot open {self._input_paths[idx].name}: {e}", "err")

    def _prev_file(self):
        if self._input_paths:
            self._current_idx = (self._current_idx - 1) % len(self._input_paths)
            self.file_list.selection_clear(0, "end")
            self.file_list.selection_set(self._current_idx)
            self._load_preview(self._current_idx)

    def _next_file(self):
        if self._input_paths:
            self._current_idx = (self._current_idx + 1) % len(self._input_paths)
            self.file_list.selection_clear(0, "end")
            self.file_list.selection_set(self._current_idx)
            self._load_preview(self._current_idx)

    def _on_list_select(self, _event):
        sel = self.file_list.curselection()
        if sel:
            self._current_idx = sel[0]
            self._load_preview(self._current_idx)

    # ── Processing ────────────────────────────────────────────────────────────

    def _get_output_dir(self) -> Path:
        if self._output_dir:
            return self._output_dir
        if self._input_paths:
            d = self._input_paths[0].parent / "output_nobg"
            d.mkdir(exist_ok=True)
            return d
        return Path("output_nobg")

    def _process_single(self):
        if not self._current_input_img:
            messagebox.showwarning("No image", "Please open an image first.")
            return
        rem, pre, post, opt = self.settings.build_configs()
        self._set_busy(True, "Processing…")

        def _run():
            try:
                img = self._current_input_img
                t0 = time.time()
                self._progress_var.set(5)

                preprocessed, orig_size, was_up = preprocess(img, pre)
                self._progress_var.set(10)

                def _cb(pct, msg):
                    self._progress_var.set(pct)
                    self.after(0, lambda: self._status_var.set(msg))

                result = remove_background(preprocessed, rem, progress_cb=_cb)
                result = postprocess(result, orig_size if was_up else None, post)
                elapsed = time.time() - t0

                self._current_output_img = result
                self.after(0, lambda: self.preview_out.show(result))
                self.after(0, lambda: self.log_panel.log(
                    f"✓ Done in {elapsed:.2f}s  —  {result.size[0]}×{result.size[1]}px", "ok"))
                self._progress_var.set(100)
            except Exception as e:
                self.after(0, lambda: self.log_panel.log(f"✗ Error: {e}", "err"))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=_run, daemon=True).start()

    def _start_batch(self):
        if not self._input_paths:
            messagebox.showwarning("No files", "Please open images or a folder first.")
            return
        if self._batch_thread and self._batch_thread.is_alive():
            messagebox.showinfo("Running", "Batch already running.")
            return

        rem, pre, post, opt = self.settings.build_configs()
        out_dir = self._get_output_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        self._cancel_flag.clear()
        self._set_busy(True, "Batch processing…")
        self.log_panel.log(f"▶ Batch: {len(self._input_paths)} files → {out_dir}", "info")

        def _run():
            ok = err = 0
            total = len(self._input_paths)
            for i, path in enumerate(self._input_paths):
                if self._cancel_flag.is_set():
                    self.after(0, lambda: self.log_panel.log("⛔ Cancelled.", "warn"))
                    break
                try:
                    self.after(0, lambda p=path, ii=i: (
                        self._status_var.set(f"[{ii+1}/{total}] {p.name}"),
                        self.file_list.selection_clear(0, "end"),
                        self.file_list.selection_set(ii),
                        self.file_list.see(ii),
                    ))
                    img = Image.open(path).convert("RGBA")
                    proc, orig_size, was_up = preprocess(img, pre)
                    result = remove_background(proc, rem)
                    result = postprocess(result, orig_size if was_up else None, post)
                    out_path = out_dir / path.stem
                    save_optimized(result, out_path, opt)
                    ok += 1
                    self.after(0, lambda p=path: self.log_panel.log(f"✓ {p.name}", "ok"))
                except Exception as e:
                    err += 1
                    self.after(0, lambda p=path, ex=e: self.log_panel.log(f"✗ {p.name}: {ex}", "err"))
                finally:
                    self._progress_var.set((i + 1) / total * 100)

            self.after(0, lambda: self.log_panel.log(
                f"Batch complete: {ok} ok / {err} errors  →  {out_dir}", "info"))
            self.after(0, lambda: self._set_busy(False))

        self._batch_thread = threading.Thread(target=_run, daemon=True)
        self._batch_thread.start()

    def _cancel_batch(self):
        self._cancel_flag.set()

    def _save_current(self):
        if not self._current_output_img:
            messagebox.showwarning("Nothing to save", "Process an image first.")
            return
        _, _, _, opt = self.settings.build_configs()
        ext = ".webp" if opt.format == "WEBP" else ".png"
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("PNG", "*.png"), ("WebP", "*.webp"), ("All", "*.*")],
        )
        if path:
            save_optimized(self._current_output_img, Path(path).with_suffix(""), opt)
            self.log_panel.log(f"💾 Saved: {path}", "ok")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool, msg: str = "Ready."):
        self._status_var.set(msg if busy else "Ready.")
        if not busy:
            self._progress_var.set(0)

    def _update_status(self):
        n = len(self._input_paths)
        out = str(self._output_dir) if self._output_dir else "(auto)"
        self._status_var.set(f"{n} file(s) loaded  ·  Output: {out}")


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = ImgToolApp()
    app.mainloop()
