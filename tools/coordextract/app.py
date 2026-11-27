"""Tkinter GUI: extract a coordinate table from a map image.

Two tools in one window:

  * "OCR table"      -- draw a box around the printed No/X/Y table, read it with
                        OCR, edit any mistakes, export CSV/JSON.
  * "Geo-reference"  -- click grid intersections and type their real X/Y, then
                        click polygon corners to compute their real coordinates
                        (plus polygon area) via an affine fit.

The map can come from an image file, a PDF page (Open PDF…), or a screen grab of
any window (Grab screen) -- see capture.py.

ორენოვანი (en/ka): თარგმანები i18n.py-შია; ენა გადაეცემა კონსტრუქტორს.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageTk

from . import capture, export
from .georef import ControlPoint, GeoReferenceError, fit_affine, polygon_area
from .ocr import OCRUnavailable, available_backends, extract_table
from .i18n import make_tr
from ..xlsx_format import FileLockedError


class CoordExtractorApp:
    ZOOM_STEP = 1.25
    MIN_SCALE = 0.05
    MAX_SCALE = 8.0

    def __init__(self, container: tk.Misc, toplevel: Optional[tk.Tk] = None,
                 lang: str = "en"):
        # ``container`` — ის widget, რომელშიც UI შენდება (frame ან Tk root).
        # ``toplevel`` — ნამდვილი ფანჯარა (after / dialog / screen-grab-ისთვის).
        # ``lang``     — "en" ან "ka" (GIS_BOX-ში მთავარი აპლიკაცია გადასცემს).
        self.container = container
        self.root: tk.Misc = toplevel if toplevel is not None else container
        self._embedded = toplevel is not None
        self.tr = make_tr(lang)
        if not self._embedded:
            container.title(self.tr("title"))
            container.geometry("1300x820")

        self.cv_img: Optional[np.ndarray] = None   # original BGR image
        self.pil_img: Optional[Image.Image] = None
        self.tk_img: Optional[ImageTk.PhotoImage] = None
        self.scale = 1.0
        self.fit_scale = 1.0
        self.mode: Optional[str] = None            # None|crop|control|polygon

        # geo state
        self.control_points: List[ControlPoint] = []
        self.polygon_px: List[Tuple[float, float]] = []
        self.model = None

        # crop state
        self.crop_start: Optional[Tuple[float, float]] = None
        self.crop_rect_px: Optional[Tuple[int, int, int, int]] = None
        self._drag_id = None

        # pdf state
        self.pdf_doc = None
        self.pdf_page = 0
        self.pdf_dpi = 200

        self._build_ui()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        tr = self.tr
        toolbar = ttk.Frame(self.container, padding=4)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(toolbar, text=tr("btn_open_image"), command=self.open_image).pack(side=tk.LEFT)
        ttk.Button(toolbar, text=tr("btn_open_pdf"), command=self.open_pdf).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(toolbar, text=tr("btn_grab"), command=self.grab_from_screen).pack(side=tk.LEFT, padx=(4, 0))

        # PDF page navigation (enabled only while a PDF is loaded)
        self.page_frame = ttk.Frame(toolbar)
        self.page_frame.pack(side=tk.LEFT, padx=(8, 0))
        self.prev_btn = ttk.Button(self.page_frame, text="◀", width=3, command=self.prev_page)
        self.prev_btn.pack(side=tk.LEFT)
        self.page_var = tk.StringVar(value=tr("page_dash"))
        ttk.Label(self.page_frame, textvariable=self.page_var, width=10, anchor=tk.CENTER).pack(side=tk.LEFT)
        self.next_btn = ttk.Button(self.page_frame, text="▶", width=3, command=self.next_page)
        self.next_btn.pack(side=tk.LEFT)
        self._set_page_controls(enabled=False)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(toolbar, text=tr("btn_zoom_in"), command=lambda: self.zoom(self.ZOOM_STEP)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text=tr("btn_zoom_out"), command=lambda: self.zoom(1 / self.ZOOM_STEP)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text=tr("btn_fit"), command=self.fit_to_window).pack(side=tk.LEFT)

        self.status = tk.StringVar(value=tr("status_start"))
        ttk.Label(toolbar, textvariable=self.status).pack(side=tk.RIGHT)

        body = ttk.Panedwindow(self.container, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        # --- canvas with scrollbars ---
        canvas_frame = ttk.Frame(body)
        self.canvas = tk.Canvas(canvas_frame, background="#2b2b2b", highlightthickness=0)
        hbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        body.add(canvas_frame, weight=3)

        self.canvas.bind("<ButtonPress-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", self.on_wheel)          # Windows / macOS
        self.canvas.bind("<Button-4>", lambda e: self.zoom(self.ZOOM_STEP))   # Linux
        self.canvas.bind("<Button-5>", lambda e: self.zoom(1 / self.ZOOM_STEP))

        # --- right side notebook ---
        nb = ttk.Notebook(body)
        body.add(nb, weight=2)
        self._build_ocr_tab(nb)
        self._build_geo_tab(nb)

    def _build_ocr_tab(self, nb: ttk.Notebook):
        tr = self.tr
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text=tr("tab_ocr"))

        row = ttk.Frame(tab)
        row.pack(fill=tk.X)
        ttk.Label(row, text=tr("lbl_backend")).pack(side=tk.LEFT)
        backs = available_backends() or [tr("backend_none")]
        self.backend_var = tk.StringVar(value=backs[0])
        ttk.Combobox(row, textvariable=self.backend_var, values=backs,
                     width=14, state="readonly").pack(side=tk.LEFT, padx=4)

        ttk.Button(tab, text=tr("ocr_mark"),
                   command=lambda: self.set_mode("crop")).pack(fill=tk.X, pady=(6, 2))
        ttk.Button(tab, text=tr("ocr_read"),
                   command=self.run_ocr).pack(fill=tk.X, pady=2)

        cols = ("no", "x", "y")
        self.ocr_tree = ttk.Treeview(tab, columns=cols, show="headings", height=12)
        for c, w in zip(cols, (50, 130, 130)):
            self.ocr_tree.heading(c, text=c.upper())
            self.ocr_tree.column(c, width=w, anchor=tk.CENTER)
        self.ocr_tree.pack(fill=tk.BOTH, expand=True, pady=6)
        self.ocr_tree.bind("<Double-1>", lambda e: self._edit_cell(self.ocr_tree, e))

        editrow = ttk.Frame(tab)
        editrow.pack(fill=tk.X)
        ttk.Button(editrow, text=tr("tbl_add_row"), command=lambda: self.ocr_tree.insert("", tk.END, values=("", "", ""))).pack(side=tk.LEFT)
        ttk.Button(editrow, text=tr("tbl_del_row"), command=lambda: self._delete_selected(self.ocr_tree)).pack(side=tk.LEFT, padx=4)

        exp = ttk.Frame(tab)
        exp.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(exp, text=tr("exp_excel"), command=lambda: self._export(self.ocr_tree, "xlsx")).pack(side=tk.LEFT)
        ttk.Button(exp, text=tr("exp_csv"), command=lambda: self._export(self.ocr_tree, "csv")).pack(side=tk.LEFT, padx=4)
        ttk.Button(exp, text=tr("exp_json"), command=lambda: self._export(self.ocr_tree, "json")).pack(side=tk.LEFT)
        ttk.Button(exp, text=tr("exp_format"), command=self._format_excel).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(tab, text=tr("ocr_tip"), foreground="#888").pack(anchor=tk.W, pady=(6, 0))

    def _build_geo_tab(self, nb: ttk.Notebook):
        tr = self.tr
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text=tr("tab_geo"))

        ttk.Label(tab, text=tr("geo_cp_header"),
                  font=("", 9, "bold")).pack(anchor=tk.W)
        ttk.Button(tab, text=tr("geo_add_cp"),
                   command=lambda: self.set_mode("control")).pack(fill=tk.X, pady=2)

        cp_cols = ("px", "py", "X", "Y")
        self.cp_tree = ttk.Treeview(tab, columns=cp_cols, show="headings", height=5)
        for c in cp_cols:
            self.cp_tree.heading(c, text=c)
            self.cp_tree.column(c, width=80, anchor=tk.CENTER)
        self.cp_tree.pack(fill=tk.X, pady=2)
        ttk.Button(tab, text=tr("geo_del_cp"),
                   command=self._delete_selected_cp).pack(anchor=tk.W)

        self.rmse_var = tk.StringVar(value=tr("fit_none"))
        ttk.Label(tab, textvariable=self.rmse_var).pack(anchor=tk.W, pady=(2, 8))

        ttk.Separator(tab).pack(fill=tk.X, pady=4)

        ttk.Label(tab, text=tr("geo_poly_header"), font=("", 9, "bold")).pack(anchor=tk.W)
        ttk.Button(tab, text=tr("geo_add_vertex"),
                   command=lambda: self.set_mode("polygon")).pack(fill=tk.X, pady=2)
        ttk.Button(tab, text=tr("geo_clear_poly"), command=self.clear_polygon).pack(anchor=tk.W)
        ttk.Button(tab, text=tr("geo_compute"), command=self.compute_geo).pack(fill=tk.X, pady=(4, 2))

        geo_cols = ("no", "x", "y")
        self.geo_tree = ttk.Treeview(tab, columns=geo_cols, show="headings", height=8)
        for c, w in zip(geo_cols, (50, 130, 130)):
            self.geo_tree.heading(c, text=c.upper())
            self.geo_tree.column(c, width=w, anchor=tk.CENTER)
        self.geo_tree.pack(fill=tk.BOTH, expand=True, pady=6)

        self.area_var = tk.StringVar(value=tr("area_none"))
        ttk.Label(tab, textvariable=self.area_var).pack(anchor=tk.W)

        exp = ttk.Frame(tab)
        exp.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(exp, text=tr("exp_excel"), command=lambda: self._export(self.geo_tree, "xlsx")).pack(side=tk.LEFT)
        ttk.Button(exp, text=tr("exp_csv"), command=lambda: self._export(self.geo_tree, "csv")).pack(side=tk.LEFT, padx=4)
        ttk.Button(exp, text=tr("exp_json"), command=lambda: self._export(self.geo_tree, "json")).pack(side=tk.LEFT)
        ttk.Button(exp, text=tr("exp_format"), command=self._format_excel).pack(side=tk.LEFT, padx=(12, 0))

    # --------------------------------------------------------------- image --
    def _set_image(self, img: np.ndarray, source: str):
        """Load a BGR image into the canvas and reset all per-image state."""
        self.cv_img = img
        self.pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        self.control_points.clear()
        self.polygon_px.clear()
        self.crop_rect_px = None
        self.model = None
        for t in (self.cp_tree, self.geo_tree, self.ocr_tree):
            t.delete(*t.get_children())
        self.rmse_var.set(self.tr("fit_none"))
        self.area_var.set(self.tr("area_none"))
        self.root.after(50, self.fit_to_window)
        self.status.set(self.tr("img_size", src=source, w=img.shape[1], h=img.shape[0]))

    def open_image(self):
        path = filedialog.askopenfilename(
            title=self.tr("open_map_title"),
            filetypes=[(self.tr("ft_images"), "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
                       (self.tr("ft_all"), "*.*")],
        )
        if not path:
            return
        # cv2.imread chokes on non-ASCII paths on Windows; read bytes via numpy.
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            messagebox.showerror(self.tr("err_title"), self.tr("img_read_err", path=path))
            return
        self._close_pdf()
        self._set_image(img, self.tr("img_loaded", name=os.path.basename(path)))

    # ------------------------------------------------------------------ PDF --
    def open_pdf(self):
        path = filedialog.askopenfilename(
            title=self.tr("open_pdf_title"),
            filetypes=[(self.tr("ft_pdf"), "*.pdf"), (self.tr("ft_all"), "*.*")])
        if not path:
            return
        try:
            doc = capture.open_pdf(path)
        except Exception as e:
            messagebox.showerror(self.tr("pdf_cannot_title"), f"{type(e).__name__}: {e}")
            return
        self._close_pdf()
        self.pdf_doc = doc
        self.pdf_path = path
        self.pdf_page = 0
        self._render_pdf_page()
        self._set_page_controls(enabled=doc.page_count > 1)

    def _render_pdf_page(self):
        if self.pdf_doc is None:
            return
        img = capture.render_page(self.pdf_doc, self.pdf_page, dpi=self.pdf_dpi)
        name = os.path.basename(getattr(self, "pdf_path", "PDF"))
        self._set_image(img, self.tr("pdf_page", name=name, page=self.pdf_page + 1,
                                     total=self.pdf_doc.page_count))
        self.page_var.set(f"{self.pdf_page + 1} / {self.pdf_doc.page_count}")

    def prev_page(self):
        if self.pdf_doc and self.pdf_page > 0:
            self.pdf_page -= 1
            self._render_pdf_page()

    def next_page(self):
        if self.pdf_doc and self.pdf_page < self.pdf_doc.page_count - 1:
            self.pdf_page += 1
            self._render_pdf_page()

    def _set_page_controls(self, enabled: bool):
        state = ("!disabled",) if enabled else ("disabled",)
        self.prev_btn.state(state)
        self.next_btn.state(state)
        if not enabled and self.pdf_doc is None:
            self.page_var.set(self.tr("page_dash"))

    def _close_pdf(self):
        if self.pdf_doc is not None:
            try:
                self.pdf_doc.close()
            except Exception:
                pass
        self.pdf_doc = None
        self._set_page_controls(enabled=False)
        self.page_var.set(self.tr("page_dash"))

    # --------------------------------------------------------- screen grab --
    def grab_from_screen(self):
        try:
            img = capture.grab_screen_region(self.root, hint=self.tr("grab_hint"))
        except Exception as e:
            messagebox.showerror(self.tr("grab_failed_title"), f"{type(e).__name__}: {e}")
            return
        if img is None:
            self.status.set(self.tr("grab_cancelled"))
            return
        self._close_pdf()
        self._set_image(img, self.tr("img_captured"))

    def fit_to_window(self):
        if self.pil_img is None:
            return
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        iw, ih = self.pil_img.size
        self.fit_scale = min(cw / iw, ch / ih)
        self.scale = self.fit_scale
        self.render()

    def zoom(self, factor: float):
        if self.pil_img is None:
            return
        self.scale = max(self.MIN_SCALE, min(self.MAX_SCALE, self.scale * factor))
        self.render()

    def on_wheel(self, event):
        self.zoom(self.ZOOM_STEP if event.delta > 0 else 1 / self.ZOOM_STEP)

    def render(self):
        if self.pil_img is None:
            return
        iw, ih = self.pil_img.size
        dw, dh = max(1, int(iw * self.scale)), max(1, int(ih * self.scale))
        disp = self.pil_img.resize((dw, dh), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
        self.canvas.configure(scrollregion=(0, 0, dw, dh))
        self._draw_overlays()

    # --------------------------------------------------- coordinate mapping --
    def canvas_to_img(self, event) -> Tuple[float, float]:
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        return cx / self.scale, cy / self.scale

    def img_to_canvas(self, px: float, py: float) -> Tuple[float, float]:
        return px * self.scale, py * self.scale

    def _draw_overlays(self):
        # crop rectangle
        if self.crop_rect_px:
            x0, y0, x1, y1 = self.crop_rect_px
            cx0, cy0 = self.img_to_canvas(x0, y0)
            cx1, cy1 = self.img_to_canvas(x1, y1)
            self.canvas.create_rectangle(cx0, cy0, cx1, cy1, outline="#00e0ff", width=2, dash=(5, 3))

        # control points
        for i, cp in enumerate(self.control_points, 1):
            cx, cy = self.img_to_canvas(cp.px, cp.py)
            r = 5
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#ffcc00", outline="black")
            self.canvas.create_text(cx + 8, cy - 8, text=f"C{i}", fill="#ffcc00", anchor=tk.W)

        # polygon
        if self.polygon_px:
            pts = [self.img_to_canvas(px, py) for px, py in self.polygon_px]
            if len(pts) >= 2:
                flat = [c for p in pts for c in p]
                self.canvas.create_line(*flat, fill="#c000ff", width=2)
                if len(pts) >= 3:
                    self.canvas.create_line(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1],
                                            fill="#c000ff", width=2, dash=(4, 2))
            for i, (cx, cy) in enumerate(pts, 1):
                r = 4
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#c000ff", outline="white")
                self.canvas.create_text(cx + 8, cy + 8, text=str(i), fill="#c000ff", anchor=tk.W)

    # ---------------------------------------------------------------- modes --
    def set_mode(self, mode: Optional[str]):
        if self.cv_img is None:
            messagebox.showinfo(self.tr("no_image_title"), self.tr("no_image"))
            return
        self.mode = mode
        cursors = {"crop": "tcross", "control": "crosshair", "polygon": "crosshair"}
        self.canvas.configure(cursor=cursors.get(mode, ""))
        labels = {
            "crop": self.tr("mode_crop"),
            "control": self.tr("mode_control"),
            "polygon": self.tr("mode_polygon"),
        }
        self.status.set(labels.get(mode, ""))

    def on_click(self, event):
        if self.cv_img is None:
            return
        px, py = self.canvas_to_img(event)
        if self.mode == "crop":
            self.crop_start = (px, py)
        elif self.mode == "control":
            self._add_control_point(px, py)
        elif self.mode == "polygon":
            self.polygon_px.append((px, py))
            self.render()

    def on_drag(self, event):
        if self.mode == "crop" and self.crop_start is not None:
            px, py = self.canvas_to_img(event)
            x0, y0 = self.crop_start
            self.render()
            cx0, cy0 = self.img_to_canvas(x0, y0)
            cx1, cy1 = self.img_to_canvas(px, py)
            self.canvas.create_rectangle(cx0, cy0, cx1, cy1, outline="#00e0ff", width=2, dash=(5, 3))

    def on_release(self, event):
        if self.mode == "crop" and self.crop_start is not None:
            px, py = self.canvas_to_img(event)
            x0, y0 = self.crop_start
            iw, ih = self.pil_img.size
            x_lo, x_hi = sorted((x0, px))
            y_lo, y_hi = sorted((y0, py))
            x_lo = int(max(0, min(iw, x_lo)))
            x_hi = int(max(0, min(iw, x_hi)))
            y_lo = int(max(0, min(ih, y_lo)))
            y_hi = int(max(0, min(ih, y_hi)))
            if x_hi - x_lo > 5 and y_hi - y_lo > 5:
                self.crop_rect_px = (x_lo, y_lo, x_hi, y_hi)
            self.crop_start = None
            self.render()

    # ------------------------------------------------------------------ OCR --
    def run_ocr(self):
        if self.cv_img is None:
            messagebox.showinfo(self.tr("no_image_title"), self.tr("no_image"))
            return
        if not self.crop_rect_px:
            messagebox.showinfo(self.tr("no_sel_title"), self.tr("no_sel"))
            return
        x0, y0, x1, y1 = self.crop_rect_px
        crop = self.cv_img[y0:y1, x0:x1].copy()
        backend = self.backend_var.get()
        backend = backend if backend in available_backends() else None
        self.status.set(self.tr("ocr_running"))
        self.root.update_idletasks()
        try:
            result = extract_table(crop, backend=backend)
        except OCRUnavailable as e:
            messagebox.showerror(self.tr("ocr_unavail_title"), str(e))
            self.status.set(self.tr("ocr_backend_missing"))
            return
        except Exception as e:  # pragma: no cover - surface any backend error
            messagebox.showerror(self.tr("ocr_err_title"), f"{type(e).__name__}: {e}")
            self.status.set(self.tr("ocr_failed"))
            return

        self.ocr_tree.delete(*self.ocr_tree.get_children())
        for r in result.rows:
            x = "" if r.x is None else _fmt(r.x)
            y = "" if r.y is None else _fmt(r.y)
            self.ocr_tree.insert("", tk.END, values=(r.label, x, y))
        self.status.set(self.tr("ocr_done", backend=result.backend, n=len(result.rows)))
        if not result.rows:
            messagebox.showinfo(
                self.tr("ocr_no_rows_title"),
                self.tr("ocr_no_rows", raw=(result.raw_text[:800] or self.tr("raw_empty"))))

    # -------------------------------------------------------------- geo-ref --
    def _add_control_point(self, px: float, py: float):
        dlg = _XYDialog(self.root, px, py, self.tr)
        self.root.wait_window(dlg.top)
        if dlg.result is None:
            return
        X, Y = dlg.result
        self.control_points.append(ControlPoint(px=px, py=py, X=X, Y=Y))
        self.cp_tree.insert("", tk.END, values=(f"{px:.0f}", f"{py:.0f}", _fmt(X), _fmt(Y)))
        self.render()
        self._refit()

    def _refit(self):
        if len(self.control_points) < 2:
            self.model = None
            self.rmse_var.set(self.tr("fit_need"))
            return
        try:
            self.model = fit_affine(self.control_points)
        except GeoReferenceError as e:
            self.model = None
            self.rmse_var.set(self.tr("fit_error", e=e))
            return
        note = self.tr("fit_exact") if self.model.n_points == 2 else self.tr("fit_rmse", v=self.model.rmse)
        self.rmse_var.set(self.tr("fit_ok", n=self.model.n_points, note=note))

    def _delete_selected_cp(self):
        sel = self.cp_tree.selection()
        if not sel:
            return
        idxs = sorted((self.cp_tree.index(s) for s in sel), reverse=True)
        for i in idxs:
            del self.control_points[i]
        self.cp_tree.delete(*sel)
        self.render()
        self._refit()

    def clear_polygon(self):
        self.polygon_px.clear()
        self.geo_tree.delete(*self.geo_tree.get_children())
        self.area_var.set(self.tr("area_none"))
        self.render()

    def compute_geo(self):
        if self.model is None:
            messagebox.showinfo(self.tr("no_fit_title"), self.tr("no_fit"))
            return
        if len(self.polygon_px) < 1:
            messagebox.showinfo(self.tr("no_poly_title"), self.tr("no_poly"))
            return
        world = self.model.apply_many(self.polygon_px)
        self.geo_tree.delete(*self.geo_tree.get_children())
        for i, (X, Y) in enumerate(world, 1):
            self.geo_tree.insert("", tk.END, values=(i, _fmt(X), _fmt(Y)))
        if len(world) >= 3:
            area = polygon_area(world)
            self.area_var.set(self.tr("area_val", u=area, ha=area / 10000))
        else:
            self.area_var.set(self.tr("area_need"))
        self.status.set(self.tr("computed", n=len(world)))

    # ------------------------------------------------------ table utilities --
    def _edit_cell(self, tree: ttk.Treeview, event):
        item = tree.identify_row(event.y)
        col = tree.identify_column(event.x)
        if not item or not col:
            return
        col_idx = int(col[1:]) - 1
        x, y, w, h = tree.bbox(item, col)
        value = tree.item(item, "values")[col_idx]
        entry = ttk.Entry(tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, value)
        entry.focus_set()

        def commit(_=None):
            vals = list(tree.item(item, "values"))
            vals[col_idx] = entry.get()
            tree.item(item, values=vals)
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda e: entry.destroy())

    def _delete_selected(self, tree: ttk.Treeview):
        for s in tree.selection():
            tree.delete(s)

    def _export(self, tree: ttk.Treeview, fmt: str):
        rows = [tree.item(i, "values") for i in tree.get_children()]
        if not rows:
            messagebox.showinfo(self.tr("nothing_exp_title"), self.tr("nothing_exp"))
            return
        ext = {"csv": ".csv", "json": ".json", "xlsx": ".xlsx"}[fmt]
        path = filedialog.asksaveasfilename(defaultextension=ext,
                                            filetypes=[(fmt.upper(), f"*{ext}")])
        if not path:
            return
        geo_note = (self.tr("geo_note")
                    if tree is self.geo_tree and self.model is not None else None)
        try:
            if fmt == "csv":
                export.rows_to_csv(path, rows)
            elif fmt == "xlsx":
                export.rows_to_xlsx(path, rows, note=geo_note)
            else:
                extra = {"crs_note": geo_note} if geo_note else None
                export.rows_to_json(path, rows, extra=extra)
        except FileLockedError:
            messagebox.showerror(self.tr("export_failed"), self.tr("file_locked"))
            return
        except Exception as e:
            messagebox.showerror(self.tr("export_failed"), str(e))
            return
        if fmt == "xlsx":
            self._last_xlsx = path            # „Format Excel“-ის ნაგულისხმევი
        self.status.set(self.tr("saved", name=os.path.basename(path)))

    def _format_excel(self):
        """დაფორმატებს არსებულ .xlsx-ს: ორიგინალის გვერდით ამატებს გასუფთავებულ,
        ცენტრირებულ, ჩარჩოებიან ასლს (№/X/Y). ორიგინალს არ ცვლის."""
        initial = getattr(self, "_last_xlsx", "") or ""
        path = filedialog.askopenfilename(
            title=self.tr("pick_xlsx"),
            initialdir=os.path.dirname(initial) or None,
            initialfile=os.path.basename(initial),
            filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            n_busy = export.format_target_filled(path)
        except Exception as e:
            messagebox.showerror(self.tr("format_failed"), str(e))
            return
        if n_busy and not messagebox.askyesno("GIS_BOX", self.tr("format_busy", n=n_busy)):
            return
        try:
            _saved, n = export.format_xlsx(path)
        except FileLockedError:
            messagebox.showerror(self.tr("format_failed"), self.tr("file_locked"))
            return
        except Exception as e:
            messagebox.showerror(self.tr("format_failed"), str(e))
            return
        if n == 0:
            messagebox.showinfo(self.tr("format_failed"), self.tr("format_empty"))
            return
        self._last_xlsx = path
        msg = self.tr("format_done", n=n)
        self.status.set(msg)
        log = getattr(self.root, "log", None)
        if callable(log):
            log(msg)


class _XYDialog:
    """Tiny modal asking for real-world X and Y of a clicked grid point."""

    def __init__(self, parent, px, py, tr):
        self.result = None
        self.tr = tr
        top = self.top = tk.Toplevel(parent)
        top.title(tr("cp_title"))
        top.transient(parent)
        top.grab_set()
        ttk.Label(top, text=tr("cp_pixel", px=px, py=py)).grid(row=0, column=0, columnspan=2, padx=8, pady=(8, 4))
        ttk.Label(top, text=tr("cp_realx")).grid(row=1, column=0, sticky=tk.E, padx=6, pady=2)
        ttk.Label(top, text=tr("cp_realy")).grid(row=2, column=0, sticky=tk.E, padx=6, pady=2)
        self.x_ent = ttk.Entry(top)
        self.y_ent = ttk.Entry(top)
        self.x_ent.grid(row=1, column=1, padx=6, pady=2)
        self.y_ent.grid(row=2, column=1, padx=6, pady=2)
        self.x_ent.focus_set()
        btns = ttk.Frame(top)
        btns.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text=tr("ok"), command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text=tr("cancel"), command=top.destroy).pack(side=tk.LEFT, padx=4)
        top.bind("<Return>", lambda e: self._ok())
        top.bind("<Escape>", lambda e: top.destroy())

    def _ok(self):
        try:
            X = float(self.x_ent.get().replace(",", "."))
            Y = float(self.y_ent.get().replace(",", "."))
        except ValueError:
            messagebox.showerror(self.tr("cp_invalid_title"), self.tr("cp_invalid"), parent=self.top)
            return
        self.result = (X, Y)
        self.top.destroy()


def _fmt(v: float) -> str:
    if v is None:
        return ""
    v = round(float(v), 3)                 # 500020.0000001 from the affine fit -> "500020"
    if v.is_integer():
        return str(int(v))
    return f"{v:.3f}"


def main(lang: str = "en"):
    capture.enable_dpi_awareness()  # align screen grabs with physical pixels
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    CoordExtractorApp(root, lang=lang)
    root.mainloop()


if __name__ == "__main__":
    main()
