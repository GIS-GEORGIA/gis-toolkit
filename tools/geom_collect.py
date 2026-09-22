# -*- coding: utf-8 -*-
"""გეომეტრიების შეგროვება — SHP/DXF/DWG ხიდან ერთ GeoPackage-ში.

მიეთითება საწყისი საქაღალდე; ხელსაწყო პოულობს ყველა ``.shp``/``.dxf``/``.dwg``
ფაილს (ქვესაქაღალდეებითურთ), კითხულობს გეომეტრიებს და აჯგუფებს სამ შრედ —
წერტილები / ხაზები / პოლიგონები — ერთ GeoPackage-ში.

სუფთა ლოგიკა ``geom_collect_core``-შია. DWG-ის წაკითხვა GDAL-ის CAD დრაივერზეა
დამოკიდებული (QGIS/OSGeo4W); თუ არაა, ეს ფაილები გამოტოვდება.
"""

import os
import queue
import subprocess
import sys
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tools.base import ToolFrame
from tools.tooltip import add_tip
from tools.geom_collect_core import (
    iter_geometry_files, collect_to_geopackage,
    VECTOR_FORMATS, GEOM_EXT, normalize_exts,
)


# ---- CRS არჩევანი: label → EPSG (None = ავტომატური) ------------------------
CRS_CHOICES = [
    ("auto", None),
    ("UTM 37N — EPSG:32637", 32637),
    ("UTM 38N — EPSG:32638", 32638),
]


