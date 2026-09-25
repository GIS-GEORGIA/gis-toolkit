# -*- coding: utf-8 -*-
"""ქართული სახელების მქონე ფაილების მასობრივი გადარქმევა ლათინურ ტრანსლიტერაციაზე.

მიეთითება საქაღალდე; ხელსაწყო პოულობს ყველა ფაილს, რომლის სახელშიც ქართული
ასოებია (მაგ. shapefile-ის ყველა თანმხლები: .shp/.shx/.dbf/.prj/.cpg/.sbn/
.sbx/.shp.xml და ა.შ.) და გადაარქმევს:
  • ქართული ასოები → ლათინური (მაგ. „საყრდენი“ → „sayrdeni“, ყ → y)
  • სფეისი → ქვედა ტირე „_“
  • გაფართოებები უცვლელი რჩება

„არსებული საყრდენი.shp“  →  „arsebuli_sayrdeni.shp“

გადარქმევა შეუქცევადია, ამიტომ ჯერ ჩნდება წინასწარი სია (Preview), შემდეგ —
დადასტურება. კონფლიქტები (ორი სახელი ერთსა და იმავე ლათინურ სახელს იძლევა, ან
სამიზნე უკვე არსებობს) გამოტოვდება და ცალკე მოინიშნება.
"""

import os
import re

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from tools.base import ToolFrame
from tools.platform_utils import UI_FONT, MONO_FONT
from tools.tooltip import add_tip
# სუფთა ლოგიკა ცალკე მოდულში (ტესტირებადი, tkinter-ის გარეშე)
from tools.translit import GEO2LAT, GEO_RANGE, transliterate, _sibling, feature_count


