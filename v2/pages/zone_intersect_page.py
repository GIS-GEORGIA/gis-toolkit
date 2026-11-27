"""Zone intersection / line crossing (PySide6).

Points where the parcel boundary crosses the protection-zone boundary (or where two lines cross), written as a new
point shapefile ``<name><UTM zone>_<N>.shp`` (never overwriting), the cut-out / remaining parcel areas, optional
saving of those pieces, hand-over to “Shp → coordinates”, and copying of ready-made template files.
Logic: ``tools/zone_intersect_core`` (shared with the classic tool); texts: the classic catalogues ZTR / LTR.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from tools import zone_intersect_core as core
from tools.template_sets import get as get_template_set
from v2.i18n import tr


def _catalog(name):
    from tools import zone_intersect as classic        # texts only (no Tk window is created)
    return getattr(classic, name)


class ZoneIntersectPage(QWidget):
    TOOL = "zone_intersect"
    CATALOG = "ZTR"
    DEFAULT_NAME = core.DEFAULT_OUT_NAME
    COPY_SETS = ("protzone_crossing",)
    FILE_FILTER = "Shapefile (*.shp);;All files (*.*)"

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        self.cat = _catalog(self.CATALOG)
        self.zone_meta = {}
        self.result = None                  # last compute() result + out_path
        self.copy_rows = []
        self._build()
        st = self._state()
        self.parcel_edit.setText(st.get("parcel", ""))
        self.zone_edit.setText(st.get("zone", ""))
        self.out_edit.setText(st.get("out", ""))
        self.name_edit.setText(st.get("outname") or self.DEFAULT_NAME)
        self._want_field, self._want_value = st.get("zfield", ""), st.get("zvalue", "")
        if os.path.isfile(self.zone_edit.text()):
            self.load_zone_meta()
        for cs in self.copy_rows:
            cs["rebuild"]()
        shell.busy_changed.connect(self._set_busy)

    # ------------------------------------------------------------------ texts / state
    def _z(self, key, **f):
        d = self.cat.get(key, {})
        s = d.get(self.lang) or d.get("en") or key
        return s.format(**f) if f else s

    def _t(self, k, **f):
        return tr(self.lang, k, **f)

    def _state(self):
        return self.shell.settings["tool_state"].get(self.TOOL, {})

    def _remember(self, **extra):
        st = dict(self._state())
        st.update({"parcel": self.parcel_edit.text().strip(), "zone": self.zone_edit.text().strip(),
                   "out": self.out_edit.text().strip(), "outname": self.name_edit.text().strip(),
                   "zfield": self.field_combo.currentText(), "zvalue": self.value_combo.currentText()})
        st.update(extra)
        self.shell.settings["tool_state"][self.TOOL] = st
        self.shell.settings.save()

    # ------------------------------------------------------------------ UI
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)   # content follows the width
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 8, 0)
        area.setWidget(host)
        outer.addWidget(area, 1)

        note = QLabel(self._z("desc"))
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)

        box = QGroupBox(self._z("section"))
        g = QGridLayout(box)
        self.parcel_edit = self._path_row(g, 0, "parcel", "tip_parcel", folder=False)
        self.zone_edit = self._path_row(g, 1, "zone", "tip_zone", folder=False, on_set=self.load_zone_meta)
        self.zone_edit.editingFinished.connect(self.load_zone_meta)
        self.out_edit = self._path_row(g, 2, "out", "tip_out", folder=True)
        g.addWidget(QLabel(self._z("outname")), 3, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setToolTip(self._z("tip_outname"))
        g.addWidget(self.name_edit, 3, 1)
        g.addWidget(QLabel(self._z("zfield")), 4, 0)
        zrow = QHBoxLayout()
        self.field_combo = QComboBox()
        self.field_combo.setToolTip(self._z("tip_zfield"))
        self.field_combo.setMinimumWidth(160)
        self.field_combo.currentTextChanged.connect(self._refresh_values)
        zrow.addWidget(self.field_combo)
        zrow.addSpacing(14)
        zrow.addWidget(QLabel(self._z("zvalue")))
        self.value_combo = QComboBox()
        self.value_combo.setToolTip(self._z("tip_zvalue"))
        self.value_combo.setMinimumWidth(200)
        self.value_combo.addItem(self._z("all_zones"))
        zrow.addWidget(self.value_combo)
        zrow.addStretch(1)
        g.addLayout(zrow, 4, 1, 1, 2)
        g.setColumnStretch(1, 1)
        lay.addWidget(box)

        brow = QHBoxLayout()
        self.create_btn = QPushButton(self._z("btn_create"))
        self.create_btn.setObjectName("primary")
        self.create_btn.setToolTip(self._z("tip_create"))
        self.create_btn.clicked.connect(self.create)
        brow.addWidget(self.create_btn)
        self.coords_btn = self._btn(brow, "btn_coords", "tip_coords", self.open_in_coords)
        self.excel_btn = self._btn(brow, "btn_excel", "tip_excel", self.excel)
        brow.addStretch(1)
        lay.addLayout(brow)
        prow = QHBoxLayout()
        self.cut_btn = self._btn(prow, "btn_cut", "tip_cut", self.save_cut)
        self.rem_btn = self._btn(prow, "btn_rem", "tip_rem", self.save_remainder)
        prow.addStretch(1)
        lay.addLayout(prow)
        self.areas_label = QLabel("")
        self.areas_label.setObjectName("muted")
        self.areas_label.setWordWrap(True)
        lay.addWidget(self.areas_label)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(110)
        self.log_view.setMaximumHeight(180)
        lay.addWidget(self.log_view)

        for set_id in self.COPY_SETS:
            self._build_copy_section(lay, get_template_set(set_id))
        lay.addStretch(1)

    def _path_row(self, g, r, label, tip, folder, on_set=None):
        g.addWidget(QLabel(self._z(label)), r, 0)
        edit = QLineEdit()
        edit.setToolTip(self._z(tip))
        g.addWidget(edit, r, 1)
        b = QPushButton(self._t("browse"))
        b.setToolTip(self._z(tip))

        def pick():
            start = edit.text().strip()
            if folder:
                p = self._dir_name(self._z(label), start)
            else:
                p = self._open_name(self._z(label), os.path.dirname(start) if start else "", self.FILE_FILTER)
            if p:
                edit.setText(os.path.normpath(p))
                if on_set:
                    on_set()
        b.clicked.connect(pick)
        g.addWidget(b, r, 2)
        return edit

    def _btn(self, row, key, tip, slot):
        b = QPushButton(self._z(key))
        b.setToolTip(self._z(tip))
        b.clicked.connect(slot)
        b.setEnabled(False)
        row.addWidget(b)
        return b

    def _set_busy(self, busy):
        self.create_btn.setEnabled(not busy)
        has_pts = bool(self.result and self.result.get("out_path"))
        self.coords_btn.setEnabled(not busy and has_pts)
        self.excel_btn.setEnabled(not busy and has_pts)
        self.cut_btn.setEnabled(not busy and self._piece("cut") is not None)
        self.rem_btn.setEnabled(not busy and self._piece("remainder") is not None)

    # ------------------------------------------------------------------ dialogs (patched in tests)
    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _open_name(self, title, start, filt):
        return QFileDialog.getOpenFileName(self, title, start, filt)[0]

    def _dir_name(self, title, start):
        return QFileDialog.getExistingDirectory(self, title, start)

    def _ask_name(self, prompt, suggested):
        text, ok = QInputDialog.getText(self, "GIS_BOX", prompt, QLineEdit.EchoMode.Normal, suggested)
        return text if ok else ""

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    def _error(self, msg):
        self._log("✗ " + msg)
        self.shell.notify(msg, "error")

    # ------------------------------------------------------------------ zone attributes
    def load_zone_meta(self):
        zone = self.zone_edit.text().strip()
        if not zone or not os.path.isfile(zone):
            return
        try:
            self.zone_meta = core.read_zone_meta(zone)
        except Exception as e:                          # noqa: BLE001
            self._log("— zone: " + str(e).splitlines()[0])
            self.zone_meta = {}
        fields = list(self.zone_meta)
        want = self._want_field if self._want_field in fields else core.auto_zone_field(fields)
        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        self.field_combo.addItems(fields)
        self.field_combo.setCurrentText(want)
        self.field_combo.blockSignals(False)
        self._refresh_values()

    def _refresh_values(self, *_):
        allv = self._z("all_zones")
        vals = self.zone_meta.get(self.field_combo.currentText(), [])
        cur = self._want_value or self.value_combo.currentText()
        self.value_combo.clear()
        self.value_combo.addItems([allv] + vals)
        self.value_combo.setCurrentText(cur if cur in vals else allv)
        self._want_value = ""

    # ------------------------------------------------------------------ create
    def create(self):
        parcel = self.parcel_edit.text().strip()
        zone = self.zone_edit.text().strip()
        out = self.out_edit.text().strip()
        if not parcel or not os.path.isfile(parcel):
            return self.shell.notify(self._z("warn_parcel"), "error")
        if not zone or not os.path.isfile(zone):
            return self.shell.notify(self._z("warn_zone"), "error")
        if not out or not os.path.isdir(out):
            return self.shell.notify(self._z("warn_out"), "error")
        field, value = self.field_combo.currentText(), self.value_combo.currentText()
        if value == self._z("all_zones") or not field:
            field, value = None, None
        self._remember()
        name, default = self.name_edit.text(), self.DEFAULT_NAME

        def work(ctx):
            ctx.log(self._z("running"))
            res = core.compute(parcel, zone, field, value)
            ctx.check_cancelled()                  # cancelled while computing: write nothing
            if res["points"]:
                path = core.next_free_path(out, core.output_base(name, default, res["crs"]))
                core.write_points(res["points"], res["crs"], path)
                res["out_path"] = path
            return res

        self.shell.run(work, self.TOOL, inputs=[parcel, zone], params={"field": field, "value": value, "out": out},
                       on_done=self._on_result, on_log=self._log)

    def _piece(self, key):
        g = ((self.result or {}).get("areas") or {}).get(key)
        return g if g is not None and not g.is_empty and g.area > 0 else None

    def _on_result(self, res):
        self.result = res
        a = res.get("areas") or {}
        self.areas_label.setText("{}: {:.3f}   |   {}: {:.3f}   |   {}: {:.3f}   (m²)".format(
            "ნაკვეთი / parcel", a.get("parcel_area", 0.0), "მოჭრილი / cut", a.get("cut_area", 0.0),
            "დარჩენილი / remaining", a.get("remainder_area", 0.0)))
        self._set_busy(False)
        if not res["points"]:
            self._log(self._z("warn_none"))
            self.shell.notify(self._z("warn_none"))
            return
        msg = self._z("done", n=len(res["points"]), path=res["out_path"])
        self._log(msg)
        if res["crs"] is None:
            self._log("⚠ " + self._z("crs_warn"))
        if res.get("shallow"):
            warn = self._z("warn_shallow", **core.shallow_summary(res["shallow"]))
            self._log("⚠ " + warn)
            self._warn(msg + "\n\n⚠ " + warn)          # must be read: the point may sit far off along the line
        self.shell.notify(msg)

    def _warn(self, text):
        QMessageBox.warning(self, "GIS_BOX", text)

    # ------------------------------------------------------------------ pieces
    def save_cut(self):
        self._save_piece("cut", core.DEFAULT_CUT_NAME, "warn_nocut", "pick_cut_out", "ask_cut_name", "cut_saved")

    def save_remainder(self):
        self._save_piece("remainder", core.DEFAULT_REMAIN_NAME, "warn_norem", "pick_rem_out", "ask_rem_name",
                         "rem_saved")

    def _save_piece(self, key, default_base, warn_key, pick_key, ask_key, saved_key):
        geom = self._piece(key)
        if geom is None:
            return self.shell.notify(self._z(warn_key))
        out = self._dir_name(self._z(pick_key), self.out_edit.text().strip())
        if not out:
            return
        crs = self.result["crs"]
        suggested = os.path.splitext(os.path.basename(core.next_free_path(
            out, default_base + core.zone_num_from_crs(crs))))[0]
        name = self._ask_name(self._z(ask_key), suggested)
        if not name.strip():
            return
        path = core.piece_path(out, name)
        try:
            core.write_piece(geom, crs, path)
        except Exception as e:                          # noqa: BLE001
            return self._error(str(e))
        msg = self._z(saved_key, area=round(geom.area, 3), path=path)
        self._log(msg)
        self.shell.notify(msg)

    # ------------------------------------------------------------------ hand-over to Shp → coordinates
    def _handoff(self):
        path = (self.result or {}).get("out_path")
        if not path or not os.path.exists(path):
            self.shell.notify(self._z("warn_nocreate"), "error")
            return None
        self.shell.show_tool("shp_coords")
        page = getattr(self.shell.pages.get("shp_coords"), "native", None)
        if page is None:
            return None
        page.load_external(path)
        a = self.result.get("areas") or {}
        page.set_pending_areas({k: a.get(k, 0.0) for k in ("parcel_area", "cut_area", "remainder_area")})
        return page

    def open_in_coords(self):
        self._handoff()

    def excel(self):
        page = self._handoff()
        if page is not None:
            page.export()

    # ------------------------------------------------------------------ copy ready-made template files
    def _build_copy_section(self, lay, cfg):
        templates = cfg["templates"]
        zoned = cfg.get("zoned", True)
        name = cfg["name_" + ("ka" if self.lang == "ka" else "en")]
        st = self._state()
        box = QGroupBox(self._z("copy_title", name=name))
        v = QVBoxLayout(box)
        d = QLabel(self._z("copy_desc", name=name) + "  " + self._z("copy_hint"))
        d.setObjectName("muted")
        d.setWordWrap(True)
        v.addWidget(d)
        g = QGridLayout()
        g.addWidget(QLabel(self._z("copy_source")), 0, 0)
        src = QLineEdit(st.get("copy_source") or self._default_source())
        g.addWidget(src, 0, 1)
        sbtn = QPushButton(self._t("browse"))
        g.addWidget(sbtn, 0, 2)
        g.addWidget(QLabel(self._z("copy_target")), 1, 0)
        dst = QLineEdit((st.get("copy_dest") or {}).get(cfg["id"], ""))
        g.addWidget(dst, 1, 1)
        dbtn = QPushButton(self._t("browse"))
        g.addWidget(dbtn, 1, 2)
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        checks_host = QWidget()
        checks = QVBoxLayout(checks_host)
        checks.setContentsMargins(0, 0, 0, 0)
        v.addWidget(checks_host)
        go = QPushButton(self._z("copy_btn"))
        go.setMaximumWidth(200)
        v.addWidget(go)
        row = {"cfg": cfg, "src": src, "dst": dst, "boxes": {}}

        def rebuild():
            while checks.count():
                w = checks.takeAt(0).widget()
                if w:
                    w.deleteLater()
            row["boxes"] = {}
            for zone, base in templates.items():
                exists = bool(core.template_files(src.text().strip(), base))
                label = (self._z("copy_zone_label", z=zone) + "  (" + base + ")") if zoned else base
                if not exists:
                    label += "  — ⚠ " + self._z("copy_notfound")
                cb = QCheckBox(label)
                cb.setEnabled(exists)
                checks.addWidget(cb)
                row["boxes"][zone] = cb

        def pick_src():
            p = self._dir_name(self._z("copy_source"), src.text())
            if p:
                src.setText(os.path.normpath(p))
                self._remember(copy_source=src.text())
                rebuild()

        def pick_dst():
            p = self._dir_name(self._z("copy_target"), dst.text())
            if p:
                dst.setText(os.path.normpath(p))

        sbtn.clicked.connect(pick_src)
        src.editingFinished.connect(rebuild)
        dbtn.clicked.connect(pick_dst)
        go.clicked.connect(lambda: self.copy_templates(row))
        row["rebuild"] = rebuild
        self.copy_rows.append(row)
        lay.addWidget(box)

    @staticmethod
    def _default_source():
        try:
            from tools.apppaths import resource_dir
            return os.path.join(resource_dir(), "shp")
        except Exception:                               # noqa: BLE001
            return ""

    def copy_templates(self, row):
        zones = [z for z, cb in row["boxes"].items() if cb.isChecked()]
        dest = row["dst"].text().strip()
        if not zones:
            return self.shell.notify(self._z("warn_copy_zone"), "error")
        if not dest:
            return self.shell.notify(self._z("warn_copy_dest"), "error")
        if not os.path.isdir(dest):
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError as e:
                return self._error(self._z("copy_err_mkdir", e=e))
        dests = dict(self._state().get("copy_dest") or {})
        dests[row["cfg"]["id"]] = dest
        self._remember(copy_dest=dests, copy_source=row["src"].text().strip())
        total, created = 0, []
        for zone in zones:
            new_base, n = core.copy_template(row["src"].text().strip(), row["cfg"]["templates"][zone], dest,
                                             log=self._log)
            if new_base:
                total += n
                created.append(new_base)
        msg = self._z("copy_done", names=", ".join(created), n=total, dest=dest)
        self._log(msg)
        self.shell.notify(msg)


class LineIntersectPage(ZoneIntersectPage):
    TOOL = "line_intersect"
    CATALOG = "LTR"
    DEFAULT_NAME = core.DEFAULT_LINE_NAME
    COPY_SETS = ("riverbank", "gas_crossing", "utm_grid")
