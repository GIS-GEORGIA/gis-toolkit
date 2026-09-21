# -*- coding: utf-8 -*-
"""დაცვის ზონის კვეთა — ნაკვეთის საზღვრის × დაცვის ზონის საზღვრის კვეთის წერტილები.

მიეთითება ნაკვეთის და დაცვის ზონის პოლიგონური shapefile-ები (დასამახსოვრებელი
ღილაკებით), აირჩევა კონკრეტული ზონა (ატრიბუტით — ველი+მნიშვნელობა — ან „ყველა“),
და იქმნება **წერტილოვანი shapefile** იმ ადგილებზე, სადაც ნაკვეთის საზღვარი კვეთს
ზონის საზღვარს (arcpy Intersect output_type="POINT"-ის ანალოგი, shapely-ით).

შედეგი პირდაპირ ეთანხმება „Shp → კოორდინატები“ ხელსაწყოს — ერთი ღილაკით
გადაეცემა (ან იქვე გამოაქვს Excel ცხრილი). სუფთა ლოგიკა ``zone_intersect_core``-შია.
"""

import os
import queue
import re
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tools.base import ToolFrame
from tools.tooltip import add_tip
from tools.zone_intersect_core import collect_points

ALL_SENTINEL = "— all —"          # „ყველა ზონა“ მარკერი value-combo-ში
_AUTO_FIELDS = ("zon", "zone", "ზონ", "type", "tip", "kind", "class", "name")


