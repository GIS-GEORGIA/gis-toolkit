"""DWG/DXF → SHP / GPKG / GDB (PySide6).

One file or every .dxf/.dwg in a folder tree is converted with GDAL (DWG through the bundled LibreDWG, ezdxf rescue
for DXF entities GDAL cannot read). Every output gets a free name (``name``, ``name_2`` …) — an earlier result is
never deleted. A drawing WITHOUT a CRS (normal for DXF/DWG) is labelled with the selected CRS only when the user
ticks that option; otherwise it is written without a CRS. Logic: ``tools/dwg_convert_core``; texts: classic DWT.
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from tools import dwg_convert_core as core
from v2 import workers
from v2.i18n import tr

CRS_CHOICES = [(None, None), ("UTM 37N — EPSG:32637", 32637), ("UTM 38N — EPSG:32638", 32638)]
EXTRA = {
    "assume": {"ka": "CRS-ის გარეშე ნახაზებს მიენიჭოს არჩეული CRS (კოორდინატები არ გადაიყვანება)",
               "en": "Label drawings without a CRS with the selected CRS (coordinates are not transformed)"},
    "assume_tip": {"ka": "DXF/DWG-ს ჩვეულებრივ CRS არ აქვს. ჩართე მხოლოდ მაშინ, თუ იცი, რომ ნახაზი არჩეულ სისტემაშია "
                         "(მაგ. UTM 38N). გამორთულზე ასეთი ფაილი CRS-ის გარეშე ჩაიწერება — არაფერი იკარგება.",
                   "en": "DXF/DWG usually have no CRS. Enable only if you know the drawing is in the selected system "
                         "(e.g. UTM 38N). When off, such a file is written without a CRS - nothing is lost."},
    "no_overwrite": {"ka": "არსებულ შედეგს არაფერი ეცვლება — ახალი იწერება თავისუფალი სახელით (_2, _3 …).",
                     "en": "Existing results are never replaced - new ones get a free name (_2, _3 …)."},
}


class DwgConvertPage(QWidget):
    TOOL = "dwg_convert"

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        from tools.dwg_convert import DWT
        self.cat = DWT
        self._build()
        st = shell.settings["tool_state"].get(self.TOOL, {})
        self.src_edit.setText(st.get("source", ""))
        self.out_edit.setText(st.get("out") or os.path.join(self._desktop(), "converted"))
        self.recursive_box.setChecked(st.get("recursive", True))
        self.fmt_buttons.get(st.get("format", "gpkg"), self.fmt_buttons["gpkg"]).setChecked(True)
        self.crs_combo.setCurrentIndex(max(0, self.crs_combo.findData(st.get("crs_epsg"))))
        self.assume_box.setChecked(bool(st.get("assume_missing_crs", False)))
        self._sync_assume()
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
        g.addWidget(self.src_edit, 0, 1)
        sb = QHBoxLayout()
        self.file_btn = QPushButton(self._z("pick_file"))
        self.file_btn.setToolTip(self._z("tip_pick_file"))
        self.file_btn.clicked.connect(self._pick_file)
        self.folder_btn = QPushButton(self._z("pick_folder"))
        self.folder_btn.setToolTip(self._z("tip_pick_folder"))
        self.folder_btn.clicked.connect(self._pick_folder)
        sb.addWidget(self.file_btn)
        sb.addWidget(self.folder_btn)
        g.addLayout(sb, 0, 2)
        self.recursive_box = QCheckBox(self._z("recursive"))
        self.recursive_box.setToolTip(self._z("tip_recursive"))
        g.addWidget(self.recursive_box, 1, 1)
        g.addWidget(QLabel(self._z("out")), 2, 0)
        self.out_edit = QLineEdit()
        self.out_edit.setToolTip(self._z("tip_out"))
        g.addWidget(self.out_edit, 2, 1)
        self.out_btn = QPushButton(tr(self.lang, "browse"))
        self.out_btn.clicked.connect(self._pick_out)
        g.addWidget(self.out_btn, 2, 2)

        g.addWidget(QLabel(self._z("format")), 3, 0)
        frow = QHBoxLayout()
        self.fmt_group = QButtonGroup(self)
        self.fmt_buttons = {}
        for key in ("shp", "gpkg", "gdb"):
            rb = QRadioButton(self._z("fmt_" + key))
            rb.setToolTip(self._z("tip_fmt"))
            self.fmt_group.addButton(rb)
            self.fmt_buttons[key] = rb
            frow.addWidget(rb)
        frow.addStretch(1)
        g.addLayout(frow, 3, 1, 1, 2)

        g.addWidget(QLabel(self._z("crs")), 4, 0)
        self.crs_combo = QComboBox()
        self.crs_combo.setToolTip(self._z("tip_crs"))
        for label, epsg in CRS_CHOICES:
            self.crs_combo.addItem(label or self._z("crs_native"), epsg)
        self.crs_combo.currentIndexChanged.connect(self._sync_assume)
        crow = QHBoxLayout()
        crow.addWidget(self.crs_combo)
        crow.addStretch(1)
        g.addLayout(crow, 4, 1, 1, 2)
        self.assume_box = QCheckBox(self._z("assume"))
        self.assume_box.setToolTip(self._z("assume_tip"))
        g.addWidget(self.assume_box, 5, 1, 1, 2)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)

        hint = QLabel(self._z("no_overwrite"))
        hint.setObjectName("muted")
        lay.addWidget(hint)

        arow = QHBoxLayout()
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

    def _sync_assume(self, *_):
        on = self.crs_combo.currentData() is not None       # only meaningful with a selected CRS
        self.assume_box.setEnabled(on)

    def _set_busy(self, busy):
        for w in (self.run_btn, self.count_btn, self.file_btn, self.folder_btn, self.out_btn):
            w.setEnabled(not busy)

    # ------------------------------------------------------------------ helpers (dialogs patched in tests)
    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _warn(self, text):
        QMessageBox.warning(self, "GIS_BOX", text)

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    def _fmt(self):
        return next(k for k, rb in self.fmt_buttons.items() if rb.isChecked())

    def _pick_file(self):
        p = QFileDialog.getOpenFileName(self, self._z("source"), os.path.dirname(self.src_edit.text()),
                                        "DXF/DWG (*.dxf *.dwg);;All files (*.*)")[0]
        if p:
            self.src_edit.setText(os.path.normpath(p))

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, self._z("source"), self.src_edit.text())
        if d:
            self.src_edit.setText(os.path.normpath(d))

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, self._z("out"), self.out_edit.text())
        if d:
            self.out_edit.setText(os.path.normpath(d))

    def open_out(self):
        d = self.out_edit.text().strip()
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
        if not source or not (os.path.isfile(source) or os.path.isdir(source)):
            self.shell.notify(self._z("warn_source"), "error")
            return None
        if not out:
            self.shell.notify(self._z("warn_out"), "error")
            return None
        return source, out, self._fmt(), self.crs_combo.currentData()

    def _files_for(self, source):
        if os.path.isfile(source):
            return [source]
        return list(core.iter_source_files(source, self.recursive_box.isChecked()))

    # ------------------------------------------------------------------ actions
    def count(self):
        v = self._validate()
        if not v:
            return
        n = len(self._files_for(v[0]))
        msg = self._z("count_n" if n else "count_none", n=n)
        self._log(msg)
        self.shell.notify(msg)

    def run(self):
        v = self._validate()
        if not v:
            return
        source, out, fmt, epsg = v
        files = self._files_for(source)
        if not files:
            return self.shell.notify(self._z("count_none"))
        if not self._confirm(self._z("confirm_m", n=len(files), fmt=self._z("fmt_" + fmt), out=out)):
            return
        assume = bool(epsg) and self.assume_box.isChecked()
        self.shell.settings["tool_state"][self.TOOL] = {
            "source": source, "out": out, "format": fmt, "crs_epsg": epsg, "assume_missing_crs": assume,
            "recursive": self.recursive_box.isChecked()}
        self.shell.settings.save()
        self._log(self._z("start", n=len(files)))

        def work(ctx):
            res = core.convert_batch(files, out, fmt, target_epsg=epsg, log=ctx.log,
                                     progress=lambda i, n: ctx.progress(i, n, self._z("progress", i=i, n=n)),
                                     cancel=ctx.cancelled, assume_missing_crs=assume)
            if res.get("cancelled"):
                raise workers.Cancelled()
            res["out"] = out
            return res

        self.shell.run(work, self.TOOL, inputs=[source], params={"files": len(files), "format": fmt, "epsg": epsg,
                                                                 "assume_missing_crs": assume, "out": out},
                       on_done=self._done, on_log=self._log)

    def _done(self, res):
        msg = self._z("done", ok=res["files_ok"], empty=res["files_empty"], sk=res["files_skipped"], out=res["out"])
        self._log(msg)
        self.shell.notify(msg, "error" if res["files_skipped"] and not res["files_ok"] else "info")
        by_reason = {}
        for r in res.get("results", []):
            if r.get("reason"):
                by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1
        for reason, n in by_reason.items():
            if reason in ("dwg_old_driver", "dwg_no_tool", "dwg_gdal_dxf_gap"):
                hint = self._z("hint_" + reason.split("_", 1)[1], n=n)
                self._log("⚠ " + hint)
                self._warn(hint)
