# -*- coding: utf-8 -*-
"""დოკუმენტებში ძებნა — Word/PDF ფაილებში სიტყვის ან ფრაზის პოვნა.

მიეთითება საქაღალდე; ხელსაწყო ერთხელ კითხულობს ყველა დოკუმენტს (.docx, .pdf,
.txt, ძველი .doc/.rtf — Word-ის დახმარებით) და ტექსტს ინახავს ლოკალურ SQLite
ქეშში. შემდეგ ძებნა მყისიერია: მარცხნივ ჩნდება ფაილების სია დამთხვევების
რაოდენობით, მარჯვნივ კი — ყველა ნაპოვნი ადგილი კონტექსტით, ნაპოვნი სიტყვები
ყვითლად მონიშნული და გვერდის/პარაგრაფის ნომრით.

ძებნა ქვესტრიქონულია — „ნაკვეთ“ იპოვის „ნაკვეთის“-საც და „ნაკვეთებში“-საც;
ფრაზაში სიტყვებს შორის ხაზის გადატანა დაიშვება, ანუ PDF-ში ორ ხაზად გატეხილი
„ნაკვეთის საზღვარი“ მაინც მოიძებნება.

სუფთა ლოგიკა ``doc_search_core``-შია (tkinter-ის გარეშე, ტესტირებადი); აქ
მხოლოდ UI-ა. ინდექსის ბაზა და საძიებო საქაღალდის გზა მომხმარებლის ლოკალურ
პარამეტრებში ინახება — რეპოში არ ხვდება.
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
from tools.translit import lat_to_geo
from tools.doc_search_core import (
    MODE_ALL, MODE_ANY, MODE_PHRASE,
    SORT_MATCHES, SORT_DATE_DESC, SORT_DATE_ASC, SORT_NAME,
    index_folder, index_stats, search, sort_results, parse_category_rules,
)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(APP_DIR, "doc_search_index.db")
CATEGORIES_FILE = os.path.join(APP_DIR, "doc_categories.txt")

# ნაგულისხმევი კატეგორიები — ლოკალური doc_categories.txt-ში (Notepad-ით რედაქტ.).
# ფორმატი: „კატეგორია = საკვანძო სიტყვა 1, საკვანძო სიტყვა 2“.
DEFAULT_CATEGORIES = (
    "# GIS_BOX — დოკუმენტების კატეგორიები / document categories\n"
    "# ფორმატი:  კატეგორია = საკვანძო სიტყვა 1, საკვანძო სიტყვა 2\n"
    "# ძებნისას დოკუმენტი პირველ დამთხვეულ კატეგორიას მიეკუთვნება (ტექსტში ეძებს).\n"
    "# ეს ფაილი ლოკალურია — რედაქტირდება Notepad-ით, GitHub-ზე არ იტვირთება.\n"
    "\n"
    "ენერგო-პრო = ენერგო-პრო, ენერგოპრო, energo-pro\n"
    "ეკონომიკა = ეკონომიკის სამინისტრო, ეკონომიკისა და მდგრადი განვითარების\n"
    "სახელმწიფო ქონება = სახელმწიფო ქონების, ქონების ეროვნული სააგენტო\n"
)


# ---- თარგმანები ------------------------------------------------------------
DTR = {
    "heading":    {"en": "Search inside documents",
                   "ka": "ძებნა დოკუმენტებში"},
    "desc":       {"en": "Point to a folder with Word/PDF files, build the index "
                         "once, then search any word or phrase across all of them. "
                         "Matches are shown with their surrounding text and page "
                         "number.",
                   "ka": "მიუთითე საქაღალდე Word/PDF ფაილებით, ერთხელ ააგე ინდექსი "
                         "და შემდეგ მოძებნე ნებისმიერი სიტყვა ან ფრაზა ყველა მათგანში. "
                         "დამთხვევები ჩანს გარშემო ტექსტთან და გვერდის ნომერთან ერთად."},
    "folder":     {"en": "Folder:", "ka": "საქაღალდე:"},
    "recursive":  {"en": "Include subfolders", "ka": "ქვესაქაღალდეებიც"},
    "btn_index":  {"en": "Build index", "ka": "ინდექსის აგება"},
    "btn_index_busy": {"en": "Indexing…", "ka": "მიმდინარეობს…"},
    "btn_reindex": {"en": "↻ Rebuild", "ka": "↻ თავიდან"},
    "btn_cancel": {"en": "✖ Cancel", "ka": "✖ გაუქმება"},
    "cancelling": {"en": "Cancelling…", "ka": "უქმდება…"},
    "cancelled":  {"en": "Indexing cancelled.", "ka": "ინდექსაცია გაუქმდა."},

    "lbl_query":  {"en": "Search:", "ka": "ძებნა:"},
    "btn_search": {"en": "Search", "ka": "ძებნა"},
    "lat2geo":    {"en": "Type Latin → Georgian",
                   "ka": "ლათინურით ვწერ (→ ქართული)"},
    "preview_lbl": {"en": "Will search:", "ka": "მოიძებნება:"},
    "tip_lat2geo": {"en": "Georgian keyboard input shows “????” in this app. "
                          "Turn this on and type the query in Latin — it is "
                          "converted to Georgian below (nakveTi → ნაკვეთი). "
                          "Turn it off for English/Latin searches or to paste "
                          "Georgian directly.",
                    "ka": "ამ პროგრამაში ქართული კლავიატურა „????“-ს წერს. "
                          "ჩართე და აკრიფე მოთხოვნა ლათინურით — ქვემოთ ქართულად "
                          "გადაკეთდება (nakveTi → ნაკვეთი). გამორთე ინგლისური/"
                          "ლათინური ძებნისთვის ან ქართულის პირდაპირ ჩასასმელად."},
    "mode_phrase": {"en": "Phrase", "ka": "ფრაზა"},
    "mode_all":   {"en": "All words", "ka": "ყველა სიტყვა"},
    "mode_any":   {"en": "Any word", "ka": "რომელიმე"},

    "col_file":   {"en": "File", "ka": "ფაილი"},
    "col_date":   {"en": "Date", "ka": "თარიღი"},
    "col_hits":   {"en": "Matches", "ka": "დამთხვევა"},

    # სორტირება / კატეგორიზაცია
    "sort_lbl":   {"en": "Sort:", "ka": "დალაგება:"},
    "sort_matches": {"en": "Most matches", "ka": "მეტი დამთხვევა"},
    "sort_date_desc": {"en": "Date — newest first", "ka": "თარიღი — ახალი ზემოთ"},
    "sort_date_asc": {"en": "Date — oldest first", "ka": "თარიღი — ძველი ზემოთ"},
    "sort_name":  {"en": "File name", "ka": "ფაილის სახელი"},
    "group_cat":  {"en": "Group by category", "ka": "დაჯგუფება კატეგორიით"},
    "cat_edit":   {"en": "🗂 Categories", "ka": "🗂 კატეგორიები"},
    "uncategorized": {"en": "Other", "ka": "სხვა"},
    "tip_sort":   {"en": "Order the found files. “Newest first” uses the date "
                         "mentioned inside the document.",
                   "ka": "ნაპოვნი ფაილების დალაგება. „ახალი ზემოთ“ იყენებს "
                         "დოკუმენტში ნახსენებ თარიღს."},
    "tip_group":  {"en": "Group files by sender/organization (Energo-Pro together, "
                         "Economy together …), using the category rules.",
                   "ka": "ფაილების დაჯგუფება გამომგზავნის/ორგანიზაციის მიხედვით "
                         "(ენერგო-პრო ერთად, ეკონომიკა ერთად …), წესების მიხედვით."},
    "tip_cat_edit": {"en": "Edit the category rules (category = keywords). Applies "
                           "on the next search — no re-indexing needed.",
                     "ka": "კატეგორიის წესების რედაქტირება (კატეგორია = სიტყვები). "
                           "მოქმედებს შემდეგ ძებნაზე — ხელახლა ინდექსაცია არ სჭირდება."},
    "btn_open":   {"en": "Open file", "ka": "ფაილის გახსნა"},
    "btn_folder": {"en": "Open folder", "ka": "საქაღალდის გახსნა"},
    "btn_export": {"en": "Export .xlsx", "ka": "ექსპორტი .xlsx"},

    "page":       {"en": "p. {n}", "ka": "გვ. {n}"},
    "para":       {"en": "¶ {n}", "ka": "¶ {n}"},
    "more_hits":  {"en": "… and {n} more match(es) in this file — refine the query.",
                   "ka": "… კიდევ {n} დამთხვევა ამ ფაილში — დააზუსტე მოთხოვნა."},
    "pick_file":  {"en": "Pick a file on the left to see the matches.",
                   "ka": "აირჩიე ფაილი მარცხნივ, რომ ნაპოვნი ადგილები დაინახო."},

    # სტატუსები / შეტყობინებები
    "idx_start":  {"en": "Indexing {n} document(s)…",
                   "ka": "ინდექსირდება {n} დოკუმენტი…"},
    "idx_progress": {"en": "Indexed {i}/{n}", "ka": "დამუშავდა {i}/{n}"},
    "idx_done":   {"en": "Index ready — {new} new, {upd} updated, {cached} unchanged.",
                   "ka": "ინდექსი მზადაა — {new} ახალი, {upd} განახლდა, {cached} უცვლელი."},
    "idx_summary": {"en": "Index: {ok} searchable, {empty} without text, {err} failed.",
                    "ka": "ინდექსი: {ok} მოსაძებნი, {empty} ტექსტის გარეშე, {err} ვერ წაიკითხა."},
    "idx_none":   {"en": "No index yet — pick a folder and press “Build index”.",
                   "ka": "ინდექსი ჯერ არაა — აირჩიე საქაღალდე და დააჭირე „ინდექსის აგებას“."},
    "no_docs":    {"en": "No supported documents in the folder "
                         "(.docx, .pdf, .txt, .doc, .rtf).",
                   "ka": "საქაღალდეში მხარდაჭერილი დოკუმენტი არაა "
                         "(.docx, .pdf, .txt, .doc, .rtf)."},
    "warn_folder": {"en": "Specify a valid folder.", "ka": "მიუთითე არსებული საქაღალდე."},
    "warn_query": {"en": "Type something to search for.", "ka": "ჩაწერე საძიებო ტექსტი."},
    "found":      {"en": "Found in {f} file(s) — {n} match(es).",
                   "ka": "ნაპოვნია {f} ფაილში — {n} დამთხვევა."},
    "not_found":  {"en": "Nothing found for “{q}”.", "ka": "„{q}“ ვერ მოიძებნა."},
    "searching":  {"en": "Searching…", "ka": "ვეძებ…"},

    # დასკანერებული ფაილები
    "scanned_hdr": {"en": "— {n} file(s) have no text layer (probably scanned) —",
                    "ka": "— {n} ფაილს ტექსტური ფენა არ აქვს (სავარაუდოდ დასკანერებულია) —"},
    "scanned_hint": {"en": "These cannot be searched without OCR.",
                     "ka": "ასეთებში OCR-ის გარეშე ძებნა შეუძლებელია."},
    "err_hdr":    {"en": "— {n} file(s) could not be read —",
                   "ka": "— {n} ფაილი ვერ წაიკითხა —"},

    # ექსპორტი
    "exp_none":   {"en": "Nothing to export — run a search first.",
                   "ka": "საექსპორტო არაფერია — ჯერ მოძებნე."},
    "exp_title":  {"en": "Save results", "ka": "შედეგების შენახვა"},
    "exp_done":   {"en": "Results saved: {path}", "ka": "შედეგები შენახულია: {path}"},
    "exp_dep":    {"en": "Export needs the openpyxl package.",
                   "ka": "ექსპორტს openpyxl პაკეტი სჭირდება."},
    "exp_cols":   {"en": ("Category", "Date", "File", "Location",
                          "Matches in file", "Context", "Path"),
                   "ka": ("კატეგორია", "თარიღი", "ფაილი", "ადგილი",
                          "დამთხვევა ფაილში", "კონტექსტი", "გზა")},

    # tooltip-ები
    "tip_browse": {"en": "Pick the folder that holds the documents.",
                   "ka": "აირჩიე საქაღალდე დოკუმენტებით."},
    "tip_recursive": {"en": "Also read documents in subfolders.",
                      "ka": "ქვესაქაღალდეების დოკუმენტებიც წაიკითხოს."},
    "tip_index":  {"en": "Read every document once and cache its text. "
                         "Unchanged files are skipped next time.",
                   "ka": "ერთხელ წაიკითხავს ყველა დოკუმენტს და ტექსტს დაიმახსოვრებს. "
                         "შემდეგ ჯერზე უცვლელი ფაილები გამოტოვდება."},
    "tip_reindex": {"en": "Ignore the cache and re-read every document.",
                    "ka": "ქეშის იგნორირება — ყველა დოკუმენტი თავიდან წაიკითხოს."},
    "tip_cancel": {"en": "Stop the running indexing.", "ka": "მიმდინარე ინდექსაციის შეჩერება."},
    "tip_query":  {"en": "Georgian search is substring-based: “ნაკვეთ” also finds "
                         "“ნაკვეთის”. In phrase mode a line break between the words "
                         "is fine.",
                   "ka": "ძებნა ქვესტრიქონულია: „ნაკვეთ“ იპოვის „ნაკვეთის“-საც. "
                         "ფრაზის რეჟიმში სიტყვებს შორის ხაზის გადატანა დაიშვება."},
    "tip_search": {"en": "Search the index (instant).", "ka": "ძებნა ინდექსში (მყისიერი)."},
    "tip_open":   {"en": "Open the selected file in its default program.",
                   "ka": "არჩეული ფაილის გახსნა ჩვეულ პროგრამაში."},
    "tip_folder": {"en": "Open the folder that holds the selected file.",
                   "ka": "არჩეული ფაილის საქაღალდის გახსნა."},
    "tip_export": {"en": "Save all matches to a spreadsheet.",
                   "ka": "ყველა დამთხვევის შენახვა ცხრილში."},
}


class DocSearchTool(ToolFrame):
    tid = "doc_search"
    CATALOG = DTR          # tr() მოდის ToolFrame-იდან (საერთო lookup)

    # ---- მდგომარეობა ----
    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    # ---- UI ----
    def build(self):
        pal = self.app.palette
        st = self._state()
        saved = self.app.get_tool_config(self.tid)

        self.db_path = DEFAULT_DB
        self.results = []
        self.indexing = False
        self.msg_queue = queue.Queue()
        self._cancel_event = threading.Event()

        ttk.Label(self, text=self.tr("heading"),
                  font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"],
                  wraplength=760, justify="left").pack(anchor="w", pady=(0, 12))

        # --- საქაღალდე + ინდექსი ---
        row = ttk.Frame(self)
        row.pack(fill="x")
        ttk.Label(row, text=self.tr("folder")).pack(side="left")
        self.folder_var = tk.StringVar(
            value=st.get("folder") or saved.get("folder") or "")
        ttk.Entry(row, textvariable=self.folder_var).pack(
            side="left", fill="x", expand=True, padx=(6, 6))
        add_tip(ttk.Button(row, text=self.tr("browse"), command=self._pick),
                self.tr("tip_browse")).pack(side="left")

        opt = ttk.Frame(self)
        opt.pack(fill="x", pady=(8, 4))
        self.recursive_var = tk.BooleanVar(value=st.get("recursive", True))
        add_tip(ttk.Checkbutton(opt, text=self.tr("recursive"),
                                variable=self.recursive_var),
                self.tr("tip_recursive")).pack(side="left")
        self.index_btn = ttk.Button(opt, text=self.tr("btn_index"),
                                    command=self._start_index)
        self.index_btn.pack(side="left", padx=(16, 4))
        add_tip(self.index_btn, self.tr("tip_index"))
        self.reindex_btn = ttk.Button(opt, text=self.tr("btn_reindex"),
                                      command=lambda: self._start_index(force=True))
        self.reindex_btn.pack(side="left", padx=(0, 4))
        add_tip(self.reindex_btn, self.tr("tip_reindex"))
        self.cancel_btn = ttk.Button(opt, text=self.tr("btn_cancel"),
                                     command=self._cancel_index, state="disabled")
        self.cancel_btn.pack(side="left")
        add_tip(self.cancel_btn, self.tr("tip_cancel"))

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", pady=(2, 2))

        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status,
                  foreground=pal["muted"]).pack(anchor="w", pady=(0, 8))

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(0, 8))

        # --- საძიებო ზოლი ---
        qrow = ttk.Frame(self)
        qrow.pack(fill="x")
        ttk.Label(qrow, text=self.tr("lbl_query")).pack(side="left")
        self.query_var = tk.StringVar(value=st.get("query", ""))
        entry = ttk.Entry(qrow, textvariable=self.query_var)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        entry.bind("<Return>", lambda _e: self._search())
        add_tip(entry, self.tr("tip_query"))
        add_tip(ttk.Button(qrow, text=self.tr("btn_search"), command=self._search),
                self.tr("tip_search")).pack(side="left")

        # --- ლათინურით შეყვანა → ქართული (კლავიატურის „????“-ის შემოვლა) ---
        # ქართული კლავიატურა ამ პროგრამის ველებში „?“-ებს წერს (Tk-ის Windows
        # WM_CHAR-ის ხარვეზი). ჩართვისას ლათინურ აკრეფას Python-ის მხარეს
        # ვაქცევთ ქართულად — ეს გვერდს უვლის დაზიანებულ კლავიატურის გზას.
        crow = ttk.Frame(self)
        crow.pack(fill="x", pady=(4, 0))
        self.lat2geo_var = tk.BooleanVar(value=st.get("lat2geo", True))
        add_tip(ttk.Checkbutton(crow, text=self.tr("lat2geo"),
                                variable=self.lat2geo_var,
                                command=self._update_preview),
                self.tr("tip_lat2geo")).pack(side="left")
        self.preview_lbl = ttk.Label(crow, text="", foreground=pal["muted"],
                                     font=("Sylfaen", 11))
        self.preview_lbl.pack(side="left", padx=(14, 0))
        self.query_var.trace_add("write", lambda *_a: self._update_preview())
        self._update_preview()

        mrow = ttk.Frame(self)
        mrow.pack(fill="x", pady=(6, 4))
        self.mode_var = tk.StringVar(value=st.get("mode", MODE_PHRASE))
        for value, key in ((MODE_PHRASE, "mode_phrase"),
                           (MODE_ALL, "mode_all"),
                           (MODE_ANY, "mode_any")):
            ttk.Radiobutton(mrow, text=self.tr(key), value=value,
                            variable=self.mode_var).pack(side="left", padx=(0, 14))

        # --- დალაგება + კატეგორიზაცია ---
        srow = ttk.Frame(self)
        srow.pack(fill="x", pady=(0, 8))
        ttk.Label(srow, text=self.tr("sort_lbl")).pack(side="left")
        # label ↔ mode რუკა (Combobox-ს ლეიბლი გამოაქვს, ვინახავთ mode-ს)
        self._sort_modes = [
            (SORT_DATE_DESC, self.tr("sort_date_desc")),
            (SORT_MATCHES, self.tr("sort_matches")),
            (SORT_DATE_ASC, self.tr("sort_date_asc")),
            (SORT_NAME, self.tr("sort_name")),
        ]
        self._sort_by_label = {lbl: mode for mode, lbl in self._sort_modes}
        saved_mode = st.get("sort", SORT_DATE_DESC)
        saved_label = next((lbl for mode, lbl in self._sort_modes
                            if mode == saved_mode), self._sort_modes[0][1])
        self.sort_label_var = tk.StringVar(value=saved_label)
        sort_combo = ttk.Combobox(srow, textvariable=self.sort_label_var,
                                  state="readonly", width=20,
                                  values=[lbl for _m, lbl in self._sort_modes])
        sort_combo.pack(side="left", padx=(6, 14))
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_results())
        add_tip(sort_combo, self.tr("tip_sort"))

        self.group_var = tk.BooleanVar(value=st.get("group", True))
        add_tip(ttk.Checkbutton(srow, text=self.tr("group_cat"),
                                variable=self.group_var,
                                command=self._render_results),
                self.tr("tip_group")).pack(side="left")
        add_tip(ttk.Button(srow, text=self.tr("cat_edit"),
                           command=self._open_categories_file),
                self.tr("tip_cat_edit")).pack(side="left", padx=(14, 0))

        # --- ქვედა ღილაკები ---
        # panes-ზე ადრე და side="bottom"-ით: გაფართოებადი პანელი მთელ თავისუფალ
        # სიმაღლეს იტაცებს, ამიტომ ღილაკების ადგილი წინასწარ უნდა დაჯავშნოს.
        brow = ttk.Frame(self)
        brow.pack(side="bottom", fill="x", pady=(8, 0))
        add_tip(ttk.Button(brow, text=self.tr("btn_open"), command=self._open_file),
                self.tr("tip_open")).pack(side="left")
        add_tip(ttk.Button(brow, text=self.tr("btn_folder"),
                           command=self._open_folder),
                self.tr("tip_folder")).pack(side="left", padx=(6, 0))
        add_tip(ttk.Button(brow, text=self.tr("btn_export"), command=self._export),
                self.tr("tip_export")).pack(side="left", padx=(6, 0))

        # --- შედეგები: მარცხნივ ფაილები, მარჯვნივ ამონარიდები ---
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        self.tree = ttk.Treeview(left, columns=("date", "hits"),
                                 show="tree headings", selectmode="browse")
        self.tree.heading("#0", text=self.tr("col_file"))
        self.tree.heading("date", text=self.tr("col_date"))
        self.tree.heading("hits", text=self.tr("col_hits"))
        self.tree.column("#0", width=220, stretch=True)
        self.tree.column("date", width=88, anchor="center", stretch=False)
        self.tree.column("hits", width=72, anchor="e", stretch=False)
        self.tree.tag_configure("cat", font=("Segoe UI", 10, "bold"))
        tsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _e: self._open_file())
        panes.add(left, weight=1)

        right = ttk.Frame(panes)
        self.preview = tk.Text(right, wrap="word", state="disabled",
                               font=("Segoe UI", 10), relief="flat", borderwidth=0,
                               padx=8, pady=6,
                               bg=pal["log_bg"], fg=pal["log_fg"])
        psb = ttk.Scrollbar(right, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=psb.set)
        self.preview.pack(side="left", fill="both", expand=True)
        psb.pack(side="right", fill="y")
        panes.add(right, weight=2)

        self.preview.tag_configure("hl", background="#ffe680", foreground="#1a1a1a")
        self.preview.tag_configure("loc", foreground=pal["muted"],
                                   font=("Segoe UI", 9))
        self.preview.tag_configure("head", font=("Segoe UI", 11, "bold"),
                                   spacing3=6)
        self.preview.tag_configure("note", foreground=pal["muted"],
                                   font=("Segoe UI", 9, "italic"))

        self._show_note(self.tr("pick_file"))
        self._refresh_stats()
        self.after(100, self._poll_queue)

    def save_state(self):
        st = self._state()
        st["folder"] = self.folder_var.get()
        st["recursive"] = self.recursive_var.get()
        st["query"] = self.query_var.get()
        st["mode"] = self.mode_var.get()
        st["lat2geo"] = self.lat2geo_var.get()
        st["sort"] = self._current_sort_mode()
        st["group"] = self.group_var.get()

    # ---- ლათინური→ქართული საძიებო ტექსტი ----
    def _effective_query(self):
        """ფაქტობრივი მოთხოვნა: ჩართული „ლათ→ქარ“-ისას ლათინურ აკრეფას
        ქართულად ვაქცევთ (Python-ის მხარეს, კლავიატურის ხარვეზის გვერდის ავლით)."""
        raw = self.query_var.get().strip()
        return lat_to_geo(raw) if self.lat2geo_var.get() else raw

    def _update_preview(self):
        """ცოცხალი გადახედვა — რა მოიძებნება (ქართული Tk-ში სწორად ჩანს)."""
        if not hasattr(self, "preview_lbl") or not self.preview_lbl.winfo_exists():
            return
        if self.lat2geo_var.get():
            q = self._effective_query()
            self.preview_lbl.configure(
                text=(self.tr("preview_lbl") + " " + q) if q else "")
        else:
            self.preview_lbl.configure(text="")

    # ---- საქაღალდე ----
    def _pick(self):
        d = filedialog.askdirectory(title=self.tr("folder"),
                                    initialdir=self.folder_var.get() or None)
        if d:
            self.folder_var.set(os.path.normpath(d))
            self.app.set_tool_config(self.tid, {"folder": os.path.normpath(d)})

    def _refresh_stats(self):
        """ინდექსის მიმდინარე მდგომარეობა სტატუსის ზოლში."""
        stats = index_stats(self.db_path)
        if stats["total"] == 0:
            self.status.set(self.tr("idx_none"))
        else:
            self.status.set(self.tr("idx_summary", ok=stats["ok"],
                                    empty=stats["empty"], err=stats["error"]))

    # ---- ინდექსაცია (ფონურ ნაკადში) ----
    def _start_index(self, force=False):
        if self.indexing:
            return
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("GIS_BOX", self.tr("warn_folder"))
            return
        self.app.set_tool_config(self.tid, {"folder": os.path.normpath(folder)})

        self.indexing = True
        self._cancel_event.clear()
        self.index_btn.configure(state="disabled", text=self.tr("btn_index_busy"))
        self.reindex_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=100)

        t = threading.Thread(
            target=index_folder,
            args=(folder, self.recursive_var.get(), self.db_path,
                  lambda m: self.msg_queue.put(("log", m)),
                  lambda r: self.msg_queue.put(("done", r)),
                  self.tr,
                  lambda i, n: self.msg_queue.put(("progress", (i, n))),
                  self._cancel_event.is_set,
                  force),
            daemon=True,
        )
        t.start()

    def _cancel_index(self):
        if self.indexing:
            self._cancel_event.set()
            self.cancel_btn.configure(state="disabled")
            self.status.set(self.tr("cancelling"))

    def _poll_queue(self):
        # frame შესაძლოა განადგურდეს ენის/თემის ცვლილებისას — მაშინ ვჩერდებით.
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.app.log(payload)
                elif kind == "progress":
                    i, n = payload
                    self.progress.configure(maximum=n, value=i)
                    self.status.set(self.tr("idx_progress", i=i, n=n))
                elif kind == "done":
                    self._on_index_done(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_index_done(self, result):
        self.indexing = False
        self.index_btn.configure(state="normal", text=self.tr("btn_index"))
        self.reindex_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

        if result.get("cancelled"):
            self.progress.configure(value=0)
            self.status.set(self.tr("cancelled"))
            self.app.log(self.tr("cancelled"))
            return
        if result.get("error"):
            self.progress.configure(value=0)
            messagebox.showerror(self.tr("err"), result["error"])
            self.status.set(result["error"].splitlines()[0])
            return

        # ტექსტის გარეშე დარჩენილი ფაილები — ლოგში ცალკე სიად
        if result.get("empty_files"):
            self.app.log(self.tr("scanned_hdr", n=len(result["empty_files"])))
            self.app.log("  " + self.tr("scanned_hint"))
            for p in result["empty_files"]:
                self.app.log("  • " + os.path.basename(p))
        if result.get("error_files"):
            self.app.log(self.tr("err_hdr", n=len(result["error_files"])))
            for p, note in result["error_files"]:
                self.app.log("  • {} — {}".format(os.path.basename(p), note))

        self._refresh_stats()
        if self.query_var.get().strip():
            self._search()

    # ---- ძებნა ----
    def _search(self):
        query = self._effective_query()
        if not query:
            messagebox.showwarning("GIS_BOX", self.tr("warn_query"))
            return
        stats = index_stats(self.db_path)
        if stats["total"] == 0:
            messagebox.showinfo("GIS_BOX", self.tr("idx_none"))
            return

        self.status.set(self.tr("searching"))
        self.update_idletasks()
        rules = self._load_category_rules()
        self.results = search(self.db_path, query, self.mode_var.get(),
                              category_rules=rules)
        # თითო შედეგს ვანიჭებთ სტაბილურ ინდექსს (iid → self.results-ის პოზიცია),
        # რომ დახარისხების/დაჯგუფების მიუხედავად არჩევა სწორად მუშაობდეს.
        for i, r in enumerate(self.results):
            r["_idx"] = i

        self._render_results()

        total = sum(r["count"] for r in self.results)
        if self.results:
            self.status.set(self.tr("found", f=len(self.results), n=total))
        else:
            self.status.set(self.tr("not_found", q=query))
            self._show_note(self.tr("not_found", q=query))
        self.app.log(self.status.get())

    # ---- სორტირება / კატეგორიზაცია ----
    def _current_sort_mode(self):
        return self._sort_by_label.get(self.sort_label_var.get(), SORT_MATCHES)

    def _fmt_date(self, iso):
        """'YYYY-MM-DD' → 'DD.MM.YYYY' (ცარიელი თუ არაა)."""
        if not iso:
            return ""
        y, m, d = iso.split("-")
        return "{}.{}.{}".format(d, m, y)

    def _render_results(self):
        """შედეგების ხის აგება მიმდინარე დახარისხებით/დაჯგუფებით (ხელახლა ძებნის
        გარეშე). ფაილის iid = მისი პოზიცია self.results-ში (_idx)."""
        self.tree.delete(*self.tree.get_children())
        if not getattr(self, "results", None):
            return
        ordered = sort_results(self.results, self._current_sort_mode())

        def add_file(parent, r):
            self.tree.insert(parent, "end", iid=str(r["_idx"]), text=r["name"],
                             values=(self._fmt_date(r.get("doc_date")), r["count"]))

        first_iid = str(ordered[0]["_idx"]) if ordered else None
        if self.group_var.get():
            groups = {}
            order = []
            for r in ordered:
                cat = r.get("category") or self.tr("uncategorized")
                if cat not in groups:
                    groups[cat] = []
                    order.append(cat)
            for r in ordered:
                groups[r.get("category") or self.tr("uncategorized")].append(r)
            for cat in order:
                items = groups[cat]
                pid = "cat::" + cat
                self.tree.insert("", "end", iid=pid, open=True, tags=("cat",),
                                 text="{}  ({})".format(cat, len(items)),
                                 values=("", ""))
                for r in items:
                    add_file(pid, r)
        else:
            for r in ordered:
                add_file("", r)

        if first_iid is not None:
            self.tree.selection_set(first_iid)
            self.tree.focus(first_iid)
            self.tree.see(first_iid)

    # ---- კატეგორიის წესები (ლოკალური, რედაქტირებადი ფაილი) ----
    def _ensure_categories_file(self):
        if not os.path.exists(CATEGORIES_FILE):
            try:
                with open(CATEGORIES_FILE, "w", encoding="utf-8") as f:
                    f.write(DEFAULT_CATEGORIES)
            except OSError:
                pass

    def _load_category_rules(self):
        """doc_categories.txt-ის წაკითხვა → წესები. თუ ფაილი არაა — ნაგულისხმევი."""
        self._ensure_categories_file()
        for enc in ("utf-8-sig", "utf-8", "cp1251", "cp1252"):
            try:
                with open(CATEGORIES_FILE, "r", encoding=enc) as f:
                    return parse_category_rules(f.read())
            except (UnicodeDecodeError, OSError):
                continue
        return parse_category_rules(DEFAULT_CATEGORIES)

    def _open_categories_file(self):
        """კატეგორიების ფაილის გახსნა რედაქტირებისთვის (Notepad და ა.შ.)."""
        self._ensure_categories_file()
        try:
            if sys.platform == "win32":
                os.startfile(CATEGORIES_FILE)             # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", CATEGORIES_FILE])
            else:
                subprocess.Popen(["xdg-open", CATEGORIES_FILE])
        except Exception as e:                            # noqa: BLE001
            messagebox.showerror(self.tr("err"), str(e))

    # ---- preview ----
    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return self.results[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _show_note(self, text):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("end", text, "note")
        self.preview.configure(state="disabled")

    def _label(self, result, hit):
        """ადგილის წარწერა — გვერდი (PDF) ან პარაგრაფი (Word)."""
        n = hit.get("label")
        if n is None:
            return ""
        return self.tr("page" if result["unit"] == "page" else "para", n=n)

    def _on_select(self, _evt=None):
        r = self._selected()
        if r is None:
            return
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("end", r["name"] + "\n", "head")

        for hit in r["hits"]:
            label = self._label(r, hit)
            if label:
                self.preview.insert("end", label + "\n", "loc")
            start_index = self.preview.index("end-1c")
            self.preview.insert("end", hit["snippet"] + "\n\n")
            # მონიშვნა — ამონარიდის შიგნით მოცემული კოორდინატებით
            for s, e in hit["hl"]:
                self.preview.tag_add(
                    "hl",
                    "{}+{}c".format(start_index, s),
                    "{}+{}c".format(start_index, e))

        if r["truncated"]:
            self.preview.insert(
                "end", self.tr("more_hits", n=r["count"] - len(r["hits"])), "note")
        self.preview.configure(state="disabled")
        self.preview.see("1.0")

    # ---- გახსნა ----
    def _open_path(self, path):
        """ფაილის/საქაღალდის გახსნა ოპერაციული სისტემის ჩვეული პროგრამით."""
        try:
            if sys.platform == "win32":
                os.startfile(path)                        # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror(self.tr("err"), str(e))

    def _open_file(self):
        r = self._selected()
        if r:
            self._open_path(r["path"])

    def _open_folder(self):
        r = self._selected()
        if r:
            self._open_path(os.path.dirname(r["path"]))

    # ---- ექსპორტი ----
    def _export(self):
        if not self.results:
            messagebox.showinfo("GIS_BOX", self.tr("exp_none"))
            return
        try:
            from openpyxl import Workbook
        except ImportError:
            messagebox.showerror(self.tr("err"), self.tr("exp_dep"))
            return

        path = filedialog.asksaveasfilename(
            title=self.tr("exp_title"), defaultextension=".xlsx",
            initialfile="doc_search.xlsx",
            filetypes=[("Excel", "*.xlsx")])
        if not path:
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "search"
        ws.append(list(self.tr("exp_cols")))
        # ექსპორტი მიმდინარე დახარისხებით (ისე, როგორც სიაშია)
        for r in sort_results(self.results, self._current_sort_mode()):
            cat = r.get("category") or self.tr("uncategorized")
            date = self._fmt_date(r.get("doc_date"))
            for hit in r["hits"]:
                ws.append([cat, date, r["name"], self._label(r, hit),
                           r["count"], hit["snippet"], r["path"]])
        for col, width in zip("ABCDEFG", (18, 12, 34, 10, 12, 90, 60)):
            ws.column_dimensions[col].width = width
        try:
            wb.save(path)
        except Exception as e:
            messagebox.showerror(self.tr("err"), str(e))
            return
        self.app.log(self.tr("exp_done", path=path))
        messagebox.showinfo("GIS_BOX", self.tr("exp_done", path=path))