ZTR = {
    "heading":  {"en": "Zone intersection points",
                 "ka": "დაცვის ზონის კვეთის წერტილები"},
    "desc":     {"en": "Pick the parcel and protection-zone polygon shapefiles, "
                       "choose a zone, and create a point shapefile where the "
                       "parcel boundary crosses the zone boundary. The result "
                       "feeds straight into “Shp → coordinates”.",
                 "ka": "აირჩიე ნაკვეთის და დაცვის ზონის პოლიგონური shapefile-ები, "
                       "მიუთითე ზონა და შექმენი წერტილოვანი shapefile იქ, სადაც "
                       "ნაკვეთის საზღვარი კვეთს ზონის საზღვარს. შედეგი პირდაპირ "
                       "გადადის „Shp → კოორდინატებში“."},
    "parcel":   {"en": "Parcel shp:", "ka": "ნაკვეთის shp:"},
    "zone":     {"en": "Zone shp:", "ka": "ზონის shp:"},
    "out":      {"en": "Output folder:", "ka": "გამომავალი საქაღალდე:"},
    "browse":   {"en": "…", "ka": "…"},
    "remember": {"en": "💾 Remember", "ka": "💾 დამახსოვრება"},
    "zfield":   {"en": "Zone field:", "ka": "ზონის ველი:"},
    "zvalue":   {"en": "Zone value:", "ka": "ზონის მნიშვნელობა:"},
    "all_zones": {"en": "— all zones —", "ka": "— ყველა ზონა —"},
    "btn_create": {"en": "Create points", "ka": "წერტილების შექმნა"},
    "btn_busy": {"en": "Working…", "ka": "მიმდინარეობს…"},
    "btn_coords": {"en": "Open in Shp → coordinates",
                   "ka": "Shp → კოორდინატებში გახსნა"},
    "btn_excel": {"en": "Excel table", "ka": "Excel ცხრილი"},

    "cfg_saved": {"en": "Paths remembered.", "ka": "გზები დამახსოვრდა."},
    "warn_parcel": {"en": "Select a valid parcel shapefile.",
                    "ka": "აირჩიე ნაკვეთის shapefile."},
    "warn_zone": {"en": "Select a valid zone shapefile.",
                  "ka": "აირჩიე ზონის shapefile."},
    "warn_out": {"en": "Select an output folder.",
                 "ka": "აირჩიე გამომავალი საქაღალდე."},
    "warn_none": {"en": "No intersection points found — the boundaries do not "
                        "cross for the selected zone.",
                  "ka": "კვეთის წერტილი ვერ მოიძებნა — არჩეული ზონისთვის "
                        "საზღვრები არ იკვეთება."},
    "warn_nocreate": {"en": "Create the points first.",
                      "ka": "ჯერ წერტილები შექმენი."},
    "crs_warn": {"en": "The parcel shapefile has no CRS (.prj); output will have "
                       "none either and the zone must be chosen manually in "
                       "“Shp → coordinates”.",
                 "ka": "ნაკვეთის shapefile-ს CRS (.prj) არ აქვს; შედეგსაც არ "
                       "ექნება და UTM ზონა ხელით უნდა აირჩიო „Shp → კოორდინატებში“."},
    "reading_zone": {"en": "Reading zone attributes…", "ka": "იკითხება ზონის ატრიბუტები…"},
    "running":  {"en": "Computing intersection…", "ka": "მიმდინარეობს კვეთის გამოთვლა…"},
    "done":     {"en": "Done — {n} point(s). → {path}",
                 "ka": "დასრულდა — {n} წერტილი. → {path}"},
    "err":      {"en": "Error", "ka": "შეცდომა"},
    "dep_err":  {"en": "This tool needs geopandas + shapely.\n{e}",
                 "ka": "ამ ხელსაწყოს სჭირდება geopandas + shapely.\n{e}"},

    "tip_parcel": {"en": "Polygon shapefile of the parcel(s).",
                   "ka": "ნაკვეთ(ებ)ის პოლიგონური shapefile."},
    "tip_zone": {"en": "Polygon shapefile of the protection zone(s).",
                 "ka": "დაცვის ზონ(ებ)ის პოლიგონური shapefile."},
    "tip_out": {"en": "Folder where the point shapefile is written.",
                "ka": "საქაღალდე, სადაც წერტილოვანი shapefile ჩაიწერება."},
    "tip_remember": {"en": "Remember the parcel, zone and output paths.",
                     "ka": "ნაკვეთის, ზონისა და გამომავალი გზის დამახსოვრება."},
    "tip_zfield": {"en": "Attribute that distinguishes zones (e.g. I / II). "
                         "Optional — leave for “all zones”.",
                   "ka": "ატრიბუტი, რომელიც ზონებს არჩევს (მაგ. I / II). "
                         "არჩევითი — „ყველა ზონისთვის“ დატოვე."},
    "tip_zvalue": {"en": "Which zone value to intersect (or all zones).",
                   "ka": "რომელი ზონის მნიშვნელობა იკვეთოს (ან ყველა ზონა)."},
    "tip_create": {"en": "Compute the boundary-crossing points and write the "
                         "point shapefile.",
                   "ka": "საზღვრების კვეთის წერტილების გამოთვლა და წერტილოვანი "
                         "shapefile-ის ჩაწერა."},
    "tip_coords": {"en": "Open the created points in “Shp → coordinates”.",
                   "ka": "შექმნილი წერტილების გახსნა „Shp → კოორდინატებში“."},
    "tip_excel": {"en": "Open in “Shp → coordinates” and export the Excel table.",
                  "ka": "„Shp → კოორდინატებში“ გახსნა და Excel ცხრილის ექსპორტი."},
}


