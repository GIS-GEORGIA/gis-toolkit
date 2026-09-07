# -*- coding: utf-8 -*-
"""საკადასტრო კოდების ძებნის ხელსაწყო — GIS_BOX-ის ხელსაწყო (ორენოვანი en/ka).

ეძებს საკადასტრო კოდებს File Geodatabase-ის შრეში და ნაპოვნებზე ქმნის
Shapefile-ს + GeoPackage-ს. ვერ ნაპოვნ კოდებს ცალკე გამოაქვს სიის სახით.

მოთხოვნები: geopandas, pyogrio, pandas, openpyxl (Excel-ისთვის).
ენა იკითხება GIS_BOX-ის მთავარი აპლიკაციიდან (self.app.lang).
"""

import os
import re
import threading
import queue
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import pandas as pd
import pyogrio

from tools.base import ToolFrame
from tools.tooltip import add_tip


# ---------------------------------------------------------------------------
# თარგმანები / translations (en/ka)
# ---------------------------------------------------------------------------
PTR = {
    "sec_db":        {"en": "1. Database", "ka": "1. მონაცემთა ბაზა"},
    "lbl_gdb":       {"en": "GDB database:", "ka": "GDB ბაზა:"},
    "btn_read_layers": {"en": "Read layers", "ka": "შრეების წაკითხვა"},
    "btn_db_remove": {"en": "🗑 Remove DB", "ka": "🗑 ბაზის წაშლა"},
    "db_remove_q":   {"en": "Remove this database from the list?",
                      "ka": "წავშალო ეს ბაზა სიიდან?"},
    "btn_remember":  {"en": "💾 Remember settings", "ka": "💾 პარამეტრების დამახსოვრება"},
    "cfg_saved":     {"en": "Settings saved — they will be remembered next time.",
                      "ka": "პარამეტრები შენახულია — მომდევნო გაშვებაზეც დაიმახსოვრდება."},
    "cfg_hint":      {"en": "Enter your database path once and click Remember; it is stored "
                            "locally (not in the code / repository).",
                      "ka": "ერთხელ შეიყვანე ბაზის გზა და დააჭირე „დამახსოვრებას“; ის ინახება "
                            "ლოკალურად (არა კოდში / რეპოზიტორიაში)."},
    "lbl_layer":     {"en": "Layer:", "ka": "შრე:"},
    "lbl_field":     {"en": "Code field:", "ka": "კოდის ველი:"},
    "sec_codes":     {"en": "2. Search codes", "ka": "2. საძებნი კოდები"},
    "lbl_enter":     {"en": "Enter codes (one per line or comma-separated):",
                      "ka": "ჩაწერე კოდები (თითო ხაზზე ან მძიმით):"},
    "btn_load":      {"en": "Load from CSV/Excel", "ka": "CSV/Excel-იდან ატვირთვა"},
    "btn_clear":     {"en": "Clear", "ka": "გასუფთავება"},
    "sec_out":       {"en": "3. Output file", "ka": "3. შედეგის ფაილი"},
    "btn_search":    {"en": "🔍  Search", "ka": "🔍  ძებნა"},
    "btn_search_busy": {"en": "Working…", "ka": "მიმდინარეობს…"},
    "btn_cancel":    {"en": "✖ Cancel", "ka": "✖ გაუქმება"},
    "cancelling":    {"en": "Cancelling…", "ka": "უქმდება…"},
    "cancelled":     {"en": "Search cancelled.", "ka": "ძებნა გაუქმდა."},
    "progress":      {"en": "Progress: {i}/{n} blocks", "ka": "პროგრესი: {i}/{n} ბლოკი"},
    "out_create":    {"en": "💾 Create:", "ka": "💾 შექმნა:"},
    "chk_shp":       {"en": "Shapefile (.shp)", "ka": "Shapefile (.shp)"},
    "chk_gpkg":      {"en": "GeoPackage (.gpkg)", "ka": "GeoPackage (.gpkg)"},
    "sec_result":    {"en": "4. Result", "ka": "4. შედეგი"},
    "btn_save_nf":   {"en": "Save not-found codes (.txt)",
                      "ka": "ვერ ნაპოვნი კოდების შენახვა (.txt)"},
    "ready":         {"en": "Ready.", "ka": "მზადაა."},
    "searching":     {"en": "Searching…", "ka": "ძებნა…"},
    "reading_layers": {"en": "Reading layers…", "ka": "შრეების წაკითხვა…"},
    "reading_fields": {"en": "Reading fields…", "ka": "ველების წაკითხვა…"},

    # dialogs
    "err":           {"en": "Error", "ka": "შეცდომა"},
    "err_gdb":       {"en": "Database path not found.", "ka": "ბაზის მისამართი ვერ მოიძებნა."},
    "err_layer_field": {"en": "Select a layer and code field.",
                        "ka": "აირჩიე შრე და კოდის ველი."},
    "err_out":       {"en": "Specify the output file path.",
                      "ka": "მიუთითე შედეგის ფაილის მისამართი."},
    "err_codes_empty": {"en": "Search codes are empty.", "ka": "საძებნი კოდები ცარიელია."},
    "empty_title":   {"en": "Empty", "ka": "ცარიელი"},
    "no_layers":     {"en": "No layers found in the database.",
                      "ka": "ბაზაში შრეები ვერ მოიძებნა."},
    "pick_gdb":      {"en": "Select a .gdb database", "ka": "აირჩიე .gdb ბაზა"},
    "pick_file":     {"en": "Select a CSV or Excel file", "ka": "აირჩიე CSV ან Excel ფაილი"},
    "ft_tables":     {"en": "Spreadsheets", "ka": "ცხრილები"},
    "ft_all":        {"en": "All files", "ka": "ყველა"},
    "ft_txt":        {"en": "Text", "ka": "ტექსტი"},
    "file_read_err": {"en": "Could not read the file:\n{e}", "ka": "ფაილი ვერ წაიკითხა:\n{e}"},
    "pick_col_title": {"en": "Choose the code column", "ka": "აირჩიე კოდების სვეტი"},
    "pick_col_q":    {"en": "Which column has the cadastral codes?",
                      "ka": "რომელ სვეტშია საკადასტრო კოდები?"},
    "out_file_title": {"en": "Output file", "ka": "შედეგის ფაილი"},
    "save_nf_title": {"en": "Save not-found codes", "ka": "ვერ ნაპოვნი კოდების შენახვა"},
    "info":          {"en": "Info", "ka": "ინფო"},
    "ok":            {"en": "OK", "ka": "დიახ"},
    "no_nf":         {"en": "There are no not-found codes.", "ka": "ვერ ნაპოვნი კოდები არ არის."},
    "saved_title":   {"en": "Saved", "ka": "შენახულია"},
    "saved_n":       {"en": "Wrote {n} codes.", "ka": "ჩაიწერა {n} კოდი."},

    # log (UI)
    "log_layers":    {"en": "Layers found: {layers}", "ka": "ბაზაში ნაპოვნია შრეები: {layers}"},
    "log_loaded":    {"en": "Loaded {n} codes from file (column: {col}).",
                      "ka": "ფაილიდან ჩაიტვირთა {n} კოდი (სვეტი: {col})."},

    # log (run_search)
    "rs_count":      {"en": "Codes to search: {n}", "ka": "საძებნი კოდი: {n}"},
    "rs_db":         {"en": "Database: {gdb}", "ka": "ბაზა: {gdb}"},
    "rs_layer":      {"en": "Layer: {layer} | field: {field}", "ka": "შრე: {layer} | ველი: {field}"},
    "rs_searching":  {"en": "Searching…", "ka": "ძებნა მიმდინარეობს…"},
    "rs_block":      {"en": "  block {i}/{n} — {k} unique codes found so far",
                      "ka": "  ბლოკი {i}/{n} — ნაპოვნია სულ {k} უნიკ. კოდი"},
    "rs_writing":    {"en": "Writing {n} features…", "ka": "ვწერ {n} ობიექტს…"},
    "rs_none":       {"en": "No codes found — no files created.",
                      "ka": "ვერცერთი კოდი ვერ მოიძებნა — ფაილები არ შეიქმნა."},
    "rs_search_only":{"en": "Search only — {n} features matched, files not created.",
                      "ka": "მხოლოდ ძებნა — {n} ობიექტი დაემთხვა, ფაილები არ შექმნილა."},
    "sum_search_only": {"en": "Search only — no files created.",
                        "ka": "მხოლოდ ძებნა — ფაილები არ შექმნილა."},
    "rs_empty_list": {"en": "Empty list — no codes could be read.",
                      "ka": "ცარიელი სია — ვერცერთი კოდი ვერ წავიკითხე."},

    # summary (_on_done)
    "done_err_hdr":  {"en": "--- Error ---", "ka": "--- შეცდომა ---"},
    "sum_total":     {"en": "Total requested: {n}", "ka": "სულ საძებნი: {n}"},
    "sum_found":     {"en": "Found:       {n}", "ka": "ნაპოვნია:    {n}"},
    "sum_nf":        {"en": "Not found:   {n}", "ka": "ვერ ნაპოვნი: {n}"},
    "sum_written":   {"en": "Features written: {n}", "ka": "ჩაწერილი ობიექტი: {n}"},
    "sum_file":      {"en": "File: {p}", "ka": "ფაილი: {p}"},
    "nf_list_hdr":   {"en": "Not-found codes:", "ka": "ვერ ნაპოვნი კოდები:"},
    "done_status":   {"en": "Done — found {f}, not found {nf}.",
                      "ka": "დასრულდა — ნაპოვნი {f}, ვერ ნაპოვნი {nf}."},
    "nf_saved":      {"en": "Not-found codes saved: {p}", "ka": "ვერ ნაპოვნი კოდები შენახულია: {p}"},

    # tooltip-ები
    "tip_browse_gdb": {"en": "Pick a .gdb File Geodatabase.", "ka": "აირჩიე .gdb ბაზა."},
    "tip_read_layers": {"en": "Read the list of layers from the database.",
                        "ka": "ბაზიდან შრეების სიის წაკითხვა."},
    "tip_db_remove": {"en": "Remove this database from the dropdown list.",
                      "ka": "ამ ბაზის ამოღება ჩამოსაშლელი სიიდან."},
    "tip_layer":     {"en": "Layer to search in.", "ka": "შრე, სადაც ვეძებთ."},
    "tip_field":     {"en": "Field that holds the cadastral code.",
                      "ka": "ველი, სადაც საკადასტრო კოდია."},
    "tip_remember":  {"en": "Remember the database, layer and field for next time.",
                      "ka": "ბაზის, შრისა და ველის დამახსოვრება მომავლისთვის."},
    "tip_load":      {"en": "Load codes from a CSV / Excel file.",
                     "ka": "კოდების ატვირთვა CSV / Excel-იდან."},
    "tip_shp":       {"en": "Create a Shapefile of the results.",
                     "ka": "შედეგების Shapefile-ის შექმნა."},
    "tip_gpkg":      {"en": "Create a GeoPackage of the results.",
                     "ka": "შედეგების GeoPackage-ის შექმნა."},
    "tip_search":    {"en": "Search the codes and create the output files.",
                     "ka": "კოდების ძებნა და შედეგის ფაილების შექმნა."},
    "tip_cancel":    {"en": "Stop the running search.", "ka": "მიმდინარე ძებნის შეჩერება."},
    "tip_save_nf":   {"en": "Save the not-found codes to a text file.",
                     "ka": "ვერ ნაპოვნი კოდების შენახვა ტექსტურ ფაილში."},
}


