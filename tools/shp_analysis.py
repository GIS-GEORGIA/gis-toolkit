# -*- coding: utf-8 -*-
"""„შეიპების ანალიზი“ — ნაკვეთის ძებნის ხელსაწყოს დამატებითი სექცია.

აირჩევ საქაღალდეს; ის რეკურსიულად სკანირდება და ყველა shapefile იზომება (ფართი,
პერიმეტრი, სიგრძე, რაოდენობა). ლოგში იბეჭდება რანჟირებები („რომელი პოლიგონური შრეა
ყველაზე დიდი ფართით“ და ა.შ.), ყოველ შრეს თან **საქაღალდის სრული გზა** ახლავს —
ერთნაირი სახელები ბევრ საქაღალდეშია. სუფთა ლოგიკა ``shp_analysis_core``-შია.

ეს სექცია მასპინძელი ``ParcelSearchTool``-ის ლოგს, პროგრესის ზოლსა და სტატუსს
იყენებს (კომპოზიცია — არა ცალკე ხელსაწყო).
"""

import os
import queue
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tools.i18n import translate
from tools.tooltip import add_tip
from tools import shp_analysis_core as core

ATR = {
    "title": {"en": "Extra: shapefile analysis across folders",
              "ka": "დამატებით: შეიპების ანალიზი საქაღალდეებში"},
    "desc": {"en": "Scans a folder (with all sub-folders), measures every shapefile "
                   "and prints which polygon layer has the largest area / perimeter, "
                   "which line layer is the longest, etc. Every entry shows the full "
                   "folder path, because the same file names repeat in many folders.",
             "ka": "სკანირებს საქაღალდეს (ყველა ქვესაქაღალდით), ზომავს თითოეულ "
                   "shapefile-ს და ლოგში ბეჭდავს, რომელი პოლიგონური შრეა ყველაზე დიდი "
                   "ფართით / პერიმეტრით, რომელი ხაზოვანია ყველაზე გრძელი და ა.შ. "
                   "ყოველი ჩანაწერის გვერდით საქაღალდის სრული გზაა, რადგან ერთნაირი "
                   "სახელები ბევრ საქაღალდეშია."},
    "root": {"en": "Folder to scan:", "ka": "სკანირების საქაღალდე:"},
    "top": {"en": "Top:", "ka": "ტოპ:"},
    "btn_run": {"en": "Analyse shapefiles", "ka": "შეიპების ანალიზი"},
    "btn_busy": {"en": "Analysing…", "ka": "ანალიზი…"},
    "btn_cancel": {"en": "✖ Cancel", "ka": "✖ გაუქმება"},
    "tip_root": {"en": "Folder whose shapefiles (including sub-folders) are analysed.",
                 "ka": "საქაღალდე, რომლის shapefile-ებიც (ქვესაქაღალდეებითურთ) გაანალიზდება."},
    "tip_top": {"en": "How many leaders to list per ranking.",
                "ka": "თითო რანჟირებაში რამდენი ლიდერი გამოვიდეს."},
    "err_root": {"en": "Select an existing folder to scan.",
                 "ka": "აირჩიე სკანირებისთვის არსებული საქაღალდე."},
    "none_found": {"en": "No shapefiles found in this folder.",
                   "ka": "ამ საქაღალდეში shapefile ვერ მოიძებნა."},
    "busy_search": {"en": "A code search is running — wait for it to finish.",
                    "ka": "კოდების ძებნა მიმდინარეობს — დაელოდე დასრულებას."},
    "busy_analysis": {"en": "Shapefile analysis is running — wait for it to finish.",
                      "ka": "შეიპების ანალიზი მიმდინარეობს — დაელოდე დასრულებას."},
    "status_progress": {"en": "Analysis: {i}/{n} shapefiles", "ka": "ანალიზი: {i}/{n} shapefile"},
    "status_done": {"en": "Analysis done — {n} shapefiles.", "ka": "ანალიზი დასრულდა — {n} shapefile."},
    "status_cancel": {"en": "Analysis cancelled.", "ka": "ანალიზი გაუქმდა."},
    "err": {"en": "Error", "ka": "შეცდომა"},

    "hdr": {"en": "Shapefile analysis — {root}", "ka": "შეიპების ანალიზი — {root}"},
    "counts": {"en": "Scanned {total} shapefiles: {p} polygon, {l} line, {pt} point",
               "ka": "სკანირებულია {total} shapefile: პოლიგონური {p}, ხაზოვანი {l}, წერტილოვანი {pt}"},
    "rank_poly_area": {"en": "POLYGONS — total area", "ka": "პოლიგონები — ჯამური ფართი"},
    "rank_poly_perimeter": {"en": "POLYGONS — total perimeter", "ka": "პოლიგონები — ჯამური პერიმეტრი"},
    "rank_poly_area_max": {"en": "POLYGONS — largest single feature",
                           "ka": "პოლიგონები — ყველაზე დიდი ერთი ობიექტი"},
    "rank_poly_count": {"en": "POLYGONS — feature count", "ka": "პოლიგონები — ობიექტების რაოდენობა"},
    "rank_line_length": {"en": "LINES — total length", "ka": "ხაზები — ჯამური სიგრძე"},
    "rank_line_length_max": {"en": "LINES — longest single line", "ka": "ხაზები — ყველაზე გრძელი ერთი ხაზი"},
    "rank_line_count": {"en": "LINES — feature count", "ka": "ხაზები — ობიექტების რაოდენობა"},
    "rank_point_count": {"en": "POINTS — feature count", "ka": "წერტილები — ობიექტების რაოდენობა"},
    "top_n": {"en": "(top {n})", "ka": "(ტოპ {n})"},
    "d_poly": {"en": "area {a} · perimeter {p} · largest {m} · {n} feature(s)",
               "ka": "ფართი {a} · პერიმეტრი {p} · უდიდესი ობიექტი {m} · {n} ობიექტი"},
    "d_line": {"en": "length {l} · longest {m} · {n} feature(s)",
               "ka": "სიგრძე {l} · უგრძესი ხაზი {m} · {n} ობიექტი"},
    "d_point": {"en": "{n} feature(s)", "ka": "{n} ობიექტი"},
    "converted": {"en": "measured after conversion: {crs}", "ka": "გაიზომა გადაყვანის შემდეგ: {crs}"},
    "folder": {"en": "folder: {f}", "ka": "საქაღალდე: {f}"},
    "skip_nocrs": {"en": "NO CRS ({n}) — area/length cannot be measured, not ranked:",
                   "ka": "CRS-გარეშე ({n}) — ფართი/სიგრძე ვერ დგინდება, რანჟირებაში არ მონაწილეობს:"},
    "skip_empty": {"en": "EMPTY layers ({n}):", "ka": "ცარიელი შრეები ({n}):"},
    "skip_error": {"en": "UNREADABLE ({n}):", "ka": "წაუკითხავი ({n}):"},
}


