# -*- coding: utf-8 -*-
"""„ბაზებს შორის მონაცემთა გადატანა“ (Database Data Transfer) — Personal Geodatabase (.mdb) → .mdb.

აირჩევ საწყის და მიმღებ ბაზას, წელს (ნაგულისხმევი 2026) და ფენების შესაბამისობას; ხელსაწყო
**თავდაპირველად მხოლოდ კითხულობს** (ანალიზი), გაჩვენებს ფენებზე რიცხვებს და ითხოვს დადასტურებას,
მერე ერთ ტრანზაქციაში წერს მიმღებში. წყარო ბაზა არასდროს იცვლება; მიმღების არსებული ჩანაწერები
არასდროს იშლება/იცვლება. სუფთა ლოგიკა ``pgdb_transfer_core``-შია (იქვეა ახსნა, რატომ ODBC).
"""

import os
import queue
import threading
import time

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from tools.base import ToolFrame
from tools.platform_utils import UI_FONT, MONO_FONT, open_path
from tools.tooltip import add_tip
from tools import pgdb_transfer_core as core

DEFAULT_YEAR = 2026

KIND_LABEL = {"point": {"en": "POINT", "ka": "წერტილი (POINT)"},
              "line": {"en": "LINE", "ka": "ხაზი (LINE)"},
              "polygon": {"en": "POLYGON", "ka": "პოლიგონი (POLYGON)"}}

