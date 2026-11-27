"""Rename → Latin (PySide6): Georgian file names transliterated to Latin.

Same behaviour as the classic tool: a preview first, renaming only after confirmation, conflicts (two names giving
the same Latin name, or the target already exists) are skipped, the last batch can be undone. All files of one
dataset (``a.shp``, ``a.dbf``, ``a.shp.xml`` …) are renamed together or not at all. Logic: ``tools/translit``.
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)
from PySide6.QtCore import Qt

from tools import translit as core
from v2.i18n import tr


class RenamePage(QWidget):
    TOOL = "rename"

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        self.plan = []
        self.undo = []                  # last batch: [(new_path, old_path)]
        self._build()
        st = shell.settings["tool_state"].get(self.TOOL, {})
        self.folder_edit.setText(st.get("folder", ""))
        self.recursive_box.setChecked(bool(st.get("recursive", False)))
        shell.busy_changed.connect(self._set_busy)

    def _t(self, k, **f):
        return tr(self.lang, k, **f)

    # ------------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        note = QLabel(self._t("rn_note"))
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(QLabel(self._t("rn_folder")))
        self.folder_edit = QLineEdit()
        self.folder_edit.returnPressed.connect(self.preview)
        row.addWidget(self.folder_edit, 1)
        self.folder_btn = QPushButton(self._t("browse"))
        self.folder_btn.clicked.connect(self._pick_folder)
        row.addWidget(self.folder_btn)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.recursive_box = QCheckBox(self._t("rn_recursive"))
        row.addWidget(self.recursive_box)
        row.addSpacing(16)
        self.preview_btn = QPushButton(self._t("rn_preview"))
        self.preview_btn.clicked.connect(self.preview)
        row.addWidget(self.preview_btn)
        self.rename_btn = QPushButton(self._t("rn_rename"))
        self.rename_btn.setObjectName("primary")
        self.rename_btn.clicked.connect(self.rename)
        row.addWidget(self.rename_btn)
        self.undo_btn = QPushButton(self._t("rn_undo"))
        self.undo_btn.clicked.connect(self.undo_last)
        self.undo_btn.setEnabled(False)
        row.addWidget(self.undo_btn)
        row.addStretch(1)
        self.check_btn = QPushButton(self._t("rn_check"))
        self.check_btn.setToolTip(self._t("rn_check_tip"))
        self.check_btn.clicked.connect(self.check_contents)
        row.addWidget(self.check_btn)
        lay.addLayout(row)

        split = QSplitter(Qt.Orientation.Vertical)
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setHeaderLabels([self._t("rn_col_old"), self._t("rn_col_new"), self._t("rn_col_status")])
        self.table.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.header().setStretchLastSection(True)
        split.addWidget(self.table)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        split.addWidget(self.log_view)
        split.setSizes([300, 140])
        lay.addWidget(split, 1)

    def _set_busy(self, busy):
        for w in (self.preview_btn, self.rename_btn, self.check_btn, self.folder_btn):
            w.setEnabled(not busy)
        self.undo_btn.setEnabled(not busy and bool(self.undo))

    # ------------------------------------------------------------------ helpers
    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, self._t("rn_folder"), self.folder_edit.text())
        if d:
            self.folder_edit.setText(os.path.normpath(d))
            self.preview()

    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _log(self, msg):
        self.log_view.appendPlainText(msg)

    def _folder(self):
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            self.shell.notify(self._t("rn_warn_folder"), "error")
            return None
        self.shell.settings["tool_state"][self.TOOL] = {"folder": folder, "recursive": self.recursive_box.isChecked()}
        self.shell.settings.save()
        return folder

    def _show_plan(self, folder):
        self.table.clear()
        multi = self.recursive_box.isChecked()
        for it in self.plan:
            rel = os.path.relpath(it["dir"], folder) if multi else "."
            prefix = "" if rel == "." else rel + os.sep
            row = QTreeWidgetItem([prefix + it["old"], prefix + it["new"], self._t("rn_st_" + it["status"])])
            if it["status"] != "ok":
                for c in range(3):
                    row.setForeground(c, Qt.GlobalColor.darkYellow)
            self.table.addTopLevelItem(row)
        for c in (0, 1):
            self.table.resizeColumnToContents(c)

    # ------------------------------------------------------------------ actions
    def preview(self):
        folder = self._folder()
        if folder is None:
            return None
        self.plan = core.build_plan(folder, self.recursive_box.isChecked())
        self._show_plan(folder)
        n_ok = sum(1 for it in self.plan if it["status"] == "ok")
        self._log(self._t("rn_scan_n", n=n_ok, c=len(self.plan) - n_ok) if self.plan else self._t("rn_none"))
        return folder

    def rename(self):
        folder = self.preview()                       # always re-scan: files may have changed since the preview
        if folder is None:
            return
        n_ok = sum(1 for it in self.plan if it["status"] == "ok")
        if not n_ok:
            self.shell.notify(self._t("rn_nothing"))
            return
        if not self._confirm(self._t("rn_confirm", n=n_ok)):
            return
        plan = list(self.plan)

        def work(ctx):
            return core.apply_plan(plan, log=ctx.log, cancel=ctx.cancelled)

        self.shell.run(work, "rename_translit", inputs=[folder], params={"files": n_ok,
                                                                          "recursive": self.recursive_box.isChecked()},
                       on_done=self._renamed, on_log=self._log)

    def _renamed(self, result):
        ok, skipped, undo = result
        self.undo = undo
        self.undo_btn.setEnabled(bool(undo))
        msg = self._t("rn_done", ok=ok, sk=skipped)
        self._log(msg)
        self.shell.notify(msg)
        self.preview()

    def undo_last(self):
        if not self.undo:
            self.shell.notify(self._t("rn_undo_none"))
            return
        if not self._confirm(self._t("rn_undo_q", n=len(self.undo))):
            return
        undo = list(self.undo)

        def work(ctx):
            return core.undo_renames(undo, log=ctx.log)

        self.shell.run(work, "rename_translit_undo", inputs=[self.folder_edit.text().strip()],
                       params={"files": len(undo)}, on_done=self._undone, on_log=self._log)

    def _undone(self, result):
        ok, skipped = result
        self.undo = []
        self.undo_btn.setEnabled(False)
        msg = self._t("rn_undo_done", ok=ok, sk=skipped)
        self._log(msg)
        self.shell.notify(msg)
        if os.path.isdir(self.folder_edit.text().strip()):
            self.preview()

    def check_contents(self):
        folder = self._folder()
        if folder is None:
            return
        res = core.check_contents(folder, self.recursive_box.isChecked())
        if not res:
            self._log(self._t("rn_chk_none"))
            self.shell.notify(self._t("rn_chk_none"))
            return
        self._log(self._t("rn_chk_hdr"))
        d = e = u = 0
        for path, n in res:
            name = os.path.basename(path)
            if n is None:
                u += 1
                self._log(self._t("rn_chk_unknown", name=name))
            elif n == 0:
                e += 1
                self._log(self._t("rn_chk_empty", name=name))
            elif n < 0:
                d += 1
                self._log(self._t("rn_chk_has_x", name=name))
            else:
                d += 1
                self._log(self._t("rn_chk_has", name=name, n=n))
        self._log(self._t("rn_chk_sum", t=len(res), d=d, e=e, u=u))