class ShpAnalysisSection:
    """UI-სექცია + ფონური ანალიზი; მასპინძელი — ``ParcelSearchTool``."""

    def __init__(self, host):
        self.host = host
        self.queue = queue.Queue()
        self.running = False
        self.cancel_event = threading.Event()

    def tr(self, key, **fmt):
        return translate(ATR, key, self.host.app.lang, **fmt)

    # ---- UI ----
    def build(self, parent, root_initial, top_initial):
        h = self.host
        box = ttk.LabelFrame(parent, text=self.tr("title"))
        box.pack(fill="x", padx=8, pady=4)
        ttk.Label(box, text=self.tr("desc"), foreground=h.app.palette["muted"],
                  wraplength=760, justify="left").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=6, pady=(4, 6))

        ttk.Label(box, text=self.tr("root")).grid(row=1, column=0, sticky="w", padx=6)
        self.root_var = tk.StringVar(value=root_initial or "")
        ttk.Entry(box, textvariable=self.root_var).grid(row=1, column=1, columnspan=2,
                                                        sticky="we", padx=6, pady=2)
        add_tip(ttk.Button(box, text="...", width=3, command=self._browse),
                self.tr("tip_root")).grid(row=1, column=3, padx=(0, 6))

        row = ttk.Frame(box)
        row.grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=(4, 6))
        self.run_btn = ttk.Button(row, text=self.tr("btn_run"), command=self.start)
        self.run_btn.pack(side="left")
        self.cancel_btn = ttk.Button(row, text=self.tr("btn_cancel"), state="disabled",
                                     command=self.cancel)
        self.cancel_btn.pack(side="left", padx=(6, 18))
        ttk.Label(row, text=self.tr("top")).pack(side="left")
        self.top_var = tk.StringVar(value=str(top_initial or 5))
        add_tip(ttk.Spinbox(row, from_=1, to=50, width=4, textvariable=self.top_var),
                self.tr("tip_top")).pack(side="left", padx=(6, 0))
        box.columnconfigure(1, weight=1)
        box.columnconfigure(2, weight=1)

        h.after(150, self._poll)
        return box

    def save_state(self, st):
        st["an_root"] = self.root_var.get()
        st["an_top"] = self.top_var.get()

    def _browse(self):
        p = filedialog.askdirectory(initialdir=self.root_var.get() or None)
        if p:
            self.root_var.set(os.path.normpath(p))

    def _top_n(self):
        try:
            return min(50, max(1, int(self.top_var.get())))
        except ValueError:
            return 5

    # ---- გაშვება ----
    def start(self):
        h = self.host
        if self.running:
            return
        if h.searching:
            messagebox.showinfo("GIS_BOX", self.tr("busy_search"))
            return
        root = self.root_var.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showerror(self.tr("err"), self.tr("err_root"))
            return
        h.log_text.configure(state="normal")
        h.log_text.delete("1.0", "end")
        h.log_text.configure(state="disabled")
        self.running = True
        self.cancel_event.clear()
        self.run_btn.configure(state="disabled", text=self.tr("btn_busy"))
        self.cancel_btn.configure(state="normal")
        h.search_btn.configure(state="disabled")
        h.progress.configure(value=0, maximum=100)
        threading.Thread(target=self._worker, args=(root, self._top_n()),
                         daemon=True).start()

    def cancel(self):
        if self.running:
            self.cancel_event.set()
            self.cancel_btn.configure(state="disabled")

    def _worker(self, root, top_n):
        try:
            paths = core.scan_shapefiles(root)
            rows = []
            n = len(paths)
            for i, p in enumerate(paths, start=1):
                if self.cancel_event.is_set():
                    self.queue.put(("done", {"cancelled": True}))
                    return
                rows.append(core.analyze_layer(p))
                self.queue.put(("progress", (i, n)))
            self.queue.put(("done", {"root": root, "top": top_n, "rows": rows}))
        except Exception as e:                     # noqa: BLE001
            self.queue.put(("done", {"fatal": str(e)}))

    # ---- queue (მთავარ ნაკადში) ----
    def _poll(self):
        h = self.host
        if not h.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "progress":
                    i, n = payload
                    h.progress.configure(maximum=max(n, 1), value=i)
                    h.status.set(self.tr("status_progress", i=i, n=n))
                elif kind == "done":
                    self._finish(payload)
        except queue.Empty:
            pass
        h.after(150, self._poll)

    def _finish(self, result):
        h = self.host
        self.running = False
        self.run_btn.configure(state="normal", text=self.tr("btn_run"))
        self.cancel_btn.configure(state="disabled")
        h.search_btn.configure(state="normal")
        h.progress.configure(value=0)
        if result.get("cancelled"):
            h.status.set(self.tr("status_cancel"))
            h._log("— " + self.tr("status_cancel"))
            return
        if "fatal" in result:
            h.status.set(self.tr("err") + ".")
            messagebox.showerror(self.tr("err"), result["fatal"])
            return
        rows = result["rows"]
        if not rows:
            h.status.set(self.tr("none_found"))
            h._log("— " + self.tr("none_found"))
            return
        self.report(result["root"], rows, result["top"])
        h.status.set(self.tr("status_done", n=len(rows)))

    # ---- ანგარიში ლოგში ----
    def _detail(self, r):
        lang = self.host.app.lang
        if r["kind"] == core.POLYGON:
            txt = self.tr("d_poly", a=core.fmt_area(r["area_total"], lang),
                          p=core.fmt_length(r["perimeter_total"], lang),
                          m=core.fmt_area(r["area_max"], lang), n=r["count"])
        elif r["kind"] == core.LINE:
            txt = self.tr("d_line", l=core.fmt_length(r["length_total"], lang),
                          m=core.fmt_length(r["length_max"], lang), n=r["count"])
        else:
            txt = self.tr("d_point", n=r["count"])
        if r.get("converted"):
            txt += " · " + self.tr("converted", crs=r["crs_label"])
        return txt

    def report(self, root, rows, top_n):
        """რანჟირებები ლოგში (ყოველი ჩანაწერი — სახელი, მნიშვნელობა, დეტალები, საქაღალდე)."""
        h = self.host
        lang = h.app.lang
        log = h._log
        summary = core.summarize(rows)
        ranks = core.rank_layers(rows, top_n)
        shown = {
            "poly_area": lambda r: core.fmt_area(r["area_total"], lang),
            "poly_perimeter": lambda r: core.fmt_length(r["perimeter_total"], lang),
            "poly_area_max": lambda r: core.fmt_area(r["area_max"], lang),
            "poly_count": lambda r: str(r["count"]),
            "line_length": lambda r: core.fmt_length(r["length_total"], lang),
            "line_length_max": lambda r: core.fmt_length(r["length_max"], lang),
            "line_count": lambda r: str(r["count"]),
            "point_count": lambda r: str(r["count"]),
        }
        log("")
        log("=" * 60)
        log(self.tr("hdr", root=root))
        log(self.tr("counts", total=summary["total"], p=summary[core.POLYGON],
                    l=summary[core.LINE], pt=summary[core.POINT]))
        log("=" * 60)
        for key, _kind, _field in core.RANKINGS:
            entries = ranks[key]
            if not entries:
                continue
            log("")
            log("▶ {} {}".format(self.tr("rank_" + key), self.tr("top_n", n=len(entries))))
            for i, r in enumerate(entries, start=1):
                log("  {}. {} — {}".format(i, r["name"], shown[key](r)))
                log("       " + self._detail(r))
                log("       " + self.tr("folder", f=r["folder"]))

        for status, key in ((core.NO_CRS, "skip_nocrs"), (core.EMPTY, "skip_empty"),
                            (core.ERROR, "skip_error")):
            items = summary[status]
            if not items:
                continue
            log("")
            log("⚠ " + self.tr(key, n=len(items)))
            for r in items:
                extra = " — " + r["error"] if status == core.ERROR and r["error"] else ""
                log("    {}{}".format(r["path"], extra))
        log("=" * 60)
