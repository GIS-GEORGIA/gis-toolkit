# -*- coding: utf-8 -*-
"""DWG/DXF → SHP/GPKG/GDB — ერთი ფაილის ან მთელი საქაღალდის კონვერტაცია.

მიეთითება ერთი .dxf/.dwg ფაილი **ან** საქაღალდე (ქვესაქაღალდეებით — ყველა
.dxf/.dwg ერთბაშად), აირჩევა გამომავალი ფორმატი (SHP / GPKG / GDB) და
საქაღალდე. სუფთა ლოგიკა ``dwg_convert_core``-შია — GDAL/pyogrio-ით, ღია
კოდით (arcpy არაა საჭირო). DXF ყოველთვის იკითხება; DWG-ს სჭირდება GDAL-ის
CAD დრაივერი (QGIS/OSGeo4W-ს ჩვეულებრივ აქვს) — თუ არაა, ის ფაილი
გამოტოვდება და ცხადად ჩაიწერება ლოგში.
"""

import os
import queue
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tools.base import ToolFrame
from tools.platform_utils import UI_FONT, open_path, default_desktop
from tools.tooltip import add_tip
from tools.dwg_convert_core import (
    convert_file, convert_batch, iter_source_files, FORMATS,
)


# ---- CRS არჩევანი: label → EPSG (None = უცვლელი/წყაროსეული) ----------------
CRS_CHOICES = [
    ("native", None),
    ("UTM 37N — EPSG:32637", 32637),
    ("UTM 38N — EPSG:32638", 32638),
]


