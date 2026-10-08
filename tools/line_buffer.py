# -*- coding: utf-8 -*-
"""ბუფერების აგება — ხაზოვანი shapefile-იდან გაზსადენის დაცვის ზონები.

აირჩევა საქაღალდე და მასში ხაზოვანი shapefile, ბუფერის ტიპი (1/2/3) და ის
ბუფერები, რომლებიც გინდა; თითო ბუფერი ცალკე shapefile-ად ინახება მითითებულ
საქაღალდეში (``gas_protection_zone_1_1.shp`` …, ინდექსი ავტომატურად იზრდება).
სუფთა ლოგიკა ``line_buffer_core``-შია.
"""

import os
import queue
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tools.base import ToolFrame
from tools.platform_utils import UI_FONT
from tools.tooltip import add_tip
from tools.line_buffer_core import BUFFER_TYPES, build_buffer, output_path, plan_crs

LBR = {
    "heading": {"en": "Buffers from a line layer",
                "ka": "ბუფერების აგება ხაზოვანი შრიდან"},
    "desc": {"en": "Pick a line shapefile, a buffer type and the buffers you need; "
                   "each buffer is written as its own shapefile. Lines are merged "
                   "first, so every buffer is a single dissolved polygon.",
             "ka": "აირჩიე ხაზოვანი shapefile, ბუფერის ტიპი და საჭირო ბუფერები; "
                   "თითო ბუფერი ცალკე shapefile-ად ჩაიწერება. ხაზები ჯერ "
                   "გაერთიანდება, ამიტომ ყოველი ბუფერი ერთიანი (dissolve) "
                   "პოლიგონია."},
    "section": {"en": "Line layer", "ka": "ხაზოვანი შრე"},
    "folder": {"en": "Line layer folder:", "ka": "ხაზოვანი შრის საქაღალდე:"},
    "shp": {"en": "Line shapefile:", "ka": "ხაზოვანი shapefile:"},
    "out": {"en": "Output folder:", "ka": "გამომავალი საქაღალდე:"},
    "browse": {"en": "…", "ka": "…"},
    "rescan": {"en": "Rescan", "ka": "თავიდან სკანირება"},
    "remember": {"en": "💾 Remember", "ka": "💾 დამახსოვრება"},
    "type_box": {"en": "Buffer type", "ka": "ბუფერის ტიპი"},
    "type_n": {"en": "Type {n}", "ka": "ტიპი {n}"},
    "zones_box": {"en": "Buffers to build", "ka": "აგებული ბუფერები"},
    "zone_row": {"en": "{d} m  →  {name}", "ka": "{d} მ  →  {name}"},
    "btn_build": {"en": "Build buffers", "ka": "ბუფერების აგება"},
    "btn_busy": {"en": "Working…", "ka": "მიმდინარეობს…"},
    "cfg_saved": {"en": "Paths remembered.", "ka": "გზები დამახსოვრდა."},
    "no_lines": {"en": "No line shapefiles found in the folder.",
                 "ka": "საქაღალდეში ხაზოვანი shapefile ვერ მოიძებნა."},
    "found": {"en": "Found {n} line shapefile(s).",
              "ka": "ნაპოვნია {n} ხაზოვანი shapefile."},
    "warn_shp": {"en": "Choose a line shapefile.", "ka": "აირჩიე ხაზოვანი shapefile."},
    "warn_out": {"en": "Choose an output folder.",
                 "ka": "აირჩიე გამომავალი საქაღალდე."},
    "warn_zone": {"en": "Tick at least one buffer.",
                  "ka": "მონიშნე მინიმუმ ერთი ბუფერი."},
    "no_crs": {"en": "The shapefile has no CRS (.prj) — the UTM zone cannot be "
                     "determined. Assign EPSG:32637 or EPSG:32638 first.",
               "ka": "shapefile-ს CRS (.prj) არ აქვს — UTM ზონა ვერ დგინდება. "
                     "ჯერ მიანიჭე EPSG:32637 ან EPSG:32638."},
    "convert_q": {"en": "The layer is in {cur}. Buffers are built only in EPSG:32637 / "
                        "EPSG:32638.\n\nConvert it to EPSG:{epsg} (UTM zone {zone}, by the "
                        "layer's location) and build the buffers there? The source "
                        "file is not changed.",
                  "ka": "შრე არის {cur}-ში. ბუფერები იგება მხოლოდ EPSG:32637 / "
                        "EPSG:32638-ში.\n\nგადავიყვანო EPSG:{epsg}-ში (UTM ზონა {zone}, "
                        "შრის მდებარეობის მიხედვით) და იქ ავაგო ბუფერები? "
                        "საწყისი ფაილი არ შეიცვლება."},
    "no_geom": {"en": "The layer has no usable line geometry.",
                "ka": "შრეში გამოსადეგი ხაზოვანი გეომეტრია არ არის."},
    "reproj": {"en": "Converted from {cur} to EPSG:{epsg} for the buffers.",
               "ka": "{cur}-დან გადაყვანილია EPSG:{epsg}-ში ბუფერებისთვის."},
    "running": {"en": "Building buffers…", "ka": "ბუფერები იგება…"},
    "wrote": {"en": "✓ {d} m → {path}", "ka": "✓ {d} მ → {path}"},
    "done": {"en": "Done — {n} buffer(s) written to {out}",
             "ka": "დასრულდა — {n} ბუფერი ჩაიწერა: {out}"},
    "err": {"en": "Error", "ka": "შეცდომა"},
    "dep_err": {"en": "This tool needs geopandas + shapely.\n{e}",
                "ka": "ამ ხელსაწყოს სჭირდება geopandas + shapely.\n{e}"},
    "tip_folder": {"en": "Folder containing the line shapefile(s).",
                   "ka": "საქაღალდე, სადაც ხაზოვანი shapefile-ებია."},
    "tip_out": {"en": "Folder where the buffer shapefiles are written.",
                "ka": "საქაღალდე, სადაც ბუფერების shapefile-ები ჩაიწერება."},
}