# ---- თარგმანები ------------------------------------------------------------
CTR = {
    "heading":   {"en": "Collect geometry → GeoPackage",
                  "ka": "გეომეტრიების შეგროვება → GeoPackage"},
    "desc":      {"en": "Pick a source folder and tick which vector formats to "
                        "look for; every matching file inside it (and its "
                        "subfolders) is read and all geometries are merged into "
                        "ONE GeoPackage with three layers: points, lines, "
                        "polygons. Any GDAL vector format is supported. DWG needs "
                        "GDAL's CAD driver (QGIS/OSGeo4W); files it cannot read "
                        "are skipped and logged.",
                  "ka": "აირჩიე საწყისი საქაღალდე და მონიშნე რომელი ვექტორული "
                        "ფორმატები მოძებნოს; მასში (და ქვესაქაღალდეებში) ყველა "
                        "შესაბამისი ფაილი იკითხება და გეომეტრიები გროვდება ერთ "
                        "GeoPackage-ში სამ შრედ: წერტილები, ხაზები, პოლიგონები. "
                        "მხარდაჭერილია ნებისმიერი GDAL ვექტორული ფორმატი. DWG-ს "
                        "სჭირდება GDAL-ის CAD დრაივერი (QGIS/OSGeo4W); წაუკითხავი "
                        "ფაილები გამოტოვდება და ლოგში აისახება."},
    "source":    {"en": "Source:", "ka": "საწყისი:"},
    "out":       {"en": "Output .gpkg:", "ka": "გამომავალი .gpkg:"},

    # ფორმატების არჩევა
    "formats":   {"en": "Formats to search", "ka": "მოსაძებნი ფორმატები"},
    "fmt_all":   {"en": "Select all", "ka": "ყველა"},
    "fmt_none":  {"en": "Clear", "ka": "გასუფთავება"},
    "fmt_other": {"en": "Other:", "ka": "სხვა:"},
    "warn_fmt":  {"en": "Select at least one format.",
                  "ka": "მონიშნე მინიმუმ ერთი ფორმატი."},
    "tip_fmt_all": {"en": "Check every listed format.",
                    "ka": "ყველა ფორმატის მონიშვნა."},
    "tip_fmt_none": {"en": "Uncheck every format.",
                     "ka": "ყველა ფორმატის მოხსნა."},
    "tip_fmt_other": {"en": "Extra extensions to include, comma-separated "
                            "(e.g. “geojson, tab”). Any GDAL vector format works.",
                      "ka": "დამატებითი გაფართოებები, მძიმით (მაგ. „geojson, tab“). "
                            "ნებისმიერი GDAL ვექტორული ფორმატი მუშაობს."},
    "crs":       {"en": "Output CRS:", "ka": "გამომავალი CRS:"},
    "crs_auto":  {"en": "auto (first found)", "ka": "ავტომატური (პირველი ნაპოვნი)"},
    "browse":    {"en": "Browse…", "ka": "დათვალიერება…"},
    "recursive": {"en": "Include subfolders", "ka": "ქვესაქაღალდეებიც"},
    "btn_count": {"en": "Count", "ka": "დათვლა"},
    "btn_run":   {"en": "Collect", "ka": "შეგროვება"},
    "btn_run_busy": {"en": "Collecting…", "ka": "მიმდინარეობს…"},
    "btn_cancel": {"en": "✖ Cancel", "ka": "✖ გაუქმება"},
    "btn_open":  {"en": "Open folder", "ka": "საქაღალდის გახსნა"},

    "warn_source": {"en": "Specify a valid source folder.",
                    "ka": "მიუთითე არსებული საწყისი საქაღალდე."},
    "warn_out":   {"en": "Specify the output .gpkg path.",
                   "ka": "მიუთითე გამომავალი .gpkg გზა."},
    "count_n":    {"en": "{n} file(s) found (.shp/.dxf/.dwg).",
                   "ka": "ნაპოვნია {n} ფაილი (.shp/.dxf/.dwg)."},
    "count_none": {"en": "No SHP/DXF/DWG files in the source.",
                   "ka": "საწყისში SHP/DXF/DWG ფაილი არაა."},
    "confirm_t":  {"en": "Confirm collect", "ka": "შეგროვების დადასტურება"},
    "confirm_m":  {"en": "Read {n} file(s) and merge geometries into:\n{out}?",
                   "ka": "წავიკითხო {n} ფაილი და გავაერთიანო გეომეტრიები:\n{out}?"},
    "start":      {"en": "Reading {n} file(s)…", "ka": "იკითხება {n} ფაილი…"},
    "progress":   {"en": "Read {i}/{n}", "ka": "წაკითხულია {i}/{n}"},
    "writing":    {"en": "Writing GeoPackage…", "ka": "იწერება GeoPackage…"},
    "cancelling": {"en": "Cancelling…", "ka": "უქმდება…"},
    "cancelled":  {"en": "Collecting cancelled.", "ka": "შეგროვება გაუქმდა."},
    "done":       {"en": "Done — points {p}, lines {l}, polygons {g}. "
                        "Files: {ok} read, {sk} skipped. → {out}",
                  "ka": "დასრულდა — წერტილი {p}, ხაზი {l}, პოლიგონი {g}. "
                        "ფაილი: {ok} წაკითხული, {sk} გამოტოვ. → {out}"},
    "done_empty": {"en": "No geometry found — GeoPackage not created.",
                   "ka": "გეომეტრია ვერ მოიძებნა — GeoPackage არ შეიქმნა."},
    "err":        {"en": "Error", "ka": "შეცდომა"},
    "dep_err":    {"en": "This tool needs geopandas + pyogrio.\n{e}",
                   "ka": "ამ ხელსაწყოს სჭირდება geopandas + pyogrio.\n{e}"},

    # tooltip-ები
    "tip_src":    {"en": "Folder to scan for SHP/DXF/DWG (recursively).",
                   "ka": "საქაღალდე SHP/DXF/DWG-ის მოსაძებნად (ხე მთლიანად)."},
    "tip_out":    {"en": "Where to write the merged GeoPackage.",
                   "ka": "სად ჩაიწეროს გაერთიანებული GeoPackage."},
    "tip_crs":    {"en": "Coordinate system for the output. “auto” uses the first "
                         "CRS found; files without a CRS are assumed to match it.",
                   "ka": "გამომავალი კოორდინატთა სისტემა. „ავტომატური“ იყენებს "
                         "პირველ ნაპოვნ CRS-ს; უCRS ფაილები მასში ჩაითვლება."},
    "tip_recursive": {"en": "Also scan subfolders.", "ka": "ქვესაქაღალდეებიც დაისკანოს."},
    "tip_count":  {"en": "Count matching files without reading them.",
                   "ka": "ფაილების დათვლა წაკითხვის გარეშე."},
    "tip_run":    {"en": "Read all files and build the GeoPackage (with confirm).",
                   "ka": "ყველა ფაილის წაკითხვა და GeoPackage-ის აგება (დადასტურებით)."},
    "tip_cancel": {"en": "Stop the running collection.",
                   "ka": "მიმდინარე შეგროვების შეჩერება."},
    "tip_open":   {"en": "Open the output folder.", "ka": "გამომავალი საქაღალდის გახსნა."},
}


