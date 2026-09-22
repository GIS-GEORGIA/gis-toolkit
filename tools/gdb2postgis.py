# -*- coding: utf-8 -*-
"""GDB/MDB → PostGIS — GIS_BOX-ის ხელსაწყო (tkinter UI ძრავ core-ზე).

ESRI File/Personal Geodatabase-ის (`.gdb`/`.mdb`) შრეებს ატანს PostgreSQL/
PostGIS-ში `ogr2ogr`-ით. ძრავა (`tools.gdb2postgis_core`) GUI-სგან თავისუფალია
და აღებულია დამოუკიდებელი gdb2postgis პროექტიდან (MIT).

მოთხოვნა (runtime): GDAL-ის `ogr2ogr`/`ogrinfo` (მაგ. QGIS / OSGeo4W) და
PostgreSQL/PostGIS ბაზა. კავშირის პარამეტრები ინახება ლოკალურ, git-ignored
პარამეტრებში; პაროლი ნაგულისხმევად მხოლოდ სესიაშია (არ ინახება).
"""

import os
import sys
import queue
import subprocess
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tools.base import ToolFrame
from tools.tooltip import add_tip
from tools import gdb2postgis_core as core
from tools.gdb2postgis_state import SyncState
from tools.gdb2postgis_audit import AuditStore

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_NAME = "GIS_BOX_gdb2postgis"     # Windows Task Scheduler-ის დავალების სახელი


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _task_command():
    """ბრძანება, რომელსაც Task Scheduler გაუშვებს — headless GDB → PostGIS."""
    exe = sys.executable
    if getattr(sys, "frozen", False):                 # PyInstaller-ის .exe
        return f'"{exe}" --gdb2pg-run'
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")   # კონსოლის გარეშე
    runner = pyw if os.path.exists(pyw) else exe
    return f'"{runner}" "{os.path.join(_APP_DIR, "gis_box.py")}" --gdb2pg-run'


def register_task(schedule_kind, every):
    """schtasks-ით ფონური დავალების რეგისტრაცია (Windows). (ok, message)."""
    r = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", _task_command(),
         "/SC", schedule_kind, "/MO", str(every), "/F"],
        capture_output=True, text=True, creationflags=_no_window())
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def unregister_task():
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                   capture_output=True, text=True, creationflags=_no_window())


