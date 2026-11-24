"""CRS Manager page (PySide6): detect, assign (with confirmation) or reproject into a NEW file."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from tools import crs_manager as cm
from v2.i18n import tr

FILE_FILTER = ("Geodata (*.shp *.gpkg *.geojson *.json *.tif *.tiff *.gdb *.kml *.dxf);;All files (*.*)")
PRESETS = [("UTM 37N — EPSG:32637", 32637), ("UTM 38N — EPSG:32638", 32638), ("WGS 84 — EPSG:4326", 4326)]


class CrsPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        self.detection = None
        self._build()
        shell.busy_changed.connect(self._set_busy)

    # ------------------------------------------------------------------ UI
    def _t(self, key, **f):
        return tr(self.lang, key, **f)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        row.addWidget(QLabel(self._t("crs_file")))
        self.file_edit = QLineEdit()
        row.addWidget(self.file_edit, 1)
        self.browse_btn = QPushButton(self._t("browse"))
        self.browse_btn.clicked.connect(self._browse)
        row.addWidget(self.browse_btn)
        self.detect_btn = QPushButton(self._t("crs_detect"))
        self.detect_btn.setObjectName("primary")
        self.detect_btn.clicked.connect(self.detect)
        row.addWidget(self.detect_btn)
        lay.addLayout(row)

        lay.addWidget(self._label(self._t("crs_info"), "title2"))
        self.info = QTableWidget(0, 2)
        self.info.horizontalHeader().setVisible(False)
        self.info.verticalHeader().setVisible(False)
        self.info.horizontalHeader().setStretchLastSection(True)
        self.info.setColumnWidth(0, 150)
        self.info.setMaximumHeight(210)
        self.info.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.info)

        self.warn = QLabel("")
        self.warn.setObjectName("warn")
        self.warn.setWordWrap(True)
        lay.addWidget(self.warn)

        self.sugg_row = QWidget()
        sr = QHBoxLayout(self.sugg_row)
        sr.setContentsMargins(0, 0, 0, 0)
        self.sugg_label = QLabel(self._t("crs_suggest"))
        self.sugg_label.setObjectName("muted")
        self.sugg_box = QComboBox()
        self.sugg_use = QPushButton(self._t("crs_use_candidate"))
        self.sugg_use.clicked.connect(self._use_candidate)
        sr.addWidget(self.sugg_label)
        sr.addWidget(self.sugg_box, 1)
        sr.addWidget(self.sugg_use)
        self.sugg_row.setVisible(False)
        lay.addWidget(self.sugg_row)

        grid = QGridLayout()
        grid.addWidget(QLabel(self._t("crs_target")), 0, 0)
        self.target_box = QComboBox()
        for label, epsg in PRESETS:
            self.target_box.addItem(label, epsg)
        grid.addWidget(self.target_box, 0, 1)
        grid.addWidget(QLabel(self._t("crs_custom")), 0, 2)
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("32637")
        self.custom_edit.setMaximumWidth(110)
        grid.addWidget(self.custom_edit, 0, 3)
        grid.addWidget(QLabel(self._t("crs_output")), 1, 0)
        self.out_edit = QLineEdit()
        grid.addWidget(self.out_edit, 1, 1, 1, 2)
        self.out_btn = QPushButton(self._t("browse"))
        self.out_btn.clicked.connect(self._browse_out)
        grid.addWidget(self.out_btn, 1, 3)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        btns = QHBoxLayout()
        self.reproject_btn = QPushButton(self._t("crs_reproject"))
        self.reproject_btn.setObjectName("primary")
        self.reproject_btn.clicked.connect(self.reproject)
        self.assign_btn = QPushButton(self._t("crs_assign"))
        self.assign_btn.clicked.connect(self.assign)
        btns.addWidget(self.reproject_btn)
        btns.addWidget(self.assign_btn)
        btns.addStretch(1)
        lay.addLayout(btns)

        lay.addWidget(self._label(self._t("crs_report"), "title2"))
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        lay.addWidget(self.report, 1)

    @staticmethod
    def _label(text, kind):
        lb = QLabel(text)
        lb.setStyleSheet("font-weight:600; background:transparent;")
        return lb

    def _set_busy(self, busy):
        for b in (self.detect_btn, self.reproject_btn, self.assign_btn, self.browse_btn, self.out_btn):
            b.setEnabled(not busy)

    # ------------------------------------------------------------------ helpers
    def set_file(self, path):
        self.file_edit.setText(path)
        self._suggest_output()

    def _suggest_output(self):
        src = self.file_edit.text().strip()
        if src and not self.out_edit.text().strip():
            stem = os.path.splitext(os.path.basename(src))[0]
            self.out_edit.setText(os.path.join(os.path.dirname(src), stem + "_crs.gpkg"))

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, self._t("crs_file"), "", FILE_FILTER)
        if path:
            self.set_file(path)

    def _browse_out(self):
        path, _ = QFileDialog.getSaveFileName(self, self._t("crs_output"), self.out_edit.text(),
                                              "GeoPackage (*.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson)")
        if path:
            self.out_edit.setText(path)

    def _target(self):
        """Selected target EPSG (custom field wins) or None."""
        txt = self.custom_edit.text().strip().upper().replace("EPSG:", "")
        if txt:
            try:
                cm.as_crs(int(txt))
                return int(txt)
            except (ValueError, cm.CrsError):
                return None
        return self.target_box.currentData()

    def _use_candidate(self):
        epsg = self.sugg_box.currentData()
        if epsg:
            self.custom_edit.setText(str(epsg))

    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _check_inputs(self, need_target=True):
        src = self.file_edit.text().strip()
        if not src or not os.path.exists(src):
            self.shell.notify(self._t("crs_need_file"), "error")
            return None
        if need_target and self._target() is None:
            self.shell.notify(self._t("crs_need_target"), "error")
            return None
        self._suggest_output()
        out = self.out_edit.text().strip()
        if need_target and not out:
            self.shell.notify(self._t("crs_need_out"), "error")
            return None
        return src, out

    # ------------------------------------------------------------------ actions
    def detect(self):
        got = self._check_inputs(need_target=False)
        if not got:
            return
        src = got[0]
        self.shell.settings.add_recent_file(src)
        self.shell.run(lambda ctx: cm.detect(src), "crs_manager.detect", inputs=[src],
                       on_done=self._show_detection, success_msg=None)

    def _show_detection(self, det):
        self.detection = det
        i = det.info
        rows = [("crs_name", i.name), ("crs_epsg", i.epsg if i.epsg else "-"), ("crs_kind", i.kind),
                ("crs_datum", i.datum or "-"), ("crs_unit", i.unit or "-"), ("crs_proj", i.projection or "-"),
                ("crs_bounds", ", ".join("{:.4f}".format(x) for x in det.bounds) if det.bounds else "-")]
        self.info.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.info.setItem(r, 0, QTableWidgetItem(self._t(k)))
            self.info.setItem(r, 1, QTableWidgetItem(str(v)))
        warns = list(det.warnings)
        if not det.has_crs:
            warns.insert(0, self._t("crs_missing"))
        self.warn.setText("\n".join("⚠ " + w for w in warns))
        self.sugg_box.clear()
        for c in det.suggestions:
            self.sugg_box.addItem("EPSG:{} — {} ({})".format(c["epsg"], c["name"], c["reason"]), c["epsg"])
        self.sugg_row.setVisible(bool(det.suggestions))

    def reproject(self):
        got = self._check_inputs()
        if not got:
            return
        src, out = got
        epsg = self._target()
        self.shell.run(lambda ctx: cm.reproject_file(src, out, epsg), "crs_manager.reproject",
                       inputs=[src], params={"target": epsg}, on_done=self._show_report,
                       success_msg=self._t("done"))

    def assign(self):
        got = self._check_inputs()
        if not got:
            return
        src, out = got
        epsg = self._target()
        if not self._confirm(self._t("crs_assign_confirm", src=src, crs="EPSG:{}".format(epsg))):
            return                                               # nothing is ever assigned without a yes
        self.shell.run(lambda ctx: cm.assign_file(src, out, epsg, confirmed=True), "crs_manager.assign",
                       inputs=[src], params={"target": epsg}, on_done=self._show_report,
                       success_msg=self._t("done"))

    def _show_report(self, rep):
        self.report.setPlainText(rep.to_text())
