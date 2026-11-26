"""Database Data Transfer (PySide6): Personal Geodatabase (.mdb) / File Geodatabase (.gdb) -> .mdb / new .gdb copy.

The same steps and dialogs as the classic tool, because both call ``tools/pgdb_transfer_flow`` (the workflow) and
``tools/pgdb_transfer_core`` (the engine):

    Check databases (read-only) -> layer mapping by geometry type + years found in the source
    Start: analysis of one year (nothing is written) -> confirmation with the numbers -> write in ONE transaction
    (backup first, optional extra databases, records without a date) -> next year ...

Several years: each year is analysed, confirmed and logged separately, or "confirm once" for all (a year with
problems still asks). "FINAL" writes into a NEW copy of the destination; a .gdb destination is never modified (always
a new copy). Every step runs as a background task (progress + Cancel in the shell's status bar); a cancelled or
failed write is rolled back by the engine. Texts: ``pgdb_transfer_flow.DTR`` (shared with the classic tool).
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from tools import pgdb_gdb_bridge as gdbx
from tools import pgdb_transfer_core as core
from tools import pgdb_transfer_flow as flow

STATUS = "\x01"                        # log-channel prefix: a status line (not a warning)
DST_COLOR = "#d9822b"


class DbTransferPage(QWidget):
    TOOL = "db_transfer"

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        self.tr = flow.make_tr(self.lang)
        self.stager = flow.Stager()
        self._infos = None
        self._pending_start = False
        self._chain = 0                            # >0 while a next step is queued (between two tasks)
        self._log_path = None
        self._year_queue, self._batch_results = [], []
        self._batch_stopped = self._batch_auto = self._batch_backed_up = False
        self._batch_ctx = None
        self._final_path = self._final_origin = None
        self._gdb_dst = self._gdb_final = None
        self._fidelity_text = None
        self._undated_path = self._copyset_path = self._copyall_path = None
        self.year_checks = {}
        self.map_combos = {}
        self._build()
        st = shell.settings["tool_state"].get(self.TOOL, {})
        self.src_edit.setText(st.get("src", ""))
        self.dst_edit.setText(st.get("dst", ""))
        self.year_edit.setText(str(st.get("year") or flow.DEFAULT_YEAR))
        self.backup_box.setChecked(st.get("backup", True))
        self.undated_box.setChecked(st.get("undated", True))
        for key in ("copyset", "copyall", "final", "onego"):
            getattr(self, key + "_box").setChecked(bool(st.get(key, False)))
        self.src_edit.textChanged.connect(self._paths_changed)
        self.dst_edit.textChanged.connect(self._paths_changed)
        self._paths_changed()
        shell.busy_changed.connect(self._set_busy)

    # ------------------------------------------------------------------ UI
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        for key in ("desc", "gdb_note"):
            lb = QLabel(self.tr(key))
            lb.setObjectName("muted")
            lb.setWordWrap(True)
            lay.addWidget(lb)

        self.src_edit, self.src_shown, src_box = self._db_box("src_box", "src_lbl", None)
        lay.addWidget(src_box)
        flow_lbl = QLabel(self.tr("flow"))
        flow_lbl.setObjectName("muted")
        flow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(flow_lbl)
        self.dst_edit, self.dst_shown, dst_box = self._db_box("dst_box", "dst_lbl", DST_COLOR)
        lay.addWidget(dst_box)

        opts = QGroupBox(self.tr("opts"))
        ol = QVBoxLayout(opts)
        r = QHBoxLayout()
        r.addWidget(QLabel(self.tr("year")))
        self.year_edit = QLineEdit()
        self.year_edit.setMaximumWidth(220)
        self.year_edit.setToolTip(self.tr("tip_year"))
        r.addWidget(self.year_edit)
        r.addSpacing(16)
        self.backup_box = self._check("backup", "tip_backup")
        r.addWidget(self.backup_box)
        r.addStretch(1)
        ol.addLayout(r)
        self.years_w = QWidget()
        self.years_grid = QGridLayout(self.years_w)
        self.years_grid.setContentsMargins(0, 0, 0, 0)
        self.years_grid.setHorizontalSpacing(22)
        self.years_grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
        ol.addWidget(self.years_w)
        self.all_years_box = None
        self._build_years([])
        for key in ("copyset", "copyall", "final", "onego", "undated"):
            box = self._check(key, "tip_" + key)
            setattr(self, key + "_box", box)
            ol.addWidget(box)
        lay.addWidget(opts)

        self.map_box = QGroupBox(self.tr("map_box"))
        self.map_grid = QGridLayout(self.map_box)
        hint = QLabel(self.tr("btn_check") + "…")
        hint.setObjectName("muted")
        self.map_grid.addWidget(hint, 0, 0)
        lay.addWidget(self.map_box)

        brow = QHBoxLayout()
        self.check_btn = self._btn("btn_check", self.check, "tip_check")
        self.start_btn = self._btn("btn_start", self.start, "tip_start")
        self.start_btn.setObjectName("primary")
        self.merge_btn = self._btn("btn_merge", self.merge_years, "tip_merge")
        self.log_btn = self._btn("btn_log", self.open_log)
        self.log_btn.setEnabled(False)
        for b in (self.check_btn, self.start_btn, self.merge_btn):
            brow.addWidget(b)
        brow.addStretch(1)
        brow.addWidget(self.log_btn)
        lay.addLayout(brow)
        self.status = QLabel(self.tr("ready"))
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        res = QGroupBox(self.tr("res_box"))
        rl = QVBoxLayout(res)
        self.table = QTableWidget(len(core.KINDS) + 1, 5)
        self.table.setHorizontalHeaderLabels([self.tr("t_layer"), self.tr("t_found"), self.tr("t_dup"),
                                              self.tr("t_plan") + " / " + self.tr("t_ins"), self.tr("t_err")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setFixedHeight(self.table.horizontalHeader().sizeHint().height()
                                  + (len(core.KINDS) + 1) * self.table.verticalHeader().defaultSectionSize() + 16)
        rl.addWidget(self.table)
        lay.addWidget(res)
        self._reset_table()

        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.summary = QPlainTextEdit()
        self.errlog = QPlainTextEdit()
        for title, w in ((self.tr("sum_box"), self.summary), (self.tr("err_box"), self.errlog)):
            w.setReadOnly(True)
            w.setFont(mono)
            w.setMinimumHeight(220)
            g = QGroupBox(title)
            QVBoxLayout(g).addWidget(w)
            split.addWidget(g)
        lay.addWidget(split, 1)

    def _db_box(self, box_key, lbl_key, color):
        box = QGroupBox(self.tr(box_key))
        bl = QVBoxLayout(box)
        r = QHBoxLayout()
        r.addWidget(QLabel(self.tr(lbl_key)))
        edit = QLineEdit()
        r.addWidget(edit, 1)
        r.addWidget(self._btn("pick_file", lambda e=edit: self._pick_file(e)))
        r.addWidget(self._btn("pick_folder", lambda e=edit: self._pick_folder(e)))
        bl.addLayout(r)
        shown = QLabel()
        shown.setStyleSheet("font-weight:600; font-size:14px; background:transparent;"
                            + ("color:{};".format(color) if color else ""))
        if not color:
            shown.setObjectName("accent")
        bl.addWidget(shown)
        return edit, shown, box

    def _btn(self, key, slot, tip=None):
        b = QPushButton(self.tr(key))
        b.clicked.connect(lambda _c=False: slot())
        if tip:
            b.setToolTip(self.tr(tip))
        return b

    def _check(self, key, tip):
        b = QCheckBox(self.tr(key))
        b.setToolTip(self.tr(tip))
        return b

    def _kind(self, k):
        return flow.kind_name(k, self.lang)

    def _set_busy(self, busy):
        for b in (self.check_btn, self.start_btn, self.merge_btn):
            b.setEnabled(not busy)
        self.start_btn.setText(self.tr("btn_busy") if busy else self.tr("btn_start"))

    @property
    def busy(self):
        return self.shell.task is not None or self._chain > 0

    # ------------------------------------------------------------------ dialogs (patched in tests)
    def _ask(self, title, text):
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def _info(self, text, title="GIS_BOX"):
        QMessageBox.information(self, title, text)

    def _warn(self, text):
        QMessageBox.warning(self, "GIS_BOX", text)

    def _error(self, title, text):
        QMessageBox.critical(self, title, text)

    def _open_file(self, start):
        return QFileDialog.getOpenFileName(self, self.tr("pick_title"), start,
                                           "Personal Geodatabase / Access (*.mdb);;All files (*.*)")[0]

    def _open_dir(self, start):
        return QFileDialog.getExistingDirectory(self, self.tr("pick_title"), start)

    def _open_files(self, start):
        return QFileDialog.getOpenFileNames(self, self.tr("merge_pick"), start,
                                            "Personal Geodatabase / Access (*.mdb);;All files (*.*)")[0]

    # ------------------------------------------------------------------ paths
    def _pick_file(self, edit):
        cur = edit.text().strip()
        p = self._open_file(os.path.dirname(cur) if cur else "")
        if p:
            edit.setText(os.path.normpath(p))

    def _pick_folder(self, edit):
        cur = edit.text().strip()
        p = self._open_dir(os.path.dirname(cur) if cur else "")
        if p:
            edit.setText(os.path.normpath(p))

    def _paths_changed(self, *_):
        for edit, shown, key in ((self.src_edit, self.src_shown, "src_shown"),
                                 (self.dst_edit, self.dst_shown, "dst_shown")):
            p = edit.text().strip()
            if p:
                shown.setText(self.tr(key, name=os.path.basename(p), size=flow.fmt_size(p)))
            else:
                shown.setText(self.tr(key, name=self.tr("none_shown"), size="—"))
        self._infos = None

    def _save_state(self):
        self.shell.settings["tool_state"][self.TOOL] = {
            "src": self.src_edit.text().strip(), "dst": self.dst_edit.text().strip(),
            "year": self.year_edit.text().strip(), "backup": self.backup_box.isChecked(),
            "undated": self.undated_box.isChecked(), "copyset": self.copyset_box.isChecked(),
            "copyall": self.copyall_box.isChecked(), "final": self.final_box.isChecked(),
            "onego": self.onego_box.isChecked()}
        self.shell.settings.save()

    # ------------------------------------------------------------------ tables / texts
    def _set_row(self, row, values):
        for c, v in enumerate(values):
            it = QTableWidgetItem(str(v))
            it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter
                                | (Qt.AlignmentFlag.AlignLeft if c == 0 else Qt.AlignmentFlag.AlignCenter))
            self.table.setItem(row, c, it)

    def _reset_table(self):
        for i, k in enumerate(core.KINDS):
            self._set_row(i, (self._kind(k), "—", "—", "—", "—"))
        self._set_row(len(core.KINDS), (self.tr("t_total"), "—", "—", "—", "—"))

    def _fill_table(self, plan, written):
        for lp in plan.layers:
            ins = lp.inserted if written else lp.to_insert_count
            self._set_row(core.KINDS.index(lp.kind), (self._kind(lp.kind), lp.found, lp.duplicates, ins,
                                                      len(lp.errors)))
        t = plan.totals()
        self._set_row(len(core.KINDS), (self.tr("t_total"), t["found"], t["duplicates"],
                                        t["inserted"] if written else t["to_insert"], t["errors"]))

    def table_values(self):
        return [[self.table.item(r, c).text() for c in range(5)] for r in range(self.table.rowCount())]

    def _err(self, line):
        self.errlog.appendPlainText(line)

    def _on_log(self, m):
        if m.startswith(STATUS):
            self.status.setText(m[1:])
        else:
            self._err(m)

    # ------------------------------------------------------------------ background steps
    def _callbacks(self, ctx):
        last = [0.0]

        def progress(k, i, n):
            ctx.progress(i, n, "")
            now = time.time()
            if now - last[0] > 0.15 or i >= n:
                last[0] = now
                ctx.log(STATUS + self.tr("st_progress", k=self._kind(k) if k in core.KINDS else k, i=i, n=n))

        def sink(line, level):
            if level in ("WARN", "ERROR"):
                ctx.log(line)

        def status(key):
            ctx.log(STATUS + self.tr(key))
        return dict(progress=progress, cancel=ctx.cancelled, sink=sink, status=status)

    def _run(self, tag, work, on_ok, params=None):
        """Run ``work(ctx, cb)`` as a shell task once the shell is free; errors -> TransferError -> _on_error."""
        def wrapped(ctx):
            try:
                return "ok", work(ctx, self._callbacks(ctx))
            except Exception as e:                 # noqa: BLE001
                return "err", flow.as_transfer_error(e)

        def done(res):
            kind, val = res
            (on_ok if kind == "ok" else self._on_error)(val)

        self._when_free(lambda: self.shell.run(wrapped, self.TOOL + "." + tag, params=params or {},
                                               on_done=done, on_log=self._on_log))

    def _when_free(self, fn):
        """Start ``fn`` as soon as the previous task has fully finished (the shell runs one task at a time)."""
        self._chain += 1

        def go():
            if self.shell.task is not None:
                QTimer.singleShot(30, go)
                return
            self._chain -= 1
            fn()
        QTimer.singleShot(0, go)

    # ------------------------------------------------------------------ validation / check
    def _validate(self):
        v = flow.validate(self.src_edit.text().strip(), self.dst_edit.text().strip(), self.year_edit.text())
        if v[0] == "warn":
            self._warn(self.tr(v[1], **v[2]))
            return None
        return v

    def _current_mapping(self):
        m = {}
        for k, (sc, dc) in self.map_combos.items():
            s, d = sc.currentText(), dc.currentText()
            if s and d:
                m[k] = (s, d)
        return m

    def check(self):
        if self.busy:
            return
        v = self._validate()
        if not v:
            return
        src, dst, _y = v
        self.errlog.clear()
        self.summary.clear()
        self.stager.reset()
        self.status.setText(self.tr("btn_check") + "…")
        self._run("check", lambda ctx, cb: flow.check(src, dst, self.stager, cb["progress"], cb["cancel"],
                                                      cb["status"]),
                  self._on_checked, {"src": src, "dst": dst})

    def _on_checked(self, res):
        si, di, mapping, amb, locked, years = res
        self._infos = (si, di)
        self._build_years(years)
        self._build_mapping(si, di, mapping)
        self.summary.setPlainText("\n".join(flow.check_lines(self.tr, self.lang, si, di, self._current_mapping(),
                                                             locked)))
        self.status.setText(self.tr("ready"))
        if self._pending_start:
            self._pending_start = False
            self._when_free(self.start)

    def _build_years(self, years):
        while self.years_grid.count():
            w = self.years_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.year_checks = {}
        self.all_years_box = None
        if not years:
            lb = QLabel(self.tr("years_hint"))
            lb.setObjectName("muted")
            self.years_grid.addWidget(lb, 0, 0, 1, 10)
            return
        try:
            cur = core.parse_years(self.year_edit.text())
        except ValueError:
            cur = []
        chosen = set(years) if cur == "all" else set(cur) & set(years)
        head = QLabel(self.tr("years_pick"))
        head.setStyleSheet("font-weight:600; background:transparent;")
        self.years_grid.addWidget(head, 0, 0, 1, 10)
        self.all_years_box = QCheckBox(self.tr("years_all"))
        self.all_years_box.setChecked(chosen == set(years))
        self.all_years_box.clicked.connect(self._years_all_toggled)
        self.years_grid.addWidget(self.all_years_box, 1, 0)
        for i, y in enumerate(years):
            cb = QCheckBox(str(y))
            cb.setChecked(y in chosen)
            cb.clicked.connect(self._years_changed)
            self.year_checks[y] = cb
            self.years_grid.addWidget(cb, 1 + (i + 1) // 10, (i + 1) % 10)
        self._years_changed()

    def _years_all_toggled(self, *_):
        for cb in self.year_checks.values():
            cb.setChecked(self.all_years_box.isChecked())
        self._years_changed()

    def _years_changed(self, *_):
        sel = sorted(y for y, cb in self.year_checks.items() if cb.isChecked())
        if self.all_years_box is not None:
            self.all_years_box.setChecked(bool(sel) and len(sel) == len(self.year_checks))
        self.year_edit.setText(", ".join(str(y) for y in sel))     # empty -> "enter a year" warning

    def _build_mapping(self, si, di, mapping):
        while self.map_grid.count():
            w = self.map_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.map_combos = {}
        for c, key in ((1, "map_src"), (3, "map_dst")):
            h = QLabel(self.tr(key))
            h.setStyleSheet("font-weight:600; background:transparent;")
            self.map_grid.addWidget(h, 0, c)
        for r, k in enumerate(core.KINDS, start=1):
            s_names = [lyr.name for lyr in si.by_kind(k)]
            d_names = [lyr.name for lyr in di.by_kind(k)]
            sc, dc = QComboBox(), QComboBox()
            sc.addItems([""] + s_names)
            dc.addItems([""] + d_names)
            if k in mapping:
                sc.setCurrentText(mapping[k][0])
                dc.setCurrentText(mapping[k][1])
                note = self.tr("map_ok")
            else:
                note = self.tr("map_missing") if not (s_names and d_names) else self.tr("map_pick")
            self.map_combos[k] = (sc, dc)
            self.map_grid.addWidget(QLabel(self._kind(k)), r, 0)
            self.map_grid.addWidget(sc, r, 1)
            self.map_grid.addWidget(QLabel("→"), r, 2)
            self.map_grid.addWidget(dc, r, 3)
            self.map_grid.addWidget(QLabel(note), r, 4)
        self.map_grid.setColumnStretch(1, 1)
        self.map_grid.setColumnStretch(3, 1)

    # ------------------------------------------------------------------ transfer
    def start(self):
        if self.busy:
            return
        v = self._validate()
        if not v:
            return
        src, dst, year = v
        if self._infos is None:
            self._pending_start = True
            self.check()                           # check / build the mapping first, then continue
            return
        mapping = self._current_mapping()
        missing = [k for k in core.KINDS if k not in mapping]
        if missing:
            self._warn(self.tr("e_map", k=", ".join(self._kind(k) for k in missing)))
            return
        self._save_state()
        src_o, dst_o = src, dst
        src, dst = self.stager.engine_path(src_o), self.stager.engine_path(dst_o)
        dst_gdb = gdbx.is_gdb(dst_o)
        self._final_path = self._final_origin = self._fidelity_text = None
        self._gdb_dst = self._gdb_final = None
        if year == "all":
            try:
                year = core.source_years(src, mapping)
            except Exception as e:                 # noqa: BLE001
                self._error("GIS_BOX", flow.message(self.tr, core.friendly_error(e)))
                return
            if not year:
                self._warn(self.tr("e_no_years"))
                return
        final = self.final_box.isChecked() or dst_gdb     # a .gdb destination is never modified in place
        auto = self.onego_box.isChecked() and len(year) > 1
        self._batch_auto = self._batch_backed_up = self._batch_stopped = False
        if final or auto:                          # one common confirmation
            fpath = (gdbx.final_gdb_path(dst_o) if dst_gdb else core.final_output_path(dst_o)) if final else None
            extra = ""
            if self.copyall_box.isChecked():
                extra += self.tr("conf_copyall", p=core.all_years_output_path(dst_o)).strip("\n") + "\n"
            if not final and self.backup_box.isChecked():
                extra += self.tr("conf_backup").strip("\n") + "\n"
            sw = core.size_warning(dst_o)
            if sw:
                extra += self.tr("size_warn", mb=sw[0], pct=sw[1])
            mode = self.tr("mode_final", p=fpath) if final else self.tr("mode_direct")
            if not self._ask(self.tr("conf_title"), self.tr(
                    "conf_batch", y=", ".join(str(y) for y in year), s=os.path.basename(src_o),
                    d=os.path.basename(dst_o), mode=mode, extra=extra)):
                return
            self._batch_auto = auto
            if dst_gdb:
                self._gdb_dst, self._gdb_final = dst_o, fpath
            elif final:
                self._final_origin = dst
                self._year_queue, self._batch_results = list(year[1:]), []
                self.status.setText(self.tr("st_copy"))
                first = year[0]
                self._run("final_copy", lambda ctx, cb: core.make_final_copy(dst, fpath),
                          lambda _r: self._on_final_ready(src, fpath, first, mapping), {"out": fpath})
                return
        self._year_queue, self._batch_results = list(year[1:]), []
        self._batch_ctx = (src, dst, mapping)
        self._launch_analysis(src, dst, year[0], mapping)

    def _on_final_ready(self, src, fpath, first_year, mapping):
        self._final_path = fpath
        self._batch_ctx = (src, fpath, mapping)
        self._launch_analysis(src, fpath, first_year, mapping)

    def _final_shown(self):
        return self._gdb_final or (self._final_path if self.final_box.isChecked() else None)

    def _launch_analysis(self, src, dst, year, mapping):
        self.summary.clear()
        self.errlog.clear()
        self._reset_table()
        self._log_path = core.default_log_path(self.stager.orig_of(dst), flow.data_dir(), year=year,
                                               src_path=self.stager.orig_of(src))
        self.status.setText(self.tr("st_analysing"))
        opts = {"backup": self.backup_box.isChecked(), "undated": self.undated_box.isChecked(),
                "copyset": self.copyset_box.isChecked(), "copyall": self.copyall_box.isChecked()}
        log_path, gdb_final = self._log_path, self._gdb_final
        self._run("analyse", lambda ctx, cb: flow.analysis(src, dst, year, mapping, log_path, self.stager, opts,
                                                           gdb_final, cb["progress"], cb["cancel"], cb["sink"]),
                  self._on_analysed, {"year": year})

    def _on_analysed(self, plan):
        self._fill_table(plan, written=False)
        todo = plan.totals()["to_insert"]
        n_undated = flow.undated_count(plan, self.undated_box.isChecked())
        o_src, o_dst = self.stager.orig_of(plan.src_path), self.stager.orig_of(plan.dst_path)
        self._undated_path = (core.undated_output_path(o_src, os.path.dirname(os.path.abspath(o_dst)))
                              if n_undated else None)
        for lp in plan.layers:
            for line in flow.issue_lines(self.tr, self.lang, lp):
                self._err(line)
        text = flow.confirm_head(self.tr, self.lang, plan, o_src, o_dst)
        if todo == 0:
            if n_undated and self._ask(self.tr("conf_title"), text + "\n" + self.tr(
                    "conf_undated_only", n=n_undated, p=self._undated_path)):
                self.status.setText(self.tr("st_undated"))
                self._launch_write(plan, False, self._undated_path, True)
                return
            flow.close_out(plan, self._log_path, "nothing to insert (analysis only)")
            self._finish(plan, written=False)
            self.status.setText(self.tr("ready"))
            self._batch_results.append((plan.year, 0))
            if self._year_queue:
                self._batch_next()
                return
            if not n_undated and len(self._batch_results) <= 1:
                self._info(text + "\n" + self.tr("conf_nothing"), self.tr("conf_title"))
            self._batch_next()
            return
        if self._gdb_final:
            text += self.tr("mode_final", p=self._gdb_final)
        else:
            text += self.tr("conf_backup") if self.backup_box.isChecked() else self.tr("conf_nobackup")
        if n_undated:
            text += "\n" + self.tr("conf_undated", n=n_undated, p=self._undated_path)
        self._copyset_path = (core.transferred_output_path(o_dst, plan.year, os.path.dirname(os.path.abspath(o_dst)))
                              if self.copyset_box.isChecked() else None)
        if self._copyset_path:
            text += "\n" + self.tr("conf_copyset", p=self._copyset_path)
        self._copyall_path = core.all_years_output_path(o_dst) if self.copyall_box.isChecked() else None
        if self._copyall_path:
            text += "\n" + self.tr("conf_copyall", p=self._copyall_path)
        text += "\n" + self.tr("conf_ask", n=todo)
        if self._batch_auto and flow.is_clean(plan):
            t = plan.totals()
            self._err("[auto] {}: {}".format(plan.year, self.tr("conf_line", k="∑", f=t["found"], u=t["duplicates"],
                                                                 n=todo, e=0).strip()))
        elif not self._ask(self.tr("conf_title"), text):
            flow.close_out(plan, self._log_path, "declined by user at confirmation (analysis only, nothing written)")
            self.status.setText(self.tr("ready"))
            self._finish(plan, written=False)
            self._batch_abort()
            return
        self.status.setText(self.tr("st_writing"))
        backup = (self.backup_box.isChecked() and not self.final_box.isChecked() and not self._gdb_final
                  and not (self._batch_auto and self._batch_backed_up))
        self._batch_backed_up = self._batch_backed_up or backup
        self._launch_write(plan, backup, self._undated_path, False)

    def _launch_write(self, plan, backup, undated_path, skip_main):
        kw = dict(gdb_dst=self._gdb_dst, gdb_final=self._gdb_final, copyall_path=self._copyall_path,
                  copyset_path=self._copyset_path, final_path=self._final_path, final_origin=self._final_origin,
                  last_year=not self._year_queue)
        log_path = self._log_path

        def work(ctx, cb):
            return flow.write(plan, log_path, backup, undated_path, skip_main, progress=cb["progress"],
                              cancel=cb["cancel"], sink=cb["sink"], status=cb["status"], **kw)
        self._run("write", work, self._on_written, {"year": plan.year, "backup": backup})

    def _on_written(self, plan):
        if plan.fidelity:
            self._fidelity_text = flow.fidelity_text(self.tr, plan.fidelity)
        self._fill_table(plan, written=True)
        self._finish(plan, written=True)
        n = plan.totals()["inserted"]
        self.status.setText(self.tr("st_done", n=n))
        self.shell.notify(self.tr("st_done", n=n))
        self._infos = None                         # the databases changed: mapping / numbers again next time
        msg = flow.done_message(self.tr, plan, self._final_shown(), self._fidelity_text)
        self._batch_results.append((plan.year, n))
        if self._year_queue:                       # several years: on to the next one, no dialog
            self._batch_next()
            return
        if len(self._batch_results) <= 1:
            self._info(msg)
            self._batch_results = []
        else:
            self._batch_next()

    def _batch_next(self):
        if self._year_queue and self._batch_ctx:
            src, dst, mapping = self._batch_ctx
            nxt = self._year_queue.pop(0)
            self._when_free(lambda: self._launch_analysis(src, dst, nxt, mapping))
            return True
        if len(self._batch_results) > 1:
            self._info("\n".join(flow.batch_lines(self.tr, self._batch_results, self._batch_stopped,
                                                  self._final_shown(), self._fidelity_text)))
        self._batch_results = []
        return False

    def _batch_abort(self):
        if self._year_queue:
            self._batch_stopped = True
        self._year_queue = []
        if len(self._batch_results) > 1 or self._batch_stopped:
            self._info("\n".join(flow.batch_lines(self.tr, self._batch_results, True)))
        self._batch_results = []
        self._batch_stopped = False

    def _finish(self, plan, written):
        lines = flow.summary_lines(self.tr, self.lang, plan, written, self._log_path, self.undated_box.isChecked())
        self.summary.setPlainText("\n".join(lines))
        if self._log_path:
            self.log_btn.setEnabled(True)
        self._save_state()

    def _on_error(self, exc):
        self._pending_start = False
        cancelled = isinstance(exc, core.TransferError) and exc.code == "cancelled"
        self.status.setText(self.tr("st_cancelled") if cancelled else self.tr("st_error"))
        if self._log_path and os.path.isfile(self._log_path):
            self.log_btn.setEnabled(True)
        text = flow.message(self.tr, exc)
        self._err(self.tr("code_cancelled") if cancelled else text)
        if cancelled:
            self._info(text)
        else:
            self._error(self.tr("st_error"), text)
        self._batch_abort()

    # ------------------------------------------------------------------ merge / log
    def merge_years(self, paths=None):
        if self.busy:
            return
        dst = self.dst_edit.text().strip()
        paths = paths if paths is not None else self._open_files(os.path.dirname(dst) if dst else "")
        paths = [os.path.normpath(x) for x in paths]
        if len(paths) < 2:
            if paths:
                self._warn(self.tr("merge_few"))
            return
        out = core.merged_output_path(paths[0])
        if not self._ask(self.tr("conf_title"), self.tr("merge_ask", n=len(paths), p=out)):
            return
        self.summary.clear()
        self.errlog.clear()
        self._log_path = core.default_log_path(out, flow.data_dir(), year="merge", src_path=paths[0])
        self.status.setText(self.tr("st_writing"))
        log_path = self._log_path
        self._run("merge", lambda ctx, cb: flow.merge(paths, out, log_path, cb["progress"], cb["cancel"], cb["sink"]),
                  self._on_merged, {"inputs": len(paths), "out": out})

    def _on_merged(self, plan):
        self.log_btn.setEnabled(True)
        if plan is None:
            self.status.setText(self.tr("ready"))
            self._info(self.tr("merge_nothing"))
            return
        lines = flow.merge_lines(self.tr, self.lang, plan, self._log_path)
        self.summary.setPlainText("\n".join(lines))
        self.status.setText(self.tr("merge_done", n=plan.totals()["inserted"]))
        self._info("\n".join(lines))

    def open_log(self):
        if self._log_path and os.path.isfile(self._log_path):
            try:
                from tools.platform_utils import open_path
                open_path(self._log_path)
            except Exception as e:                 # noqa: BLE001
                self._error("GIS_BOX", str(e))