# ---------------------------------------------------------------------------
# ნაგულისხმევი პარამეტრები — config.txt იკითხება GIS_BOX-ის ძირეული საქაღალდიდან
# (თითო ხაზი: KEY=VALUE — GDB=..., LAYER=RegParcels, FIELD=CADCODE).
# config.txt .gitignore-შია და GitHub-ზე არ აიტვირთება.
# ---------------------------------------------------------------------------
def _load_config():
    cfg = {"GDB": "", "LAYER": "RegParcels", "FIELD": "CADCODE"}
    # tools/parcel_search.py -> ../ = GIS_BOX ძირი
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(app_dir, "config.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip().upper()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg


_CFG = _load_config()
DEFAULT_GDB = _CFG["GDB"]
DEFAULT_LAYER = _CFG["LAYER"]
DEFAULT_FIELD = _CFG["FIELD"]
# არჩევითი: რამდენიმე ბაზა config.txt-ში — GDBS=path1;path2;path3
DEFAULT_GDBS = [p.strip() for p in re.split(r"[;\n]+", _CFG.get("GDBS", ""))
                if p.strip()]
# CadData.gdb-ის დათასეთების კოდები → რეგიონები (სუფთა ლოგიკა ცალკე მოდულში)
from tools.regions import REGION_CODES, region_name, layer_display, layer_code
from tools.fields import pick_code_field
# ძებნის სუფთა ლოგიკა — GUI-სგან დამოუკიდებელი, ტესტირებადი
from tools.search_core import (CHUNK_SIZE, normalize, chunked,
                               parse_manual_codes, run_search)


# ---------------------------------------------------------------------------
# ხელსაწყო (ToolFrame) — UI ჩაშენებულია GIS_BOX-ის მთავარ ფანჯარაში
# ---------------------------------------------------------------------------
class ParcelSearchTool(ToolFrame):
    tid = "parcel_search"
    CATALOG = PTR          # tr() მოდის ToolFrame-იდან (საერთო lookup)

    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    def build(self):
        self.msg_queue = queue.Queue()
        self.searching = False
        self._cancel_event = threading.Event()
        self._meta_gen = 0            # ბაზის მეტამონაცემების წაკითხვის თაობა
        self.last_not_found = []
        st = self._state()                       # transient (სესიის ფარგლებში)
        saved = self.app.get_tool_config(self.tid)  # მუდმივი (git-ignored ფაილი)
        tr = self.tr

        # საწყისი მნიშვნელობა: სესიის მდგომარეობა → შენახული კონფიგი → ნაგულისხმევი
        def initial(key, default):
            return st.get(key) or saved.get(key) or default

        pad = {"padx": 8, "pady": 4}

        # --- ბაზის პარამეტრები ---
        db = ttk.LabelFrame(self, text=tr("sec_db"))
        db.pack(fill="x", **pad)

        # შენახული ბაზების სია: მუდმივი კონფიგი → config.txt (GDBS) → ერთი DEFAULT_GDB
        self._databases = list(saved.get("databases") or DEFAULT_GDBS
                               or ([DEFAULT_GDB] if DEFAULT_GDB else []))

        ttk.Label(db, text=tr("lbl_gdb")).grid(row=0, column=0, sticky="w", padx=6, pady=3)
        self.gdb_var = tk.StringVar(value=initial("gdb", DEFAULT_GDB)
                                    or (self._databases[0] if self._databases else ""))
        # ჩამოსაშლელი — რამდენიმე ბაზას შორის გადართვა (რედაქტირებადი: ახლის ჩაწერაც შეიძლება)
        self.gdb_combo = ttk.Combobox(db, textvariable=self.gdb_var,
                                      values=self._databases, width=68)
        self.gdb_combo.grid(row=0, column=1, sticky="we", padx=6)
        self.gdb_combo.bind("<<ComboboxSelected>>", lambda e: self._on_db_selected())
        add_tip(ttk.Button(db, text="...", width=3, command=self._browse_gdb),
                tr("tip_browse_gdb")).grid(row=0, column=2, padx=4)
        add_tip(ttk.Button(db, text=tr("btn_read_layers"), command=self._load_layers),
                tr("tip_read_layers")).grid(row=0, column=3, padx=6)
        add_tip(ttk.Button(db, text=tr("btn_db_remove"), command=self._remove_db),
                tr("tip_db_remove")).grid(row=0, column=4, padx=(0, 6))

        ttk.Label(db, text=tr("lbl_layer")).grid(row=1, column=0, sticky="w", padx=6, pady=3)
        self.layer_var = tk.StringVar(value=initial("layer", DEFAULT_LAYER))
        self.layer_combo = ttk.Combobox(db, textvariable=self.layer_var,
                                        values=[self.layer_var.get()], state="readonly", width=30)
        self.layer_combo.grid(row=1, column=1, sticky="w", padx=6)
        self.layer_combo.bind("<<ComboboxSelected>>", lambda e: self._load_fields())
        add_tip(self.layer_combo, tr("tip_layer"))

        ttk.Label(db, text=tr("lbl_field")).grid(row=1, column=2, sticky="e", padx=6)
        self.field_var = tk.StringVar(value=initial("field", DEFAULT_FIELD))
        self.field_combo = ttk.Combobox(db, textvariable=self.field_var,
                                        values=[self.field_var.get()], state="readonly", width=22)
        self.field_combo.grid(row=1, column=3, sticky="w", padx=6)
        add_tip(self.field_combo, tr("tip_field"))

        # --- დამახსოვრება (მუდმივი კონფიგი) ---
        add_tip(ttk.Button(db, text=tr("btn_remember"), command=self._remember),
                tr("tip_remember")).grid(row=2, column=1, sticky="w", padx=6, pady=(2, 4))
        ttk.Label(db, text=tr("cfg_hint"), foreground=self.app.palette["muted"],
                  wraplength=560, justify="left").grid(
            row=3, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 4))

        db.columnconfigure(1, weight=1)

        # --- შეყვანა ---
        inp = ttk.LabelFrame(self, text=tr("sec_codes"))
        inp.pack(fill="both", expand=True, **pad)

        bar = ttk.Frame(inp)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Label(bar, text=tr("lbl_enter")).pack(side="left")
        add_tip(ttk.Button(bar, text=tr("btn_load"), command=self._load_file),
                tr("tip_load")).pack(side="right")
        ttk.Button(bar, text=tr("btn_clear"), command=lambda: self.codes_text.delete("1.0", "end")).pack(side="right", padx=4)

        self.codes_text = scrolledtext.ScrolledText(inp, height=8, font=("Consolas", 10))
        self.codes_text.pack(fill="both", expand=True, padx=6, pady=4)
        if st.get("codes"):
            self.codes_text.insert("1.0", st["codes"])

        # --- გამომავალი ფაილი ---
        out = ttk.LabelFrame(self, text=tr("sec_out"))
        out.pack(fill="x", **pad)
        default_out = os.path.join(os.path.expanduser("~"), "Desktop", "found_parcels.shp")
        self.out_var = tk.StringVar(value=initial("out", default_out))
        ttk.Entry(out, textvariable=self.out_var, width=70).grid(row=0, column=0, sticky="we", padx=6, pady=6)
        ttk.Button(out, text="...", width=3, command=self._browse_out).grid(row=0, column=1, padx=6)
        # ფორმატები — თითოეული ცალკე თოლიით (არცერთი => მხოლოდ ძებნა, ფაილების გარეშე)
        fmt_row = ttk.Frame(out)
        fmt_row.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))
        ttk.Label(fmt_row, text=tr("out_create")).pack(side="left")
        self.shp_var = tk.BooleanVar(value=st.get("shp", True))
        self.gpkg_var = tk.BooleanVar(value=st.get("gpkg", True))
        add_tip(ttk.Checkbutton(fmt_row, text=tr("chk_shp"), variable=self.shp_var),
                tr("tip_shp")).pack(side="left", padx=(8, 4))
        add_tip(ttk.Checkbutton(fmt_row, text=tr("chk_gpkg"), variable=self.gpkg_var),
                tr("tip_gpkg")).pack(side="left")
        out.columnconfigure(0, weight=1)

        # --- ღილაკი + გაუქმება + პროგრესი ---
        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=8, pady=6)
        self.search_btn = ttk.Button(btn_row, text=tr("btn_search"), command=self._start_search)
        self.search_btn.pack(side="left", fill="x", expand=True)
        add_tip(self.search_btn, tr("tip_search"))
        self.cancel_btn = ttk.Button(btn_row, text=tr("btn_cancel"),
                                     command=self._cancel_search, state="disabled")
        self.cancel_btn.pack(side="left", padx=(6, 0))
        add_tip(self.cancel_btn, tr("tip_cancel"))
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=8)

        # --- შედეგები / ლოგი ---
        res = ttk.LabelFrame(self, text=tr("sec_result"))
        res.pack(fill="both", expand=True, **pad)
        self.log_text = scrolledtext.ScrolledText(res, height=10, font=("Consolas", 10), state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=4)
        add_tip(ttk.Button(res, text=tr("btn_save_nf"), command=self._save_not_found),
                tr("tip_save_nf")).pack(side="right", padx=6, pady=4)

        self.status = tk.StringVar(value=tr("ready"))
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

        self.after(100, self._poll_queue)

        # გაშვებისთანავე — ბაზის ყველა შრის ავტომატური წაკითხვა (popup-ის გარეშე),
        # კონკრეტული შრე/ველი ნაგულისხმევად რჩება.
        if self.gdb_var.get().strip():
            self.after(0, lambda: self._load_layers(silent=True))

    def save_state(self):
        st = self._state()
        st["gdb"] = self.gdb_var.get()
        st["layer"] = self._layer_code(self.layer_var.get())
        st["field"] = self.field_var.get()
        st["out"] = self.out_var.get()
        st["codes"] = self.codes_text.get("1.0", "end").strip()
        if hasattr(self, "shp_var"):
            st["shp"] = self.shp_var.get()
            st["gpkg"] = self.gpkg_var.get()

    def _remember(self):
        """მიმდინარე ბაზის პარამეტრების მუდმივად შენახვა (git-ignored ფაილში).

        მიმდინარე ბაზა ემატება ჩამოსაშლელი სიის (databases) მუდმივ ნაკრებს."""
        gdb = self.gdb_var.get().strip()
        if gdb and gdb not in self._databases:
            self._databases.append(gdb)
            self.gdb_combo["values"] = self._databases
        self.app.set_tool_config(self.tid, {
            "gdb": gdb,
            "layer": self._layer_code(self.layer_var.get().strip()),
            "field": self.field_var.get().strip(),
            "out": self.out_var.get().strip(),
            "databases": self._databases,
        })
        self.save_state()
        messagebox.showinfo(self.tr("saved_title"), self.tr("cfg_saved"))

    def _on_db_selected(self):
        """ჩამოსაშლელიდან ბაზის არჩევისას — ყველა შრის ავტომატური, ჩუმი წაკითხვა
        (popup-ის გარეშე). „Read layers“ ღილაკი კი ცხად შეცდომას აჩვენებს."""
        if self.gdb_var.get().strip():
            self._load_layers(silent=True)

    def _remove_db(self):
        """მიმდინარე ბაზის ამოღება ჩამოსაშლელი სიიდან (მუდმივადაც)."""
        gdb = self.gdb_var.get().strip()
        if gdb not in self._databases:
            return
        if not messagebox.askyesno("GIS_BOX", f"{self.tr('db_remove_q')}\n\n{gdb}"):
            return
        self._databases.remove(gdb)
        self.gdb_combo["values"] = self._databases
        cfg = self.app.get_tool_config(self.tid)
        cfg["databases"] = self._databases
        self.app.set_tool_config(self.tid, cfg)
        self.gdb_var.set(self._databases[0] if self._databases else "")

    # ---- ბაზის დამხმარეები ----
    def _browse_gdb(self):
        p = filedialog.askdirectory(title=self.tr("pick_gdb"))
        if p:
            self.gdb_var.set(p)
            self._load_layers()

    def _load_layers(self, silent=False):
        """ბაზიდან შრეების და ველების წაკითხვა — ფონურ ნაკადში, რომ დიდი/ქსელური
        .gdb-ის კითხვამ მთელი პროგრამა არ გააჭედოს. შედეგი queue-თი ბრუნდება და
        მთავარ ნაკადში ივსება (Tk-ის widget-ები მხოლოდ იქ იცვლება).

        კონკრეტული (კონფიგში მითითებული) შრე რჩება ნაგულისხმევად, თუ ბაზაშია;
        თუ არა — პირველი. silent=True — popup-ების გარეშე (ავტოწაკითხვა)."""
        gdb = self.gdb_var.get().strip()
        if not os.path.exists(gdb):
            if not silent:
                messagebox.showerror(self.tr("err"), self.tr("err_gdb"))
            return
        # მიმდინარე მნიშვნელობებს მთავარ ნაკადში ვკითხულობთ (Tk thread-safe არაა)
        cur_layer = self._layer_code(self.layer_var.get())
        cur_field = self.field_var.get()
        self._meta_gen += 1
        gen = self._meta_gen
        self.status.set(self.tr("reading_layers"))
        threading.Thread(target=self._meta_worker,
                         args=(gen, gdb, cur_layer, cur_field, silent),
                         daemon=True).start()

    def _meta_worker(self, gen, gdb, cur_layer, cur_field, silent):
        """ფონური: შრეების სია + არჩეული შრის ველები. ცდომილება/შედეგი queue-ში."""
        try:
            layers = [row[0] for row in pyogrio.list_layers(gdb)]
            if not layers:
                self.msg_queue.put(("meta_empty", (gen, silent)))
                return
            displays = [self._layer_display(l) for l in layers]
            match = next((d for d, l in zip(displays, layers) if l == cur_layer),
                         None)
            chosen_display = match or displays[0]
            chosen_layer = self._layer_code(chosen_display)
            fields, chosen_field = None, cur_field
            try:                       # ველების წაკითხვა იმავე ნაკადში
                info = pyogrio.read_info(gdb, layer=chosen_layer)
                fields = list(info["fields"])
                chosen_field = pick_code_field(fields, cur_field, DEFAULT_FIELD)
            except Exception:          # noqa: BLE001 — შრეები მაინც ჩავსვათ
                pass
            self.msg_queue.put(("meta", {
                "gen": gen, "silent": silent, "displays": displays,
                "chosen_display": chosen_display, "fields": fields,
                "chosen_field": chosen_field,
            }))
        except Exception as e:         # noqa: BLE001
            self.msg_queue.put(("meta_err", (gen, silent, str(e))))

    _layer_display = staticmethod(layer_display)
    _layer_code = staticmethod(layer_code)

    def _load_fields(self, silent=False):
        """მხოლოდ ველების ხელახალი წაკითხვა (შრის შეცვლისას) — ფონურ ნაკადში."""
        gdb = self.gdb_var.get().strip()
        layer = self._layer_code(self.layer_var.get().strip())
        cur_field = self.field_var.get()
        if not gdb or not layer:
            return
        self._meta_gen += 1
        gen = self._meta_gen
        self.status.set(self.tr("reading_fields"))
        threading.Thread(target=self._fields_worker,
                         args=(gen, gdb, layer, cur_field, silent),
                         daemon=True).start()

    def _fields_worker(self, gen, gdb, layer, cur_field, silent):
        try:
            info = pyogrio.read_info(gdb, layer=layer)
            fields = list(info["fields"])
            chosen = pick_code_field(fields, cur_field, DEFAULT_FIELD)
            self.msg_queue.put(("fields", {
                "gen": gen, "fields": fields, "chosen_field": chosen,
            }))
        except Exception as e:         # noqa: BLE001
            self.msg_queue.put(("meta_err", (gen, silent, str(e))))

    # ---- შეყვანის დამხმარეები ----
    def _load_file(self):
        path = filedialog.askopenfilename(
            title=self.tr("pick_file"),
            filetypes=[(self.tr("ft_tables"), "*.csv *.xlsx *.xls"), (self.tr("ft_all"), "*.*")],
        )
        if not path:
            return
        try:
            if path.lower().endswith((".xlsx", ".xls")):
                df = pd.read_excel(path, dtype=str)
            else:
                df = pd.read_csv(path, dtype=str, sep=None, engine="python")
        except Exception as e:
            messagebox.showerror(self.tr("err"), self.tr("file_read_err", e=e))
            return

        col = self._ask_column(list(df.columns))
        if not col:
            return
        codes = [normalize(v) for v in df[col].tolist() if normalize(v)]
        self.codes_text.delete("1.0", "end")
        self.codes_text.insert("1.0", "\n".join(codes))
        self._log(self.tr("log_loaded", n=len(codes), col=col))

    def _ask_column(self, columns):
        """დიალოგი სვეტის ასარჩევად."""
        dlg = tk.Toplevel(self)
        dlg.title(self.tr("pick_col_title"))
        dlg.geometry("360x140")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        ttk.Label(dlg, text=self.tr("pick_col_q")).pack(padx=12, pady=10)
        var = tk.StringVar(value=columns[0] if columns else "")
        cb = ttk.Combobox(dlg, textvariable=var, values=columns, state="readonly")
        cb.pack(padx=12, pady=6, fill="x")
        result = {"col": None}
        def ok():
            result["col"] = var.get()
            dlg.destroy()
        ttk.Button(dlg, text=self.tr("ok"), command=ok).pack(pady=10)
        self.wait_window(dlg)
        return result["col"]

    def _browse_out(self):
        p = filedialog.asksaveasfilename(
            title=self.tr("out_file_title"),
            defaultextension=".shp",
            filetypes=[("Shapefile", "*.shp"), ("GeoPackage", "*.gpkg")],
        )
        if p:
            self.out_var.set(p)

    # ---- ძებნის გაშვება ----
    def _start_search(self):
        if self.searching:
            return
        gdb = self.gdb_var.get().strip()
        layer = self._layer_code(self.layer_var.get().strip())   # ნამდვილი შრის სახელი
        field = self.field_var.get().strip()
        out_path = self.out_var.get().strip()

        if not os.path.exists(gdb):
            messagebox.showerror(self.tr("err"), self.tr("err_gdb"))
            return
        if not (layer and field):
            messagebox.showerror(self.tr("err"), self.tr("err_layer_field"))
            return
        formats = []
        if self.shp_var.get():
            formats.append("shp")
        if self.gpkg_var.get():
            formats.append("gpkg")
        # გამომავალი გზა საჭიროა მხოლოდ მაშინ, თუ რომელიმე ფაილს ვქმნით
        if formats and not out_path:
            messagebox.showerror(self.tr("err"), self.tr("err_out"))
            return

        codes = parse_manual_codes(self.codes_text.get("1.0", "end"))
        if not codes:
            messagebox.showerror(self.tr("err"), self.tr("err_codes_empty"))
            return

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.searching = True
        self._cancel_event.clear()
        self.search_btn.configure(state="disabled", text=self.tr("btn_search_busy"))
        self.cancel_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=100)
        self.status.set(self.tr("searching"))

        t = threading.Thread(
            target=run_search,
            args=(gdb, layer, field, codes, out_path,
                  lambda m: self.msg_queue.put(("log", m)),
                  lambda r: self.msg_queue.put(("done", r)),
                  self.tr, formats,
                  lambda i, n: self.msg_queue.put(("progress", (i, n))),
                  self._cancel_event.is_set),
            daemon=True,
        )
        t.start()

    def _cancel_search(self):
        if self.searching:
            self._cancel_event.set()
            self.cancel_btn.configure(state="disabled")
            self.status.set(self.tr("cancelling"))

    # ---- queue / ლოგი ----
    def _poll_queue(self):
        # frame შესაძლოა განადგურდეს ენის/თემის ცვლილებისას — მაშინ ვჩერდებით.
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    i, n = payload
                    self.progress.configure(maximum=n, value=i)
                    self.status.set(self.tr("progress", i=i, n=n))
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "meta":
                    self._apply_meta(payload)
                elif kind == "fields":
                    self._apply_fields(payload)
                elif kind == "meta_empty":
                    gen, silent = payload
                    if gen == self._meta_gen:
                        if not self.searching:
                            self.status.set(self.tr("ready"))
                        if not silent:
                            messagebox.showwarning(self.tr("empty_title"),
                                                   self.tr("no_layers"))
                elif kind == "meta_err":
                    gen, silent, msg = payload
                    if gen == self._meta_gen:
                        if not self.searching:
                            self.status.set(self.tr("ready"))
                        if not silent:
                            messagebox.showerror(self.tr("err"), msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _apply_meta(self, d):
        """ფონურად წაკითხული შრეები/ველები — widget-ებში (მთავარ ნაკადში)."""
        if d["gen"] != self._meta_gen:
            return                          # უფრო ახალმა წაკითხვამ გადაასწრო
        self.layer_combo["values"] = d["displays"]
        self.layer_var.set(d["chosen_display"])
        if d["fields"] is not None:
            self.field_combo["values"] = d["fields"]
            self.field_var.set(d["chosen_field"])
        self._log(self.tr("log_layers", layers=", ".join(d["displays"])))
        if not self.searching:
            self.status.set(self.tr("ready"))

    def _apply_fields(self, d):
        if d["gen"] != self._meta_gen:
            return
        self.field_combo["values"] = d["fields"]
        self.field_var.set(d["chosen_field"])
        if not self.searching:
            self.status.set(self.tr("ready"))

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.app.log(msg)  # საერთო ლოგშიც

    def _on_done(self, result):
        self.searching = False
        self.search_btn.configure(state="normal", text=self.tr("btn_search"))
        self.cancel_btn.configure(state="disabled")

        if result.get("cancelled"):
            self.progress.configure(value=0)
            self.status.set(self.tr("cancelled"))
            self._log("— " + self.tr("cancelled"))
            return

        if "error" in result:
            self.progress.configure(value=0)
            self.status.set(self.tr("err") + ".")
            self._log(self.tr("done_err_hdr"))
            self._log(result["error"])
            messagebox.showerror(self.tr("err"), result["error"].split("\n")[0])
            return

        found = result["found_list"]
        not_found = result["not_found"]
        self.last_not_found = not_found

        self._log("")
        self._log("=" * 50)
        self._log(self.tr("sum_total", n=len(result['requested'])))
        self._log(self.tr("sum_found", n=len(found)))
        self._log(self.tr("sum_nf", n=len(not_found)))
        if result.get("search_only"):
            self._log(self.tr("sum_search_only"))
        else:
            self._log(self.tr("sum_written", n=result['written']))
            for fp in result.get("out_files", []):
                self._log(self.tr("sum_file", p=fp))
        self._log("=" * 50)

        if not_found:
            self._log("")
            self._log(self.tr("nf_list_hdr"))
            for c in not_found:
                self._log(f"  ✗ {c}")

        self.status.set(self.tr("done_status", f=len(found), nf=len(not_found)))

        # ვერ ნაპოვნის ავტომატური შენახვა shapefile-ის გვერდით
        if not_found and result["out_path"]:
            side = os.path.splitext(result["out_path"])[0] + "_NOT_FOUND.txt"
            try:
                with open(side, "w", encoding="utf-8") as f:
                    f.write("\n".join(not_found))
                self._log(self.tr("nf_saved", p=side))
            except Exception:
                pass

    def _save_not_found(self):
        if not self.last_not_found:
            messagebox.showinfo(self.tr("info"), self.tr("no_nf"))
            return
        p = filedialog.asksaveasfilename(
            title=self.tr("save_nf_title"),
            defaultextension=".txt",
            filetypes=[(self.tr("ft_txt"), "*.txt"), ("CSV", "*.csv")],
        )
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(self.last_not_found))
        messagebox.showinfo(self.tr("saved_title"), self.tr("saved_n", n=len(self.last_not_found)))