class LineBufferTool(ToolFrame):
    tid = "line_buffer"
    CATALOG = LBR

    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    def build(self):
        pal = self.app.palette
        st = self._state()
        saved = self.app.get_tool_config(self.tid)

        self.busy = False
        self.msg_queue = queue.Queue()
        self._shp_map = {}                 # ჩვენებული სახელი → სრული გზა
        self.zone_vars = {}                # (მანძილი, სახელი) → BooleanVar (self-ზე, GC-სგან)

        ttk.Label(self, text=self.tr("heading"),
                  font=(UI_FONT, 13, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"],
                  wraplength=760, justify="left").pack(anchor="w", pady=(0, 12))

        grid = ttk.LabelFrame(self, text=self.tr("section"))
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        ttk.Label(grid, text=self.tr("folder")).grid(row=0, column=0, sticky="w",
                                                    padx=6, pady=2)
        self.folder_var = tk.StringVar(value=st.get("folder") or saved.get("folder") or "")
        ttk.Entry(grid, textvariable=self.folder_var).grid(row=0, column=1,
                                                           sticky="ew", padx=6, pady=2)
        add_tip(ttk.Button(grid, text=self.tr("browse"), width=3,
                           command=self._pick_folder),
                self.tr("tip_folder")).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(grid, text=self.tr("rescan"), command=self._scan).grid(
            row=0, column=3, padx=(0, 6))

        ttk.Label(grid, text=self.tr("shp")).grid(row=1, column=0, sticky="w",
                                                 padx=6, pady=2)
        self.shp_var = tk.StringVar(value=st.get("shp", ""))
        self.shp_combo = ttk.Combobox(grid, textvariable=self.shp_var,
                                      state="readonly", values=[])
        self.shp_combo.grid(row=1, column=1, columnspan=3, sticky="ew",
                            padx=6, pady=2)

        ttk.Label(grid, text=self.tr("out")).grid(row=2, column=0, sticky="w",
                                                 padx=6, pady=2)
        self.out_var = tk.StringVar(value=st.get("out") or saved.get("out") or "")
        ttk.Entry(grid, textvariable=self.out_var).grid(row=2, column=1,
                                                        sticky="ew", padx=6, pady=2)
        add_tip(ttk.Button(grid, text=self.tr("browse"), width=3,
                           command=self._pick_out),
                self.tr("tip_out")).grid(row=2, column=2, padx=(0, 6))
        ttk.Button(grid, text=self.tr("remember"), command=self._remember).grid(
            row=3, column=1, sticky="w", padx=6, pady=(4, 6))

        tbox = ttk.LabelFrame(self, text=self.tr("type_box"))
        tbox.pack(fill="x", pady=(10, 0))
        self.type_var = tk.StringVar(value=st.get("btype", "1"))
        if self.type_var.get() not in BUFFER_TYPES:
            self.type_var.set("1")
        for n in BUFFER_TYPES:
            dists = " · ".join("{} {}".format(d, "m" if self.app.lang == "en" else "მ")
                               for d, _name in BUFFER_TYPES[n])
            ttk.Radiobutton(tbox, text="{}   ({})".format(self.tr("type_n", n=n), dists),
                            variable=self.type_var, value=n,
                            command=self._build_zone_boxes).pack(anchor="w", padx=8, pady=2)

        self.zones_box = ttk.LabelFrame(self, text=self.tr("zones_box"), padding=8)
        self.zones_box.pack(fill="x", pady=(10, 0))
        self._build_zone_boxes()

        brow = ttk.Frame(self)
        brow.pack(fill="x", pady=(12, 4))
        self.build_btn = ttk.Button(brow, text=self.tr("btn_build"),
                                    style="Accent.TButton", command=self._start)
        self.build_btn.pack(side="left")

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", pady=(6, 2))
        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status,
                  foreground=pal["muted"]).pack(anchor="w", pady=(0, 4))

        self.after(100, self._poll_queue)
        if self.folder_var.get().strip():
            self.after(0, self._scan)

    def save_state(self):
        st = self._state()
        st["folder"] = self.folder_var.get()
        st["shp"] = self.shp_var.get()
        st["out"] = self.out_var.get()
        st["btype"] = self.type_var.get()

    # ---- გზები ----
    def _pick_folder(self):
        p = filedialog.askdirectory(initialdir=self.folder_var.get() or None)
        if p:
            self.folder_var.set(os.path.normpath(p))
            self._scan()

    def _pick_out(self):
        p = filedialog.askdirectory(initialdir=self.out_var.get() or None)
        if p:
            self.out_var.set(os.path.normpath(p))

    def _remember(self):
        self.app.set_tool_config(self.tid, {"folder": self.folder_var.get().strip(),
                                            "out": self.out_var.get().strip()})
        self.save_state()
        messagebox.showinfo("GIS_BOX", self.tr("cfg_saved"))

    # ---- საქაღალდის სკანირება: მხოლოდ ხაზოვანი shapefile-ები ----
    def _scan(self):
        import glob
        folder = self.folder_var.get().strip()
        self._shp_map = {}
        if folder and os.path.isdir(folder):
            try:
                import pyogrio
            except ImportError:
                pyogrio = None
            for shp in sorted(glob.glob(os.path.join(folder, "*.shp"))):
                try:
                    gtype = str(pyogrio.read_info(shp).get("geometry_type") or "") if pyogrio else "Line"
                except Exception:                  # noqa: BLE001
                    continue
                if "Line" in gtype:
                    self._shp_map[os.path.basename(shp)] = shp
        names = list(self._shp_map)
        self.shp_combo["values"] = names
        if self.shp_var.get() not in names:
            self.shp_var.set(names[0] if names else "")
        if folder:
            self.app.log("— " + (self.tr("found", n=len(names)) if names
                                 else self.tr("no_lines")))

    # ---- ბუფერის ჩამონათვალი არჩეული ტიპისთვის ----
    def _build_zone_boxes(self):
        for w in self.zones_box.winfo_children():
            w.destroy()
        self.zone_vars = {}
        for i, (d, name) in enumerate(BUFFER_TYPES[self.type_var.get()]):
            var = tk.BooleanVar(value=True)
            self.zone_vars[(d, name)] = var
            ttk.Checkbutton(self.zones_box, text=self.tr("zone_row", d=d, name=name),
                            variable=var).grid(row=i, column=0, sticky="w", pady=2)

    # ---- აგება ----
    def _start(self):
        if self.busy:
            return
        shp = self._shp_map.get(self.shp_var.get())
        out = self.out_var.get().strip()
        zones = [k for k, v in self.zone_vars.items() if v.get()]
        if not shp or not os.path.isfile(shp):
            messagebox.showwarning("GIS_BOX", self.tr("warn_shp"))
            return
        if not out or not os.path.isdir(out):
            messagebox.showwarning("GIS_BOX", self.tr("warn_out"))
            return
        if not zones:
            messagebox.showwarning("GIS_BOX", self.tr("warn_zone"))
            return
        target = self._plan_target(shp)
        if target is None:
            return
        self.busy = True
        self.build_btn.configure(state="disabled", text=self.tr("btn_busy"))
        self.progress.start(12)
        self.status.set(self.tr("running"))
        threading.Thread(target=self._worker, args=(shp, out, zones, target),
                         daemon=True).start()

    def _plan_target(self, shp):
        """გამომავალი EPSG (32637/32638) ან None (გაუქმდა/შეუძლებელია).

        32637/32638-ში მყოფ შრეს არაფერს ვეკითხებით; სხვას (მათ შორის 4326)
        ვთავაზობთ კონვერტაციას შრის მდებარეობის შესაბამის ზონაში."""
        try:
            import pyogrio
            info = pyogrio.read_info(shp)
            crs = info.get("crs")
            epsg, convert = plan_crs(crs, info["total_bounds"])
        except ValueError:
            messagebox.showwarning("GIS_BOX", self.tr("no_crs"))
            return None
        except ImportError as e:
            messagebox.showerror(self.tr("err"), self.tr("dep_err", e=e))
            return None
        except Exception as e:                     # noqa: BLE001
            messagebox.showerror(self.tr("err"), str(e))
            return None
        if convert:
            import pyproj
            c = pyproj.CRS.from_user_input(crs)
            cur = "EPSG:{}".format(c.to_epsg()) if c.to_epsg() else c.name
            if not messagebox.askyesno("GIS_BOX", self.tr(
                    "convert_q", cur=cur, epsg=epsg, zone=epsg - 32600)):
                return None
        return epsg

    def _worker(self, shp, out, zones, target_epsg):
        try:
            import geopandas as gpd

            gdf = gpd.read_file(shp)
            if gdf.crs is None:
                self.msg_queue.put(("warn", self.tr("no_crs")))
                return
            src_epsg = gdf.crs.to_epsg()
            if src_epsg != target_epsg:
                cur = "EPSG:{}".format(src_epsg) if src_epsg else "CRS"
                gdf = gdf.to_crs(epsg=target_epsg)
                self.msg_queue.put(("log", self.tr("reproj", cur=cur, epsg=target_epsg)))
            geoms = [g for g in gdf.geometry if g is not None and not g.is_empty]
            if not geoms:
                self.msg_queue.put(("warn", self.tr("no_geom")))
                return

            written = []
            for dist, name in zones:
                geom = build_buffer(geoms, dist)
                path = output_path(out, name)
                gpd.GeoDataFrame([{"Zone": name, "Dist_m": dist}],
                                 geometry=[geom], crs=gdf.crs).to_file(
                    path, driver="ESRI Shapefile", encoding="utf-8")
                written.append((dist, path))
                self.msg_queue.put(("log", self.tr("wrote", d=dist, path=path)))
            self.msg_queue.put(("done", {"n": len(written), "out": out}))
        except ImportError as e:
            self.msg_queue.put(("dep_err", str(e)))
        except Exception as e:                     # noqa: BLE001
            self.msg_queue.put(("fatal", str(e)))

    # ---- queue (მთავარ ნაკადში) ----
    def _poll_queue(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.app.log("— " + payload)
                elif kind == "done":
                    self._reset()
                    msg = self.tr("done", n=payload["n"], out=payload["out"])
                    self.status.set(msg)
                    self.app.log("— " + msg)
                    messagebox.showinfo("GIS_BOX", msg)
                elif kind == "warn":
                    self._reset()
                    self.status.set("")
                    messagebox.showwarning("GIS_BOX", payload)
                elif kind == "dep_err":
                    self._reset()
                    messagebox.showerror(self.tr("err"), self.tr("dep_err", e=payload))
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
        self.build_btn.configure(state="normal", text=self.tr("btn_build"))
