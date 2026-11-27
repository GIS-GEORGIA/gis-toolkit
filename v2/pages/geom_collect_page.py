"""Collect geometry → GeoPackage (PySide6).

Every matching vector file in a folder tree is read and its geometries are merged into ONE new GeoPackage with
three layers (points / lines / polygons). The output gets the collection date (``…_DDMMYY.gpkg``) and, if that file
exists, ``_2``, ``_3`` … — nothing is overwritten. Files WITHOUT a CRS are skipped unless the user explicitly ticks
“treat as the output CRS”. Logic: ``tools/geom_collect_core``; texts: the classic catalogue CTR.
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from tools import geom_collect_core as core
from v2 import workers
from v2.i18n import tr

CRS_CHOICES = [(None, None), ("UTM 37N — EPSG:32637", 32637), ("UTM 38N — EPSG:32638", 32638)]
EXTRA = {                              # "assume" / "assume_tip" come from the classic CTR (same wording in both)
    "crs_tip": {"ka": "გამომავალი კოორდინატთა სისტემა. „ავტომატური“ იყენებს პირველ ნაპოვნ CRS-ს; სხვა CRS-ის ფაილები "
                      "გადაიყვანება. CRS-ის გარეშე ფაილები — იხ. ქვემოთ მოცემული ჩამრთველი.",
                "en": "Output coordinate system. “auto” uses the first CRS found; files in another CRS are reprojected. "
                      "Files without a CRS - see the option below."},
    "skipped": {"ka": "გამოტოვებული / წაუკითხავი ფაილები:", "en": "Skipped / unreadable files:"},
}


class GeomCollectPage(QWidget):
    TOOL = "geom_collect"

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        from tools.geom_collect import CTR
        self.cat = CTR
        self.fmt_boxes = []                 # [(QCheckBox, exts)]
        self.last_out = None
        self._build()
        st = shell.settings["tool_state"].get(self.TOOL, {})
        self.src_edit.setText(st.get("source", ""))
        self.out_edit.setText(st.get("out") or os.path.join(self._desktop(), "collected_geometry.gpkg"))
        self.crs_combo.setCurrentIndex(max(0, self.crs_combo.findData(st.get("crs_epsg"))))
        exts = set(st.get("exts") or core.GEOM_EXT)
        for cb, fe in self.fmt_boxes:
            cb.setChecked(any(e in exts for e in fe))
        known = {e for _l, fe in core.VECTOR_FORMATS for e in fe}
        self.other_edit.setText(", ".join(sorted(e for e in exts if e not in known)))
        self.recursive_box.setChecked(st.get("recursive", True))
        shell.busy_changed.connect(self._set_busy)

    def _z(self, key, **f):
        d = self.cat.get(key) or EXTRA.get(key) or {}
        s = d.get(self.lang) or d.get("en") or key
        return s.format(**f) if f else s

    @staticmethod
    def _desktop():
        try:
            from tools.platform_utils import default_desktop
            return default_desktop()
        except Exception:                               # noqa: BLE001
            return os.path.expanduser("~")

    # ------------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        note = QLabel(self._z("desc"))
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)

        g = QGridLayout()
        g.addWidget(QLabel(self._z("source")), 0, 0)
        self.src_edit = QLineEdit()
        self.src_edit.setToolTip(self._z("tip_src"))
        g.addWidget(self.src_edit, 0, 1)
        self.src_btn = QPushButton(tr(self.lang, "browse"))
        self.src_btn.clicked.connect(self._pick_src)
        g.addWidget(self.src_btn, 0, 2)
        g.addWidget(QLabel(self._z("out")), 1, 0)
        self.out_edit = QLineEdit()
        self.out_edit.setToolTip(self._z("tip_out"))
        g.addWidget(self.out_edit, 1, 1)
        self.out_btn = QPushButton(tr(self.lang, "browse"))
        self.out_btn.clicked.connect(self._pick_out)
        g.addWidget(self.out_btn, 1, 2)
        g.addWidget(QLabel(self._z("crs")), 2, 0)
        self.crs_combo = QComboBox()
        self.crs_combo.setToolTip(self._z("crs_tip"))
        for label, epsg in CRS_CHOICES:
            self.crs_combo.addItem(label or self._z("crs_auto"), epsg)
        crow = QHBoxLayout()
        crow.addWidget(self.crs_combo)
        crow.addStretch(1)
        g.addLayout(crow, 2, 1, 1, 2)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)

        self.assume_box = QCheckBox(self._z("assume"))
        self.assume_box.setToolTip(self._z("assume_tip"))
        lay.addWidget(self.assume_box)

        fmt = QGroupBox(self._z("formats"))
        fv = QVBoxLayout(fmt)
        brow = QHBoxLayout()
        for key, tip, val in (("fmt_all", "tip_fmt_all", True), ("fmt_none", "tip_fmt_none", False)):
            b = QPushButton(self._z(key))
            b.setToolTip(self._z(tip))
            b.clicked.connect(lambda _c=False, v=val: self.set_all_formats(v))
            brow.addWidget(b)
        brow.addStretch(1)
        fv.addLayout(brow)
        grid = QGridLayout()
        for i, (label, exts) in enumerate(core.VECTOR_FORMATS):
            cb = QCheckBox(label)
            grid.addWidget(cb, i // 3, i % 3)
            self.fmt_boxes.append((cb, exts))
        fv.addLayout(grid)
        orow = QHBoxLayout()
        orow.addWidget(QLabel(self._z("fmt_other")))
        self.other_edit = QLineEdit()
        self.other_edit.setToolTip(self._z("tip_fmt_other"))
        self.other_edit.setMaximumWidth(320)
        orow.addWidget(self.other_edit)
        orow.addStretch(1)
        fv.addLayout(orow)
        lay.addWidget(fmt)

        arow = QHBoxLayout()
        self.recursive_box = QCheckBox(self._z("recursive"))
        self.recursive_box.setToolTip(self._z("tip_recursive"))
        arow.addWidget(self.recursive_box)
        arow.addSpacing(14)
        self.count_btn = QPushButton(self._z("btn_count"))
        self.count_btn.setToolTip(self._z("tip_count"))
        self.count_btn.clicked.connect(self.count)
        arow.addWidget(self.count_btn)
        self.run_btn = QPushButton(self._z("btn_run"))
        self.run_btn.setObjectName("primary")
        self.run_btn.setToolTip(self._z("tip_run"))
        self.run_btn.clicked.connect(self.run)
        arow.addWidget(self.run_btn)
        self.open_btn = QPushButton(self._z("btn_open"))
        self.open_btn.setToolTip(self._z("tip_open"))
        self.open_btn.clicked.connect(self.open_out)
        arow.addWidget(self.open_btn)
        arow.addStretch(1)
        lay.addLayout(arow)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        lay.addWidget(self.log_view, 1)

    def _set_busy(self, busy):
        for w in (self.run_btn, self.count_btn, self.src_btn, self.out_btn):
            w.setEnabled(not busy)

    # ------------------------------------------------------------------ helpers (dialogs patched in tests)
    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    def set_all_formats(self, value):
        for cb, _e in self.fmt_boxes:
            cb.setChecked(value)

    def selected_exts(self):
        out = []
        for cb, exts in self.fmt_boxes:
            if cb.isChecked():
                out += [e for e in exts if e not in out]
        out += [e for e in core.normalize_exts(self.other_edit.text()) if e not in out]
        return tuple(out)

    def _pick_src(self):
        d = QFileDialog.getExistingDirectory(self, self._z("source"), self.src_edit.text())
        if d:
            self.src_edit.setText(os.path.normpath(d))

    def _pick_out(self):
        p = QFileDialog.getSaveFileName(self, self._z("out"), self.out_edit.text(), "GeoPackage (*.gpkg)",
                                        options=QFileDialog.Option.DontConfirmOverwrite)[0]
        if p:                                           # no overwrite question: the real name is dated / unique
            self.out_edit.setText(os.path.normpath(p))

    def open_out(self):
        d = os.path.dirname(self.last_out or self.out_edit.text().strip())
        if not d or not os.path.isdir(d):
            return self.shell.notify(self._z("warn_out"), "error")
        try:
            from tools.platform_utils import open_path
            open_path(d)
        except Exception as e:                          # noqa: BLE001
            self.shell.notify(str(e), "error")

    def _validate(self):
        source = self.src_edit.text().strip()
        out = self.out_edit.text().strip()
        if not source or not os.path.isdir(source):
            self.shell.notify(self._z("warn_source"), "error")
            return None
        if not out:
            self.shell.notify(self._z("warn_out"), "error")
            return None
        if not out.lower().endswith(".gpkg"):
            out += ".gpkg"
            self.out_edit.setText(out)
        exts = self.selected_exts()
        if not exts:
            self.shell.notify(self._z("warn_fmt"), "error")
            return None
        return source, out, self.crs_combo.currentData(), exts

    def _remember(self, source, out, epsg, exts):
        self.shell.settings["tool_state"][self.TOOL] = {
            "source": source, "out": out, "crs_epsg": epsg, "exts": list(exts),
            "recursive": self.recursive_box.isChecked()}
        self.shell.settings.save()

    # ------------------------------------------------------------------ actions
    def count(self):
        v = self._validate()
        if not v:
            return
        n = len(core.iter_geometry_files(v[0], v[3], self.recursive_box.isChecked()))
        msg = self._z("count_n" if n else "count_none", n=n)
        self._log(msg)
        self.shell.notify(msg)

    def run(self):
        v = self._validate()
        if not v:
            return
        source, base_out, epsg, exts = v
        out = core.unique_output_path(core.dated_output_path(base_out))
        files = core.iter_geometry_files(source, exts, self.recursive_box.isChecked())
        if not files:
            return self.shell.notify(self._z("count_none"))
        if not self._confirm(self._z("confirm_m", n=len(files), out=out)):
            return
        self._remember(source, base_out, epsg, exts)
        assume = self.assume_box.isChecked()
        self._log(self._z("start", n=len(files)))

        def work(ctx):
            res = core.collect_to_geopackage(files, out, target_epsg=epsg, log=ctx.log,
                                             progress=lambda i, n: ctx.progress(i, n, self._z("progress", i=i, n=n)),
                                             cancel=ctx.cancelled, assume_missing_crs=assume)
            if res.get("cancelled"):
                raise workers.Cancelled()
            return res

        self.shell.run(work, self.TOOL, inputs=[source], params={"files": len(files), "out": out, "epsg": epsg,
                                                                 "assume_missing_crs": assume},
                       on_done=self._done, on_log=self._log)

    def _done(self, res):
        if res.get("errors"):
            self._log(self._z("skipped"))
            for path, note in res["errors"]:
                self._log("  ✗ {} — {}".format(os.path.basename(path), str(note).splitlines()[0]))
        if not res.get("out_files"):
            self._log(self._z("done_empty"))
            return self.shell.notify(self._z("done_empty"))
        self.last_out = res["out_path"]
        msg = self._z("done", p=res["points"], l=res["lines"], g=res["polygons"], ok=res["files_ok"],
                      sk=res["files_skipped"], out=res["out_path"])
        self._log(msg)
        self.shell.notify(msg)