CATALOG = {
    "heading":  {"en": "GDB/MDB → PostGIS", "ka": "GDB/MDB → PostGIS"},
    "desc":     {"en": "Load Geodatabase (.gdb/.mdb) layers into PostgreSQL/PostGIS "
                       "with ogr2ogr. Needs GDAL (QGIS/OSGeo4W) and a PostGIS database.",
                 "ka": "Geodatabase-ის (.gdb/.mdb) შრეების ატანა PostgreSQL/PostGIS-ში "
                       "ogr2ogr-ით. სჭირდება GDAL (QGIS/OSGeo4W) და PostGIS ბაზა."},
    "gdal":     {"en": "GDAL (ogr2ogr):", "ka": "GDAL (ogr2ogr):"},
    "gdal_ok":  {"en": "found — {v}", "ka": "ნაპოვნია — {v}"},
    "gdal_missing": {"en": "not found — set the ogr2ogr path",
                     "ka": "ვერ მოიძებნა — მიუთითე ogr2ogr-ის გზა"},
    "source_dir": {"en": "Source folder:", "ka": "წყარო საქაღალდე:"},
    "browse":   {"en": "Browse…", "ka": "დათვალიერება…"},
    "source":   {"en": "Source (.gdb/.mdb):", "ka": "წყარო (.gdb/.mdb):"},
    "no_sources": {"en": "No .gdb/.mdb found in the folder.",
                   "ka": "საქაღალდეში .gdb/.mdb ვერ მოიძებნა."},
    "layers":   {"en": "Layers (select to import):",
                 "ka": "შრეები (მონიშნე ასატანი):"},
    "sel_all":  {"en": "Select all", "ka": "ყველა"},
    "sel_none": {"en": "None", "ka": "არცერთი"},
    "conn":     {"en": "PostGIS connection", "ka": "PostGIS კავშირი"},
    "host":     {"en": "Host", "ka": "ჰოსტი"},
    "port":     {"en": "Port", "ka": "პორტი"},
    "dbname":   {"en": "Database", "ka": "ბაზა"},
    "user":     {"en": "User", "ka": "მომხმარებელი"},
    "password": {"en": "Password", "ka": "პაროლი"},
    "schema":   {"en": "Schema", "ka": "სქემა"},
    "remember_pw": {"en": "remember password (local)", "ka": "პაროლის დამახსოვრება (ლოკალურად)"},
    "test_conn":{"en": "Test connection", "ka": "კავშირის შემოწმება"},
    "conn_ok":  {"en": "Connection OK.", "ka": "კავშირი წარმატებულია."},
    "conn_fail":{"en": "Connection failed:", "ka": "კავშირი ვერ დამყარდა:"},
    "opts":     {"en": "Options", "ka": "პარამეტრები"},
    "mode":     {"en": "Mode", "ka": "რეჟიმი"},
    "reproj":   {"en": "Reproject (e.g. EPSG:4326)", "ka": "რეპროექცია (მაგ. EPSG:4326)"},
    "prefix":   {"en": "Table prefix", "ka": "ცხრილის პრეფიქსი"},
    "promote":  {"en": "Promote to multi", "ka": "Promote to multi"},
    "gist":     {"en": "Spatial index (GiST)", "ka": "სივრცული ინდექსი (GiST)"},
    "copy":     {"en": "Fast COPY", "ka": "სწრაფი COPY"},
    "incr_group": {"en": "Incremental sync", "ka": "ინკრემენტული სინქრონი"},
    "incr_enable": {"en": "Incremental (only changed rows)",
                    "ka": "ინკრემენტული (მხოლოდ ცვლილებები)"},
    "key_field": {"en": "Key field", "ka": "key ველი"},
    "track_field": {"en": "Change field", "ka": "ცვლილების ველი"},
    "auto_fields": {"en": "Auto-detect fields", "ka": "ველების ავტო-აღმოჩენა"},
    "detect_deletes": {"en": "Detect deletes", "ka": "წაშლილების დეტექცია"},
    "incr_hint": {"en": "First run per layer = full load + watermark; then only rows "
                        "where change > watermark (upsert by key). Empty = auto.",
                  "ka": "თითო შრის პირველი გაშვება = სრული load + watermark; მერე მხოლოდ "
                        "ცვლილება > watermark (upsert key-ით). ცარიელი = ავტო."},
    "auto_need_one": {"en": "Select exactly one layer to auto-detect fields.",
                      "ka": "ავტო-აღმოჩენისთვის მონიშნე ზუსტად ერთი შრე."},
    "auto_done": {"en": "Detected — key: {k}, change: {t}",
                  "ka": "აღმოჩენილია — key: {k}, ცვლილება: {t}"},
    "sched_group": {"en": "Scheduler", "ka": "განრიგი"},
    "sched_enable": {"en": "Run automatically every", "ka": "ავტომატურად ყოველ"},
    "unit_min":  {"en": "minutes", "ka": "წუთი"},
    "unit_hour": {"en": "hours", "ka": "საათი"},
    "unit_day":  {"en": "days", "ka": "დღე"},
    "sched_apply": {"en": "Apply", "ka": "გამოყენება"},
    "next_run":  {"en": "Next run: {t}", "ka": "შემდეგი გაშვება: {t}"},
    "sched_off": {"en": "Scheduler off.", "ka": "განრიგი გამორთულია."},
    "sched_skip":{"en": "Scheduled run skipped (busy or no layers selected).",
                  "ka": "განრიგის გაშვება გამოტოვდა (დაკავებული ან შრე არაა მონიშნული)."},
    "sched_hint":{"en": "Uses the current source, selected layers and settings above.",
                  "ka": "იყენებს მიმდინარე წყაროს, მონიშნულ შრეებსა და ზემოთ პარამეტრებს."},
    "sched_fire":{"en": "— Scheduled run —", "ka": "— განრიგით გაშვება —"},
    "bg_enable": {"en": "Even when GIS_BOX is closed (Windows Task Scheduler)",
                  "ka": "GIS_BOX-ის დახურვის შემდეგაც (Windows Task Scheduler)"},
    "bg_registered": {"en": "Background task registered (runs even when closed).",
                      "ka": "ფონური დავალება რეგისტრირდა (მუშაობს დახურვის შემდეგაც)."},
    "bg_removed": {"en": "Background task removed.", "ka": "ფონური დავალება წაიშალა."},
    "bg_win_only": {"en": "Background scheduling is Windows-only.",
                    "ka": "ფონური განრიგი მხოლოდ Windows-ზეა."},
    "bg_fail":   {"en": "Could not register the background task (admin rights may be needed):",
                  "ka": "ფონური დავალება ვერ დარეგისტრირდა (შესაძლოა ადმინ. უფლებები სჭირდება):"},
    "bg_no_pw":  {"en": "Tip: tick “remember password” (or set PGPASSWORD), otherwise "
                        "background runs cannot authenticate.",
                  "ka": "რჩევა: მონიშნე „პაროლის დამახსოვრება“ (ან დააყენე PGPASSWORD), "
                        "თორემ ფონური გაშვება ვერ დაამოწმებს."},
    "import":   {"en": "▶ Import", "ka": "▶ იმპორტი"},
    "history":  {"en": "🕘 History…", "ka": "🕘 ისტორია…"},
    "hist_title": {"en": "GDB → PostGIS — history", "ka": "GDB → PostGIS — ისტორია"},
    "hist_date": {"en": "Date:", "ka": "თარიღი:"},
    "hist_none": {"en": "No history yet.", "ka": "ისტორია ჯერ არ არის."},
    "col_time":  {"en": "time", "ka": "დრო"},
    "col_layer": {"en": "layer", "ka": "შრე"},
    "col_mode":  {"en": "mode", "ka": "რეჟიმი"},
    "col_aff":   {"en": "affected", "ka": "შეხებული"},
    "col_del":   {"en": "deleted", "ka": "წაშლილი"},
    "col_ok":    {"en": "ok", "ka": "ok"},
    "col_table": {"en": "table", "ka": "ცხრილი"},
    "hist_ids":  {"en": "Feature IDs (key → action):", "ka": "ობიექტების ID (key → მოქმედება):"},
    "hist_del_feats": {"en": "Delete these features from target",
                       "ka": "ამ ობიექტების წაშლა ბაზიდან"},
    "hist_del_rec": {"en": "Delete this history record", "ka": "ამ ჩანაწერის წაშლა"},
    "hist_pick_run": {"en": "Select a run first.", "ka": "ჯერ აირჩიე გაშვება."},
    "hist_del_feats_q": {"en": "Delete {n} feature(s) from {t}? This changes the database.",
                         "ka": "წავშალო {n} ობიექტი {t}-დან? ეს ცვლის ბაზას."},
    "hist_deleted": {"en": "Deleted {n} feature(s).", "ka": "წაიშალა {n} ობიექტი."},
    "hist_no_key": {"en": "This run has no key field / stored IDs — cannot delete features.",
                    "ka": "ამ გაშვებას key ველი / შენახული ID არ აქვს — წაშლა ვერ ხერხდება."},
    "cancel":   {"en": "✖ Cancel", "ka": "✖ გაუქმება"},
    "remember": {"en": "💾 Remember settings", "ka": "💾 პარამეტრების დამახსოვრება"},
    "saved":    {"en": "Settings saved (password not stored unless ticked).",
                 "ka": "პარამეტრები შენახულია (პაროლი მხოლოდ თოლიის მონიშვნისას)."},
    "warn_gdal":{"en": "ogr2ogr / ogrinfo not found. Set a valid GDAL path.",
                 "ka": "ogr2ogr / ogrinfo ვერ მოიძებნა. მიუთითე GDAL-ის გზა."},
    "warn_source": {"en": "Choose a source (.gdb/.mdb).", "ka": "აირჩიე წყარო (.gdb/.mdb)."},
    "warn_layers": {"en": "Select at least one layer.", "ka": "მონიშნე მინიმუმ ერთი შრე."},
    "running":  {"en": "Importing…", "ka": "მიმდინარეობს იმპორტი…"},
    "done":     {"en": "Done — OK {ok}, failed {fail}.", "ka": "დასრულდა — OK {ok}, ჩავარდა {fail}."},
    "cancelled":{"en": "Cancelled.", "ka": "გაუქმდა."},

    # --- tooltip-ები (hover-მინიშნებები) ---
    "tip_browse_ogr": {"en": "Pick ogr2ogr.exe (from QGIS/OSGeo4W) if not auto-detected.",
                       "ka": "მიუთითე ogr2ogr.exe (QGIS/OSGeo4W-დან), თუ ავტომატურად ვერ იპოვა."},
    "tip_browse_dir": {"en": "Folder that contains your .gdb / .mdb.",
                       "ka": "საქაღალდე, სადაც შენი .gdb / .mdb-ია."},
    "tip_source": {"en": "Choose the Geodatabase to read layers from.",
                   "ka": "აირჩიე Geodatabase, საიდანაც შრეები წაიკითხოს."},
    "tip_layers": {"en": "Select layers to import (Ctrl/Shift for several).",
                   "ka": "მონიშნე ასატანი შრეები (Ctrl/Shift — რამდენიმე)."},
    "tip_test":   {"en": "Check the PostGIS connection before importing.",
                   "ka": "იმპორტამდე შეამოწმე PostGIS-კავშირი."},
    "tip_remember_pw": {"en": "Store the password locally — needed for background runs.",
                        "ka": "პაროლი ლოკალურად შეინახე — ფონურ გაშვებას სჭირდება."},
    "tip_mode":   {"en": "overwrite = recreate table (first load); append = add rows; "
                         "update = update existing.",
                   "ka": "overwrite = ცხრილს თავიდან ქმნის (პირველი load); append = რიგებს ამატებს; "
                         "update = არსებულს ანახლებს."},
    "tip_promote": {"en": "Convert Point/Line/Polygon to Multi* — avoids type-mix errors.",
                    "ka": "Point/Line/Polygon → Multi* — თავიდან ირიდებს ტიპის-შერევის შეცდომას."},
    "tip_gist":   {"en": "Create a spatial (GiST) index — faster queries.",
                   "ka": "სივრცული (GiST) ინდექსი — სწრაფი მოთხოვნები."},
    "tip_copy":   {"en": "Fast COPY load. Turn OFF to see the real error on failures.",
                   "ka": "სწრაფი COPY. ჩავარდნისას გამორთე ნამდვილი შეცდომის სანახავად."},
    "tip_incr":   {"en": "Sync only changed rows (upsert by key). Needs key + change field.",
                   "ka": "მხოლოდ ცვლილებების სინქრონი (upsert key-ით). სჭირდება key + change ველი."},
    "tip_auto":   {"en": "Auto-fill key & change fields from the selected layer.",
                   "ka": "key და change ველების ავტო-შევსება არჩეული შრიდან."},
    "tip_deletes":{"en": "Also remove target rows deleted in the source.",
                   "ka": "წყაროში წაშლილ ობიექტებს სამიზნიდანაც აშორებს."},
    "tip_key":    {"en": "Unique id, e.g. OBJECTID / GlobalID (empty = auto).",
                   "ka": "უნიკალური id, მაგ. OBJECTID / GlobalID (ცარიელი = ავტო)."},
    "tip_track":  {"en": "Change timestamp, e.g. last_edited_date (empty = auto).",
                   "ka": "ცვლილების თარიღი, მაგ. last_edited_date (ცარიელი = ავტო)."},
    "tip_sched":  {"en": "Run automatically at the interval (while GIS_BOX is open).",
                   "ka": "ავტომატური გაშვება ინტერვალით (სანამ GIS_BOX ღიაა)."},
    "tip_apply":  {"en": "Apply / update the schedule.",
                   "ka": "განრიგის გამოყენება / განახლება."},
    "tip_bg":     {"en": "Register a Windows task so it runs even when GIS_BOX is closed.",
                   "ka": "Windows-დავალება — მუშაობს GIS_BOX-ის დახურვის შემდეგაც."},
    "tip_import": {"en": "Import the selected layers now.",
                   "ka": "მონიშნული შრეების იმპორტი ახლა."},
    "tip_cancel": {"en": "Stop the current import (between layers).",
                   "ka": "მიმდინარე იმპორტის შეჩერება (შრეებს შორის)."},
    "tip_remember": {"en": "Save all settings, chosen source and selected layers.",
                     "ka": "შეინახე ყველა პარამეტრი, არჩეული ბაზა და მონიშნული შრეები."},
    "tip_history": {"en": "Browse past runs by date; drill into IDs; delete features/records.",
                    "ka": "წარსული გაშვებები თარიღით; ID-ები; ობიექტების/ჩანაწერის წაშლა."},
    "tip_sel_all": {"en": "Select all layers.", "ka": "ყველა შრის მონიშვნა."},
    "tip_sel_none":{"en": "Clear layer selection.", "ka": "მონიშვნის გასუფთავება."},
}