DWT = {
    "heading":  {"en": "DWG/DXF → SHP/GPKG/GDB", "ka": "DWG/DXF → SHP/GPKG/GDB"},
    "desc":     {"en": "Convert one .dxf/.dwg file, or every one in a folder, "
                       "into ESRI Shapefile, GeoPackage or File Geodatabase — "
                       "open source, no ArcGIS or AutoCAD needed, nothing extra "
                       "to install. DXF always works. DWG is read by GNU "
                       "LibreDWG, bundled with this app (GPL-3.0) — it reliably "
                       "handles modern DWG (r13–r2018), unlike QGIS's own CAD "
                       "driver which only supports old DWG R2000. If a DWG "
                       "still fails, the log explains why (a specific known "
                       "limitation, not a bug here).",
                 "ka": "დააკონვერტირე ერთი .dxf/.dwg ფაილი, ან საქაღალდის ყველა "
                       "ასეთი, ESRI Shapefile / GeoPackage / File Geodatabase "
                       "ფორმატში — ღია კოდით, ArcGIS ან AutoCAD არ სჭირდება, "
                       "არაფრის დამატებით დაყენება. DXF ყოველთვის იკითხება. "
                       "DWG-ს კითხულობს GNU LibreDWG, ჩაშენებული ამ პროგრამაში "
                       "(GPL-3.0) — საიმედოდ ამუშავებს თანამედროვე DWG-საც "
                       "(r13–r2018), განსხვავებით QGIS-ის საკუთარი CAD "
                       "დრაივერისგან, რომელსაც მხოლოდ ძველი DWG R2000 შეუძლია. "
                       "თუ მაინც ჩავარდა, ლოგში ახსნილია რატომ (კონკრეტული "
                       "ცნობილი შეზღუდვა, არა ამ პროგრამის ხარვეზი)."},
    "source":   {"en": "Source:", "ka": "საწყისი:"},
    "pick_file": {"en": "📄 File…", "ka": "📄 ფაილი…"},
    "pick_folder": {"en": "📁 Folder…", "ka": "📁 საქაღალდე…"},
    "recursive": {"en": "Include subfolders (folder mode)",
                  "ka": "ქვესაქაღალდეებიც (საქაღალდის რეჟიმში)"},
    "out":      {"en": "Output folder:", "ka": "გამომავალი საქაღალდე:"},
    "browse":   {"en": "Browse…", "ka": "დათვალიერება…"},
    "format":   {"en": "Output format:", "ka": "გამომავალი ფორმატი:"},
    "fmt_shp":  {"en": "Shapefile (.shp)", "ka": "Shapefile (.shp)"},
    "fmt_gpkg": {"en": "GeoPackage (.gpkg)", "ka": "GeoPackage (.gpkg)"},
    "fmt_gdb":  {"en": "File Geodatabase (.gdb)", "ka": "File Geodatabase (.gdb)"},
    "crs":      {"en": "CRS:", "ka": "CRS:"},
    "crs_native": {"en": "native (keep source CRS)",
                   "ka": "წყაროსეული (უცვლელი)"},

    "btn_count": {"en": "Count", "ka": "დათვლა"},
    "btn_run":  {"en": "Convert", "ka": "კონვერტაცია"},
    "btn_run_busy": {"en": "Converting…", "ka": "მიმდინარეობს…"},
    "btn_cancel": {"en": "✖ Cancel", "ka": "✖ გაუქმება"},
    "btn_open": {"en": "Open output folder", "ka": "გამომავალი საქაღალდის გახსნა"},

    "warn_source": {"en": "Select a valid .dxf/.dwg file or a folder.",
                    "ka": "აირჩიე .dxf/.dwg ფაილი ან საქაღალდე."},
    "warn_out": {"en": "Select an output folder.",
                 "ka": "აირჩიე გამომავალი საქაღალდე."},
    "count_n": {"en": "{n} DXF/DWG file(s) found.",
                "ka": "ნაპოვნია {n} DXF/DWG ფაილი."},
    "count_none": {"en": "No .dxf/.dwg files in the source.",
                   "ka": "საწყისში .dxf/.dwg ფაილი არაა."},
    "confirm_t": {"en": "Confirm conversion", "ka": "კონვერტაციის დადასტურება"},
    "confirm_m": {"en": "Convert {n} file(s) to {fmt} in:\n{out}?",
                  "ka": "დავაკონვერტირო {n} ფაილი {fmt}-ში:\n{out}?"},
    "start":    {"en": "Converting {n} file(s)…", "ka": "მიმდინარეობს {n} ფაილის კონვერტაცია…"},
    "progress": {"en": "Converted {i}/{n}", "ka": "დასრულდა {i}/{n}"},
    "cancelling": {"en": "Cancelling…", "ka": "უქმდება…"},
    "cancelled": {"en": "Conversion cancelled.", "ka": "კონვერტაცია გაუქმდა."},
    "done":     {"en": "Done — {ok} converted, {empty} without geometry, "
                       "{sk} skipped. → {out}",
                 "ka": "დასრულდა — {ok} დაკონვერტირდა, {empty} გეომეტრიის "
                       "გარეშე, {sk} გამოტოვდა. → {out}"},
    "err":      {"en": "Error", "ka": "შეცდომა"},
    "dep_err":  {"en": "This tool needs geopandas + pyogrio.\n{e}",
                 "ka": "ამ ხელსაწყოს სჭირდება geopandas + pyogrio.\n{e}"},

    # DWG-სპეციფიკური მინიშნებები (convert_file-ის ``reason``-ის მიხედვით)
    "hint_old_driver": {"en": "{n} DWG file(s) could not be read — they were "
                              "saved with a newer AutoCAD version than the "
                              "open-source CAD driver (libopencad) supports "
                              "(it reliably reads only old DWG R2000 files). "
                              "This is a known limitation of the open-source "
                              "driver, not a bug here.\n\nFix: in AutoCAD, "
                              "Save As → DXF for those files, then convert the "
                              "DXF instead — it always works.",
                        "ka": "{n} DWG ფაილი ვერ წაიკითხა — ისინი შენახულია "
                              "ღია კოდის CAD დრაივერის (libopencad) მხარდაჭერაზე "
                              "უფრო ახალი AutoCAD-ის ვერსიით (საიმედოდ მხოლოდ "
                              "ძველ DWG R2000-ს კითხულობს). ეს ღია კოდის "
                              "დრაივერის ცნობილი შეზღუდვაა, არა ამ პროგრამის "
                              "ხარვეზი.\n\nგამოსავალი: AutoCAD-ში ამ ფაილებზე "
                              "Save As → DXF, შემდეგ DXF დააკონვერტირე — ის "
                              "ყოველთვის მუშაობს."},
    "hint_no_tool": {"en": "{n} DWG file(s) were skipped — no DWG reader is "
                          "available at all (neither the bundled LibreDWG "
                          "nor a system GDAL/QGIS install was found). This "
                          "usually means a packaging problem; installing "
                          "QGIS or OSGeo4W also fixes it.",
                     "ka": "{n} DWG ფაილი გამოტოვდა — DWG-ის წამკითხველი "
                          "საერთოდ ვერ მოიძებნა (არც ჩაშენებული LibreDWG და "
                          "არც სისტემური GDAL/QGIS). ეს ჩვეულებრივ packaging-"
                          "ის პრობლემას ნიშნავს; QGIS-ის ან OSGeo4W-ის "
                          "დაყენებაც აგვარებს."},
    "hint_gdal_dxf_gap": {"en": "{n} DWG file(s) converted successfully to "
                              "DXF, but GDAL's own DXF reader could not parse "
                              "a specific entity in the result (a rare "
                              "interoperability gap between two different "
                              "open-source projects — the DWG itself was read "
                              "fine). Try converting to a different output "
                              "format, or open the DWG in AutoCAD/QGIS and "
                              "re-save it there.",
                         "ka": "{n} DWG ფაილი წარმატებით დაკონვერტირდა "
                              "DXF-ად, მაგრამ GDAL-ის საკუთარმა DXF-რიდერმა "
                              "ვერ ამოიცნო შედეგში კონკრეტული ობიექტი (იშვიათი "
                              "შეუთავსებლობა ორ სხვადასხვა ღია კოდის პროექტს "
                              "შორის — თავად DWG კარგად წაიკითხა). სცადე სხვა "
                              "გამომავალი ფორმატი, ან DWG გახსენი AutoCAD/"
                              "QGIS-ში და იქ ხელახლა შეინახე."},

    "tip_pick_file": {"en": "Pick a single .dxf/.dwg file to convert.",
                      "ka": "აირჩიე ერთი გასაკონვერტირებელი .dxf/.dwg ფაილი."},
    "tip_pick_folder": {"en": "Pick a folder — every .dxf/.dwg inside it is "
                              "converted.",
                        "ka": "აირჩიე საქაღალდე — შიგნით ყველა .dxf/.dwg "
                              "დაკონვერტირდება."},
    "tip_recursive": {"en": "Also look in subfolders (only when the source "
                            "is a folder).",
                      "ka": "ქვესაქაღალდეებშიც მოძებნოს (მხოლოდ საქაღალდის "
                            "არჩევისას)."},
    "tip_out":  {"en": "Folder to write the converted file(s) into.",
                 "ka": "საქაღალდე, სადაც დაკონვერტირებული ფაილ(ებ)ი ჩაიწერება."},
    "tip_fmt":  {"en": "Shapefile/File Geodatabase split mixed geometry (a "
                       "DXF layer can hold points+lines+polygons) into "
                       "separate point/line/polygon outputs; GeoPackage "
                       "keeps them together in one layer.",
                 "ka": "Shapefile/File Geodatabase-ს ცალკე გამოაქვს წერტილი/"
                       "ხაზი/პოლიგონი (DXF-ის შრეში სამივე ერთად შეიძლება "
                       "იყოს); GeoPackage-ში ერთ შრეში ერთდება."},
    "tip_crs":  {"en": "Reproject the output, or keep each file's own CRS.",
                 "ka": "გამომავალის რეპროექცია, ან თითო ფაილის საკუთარი "
                       "CRS-ის შენარჩუნება."},
    "tip_count": {"en": "Count matching files without converting them.",
                  "ka": "შესაბამისი ფაილების დათვლა კონვერტაციის გარეშე."},
    "tip_run":  {"en": "Convert now (with confirmation).",
                 "ka": "კონვერტაცია ახლავე (დადასტურებით)."},
    "tip_cancel": {"en": "Stop the running conversion.",
                   "ka": "მიმდინარე კონვერტაციის შეჩერება."},
    "tip_open": {"en": "Open the output folder.", "ka": "გამომავალი საქაღალდის გახსნა."},
}


