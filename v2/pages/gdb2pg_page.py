"""GDB / MDB -> PostGIS (PySide6): load Geodatabase layers into PostgreSQL/PostGIS with GDAL ogr2ogr.

Engine: ``tools/gdb2postgis_core`` (shared with the classic tool and the scheduled headless run). Differences from the
classic window, all on the safe side:

* "overwrite" (and the first load of an incremental sync) REPLACES an existing PostGIS table. Before an import the
  page checks which target tables already exist and asks, naming them.
* Turning the schedule on (in-app timer or a Windows Task Scheduler task) asks first; the Windows task is a
  persistent system entry, so it is never registered silently.
* The password is entered masked, is never put on the command line or in a log (the core passes it through
  ``PGPASSWORD`` and masks it), and is stored only when "remember password" is ticked.

"Remember settings" writes the same place as the classic tool (``gis_box_settings.json`` -> tool_config.gdb2postgis),
because the scheduled background run reads it from there. Every GDAL / database call runs as a background task.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from tools import gdb2postgis_cli as cli
from tools import gdb2postgis_core as core
from v2 import workers

EXTRA = {
    "ow_confirm": {"ka": "რეჟიმი „{mode}“ არსებულ ცხრილს თავიდან ქმნის — მისი ახლანდელი შიგთავსი ჩანაცვლდება.\n\n"
                         "ჩანაცვლდება ({n}):\n{tables}\n\nბაზა: {db}\n\nგავაგრძელო?",
                   "en": "Mode \"{mode}\" recreates an existing table - its current content is replaced.\n\n"
                         "Will be replaced ({n}):\n{tables}\n\nDatabase: {db}\n\nContinue?"},
    "import_confirm": {"ka": "{n} შრე აიტანება ბაზაში {db} (რეჟიმი: {mode}). გავაგრძელო?",
                       "en": "{n} layer(s) will be imported into {db} (mode: {mode}). Continue?"},
    "sched_confirm": {"ka": "ყოველ {every} {unit}-ში ავტომატურად აიტანება {n} შრე ბაზაში {db} (რეჟიმი: {mode}), "
                            "კითხვის გარეშე.{bg}\n\nჩავრთო?",
                      "en": "Every {every} {unit}, {n} layer(s) will be imported into {db} automatically (mode: "
                            "{mode}), without asking.{bg}\n\nTurn it on?"},
    "sched_bg_note": {"ka": "\n\nამისთვის Windows-ში დარეგისტრირდება დავალება „{task}“ (მუშაობს GIS_BOX-ის "
                            "დახურვის შემდეგაც). განრიგის გამორთვა მას წაშლის.",
                      "en": "\n\nA Windows task \"{task}\" is registered for this (it runs even when GIS_BOX is closed). "
                            "Turning the schedule off removes it."},
    "checking": {"ka": "მოწმდება სამიზნე ცხრილები…", "en": "Checking target tables…"},
    "loading_layers": {"ka": "შრეები იკითხება…", "en": "Reading layers…"},
    "testing": {"ka": "კავშირი მოწმდება…", "en": "Testing the connection…"},
    "err": {"ka": "შეცდომა", "en": "Error"},
    "shared_note": {"ka": "„დამახსოვრება“ იმავე ადგილას ინახავს, რასაც კლასიკური ხელსაწყო და განრიგით გაშვება კითხულობს.",
                    "en": "\"Remember\" saves to the same place the classic tool and the scheduled run read."},
    "no_overwrite_needed": {"ka": "არსებული ცხრილი არ ჩანაცვლდება.", "en": "No existing table is replaced."},
    "cancelled_after": {"ka": "გაუქმდა: {n} შრიდან დამუშავდა {done} (OK {ok}, ჩავარდა {fail}); "
                              "დანარჩენი შრეები არ დამუშავებულა.",
                        "en": "Cancelled: {done} of {n} layer(s) processed (OK {ok}, failed {fail}); "
                              "the remaining layers were not touched."},
}
UNITS = ("minutes", "hours", "days")


class Gdb2PgPage(QWidget):
    TOOL = "gdb2pg"

    def __init__(self, shell, settings_path=None):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        from tools.gdb2postgis import CATALOG
        self.cat = CATALOG
        self.settings_path = settings_path          # tests: a temporary classic settings file
        self._sources = {}
        self._layer_names = []
        self._sched_timer = QTimer(self)
        self._sched_timer.setSingleShot(True)
        self._sched_timer.timeout.connect(self._sched_tick)
        self._gdal_checked = False
        cfg = cli.load_cfg(settings_path)
        self._saved_source = cfg.get("source", "")
        self._saved_layers = cfg.get("layers", [])
        self._build(cfg)
        self._toggle_incr()
        shell.busy_changed.connect(self._set_busy)
        if self.dir_edit.text():
            self._scan_sources()
        if self.sched_box.isChecked():              # schedule from a previous session (already confirmed then)
            QTimer.singleShot(0, self, lambda: self.apply_schedule(confirm=False))

    def _z(self, key, **f):
        from tools.i18n import translate
        d = EXTRA.get(key)
        if d:
            s = d.get(self.lang) or d.get("en")
            return s.format(**f) if f else s
        return translate(self.cat, key, self.lang, **f)

    # ------------------------------------------------------------------ UI
    def _build(self, cfg):
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

        desc = QLabel(self._z("desc"))
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        g = QGridLayout()
        g.addWidget(QLabel(self._z("gdal")), 0, 0)
        self.ogr_edit = QLineEdit(cfg.get("ogr2ogr", ""))
        self.ogr_edit.editingFinished.connect(self.refresh_gdal)
        g.addWidget(self.ogr_edit, 0, 1)
        g.addWidget(self._btn("browse", self._pick_ogr, "tip_browse_ogr"), 0, 2)
        self.gdal_status = QLabel("")
        self.gdal_status.setObjectName("muted")
        g.addWidget(self.gdal_status, 1, 1, 1, 2)
        g.addWidget(QLabel(self._z("source_dir")), 2, 0)
        self.dir_edit = QLineEdit(cfg.get("source_dir", ""))
        self.dir_edit.editingFinished.connect(self._scan_sources)
        g.addWidget(self.dir_edit, 2, 1)
        g.addWidget(self._btn("browse", self._pick_dir, "tip_browse_dir"), 2, 2)
        g.addWidget(QLabel(self._z("source")), 3, 0)
        self.source_combo = QComboBox()
        self.source_combo.setToolTip(self._z("tip_source"))
        self.source_combo.activated.connect(lambda _i: self.load_layers())
        g.addWidget(self.source_combo, 3, 1, 1, 2)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)

        lay.addWidget(QLabel(self._z("layers")))
        self.layers_list = QListWidget()
        self.layers_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.layers_list.setToolTip(self._z("tip_layers"))
        self.layers_list.setMinimumHeight(130)
        lay.addWidget(self.layers_list)
        sr = QHBoxLayout()
        sr.addWidget(self._btn("sel_all", self.layers_list.selectAll, "tip_sel_all"))
        sr.addWidget(self._btn("sel_none", self.layers_list.clearSelection, "tip_sel_none"))
        sr.addStretch(1)
        lay.addLayout(sr)

        conn = QGroupBox(self._z("conn"))
        cg = QGridLayout(conn)
        self.host_edit = QLineEdit(cfg.get("host", "localhost"))
        self.port_edit = QLineEdit(str(cfg.get("port", "5432")))
        self.db_edit = QLineEdit(cfg.get("dbname", "postgis"))
        self.schema_edit = QLineEdit(cfg.get("schema", "public"))
        self.user_edit = QLineEdit(cfg.get("user", "postgres"))
        self.pw_edit = QLineEdit(cfg.get("password", ""))
        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        for (key, w), (r, c) in zip((("host", self.host_edit), ("port", self.port_edit), ("dbname", self.db_edit),
                                     ("schema", self.schema_edit), ("user", self.user_edit),
                                     ("password", self.pw_edit)),
                                    ((0, 0), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2))):
            cg.addWidget(QLabel(self._z(key)), r, c)
            cg.addWidget(w, r, c + 1)
        self.remember_pw = QCheckBox(self._z("remember_pw"))
        self.remember_pw.setToolTip(self._z("tip_remember_pw"))
        self.remember_pw.setChecked(bool(cfg.get("password")))
        cg.addWidget(self.remember_pw, 3, 0, 1, 2)
        self.test_btn = self._btn("test_conn", self.test_connection, "tip_test")
        cg.addWidget(self.test_btn, 3, 3)
        cg.setColumnStretch(1, 1)
        cg.setColumnStretch(3, 1)
        lay.addWidget(conn)

        opts = QGroupBox(self._z("opts"))
        og = QGridLayout(opts)
        og.addWidget(QLabel(self._z("mode")), 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["overwrite", "append", "update"])
        self.mode_combo.setCurrentText(cfg.get("mode", "overwrite"))
        self.mode_combo.setToolTip(self._z("tip_mode"))
        og.addWidget(self.mode_combo, 0, 1)
        og.addWidget(QLabel(self._z("reproj")), 0, 2)
        self.tsrs_edit = QLineEdit(cfg.get("t_srs", ""))
        og.addWidget(self.tsrs_edit, 0, 3)
        og.addWidget(QLabel(self._z("prefix")), 1, 0)
        self.prefix_edit = QLineEdit(cfg.get("prefix", ""))
        og.addWidget(self.prefix_edit, 1, 1)
        self.promote_box = self._check("promote", "tip_promote", cfg.get("promote", True))
        self.gist_box = self._check("gist", "tip_gist", cfg.get("gist", True))
        self.copy_box = self._check("copy", "tip_copy", cfg.get("copy", True))
        for i, b in enumerate((self.promote_box, self.gist_box, self.copy_box)):
            og.addWidget(b, 2, i)
        lay.addWidget(opts)

        incr = QGroupBox(self._z("incr_group"))
        ig = QGridLayout(incr)
        self.incr_box = self._check("incr_enable", "tip_incr", cfg.get("incremental", False))
        self.incr_box.toggled.connect(self._toggle_incr)
        ig.addWidget(self.incr_box, 0, 0, 1, 2)
        self.deletes_box = self._check("detect_deletes", "tip_deletes", cfg.get("detect_deletes", False))
        ig.addWidget(self.deletes_box, 0, 2, 1, 2)
        ig.addWidget(QLabel(self._z("key_field")), 1, 0)
        self.key_edit = QLineEdit(cfg.get("key_field", ""))
        self.key_edit.setToolTip(self._z("tip_key"))
        ig.addWidget(self.key_edit, 1, 1)
        ig.addWidget(QLabel(self._z("track_field")), 1, 2)
        self.track_edit = QLineEdit(cfg.get("track_field", ""))
        self.track_edit.setToolTip(self._z("tip_track"))
        ig.addWidget(self.track_edit, 1, 3)
        self.auto_btn = self._btn("auto_fields", self.auto_fields, "tip_auto")
        ig.addWidget(self.auto_btn, 2, 0, 1, 2)
        hint = QLabel(self._z("incr_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        ig.addWidget(hint, 3, 0, 1, 4)
        lay.addWidget(incr)

        sched = QGroupBox(self._z("sched_group"))
        sg = QGridLayout(sched)
        self.sched_box = self._check("sched_enable", "tip_sched", cfg.get("sched_on", False))
        self.sched_box.clicked.connect(lambda _c=False: self.apply_schedule())
        sg.addWidget(self.sched_box, 0, 0)
        self.every_spin = QSpinBox()
        self.every_spin.setRange(1, 9999)
        try:
            self.every_spin.setValue(int(cfg.get("sched_every", 1)))
        except (TypeError, ValueError):
            self.every_spin.setValue(1)
        sg.addWidget(self.every_spin, 0, 1)
        self.unit_combo = QComboBox()
        for u in UNITS:
            self.unit_combo.addItem(self._z("unit_" + {"minutes": "min", "hours": "hour", "days": "day"}[u]), u)
        self.unit_combo.setCurrentIndex(max(0, self.unit_combo.findData(cfg.get("sched_unit", "minutes"))))
        sg.addWidget(self.unit_combo, 0, 2)
        sg.addWidget(self._btn("sched_apply", self.apply_schedule, "tip_apply"), 0, 3)
        self.bg_box = self._check("bg_enable", "tip_bg", cfg.get("sched_bg", False))
        self.bg_box.setEnabled(sys.platform == "win32")
        sg.addWidget(self.bg_box, 1, 0, 1, 4)
        self.next_run = QLabel(self._z("sched_off"))
        self.next_run.setStyleSheet("font-weight:600; background:transparent;")
        sg.addWidget(self.next_run, 2, 0, 1, 4)
        sh = QLabel(self._z("sched_hint"))
        sh.setObjectName("muted")
        sh.setWordWrap(True)
        sg.addWidget(sh, 3, 0, 1, 4)
        sg.setColumnStretch(4, 1)
        lay.addWidget(sched)

        act = QHBoxLayout()
        self.import_btn = self._btn("import", self.start_import, "tip_import")
        self.import_btn.setObjectName("primary")
        act.addWidget(self.import_btn)
        act.addWidget(self._btn("remember", self.remember, "tip_remember"))
        act.addWidget(self._btn("history", self.open_history, "tip_history"))
        act.addStretch(1)
        lay.addLayout(act)
        note = QLabel(self._z("shared_note"))
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(200)
        lay.addWidget(self.log_view, 1)

    def _btn(self, key, slot, tip=None):
        b = QPushButton(self._z(key))
        b.clicked.connect(lambda _c=False: slot())
        if tip:
            b.setToolTip(self._z(tip))
        return b

    def _check(self, key, tip, checked):
        b = QCheckBox(self._z(key))
        b.setToolTip(self._z(tip))
        b.setChecked(bool(checked))
        return b

    def showEvent(self, event):
        super().showEvent(event)
        if not self._gdal_checked:
            self._gdal_checked = True
            self.refresh_gdal()

    def _set_busy(self, busy):
        for b in (self.import_btn, self.test_btn, self.auto_btn):
            b.setEnabled(not busy)
        if not busy:
            self._toggle_incr()

    def _toggle_incr(self, *_):
        on = self.incr_box.isChecked()
        for w in (self.key_edit, self.track_edit, self.auto_btn, self.deletes_box):
            w.setEnabled(on)

    # ------------------------------------------------------------------ dialogs (patched in tests)
    def _ask(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _info(self, text):
        QMessageBox.information(self, "GIS_BOX", text)

    def _warn(self, text):
        QMessageBox.warning(self, "GIS_BOX", text)

    def _error(self, text):
        QMessageBox.critical(self, self._z("err"), text)

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    # ------------------------------------------------------------------ GDAL / sources / layers
    def tools(self):
        override = self.ogr_edit.text().strip() or None
        return core.find_tool("ogr2ogr", override), core.find_tool("ogrinfo", override)

    def refresh_gdal(self):
        ogr2ogr, _ = self.tools()
        self.gdal_status.setText(self._z("gdal_ok", v=core.gdal_version(ogr2ogr)) if ogr2ogr
                                 else self._z("gdal_missing"))

    def _pick_ogr(self):
        p = QFileDialog.getOpenFileName(self, "ogr2ogr", "", "ogr2ogr (ogr2ogr*);;All (*.*)")[0]
        if p:
            self.ogr_edit.setText(os.path.normpath(p))
            self.refresh_gdal()

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, self._z("source_dir"), self.dir_edit.text())
        if d:
            self.dir_edit.setText(os.path.normpath(d))
            self._scan_sources()

    def _scan_sources(self):
        d = self.dir_edit.text().strip()
        if not d or not os.path.isdir(d):
            return
        try:
            srcs = core.list_sources(d)
        except Exception:                          # noqa: BLE001
            srcs = []
        self._sources = {os.path.basename(s): s for s in srcs}
        self.source_combo.clear()
        self.source_combo.addItems(list(self._sources))
        if self._sources:
            want = self._saved_source if self._saved_source in self._sources else next(iter(self._sources))
            self.source_combo.setCurrentText(want)
            self.load_layers()
        else:
            self.layers_list.clear()
            self._layer_names = []
            self._log("— " + self._z("no_sources"))

    def _source(self):
        return self._sources.get(self.source_combo.currentText())

    def load_layers(self):
        src = self._source()
        _, ogrinfo = self.tools()
        self.layers_list.clear()
        self._layer_names = []
        if not src or not ogrinfo:
            return
        if self.shell.task is not None:
            QTimer.singleShot(200, self, self.load_layers)
            return
        self._log("— " + self._z("loading_layers"))
        self.shell.run(lambda ctx: core.list_layers(ogrinfo, src), "gdb2pg.layers", inputs=[src],
                       on_done=lambda layers: self._fill_layers(src, layers), owner=self)

    def _fill_layers(self, src, layers):
        if src != self._source():
            return
        self.layers_list.clear()
        self._layer_names = []
        for li in layers:
            self.layers_list.addItem(li.name + (f"  ({li.geom_type})" if li.geom_type else ""))
            self._layer_names.append(li.name)
        if self.source_combo.currentText() == self._saved_source and self._saved_layers:
            for i, name in enumerate(self._layer_names):
                if name in self._saved_layers:
                    self.layers_list.item(i).setSelected(True)

    def selected_layers(self):
        rows = sorted(self.layers_list.row(it) for it in self.layers_list.selectedItems())
        return [self._layer_names[r] for r in rows if r < len(self._layer_names)]

    # ------------------------------------------------------------------ connection / options
    def pg(self):
        try:
            port = int(self.port_edit.text().strip() or "5432")
        except ValueError:
            port = 5432
        return core.PgConfig(host=self.host_edit.text().strip(), port=port, dbname=self.db_edit.text().strip(),
                             user=self.user_edit.text().strip(), password=self.pw_edit.text(),
                             schema=self.schema_edit.text().strip() or "public")

    def _db_label(self):
        pg = self.pg()
        return f"{pg.host}:{pg.port}/{pg.dbname} ({pg.schema})"

    def opts(self):
        return core.ImportOptions(
            mode=self.mode_combo.currentText(), t_srs=self.tsrs_edit.text().strip(),
            prefix=self.prefix_edit.text().strip(), promote_to_multi=self.promote_box.isChecked(),
            spatial_index=self.gist_box.isChecked(), use_copy=self.copy_box.isChecked(),
            incremental=self.incr_box.isChecked(), key_field=self.key_edit.text().strip(),
            track_field=self.track_edit.text().strip(), detect_deletes=self.deletes_box.isChecked())

    def _mode_label(self):
        return "incremental" if self.incr_box.isChecked() else self.mode_combo.currentText()

    def test_connection(self):
        _, ogrinfo = self.tools()
        if not ogrinfo:
            return self._warn(self._z("warn_gdal"))
        pg = self.pg()
        self._log("— " + self._z("testing"))
        self.shell.run(lambda ctx: core.test_pg_connection(ogrinfo, pg), "gdb2pg.test",
                       params={"db": self._db_label()}, on_done=self._tested)

    def _tested(self, res):
        ok, msg = res
        if ok:
            self._log("— " + self._z("conn_ok"))
            self._info(self._z("conn_ok"))
        else:
            self._log("— {} {}".format(self._z("conn_fail"), msg))
            self._error(f"{self._z('conn_fail')}\n{msg}")

    def auto_fields(self):
        src = self._source()
        _, ogrinfo = self.tools()
        layers = self.selected_layers()
        if not (src and ogrinfo) or len(layers) != 1:
            return self._warn(self._z("auto_need_one"))
        self.shell.run(lambda ctx: [f.name for f in core.list_fields(ogrinfo, src, layers[0])], "gdb2pg.fields",
                       on_done=self._fields_detected)

    def _fields_detected(self, names):
        key, track = core.auto_detect_key(names), core.auto_detect_track(names)
        self.key_edit.setText(key)
        self.track_edit.setText(track)
        self._log("— " + self._z("auto_done", k=key or "?", t=track or "?"))

    # ------------------------------------------------------------------ persistence (shared with classic)
    def config(self):
        data = {
            "ogr2ogr": self.ogr_edit.text().strip(), "source_dir": self.dir_edit.text().strip(),
            "host": self.host_edit.text().strip(), "port": self.port_edit.text().strip(),
            "dbname": self.db_edit.text().strip(), "user": self.user_edit.text().strip(),
            "schema": self.schema_edit.text().strip(), "mode": self.mode_combo.currentText(),
            "t_srs": self.tsrs_edit.text().strip(), "prefix": self.prefix_edit.text().strip(),
            "promote": self.promote_box.isChecked(), "gist": self.gist_box.isChecked(),
            "copy": self.copy_box.isChecked(), "incremental": self.incr_box.isChecked(),
            "key_field": self.key_edit.text().strip(), "track_field": self.track_edit.text().strip(),
            "detect_deletes": self.deletes_box.isChecked(), "sched_on": self.sched_box.isChecked(),
            "sched_every": str(self.every_spin.value()), "sched_unit": self.unit_combo.currentData(),
            "sched_bg": self.bg_box.isChecked(), "source": self.source_combo.currentText(),
            "layers": self.selected_layers()}
        if self.remember_pw.isChecked():           # the password only when ticked
            data["password"] = self.pw_edit.text()
        return data

    def persist(self):
        data = self.config()
        cli.save_cfg(data, self.settings_path)
        self._saved_source, self._saved_layers = data["source"], data["layers"]

    def remember(self):
        try:
            self.persist()
        except (OSError, ValueError) as e:
            return self._error(str(e))
        self._log("— " + self._z("saved"))
        self.shell.notify(self._z("saved"))

    # ------------------------------------------------------------------ import
    def _check_inputs(self):
        ogr2ogr, ogrinfo = self.tools()
        if not (ogr2ogr and ogrinfo):
            self._warn(self._z("warn_gdal"))
            return None
        src = self._source()
        if not src:
            self._warn(self._z("warn_source"))
            return None
        layers = self.selected_layers()
        if not layers:
            self._warn(self._z("warn_layers"))
            return None
        return ogr2ogr, ogrinfo, src, layers

    def start_import(self, scheduled=False):
        if self.shell.task is not None:
            return False
        v = self._check_inputs()
        if not v:
            return False
        ogr2ogr, ogrinfo, src, layers = v
        pg, opt = self.pg(), self.opts()
        if scheduled:                               # confirmed when the schedule was turned on
            self._run_import(ogr2ogr, ogrinfo, src, layers, pg, opt)
            return True
        replaces = opt.incremental or opt.mode == "overwrite"
        if not replaces:
            if self._ask(self._z("import_confirm", n=len(layers), db=self._db_label(), mode=self._mode_label())):
                self._run_import(ogr2ogr, ogrinfo, src, layers, pg, opt)
            return True
        self._log("— " + self._z("checking"))

        def check(ctx):
            ok, msg = core.test_pg_connection(ogrinfo, pg)
            if not ok:                             # without a connection "no table exists" would be a guess
                return False, msg
            if opt.incremental:                    # only a layer without a watermark is fully (re)loaded
                from tools.gdb2postgis_state import SyncState
                st = SyncState()
                layers_full = [lyr for lyr in layers if not st.get(src, lyr).watermark]
            else:
                layers_full = layers
            tables = [((opt.prefix + lyr) if opt.prefix else lyr) for lyr in layers_full]
            return True, [t for t in tables if core._pg_table_exists(ogrinfo, pg, t)]

        def checked(res):
            ok, existing = res
            if not ok:
                self._log("— {} {}".format(self._z("conn_fail"), existing))
                return self._error(f"{self._z('conn_fail')}\n{existing}")
            if existing:
                text = self._z("ow_confirm", mode=self._mode_label(), n=len(existing), db=self._db_label(),
                               tables="\n".join(f"  {pg.schema}.{t.lower()}" for t in existing))
            else:
                text = (self._z("import_confirm", n=len(layers), db=self._db_label(), mode=self._mode_label())
                        + "\n" + self._z("no_overwrite_needed"))
            if self._ask(text):
                QTimer.singleShot(0, self, lambda: self._when_free(
                    lambda: self._run_import(ogr2ogr, ogrinfo, src, layers, pg, opt)))
        self.shell.run(check, "gdb2pg.check", params={"db": self._db_label(), "layers": len(layers)},
                       on_done=checked, owner=self)
        return True

    def _when_free(self, fn):
        # Every QTimer.singleShot in this page passes `self` as context: Qt drops the call if the page is deleted first.
        if self.shell.task is not None:
            QTimer.singleShot(50, self, lambda: self._when_free(fn))
        else:
            fn()

    def _run_import(self, ogr2ogr, ogrinfo, src, layers, pg, opt):
        from tools.gdb2postgis_audit import AuditStore
        from tools.gdb2postgis_state import SyncState
        self._log("— " + self._z("running"))

        def work(ctx):
            def log_cb(level, message):            # the core masks the password; it is never on the command line
                ctx.log(f"{level}: {message}")
            res = core.run_import(ogr2ogr, src, layers, pg, opt, log_cb, should_cancel=ctx.cancelled,
                                  ogrinfo_path=ogrinfo, state=SyncState(), audit=AuditStore(), profile="")
            if res.cancelled:      # stopped between layers: say so (not "Done") and show what was finished
                ctx.log("— " + self._z("cancelled_after", n=len(layers), done=len(res.results),
                                       ok=res.ok_count, fail=res.fail_count))
                raise workers.Cancelled()
            return res
        self.shell.run(work, "gdb2pg.import", inputs=[src],
                       params={"layers": len(layers), "db": self._db_label(), "mode": self._mode_label()},
                       on_done=self._imported, on_log=self._log)

    def _imported(self, res):
        msg = self._z("done", ok=res.ok_count, fail=res.fail_count)
        self._log("— " + msg)
        self.shell.notify(msg, "error" if res.fail_count else "info")

    # ------------------------------------------------------------------ schedule
    def _interval_ms(self):
        return self.every_spin.value() * {"minutes": 60_000, "hours": 3_600_000,
                                          "days": 86_400_000}[self.unit_combo.currentData()]

    def _sc_mo(self):
        return {"minutes": "MINUTE", "hours": "HOURLY", "days": "DAILY"}[self.unit_combo.currentData()], \
            self.every_spin.value()

    def apply_schedule(self, confirm=True):
        from tools import gdb2postgis as classic
        self._sched_timer.stop()
        want_bg = self.bg_box.isChecked() and sys.platform == "win32"
        if not self.sched_box.isChecked():
            if sys.platform == "win32":
                classic.unregister_task()
            self.next_run.setText(self._z("sched_off"))
            return False
        if confirm:
            if not self._check_inputs():
                self.sched_box.setChecked(False)
                return False
            text = self._z("sched_confirm", every=self.every_spin.value(), unit=self.unit_combo.currentText(),
                           n=len(self.selected_layers()), db=self._db_label(), mode=self._mode_label(),
                           bg=self._z("sched_bg_note", task=classic.TASK_NAME) if want_bg else "")
            if not self._ask(text):
                self.sched_box.setChecked(False)
                self.next_run.setText(self._z("sched_off"))
                return False
        if want_bg:
            try:
                self.persist()                      # the Windows task reads the saved settings
            except (OSError, ValueError) as e:
                self._error(str(e))
                return False
            sc, mo = self._sc_mo()
            ok, msg = classic.register_task(sc, mo)
            if not ok:
                self._error(f"{self._z('bg_fail')}\n{msg}")
                self.next_run.setText(self._z("sched_off"))
                return False
            if not (self.remember_pw.isChecked() and self.pw_edit.text()):
                self._log("— " + self._z("bg_no_pw"))
            self.next_run.setText(self._z("bg_registered"))
            self._log("— " + self._z("bg_registered"))
        else:
            if sys.platform == "win32":
                classic.unregister_task()
            self._schedule_next(self._interval_ms())
        return True

    def _schedule_next(self, ms):
        nxt = datetime.now() + timedelta(milliseconds=ms)
        self.next_run.setText(self._z("next_run", t=nxt.strftime("%Y-%m-%d %H:%M:%S")))
        self._sched_timer.start(ms)

    def _sched_tick(self):
        if not self.sched_box.isChecked():
            return
        if self.shell.task is None and self._source() and self.selected_layers():
            self._log(self._z("sched_fire"))
            self.start_import(scheduled=True)
        else:
            self._log("— " + self._z("sched_skip"))
        self._schedule_next(self._interval_ms())

    # ------------------------------------------------------------------ history
    def open_history(self, audit=None):
        from tools.gdb2postgis_audit import AuditStore
        dlg = HistoryDialog(self, audit or AuditStore())
        dlg.show()
        self._history = dlg
        return dlg


class HistoryDialog(QDialog):
    """Past runs by date -> feature IDs; delete those features from PostGIS (confirmed) or the history record."""

    COLS = (("time", "col_time"), ("layer", "col_layer"), ("mode", "col_mode"), ("aff", "col_aff"),
            ("del", "col_del"), ("ok", "col_ok"), ("table", "col_table"))

    def __init__(self, page, audit):
        super().__init__(page)
        self.page, self.audit = page, audit
        z = page._z
        self.setWindowTitle(z("hist_title"))
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(z("hist_date")))
        self.date_combo = QComboBox()
        top.addWidget(self.date_combo)
        top.addStretch(1)
        lay.addLayout(top)
        self.empty = QLabel(z("hist_none"))
        lay.addWidget(self.empty)
        self.runs = QTableWidget(0, len(self.COLS))
        self.runs.setHorizontalHeaderLabels([z(k) for _c, k in self.COLS])
        self.ids = QTableWidget(0, 2)
        self.ids.setHorizontalHeaderLabels(["key", "action"])
        for t in (self.runs, self.ids):
            t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            t.verticalHeader().setVisible(False)
            t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        lay.addWidget(self.runs, 1)
        lay.addWidget(QLabel(z("hist_ids")))
        lay.addWidget(self.ids, 1)
        br = QHBoxLayout()
        self.del_feats_btn = QPushButton(z("hist_del_feats"))
        self.del_feats_btn.clicked.connect(self.delete_features)
        self.del_rec_btn = QPushButton(z("hist_del_rec"))
        self.del_rec_btn.clicked.connect(self.delete_record)
        br.addWidget(self.del_feats_btn)
        br.addWidget(self.del_rec_btn)
        br.addStretch(1)
        lay.addLayout(br)
        self._rows = []
        dates = audit.dates()
        self.date_combo.addItems(dates)
        self.empty.setVisible(not dates)
        for w in (self.runs, self.ids, self.del_feats_btn, self.del_rec_btn, self.date_combo):
            w.setEnabled(bool(dates))
        self.date_combo.currentIndexChanged.connect(lambda _i: self.load_runs())
        self.runs.itemSelectionChanged.connect(self.load_ids)
        if dates:
            self.load_runs()

    def load_runs(self):
        self.runs.setRowCount(0)
        self.ids.setRowCount(0)
        self._rows = list(self.audit.runs_on(self.date_combo.currentText()))
        for r in self._rows:
            i = self.runs.rowCount()
            self.runs.insertRow(i)
            for c, v in enumerate((r["ts"][11:19], r["layer"], r["mode"], r["affected"], r["deleted"],
                                   "✓" if r["ok"] else "✗", r["target_table"])):
                self.runs.setItem(i, c, QTableWidgetItem(str(v)))

    def selected_run(self):
        rows = self.runs.selectionModel().selectedRows()
        return self._rows[rows[0].row()] if rows else None

    def load_ids(self):
        self.ids.setRowCount(0)
        r = self.selected_run()
        if not r:
            return
        for kv, act in self.audit.id_rows(r["id"]):
            i = self.ids.rowCount()
            self.ids.insertRow(i)
            self.ids.setItem(i, 0, QTableWidgetItem(str(kv)))
            self.ids.setItem(i, 1, QTableWidgetItem(str(act)))

    def delete_features(self):
        p, z = self.page, self.page._z
        r = self.selected_run()
        if not r:
            return p._warn(z("hist_pick_run"))
        ids = self.audit.ids(r["id"], "upsert")
        key = r["key_field"]
        if not (key and ids):
            return p._info(z("hist_no_key"))
        table = r["target_table"]
        if not p._ask(z("hist_del_feats_q", n=len(ids), t=f"{r['schema']}.{table}")):
            return
        _, ogrinfo = p.tools()
        if not ogrinfo:
            return p._warn(z("warn_gdal"))
        pg = p.pg()

        def done(res):
            n, msg = res
            if msg and n == 0:
                p._error(msg)
            else:
                p._log("— " + z("hist_deleted", n=n))
                p._info(z("hist_deleted", n=n))
        p.shell.run(lambda ctx: core.delete_features(ogrinfo, pg, r["schema"], table, key, ids),
                    "gdb2pg.delete_features", params={"table": table, "n": len(ids)}, on_done=done,
                    owner=p)

    def delete_record(self):
        r = self.selected_run()
        if not r:
            return self.page._warn(self.page._z("hist_pick_run"))
        self.audit.delete_run(r["id"])
        self.load_runs()