class Gdb2PostgisTool(ToolFrame):
    tid = "gdb2postgis"
    CATALOG = CATALOG

    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    def build(self):
        pal = self.app.palette
        saved = self.app.get_tool_config(self.tid)
        self.msg_queue = queue.Queue()
        self.running = False
        self._cancel_event = threading.Event()
        self._sources = {}                 # basename -> full path
        # დამახსოვრებული არჩევანი — ბაზა და მონიშნული შრეები (ავტომატიზაციისთვის)
        self._saved_source = saved.get("source", "")
        self._saved_layers = saved.get("layers", [])

        def cfg(key, default=""):
            return saved.get(key, default)

        # --- სქროლადი content (ხელსაწყო ფანჯარაზე მაღალია) ---
        canvas = tk.Canvas(self, highlightthickness=0, bg=pal["bg"])
        vbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))

        def _wheel(e):
            step = 1 if (getattr(e, "num", 0) == 5 or getattr(e, "delta", 0) < 0) else -1
            canvas.yview_scroll(step, "units")
        canvas.bind("<Enter>", lambda e: (canvas.bind_all("<MouseWheel>", _wheel),
                                          canvas.bind_all("<Button-4>", _wheel),
                                          canvas.bind_all("<Button-5>", _wheel)))
        canvas.bind("<Leave>", lambda e: (canvas.unbind_all("<MouseWheel>"),
                                          canvas.unbind_all("<Button-4>"),
                                          canvas.unbind_all("<Button-5>")))

        ttk.Label(body, text=self.tr("heading"),
                  font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(body, text=self.tr("desc"), foreground=pal["muted"],
                  wraplength=680, justify="left").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))

        # --- GDAL ---
        ttk.Label(body, text=self.tr("gdal")).grid(row=2, column=0, sticky="w")
        self.ogr2ogr_var = tk.StringVar(value=cfg("ogr2ogr"))
        ttk.Entry(body, textvariable=self.ogr2ogr_var).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=6)
        add_tip(ttk.Button(body, text=self.tr("browse"), command=self._pick_ogr),
                self.tr("tip_browse_ogr")).grid(row=2, column=3, sticky="ew")
        self.gdal_status = ttk.Label(body, text="", foreground=pal["muted"])
        self.gdal_status.grid(row=3, column=1, columnspan=3, sticky="w", pady=(0, 8))

        # --- Source ---
        ttk.Label(body, text=self.tr("source_dir")).grid(row=4, column=0, sticky="w")
        self.dir_var = tk.StringVar(value=cfg("source_dir"))
        ttk.Entry(body, textvariable=self.dir_var).grid(row=4, column=1, columnspan=2, sticky="ew", padx=6)
        add_tip(ttk.Button(body, text=self.tr("browse"), command=self._pick_dir),
                self.tr("tip_browse_dir")).grid(row=4, column=3, sticky="ew")

        ttk.Label(body, text=self.tr("source")).grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.source_var = tk.StringVar()
        self.source_combo = ttk.Combobox(body, textvariable=self.source_var, state="readonly")
        self.source_combo.grid(row=5, column=1, columnspan=3, sticky="ew", padx=6, pady=(6, 0))
        self.source_combo.bind("<<ComboboxSelected>>", lambda e: self._load_layers())

        # --- Layers ---
        lay = ttk.Frame(body)
        lay.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=(8, 8))
        ttk.Label(lay, text=self.tr("layers")).pack(anchor="w")
        box = ttk.Frame(lay)
        box.pack(fill="both", expand=True)
        self.layers_list = tk.Listbox(box, selectmode="extended", height=6,
                                      bg=pal["field_bg"], fg=pal["field_fg"],
                                      exportselection=False)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.layers_list.yview)
        self.layers_list.configure(yscrollcommand=sb.set)
        self.layers_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        selbtns = ttk.Frame(lay)
        selbtns.pack(anchor="w", pady=(4, 0))
        add_tip(ttk.Button(selbtns, text=self.tr("sel_all"),
                           command=lambda: self.layers_list.selection_set(0, "end")),
                self.tr("tip_sel_all")).pack(side="left")
        add_tip(ttk.Button(selbtns, text=self.tr("sel_none"),
                           command=lambda: self.layers_list.selection_clear(0, "end")),
                self.tr("tip_sel_none")).pack(side="left", padx=(4, 0))

        # --- PostGIS connection ---
        conn = ttk.LabelFrame(body, text=self.tr("conn"), padding=8)
        conn.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.host_var = tk.StringVar(value=cfg("host", "localhost"))
        self.port_var = tk.StringVar(value=str(cfg("port", "5432")))
        self.db_var = tk.StringVar(value=cfg("dbname", "postgis"))
        self.user_var = tk.StringVar(value=cfg("user", "postgres"))
        self.pw_var = tk.StringVar(value=cfg("password", ""))
        self.schema_var = tk.StringVar(value=cfg("schema", "public"))
        grid = [("host", self.host_var, 0, 0, 16), ("port", self.port_var, 0, 2, 8),
                ("dbname", self.db_var, 1, 0, 16), ("schema", self.schema_var, 1, 2, 12),
                ("user", self.user_var, 2, 0, 16)]
        for key, var, r, c, w in grid:
            ttk.Label(conn, text=self.tr(key)).grid(row=r, column=c, sticky="w", padx=4, pady=2)
            ttk.Entry(conn, textvariable=var, width=w).grid(row=r, column=c + 1, sticky="w", padx=4)
        ttk.Label(conn, text=self.tr("password")).grid(row=2, column=2, sticky="w", padx=4)
        ttk.Entry(conn, textvariable=self.pw_var, show="•", width=16).grid(row=2, column=3, sticky="w", padx=4)
        self.remember_pw = tk.BooleanVar(value=bool(cfg("password")))
        add_tip(ttk.Checkbutton(conn, text=self.tr("remember_pw"), variable=self.remember_pw),
                self.tr("tip_remember_pw")).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0))
        add_tip(ttk.Button(conn, text=self.tr("test_conn"), command=self._test_conn),
                self.tr("tip_test")).grid(
            row=3, column=2, columnspan=2, sticky="e", padx=4, pady=(4, 0))

        # --- Options ---
        opts = ttk.LabelFrame(body, text=self.tr("opts"), padding=8)
        opts.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        ttk.Label(opts, text=self.tr("mode")).grid(row=0, column=0, sticky="w", padx=4)
        self.mode_var = tk.StringVar(value=cfg("mode", "overwrite"))
        add_tip(ttk.Combobox(opts, textvariable=self.mode_var, state="readonly", width=12,
                             values=["overwrite", "append", "update"]),
                self.tr("tip_mode")).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(opts, text=self.tr("reproj")).grid(row=0, column=2, sticky="w", padx=4)
        self.tsrs_var = tk.StringVar(value=cfg("t_srs", ""))
        ttk.Entry(opts, textvariable=self.tsrs_var, width=14).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(opts, text=self.tr("prefix")).grid(row=1, column=0, sticky="w", padx=4, pady=(4, 0))
        self.prefix_var = tk.StringVar(value=cfg("prefix", ""))
        ttk.Entry(opts, textvariable=self.prefix_var, width=14).grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))
        self.promote_var = tk.BooleanVar(value=cfg("promote", True))
        self.gist_var = tk.BooleanVar(value=cfg("gist", True))
        self.copy_var = tk.BooleanVar(value=cfg("copy", True))
        add_tip(ttk.Checkbutton(opts, text=self.tr("promote"), variable=self.promote_var),
                self.tr("tip_promote")).grid(row=2, column=0, columnspan=2, sticky="w", padx=4)
        add_tip(ttk.Checkbutton(opts, text=self.tr("gist"), variable=self.gist_var),
                self.tr("tip_gist")).grid(row=2, column=2, sticky="w", padx=4)
        add_tip(ttk.Checkbutton(opts, text=self.tr("copy"), variable=self.copy_var),
                self.tr("tip_copy")).grid(row=2, column=3, sticky="w", padx=4)

        # --- Incremental sync ---
        incr = ttk.LabelFrame(body, text=self.tr("incr_group"), padding=8)
        incr.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.incr_var = tk.BooleanVar(value=cfg("incremental", False))
        add_tip(ttk.Checkbutton(incr, text=self.tr("incr_enable"), variable=self.incr_var,
                                command=self._toggle_incr),
                self.tr("tip_incr")).grid(row=0, column=0, columnspan=2, sticky="w", padx=4)
        self.deletes_var = tk.BooleanVar(value=cfg("detect_deletes", False))
        self.deletes_cb = ttk.Checkbutton(incr, text=self.tr("detect_deletes"),
                                          variable=self.deletes_var)
        self.deletes_cb.grid(row=0, column=2, columnspan=2, sticky="w", padx=4)
        ttk.Label(incr, text=self.tr("key_field")).grid(row=1, column=0, sticky="w", padx=4, pady=(4, 0))
        self.key_var = tk.StringVar(value=cfg("key_field", ""))
        self.key_entry = ttk.Entry(incr, textvariable=self.key_var, width=18)
        self.key_entry.grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))
        ttk.Label(incr, text=self.tr("track_field")).grid(row=1, column=2, sticky="w", padx=4, pady=(4, 0))
        self.track_var = tk.StringVar(value=cfg("track_field", ""))
        self.track_entry = ttk.Entry(incr, textvariable=self.track_var, width=18)
        self.track_entry.grid(row=1, column=3, sticky="w", padx=4, pady=(4, 0))
        self.auto_btn = ttk.Button(incr, text=self.tr("auto_fields"), command=self._auto_fields)
        self.auto_btn.grid(row=2, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0))
        ttk.Label(incr, text=self.tr("incr_hint"), foreground=pal["muted"],
                  wraplength=660, justify="left").grid(
            row=3, column=0, columnspan=4, sticky="w", padx=4, pady=(4, 0))

        # --- Scheduler (tkinter after(); no external dependency) ---
        sched = ttk.LabelFrame(body, text=self.tr("sched_group"), padding=8)
        sched.grid(row=10, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.sched_var = tk.BooleanVar(value=cfg("sched_on", False))
        add_tip(ttk.Checkbutton(sched, text=self.tr("sched_enable"), variable=self.sched_var,
                                command=self._apply_schedule),
                self.tr("tip_sched")).grid(row=0, column=0, sticky="w", padx=4)
        self.every_var = tk.StringVar(value=str(cfg("sched_every", "1")))
        ttk.Spinbox(sched, from_=1, to=9999, width=6, textvariable=self.every_var).grid(
            row=0, column=1, sticky="w", padx=4)
        self._unit_map = {self.tr("unit_min"): "minutes",
                          self.tr("unit_hour"): "hours", self.tr("unit_day"): "days"}
        self.unit_var = tk.StringVar()
        self.unit_combo = ttk.Combobox(sched, textvariable=self.unit_var, state="readonly",
                                       width=10, values=list(self._unit_map))
        self.unit_combo.grid(row=0, column=2, sticky="w", padx=4)
        self._set_unit(cfg("sched_unit", "minutes"))
        add_tip(ttk.Button(sched, text=self.tr("sched_apply"), command=self._apply_schedule),
                self.tr("tip_apply")).grid(row=0, column=3, sticky="w", padx=4)
        # ფონური გაშვება — GIS_BOX-ის დახურვის შემდეგაც (Windows Task Scheduler)
        self.bg_var = tk.BooleanVar(value=cfg("sched_bg", False))
        self.bg_cb = ttk.Checkbutton(sched, text=self.tr("bg_enable"),
                                     variable=self.bg_var, command=self._apply_schedule)
        self.bg_cb.grid(row=1, column=0, columnspan=4, sticky="w", padx=4, pady=(4, 0))
        if sys.platform != "win32":
            self.bg_cb.configure(state="disabled")
        self.next_run_var = tk.StringVar(value=self.tr("sched_off"))
        ttk.Label(sched, textvariable=self.next_run_var,
                  font=("Segoe UI", 9, "bold")).grid(row=2, column=0, columnspan=4, sticky="w", padx=4, pady=(4, 0))
        ttk.Label(sched, text=self.tr("sched_hint"), foreground=pal["muted"],
                  wraplength=660, justify="left").grid(row=3, column=0, columnspan=4, sticky="w", padx=4)

        # --- Actions ---
        act = ttk.Frame(body)
        act.grid(row=11, column=0, columnspan=4, sticky="ew")
        self.import_btn = ttk.Button(act, text=self.tr("import"),
                                     style="Accent.TButton", command=self._start_import)
        self.import_btn.pack(side="left")
        self.cancel_btn = ttk.Button(act, text=self.tr("cancel"), command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(6, 0))
        add_tip(ttk.Button(act, text=self.tr("remember"), command=self._remember),
                self.tr("tip_remember")).pack(side="left", padx=(12, 0))
        add_tip(ttk.Button(act, text=self.tr("history"), command=self._open_history),
                self.tr("tip_history")).pack(side="left", padx=(6, 0))
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=12, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        # tooltip-ები ref-იან widget-ებზე
        add_tip(self.source_combo, self.tr("tip_source"))
        add_tip(self.layers_list, self.tr("tip_layers"))
        add_tip(self.key_entry, self.tr("tip_key"))
        add_tip(self.track_entry, self.tr("tip_track"))
        add_tip(self.auto_btn, self.tr("tip_auto"))
        add_tip(self.deletes_cb, self.tr("tip_deletes"))
        add_tip(self.bg_cb, self.tr("tip_bg"))
        add_tip(self.import_btn, self.tr("tip_import"))
        add_tip(self.cancel_btn, self.tr("tip_cancel"))

        body.columnconfigure(1, weight=1)
        body.rowconfigure(6, weight=1)

        self._sync = SyncState()          # ინკრემენტული watermark-ები (git-ignored)
        self._audit = AuditStore()        # გაშვებების ისტორია (git-ignored SQLite)
        self._sched_after_id = None       # scheduler-ის after()-callback
        self._refresh_gdal()
        self._toggle_incr()
        if self.dir_var.get():
            self._scan_sources()
        if self.sched_var.get():          # წინა სესიის განრიგი ხელახლა ჩაირთოს
            self._apply_schedule()
        self.after(100, self._poll)

    # ---- GDAL ----
    def _tools(self):
        ogr2ogr = core.find_tool("ogr2ogr", self.ogr2ogr_var.get().strip() or None)
        ogrinfo = core.find_tool("ogrinfo", self.ogr2ogr_var.get().strip() or None)
        return ogr2ogr, ogrinfo

    def _refresh_gdal(self):
        ogr2ogr, _ = self._tools()
        if ogr2ogr:
            self.gdal_status.configure(text=self.tr("gdal_ok", v=core.gdal_version(ogr2ogr)))
        else:
            self.gdal_status.configure(text=self.tr("gdal_missing"))

    def _pick_ogr(self):
        p = filedialog.askopenfilename(title="ogr2ogr",
                                       filetypes=[("ogr2ogr", "ogr2ogr*"), ("All", "*.*")])
        if p:
            self.ogr2ogr_var.set(os.path.normpath(p))
            self._refresh_gdal()

    # ---- Source / layers ----
    def _pick_dir(self):
        d = filedialog.askdirectory(title=self.tr("source_dir"), initialdir=self.dir_var.get() or None)
        if d:
            self.dir_var.set(os.path.normpath(d))
            self._scan_sources()

    def _scan_sources(self):
        d = self.dir_var.get().strip()
        if not d or not os.path.isdir(d):
            return
        try:
            srcs = core.list_sources(d)
        except Exception:
            srcs = []
        self._sources = {os.path.basename(s): s for s in srcs}
        self.source_combo["values"] = list(self._sources)
        if self._sources:
            want = self._saved_source if self._saved_source in self._sources \
                else next(iter(self._sources))
            self.source_var.set(want)
            self._load_layers()
        else:
            self.source_var.set("")
            self.layers_list.delete(0, "end")
            self.app.log("— " + self.tr("no_sources"))

    def _load_layers(self):
        src = self._sources.get(self.source_var.get())
        _, ogrinfo = self._tools()
        self.layers_list.delete(0, "end")
        self._layer_names = []
        if not src or not ogrinfo:
            return
        try:
            layers = core.list_layers(ogrinfo, src)
        except Exception as e:
            messagebox.showerror(self.tr("err"), str(e))
            return
        for li in layers:
            label = li.name + (f"  ({li.geom_type})" if li.geom_type else "")
            self.layers_list.insert("end", label)
            self._layer_names.append(li.name)      # ნამდვილი სახელი (label-ის გარეშე)
        # დამახსოვრებული შრეების ხელახლა მონიშვნა (მხოლოდ იმავე ბაზისთვის)
        if self.source_var.get() == self._saved_source and self._saved_layers:
            for i, name in enumerate(self._layer_names):
                if name in self._saved_layers:
                    self.layers_list.selection_set(i)

    def _selected_layers(self):
        return [self._layer_names[i] for i in self.layers_list.curselection()
                if i < len(getattr(self, "_layer_names", []))]

    # ---- connection ----
    def _pg(self):
        try:
            port = int(self.port_var.get().strip() or "5432")
        except ValueError:
            port = 5432
        return core.PgConfig(host=self.host_var.get().strip(), port=port,
                             dbname=self.db_var.get().strip(), user=self.user_var.get().strip(),
                             password=self.pw_var.get(), schema=self.schema_var.get().strip() or "public")

    def _test_conn(self):
        _, ogrinfo = self._tools()
        if not ogrinfo:
            messagebox.showwarning("GIS_BOX", self.tr("warn_gdal"))
            return
        ok, msg = core.test_pg_connection(ogrinfo, self._pg())
        if ok:
            messagebox.showinfo("GIS_BOX", self.tr("conn_ok"))
        else:
            messagebox.showerror(self.tr("err"), f"{self.tr('conn_fail')}\n{msg}")

    # ---- incremental ----
    def _toggle_incr(self):
        state = "normal" if self.incr_var.get() else "disabled"
        for w in (self.key_entry, self.track_entry, self.auto_btn, self.deletes_cb):
            w.configure(state=state)

    def _auto_fields(self):
        """არჩეული (ერთადერთი) შრის ველებიდან key/change ველების ავტო-შერჩევა."""
        src = self._sources.get(self.source_var.get())
        _, ogrinfo = self._tools()
        layers = self._selected_layers()
        if not (src and ogrinfo) or len(layers) != 1:
            messagebox.showwarning("GIS_BOX", self.tr("auto_need_one"))
            return
        try:
            names = [f.name for f in core.list_fields(ogrinfo, src, layers[0])]
        except Exception as e:
            messagebox.showerror(self.tr("err"), str(e))
            return
        key = core.auto_detect_key(names)
        track = core.auto_detect_track(names)
        self.key_var.set(key)
        self.track_var.set(track)
        self.app.log("— " + self.tr("auto_done", k=key or "?", t=track or "?"))

    # ---- scheduler (tkinter after(); no external dependency) ----
    def _set_unit(self, canonical):
        for disp, u in self._unit_map.items():
            if u == canonical:
                self.unit_var.set(disp)
                return
        self.unit_var.set(next(iter(self._unit_map)))

    def _interval_ms(self):
        try:
            n = max(1, int(self.every_var.get()))
        except ValueError:
            n = 1
        unit = self._unit_map.get(self.unit_var.get(), "minutes")
        return n * {"minutes": 60_000, "hours": 3_600_000, "days": 86_400_000}[unit]

    def _sc_mo(self):
        """schtasks-ის /SC და /MO — ინტერვალის ერთეულიდან."""
        unit = self._unit_map.get(self.unit_var.get(), "minutes")
        try:
            n = max(1, int(self.every_var.get()))
        except ValueError:
            n = 1
        return {"minutes": "MINUTE", "hours": "HOURLY", "days": "DAILY"}[unit], n

    def _apply_schedule(self):
        # in-app ტაიმერის გაუქმება (ხელახლა დაისმება საჭიროებისამებრ)
        if self._sched_after_id is not None:
            self.after_cancel(self._sched_after_id)
            self._sched_after_id = None

        want_bg = self.bg_var.get() and sys.platform == "win32"

        if not self.sched_var.get():           # განრიგი გამორთულია — ყველაფრის მოხსნა
            if sys.platform == "win32":
                unregister_task()
            self.next_run_var.set(self.tr("sched_off"))
            return

        if want_bg:                            # ფონური — Windows Task Scheduler
            self._persist()                    # task შენახულ კონფიგს კითხულობს
            sc, mo = self._sc_mo()
            ok, msg = register_task(sc, mo)
            if not ok:
                messagebox.showerror(self.tr("err"), f"{self.tr('bg_fail')}\n{msg}")
                self.next_run_var.set(self.tr("sched_off"))
                return
            # პაროლის შეხსენება — უპაროლოდ ფონური გაშვება ვერ დაამოწმებს
            if not (self.remember_pw.get() and self.pw_var.get()):
                self.app.log("— " + self.tr("bg_no_pw"))
            self.next_run_var.set(self.tr("bg_registered"))
            self.app.log("— " + self.tr("bg_registered"))
        else:                                  # in-app ტაიმერი (მხოლოდ ღია აპში)
            if sys.platform == "win32":
                unregister_task()
            self._schedule_next(self._interval_ms())

    def _schedule_next(self, ms):
        from datetime import datetime, timedelta
        nxt = datetime.now() + timedelta(milliseconds=ms)
        self.next_run_var.set(self.tr("next_run", t=nxt.strftime("%Y-%m-%d %H:%M:%S")))
        self._sched_after_id = self.after(ms, self._sched_tick)

    def _sched_tick(self):
        self._sched_after_id = None
        if not self.winfo_exists() or not self.sched_var.get():
            return
        # overlap-ის გარეშე + საჭიროა მონიშნული წყარო/შრეები
        if (not self.running and self._sources.get(self.source_var.get())
                and self._selected_layers()):
            self.app.log(self.tr("sched_fire"))
            self._start_import()
        else:
            self.app.log("— " + self.tr("sched_skip"))
        self._schedule_next(self._interval_ms())      # რესქედულა

    # ---- options / persistence ----
    def _opts(self):
        return core.ImportOptions(
            mode=self.mode_var.get(), t_srs=self.tsrs_var.get().strip(),
            prefix=self.prefix_var.get().strip(), promote_to_multi=self.promote_var.get(),
            spatial_index=self.gist_var.get(), use_copy=self.copy_var.get(),
            incremental=self.incr_var.get(), key_field=self.key_var.get().strip(),
            track_field=self.track_var.get().strip(), detect_deletes=self.deletes_var.get())

    def _persist(self):
        """მიმდინარე პარამეტრების შენახვა tool_config-ში (git-ignored)."""
        data = {
            "ogr2ogr": self.ogr2ogr_var.get().strip(), "source_dir": self.dir_var.get().strip(),
            "host": self.host_var.get().strip(), "port": self.port_var.get().strip(),
            "dbname": self.db_var.get().strip(), "user": self.user_var.get().strip(),
            "schema": self.schema_var.get().strip(), "mode": self.mode_var.get(),
            "t_srs": self.tsrs_var.get().strip(), "prefix": self.prefix_var.get().strip(),
            "promote": self.promote_var.get(), "gist": self.gist_var.get(), "copy": self.copy_var.get(),
            "incremental": self.incr_var.get(), "key_field": self.key_var.get().strip(),
            "track_field": self.track_var.get().strip(), "detect_deletes": self.deletes_var.get(),
            "sched_on": self.sched_var.get(), "sched_every": self.every_var.get().strip(),
            "sched_unit": self._unit_map.get(self.unit_var.get(), "minutes"),
            "sched_bg": self.bg_var.get(),
            # არჩეული ბაზა + მონიშნული შრეები — ავტომატიზაცია იმახსოვრებს რა-სად წავიდეს
            "source": self.source_var.get(), "layers": self._selected_layers(),
        }
        if self.remember_pw.get():          # პაროლი მხოლოდ თოლიის მონიშვნისას
            data["password"] = self.pw_var.get()
        self.app.set_tool_config(self.tid, data)
        # რომ ამავე სესიაში მიმდინარე არჩევანი შენარჩუნდეს frame-ის ხელახლა აწყობისას
        self._saved_source = data["source"]
        self._saved_layers = data["layers"]

    def _remember(self):
        self._persist()
        messagebox.showinfo("GIS_BOX", self.tr("saved"))

    # ---- import (thread) ----
    def _start_import(self):
        if self.running:
            return
        ogr2ogr, ogrinfo = self._tools()
        if not (ogr2ogr and ogrinfo):
            messagebox.showwarning("GIS_BOX", self.tr("warn_gdal"))
            return
        src = self._sources.get(self.source_var.get())
        if not src:
            messagebox.showwarning("GIS_BOX", self.tr("warn_source"))
            return
        layers = self._selected_layers()
        if not layers:
            messagebox.showwarning("GIS_BOX", self.tr("warn_layers"))
            return

        self.running = True
        self._cancel_event.clear()
        self.import_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.start(12)
        self.app.log("— " + self.tr("running"))

        pg, opt = self._pg(), self._opts()

        def log_cb(level, message):
            self.msg_queue.put(("log", f"{level}: {message}"))

        def worker():
            try:
                res = core.run_import(ogr2ogr, src, layers, pg, opt, log_cb,
                                      should_cancel=self._cancel_event.is_set,
                                      ogrinfo_path=ogrinfo, state=self._sync,
                                      audit=self._audit, profile="")
                self.msg_queue.put(("done", res))
            except Exception as e:
                self.msg_queue.put(("done", e))

        threading.Thread(target=worker, daemon=True).start()

    def _cancel(self):
        if self.running:
            self._cancel_event.set()
            self.cancel_btn.configure(state="disabled")

    def _poll(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.app.log(payload)
                elif kind == "done":
                    self._on_done(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _on_done(self, payload):
        self.running = False
        self.progress.stop()
        self.import_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        if isinstance(payload, Exception):
            messagebox.showerror(self.tr("err"), str(payload))
            return
        if self._cancel_event.is_set():
            self.app.log("— " + self.tr("cancelled"))
        msg = self.tr("done", ok=payload.ok_count, fail=payload.fail_count)
        self.app.log("— " + msg)
        messagebox.showinfo("GIS_BOX", msg)

    # ---- History (audit) ----
    def _open_history(self):
        dates = self._audit.dates()
        win = tk.Toplevel(self)
        win.title(self.tr("hist_title"))
        win.geometry("780x580")
        win.transient(self.winfo_toplevel())

        top = ttk.Frame(win, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text=self.tr("hist_date")).pack(side="left")
        date_var = tk.StringVar()
        date_cb = ttk.Combobox(top, textvariable=date_var, state="readonly",
                               values=dates, width=16)
        date_cb.pack(side="left", padx=6)
        if not dates:
            ttk.Label(win, text=self.tr("hist_none"), padding=12).pack(anchor="w")
            return

        run_cols = [("time", "col_time", 90), ("layer", "col_layer", 180),
                    ("mode", "col_mode", 90), ("aff", "col_aff", 80),
                    ("del", "col_del", 70), ("ok", "col_ok", 40),
                    ("table", "col_table", 160)]
        runs = ttk.Treeview(win, columns=[c[0] for c in run_cols],
                            show="headings", height=9)
        for cid, key, w in run_cols:
            runs.heading(cid, text=self.tr(key))
            runs.column(cid, width=w, anchor="w")
        runs.pack(fill="both", expand=True, padx=8)

        ttk.Label(win, text=self.tr("hist_ids")).pack(anchor="w", padx=8, pady=(6, 0))
        ids_tree = ttk.Treeview(win, columns=("key", "action"), show="headings", height=8)
        ids_tree.heading("key", text="key")
        ids_tree.heading("action", text="action")
        ids_tree.column("key", width=280)
        ids_tree.column("action", width=100)
        ids_tree.pack(fill="both", expand=True, padx=8)

        run_map = {}

        def load_runs():
            runs.delete(*runs.get_children())
            ids_tree.delete(*ids_tree.get_children())
            run_map.clear()
            for r in self._audit.runs_on(date_var.get()):
                iid = runs.insert("", "end", values=(
                    r["ts"][11:19], r["layer"], r["mode"], r["affected"], r["deleted"],
                    "✓" if r["ok"] else "✗", r["target_table"]))
                run_map[iid] = r

        def load_ids(_evt=None):
            ids_tree.delete(*ids_tree.get_children())
            sel = runs.selection()
            r = run_map.get(sel[0]) if sel else None
            if not r:
                return
            for kv, act in self._audit.id_rows(r["id"]):
                ids_tree.insert("", "end", values=(kv, act))

        def selected_run():
            sel = runs.selection()
            return run_map.get(sel[0]) if sel else None

        def del_feats():
            r = selected_run()
            if not r:
                messagebox.showwarning("GIS_BOX", self.tr("hist_pick_run"))
                return
            ids = self._audit.ids(r["id"], "upsert")
            key = r["key_field"]
            if not (key and ids):
                messagebox.showinfo("GIS_BOX", self.tr("hist_no_key"))
                return
            table = r["target_table"]
            if not messagebox.askyesno("GIS_BOX",
                                       self.tr("hist_del_feats_q", n=len(ids), t=table)):
                return
            _, ogrinfo = self._tools()
            if not ogrinfo:
                messagebox.showwarning("GIS_BOX", self.tr("warn_gdal"))
                return
            n, msg = core.delete_features(ogrinfo, self._pg(), r["schema"], table, key, ids)
            if msg and n == 0:
                messagebox.showerror(self.tr("err"), msg)
            else:
                messagebox.showinfo("GIS_BOX", self.tr("hist_deleted", n=n))
                self.app.log("— " + self.tr("hist_deleted", n=n))

        def del_rec():
            r = selected_run()
            if not r:
                messagebox.showwarning("GIS_BOX", self.tr("hist_pick_run"))
                return
            self._audit.delete_run(r["id"])
            load_runs()

        btns = ttk.Frame(win, padding=8)
        btns.pack(fill="x")
        ttk.Button(btns, text=self.tr("hist_del_feats"), command=del_feats).pack(side="left")
        ttk.Button(btns, text=self.tr("hist_del_rec"), command=del_rec).pack(side="left", padx=6)

        date_cb.bind("<<ComboboxSelected>>", lambda e: load_runs())
        runs.bind("<<TreeviewSelect>>", load_ids)
        date_var.set(dates[0])
        load_runs()
