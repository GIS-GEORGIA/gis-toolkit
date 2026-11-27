"""Line buffers (PySide6): gas-pipeline protection zones from a line shapefile.

Same behaviour as the classic tool: buffers are built in EPSG:32637/32638 only (a layer in another CRS is
converted only after the user agrees, the source file is never changed), each buffer is a separate new shapefile
``<name>_<N>.shp``, lines are merged first so every buffer is one dissolved polygon. Logic: ``tools/line_buffer_core``.
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from tools import line_buffer_core as core
from v2 import workers
from v2.i18n import tr


class LineBufferPage(QWidget):
    TOOL = "line_buffer"

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        self.shp_map = {}
        self.zone_boxes = {}
        self._build()
        st = shell.settings["tool_state"].get(self.TOOL, {})
        self.folder_edit.setText(st.get("folder", ""))
        self.out_edit.setText(st.get("out", ""))
        if st.get("type") in core.BUFFER_TYPES:
            self.type_box.setCurrentIndex(self.type_box.findData(st["type"]))
        self._fill_zones()
        if self.folder_edit.text():
            self.scan()
        shell.busy_changed.connect(self._set_busy)

    def _t(self, k, **f):
        return tr(self.lang, k, **f)

    # ------------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        grid.addWidget(QLabel(self._t("lb_folder")), 0, 0)
        self.folder_edit = QLineEdit()
        grid.addWidget(self.folder_edit, 0, 1)
        self.folder_btn = QPushButton(self._t("browse"))
        self.folder_btn.clicked.connect(self._pick_folder)
        grid.addWidget(self.folder_btn, 0, 2)
        self.scan_btn = QPushButton(self._t("lb_rescan"))
        self.scan_btn.clicked.connect(self.scan)
        grid.addWidget(self.scan_btn, 0, 3)
        grid.addWidget(QLabel(self._t("lb_shp")), 1, 0)
        self.shp_combo = QComboBox()
        grid.addWidget(self.shp_combo, 1, 1, 1, 3)
        grid.addWidget(QLabel(self._t("lb_out")), 2, 0)
        self.out_edit = QLineEdit()
        grid.addWidget(self.out_edit, 2, 1)
        self.out_btn = QPushButton(self._t("browse"))
        self.out_btn.clicked.connect(self._pick_out)
        grid.addWidget(self.out_btn, 2, 2)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        row = QHBoxLayout()
        row.addWidget(QLabel(self._t("lb_type")))
        self.type_box = QComboBox()
        for key in core.BUFFER_TYPES:
            self.type_box.addItem(self._t("lb_type_n", n=key), key)
        self.type_box.currentIndexChanged.connect(self._fill_zones)
        row.addWidget(self.type_box)
        row.addStretch(1)
        lay.addLayout(row)

        self.zones_group = QGroupBox(self._t("lb_zones"))
        self.zones_lay = QVBoxLayout(self.zones_group)
        lay.addWidget(self.zones_group)

        self.build_btn = QPushButton(self._t("lb_build"))
        self.build_btn.setObjectName("primary")
        self.build_btn.setMaximumWidth(260)
        self.build_btn.clicked.connect(self.build)
        lay.addWidget(self.build_btn)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        lay.addWidget(self.log_view, 1)

    def _set_busy(self, busy):
        for w in (self.build_btn, self.scan_btn, self.folder_btn, self.out_btn):
            w.setEnabled(not busy)

    def _fill_zones(self, *_):
        while self.zones_lay.count():
            w = self.zones_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.zone_boxes = {}
        for dist, name in core.BUFFER_TYPES[self.type_box.currentData() or "1"]:
            cb = QCheckBox(self._t("lb_zone_row", d=dist, name=name))
            cb.setChecked(True)
            self.zones_lay.addWidget(cb)
            self.zone_boxes[(dist, name)] = cb

    # ------------------------------------------------------------------ helpers
    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, self._t("lb_folder"), self.folder_edit.text())
        if d:
            self.folder_edit.setText(d)
            self.scan()

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, self._t("lb_out"), self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _remember(self):
        self.shell.settings["tool_state"][self.TOOL] = {
            "folder": self.folder_edit.text().strip(), "out": self.out_edit.text().strip(),
            "type": self.type_box.currentData()}
        self.shell.settings.save()

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    # ------------------------------------------------------------------ actions
    def scan(self):
        folder = self.folder_edit.text().strip()
        try:
            self.shp_map = core.scan_line_shapefiles(folder)
        except ImportError as e:
            self.shell.notify(self._t("lb_dep", e=e), "error")
            self.shp_map = {}
        prev = self.shp_combo.currentText()
        self.shp_combo.clear()
        self.shp_combo.addItems(list(self.shp_map))
        if prev in self.shp_map:
            self.shp_combo.setCurrentText(prev)
        if folder:
            self._log(self._t("lb_found", n=len(self.shp_map)) if self.shp_map else self._t("lb_none"))

    def build(self):
        shp = self.shp_map.get(self.shp_combo.currentText())
        out = self.out_edit.text().strip()
        zones = [k for k, cb in self.zone_boxes.items() if cb.isChecked()]
        if not shp or not os.path.isfile(shp):
            self.shell.notify(self._t("lb_warn_shp"), "error")
            return
        if not out or not os.path.isdir(out):
            self.shell.notify(self._t("lb_warn_out"), "error")
            return
        if not zones:
            self.shell.notify(self._t("lb_warn_zone"), "error")
            return
        try:
            plan = core.plan_layer(shp)
        except ValueError:
            self.shell.notify(self._t("lb_no_crs"), "error")          # a missing CRS is never guessed
            return
        except Exception as e:                                        # noqa: BLE001
            self.shell.notify(str(e), "error")
            return
        if plan["convert"] and not self._confirm(
                self._t("lb_convert_q", cur=plan["current"], epsg=plan["epsg"], zone=plan["zone"])):
            return
        self._remember()
        epsg = plan["epsg"]

        def work(ctx):
            try:
                return core.build_buffers(shp, out, zones, epsg, log=ctx.log,
                                          progress=lambda i, n: ctx.progress(i, n), cancel=ctx.cancelled)
            except core.Cancelled:
                raise workers.Cancelled()
            except ValueError as e:
                raise RuntimeError(self._t("lb_no_crs") if str(e) == "no_crs" else self._t("lb_no_geom"))

        self.shell.run(work, "line_buffer", inputs=[shp], params={"zones": [z[0] for z in zones], "epsg": epsg},
                       on_done=self._done, on_log=self._log)

    def _done(self, written):
        out = self.out_edit.text().strip()
        msg = self._t("lb_done", n=len(written), out=out)
        self._log(msg)
        self.shell.notify(msg)