class DwgConvertTool(ToolFrame):
    tid = "dwg_convert"
    CATALOG = DWT

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
                  font=(UI_FONT, 13, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"],
                  wraplength=760, justify="left").pack(anchor="w", pady=(0, 12))

        grid = ttk.Frame(self)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        # --- საწყისი: ერთი ფაილი ან საქაღალდე ---
        ttk.Label(grid, text=self.tr("source")).grid(row=0, column=0, sticky="w")
        self.src_var = tk.StringVar(
            value=st.get("source") or saved.get("source") or "")
        ttk.Entry(grid, textvariable=self.src_var).grid(
            row=0, column=1, sticky="ew", padx=(6, 6), pady=2)
        srcbtns = ttk.Frame(grid)
        srcbtns.grid(row=0, column=2)
        add_tip(ttk.Button(srcbtns, text=self.tr("pick_file"),
                           command=self._pick_file),
                self.tr("tip_pick_file")).pack(side="left")
        add_tip(ttk.Button(srcbtns, text=self.tr("pick_folder"),
                           command=self._pick_folder),
                self.tr("tip_pick_folder")).pack(side="left", padx=(4, 0))

        self.recursive_var = tk.BooleanVar(value=st.get("recursive", True))
        add_tip(ttk.Checkbutton(grid, text=self.tr("recursive"),
                                variable=self.recursive_var),
                self.tr("tip_recursive")).grid(row=1, column=1, sticky="w",
                                               padx=(6, 0), pady=(0, 6))

        # --- გამომავალი საქაღალდე ---
        ttk.Label(grid, text=self.tr("out")).grid(row=2, column=0, sticky="w")
        default_out = st.get("out") or saved.get("out") or os.path.join(
            default_desktop(), "converted")
        self.out_var = tk.StringVar(value=default_out)
        ttk.Entry(grid, textvariable=self.out_var).grid(
            row=2, column=1, sticky="ew", padx=(6, 6), pady=2)
        add_tip(ttk.Button(grid, text=self.tr("browse"), command=self._pick_out),
                self.tr("tip_out")).grid(row=2, column=2)

        # --- ფორმატი + CRS ---
        frow = ttk.Frame(self)
        frow.pack(fill="x", pady=(8, 0))
        ttk.Label(frow, text=self.tr("format")).pack(side="left")
        self.fmt_var = tk.StringVar(value=st.get("format", "gpkg"))
        for key, label_key in (("shp", "fmt_shp"), ("gpkg", "fmt_gpkg"),
                               ("gdb", "fmt_gdb")):
            add_tip(ttk.Radiobutton(frow, text=self.tr(label_key), value=key,
                                    variable=self.fmt_var),
                    self.tr("tip_fmt")).pack(side="left", padx=(8, 0))

        crow = ttk.Frame(self)
        crow.pack(fill="x", pady=(6, 4))
        ttk.Label(crow, text=self.tr("crs")).pack(side="left")
        self._crs_labels = [self.tr("crs_native")] + \
            [lbl for lbl, _e in CRS_CHOICES[1:]]
        self._crs_by_label = {self.tr("crs_native"): None}
        for lbl, epsg in CRS_CHOICES[1:]:
            self._crs_by_label[lbl] = epsg
        saved_epsg = st.get("crs_epsg", saved.get("crs_epsg"))
        cur_label = next((lbl for lbl, e in
                          [(self.tr("crs_native"), None)] + CRS_CHOICES[1:]
                          if e == saved_epsg), self.tr("crs_native"))
        self.crs_var = tk.StringVar(value=cur_label)
        add_tip(ttk.Combobox(crow, textvariable=self.crs_var, state="readonly",
                             width=28, values=self._crs_labels),
                self.tr("tip_crs")).pack(side="left", padx=(6, 0))

        # --- ღილაკები ---
        opt = ttk.Frame(self)
        opt.pack(fill="x", pady=(10, 4))
        add_tip(ttk.Button(opt, text=self.tr("btn_count"), command=self._count),
                self.tr("tip_count")).pack(side="left")
        self.run_btn = ttk.Button(opt, text=self.tr("btn_run"),
                                  style="Accent.TButton", command=self._start)
        self.run_btn.pack(side="left", padx=(8, 4))
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
        st["recursive"] = self.recursive_var.get()
        st["out"] = self.out_var.get()
        st["format"] = self.fmt_var.get()
        st["crs_epsg"] = self._crs_by_label.get(self.crs_var.get())

    # ---- არჩევა ----
    def _pick_file(self):
        p = filedialog.askopenfilename(
            initialdir=os.path.dirname(self.src_var.get()) or None,
            filetypes=[("DXF/DWG", "*.dxf *.dwg"), ("All files", "*.*")])
        if p:
            p = os.path.normpath(p)
            self.src_var.set(p)
            self.app.set_tool_config(self.tid, {"source": p})

    def _pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.src_var.get() or None)
        if d:
            d = os.path.normpath(d)
            self.src_var.set(d)
            self.app.set_tool_config(self.tid, {"source": d})

    def _pick_out(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get() or None)
        if d:
            self.out_var.set(os.path.normpath(d))

    def _open_out(self):
        d = self.out_var.get().strip()
        if not d or not os.path.isdir(d):
            messagebox.showwarning("GIS_BOX", self.tr("warn_out"))
            return
        try:
            open_path(d)
        except Exception as e:                        # noqa: BLE001
            messagebox.showerror(self.tr("err"), str(e))

    # ---- ვალიდაცია ----
    def _validate(self):
        source = self.src_var.get().strip()
        out = self.out_var.get().strip()
        if not source or not (os.path.isfile(source) or os.path.isdir(source)):
            messagebox.showwarning("GIS_BOX", self.tr("warn_source"))
            return None
        if not out:
            messagebox.showwarning("GIS_BOX", self.tr("warn_out"))
            return None
        epsg = self._crs_by_label.get(self.crs_var.get())
        return source, out, self.fmt_var.get(), epsg

    def _files_for(self, source):
        if os.path.isfile(source):
            return [source]
        return list(iter_source_files(source, self.recursive_var.get()))

    def _count(self):
        v = self._validate()
        if not v:
            return
        source, _out, _fmt, _epsg = v
        n = len(self._files_for(source))
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
        source, out, fmt, epsg = v
        files = self._files_for(source)
        if not files:
            messagebox.showinfo("GIS_BOX", self.tr("count_none"))
            return
        fmt_label = self.tr("fmt_" + fmt)
        if not messagebox.askyesno(self.tr("confirm_t"),
                                   self.tr("confirm_m", n=len(files),
                                          fmt=fmt_label, out=out)):
            return
        self.app.set_tool_config(self.tid, {"source": source, "out": out,
                                            "format": fmt})

        self.busy = True
        self._cancel_event.clear()
        self.run_btn.configure(state="disabled", text=self.tr("btn_run_busy"))
        self.cancel_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=len(files))
        self.status.set(self.tr("start", n=len(files)))
        self.app.log("— " + self.tr("start", n=len(files)))

        threading.Thread(target=self._worker, args=(files, out, fmt, epsg),
                         daemon=True).start()

    def _worker(self, files, out, fmt, epsg):
        try:
            result = convert_batch(
                files, out, fmt, target_epsg=epsg,
                log=lambda m: self.msg_queue.put(("log", m)),
                progress=lambda i, n: self.msg_queue.put(("progress", (i, n))),
                cancel=self._cancel_event.is_set)
            result["out"] = out
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

        self.progress.configure(value=self.progress["maximum"])
        msg = self.tr("done", ok=result["files_ok"], empty=result["files_empty"],
                      sk=result["files_skipped"], out=result["out"])
        self.status.set(msg)
        self.app.log("— " + msg)

        # DWG-სპეციფიკური მინიშნება — ერთი შეჯამებული დიალოგი, არა თითო ფაილზე
        by_reason = {}
        for r in result.get("results", []):
            reason = r.get("reason")
            if reason:
                by_reason[reason] = by_reason.get(reason, 0) + 1
        hints = [self.tr("hint_" + reason.split("_", 1)[1], n=n)
                for reason, n in by_reason.items()
                if reason in ("dwg_old_driver", "dwg_no_tool", "dwg_gdal_dxf_gap")]

        messagebox.showinfo("GIS_BOX", msg)
        for hint in hints:
            messagebox.showwarning("GIS_BOX", hint)
