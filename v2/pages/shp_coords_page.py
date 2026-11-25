"""Shp → coordinates (PySide6): point shapefile → formatted Excel / clipboard / PNG.

Same output as the classic tool (the Excel writer is shared: ``tools/shp_coords_core``). Safety rules:
a layer without a CRS is used as UTM only after the user agrees (single export) and is skipped in a batch; a batch
never overwrites an existing file; integer rounding asks first; a file open in Excel is closed only with consent.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QRadioButton, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from tools import shp_coords_core as core
from tools.translit import lat_to_geo
from tools.xlsx_format import FileLockedError
from v2.i18n import tr

LOCKED = "__locked__"


class ShpCoordsPage(QWidget):
    TOOL = "shp_coords"

    def __init__(self, shell, templates_path=None):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        self.tpath = templates_path            # None = the shared app file (tests pass their own)
        self.shp_map = {}
        self.detected_zone = None
        self.points = []
        self.pending_areas = None
        self.last_xlsx = ""
        self._build()
        st = shell.settings["tool_state"].get(self.TOOL, {})
        self.folder_edit.setText(st.get("folder", ""))
        {"37": self.z37, "38": self.z38}.get(str(st.get("zone")), self.zauto).setChecked(True)
        (self.v_int if st.get("vtype") == "int" else self.v_dbl).setChecked(True)
        self._refresh_templates(st.get("template", ""))
        self.angle_box.setChecked(bool(st.get("angle", False)))
        self.angle_all_edit.setText(st.get("angle_all", ""))
        for rb in (self.zauto, self.z37, self.z38, self.v_dbl, self.v_int):
            rb.toggled.connect(lambda on: on and self.preview())
        if self.folder_edit.text():
            self.scan(quiet=True)
        shell.busy_changed.connect(self._set_busy)

    def _t(self, k, **f):
        return tr(self.lang, k, **f)

    # ------------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        note = QLabel(self._t("sc_note"))
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)

        g = QGridLayout()
        g.addWidget(QLabel(self._t("sc_folder")), 0, 0)
        self.folder_edit = QLineEdit()
        self.folder_edit.returnPressed.connect(self.scan)
        g.addWidget(self.folder_edit, 0, 1)
        self.folder_btn = QPushButton(self._t("browse"))
        self.folder_btn.clicked.connect(self._pick_folder)
        g.addWidget(self.folder_btn, 0, 2)
        g.addWidget(QLabel(self._t("sc_shp")), 1, 0)
        self.shp_combo = QComboBox()
        self.shp_combo.currentTextChanged.connect(self._on_shp_selected)
        g.addWidget(self.shp_combo, 1, 1)
        self.scan_btn = QPushButton(self._t("sc_rescan"))
        self.scan_btn.clicked.connect(self.scan)
        g.addWidget(self.scan_btn, 1, 2)

        g.addWidget(QLabel(self._t("sc_zone")), 2, 0)
        zrow = QHBoxLayout()
        self.zauto = QRadioButton(self._t("sc_zone_auto", z="—"))
        self.z37, self.z38 = QRadioButton("37"), QRadioButton("38")
        self.zone_group = QButtonGroup(self)
        for rb in (self.zauto, self.z37, self.z38):
            self.zone_group.addButton(rb)
            zrow.addWidget(rb)
        zrow.addStretch(1)
        g.addLayout(zrow, 2, 1, 1, 2)

        g.addWidget(QLabel(self._t("sc_vtype")), 3, 0)
        vrow = QHBoxLayout()
        self.v_dbl, self.v_int = QRadioButton(self._t("sc_v_dbl")), QRadioButton(self._t("sc_v_int"))
        self.vtype_group = QButtonGroup(self)
        for rb in (self.v_dbl, self.v_int):
            self.vtype_group.addButton(rb)
            vrow.addWidget(rb)
        vrow.addStretch(1)
        g.addLayout(vrow, 3, 1, 1, 2)

        g.addWidget(QLabel(self._t("sc_tmpl")), 4, 0)
        trow = QHBoxLayout()
        self.tmpl_combo = QComboBox()
        self.tmpl_combo.setEditable(True)               # a one-off title can be typed directly
        self.tmpl_combo.setMinimumContentsLength(40)
        trow.addWidget(self.tmpl_combo, 1)
        for key, slot, tip in (("sc_tmpl_add", self._add_template, None), ("sc_tmpl_del", self._delete_template, None),
                               ("sc_tmpl_file", self._open_templates_file, "sc_tmpl_file_tip")):
            b = QPushButton(self._t(key))
            b.clicked.connect(slot)
            if tip:
                b.setToolTip(self._t(tip))
            trow.addWidget(b)
        g.addLayout(trow, 4, 1, 1, 2)

        arow = QHBoxLayout()
        self.angle_box = QCheckBox(self._t("sc_angle"))
        arow.addWidget(self.angle_box)
        arow.addSpacing(14)
        arow.addWidget(QLabel(self._t("sc_angle_all")))
        self.angle_all_edit = QLineEdit()
        self.angle_all_edit.setMaximumWidth(80)
        arow.addWidget(self.angle_all_edit)
        arow.addStretch(1)
        g.addLayout(arow, 5, 1, 1, 2)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)

        brow = QHBoxLayout()
        self.export_btn = QPushButton(self._t("sc_export"))
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self.export)
        brow.addWidget(self.export_btn)
        self.action_btns = [self.export_btn]
        for key, tip, slot in (("sc_copy", "sc_copy_tip", self.copy_clipboard), ("sc_png", "sc_png_tip", self.save_png),
                               ("sc_batch", "sc_batch_tip", self.batch),
                               ("sc_apply_deg", "sc_apply_deg_tip", self.apply_degree)):
            b = QPushButton(self._t(key))
            b.setToolTip(self._t(tip))
            b.clicked.connect(slot)
            brow.addWidget(b)
            self.action_btns.append(b)
        brow.addStretch(1)
        lay.addLayout(brow)

        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        lay.addWidget(self.count_label)
        split = QSplitter(Qt.Orientation.Vertical)
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setHeaderLabels(["№", "X", "Y"])
        self.table.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        split.addWidget(self.table)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        split.addWidget(self.log_view)
        split.setSizes([280, 120])
        lay.addWidget(split, 1)

    def _set_busy(self, busy):
        for w in self.action_btns + [self.scan_btn, self.folder_btn]:
            w.setEnabled(not busy)

    # ------------------------------------------------------------------ small helpers
    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _save_name(self, title, initial, filt):
        return QFileDialog.getSaveFileName(self, title, initial, filt)[0]

    def _open_name(self, title, initial, filt):
        return QFileDialog.getOpenFileName(self, title, initial, filt)[0]

    def _dir_name(self, title, initial):
        return QFileDialog.getExistingDirectory(self, title, initial)

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    def _error(self, msg):
        self._log("✗ " + msg)
        self.shell.notify(msg, "error")

    def _zone_choice(self):
        return 37 if self.z37.isChecked() else 38 if self.z38.isChecked() else None

    def _resolve_zone(self, shp):
        return self._zone_choice() or core.detect_zone(shp)

    def _vtype(self):
        return "int" if self.v_int.isChecked() else "double"

    def _template(self):
        t = self.tmpl_combo.currentText().strip()
        return "" if t == self._t("sc_tmpl_none") else t

    def _settings(self):
        angle_on = self.angle_box.isChecked()
        angle_all = core.parse_angle(self.angle_all_edit.text()) if angle_on else None
        return self._template(), angle_on, angle_all, self._vtype()

    def _angle_hdr(self):
        return core.ANGLE_HEADERS[self.lang if self.lang in core.ANGLE_HEADERS else "en"]

    def _remember(self):
        z = self._zone_choice()
        self.shell.settings["tool_state"][self.TOOL] = {
            "folder": self.folder_edit.text().strip(), "zone": str(z) if z else "auto", "vtype": self._vtype(),
            "template": self._template(), "angle": self.angle_box.isChecked(), "angle_all": self.angle_all_edit.text()}
        self.shell.settings.save()

    def _current_shp(self):
        return self.shp_map.get(self.shp_combo.currentText())

    # ------------------------------------------------------------------ templates
    def _refresh_templates(self, select=None):
        cur = select if select is not None else self.tmpl_combo.currentText()
        self.tmpl_combo.blockSignals(True)
        self.tmpl_combo.clear()
        self.tmpl_combo.addItems([self._t("sc_tmpl_none")] + core.templates(self.tpath))
        self.tmpl_combo.setCurrentText(cur or self._t("sc_tmpl_none"))
        self.tmpl_combo.lineEdit().setCursorPosition(0)        # show the beginning of a long title
        self.tmpl_combo.blockSignals(False)

    def _ask_template(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("GIS_BOX")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(self._t("sc_tmpl_add_q")))
        hint = QLabel(self._t("sc_conv_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        v.addWidget(hint)
        edit = QLineEdit()
        edit.setMinimumWidth(460)
        v.addWidget(edit)
        v.addWidget(QLabel(self._t("sc_conv_geo")))
        out = QLabel("")
        out.setWordWrap(True)
        out.setStyleSheet("font-size:14px; font-weight:600;")
        v.addWidget(out)
        edit.textChanged.connect(lambda s: out.setText(lat_to_geo(s)))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        return lat_to_geo(edit.text()).strip() if dlg.exec() == QDialog.DialogCode.Accepted else ""

    def _add_template(self):
        text = self._ask_template()
        if not text:
            return
        try:
            if not core.add_template(text, self.tpath):
                self.shell.notify(self._t("sc_tmpl_bad"), "error")
                return
        except OSError as e:
            self._error(str(e))
            return
        self._refresh_templates(text)

    def _delete_template(self):
        cur = self._template()
        if not cur:
            return
        if cur not in core.file_templates(self.tpath):
            self.shell.notify(self._t("sc_tmpl_builtin"))
            return
        if not self._confirm(self._t("sc_tmpl_del_q", t=cur)):
            return
        try:
            core.delete_template(cur, self.tpath)
        except OSError as e:
            self._error(str(e))
            return
        self._refresh_templates(self._t("sc_tmpl_none"))

    def _open_templates_file(self):
        from tools.platform_utils import open_path
        path = self.tpath or core.TEMPLATES_FILE
        try:
            if not os.path.exists(path):
                core.write_file_templates(core.file_templates(path), path)
            open_path(path)
        except Exception as e:                          # noqa: BLE001
            self._error(str(e))

    # ------------------------------------------------------------------ folder / scan / preview
    def _pick_folder(self):
        d = self._dir_name(self._t("sc_folder"), self.folder_edit.text())
        if d:
            self.folder_edit.setText(os.path.normpath(d))
            self.scan()

    def scan(self, quiet=False):
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            if not quiet:
                self.shell.notify(self._t("sc_no_folder"), "error")
            return
        try:
            self.shp_map = core.scan_point_shapefiles(folder)
        except ImportError as e:
            self._error(str(e))
            return
        names = list(self.shp_map)
        self.shp_combo.blockSignals(True)
        self.shp_combo.clear()
        self.shp_combo.addItems(names)
        self.shp_combo.blockSignals(False)
        if not names:
            self._fill_table([])
            self._log(self._t("sc_no_shp"))
            if not quiet:
                self.shell.notify(self._t("sc_no_shp"))
            return
        self._log(self._t("sc_found", n=len(names)))
        self.shp_combo.setCurrentText(core.auto_pick(names))
        self._on_shp_selected()

    def load_external(self, path):
        """Select a point shapefile handed over by another tool (e.g. zone intersection)."""
        if not path or not os.path.exists(path):
            return
        self.folder_edit.setText(os.path.dirname(path))
        self.scan(quiet=True)
        for name, p in self.shp_map.items():
            if os.path.normcase(p) == os.path.normcase(path):
                self.shp_combo.setCurrentText(name)
                break

    def set_pending_areas(self, areas):
        self.pending_areas = areas if core.has_areas(areas) else None
        if self.pending_areas:
            self._log(self._t("sc_areas"))

    def _on_shp_selected(self, *_):
        shp = self._current_shp()
        if not shp:
            return
        self.detected_zone = core.detect_zone(shp)
        z = self.detected_zone
        self.zauto.setText(self._t("sc_zone_auto", z=z if z else self._t("sc_zone_unknown")))
        self._log(self._t("sc_detected", name=self.shp_combo.currentText(), z=z or "?", n=core.count_points(shp)))
        self.preview()

    def _fill_table(self, points):
        self.table.clear()
        vt = self._vtype()
        for i, (_idv, x, y) in enumerate(points, 1):
            self.table.addTopLevelItem(QTreeWidgetItem([str(i), str(core.coord_value(x, vt)),
                                                        str(core.coord_value(y, vt))]))
        self.count_label.setText(self._t("sc_prev_count", n=len(points)) if points else "")

    def preview(self):
        shp = self._current_shp()
        self.points = []
        if shp:
            zone = self._resolve_zone(shp)
            if zone in (37, 38):
                try:
                    self.points = core.read_points(shp, zone)
                except Exception as e:                  # noqa: BLE001
                    self._log("⚠ " + self._t("sc_load_err", e=e))
        self._fill_table(self.points)

    def _ready_points(self, need_crs_consent=True):
        """(shp, zone, points) after validation and the no-CRS consent, or None."""
        shp = self._current_shp()
        if not shp:
            self.shell.notify(self._t("sc_pick_shp"), "error")
            return None
        zone = self._resolve_zone(shp)
        if zone not in (37, 38):
            self.shell.notify(self._t("sc_need_zone"), "error")
            return None
        if need_crs_consent and core.crs_missing(shp) and not self._confirm(self._t("sc_no_crs_q", z=zone)):
            return None
        try:
            points = core.read_points(shp, zone)
        except Exception as e:                          # noqa: BLE001
            self._error(self._t("sc_load_err", e=e))
            return None
        if not points:
            self.shell.notify(self._t("sc_no_points"), "error")
            return None
        return shp, zone, points

    # ------------------------------------------------------------------ export
    def export(self):
        got = self._ready_points()
        if not got:
            return
        shp, zone, points = got
        if self._vtype() == "int" and not self._confirm(self._t("sc_int_q")):
            return
        base = os.path.splitext(os.path.basename(shp))[0]
        path = self._save_name(self._t("sc_save_title"), os.path.join(os.path.dirname(shp), base + ".xlsx"),
                               "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        self._remember()
        template, angle_on, angle_all, vtype = self._settings()
        args = dict(sheet_name=os.path.basename(shp), points=points, value_type=vtype, template=template,
                    angle_on=angle_on, angle_all=angle_all, angle_hdr=self._angle_hdr(), areas=self.pending_areas)
        self._run_export(shp, zone, path, args, retried=False)

    def _run_export(self, shp, zone, path, args, retried):
        def work(ctx):
            try:
                core.write_workbook(path, **args)
            except FileLockedError:
                return LOCKED
            return len(args["points"])

        def done(res):
            if res == LOCKED:
                if retried or not self._confirm(self._t("sc_locked_q", path=path)):
                    self._error(self._t("sc_locked"))
                    return
                from tools.xlsx_format import close_open_workbook
                import time
                close_open_workbook(path)
                time.sleep(0.4)
                self._run_export(shp, zone, path, args, retried=True)
                return
            self.last_xlsx = path
            self.pending_areas = None                   # areas belong to this one export
            msg = self._t("sc_done", n=res, path=path)
            self._log(msg)
            self.shell.notify(msg)

        self.shell.run(work, "shp_coords", inputs=[shp], params={"zone": zone, "out": path,
                                                                  "vtype": args["value_type"]},
                       on_done=done, on_log=self._log)

    # ------------------------------------------------------------------ clipboard / PNG
    def _block(self):
        got = self._ready_points(need_crs_consent=False)
        if not got:
            return None
        template, angle_on, angle_all, vtype = self._settings()
        headers, rows = core.block_rows(got[2], vtype, angle_on, angle_all, self._angle_hdr())
        return got[0], template, headers, rows

    def copy_clipboard(self):
        b = self._block()
        if not b:
            return
        _shp, template, headers, rows = b
        html, text = core.clipboard_payload(template, headers, rows)
        md = QMimeData()
        md.setHtml(html)
        md.setText(text)
        QApplication.clipboard().setMimeData(md)
        msg = self._t("sc_clip_done", n=len(rows))
        self._log(msg)
        self.shell.notify(msg)

    def save_png(self):
        b = self._block()
        if not b:
            return
        shp, template, headers, rows = b
        base = os.path.splitext(os.path.basename(shp))[0]
        path = self._save_name(self._t("sc_png_title"), os.path.join(os.path.dirname(shp), base + "_table.png"),
                               "PNG (*.png)")
        if not path:
            return
        try:
            from tools.table_image import render_table
            render_table(template, headers, rows, transparent=True).save(path)
        except Exception as e:                          # noqa: BLE001
            self._error(str(e))
            return
        QApplication.clipboard().setImage(QImage(path))
        msg = self._t("sc_png_done", path=path)
        self._log(msg)
        self.shell.notify(msg)

    # ------------------------------------------------------------------ batch
    def batch(self):
        if not self.shp_map:
            self.shell.notify(self._t("sc_no_shp"), "error")
            return
        if self._vtype() == "int" and not self._confirm(self._t("sc_int_q")):
            return
        outdir = self._dir_name(self._t("sc_batch_dir"), self.folder_edit.text())
        if not outdir:
            return
        self._remember()
        template, angle_on, angle_all, vtype = self._settings()
        shps = dict(self.shp_map)
        manual = self._zone_choice()
        hdr = self._angle_hdr()
        t = self._t

        def work(ctx):
            ok = skipped = 0
            for i, (name, shp) in enumerate(shps.items()):
                ctx.check_cancelled()
                ctx.progress(i, len(shps), name)
                if core.crs_missing(shp):                # never assume a zone without the user's consent
                    ctx.log("↷ {}: {}".format(name, t("sc_no_crs_warn")))
                    skipped += 1
                    continue
                zone = manual or core.detect_zone(shp)
                out = os.path.join(outdir, os.path.splitext(name)[0] + ".xlsx")
                if zone not in (37, 38):
                    ctx.log("↷ {} {}".format(t("sc_batch_skip"), name))
                    skipped += 1
                    continue
                if os.path.exists(out):
                    ctx.log("↷ {} {}".format(t("sc_batch_exists"), out))
                    skipped += 1
                    continue
                try:
                    points = core.read_points(shp, zone)
                    if not points:
                        ctx.log("↷ {} {}".format(t("sc_batch_skip"), name))
                        skipped += 1
                        continue
                    core.write_workbook(out, name, points, vtype, template, angle_on, angle_all, hdr)
                except FileLockedError:
                    ctx.log("✗ {}: {}".format(name, t("sc_locked")))
                    skipped += 1
                    continue
                except Exception as e:                  # noqa: BLE001
                    ctx.log("✗ {}: {}".format(name, e))
                    skipped += 1
                    continue
                ctx.log("✓ {} ({})".format(os.path.basename(out), len(points)))
                ok += 1
            return ok, skipped

        def done(res):
            msg = self._t("sc_batch_done", ok=res[0], sk=res[1])
            self._log(msg + "  " + outdir)
            self.shell.notify(msg)

        self.shell.run(work, "shp_coords_batch", inputs=list(shps.values()), params={"out": outdir, "vtype": vtype},
                       on_done=done, on_log=self._log)

    # ------------------------------------------------------------------ ° in an existing file
    def apply_degree(self):
        path = self._open_name(self._t("sc_pick_xlsx"), self.last_xlsx or self.folder_edit.text(), "Excel (*.xlsx)")
        if not path:
            return
        try:
            n = core.apply_degree(path)
        except FileLockedError:
            self._error(self._t("sc_locked"))
            return
        except Exception as e:                          # noqa: BLE001
            self._error(str(e))
            return
        if not n:
            self.shell.notify(self._t("sc_deg_nocol"))
            return
        self.last_xlsx = path
        msg = self._t("sc_deg_done", n=n)
        self._log(msg)
        self.shell.notify(msg)