DTR = {
    "heading": {"en": "Database Data Transfer", "ka": "ბაზებს შორის მონაცემთა გადატანა"},
    "desc": {"en": "Copies the spatial features of one year (point, line, polygon) from the source "
                   "Personal Geodatabase into the destination one. A record is skipped when the destination "
                   "already holds the same werilis_no with a date in that year. Nothing is ever deleted or "
                   "overwritten, the source is only read, and the destination is written in one transaction "
                   "(all layers or nothing).",
             "ka": "საწყისი Personal Geodatabase-დან მიმღებში გადააქვს არჩეული წლის სივრცითი ობიექტები "
                   "(წერტილი, ხაზი, პოლიგონი). ჩანაწერი გამოტოვდება, თუ მიმღებში უკვე არის იგივე werilis_no "
                   "ამავე წლის თარიღით. არაფერი არ იშლება/გადაიწერება, წყარო მხოლოდ იკითხება, მიმღებში "
                   "ჩაწერა ერთ ტრანზაქციაშია (ყველა ფენა ერთად — ან არაფერი)."},
    "src_box": {"en": "SOURCE database (data is read from here)",
                "ka": "საწყისი ბაზა — აქედან იკითხება მონაცემები"},
    "dst_box": {"en": "DESTINATION database (data is written here)",
                "ka": "მიმღები ბაზა — აქ ჩაიწერება მონაცემები"},
    "src_lbl": {"en": "Source Database (აირჩიე საწყისი ბაზა):", "ka": "აირჩიე საწყისი ბაზა:"},
    "dst_lbl": {"en": "Destination Database (აირჩიე მიმღები ბაზა):", "ka": "აირჩიე მიმღები ბაზა:"},
    "src_shown": {"en": "SOURCE:  {name}   ({size})", "ka": "საწყისი:  {name}   ({size})"},
    "dst_shown": {"en": "DESTINATION:  {name}   ({size})", "ka": "მიმღები:  {name}   ({size})"},
    "none_shown": {"en": "— not selected —", "ka": "— არ არის არჩეული —"},
    "flow": {"en": "▼  data flows from SOURCE to DESTINATION  ▼",
             "ka": "▼  მონაცემები გადადის საწყისიდან მიმღებში  ▼"},
    "browse": {"en": "…", "ka": "…"},
    "pick_title": {"en": "Select a Personal Geodatabase (.mdb)", "ka": "აირჩიე Personal Geodatabase (.mdb)"},
    "opts": {"en": "Options", "ka": "პარამეტრები"},
    "year": {"en": "Year to transfer:", "ka": "გადასატანი წელი:"},
    "tip_year": {"en": "All records with the date field (TariRI) from 1 Jan 00:00:00 to 31 Dec 23:59:59 of this year.",
                 "ka": "ყველა ჩანაწერი, რომლის თარიღი (TariRI) ამ წლის 1 იანვარი 00:00:00 — 31 დეკემბერი 23:59:59 "
                       "შუალედშია."},
    "backup": {"en": "Back up the destination before writing", "ka": "ჩაწერამდე მიმღების სარეზერვო ასლის შექმნა"},
    "tip_backup": {"en": "Copies the destination .mdb next to it (…_backup_DATE.mdb) before anything is written.",
                   "ka": "ჩაწერამდე მიმღები .mdb-ის ასლს ქმნის გვერდით (…_backup_თარიღი.mdb)."},
    "map_box": {"en": "Layers (matched by geometry type, not by name)", "ka": "ფენები (შესაბამისობა გეომეტრიის ტიპით, არა სახელით)"},
    "map_src": {"en": "Source layer", "ka": "საწყისი ფენა"},
    "map_dst": {"en": "Destination layer", "ka": "მიმღები ფენა"},
    "map_ok": {"en": "✓ matched", "ka": "✓ დადგინდა"},
    "map_pick": {"en": "⚠ cannot be matched confidently — choose the layers", "ka": "⚠ დარწმუნებით ვერ დადგინდა — აირჩიე ფენები"},
    "map_missing": {"en": "⚠ no layer of this type", "ka": "⚠ ამ ტიპის ფენა არ არის"},
    "btn_check": {"en": "Check databases", "ka": "ბაზების შემოწმება"},
    "btn_start": {"en": "Start Transfer", "ka": "გადატანის დაწყება"},
    "btn_busy": {"en": "Working…", "ka": "მიმდინარეობს…"},
    "btn_cancel": {"en": "✖ Cancel", "ka": "✖ გაუქმება"},
    "btn_log": {"en": "Open log file", "ka": "ლოგის ფაილის გახსნა"},
    "ready": {"en": "Ready.", "ka": "მზადაა."},
    "t_layer": {"en": "Layer", "ka": "ფენა"},
    "t_found": {"en": "Found in source", "ka": "ნაპოვნია წყაროში"},
    "t_dup": {"en": "Already exists in destination", "ka": "მიმღებში უკვე არის"},
    "t_ins": {"en": "Inserted", "ka": "ჩაიწერა"},
    "t_plan": {"en": "To insert", "ka": "ჩასაწერია"},
    "t_err": {"en": "Errors", "ka": "შეცდომა"},
    "t_total": {"en": "TOTAL", "ka": "ჯამი"},
    "res_box": {"en": "Progress per layer", "ka": "პროგრესი ფენების მიხედვით"},
    "sum_box": {"en": "Transfer summary", "ka": "გადატანის შეჯამება"},
    "err_box": {"en": "Warnings and errors", "ka": "გაფრთხილებები და შეცდომები"},
    "log_path": {"en": "Log file: {p}", "ka": "ლოგის ფაილი: {p}"},

    # ვალიდაცია
    "e_pick_src": {"en": "Select the source database.", "ka": "აირჩიე საწყისი ბაზა."},
    "e_pick_dst": {"en": "Select the destination database.", "ka": "აირჩიე მიმღები ბაზა."},
    "e_not_mdb": {"en": "“{p}” is not an .mdb file.", "ka": "„{p}“ არ არის .mdb ფაილი."},
    "e_missing": {"en": "File not found: {p}", "ka": "ფაილი ვერ მოიძებნა: {p}"},
    "e_same": {"en": "The source and the destination are the same database. Choose two different files.",
               "ka": "საწყისი და მიმღები ერთი და იგივე ბაზაა. აირჩიე ორი განსხვავებული ფაილი."},
    "e_year": {"en": "Enter a valid year (e.g. 2026).", "ka": "მიუთითე სწორი წელი (მაგ. 2026)."},
    "e_map": {"en": "Choose the matching source and destination layer for: {k}.",
              "ka": "აირჩიე შესაბამისი საწყისი და მიმღები ფენა: {k}."},
    "e_nothing": {"en": "No layer can be transferred.", "ka": "ვერცერთი ფენა ვერ გადაიტანება."},
    "code_locked": {"en": "The database is open in another program (ArcGIS Pro, ArcMap, Access…) or locked.\n"
                          "Close it there and try again.\n\n{d}",
                    "ka": "ბაზა ღიაა სხვა პროგრამაში (ArcGIS Pro, ArcMap, Access…) ან დაბლოკილია.\n"
                          "დახურე იქ და სცადე ხელახლა.\n\n{d}"},
    "code_not_found": {"en": "The database file could not be found or opened.\n\n{d}",
                       "ka": "ბაზის ფაილი ვერ მოიძებნა ან ვერ გაიხსნა.\n\n{d}"},
    "code_bad_format": {"en": "This file is not a readable Access (.mdb) database.\n\n{d}",
                        "ka": "ეს ფაილი არ არის წასაკითხი Access (.mdb) ბაზა.\n\n{d}"},
    "code_no_driver": {"en": "The 64-bit “Microsoft Access Database Engine” ODBC driver is not installed.\n"
                             "Install it (Microsoft Access Database Engine 2016 Redistributable, x64).\n\n{d}",
                       "ka": "64-ბიტიანი „Microsoft Access Database Engine“ ODBC დრაივერი დაყენებული არ არის.\n"
                             "დააინსტალირე (Microsoft Access Database Engine 2016 Redistributable, x64).\n\n{d}"},
    "code_no_pyodbc": {"en": "The Python package “pyodbc” is missing. Install it with:  pip install pyodbc\n\n{d}",
                       "ka": "Python-ის პაკეტი „pyodbc“ აკლია. დააინსტალირე:  pip install pyodbc\n\n{d}"},
    "code_not_pgdb": {"en": "This is not an ESRI Personal Geodatabase (the GDB_ system tables are missing).\n\n{d}",
                      "ka": "ეს არ არის ESRI Personal Geodatabase (GDB_ სისტემური ცხრილები არ არის).\n\n{d}"},
    "code_no_space": {"en": "Not enough free disk space for the backup copy.\n\n{d}",
                      "ka": "სარეზერვო ასლისთვის დისკზე საკმარისი ადგილი არ არის.\n\n{d}"},
    "code_verify_failed": {"en": "Verification failed — nothing was written (rolled back).\n\n{d}",
                           "ka": "ვერიფიკაცია ჩავარდა — არაფერი ჩაწერილა (უკან დაბრუნდა).\n\n{d}"},
    "code_cancelled": {"en": "Cancelled — nothing was written.", "ka": "გაუქმდა — არაფერი ჩაწერილა."},
    "code_db_error": {"en": "Database error:\n\n{d}", "ka": "ბაზის შეცდომა:\n\n{d}"},
    "code_readonly": {"en": "The database is read-only.\n\n{d}", "ka": "ბაზა მხოლოდ წასაკითხია.\n\n{d}"},

    # შემოწმება
    "chk_ok": {"en": "Both databases are readable.", "ka": "ორივე ბაზა წაკითხვადია."},
    "chk_dst_locked": {"en": "⚠ The destination is open in another program — close it before transferring.",
                       "ka": "⚠ მიმღები ბაზა ღიაა სხვა პროგრამაში — გადატანამდე დახურე."},
    "chk_dst_writable": {"en": "The destination can be opened for writing.", "ka": "მიმღები ჩაწერისთვის მზადაა."},
    "chk_layer": {"en": "{k}: source '{s}' ({sn} records) → destination '{d}' ({dn} records)",
                  "ka": "{k}: საწყისი '{s}' ({sn} ჩანაწერი) → მიმღები '{d}' ({dn} ჩანაწერი)"},
    "chk_crs_diff": {"en": "   ⚠ coordinate systems differ — geometry will be reprojected",
                     "ka": "   ⚠ კოორდინატთა სისტემები განსხვავდება — გეომეტრია გადაიყვანება"},
    "chk_crs_bad": {"en": "   ⛔ coordinate systems differ and cannot be transformed reliably",
                    "ka": "   ⛔ კოორდინატთა სისტემები განსხვავდება და სანდოდ ვერ გარდაიქმნება"},
    "chk_fields": {"en": "   ⚠ source fields missing in the destination (NOT transferred): {f}",
                   "ka": "   ⚠ წყაროს ველები მიმღებში არ არის (ვერ გადავა): {f}"},
    "chk_schema": {"en": "   ⛔ incompatible schema: {f}", "ka": "   ⛔ სქემა შეუთავსებელია: {f}"},
    "chk_zm": {"en": "   ⛔ Z/M geometry is not supported", "ka": "   ⛔ Z/M გეომეტრია არ მხარდაიჭერება"},

    # დადასტურება
    "conf_title": {"en": "Confirm transfer", "ka": "გადატანის დადასტურება"},
    "conf_head": {"en": "Year {y}.\nFrom: {s}\nTo:   {d}\n", "ka": "წელი {y}.\nსაწყისი: {s}\nმიმღები: {d}\n"},
    "conf_line": {"en": "{k}: found {f}, already in destination {u}, to insert {n}, errors {e}",
                  "ka": "{k}: ნაპოვნია {f}, მიმღებში უკვე არის {u}, ჩასაწერია {n}, შეცდომა {e}"},
    "conf_blocked": {"en": "{k}: SKIPPED — {why}", "ka": "{k}: გამოტოვებულია — {why}"},
    "conf_backup": {"en": "\nA backup copy of the destination will be created first.",
                    "ka": "\nჯერ მიმღების სარეზერვო ასლი შეიქმნება."},
    "conf_nobackup": {"en": "\nNo backup copy will be made.", "ka": "\nსარეზერვო ასლი არ შეიქმნება."},
    "conf_warn": {"en": "\nNotes:", "ka": "\nშენიშვნები:"},
    "conf_ask": {"en": "\nWrite {n} record(s) into the destination now?", "ka": "\nჩაიწეროს {n} ჩანაწერი მიმღებში ახლა?"},
    "conf_nothing": {"en": "There is nothing to insert: every matching record already exists in the destination "
                           "(or no records match the year).",
                     "ka": "ჩასაწერი არაფერია: ყველა შესაბამისი ჩანაწერი მიმღებში უკვე არის (ან წელს ჩანაწერი არ ემთხვევა)."},

    # პროგრესი / შეჯამება
    "st_analysing": {"en": "Analysing (read-only)…", "ka": "ანალიზი (მხოლოდ კითხვა)…"},
    "st_writing": {"en": "Writing to the destination…", "ka": "მიმღებში ჩაწერა…"},
    "st_progress": {"en": "{k}: {i}/{n}", "ka": "{k}: {i}/{n}"},
    "st_done": {"en": "Done — inserted {n} record(s).", "ka": "დასრულდა — ჩაიწერა {n} ჩანაწერი."},
    "st_cancelled": {"en": "Cancelled.", "ka": "გაუქმდა."},
    "st_error": {"en": "Error.", "ka": "შეცდომა."},
    "sum_title": {"en": "TRANSFER SUMMARY", "ka": "გადატანის შეჯამება"},
    "sum_layer": {"en": "{k}:\n   Found in source: {f}\n   Already exists in destination ({y}): {u}\n"
                        "   Inserted: {i}\n   Errors: {e}",
                  "ka": "{k}:\n   ნაპოვნია წყაროში: {f}\n   მიმღებში უკვე არის ({y}): {u}\n"
                        "   ჩაიწერა: {i}\n   შეცდომა: {e}"},
    "sum_total": {"en": "TOTAL:\n   Source records found: {f}\n   Duplicates skipped: {u}\n   Records inserted: {i}\n"
                        "   Records with errors: {e}\n   Records with missing/invalid dates: {b}\n   Duration: {t}",
                  "ka": "ჯამი:\n   წყაროს ჩანაწერი ნაპოვნია: {f}\n   დუბლიკატი გამოტოვებულია: {u}\n"
                        "   ჩაიწერა: {i}\n   შეცდომიანი ჩანაწერი: {e}\n   ცარიელი/არასწორი თარიღით: {b}\n"
                        "   ხანგრძლივობა: {t}"},
    "sum_backup": {"en": "Backup of the destination: {p}", "ka": "მიმღების სარეზერვო ასლი: {p}"},
    "sum_blocked": {"en": "{k}: not transferred — {why}", "ka": "{k}: არ გადაიტანა — {why}"},
    "why_kind_mismatch": {"en": "geometry type mismatch", "ka": "გეომეტრიის ტიპი არ ემთხვევა"},
    "why_has_zm": {"en": "Z/M geometry is not supported", "ka": "Z/M გეომეტრია არ მხარდაიჭერება"},
    "why_crs_unknown": {"en": "coordinate systems differ and cannot be transformed reliably",
                        "ka": "კოორდინატთა სისტემები განსხვავდება და სანდოდ ვერ გარდაიქმნება"},
    "why_schema": {"en": "incompatible fields ({d})", "ka": "შეუთავსებელი ველები ({d})"},
    "why_no_key_fields": {"en": "werilis_no / date fields not found ({d})", "ka": "werilis_no / თარიღის ველები ვერ მოიძებნა ({d})"},
    "err_rec": {"en": "{k}: OBJECTID {o} ({n}) — {why}", "ka": "{k}: OBJECTID {o} ({n}) — {why}"},
    "why_no_number": {"en": "no werilis_no — duplicate check impossible, not inserted",
                      "ka": "werilis_no არ აქვს — დუბლიკატის შემოწმება შეუძლებელია, არ ჩაიწერა"},
    "amb": {"en": "{k}: {n} werilis_no value(s) occur several times inside the source selection; all were inserted "
                  "because the destination had none for {y}: {l}",
            "ka": "{k}: {n} werilis_no მნიშვნელობა განმეორდება წყაროს არჩევანის შიგნით; ყველა ჩაიწერა, რადგან "
                  "მიმღებში {y} წლით არ ჰქონდა: {l}"},
    "bad_dates": {"en": "{k}: {n} source record(s) with a missing/invalid date (not transferred, listed in the log)",
                  "ka": "{k}: {n} წყაროს ჩანაწერს თარიღი ცარიელი/არასწორი აქვს (არ გადაიტანა, ჩამოთვლილია ლოგში)"},
    "tip_check": {"en": "Open both databases (read-only), list their layers and check the destination can be written.",
                  "ka": "ორივე ბაზის გახსნა (მხოლოდ კითხვა), ფენების ჩამოთვლა და მიმღების ჩაწერისთვის მზადობის შემოწმება."},
    "tip_start": {"en": "Analyse first (nothing is written), then ask for confirmation, then write.",
                  "ka": "ჯერ ანალიზი (არაფერი იწერება), შემდეგ დადასტურება, ბოლოს ჩაწერა."},
}