# ---- თარგმანები ------------------------------------------------------------
RTR = {
    "heading":   {"en": "Rename files → Latin",
                  "ka": "ფაილების გადარქმევა → ლათინური"},
    "desc":      {"en": "Point to a folder. Every file whose name contains "
                        "Georgian letters is renamed to Latin; spaces, commas and "
                        "any other symbol become “_”. The extension is kept. All "
                        "sidecar files are handled.",
                  "ka": "მიუთითე საქაღალდე. ყველა ფაილს, რომლის სახელშიც ქართული "
                        "ასოებია, გადაერქმევა ლათინურად; სფეისი, მძიმე და ნებისმიერი "
                        "სხვა სიმბოლო ხდება „_“. გაფართოება უცვლელი რჩება. ყველა "
                        "თანმხლები ფაილი მუშავდება."},
    "folder":    {"en": "Folder:", "ka": "საქაღალდე:"},
    "browse":    {"en": "Browse…", "ka": "დათვალიერება…"},
    "recursive": {"en": "Include subfolders", "ka": "ქვესაქაღალდეებიც"},
    "preview":   {"en": "Preview", "ka": "წინასწარი სია"},
    "rename":    {"en": "Rename", "ka": "გადარქმევა"},
    "undo":      {"en": "↩ Undo", "ka": "↩ დაბრუნება"},
    "undo_none": {"en": "Nothing to undo.", "ka": "დასაბრუნებელი არაფერია."},
    "undo_confirm": {"en": "Undo the last rename ({n} file(s))?",
                     "ka": "დავაბრუნო ბოლო გადარქმევა ({n} ფაილი)?"},
    "undo_done": {"en": "Undone — restored {ok}, skipped {sk}.",
                  "ka": "დაბრუნდა — აღდგა {ok}, გამოტოვდა {sk}."},
    "col_hint":  {"en": "old  →  new   (⚠ = will be skipped)",
                  "ka": "ძველი  →  ახალი   (⚠ = გამოტოვდება)"},
    "warn_folder": {"en": "Specify a valid folder.",
                    "ka": "მიუთითე არსებული საქაღალდე."},
    "none":      {"en": "No files with Georgian names found.",
                  "ka": "ქართული სახელის მქონე ფაილი ვერ მოიძებნა."},
    "scan_n":    {"en": "Found {n} file(s) to rename"
                        " ({c} conflict(s) will be skipped).",
                  "ka": "საგადარქმევოა {n} ფაილი"
                        " ({c} კონფლიქტი გამოტოვდება)."},
    "confirm_t": {"en": "Confirm rename", "ka": "გადარქმევის დადასტურება"},
    "confirm_m": {"en": "Rename {n} file(s)? This cannot be undone.",
                  "ka": "გადავარქვათ {n} ფაილს? მოქმედება შეუქცევადია."},
    "st_conflict": {"en": "duplicate name — skipped",
                    "ka": "დუბლი სახელი — გამოტოვდა"},
    "st_exists": {"en": "target exists — skipped",
                  "ka": "სამიზნე არსებობს — გამოტოვდა"},
    "done":      {"en": "Done — renamed {ok}, skipped {sk}.",
                  "ka": "დასრულდა — გადაერქვა {ok}, გამოტოვდა {sk}."},
    "nothing":   {"en": "Nothing to rename — run Preview first.",
                  "ka": "გადასარქმევი არაფერია — ჯერ „წინასწარი სია“ გაუშვი."},
    "err":       {"en": "Error", "ka": "შეცდომა"},

    # ცარიელობის შემოწმება
    "check":     {"en": "Check contents (empty or not)",
                  "ka": "შემოწმება: მასალა დევს თუ ცარიელია"},
    "check_hint":{"en": "Logs, for every .shp in the folder, its feature count "
                        "and whether it is empty. Independent of renaming.",
                  "ka": "საქაღალდის ყველა .shp-ისთვის ლოგში წერს ობიექტების "
                        "რაოდენობას და ცარიელია თუ არა. გადარქმევისგან დამოუკიდებელი."},
    "chk_none":  {"en": "No .shp files found in the folder.",
                  "ka": "საქაღალდეში .shp ფაილი ვერ მოიძებნა."},
    "chk_hdr":   {"en": "— Content check —", "ka": "— მასალის შემოწმება —"},
    "chk_has":   {"en": "✓ {name} — {n} feature(s)",
                  "ka": "✓ {name} — {n} ობიექტი"},
    "chk_has_x": {"en": "✓ {name} — has data",
                  "ka": "✓ {name} — მასალა დევს"},
    "chk_empty": {"en": "⚠ {name} — EMPTY (0 features)",
                  "ka": "⚠ {name} — ცარიელია (0 ობიექტი)"},
    "chk_unknown": {"en": "? {name} — could not read",
                    "ka": "? {name} — ვერ წავიკითხე"},
    "chk_sum":   {"en": "— Checked {t}: {d} with data, {e} empty, {u} unreadable —",
                  "ka": "— შემოწმდა {t}: {d} მასალით, {e} ცარიელი, {u} წაუკითხავი —"},

    # tooltip-ები
    "tip_browse": {"en": "Pick the folder with the files to rename.",
                   "ka": "აირჩიე საქაღალდე გადასარქმევი ფაილებით."},
    "tip_recursive": {"en": "Also process files in subfolders.",
                      "ka": "ქვესაქაღალდეების ფაილებიც დამუშავდეს."},
    "tip_preview": {"en": "Show old → new names before renaming.",
                    "ka": "აჩვენე ძველი → ახალი სახელები გადარქმევამდე."},
    "tip_rename": {"en": "Rename now (with confirmation). Undo available.",
                   "ka": "გადაარქვი ახლა (დადასტურებით). დაბრუნება შესაძლებელია."},
    "tip_undo":  {"en": "Revert the last rename batch.",
                  "ka": "ბოლო გადარქმევის დაბრუნება."},
    "tip_check": {"en": "Log which .shp have data and which are empty.",
                  "ka": "ლოგში — რომელ .shp-ში დევს მასალა და რომელი ცარიელია."},
}


