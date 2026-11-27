"""Parcel search (PySide6): cadastral codes in a File Geodatabase layer → Shapefile / GeoPackage + not-found list.

Plus the “shapefile analysis across folders” section of the classic tool. Logic: ``tools/search_core`` (search,
results written under a free name — nothing is overwritten), ``tools/shp_analysis_core`` + ``report_lines``;
texts: the classic catalogues PTR / ATR.
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
                               QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from tools import search_core
from tools import shp_analysis_core as an_core
from tools.regions import layer_code, layer_display
from v2 import workers
from v2.i18n import plain, tr


def _defaults():
    from tools import parcel_search as classic           # texts + config.txt defaults (no Tk window)
    return classic


class ParcelSearchPage(QWidget):
    TOOL = "parcel_search"

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        c = _defaults()
        self.PTR = c.PTR
        from tools.shp_analysis import ATR
        self.ATR = ATR
        self.default_field = c.DEFAULT_FIELD
        st = shell.settings["tool_state"].get(self.TOOL, {})
        self.databases = list(st.get("databases") or c.DEFAULT_GDBS or ([c.DEFAULT_GDB] if c.DEFAULT_GDB else []))
        self.last_not_found = []
        self._build()
        self.gdb_combo.setEditText(st.get("gdb") or c.DEFAULT_GDB or (self.databases[0] if self.databases else ""))
        self._want_layer = st.get("layer") or c.DEFAULT_LAYER
        self._want_field = st.get("field") or c.DEFAULT_FIELD
        self.layer_combo.addItem(layer_display(self._want_layer))
        self.field_combo.addItem(self._want_field)
        self.codes_edit.setPlainText(st.get("codes", ""))
        self.out_edit.setText(st.get("out") or os.path.join(self._desktop(), "found_parcels.shp"))
        self.shp_box.setChecked(st.get("shp", True))
        self.gpkg_box.setChecked(st.get("gpkg", True))
        self.an_root.setText(st.get("an_root", ""))
        self.an_top.setValue(int(st.get("an_top", 5) or 5))
        shell.busy_changed.connect(self._set_busy)
        self._auto_read_done = False

    def showEvent(self, event):                            # noqa: N802 (Qt API)
        """Like the classic tool: on the first display, read the real layer / field lists of the database
        (only when nothing else is running)."""
        super().showEvent(event)
        if not self._auto_read_done and getattr(self.shell, "task", None) is None:
            self._auto_read_done = True
            if self._gdb() and os.path.exists(self._gdb()):
                self.read_layers(silent=True)

    # ------------------------------------------------------------------ texts / state
    def _p(self, key, **f):
        d = self.PTR.get(key, {})
        s = plain(d.get(self.lang) or d.get("en") or key)       # the shared strings carry emoji (💾, 🗑, 🔍)
        return s.format(**f) if f else s

    def _a(self, key, **f):
        d = self.ATR.get(key, {})
        s = d.get(self.lang) or d.get("en") or key
        return s.format(**f) if f else s

    @staticmethod
    def _desktop():
        try:
            from tools.platform_utils import default_desktop
            return default_desktop()
        except Exception:                               # noqa: BLE001
            return os.path.expanduser("~")

    def _remember(self):
        self.shell.settings["tool_state"][self.TOOL] = {
            "gdb": self.gdb_combo.currentText().strip(), "layer": layer_code(self.layer_combo.currentText()),
            "field": self.field_combo.currentText(), "databases": self.databases,
            "codes": self.codes_edit.toPlainText().strip()[:200000], "out": self.out_edit.text().strip(),
            "shp": self.shp_box.isChecked(), "gpkg": self.gpkg_box.isChecked(),
            "an_root": self.an_root.text().strip(), "an_top": self.an_top.value()}
        self.shell.settings.save()

    # ------------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        db = QGroupBox(self._p("sec_db"))
        g = QGridLayout(db)
        g.addWidget(QLabel(self._p("lbl_gdb")), 0, 0)
        self.gdb_combo = QComboBox()
        self.gdb_combo.setEditable(True)
        self.gdb_combo.addItems(self.databases)
        self.gdb_combo.activated.connect(lambda _i: self.read_layers(silent=True))
        g.addWidget(self.gdb_combo, 0, 1, 1, 3)
        b = QPushButton(tr(self.lang, "browse"))
        b.setToolTip(self._p("tip_browse_gdb"))
        b.clicked.connect(self._browse_gdb)
        g.addWidget(b, 0, 4)
        g.addWidget(QLabel(self._p("lbl_layer")), 1, 0)
        self.layer_combo = QComboBox()
        self.layer_combo.setToolTip(self._p("tip_layer"))
        self.layer_combo.setMinimumWidth(220)
        self.layer_combo.activated.connect(lambda _i: self.read_fields())
        g.addWidget(self.layer_combo, 1, 1)
        g.addWidget(QLabel(self._p("lbl_field")), 1, 2)
        self.field_combo = QComboBox()
        self.field_combo.setToolTip(self._p("tip_field"))
        self.field_combo.setMinimumWidth(160)
        g.addWidget(self.field_combo, 1, 3)
        row = QHBoxLayout()
        self.read_btn = QPushButton(self._p("btn_read_layers"))
        self.read_btn.setToolTip(self._p("tip_read_layers"))
        self.read_btn.clicked.connect(lambda: self.read_layers(silent=False))
        row.addWidget(self.read_btn)
        keep = QPushButton(self._p("btn_remember"))
        keep.setToolTip(self._p("tip_remember"))
        keep.clicked.connect(self.remember_db)
        row.addWidget(keep)
        rm = QPushButton(self._p("btn_db_remove"))
        rm.setToolTip(self._p("tip_db_remove"))
        rm.clicked.connect(self.remove_db)
        row.addWidget(rm)
        row.addStretch(1)
        g.addLayout(row, 2, 1, 1, 4)
        g.setColumnStretch(1, 1)
        lay.addWidget(db)

        codes = QGroupBox(self._p("sec_codes"))
        cv = QVBoxLayout(codes)
        crow = QHBoxLayout()
        crow.addWidget(QLabel(self._p("lbl_enter")))
        crow.addStretch(1)
        clr = QPushButton(self._p("btn_clear"))
        clr.clicked.connect(lambda: self.codes_edit.clear())
        crow.addWidget(clr)
        ld = QPushButton(self._p("btn_load"))
        ld.setToolTip(self._p("tip_load"))
        ld.clicked.connect(self.load_file)
        crow.addWidget(ld)
        cv.addLayout(crow)
        self.codes_edit = QPlainTextEdit()
        self.codes_edit.setMinimumHeight(80)
        cv.addWidget(self.codes_edit)

        out = QGroupBox(self._p("sec_out"))
        og = QGridLayout(out)
        self.out_edit = QLineEdit()
        og.addWidget(self.out_edit, 0, 0, 1, 3)
        ob = QPushButton(tr(self.lang, "browse"))
        ob.clicked.connect(self._browse_out)
        og.addWidget(ob, 0, 3)
        og.addWidget(QLabel(self._p("out_create")), 1, 0)
        self.shp_box = QCheckBox(self._p("chk_shp"))
        self.shp_box.setToolTip(self._p("tip_shp"))
        self.gpkg_box = QCheckBox(self._p("chk_gpkg"))
        self.gpkg_box.setToolTip(self._p("tip_gpkg"))
        og.addWidget(self.shp_box, 1, 1)
        og.addWidget(self.gpkg_box, 1, 2)
        og.setColumnStretch(2, 1)
        srow = QHBoxLayout()
        self.search_btn = QPushButton(self._p("btn_search"))
        self.search_btn.setObjectName("primary")
        self.search_btn.setToolTip(self._p("tip_search"))
        self.search_btn.clicked.connect(self.search)
        srow.addWidget(self.search_btn)
        nf = QPushButton(self._p("btn_save_nf"))
        nf.setToolTip(self._p("tip_save_nf"))
        nf.clicked.connect(self.save_not_found)
        srow.addWidget(nf)
        srow.addStretch(1)
        og.addLayout(srow, 2, 0, 1, 4)

        an = QGroupBox(self._a("title"))
        ag = QGridLayout(an)
        an.setToolTip(self._a("desc"))
        ag.addWidget(QLabel(self._a("root")), 1, 0)
        self.an_root = QLineEdit()
        self.an_root.setToolTip(self._a("tip_root"))
        ag.addWidget(self.an_root, 1, 1)
        ab = QPushButton(tr(self.lang, "browse"))
        ab.clicked.connect(self._browse_an)
        ag.addWidget(ab, 1, 2)
        arow = QHBoxLayout()
        self.an_btn = QPushButton(self._a("btn_run"))
        self.an_btn.clicked.connect(self.analyse)
        arow.addWidget(self.an_btn)
        arow.addSpacing(12)
        arow.addWidget(QLabel(self._a("top")))
        self.an_top = QSpinBox()
        self.an_top.setRange(1, 50)
        self.an_top.setToolTip(self._a("tip_top"))
        arow.addWidget(self.an_top)
        arow.addStretch(1)
        ag.addLayout(arow, 2, 0, 1, 4)
        ag.setColumnStretch(1, 1)

        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(codes, 1)
        tv.addWidget(out)
        tv.addWidget(an)
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(top)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        split.addWidget(self.log_view)
        split.setSizes([430, 160])
        lay.addWidget(split, 1)

    def _set_busy(self, busy):
        for w in (self.search_btn, self.an_btn, self.read_btn):
            w.setEnabled(not busy)

    # ------------------------------------------------------------------ dialogs (patched in tests)
    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _pick_item(self, title, label, items):
        item, ok = QInputDialog.getItem(self, title, label, items, 0, False)
        return item if ok else None

    def _open_name(self, title, filt):
        return QFileDialog.getOpenFileName(self, title, "", filt)[0]

    def _save_name(self, title, start, filt):
        return QFileDialog.getSaveFileName(self, title, start, filt)[0]

    def _dir_name(self, title, start):
        return QFileDialog.getExistingDirectory(self, title, start)

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    def _error(self, msg):
        self._log("✗ " + msg)
        self.shell.notify(msg, "error")

    # ------------------------------------------------------------------ database
    def _gdb(self):
        return self.gdb_combo.currentText().strip()

    def _browse_gdb(self):
        p = self._dir_name(self._p("pick_gdb"), self._gdb())
        if p:
            self.gdb_combo.setEditText(os.path.normpath(p))
            self.read_layers(silent=False)

    def _gdb_problem(self, gdb):
        """Error text when the path is missing or is a folder that only CONTAINS .gdb databases."""
        if not os.path.exists(gdb):
            return self._p("err_gdb")
        p = gdb.rstrip("/\\")
        if os.path.isdir(p) and not p.lower().endswith(".gdb"):
            kids = sorted(n for n in os.listdir(p) if n.lower().endswith(".gdb") and os.path.isdir(os.path.join(p, n)))
            if kids:
                return self._p("err_gdb_folder", name=os.path.basename(p) or p, n=len(kids), list=", ".join(kids),
                               first=kids[0])
        return None

    def read_layers(self, silent=False):
        gdb = self._gdb()
        problem = self._gdb_problem(gdb) if gdb else self._p("err_gdb")
        if problem:
            return None if silent else self._error(problem)
        want_layer = layer_code(self.layer_combo.currentText()) or self._want_layer
        want_field = self.field_combo.currentText() or self._want_field
        default_field = self.default_field

        def work(ctx):
            import pyogrio
            from tools.fields import pick_code_field
            layers = [r[0] for r in pyogrio.list_layers(gdb)]
            if not layers:
                return {"layers": []}
            layer = want_layer if want_layer in layers else layers[0]
            fields = list(pyogrio.read_info(gdb, layer=layer)["fields"])
            return {"layers": layers, "layer": layer, "fields": fields,
                    "field": pick_code_field(fields, want_field, default_field)}

        def done(res):
            if not res["layers"]:
                return None if silent else self.shell.notify(self._p("no_layers"), "error")
            self.layer_combo.clear()
            self.layer_combo.addItems([layer_display(n) for n in res["layers"]])
            self.layer_combo.setCurrentText(layer_display(res["layer"]))
            self._set_fields(res["fields"], res["field"])
            self._log(self._p("log_layers", layers=", ".join(layer_display(n) for n in res["layers"])))

        self.shell.run(work, "parcel_search_layers", inputs=[gdb], on_done=done, on_log=self._log)

    def read_fields(self):
        gdb, layer = self._gdb(), layer_code(self.layer_combo.currentText())
        if not gdb or not layer:
            return
        want, default_field = self.field_combo.currentText(), self.default_field

        def work(ctx):
            import pyogrio
            from tools.fields import pick_code_field
            fields = list(pyogrio.read_info(gdb, layer=layer)["fields"])
            return fields, pick_code_field(fields, want, default_field)

        self.shell.run(work, "parcel_search_fields", inputs=[gdb], on_done=lambda r: self._set_fields(*r),
                       on_log=self._log)

    def _set_fields(self, fields, chosen):
        self.field_combo.clear()
        self.field_combo.addItems(fields)
        self.field_combo.setCurrentText(chosen)

    def remember_db(self):
        gdb = self._gdb()
        if gdb and gdb not in self.databases:
            self.databases.append(gdb)
            self.gdb_combo.addItem(gdb)
        self._remember()
        self.shell.notify(self._p("cfg_saved"))

    def remove_db(self):
        gdb = self._gdb()
        if gdb not in self.databases or not self._confirm("{}\n\n{}".format(self._p("db_remove_q"), gdb)):
            return
        self.databases.remove(gdb)
        self.gdb_combo.removeItem(self.gdb_combo.findText(gdb))
        self.gdb_combo.setEditText(self.databases[0] if self.databases else "")
        self._remember()

    # ------------------------------------------------------------------ codes / output
    def load_file(self):
        path = self._open_name(self._p("pick_file"), "{} (*.csv *.xlsx *.xls);;{} (*.*)".format(
            self._p("ft_tables"), self._p("ft_all")))
        if not path:
            return
        try:
            import pandas as pd
            if path.lower().endswith((".xlsx", ".xls")):
                df = pd.read_excel(path, dtype=str)
            else:
                df = pd.read_csv(path, dtype=str, sep=None, engine="python")
        except Exception as e:                          # noqa: BLE001
            return self._error(self._p("file_read_err", e=e))
        col = self._pick_item(self._p("pick_col_title"), self._p("pick_col_q"), [str(c) for c in df.columns])
        if not col:
            return
        codes = [search_core.normalize(v) for v in df[col].tolist() if search_core.normalize(v)]
        self.codes_edit.setPlainText("\n".join(codes))
        self._log(self._p("log_loaded", n=len(codes), col=col))

    def _browse_out(self):
        p = self._save_name(self._p("out_file_title"), self.out_edit.text(), "Shapefile (*.shp);;GeoPackage (*.gpkg)")
        if p:
            self.out_edit.setText(os.path.normpath(p))

    # ------------------------------------------------------------------ search
    def search(self):
        gdb = self._gdb()
        problem = self._gdb_problem(gdb) if gdb else self._p("err_gdb")
        if problem:
            return self._error(problem)
        layer, field = layer_code(self.layer_combo.currentText().strip()), self.field_combo.currentText().strip()
        if not (layer and field):
            return self._error(self._p("err_layer_field"))
        formats = [f for f, box in (("shp", self.shp_box), ("gpkg", self.gpkg_box)) if box.isChecked()]
        out = self.out_edit.text().strip()
        if formats and not out:
            return self._error(self._p("err_out"))
        codes = search_core.parse_manual_codes(self.codes_edit.toPlainText())
        if not codes:
            return self._error(self._p("err_codes_empty"))
        self._remember()
        self.log_view.clear()

        def work(ctx):
            box = {}
            search_core.run_search(gdb, layer, field, codes, out, ctx.log, box.update, self._p, formats,
                                   progress=lambda i, n: ctx.progress(i, n, self._p("progress", i=i, n=n)),
                                   cancel=ctx.cancelled)
            if box.get("cancelled"):
                raise workers.Cancelled()
            if "error" in box:
                raise RuntimeError(box["error"].split("\n")[0])
            if box.get("not_found") and box.get("out_path"):
                box["nf_file"] = search_core.write_not_found(box["out_path"], box["not_found"])
            return box

        self.shell.run(work, self.TOOL, inputs=[gdb], params={"layer": layer, "field": field, "codes": len(codes),
                                                              "formats": formats},
                       on_done=self._done, on_log=self._log)

    def _done(self, r):
        found, nf = r["found_list"], r["not_found"]
        self.last_not_found = nf
        lines = ["", "=" * 50, self._p("sum_total", n=len(r["requested"])), self._p("sum_found", n=len(found)),
                 self._p("sum_nf", n=len(nf))]
        if r.get("search_only"):
            lines.append(self._p("sum_search_only"))
        else:
            lines.append(self._p("sum_written", n=r["written"]))
            lines += [self._p("sum_file", p=fp) for fp in r.get("out_files", [])]
        lines.append("=" * 50)
        if nf:
            lines += ["", self._p("nf_list_hdr")] + ["  ✗ " + c for c in nf]
        if r.get("nf_file"):
            lines.append(self._p("nf_saved", p=r["nf_file"]))
        for ln in lines:
            self._log(ln)
        self.shell.notify(self._p("done_status", f=len(found), nf=len(nf)))

    def save_not_found(self):
        if not self.last_not_found:
            return self.shell.notify(self._p("no_nf"))
        p = self._save_name(self._p("save_nf_title"), "", "{} (*.txt);;CSV (*.csv)".format(self._p("ft_txt")))
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:              # the user picked this name (dialog confirms overwrite)
            f.write("\n".join(self.last_not_found))
        self.shell.notify(self._p("saved_n", n=len(self.last_not_found)))

    # ------------------------------------------------------------------ shapefile analysis
    def _browse_an(self):
        p = self._dir_name(self._a("root"), self.an_root.text())
        if p:
            self.an_root.setText(os.path.normpath(p))

    def analyse(self):
        root = self.an_root.text().strip()
        if not root or not os.path.isdir(root):
            return self._error(self._a("err_root"))
        top_n = self.an_top.value()
        self._remember()
        self.log_view.clear()

        def work(ctx):
            paths = an_core.scan_shapefiles(root)
            rows = []
            for i, p in enumerate(paths, start=1):
                ctx.check_cancelled()
                rows.append(an_core.analyze_layer(p))
                ctx.progress(i, len(paths), self._a("status_progress", i=i, n=len(paths)))
            return rows

        def done(rows):
            if not rows:
                self._log("— " + self._a("none_found"))
                return self.shell.notify(self._a("none_found"))
            from tools.shp_analysis import report_lines
            for ln in report_lines(root, rows, top_n, self.lang):
                self._log(ln)
            self.shell.notify(self._a("status_done", n=len(rows)))

        self.shell.run(work, "shp_analysis", inputs=[root], params={"top": top_n}, on_done=done, on_log=self._log)