class ZoneIntersectTool(ToolFrame):
    tid = "zone_intersect"
    CATALOG = ZTR

    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    def build(self):
        pal = self.app.palette
        st = self._state()
        saved = self.app.get_tool_config(self.tid)

        self.busy = False
        self.msg_queue = queue.Queue()
        self._zone_meta = {}          # {field: [distinct values...]}
        self._last_output = None

        ttk.Label(self, text=self.tr("heading"),
                  font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"],
                  wraplength=760, justify="left").pack(anchor="w", pady=(0, 12))

        grid = ttk.Frame(self)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        def path_row(r, label, key, tip, on_set=None):
            ttk.Label(grid, text=self.tr(label)).grid(row=r, column=0, sticky="w",
                                                      pady=2)
            var = tk.StringVar(value=st.get(key) or saved.get(key) or "")
            ttk.Entry(grid, textvariable=var).grid(row=r, column=1, sticky="ew",
                                                   padx=(6, 6), pady=2)
            add_tip(ttk.Button(grid, text=self.tr("browse"), width=3,
                               command=lambda: self._pick(var, key, on_set)),
                    tip).grid(row=r, column=2)
            return var

        self.parcel_var = path_row(0, "parcel", "parcel", self.tr("tip_parcel"))
        self.zone_var = path_row(1, "zone", "zone", self.tr("tip_zone"),
                                 on_set=lambda: self._load_zone_meta())
        self.out_var = path_row(2, "out", "out", self.tr("tip_out"))

        add_tip(ttk.Button(grid, text=self.tr("remember"), command=self._remember),
                self.tr("tip_remember")).grid(row=3, column=1, sticky="w",
                                              padx=(6, 0), pady=(4, 0))

        # ზონის არჩევა (ველი + მნიშვნელობა)
        zsel = ttk.Frame(self)
        zsel.pack(fill="x", pady=(10, 4))
        ttk.Label(zsel, text=self.tr("zfield")).pack(side="left")
        self.zfield_var = tk.StringVar(value=st.get("zfield", ""))
        self.zfield_combo = ttk.Combobox(zsel, textvariable=self.zfield_var,
                                         state="readonly", width=18, values=[])
        self.zfield_combo.pack(side="left", padx=(6, 14))
        self.zfield_combo.bind("<<ComboboxSelected>>",
                               lambda _e: self._refresh_values())
        add_tip(self.zfield_combo, self.tr("tip_zfield"))
        ttk.Label(zsel, text=self.tr("zvalue")).pack(side="left")
        self.zvalue_var = tk.StringVar(value=st.get("zvalue", self.tr("all_zones")))
        self.zvalue_combo = ttk.Combobox(zsel, textvariable=self.zvalue_var,
                                         state="readonly", width=22,
                                         values=[self.tr("all_zones")])
        self.zvalue_combo.pack(side="left", padx=(6, 0))
        add_tip(self.zvalue_combo, self.tr("tip_zvalue"))

        # ღილაკები
        brow = ttk.Frame(self)
        brow.pack(fill="x", pady=(10, 4))
        self.create_btn = ttk.Button(brow, text=self.tr("btn_create"),
                                     command=self._create)
        self.create_btn.pack(side="left")
        add_tip(self.create_btn, self.tr("tip_create"))
        self.coords_btn = ttk.Button(brow, text=self.tr("btn_coords"),
                                     command=self._open_in_coords, state="disabled")
        self.coords_btn.pack(side="left", padx=(8, 0))
        add_tip(self.coords_btn, self.tr("tip_coords"))
        self.excel_btn = ttk.Button(brow, text=self.tr("btn_excel"),
                                    command=self._excel, state="disabled")
        self.excel_btn.pack(side="left", padx=(8, 0))
        add_tip(self.excel_btn, self.tr("tip_excel"))

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", pady=(6, 2))
        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status,
                  foreground=pal["muted"]).pack(anchor="w", pady=(0, 4))

        self.after(100, self._poll_queue)
        if self.zone_var.get().strip():
            self.after(0, self._load_zone_meta)

    def save_state(self):
        st = self._state()
        st["parcel"] = self.parcel_var.get()
        st["zone"] = self.zone_var.get()
        st["out"] = self.out_var.get()
        st["zfield"] = self.zfield_var.get()
        st["zvalue"] = self.zvalue_var.get()

    # ---- გზები ----
    def _pick(self, var, key, on_set=None):
        if key == "out":
            p = filedialog.askdirectory(initialdir=var.get() or None)
        else:
            p = filedialog.askopenfilename(
                initialdir=os.path.dirname(var.get()) if var.get() else None,
                filetypes=[("Shapefile", "*.shp"), ("All files", "*.*")])
        if p:
            var.set(os.path.normpath(p))
            if on_set:
                on_set()

    def _remember(self):
        self.app.set_tool_config(self.tid, {
            "parcel": self.parcel_var.get().strip(),
            "zone": self.zone_var.get().strip(),
            "out": self.out_var.get().strip(),
        })
        self.save_state()
        messagebox.showinfo("GIS_BOX", self.tr("cfg_saved"))

    # ---- ზონის ატრიბუტების წაკითხვა (ფონურ ნაკადში) ----
    def _load_zone_meta(self):
        zone = self.zone_var.get().strip()
        if not zone or not os.path.isfile(zone):
            return
        self.status.set(self.tr("reading_zone"))
        threading.Thread(target=self._zone_meta_worker, args=(zone,),
                         daemon=True).start()

    def _zone_meta_worker(self, zone):
        try:
            import pyogrio
            df = pyogrio.read_dataframe(zone, read_geometry=False)
            meta = {}
            for col in df.columns:
                try:
                    vals = sorted({str(v) for v in df[col].tolist()
                                   if v is not None and str(v).strip() != ""})
                except Exception:                  # noqa: BLE001
                    vals = []
                if vals:
                    meta[str(col)] = vals
            self.msg_queue.put(("zonemeta", meta))
        except Exception as e:                     # noqa: BLE001
            self.msg_queue.put(("zoneerr", str(e)))

    def _apply_zone_meta(self, meta):
        self._zone_meta = meta
        fields = list(meta.keys())
        self.zfield_combo["values"] = fields
        cur = self.zfield_var.get()
        if cur not in fields:
            # ავტო-შერჩევა — სავარაუდო ზონის ველი, თუ არა — ცარიელი
            auto = next((f for f in fields
                         if any(p in f.lower() for p in _AUTO_FIELDS)), "")
            self.zfield_var.set(auto)
        self._refresh_values()
        if not self.busy:
            self.status.set("")

    def _refresh_values(self):
        field = self.zfield_var.get()
        vals = self._zone_meta.get(field, [])
        allv = self.tr("all_zones")
        self.zvalue_combo["values"] = [allv] + vals
        if self.zvalue_var.get() not in ([allv] + vals):
            self.zvalue_var.set(allv)

    # ---- შექმნა ----
    def _create(self):
        if self.busy:
            return
        parcel = self.parcel_var.get().strip()
        zone = self.zone_var.get().strip()
        out = self.out_var.get().strip()
        if not parcel or not os.path.isfile(parcel):
            messagebox.showwarning("GIS_BOX", self.tr("warn_parcel"))
            return
        if not zone or not os.path.isfile(zone):
            messagebox.showwarning("GIS_BOX", self.tr("warn_zone"))
            return
        if not out or not os.path.isdir(out):
            messagebox.showwarning("GIS_BOX", self.tr("warn_out"))
            return
        field = self.zfield_var.get()
        value = self.zvalue_var.get()
        if value == self.tr("all_zones"):
            field, value = None, None

        self.busy = True
        self.create_btn.configure(state="disabled", text=self.tr("btn_busy"))
        self.progress.start(12)
        self.status.set(self.tr("running"))
        threading.Thread(target=self._worker,
                         args=(parcel, zone, out, field, value),
                         daemon=True).start()

    def _worker(self, parcel, zone, out, field, value):
        try:
            import geopandas as gpd

            pgdf = gpd.read_file(parcel)
            zgdf = gpd.read_file(zone)

            # ზონის ფილტრი ატრიბუტით
            if field and field in zgdf.columns and value is not None:
                zgdf = zgdf[zgdf[field].astype(str) == str(value)]

            # CRS — ზონა ნაკვეთის სისტემაში
            target_crs = pgdf.crs
            if target_crs is not None and zgdf.crs is not None \
                    and zgdf.crs != target_crs:
                zgdf = zgdf.to_crs(target_crs)

            parcels = [g for g in pgdf.geometry if g is not None]
            zones = [g for g in zgdf.geometry if g is not None]
            pts = collect_points(parcels, zones)

            zlabel = self._sanitize(value) if value else "all"
            base = os.path.splitext(os.path.basename(parcel))[0]
            out_path = os.path.join(out, "{}_{}_intersection.shp".format(
                self._sanitize(base), zlabel))

            self.msg_queue.put(("result", {
                "points": pts, "crs": target_crs, "out_path": out_path,
                "zvalue": value,
            }))
        except ImportError as e:
            self.msg_queue.put(("dep_err", str(e)))
        except Exception as e:                     # noqa: BLE001
            self.msg_queue.put(("fatal", str(e)))

    @staticmethod
    def _sanitize(text):
        s = re.sub(r"[^0-9A-Za-z._-]+", "_", str(text or "")).strip("_")
        return s or "zone"

    def _write_shp(self, pts, crs, out_path):
        """წერტილების ჩაწერა shapefile-ად (მთავარ ნაკადში — მსუბუქია)."""
        import geopandas as gpd
        from shapely.geometry import Point
        rows = [{"N": i, "X": round(x, 3), "Y": round(y, 3)}
                for i, (x, y) in enumerate(pts, start=1)]
        geoms = [Point(x, y) for x, y in pts]
        gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=crs)
        gdf.to_file(out_path, driver="ESRI Shapefile", encoding="utf-8")

    # ---- queue ----
    def _poll_queue(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "zonemeta":
                    self._apply_zone_meta(payload)
                elif kind == "zoneerr":
                    self.status.set("")
                    self.app.log("— zone: " + payload.splitlines()[0])
                elif kind == "result":
                    self._on_result(payload)
                elif kind == "dep_err":
                    self._reset()
                    messagebox.showerror(self.tr("err"),
                                         self.tr("dep_err", e=payload))
                elif kind == "fatal":
                    self._reset()
                    self.status.set(self.tr("err"))
                    messagebox.showerror(self.tr("err"), payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _reset(self):
        self.busy = False
        self.progress.stop()
        self.create_btn.configure(state="normal", text=self.tr("btn_create"))

    def _on_result(self, res):
        self._reset()
        pts = res["points"]
        if not pts:
            self.status.set(self.tr("warn_none"))
            messagebox.showinfo("GIS_BOX", self.tr("warn_none"))
            return
        try:
            self._write_shp(pts, res["crs"], res["out_path"])
        except Exception as e:                     # noqa: BLE001
            self.status.set(self.tr("err"))
            messagebox.showerror(self.tr("err"), str(e))
            return
        self._last_output = res["out_path"]
        self.coords_btn.configure(state="normal")
        self.excel_btn.configure(state="normal")
        msg = self.tr("done", n=len(pts), path=res["out_path"])
        self.status.set(msg)
        self.app.log("— " + msg)
        if res["crs"] is None:
            self.app.log("  ⚠ " + self.tr("crs_warn"))
        messagebox.showinfo("GIS_BOX", msg)

    # ---- ინტეგრაცია: Shp → კოორდინატები ----
    def _handoff(self):
        if not self._last_output or not os.path.exists(self._last_output):
            messagebox.showwarning("GIS_BOX", self.tr("warn_nocreate"))
            return None
        frame = self.app.show_tool_by_tid("shp_coords")
        if frame is not None and hasattr(frame, "load_external"):
            frame.load_external(self._last_output)
        return frame

    def _open_in_coords(self):
        self._handoff()

    def _excel(self):
        frame = self._handoff()
        if frame is not None and hasattr(frame, "_export"):
            frame._export()
