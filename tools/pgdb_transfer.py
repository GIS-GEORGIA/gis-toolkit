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
from tools import pgdb_gdb_bridge as gdbx

from tools.pgdb_transfer_flow import DTR, KIND_LABEL, DEFAULT_YEAR, fmt_size, fmt_duration  # noqa: F401,E402
from tools import pgdb_transfer_flow as flow  # noqa: E402


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
        self._undated_path = None
        self._copyset_path = None
        self._year_queue = []
        self._batch_results = []
        self._batch_stopped = False
        self._copyall_path = None
        self._batch_auto = False
        self._batch_backed_up = False
        self._stager = flow.Stager()               # .gdb ↔ დროებითი .mdb (ძრავა .mdb-ზე მუშაობს)
        self._gdb_dst = self._gdb_final = None     # მიმღები .gdb და მისი ახალი FINAL ასლი
        self._final_path = None
        self._final_origin = None                  # .mdb FINAL-ის წყარო (მიმღები) — სიზუსტის შესადარებლად
        self._fidelity_text = None

        ttk.Label(self, text=self.tr("heading"), font=(UI_FONT, 13, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"], wraplength=780,
                  justify="left").pack(anchor="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("gdb_note"), foreground=pal["muted"], wraplength=780,
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
        add_tip(ttk.Entry(row, width=14, textvariable=self.year_var),
                self.tr("tip_year")).pack(side="left", padx=(6, 24))
        self.backup_var = tk.BooleanVar(value=st.get("backup", saved.get("backup", True)))
        add_tip(ttk.Checkbutton(row, text=self.tr("backup"), variable=self.backup_var),
                self.tr("tip_backup")).pack(side="left")
        self.years_box = ttk.Frame(opts)
        self.years_box.pack(fill="x", padx=8, pady=(0, 6))
        self.year_checks = {}
        self.all_years_var = tk.BooleanVar(value=False)
        ttk.Label(self.years_box, text=self.tr("years_hint"), foreground=pal["muted"]).pack(anchor="w")
        row3 = ttk.Frame(opts)
        row3.pack(fill="x", padx=8, pady=(0, 6))
        self.copyset_var = tk.BooleanVar(value=st.get("copyset", saved.get("copyset", False)))
        add_tip(ttk.Checkbutton(row3, text=self.tr("copyset"), variable=self.copyset_var),
                self.tr("tip_copyset")).pack(side="left")
        row4 = ttk.Frame(opts)
        row4.pack(fill="x", padx=8, pady=(0, 6))
        self.copyall_var = tk.BooleanVar(value=st.get("copyall", saved.get("copyall", False)))
        add_tip(ttk.Checkbutton(row4, text=self.tr("copyall"), variable=self.copyall_var),
                self.tr("tip_copyall")).pack(side="left")
        rowf = ttk.Frame(opts)
        rowf.pack(fill="x", padx=8, pady=(0, 6))
        self.final_var = tk.BooleanVar(value=st.get("final", saved.get("final", False)))
        add_tip(ttk.Checkbutton(rowf, text=self.tr("final"), variable=self.final_var),
                self.tr("tip_final")).pack(side="left")
        rowo = ttk.Frame(opts)
        rowo.pack(fill="x", padx=8, pady=(0, 6))
        self.onego_var = tk.BooleanVar(value=st.get("onego", saved.get("onego", False)))
        add_tip(ttk.Checkbutton(rowo, text=self.tr("onego"), variable=self.onego_var),
                self.tr("tip_onego")).pack(side="left")
        row2 = ttk.Frame(opts)
        row2.pack(fill="x", padx=8, pady=(0, 6))
        self.undated_var = tk.BooleanVar(value=st.get("undated", saved.get("undated", True)))
        add_tip(ttk.Checkbutton(row2, text=self.tr("undated"), variable=self.undated_var),
                self.tr("tip_undated")).pack(side="left")

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
        self.merge_btn = ttk.Button(brow, text=self.tr("btn_merge"), command=self._merge_years)
        self.merge_btn.pack(side="left", padx=(8, 0))
        add_tip(self.merge_btn, self.tr("tip_merge"))
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
        st["undated"] = self.undated_var.get()
        st["copyset"] = self.copyset_var.get()
        st["copyall"] = self.copyall_var.get()
        st["final"], st["onego"] = self.final_var.get(), self.onego_var.get()

    def _pick(self, var):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=self.tr("pick_file"), command=lambda: self._pick_file(var))
        menu.add_command(label=self.tr("pick_folder"), command=lambda: self._pick_folder(var))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _pick_file(self, var):
        cur = var.get().strip()
        p = filedialog.askopenfilename(
            title=self.tr("pick_title"), initialdir=os.path.dirname(cur) if cur else None,
            filetypes=[("Personal Geodatabase / Access", "*.mdb"), ("All files", "*.*")])
        if p:
            var.set(os.path.normpath(p))
            self._infos = None

    def _pick_folder(self, var):
        cur = var.get().strip()
        p = filedialog.askdirectory(title=self.tr("pick_title"), initialdir=os.path.dirname(cur) if cur else None,
                                    mustexist=True)
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
        return flow.message(self.tr, exc)

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
        self.merge_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    # ------------------------------------------------------------ ვალიდაცია
    def _validate_inputs(self, need_map=True):
        """(src, dst, year) ან None (შეტყობინება უკვე ნაჩვენებია)."""
        v = flow.validate(self.src_var.get().strip(), self.dst_var.get().strip(), self.year_var.get())
        if v[0] == "warn":
            messagebox.showwarning("GIS_BOX", self.tr(v[1], **v[2]))
            return None
        return v

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
        self._stager.reset()
        self.cancel_event.clear()
        self._set_busy(True)
        self.status.set(self.tr("btn_check") + "…")
        threading.Thread(target=self._check_worker, args=(src, dst), daemon=True).start()

    def _progress_cb(self):
        return lambda k, i, n: self.msg_queue.put(("progress", (k, i, n)))

    def _check_worker(self, src, dst):
        try:
            res = flow.check(src, dst, self._stager, progress=self._progress_cb(), cancel=self.cancel_event.is_set,
                             status=lambda key: self.msg_queue.put(("status", self.tr(key))))
            self.msg_queue.put(("checked", res))
        except Exception as e:                       # noqa: BLE001
            self.msg_queue.put(("error", flow.as_transfer_error(e)))

    def _on_checked(self, payload):
        si, di, mapping, amb, locked, years = payload
        self._infos = (si, di)
        self._build_years(years)
        self._build_mapping(si, di, mapping, amb)
        lines = flow.check_lines(self.tr, self.app.lang, si, di, self._current_mapping(), locked)
        self._set_text(self.summary, "\n".join(lines))
        self.status.set(self.tr("ready"))
        self._set_busy(False)

    def _build_years(self, years):
        """წყაროში ნაპოვნი წლები → მოსანიშნი თოლიები; არჩევანი ``year_var``-ში იწერება (ხელით შეყვანაც მუშაობს)."""
        for w in self.years_box.winfo_children():
            w.destroy()
        self.year_checks = {}
        if not years:
            ttk.Label(self.years_box, text=self.tr("years_hint"), foreground=self.app.palette["muted"]).pack(anchor="w")
            return
        try:
            cur = core.parse_years(self.year_var.get())
        except ValueError:
            cur = []
        chosen = set(years) if cur == "all" else set(cur) & set(years)
        ttk.Label(self.years_box, text=self.tr("years_pick"), font=(UI_FONT, 9, "bold")).grid(
            row=0, column=0, columnspan=12, sticky="w")
        self.all_years_var = tk.BooleanVar(value=(chosen == set(years)))
        ttk.Checkbutton(self.years_box, text=self.tr("years_all"), variable=self.all_years_var,
                        command=self._years_all_toggled).grid(row=1, column=0, sticky="w", padx=(0, 12))
        for i, y in enumerate(years):
            var = tk.BooleanVar(value=(y in chosen))
            self.year_checks[y] = var
            ttk.Checkbutton(self.years_box, text=str(y), variable=var, command=self._years_changed).grid(
                row=1 + (i + 1) // 10, column=(i + 1) % 10, sticky="w", padx=(0, 12))
        self._years_changed()

    def _years_all_toggled(self):
        for v in self.year_checks.values():
            v.set(self.all_years_var.get())
        self._years_changed()

    def _years_changed(self):
        sel = sorted(y for y, v in self.year_checks.items() if v.get())
        self.all_years_var.set(bool(sel) and len(sel) == len(self.year_checks))
        self.year_var.set(", ".join(str(y) for y in sel))      # ცარიელი → „მიუთითე წელი“ გაფრთხილება

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
        src_o, dst_o = src, dst                        # მომხმარებლის არჩეული (შეიძლება .gdb)
        src, dst = self._stager.engine_path(src_o), self._stager.engine_path(dst_o)  # ძრავისთვის (.mdb)
        dst_gdb = gdbx.is_gdb(dst_o)
        self._final_path = None
        self._final_origin, self._fidelity_text = None, None
        self._gdb_dst = self._gdb_final = None
        if year == "all":
            try:
                year = core.source_years(src, mapping)
            except Exception as e:                 # noqa: BLE001
                messagebox.showerror("GIS_BOX", self._msg(core.friendly_error(e)))
                return
            if not year:
                messagebox.showwarning("GIS_BOX", self.tr("e_no_years"))
                return
        final = bool(self.final_var.get()) or dst_gdb  # .gdb მიმღები ადგილზე არასდროს იცვლება → ყოველთვის ახალი ასლი
        auto = bool(self.onego_var.get()) and len(year) > 1
        self._batch_auto, self._batch_backed_up = False, False
        if final or auto:                              # ერთი საერთო დადასტურება
            fpath = (gdbx.final_gdb_path(dst_o) if dst_gdb else core.final_output_path(dst_o)) if final else None
            extra = ""
            if self.copyall_var.get():
                extra += self.tr("conf_copyall", p=core.all_years_output_path(dst_o)).strip("\n") + "\n"
            if not final and self.backup_var.get():
                extra += self.tr("conf_backup").strip("\n") + "\n"
            sw = core.size_warning(dst_o)
            if sw:
                extra += self.tr("size_warn", mb=sw[0], pct=sw[1])
            mode = self.tr("mode_final", p=fpath) if final else self.tr("mode_direct")
            if not messagebox.askyesno(self.tr("conf_title"), self.tr(
                    "conf_batch", y=", ".join(str(y) for y in year), s=os.path.basename(src_o),
                    d=os.path.basename(dst_o), mode=mode, extra=extra)):
                return
            self._batch_auto = auto
            if dst_gdb:
                self._gdb_dst, self._gdb_final = dst_o, fpath
            elif final:
                self._final_origin = dst
                self._set_busy(True)
                self.status.set(self.tr("st_copy"))
                self._year_queue = list(year[1:])
                self._batch_results = []
                threading.Thread(target=self._final_copy_worker, args=(src, dst, fpath, year[0], mapping),
                                 daemon=True).start()
                return
        self._year_queue = list(year[1:])
        self._batch_ctx = (src, dst, mapping)
        self._batch_results = []
        self._launch_analysis(src, dst, year[0], mapping)

    def _final_copy_worker(self, src, dst, fpath, first_year, mapping):
        try:
            core.make_final_copy(dst, fpath)
            self.msg_queue.put(("final_ready", (src, fpath, first_year, mapping)))
        except core.TransferError as e:
            self.msg_queue.put(("error", e))
        except Exception as e:                         # noqa: BLE001
            self.msg_queue.put(("error", core.friendly_error(e)))

    def _on_final_ready(self, payload):
        src, fpath, first_year, mapping = payload
        self._final_path = fpath
        self._batch_ctx = (src, fpath, mapping)
        self._launch_analysis(src, fpath, first_year, mapping)

    def _final_shown(self):
        return self._gdb_final or (self._final_path if self.final_var.get() else None)

    def _batch_next(self):
        """მომდევნო წელი რიგიდან (ავტომატურად); რიგი ცარიელია → ჯამური შეტყობინება."""
        if self._year_queue and getattr(self, "_batch_ctx", None):
            src, dst, mapping = self._batch_ctx
            nxt = self._year_queue.pop(0)
            self.after(100, lambda: self._launch_analysis(src, dst, nxt, mapping))
            return True
        if len(self._batch_results) > 1:
            lines = flow.batch_lines(self.tr, self._batch_results, getattr(self, "_batch_stopped", False),
                                     self._final_shown(), self._fidelity_text)
            messagebox.showinfo("GIS_BOX", "\n".join(lines))
        self._batch_results = []
        return False

    def _batch_abort(self):
        """გამოტოვებული/გაუქმებული/შეცდომა: დარჩენილი წლები აღარ მუშავდება."""
        if self._year_queue:
            self._batch_stopped = True
        self._year_queue = []
        if len(getattr(self, "_batch_results", [])) > 1 or getattr(self, "_batch_stopped", False):
            messagebox.showinfo("GIS_BOX", "\n".join(flow.batch_lines(self.tr, self._batch_results, True)))
        self._batch_results = []
        self._batch_stopped = False

    def _launch_analysis(self, src, dst, year, mapping):
        self.cancel_event.clear()
        self._set_text(self.summary, "")
        self._set_text(self.errlog, "")
        self._reset_tree()
        self._wrote = False
        self._log_path = core.default_log_path(self._stager.orig_of(dst), self.app_data_dir(), year=year,
                                               src_path=self._stager.orig_of(src))
        self._set_busy(True)
        self.progress.configure(value=0)
        self.status.set(self.tr("st_analysing"))
        self._t0 = time.time()
        threading.Thread(target=self._analysis_worker, args=(src, dst, year, mapping), daemon=True).start()

    def app_data_dir(self):
        return flow.data_dir()

    def _sink(self, line, level):
        self.msg_queue.put(("log", (line, level)))

    def _analysis_worker(self, src, dst, year, mapping):
        opts = {"backup": self.backup_var.get(), "undated": self.undated_var.get(),
                "copyset": self.copyset_var.get(), "copyall": self.copyall_var.get()}
        try:
            plan = flow.analysis(src, dst, year, mapping, self._log_path, self._stager, opts,
                                 gdb_final=self._gdb_final, progress=self._progress_cb(),
                                 cancel=self.cancel_event.is_set, sink=self._sink)
            self.msg_queue.put(("analysed", plan))
        except Exception as e:                     # noqa: BLE001
            self.msg_queue.put(("error", flow.as_transfer_error(e)))

    def _undated_count(self, plan):
        return flow.undated_count(plan, self.undated_var.get())

    def _on_analysed(self, plan):
        self._fill_tree(plan, written=False)
        todo = plan.totals()["to_insert"]
        n_undated = self._undated_count(plan)
        o_src, o_dst = self._stager.orig_of(plan.src_path), self._stager.orig_of(plan.dst_path)
        self._undated_path = (core.undated_output_path(o_src, os.path.dirname(os.path.abspath(o_dst)))
                              if n_undated else None)
        for lp in plan.layers:
            self._report_layer_issues(lp, plan)
        text = flow.confirm_head(self.tr, self.app.lang, plan, o_src, o_dst)
        if todo == 0:
            if n_undated and messagebox.askyesno(self.tr("conf_title"), text + "\n" + self.tr("conf_undated_only",
                                                                                              n=n_undated, p=self._undated_path)):
                self.cancel_event.clear()
                self.status.set(self.tr("st_undated"))
                self.progress.configure(value=0)
                threading.Thread(target=self._write_worker, args=(plan, False, self._undated_path, True),
                                 daemon=True).start()
                return
            self._close_out(plan, "nothing to insert (analysis only)")
            self._finish(plan, written=False)
            self._set_busy(False)
            self.status.set(self.tr("ready"))
            self._batch_results.append((plan.year, 0))
            if self._year_queue:
                self._batch_next()
                return
            if not n_undated and len(self._batch_results) <= 1:
                messagebox.showinfo(self.tr("conf_title"), text + "\n" + self.tr("conf_nothing"))
            self._batch_next()
            return
        if self._gdb_final:
            text += self.tr("mode_final", p=self._gdb_final)
        else:
            text += self.tr("conf_backup") if self.backup_var.get() else self.tr("conf_nobackup")
        if n_undated:
            text += "\n" + self.tr("conf_undated", n=n_undated, p=self._undated_path)
        self._copyset_path = (core.transferred_output_path(o_dst, plan.year,
                                                           os.path.dirname(os.path.abspath(o_dst)))
                              if self.copyset_var.get() else None)
        if self._copyset_path:
            text += "\n" + self.tr("conf_copyset", p=self._copyset_path)
        self._copyall_path = (core.all_years_output_path(o_dst) if self.copyall_var.get() else None)
        if self._copyall_path:
            text += "\n" + self.tr("conf_copyall", p=self._copyall_path)
        text += "\n" + self.tr("conf_ask", n=todo)
        if self._batch_auto and flow.is_clean(plan):
            self._append(self.errlog, "[auto] {}: {}".format(plan.year, self.tr("conf_line", k="∑", f=plan.totals()["found"],
                         u=plan.totals()["duplicates"], n=todo, e=0).strip()))
        elif not messagebox.askyesno(self.tr("conf_title"), text):
            self._close_out(plan, "declined by user at confirmation (analysis only, nothing written)")
            self._set_busy(False)
            self.status.set(self.tr("ready"))
            self._finish(plan, written=False, summary_only=True)
            self._batch_abort()
            return
        self.cancel_event.clear()
        self.status.set(self.tr("st_writing"))
        self.progress.configure(value=0)
        backup = (bool(self.backup_var.get()) and not self.final_var.get() and not self._gdb_final
                  and not (self._batch_auto and self._batch_backed_up))
        self._batch_backed_up = self._batch_backed_up or backup
        threading.Thread(target=self._write_worker, args=(plan, backup, self._undated_path, False),
                         daemon=True).start()

    def _write_worker(self, plan, backup, undated_path=None, skip_main=False):
        try:
            flow.write(plan, self._log_path, backup, undated_path, skip_main,
                       gdb_dst=self._gdb_dst, gdb_final=self._gdb_final, copyall_path=self._copyall_path,
                       copyset_path=self._copyset_path, final_path=self._final_path,
                       final_origin=self._final_origin, last_year=not self._year_queue,
                       progress=self._progress_cb(), cancel=self.cancel_event.is_set, sink=self._sink,
                       status=lambda key: self.msg_queue.put(("status", self.tr(key))))
            if plan.fidelity:
                self._fidelity_text = flow.fidelity_text(self.tr, plan.fidelity)
            self.msg_queue.put(("written", plan))
        except Exception as e:                     # noqa: BLE001
            self.msg_queue.put(("error", flow.as_transfer_error(e)))

    def _merge_years(self):
        if self.busy:
            return
        dst = self.dst_var.get().strip()
        paths = filedialog.askopenfilenames(
            title=self.tr("merge_pick"), initialdir=os.path.dirname(dst) if dst else None,
            filetypes=[("Personal Geodatabase / Access", "*.mdb"), ("All files", "*.*")])
        paths = [os.path.normpath(x) for x in paths]
        if len(paths) < 2:
            if paths:
                messagebox.showwarning("GIS_BOX", self.tr("merge_few"))
            return
        out = core.merged_output_path(paths[0])
        if not messagebox.askyesno(self.tr("conf_title"), self.tr("merge_ask", n=len(paths), p=out)):
            return
        self.cancel_event.clear()
        self._set_text(self.summary, "")
        self._set_text(self.errlog, "")
        self._log_path = core.default_log_path(out, self.app_data_dir(), year="merge", src_path=paths[0])
        self._set_busy(True)
        self.progress.configure(value=0)
        self.status.set(self.tr("st_writing"))
        threading.Thread(target=self._merge_worker, args=(paths, out), daemon=True).start()

    def _merge_worker(self, paths, out):
        try:
            plan = flow.merge(paths, out, self._log_path, progress=self._progress_cb(),
                              cancel=self.cancel_event.is_set, sink=self._sink)
            self.msg_queue.put(("merged", plan))
        except Exception as e:                     # noqa: BLE001
            self.msg_queue.put(("error", flow.as_transfer_error(e)))

    def _on_merged(self, plan):
        self._set_busy(False)
        self.progress.configure(value=0)
        self.log_btn.configure(state="normal")
        if plan is None:
            self.status.set(self.tr("ready"))
            messagebox.showinfo("GIS_BOX", self.tr("merge_nothing"))
            return
        lines = flow.merge_lines(self.tr, self.app.lang, plan, self._log_path)
        self._set_text(self.summary, "\n".join(lines))
        self.status.set(self.tr("merge_done", n=plan.totals()["inserted"]))
        messagebox.showinfo("GIS_BOX", "\n".join(lines))

    def _close_out(self, plan, outcome, written=False):
        """ლოგის დასრულება: საბოლოო შეჯამება + ჩანაწერების CSV + ისტორიის ინდექსი (ფაილებს მხოლოდ ემატება)."""
        flow.close_out(plan, self._log_path, outcome, written=written)

    def _on_written(self, plan):
        self._wrote = True
        self._fill_tree(plan, written=True)
        self._finish(plan, written=True)
        self._set_busy(False)
        n = plan.totals()["inserted"]
        self.status.set(self.tr("st_done", n=n))
        self._infos = None                        # ბაზები შეიცვალა — შესაბამისობა/რიცხვები ხელახლა
        msg = flow.done_message(self.tr, plan, self._final_shown(), self._fidelity_text)
        self._batch_results.append((plan.year, n))
        if self._year_queue:                       # რამდენიმე წელი: ავტომატურად შემდეგი, დიალოგის გარეშე
            self._batch_next()
            return
        if len(self._batch_results) <= 1:
            messagebox.showinfo("GIS_BOX", msg)
            self._batch_results = []
        else:
            self._batch_next()

    def _report_layer_issues(self, lp, plan):
        """შეცდომების/გაფრთხილებების არეში: ჩანაწერები, რომლებიც ვერ გადავა."""
        for line in flow.issue_lines(self.tr, self.app.lang, lp):
            self._append(self.errlog, line)

    def _finish(self, plan, written, summary_only=False):
        t = plan.totals()
        lines = flow.summary_lines(self.tr, self.app.lang, plan, written, self._log_path, self.undated_var.get())
        if self._log_path:
            self.log_btn.configure(state="normal")
        self._set_text(self.summary, "\n".join(lines))
        if written:
            self.app.log("— " + self.tr("st_done", n=t["inserted"]))
        self.app.set_tool_config(self.tid, {"src": self.src_var.get().strip(), "dst": self.dst_var.get().strip(),
                                            "year": self.year_var.get().strip(), "backup": bool(self.backup_var.get()),
                                            "undated": bool(self.undated_var.get()),
                                            "copyset": bool(self.copyset_var.get()),
                                            "copyall": bool(self.copyall_var.get()),
                                            "final": bool(self.final_var.get()),
                                            "onego": bool(self.onego_var.get())})

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
                elif kind == "status":
                    self.status.set(payload)
                elif kind == "final_ready":
                    self._on_final_ready(payload)
                elif kind == "analysed":
                    self._on_analysed(payload)
                elif kind == "written":
                    self._on_written(payload)
                elif kind == "merged":
                    self._on_merged(payload)
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
                    self._batch_abort()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)