def fmt_size(path):
    try:
        n = os.path.getsize(path)
    except OSError:
        return "?"
    return "{:.0f} MB".format(n / 1048576.0) if n >= 1048576 else "{:.0f} KB".format(n / 1024.0)


def fmt_duration(sec):
    sec = max(0.0, float(sec))
    return "{:.1f} s".format(sec) if sec < 60 else "{}m {:.0f}s".format(int(sec // 60), sec % 60)


class PgdbTransferTool(ToolFrame):
    tid = "db_transfer"
    CATALOG = DTR

    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    # ------------------------------------------------------------------ UI
    def build(self):
        pal = self.app.palette
        st = self._state()
        saved = self.app.get_tool_config(self.tid)
        self.busy = False
        self.msg_queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.mapping_vars = {}            # kind → (src_var, dst_var)
        self._infos = None                # (src_info, dst_info) ბოლო შემოწმებიდან
        self._log_path = None
        self._wrote = False
        self._pending_start = False

        ttk.Label(self, text=self.tr("heading"), font=(UI_FONT, 13, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"], wraplength=780,
                  justify="left").pack(anchor="w", pady=(0, 8))

        self.src_var = tk.StringVar(value=st.get("src") or saved.get("src") or "")
        self.dst_var = tk.StringVar(value=st.get("dst") or saved.get("dst") or "")
        self.src_shown = tk.StringVar()
        self.dst_shown = tk.StringVar()
        self._db_box("src_box", "src_lbl", self.src_var, self.src_shown, pal["accent"])
        ttk.Label(self, text=self.tr("flow"), foreground=pal["muted"],
                  font=(UI_FONT, 9, "bold")).pack(pady=2)
        self._db_box("dst_box", "dst_lbl", self.dst_var, self.dst_shown, "#d9822b")
        self.src_var.trace_add("write", lambda *_a: self._refresh_names())
        self.dst_var.trace_add("write", lambda *_a: self._refresh_names())
        self._refresh_names()

        opts = ttk.LabelFrame(self, text=self.tr("opts"))
        opts.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(opts)
        row.pack(fill="x", padx=8, pady=6)
        ttk.Label(row, text=self.tr("year")).pack(side="left")
        self.year_var = tk.StringVar(value=str(st.get("year") or saved.get("year") or DEFAULT_YEAR))
        add_tip(ttk.Spinbox(row, from_=1990, to=2100, width=6, textvariable=self.year_var),
                self.tr("tip_year")).pack(side="left", padx=(6, 24))
        self.backup_var = tk.BooleanVar(value=st.get("backup", saved.get("backup", True)))
        add_tip(ttk.Checkbutton(row, text=self.tr("backup"), variable=self.backup_var),
                self.tr("tip_backup")).pack(side="left")

        self.map_box = ttk.LabelFrame(self, text=self.tr("map_box"))
        self.map_box.pack(fill="x", pady=(8, 0))
        ttk.Label(self.map_box, text=self.tr("btn_check") + "…", foreground=pal["muted"]).pack(anchor="w", padx=8, pady=4)

        brow = ttk.Frame(self)
        brow.pack(fill="x", pady=(10, 4))
        self.check_btn = ttk.Button(brow, text=self.tr("btn_check"), command=self._check)
        self.check_btn.pack(side="left")
        add_tip(self.check_btn, self.tr("tip_check"))
        self.start_btn = ttk.Button(brow, text=self.tr("btn_start"), style="Accent.TButton", command=self._start)
        self.start_btn.pack(side="left", padx=(8, 0))
        add_tip(self.start_btn, self.tr("tip_start"))
        self.cancel_btn = ttk.Button(brow, text=self.tr("btn_cancel"), command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.log_btn = ttk.Button(brow, text=self.tr("btn_log"), command=self._open_log, state="disabled")
        self.log_btn.pack(side="right")

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", pady=(2, 2))
        self.status = tk.StringVar(value=self.tr("ready"))
        ttk.Label(self, textvariable=self.status, foreground=pal["muted"]).pack(anchor="w")

        res = ttk.LabelFrame(self, text=self.tr("res_box"))
        res.pack(fill="x", pady=(6, 0))
        cols = ("layer", "found", "dup", "ins", "err")
        self.tree = ttk.Treeview(res, columns=cols, show="headings", height=4)
        heads = {"layer": self.tr("t_layer"), "found": self.tr("t_found"), "dup": self.tr("t_dup"),
                 "ins": self.tr("t_plan") + " / " + self.tr("t_ins"), "err": self.tr("t_err")}
        widths = {"layer": 150, "found": 140, "dup": 220, "ins": 170, "err": 90}
        for c_ in cols:
            self.tree.heading(c_, text=heads[c_])
            self.tree.column(c_, width=widths[c_], anchor=("w" if c_ == "layer" else "center"))
        self.tree.pack(fill="x", padx=6, pady=6)
        self._reset_tree()

        sbox = ttk.LabelFrame(self, text=self.tr("sum_box"))
        sbox.pack(fill="both", expand=True, pady=(6, 0))
        self.summary = scrolledtext.ScrolledText(sbox, height=9, font=(MONO_FONT, 9), state="disabled")
        self.summary.pack(fill="both", expand=True, padx=6, pady=4)
        ebox = ttk.LabelFrame(self, text=self.tr("err_box"))
        ebox.pack(fill="both", expand=True, pady=(6, 0))
        self.errlog = scrolledtext.ScrolledText(ebox, height=8, font=(MONO_FONT, 9), state="disabled")
        self.errlog.pack(fill="both", expand=True, padx=6, pady=4)

        self.after(100, self._poll_queue)

    def _db_box(self, box_key, lbl_key, var, shown, color):
        box = ttk.LabelFrame(self, text=self.tr(box_key))
        box.pack(fill="x")
        row = ttk.Frame(box)
        row.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(row, text=self.tr(lbl_key)).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text=self.tr("browse"), width=3,
                   command=lambda: self._pick(var)).pack(side="left")
        ttk.Label(box, textvariable=shown, foreground=color,
                  font=(UI_FONT, 11, "bold")).pack(anchor="w", padx=8, pady=(0, 6))

    def save_state(self):
        st = self._state()
        st["src"], st["dst"] = self.src_var.get(), self.dst_var.get()
        st["year"], st["backup"] = self.year_var.get(), self.backup_var.get()

    def _pick(self, var):
        cur = var.get().strip()
        p = filedialog.askopenfilename(
            title=self.tr("pick_title"), initialdir=os.path.dirname(cur) if cur else None,
            filetypes=[("Personal Geodatabase / Access", "*.mdb"), ("All files", "*.*")])
        if p:
            var.set(os.path.normpath(p))
            self._infos = None

    def _refresh_names(self):
        for var, shown, key in ((self.src_var, self.src_shown, "src_shown"), (self.dst_var, self.dst_shown, "dst_shown")):
            p = var.get().strip()
            if p:
                shown.set(self.tr(key, name=os.path.basename(p), size=fmt_size(p)))
            else:
                shown.set(self.tr(key, name=self.tr("none_shown"), size="—"))
        self._infos = None

    # ---------------------------------------------------------- დამხმარეები
    def _msg(self, exc):
        """TransferError / სხვა → გასაგები ტექსტი."""
        if isinstance(exc, core.TransferError):
            key = "code_" + exc.code
            if key in DTR:
                return self.tr(key, d=(exc.detail or "")[:400])
            return str(exc)
        return str(exc)

    def _set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _append(self, widget, text):
        widget.configure(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _reset_tree(self):
        self.tree.delete(*self.tree.get_children())
        for k in core.KINDS:
            self.tree.insert("", "end", iid=k, values=(KIND_LABEL[k][self.app.lang], "—", "—", "—", "—"))
        self.tree.insert("", "end", iid="total", values=(self.tr("t_total"), "—", "—", "—", "—"))

    def _fill_tree(self, plan, written):
        for lp in plan.layers:
            ins = lp.inserted if written else lp.to_insert_count
            self.tree.item(lp.kind, values=(KIND_LABEL[lp.kind][self.app.lang], lp.found,
                                            lp.duplicates, ins, len(lp.errors)))
        t = plan.totals()
        self.tree.item("total", values=(self.tr("t_total"), t["found"], t["duplicates"],
                                        t["inserted"] if written else t["to_insert"], t["errors"]))

    def _set_busy(self, busy):
        self.busy = busy
        self.start_btn.configure(state="disabled" if busy else "normal",
                                 text=self.tr("btn_busy") if busy else self.tr("btn_start"))
        self.check_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    # ------------------------------------------------------------ ვალიდაცია
    def _validate_inputs(self, need_map=True):
        """(src, dst, year) ან None (შეტყობინება უკვე ნაჩვენებია)."""
        src, dst = self.src_var.get().strip(), self.dst_var.get().strip()
        if not src:
            messagebox.showwarning("GIS_BOX", self.tr("e_pick_src"))
            return None
        if not dst:
            messagebox.showwarning("GIS_BOX", self.tr("e_pick_dst"))
            return None
        for p in (src, dst):
            if not p.lower().endswith(".mdb"):
                messagebox.showwarning("GIS_BOX", self.tr("e_not_mdb", p=p))
                return None
            if not os.path.isfile(p):
                messagebox.showwarning("GIS_BOX", self.tr("e_missing", p=p))
                return None
        if core.same_file(src, dst):
            messagebox.showwarning("GIS_BOX", self.tr("e_same"))
            return None
        try:
            year = int(self.year_var.get())
            if not 1900 <= year <= 2200:
                raise ValueError
        except ValueError:
            messagebox.showwarning("GIS_BOX", self.tr("e_year"))
            return None
        return src, dst, year

    def _current_mapping(self):
        """მომხმარებლის არჩეული შესაბამისობა: {kind: (src, dst)} ან None (არასრული)."""
        m = {}
        for k in core.KINDS:
            sv, dv = self.mapping_vars.get(k, (None, None))
            s, d = (sv.get() if sv else ""), (dv.get() if dv else "")
            if s and d:
                m[k] = (s, d)
        return m

    # ------------------------------------------------------------- შემოწმება
    def _check(self):
        if self.busy:
            return
        v = self._validate_inputs()
        if not v:
            return
        src, dst, _y = v
        self._set_text(self.errlog, "")
        self._set_text(self.summary, "")
        self._set_busy(True)
        self.status.set(self.tr("btn_check") + "…")
        threading.Thread(target=self._check_worker, args=(src, dst), daemon=True).start()

    def _check_worker(self, src, dst):
        try:
            if not core.driver_available():
                import pyodbc  # noqa: F401  (ImportError → no_pyodbc)
                raise core.TransferError("no_driver", core.ODBC_DRIVER)
            si, di = core.inspect_db(src), core.inspect_db(dst)
            mapping, amb = core.match_layers(si, di)
            locked = None
            try:
                core.check_writable(dst)
            except core.TransferError as e:
                locked = e
            self.msg_queue.put(("checked", (si, di, mapping, amb, locked)))
        except ImportError as e:
            self.msg_queue.put(("error", core.TransferError("no_pyodbc", str(e))))
        except core.TransferError as e:
            self.msg_queue.put(("error", e))
        except Exception as e:                       # noqa: BLE001
            self.msg_queue.put(("error", core.friendly_error(e)))

    def _on_checked(self, payload):
        si, di, mapping, amb, locked = payload
        self._infos = (si, di)
        self._build_mapping(si, di, mapping, amb)
        lines = [self.tr("chk_ok")]
        for k in core.KINDS:
            sm = self.mapping_vars.get(k)
            if not sm:
                continue
            s, d = sm[0].get(), sm[1].get()
            if not (s and d):
                continue
            sl, dl = si.layers[s], di.layers[d]
            lines.append(self.tr("chk_layer", k=KIND_LABEL[k][self.app.lang], s=s, d=d, sn=sl.count, dn=dl.count))
            if sl.has_z or sl.has_m or dl.has_z or dl.has_m:
                lines.append(self.tr("chk_zm"))
            rel = core.crs_relation(sl.srtext, dl.srtext)
            if rel == "reproject":
                lines.append(self.tr("chk_crs_diff"))
            elif rel == "unknown":
                lines.append(self.tr("chk_crs_bad"))
            fp = core.plan_fields(sl.fields, dl.fields)
            if fp.unmatched_src:
                lines.append(self.tr("chk_fields", f=", ".join(fp.unmatched_src)))
            if not fp.ok:
                bits = ["{} ({})".format(f, dtl) for _c, f, dtl in fp.blockers] + fp.missing_required
                lines.append(self.tr("chk_schema", f="; ".join(bits)))
        lines.append(self.tr("chk_dst_locked") if locked else self.tr("chk_dst_writable"))
        self._set_text(self.summary, "\n".join(lines))
        self.status.set(self.tr("ready"))
        self._set_busy(False)

    def _build_mapping(self, si, di, mapping, amb):
        for w in self.map_box.winfo_children():
            w.destroy()
        self.mapping_vars = {}
        grid = ttk.Frame(self.map_box)
        grid.pack(fill="x", padx=8, pady=6)
        ttk.Label(grid, text=self.tr("map_src"), font=(UI_FONT, 9, "bold")).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(grid, text=self.tr("map_dst"), font=(UI_FONT, 9, "bold")).grid(row=0, column=3, sticky="w", padx=6)
        for r, k in enumerate(core.KINDS, start=1):
            s_names = [l.name for l in si.by_kind(k)]
            d_names = [l.name for l in di.by_kind(k)]
            sv, dv = tk.StringVar(), tk.StringVar()
            if k in mapping:
                sv.set(mapping[k][0])
                dv.set(mapping[k][1])
                note = self.tr("map_ok")
            else:
                note = self.tr("map_missing") if not (s_names and d_names) else self.tr("map_pick")
            self.mapping_vars[k] = (sv, dv)
            ttk.Label(grid, text=KIND_LABEL[k][self.app.lang]).grid(row=r, column=0, sticky="w", padx=6, pady=2)
            ttk.Combobox(grid, textvariable=sv, values=s_names, state="readonly", width=22).grid(row=r, column=1, padx=6)
            ttk.Label(grid, text="→").grid(row=r, column=2)
            ttk.Combobox(grid, textvariable=dv, values=d_names, state="readonly", width=22).grid(row=r, column=3, padx=6)
            ttk.Label(grid, text=note).grid(row=r, column=4, sticky="w", padx=6)

    # ----------------------------------------------------------- გადატანა
    def _start(self):
        if self.busy:
            return
        v = self._validate_inputs()
        if not v:
            return
        src, dst, year = v
        if self._infos is None:
            self._pending_start = True
            self._check()                      # ჯერ შევამოწმოთ/ავაგოთ შესაბამისობა, მერე გავაგრძელოთ
            return
        mapping = self._current_mapping()
        missing = [k for k in core.KINDS if k not in mapping]
        if missing:
            messagebox.showwarning("GIS_BOX", self.tr("e_map", k=", ".join(KIND_LABEL[k][self.app.lang] for k in missing)))
            return
        self._launch_analysis(src, dst, year, mapping)

    def _launch_analysis(self, src, dst, year, mapping):
        self.cancel_event.clear()
        self._set_text(self.summary, "")
        self._set_text(self.errlog, "")
        self._reset_tree()
        self._wrote = False
        self._log_path = core.default_log_path(dst, self.app_data_dir())
        self._set_busy(True)
        self.progress.configure(value=0)
        self.status.set(self.tr("st_analysing"))
        self._t0 = time.time()
        threading.Thread(target=self._analysis_worker, args=(src, dst, year, mapping), daemon=True).start()

    def app_data_dir(self):
        try:
            from tools.apppaths import data_dir
            return data_dir()
        except Exception:                          # noqa: BLE001
            return None

    def _make_log(self):
        def sink(line, level):
            self.msg_queue.put(("log", (line, level)))
        return core.TransferLog(self._log_path, sink=sink)

    def _analysis_worker(self, src, dst, year, mapping):
        log = self._make_log()
        try:
            log("Database Data Transfer — year {}".format(year))
            log("source:      {}".format(src))
            log("destination: {}".format(dst))
            plan = core.analyze(src, dst, mapping, year, log=log,
                                progress=lambda k, i, n: self.msg_queue.put(("progress", (k, i, n))),
                                cancel=self.cancel_event.is_set)
            self.msg_queue.put(("analysed", plan))
        except core.TransferError as e:
            log("{}: {}".format(e.code, e.detail), "ERROR")
            self.msg_queue.put(("error", e))
        except Exception as e:                     # noqa: BLE001
            log(str(e), "ERROR")
            self.msg_queue.put(("error", core.friendly_error(e)))
        finally:
            log.close()

    def _why(self, lp):
        code, detail = lp.blocked
        key = "why_" + code
        return self.tr(key, d=detail) if key in DTR else code

    def _notes(self, plan):
        notes = []
        for lp in plan.layers:
            k = KIND_LABEL[lp.kind][self.app.lang]
            if lp.unmatched_fields:
                notes.append(self.tr("chk_fields", f=", ".join(lp.unmatched_fields)).strip())
            if lp.reprojected:
                notes.append(k + ": " + self.tr("chk_crs_diff").strip())
            if lp.src_internal_dup_nos:
                notes.append(self.tr("amb", k=k, n=len(lp.src_internal_dup_nos), y=plan.year,
                                     l=", ".join(lp.src_internal_dup_nos[:15]) + (" …" if len(lp.src_internal_dup_nos) > 15 else "")))
            n_bad = len(lp.missing_dates) + len(lp.invalid_dates)
            if n_bad:
                notes.append(self.tr("bad_dates", k=k, n=n_bad))
        return notes

    def _on_analysed(self, plan):
        self._fill_tree(plan, written=False)
        todo = plan.totals()["to_insert"]
        for lp in plan.layers:
            self._report_layer_issues(lp, plan)
        text = self.tr("conf_head", y=plan.year, s=os.path.basename(plan.src_path), d=os.path.basename(plan.dst_path))
        for lp in plan.layers:
            k = KIND_LABEL[lp.kind][self.app.lang]
            if lp.blocked:
                text += self.tr("conf_blocked", k=k, why=self._why(lp)) + "\n"
            else:
                text += self.tr("conf_line", k=k, f=lp.found, u=lp.duplicates, n=lp.to_insert_count, e=len(lp.errors)) + "\n"
        notes = self._notes(plan)
        if notes:
            text += self.tr("conf_warn") + "\n" + "\n".join("• " + n for n in notes) + "\n"
        if todo == 0:
            self._finish(plan, written=False)
            self._set_busy(False)
            self.status.set(self.tr("ready"))
            messagebox.showinfo(self.tr("conf_title"), text + "\n" + self.tr("conf_nothing"))
            return
        text += self.tr("conf_backup") if self.backup_var.get() else self.tr("conf_nobackup")
        text += "\n" + self.tr("conf_ask", n=todo)
        if not messagebox.askyesno(self.tr("conf_title"), text):
            self._set_busy(False)
            self.status.set(self.tr("ready"))
            self._finish(plan, written=False, summary_only=True)
            return
        self.cancel_event.clear()
        self.status.set(self.tr("st_writing"))
        self.progress.configure(value=0)
        threading.Thread(target=self._write_worker, args=(plan, self.backup_var.get()), daemon=True).start()

    def _write_worker(self, plan, backup):
        log = core.TransferLog(self._log_path, sink=lambda line, lvl: self.msg_queue.put(("log", (line, lvl))))
        try:
            log("--- writing ---")
            core.execute(plan, log=log, backup=backup,
                         progress=lambda k, i, n: self.msg_queue.put(("progress", (k, i, n))),
                         cancel=self.cancel_event.is_set)
            self.msg_queue.put(("written", plan))
        except core.TransferError as e:
            log("{}: {}".format(e.code, e.detail), "ERROR")
            self.msg_queue.put(("error", e))
        except Exception as e:                     # noqa: BLE001
            log(str(e), "ERROR")
            self.msg_queue.put(("error", core.friendly_error(e)))
        finally:
            log.close()

    def _on_written(self, plan):
        self._wrote = True
        self._fill_tree(plan, written=True)
        self._finish(plan, written=True)
        self._set_busy(False)
        n = plan.totals()["inserted"]
        self.status.set(self.tr("st_done", n=n))
        self._infos = None                        # ბაზები შეიცვალა — შესაბამისობა/რიცხვები ხელახლა
        messagebox.showinfo("GIS_BOX", self.tr("st_done", n=n))

    def _report_layer_issues(self, lp, plan):
        """შეცდომების/გაფრთხილებების არეში: ჩანაწერები, რომლებიც ვერ გადავა."""
        k = KIND_LABEL[lp.kind][self.app.lang]
        if lp.blocked:
            self._append(self.errlog, self.tr("sum_blocked", k=k, why=self._why(lp)))
        for oid, no, why in lp.errors:
            reason = self.tr("why_no_number") if why == "no_number" else why
            self._append(self.errlog, self.tr("err_rec", k=k, o=oid, n=no, why=reason))
        for oid, no in lp.missing_dates:
            self._append(self.errlog, "{}: OBJECTID {} ({}) — {}".format(k, oid, no, "NULL date"))
        for oid, no, dt in lp.invalid_dates:
            self._append(self.errlog, "{}: OBJECTID {} ({}) — invalid date {}".format(k, oid, no, dt))

    def _finish(self, plan, written, summary_only=False):
        t = plan.totals()
        lines = [self.tr("sum_title"), "=" * 44]
        for lp in plan.layers:
            k = KIND_LABEL[lp.kind][self.app.lang]
            if lp.blocked:
                lines.append(self.tr("sum_blocked", k=k, why=self._why(lp)))
                continue
            lines.append(self.tr("sum_layer", k=k, f=lp.found, y=plan.year, u=lp.duplicates,
                                 i=(lp.inserted if written else 0), e=len(lp.errors)))
        lines.append("-" * 44)
        lines.append(self.tr("sum_total", f=t["found"], u=t["duplicates"], i=(t["inserted"] if written else 0),
                             e=t["errors"], b=t["bad_dates"], t=fmt_duration(time.time() - plan.started)))
        if getattr(plan, "backup_path", None):
            lines.append(self.tr("sum_backup", p=plan.backup_path))
        if self._log_path:
            lines.append(self.tr("log_path", p=self._log_path))
            self.log_btn.configure(state="normal")
        self._set_text(self.summary, "\n".join(lines))
        if written:
            self.app.log("— " + self.tr("st_done", n=t["inserted"]))
        self.app.set_tool_config(self.tid, {"src": self.src_var.get().strip(), "dst": self.dst_var.get().strip(),
                                            "year": self.year_var.get().strip(), "backup": bool(self.backup_var.get())})

    def _cancel(self):
        if self.busy:
            self.cancel_event.set()
            self.cancel_btn.configure(state="disabled")

    def _open_log(self):
        if self._log_path and os.path.isfile(self._log_path):
            try:
                open_path(self._log_path)
            except Exception as e:                   # noqa: BLE001
                messagebox.showerror("GIS_BOX", str(e))

    # --------------------------------------------------------------- queue
    def _poll_queue(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    line, level = payload
                    if level in ("WARN", "ERROR"):
                        self._append(self.errlog, line)
                elif kind == "progress":
                    k, i, n = payload
                    self.progress.configure(maximum=max(1, n), value=i)
                    self.status.set(self.tr("st_progress", k=KIND_LABEL[k][self.app.lang], i=i, n=n))
                elif kind == "checked":
                    self._on_checked(payload)
                    if getattr(self, "_pending_start", False):
                        self._pending_start = False
                        self._start()
                elif kind == "analysed":
                    self._on_analysed(payload)
                elif kind == "written":
                    self._on_written(payload)
                elif kind == "error":
                    self._pending_start = False
                    self._set_busy(False)
                    cancelled = isinstance(payload, core.TransferError) and payload.code == "cancelled"
                    self.status.set(self.tr("st_cancelled") if cancelled else self.tr("st_error"))
                    self.progress.configure(value=0)
                    if self._log_path and os.path.isfile(self._log_path):
                        self.log_btn.configure(state="normal")
                    if cancelled:
                        self._append(self.errlog, self.tr("code_cancelled"))
                    else:
                        self._append(self.errlog, self._msg(payload))
                    (messagebox.showinfo if cancelled else messagebox.showerror)(
                        "GIS_BOX" if cancelled else self.tr("st_error"), self._msg(payload))
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)