class RenameTransliterateTool(ToolFrame):
    tid = "rename_translit"
    CATALOG = RTR          # tr() მოდის ToolFrame-იდან (საერთო lookup)

    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    def build(self):
        pal = self.app.palette
        st = self._state()
        saved = self.app.get_tool_config(self.tid)
        self._plan = []
        self._undo = []          # ბოლო გადარქმევა: (ახალი_გზა, ძველი_გზა)

        ttk.Label(self, text=self.tr("heading"),
                  font=(UI_FONT, 13, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"],
                  wraplength=620, justify="left").pack(anchor="w", pady=(0, 12))

        # საქაღალდე
        row = ttk.Frame(self)
        row.pack(fill="x")
        ttk.Label(row, text=self.tr("folder")).pack(side="left")
        self.folder_var = tk.StringVar(value=st.get("folder") or saved.get("folder") or "")
        ttk.Entry(row, textvariable=self.folder_var).pack(
            side="left", fill="x", expand=True, padx=(6, 6))
        add_tip(ttk.Button(row, text=self.tr("browse"), command=self._pick),
                self.tr("tip_browse")).pack(side="left")

        opt = ttk.Frame(self)
        opt.pack(fill="x", pady=(8, 8))
        self.recursive_var = tk.BooleanVar(value=st.get("recursive", False))
        add_tip(ttk.Checkbutton(opt, text=self.tr("recursive"),
                                variable=self.recursive_var),
                self.tr("tip_recursive")).pack(side="left")
        add_tip(ttk.Button(opt, text=self.tr("preview"), command=self._preview),
                self.tr("tip_preview")).pack(side="left", padx=(16, 4))
        add_tip(ttk.Button(opt, text=self.tr("rename"), style="Accent.TButton",
                           command=self._rename),
                self.tr("tip_rename")).pack(side="left")
        add_tip(ttk.Button(opt, text=self.tr("undo"), command=self._undo_rename),
                self.tr("tip_undo")).pack(side="left", padx=(4, 0))

        # --- ცალკე მდგომი ფუნქცია: მასალის (ცარიელობის) შემოწმება ---
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(4, 6))
        chk = ttk.Frame(self)
        chk.pack(fill="x")
        self.check_var = tk.BooleanVar(value=False)
        add_tip(ttk.Checkbutton(chk, text=self.tr("check"), variable=self.check_var,
                                command=self._check_empty),
                self.tr("tip_check")).pack(side="left")
        ttk.Label(self, text=self.tr("check_hint"), foreground=pal["muted"],
                  wraplength=620, justify="left").pack(anchor="w", pady=(0, 8))

        ttk.Label(self, text=self.tr("col_hint"),
                  foreground=pal["muted"]).pack(anchor="w")
        self.preview = scrolledtext.ScrolledText(
            self, height=16, font=(MONO_FONT, 10), state="disabled",
            bg=pal["log_bg"], fg=pal["log_fg"], relief="flat", borderwidth=0)
        self.preview.pack(fill="both", expand=True, pady=(2, 0))

    def save_state(self):
        st = self._state()
        st["folder"] = self.folder_var.get()
        st["recursive"] = self.recursive_var.get()

    def _pick(self):
        d = filedialog.askdirectory(title=self.tr("folder"),
                                    initialdir=self.folder_var.get() or None)
        if d:
            self.folder_var.set(os.path.normpath(d))
            self.app.set_tool_config(self.tid, {"folder": os.path.normpath(d)})

    # ---- მასალის (ცარიელობის) შემოწმება — გადარქმევისგან დამოუკიდებელი ----
    def _check_empty(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("GIS_BOX", self.tr("warn_folder"))
            return
        shps = sorted((os.path.join(d, name) for d, name in self._iter_files(folder)
                       if name.lower().endswith(".shp")),
                      key=lambda p: os.path.basename(p).lower())
        if not shps:
            self.app.log("— " + self.tr("chk_none"))
            messagebox.showinfo("GIS_BOX", self.tr("chk_none"))
            return

        self.app.log(self.tr("chk_hdr"))
        with_data = empty = unknown = 0
        for shp in shps:
            name = os.path.basename(shp)
            cnt = feature_count(shp)
            if cnt is None:
                unknown += 1
                self.app.log(self.tr("chk_unknown", name=name))
            elif cnt == 0:
                empty += 1
                self.app.log(self.tr("chk_empty", name=name))
            elif cnt < 0:                     # მასალა დევს, ზუსტი რაოდენობა უცნობია
                with_data += 1
                self.app.log(self.tr("chk_has_x", name=name))
            else:
                with_data += 1
                self.app.log(self.tr("chk_has", name=name, n=cnt))

        self.app.log(self.tr("chk_sum", t=len(shps), d=with_data,
                             e=empty, u=unknown))

    # ---- გეგმის აგება ----
    def _iter_files(self, folder):
        if self.recursive_var.get():
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    yield root, f
        else:
            for f in os.listdir(folder):
                if os.path.isfile(os.path.join(folder, f)):
                    yield folder, f

    def _build_plan(self, folder):
        """დააბრუნებს (plan, conflicts). plan: dict-ების სია
        {dir, old, new, status}. status: ok / conflict / exists."""
        items = []
        target_count = {}
        for d, name in self._iter_files(folder):
            if not GEO_RANGE.search(name):
                continue                       # ქართული ასო არ არის — გამოტოვება
            new = transliterate(name)
            if new == name:
                continue                       # უცვლელი
            items.append({"dir": d, "old": name, "new": new, "status": "ok"})
            key = (os.path.normcase(d), os.path.normcase(new))
            target_count[key] = target_count.get(key, 0) + 1

        for it in items:
            key = (os.path.normcase(it["dir"]), os.path.normcase(it["new"]))
            dst = os.path.join(it["dir"], it["new"])
            if target_count[key] > 1:
                it["status"] = "conflict"
            elif os.path.exists(dst) and \
                    os.path.normcase(dst) != os.path.normcase(os.path.join(it["dir"], it["old"])):
                it["status"] = "exists"
        return items

    def _preview(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("GIS_BOX", self.tr("warn_folder"))
            return
        self._plan = self._build_plan(folder)
        self._show_plan()
        n_ok = sum(1 for it in self._plan if it["status"] == "ok")
        n_bad = len(self._plan) - n_ok
        if not self._plan:
            self.app.log("— " + self.tr("none"))
        else:
            self.app.log("— " + self.tr("scan_n", n=n_ok, c=n_bad))

    def _show_plan(self):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        if not self._plan:
            self.preview.insert("end", self.tr("none") + "\n")
        for it in self._plan:
            if it["status"] == "ok":
                self.preview.insert("end", f"{it['old']}   →   {it['new']}\n")
            else:
                note = self.tr("st_conflict") if it["status"] == "conflict" \
                    else self.tr("st_exists")
                self.preview.insert("end",
                                    f"⚠ {it['old']}   →   {it['new']}   [{note}]\n")
        self.preview.configure(state="disabled")

    # ---- გადარქმევა ----
    def _rename(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("GIS_BOX", self.tr("warn_folder"))
            return
        # ყოველთვის ხელახლა ვასკანერებთ (ფაილები შესაძლოა შეცვლილიყო)
        self._plan = self._build_plan(folder)
        doable = [it for it in self._plan if it["status"] == "ok"]
        self._show_plan()
        if not doable:
            messagebox.showinfo("GIS_BOX", self.tr("nothing"))
            return
        if not messagebox.askyesno(self.tr("confirm_t"),
                                   self.tr("confirm_m", n=len(doable))):
            return

        ok = 0
        skipped = len(self._plan) - len(doable)
        self._undo = []          # ახალი პარტია — წინა undo იშლება
        for it in doable:
            src = os.path.join(it["dir"], it["old"])
            dst = os.path.join(it["dir"], it["new"])
            try:
                os.rename(src, dst)
                self._undo.append((dst, src))     # დასაბრუნებლად: ახალი → ძველი
                self.app.log(f"✓ {it['old']} → {it['new']}")
                ok += 1
            except OSError as e:
                self.app.log(f"✗ {it['old']}: {e}")
                skipped += 1

        self.app.log("— " + self.tr("done", ok=ok, sk=skipped))
        messagebox.showinfo("GIS_BOX", self.tr("done", ok=ok, sk=skipped))
        # გადარქმევის შემდეგ სია განახლდეს
        self._plan = self._build_plan(folder)
        self._show_plan()

    def _undo_rename(self):
        """ბოლო გადარქმევის დაბრუნება — ახალ სახელებს ძველზე გადაარქმევს."""
        if not self._undo:
            messagebox.showinfo("GIS_BOX", self.tr("undo_none"))
            return
        if not messagebox.askyesno("GIS_BOX",
                                   self.tr("undo_confirm", n=len(self._undo))):
            return
        ok = skipped = 0
        for new_path, old_path in reversed(self._undo):
            # უსაფრთხოება: ახალი უნდა არსებობდეს, ძველი — არა (რომ არ გადავაწეროთ)
            if not os.path.exists(new_path) or os.path.exists(old_path):
                self.app.log(f"↷ {os.path.basename(new_path)}")
                skipped += 1
                continue
            try:
                os.rename(new_path, old_path)
                self.app.log(f"↩ {os.path.basename(new_path)} → {os.path.basename(old_path)}")
                ok += 1
            except OSError as e:
                self.app.log(f"✗ {os.path.basename(new_path)}: {e}")
                skipped += 1
        self._undo = []
        self.app.log("— " + self.tr("undo_done", ok=ok, sk=skipped))
        messagebox.showinfo("GIS_BOX", self.tr("undo_done", ok=ok, sk=skipped))
        folder = self.folder_var.get().strip()
        if folder and os.path.isdir(folder):
            self._plan = self._build_plan(folder)
            self._show_plan()