class GeomCollectTool(ToolFrame):
    tid = "geom_collect"
    CATALOG = CTR

    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    def build(self):
        pal = self.app.palette
        st = self._state()
        saved = self.app.get_tool_config(self.tid)

        self.busy = False
        self.msg_queue = queue.Queue()
        self._cancel_event = threading.Event()

        ttk.Label(self, text=self.tr("heading"),
                  font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"],
                  wraplength=760, justify="left").pack(anchor="w", pady=(0, 12))

        grid = ttk.Frame(self)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        # საწყისი
        ttk.Label(grid, text=self.tr("source")).grid(row=0, column=0, sticky="w")
        self.src_var = tk.StringVar(
            value=st.get("source") or saved.get("source") or "")
        ttk.Entry(grid, textvariable=self.src_var).grid(
            row=0, column=1, sticky="ew", padx=(6, 6), pady=2)
        add_tip(ttk.Button(grid, text=self.tr("browse"), command=self._pick_src),
                self.tr("tip_src")).grid(row=0, column=2)

        # გამომავალი
        ttk.Label(grid, text=self.tr("out")).grid(row=1, column=0, sticky="w")
        default_out = st.get("out") or saved.get("out") or os.path.join(
            os.path.expanduser("~"), "Desktop", "collected_geometry.gpkg")
        self.out_var = tk.StringVar(value=default_out)
        ttk.Entry(grid, textvariable=self.out_var).grid(
            row=1, column=1, sticky="ew", padx=(6, 6), pady=2)
        add_tip(ttk.Button(grid, text=self.tr("browse"), command=self._pick_out),
                self.tr("tip_out")).grid(row=1, column=2)

        # CRS
        ttk.Label(grid, text=self.tr("crs")).grid(row=2, column=0, sticky="w",
                                                  pady=(6, 0))
        self._crs_labels = [self.tr("crs_auto")] + [lbl for lbl, _e in CRS_CHOICES[1:]]
        self._crs_by_label = {self.tr("crs_auto"): None}
        for lbl, epsg in CRS_CHOICES[1:]:
            self._crs_by_label[lbl] = epsg
        saved_epsg = st.get("crs_epsg", saved.get("crs_epsg"))
        cur_label = next((lbl for lbl, e in
                          [(self.tr("crs_auto"), None)] + CRS_CHOICES[1:]
                          if e == saved_epsg), self.tr("crs_auto"))
        self.crs_var = tk.StringVar(value=cur_label)
        add_tip(ttk.Combobox(grid, textvariable=self.crs_var, state="readonly",
                             width=28, values=self._crs_labels),
                self.tr("tip_crs")).grid(row=2, column=1, sticky="w",
                                         padx=(6, 6), pady=(6, 0))

        # --- მოსაძებნი ფორმატები (მონიშვნა) ---
        saved_exts = set(st.get("exts") or saved.get("exts") or GEOM_EXT)
        fmt = ttk.LabelFrame(self, text=self.tr("formats"))
        fmt.pack(fill="x", pady=(8, 4))
        btns = ttk.Frame(fmt)
        btns.pack(fill="x", padx=6, pady=(4, 2))
        add_tip(ttk.Button(btns, text=self.tr("fmt_all"), width=10,
                           command=lambda: self._set_all_formats(True)),
                self.tr("tip_fmt_all")).pack(side="left")
        add_tip(ttk.Button(btns, text=self.tr("fmt_none"), width=12,
                           command=lambda: self._set_all_formats(False)),
                self.tr("tip_fmt_none")).pack(side="left", padx=(6, 0))

        grid_f = ttk.Frame(fmt)
        grid_f.pack(fill="x", padx=6, pady=(0, 4))
        self.fmt_vars = []                 # [(BooleanVar, (ext,…)), …]
        cols = 3
        for i, (label, exts) in enumerate(VECTOR_FORMATS):
            var = tk.BooleanVar(value=any(e in saved_exts for e in exts))
            ttk.Checkbutton(grid_f, text=label, variable=var).grid(
                row=i // cols, column=i % cols, sticky="w", padx=(0, 14), pady=1)
            self.fmt_vars.append((var, exts))

        other = ttk.Frame(fmt)
        other.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(other, text=self.tr("fmt_other")).pack(side="left")
        # „სხვა“ = მონიშნული ცნობილი ფორმატების გარეთ დარჩენილი გაფართოებები
        known = {e for _lbl, exts in VECTOR_FORMATS for e in exts}
        extra = [e for e in saved_exts if e not in known]
        self.other_var = tk.StringVar(value=", ".join(sorted(extra)))
        add_tip(ttk.Entry(other, textvariable=self.other_var, width=36),
                self.tr("tip_fmt_other")).pack(side="left", padx=(6, 0))

        # პარამეტრები + ღილაკები
        opt = ttk.Frame(self)
        opt.pack(fill="x", pady=(10, 4))
        self.recursive_var = tk.BooleanVar(value=st.get("recursive", True))
        add_tip(ttk.Checkbutton(opt, text=self.tr("recursive"),
                                variable=self.recursive_var),
                self.tr("tip_recursive")).pack(side="left")
        add_tip(ttk.Button(opt, text=self.tr("btn_count"), command=self._count),
                self.tr("tip_count")).pack(side="left", padx=(16, 4))
        self.run_btn = ttk.Button(opt, text=self.tr("btn_run"),
                                  style="Accent.TButton", command=self._start)
        self.run_btn.pack(side="left", padx=(0, 4))
        add_tip(self.run_btn, self.tr("tip_run"))
        self.cancel_btn = ttk.Button(opt, text=self.tr("btn_cancel"),
                                     command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(0, 4))
        add_tip(self.cancel_btn, self.tr("tip_cancel"))
        add_tip(ttk.Button(opt, text=self.tr("btn_open"), command=self._open_out),
                self.tr("tip_open")).pack(side="left")

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", pady=(6, 2))

        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status,
                  foreground=pal["muted"]).pack(anchor="w", pady=(0, 4))

        self.after(100, self._poll_queue)

    def save_state(self):
        st = self._state()
        st["source"] = self.src_var.get()
        st["out"] = self.out_var.get()
        st["recursive"] = self.recursive_var.get()
        st["crs_epsg"] = self._crs_by_label.get(self.crs_var.get())
        st["exts"] = list(self._selected_exts())

    # ---- ფორმატები ----
    def _set_all_formats(self, value):
        for var, _exts in self.fmt_vars:
            var.set(value)

    def _selected_exts(self):
        """მონიშნული ფორმატები + „სხვა“ ველი → გაფართოებების tuple (უნიკ.)."""
        out = []
        for var, exts in self.fmt_vars:
            if var.get():
                for e in exts:
                    if e not in out:
                        out.append(e)
        for e in normalize_exts(self.other_var.get()):
            if e not in out:
                out.append(e)
        return tuple(out)

    # ---- არჩევა ----
    def _pick_src(self):
        d = filedialog.askdirectory(initialdir=self.src_var.get() or None)
        if d:
            d = os.path.normpath(d)
            self.src_var.set(d)
            self.app.set_tool_config(self.tid, {"source": d})

    def _pick_out(self):
        p = filedialog.asksaveasfilename(
            title=self.tr("out"), defaultextension=".gpkg",
            initialfile=os.path.basename(self.out_var.get() or "collected_geometry.gpkg"),
            filetypes=[("GeoPackage", "*.gpkg")])
        if p:
            self.out_var.set(os.path.normpath(p))

    def _open_out(self):
        d = os.path.dirname(self.out_var.get().strip())
        if not d or not os.path.isdir(d):
            messagebox.showwarning("GIS_BOX", self.tr("warn_out"))
            return
        try:
            if sys.platform == "win32":
                os.startfile(d)                       # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:                        # noqa: BLE001
            messagebox.showerror(self.tr("err"), str(e))

    # ---- ვალიდაცია ----
    def _validate(self):
        source = self.src_var.get().strip()
        out = self.out_var.get().strip()
        if not source or not os.path.isdir(source):
            messagebox.showwarning("GIS_BOX", self.tr("warn_source"))
            return None
        if not out:
            messagebox.showwarning("GIS_BOX", self.tr("warn_out"))
            return None
        if not out.lower().endswith(".gpkg"):
            out += ".gpkg"
            self.out_var.set(out)
        exts = self._selected_exts()
        if not exts:
            messagebox.showwarning("GIS_BOX", self.tr("warn_fmt"))
            return None
        return source, out, self._crs_by_label.get(self.crs_var.get()), exts

    def _count(self):
        v = self._validate()
        if not v:
            return
        source, _out, _epsg, exts = v
        n = len(iter_geometry_files(source, exts, self.recursive_var.get()))
        msg = self.tr("count_n" if n else "count_none", n=n)
        self.status.set(msg)
        self.app.log(msg)

    # ---- გაშვება (ფონურ ნაკადში) ----
    def _start(self):
        if self.busy:
            return
        v = self._validate()
        if not v:
            return
        source, out, epsg, exts = v
        files = iter_geometry_files(source, exts, self.recursive_var.get())
        if not files:
            messagebox.showinfo("GIS_BOX", self.tr("count_none"))
            return
        if not messagebox.askyesno(self.tr("confirm_t"),
                                   self.tr("confirm_m", n=len(files), out=out)):
            return
        self.app.set_tool_config(self.tid,
                                 {"source": source, "out": out,
                                  "exts": list(exts)})

        self.busy = True
        self._cancel_event.clear()
        self.run_btn.configure(state="disabled", text=self.tr("btn_run_busy"))
        self.cancel_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=len(files))
        self.status.set(self.tr("start", n=len(files)))
        self.app.log("— " + self.tr("start", n=len(files)))

        threading.Thread(target=self._worker, args=(files, out, epsg),
                         daemon=True).start()

    def _worker(self, files, out, epsg):
        try:
            result = collect_to_geopackage(
                files, out, target_epsg=epsg,
                log=lambda m: self.msg_queue.put(("log", m)),
                progress=lambda i, n: self.msg_queue.put(("progress", (i, n))),
                cancel=self._cancel_event.is_set)
            self.msg_queue.put(("done", result))
        except ImportError as e:
            self.msg_queue.put(("dep_err", str(e)))
        except Exception as e:            # noqa: BLE001
            self.msg_queue.put(("fatal", str(e)))

    def _cancel(self):
        if self.busy:
            self._cancel_event.set()
            self.cancel_btn.configure(state="disabled")
            self.status.set(self.tr("cancelling"))

    def _poll_queue(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.app.log(payload)
                elif kind == "progress":
                    i, n = payload
                    self.progress.configure(maximum=max(1, n), value=i)
                    self.status.set(self.tr("progress", i=i, n=n))
                    if i == n:
                        self.status.set(self.tr("writing"))
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "dep_err":
                    self._reset_buttons()
                    messagebox.showerror(self.tr("err"),
                                         self.tr("dep_err", e=payload))
                elif kind == "fatal":
                    self._reset_buttons()
                    self.status.set(self.tr("err"))
                    messagebox.showerror(self.tr("err"), payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _reset_buttons(self):
        self.busy = False
        self.run_btn.configure(state="normal", text=self.tr("btn_run"))
        self.cancel_btn.configure(state="disabled")

    def _on_done(self, result):
        self._reset_buttons()
        if result.get("cancelled"):
            self.progress.configure(value=0)
            self.status.set(self.tr("cancelled"))
            self.app.log("— " + self.tr("cancelled"))
            return

        # შეცდომიანი ფაილები ლოგში (ცალკე)
        for path, note in result.get("errors", []):
            self.app.log("  ✗ {} — {}".format(os.path.basename(path), note))

        if not result.get("out_files"):
            self.status.set(self.tr("done_empty"))
            self.app.log("— " + self.tr("done_empty"))
            messagebox.showinfo("GIS_BOX", self.tr("done_empty"))
            return

        self.progress.configure(value=self.progress["maximum"])
        msg = self.tr("done", p=result["points"], l=result["lines"],
                      g=result["polygons"], ok=result["files_ok"],
                      sk=result["files_skipped"], out=result["out_path"])
        self.status.set(msg)
        self.app.log("— " + msg)
        messagebox.showinfo("GIS_BOX", msg)
