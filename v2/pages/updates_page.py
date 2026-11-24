"""Updates page: check GitHub Releases, download (confirm), install with backup (confirm), roll back (confirm)."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from tools import update_manager as um
from tools import version
from v2 import update_state, workers
from v2.i18n import tr
from v2.settings import settings_dir


def updates_dir():
    d = os.path.join(settings_dir(), "updates")
    os.makedirs(d, exist_ok=True)
    return d


def backups_dir():
    d = os.path.join(settings_dir(), "update_backups")
    os.makedirs(d, exist_ok=True)
    return d


class UpdatesPage(QWidget):
    def __init__(self, shell, opener=None):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        self.opener = opener                       # tests inject a fake network
        self.check = None
        self.asset = None
        self.dl = None
        self._build()
        self._refresh()
        shell.busy_changed.connect(lambda _b: self._refresh())

    def _t(self, k, **f):
        return tr(self.lang, k, **f)

    @property
    def cfg(self):
        return self.shell.settings["updates"]

    # ------------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        self.v_current, self.v_latest, self.v_date, self.v_last = (QLabel("") for _ in range(4))
        for r, (key, w) in enumerate((("upd_current", self.v_current), ("upd_latest", self.v_latest),
                                      ("upd_date", self.v_date), ("upd_last", self.v_last))):
            lb = QLabel(self._t(key))
            lb.setObjectName("muted")
            grid.addWidget(lb, r, 0)
            grid.addWidget(w, r, 1)
        grid.setColumnStretch(2, 1)
        lay.addLayout(grid)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.cb_auto = QCheckBox(self._t("upd_auto"))
        self.cb_notify = QCheckBox(self._t("upd_notify"))
        self.cb_pre = QCheckBox(self._t("upd_pre"))
        for cb, key in ((self.cb_auto, "auto_check"), (self.cb_notify, "notify"), (self.cb_pre, "prerelease")):
            cb.setChecked(bool(self.cfg.get(key)))
            cb.toggled.connect(lambda v, k=key: self._set_opt(k, v))
            lay.addWidget(cb)

        row = QHBoxLayout()
        self.btn_check = QPushButton(self._t("upd_check"))
        self.btn_check.setObjectName("primary")
        self.btn_check.clicked.connect(self.check_now)
        self.btn_dl = QPushButton(self._t("upd_download"))
        self.btn_dl.clicked.connect(self.download)
        self.btn_inst = QPushButton(self._t("upd_install"))
        self.btn_inst.clicked.connect(self.install)
        self.btn_rb = QPushButton(self._t("upd_rollback"))
        self.btn_rb.clicked.connect(self.rollback)
        for b in (self.btn_check, self.btn_dl, self.btn_inst, self.btn_rb):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        lb = QLabel(self._t("upd_notes"))
        lb.setStyleSheet("font-weight:600; background:transparent;")
        lay.addWidget(lb)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        lay.addWidget(self.notes, 1)

    def _set_opt(self, key, value):
        self.cfg[key] = bool(value)
        self.shell.settings.save()

    def _refresh(self):
        busy = self.shell.task is not None
        self.v_current.setText(version.__version__)
        self.v_latest.setText(self.cfg.get("latest_version") or "-")
        self.v_date.setText((self.cfg.get("latest_published") or "-")[:10])
        self.v_last.setText(self.cfg.get("last_check") or self._t("upd_never"))
        avail = self.check is not None and self.check.status == "available"
        self.btn_check.setEnabled(not busy)
        self.btn_dl.setEnabled(not busy and avail)
        self.btn_inst.setEnabled(not busy and self.dl is not None and self.dl.path.lower().endswith(
            (".zip", ".tar.gz", ".tgz")))
        self.btn_rb.setEnabled(not busy)

    # ------------------------------------------------------------------ hooks for tests
    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------ check
    def check_now(self):
        pre = bool(self.cfg.get("prerelease"))
        self.shell.run(lambda ctx: um.check_for_updates(allow_prerelease=pre, opener=self.opener),
                       "updates.check", params={"prerelease": pre}, on_done=self._checked)

    def _checked(self, chk):
        self.check, self.dl = chk, None
        update_state.record_check(self.shell.settings, chk)
        if chk.status == "available":
            self.asset = um.select_asset(chk.latest)
            self.status.setText(self._t("upd_available", v=chk.latest.version) +
                                ("" if self.asset else "\n" + self._t("upd_no_asset")))
            self.notes.setPlainText(chk.latest.notes)
        elif chk.status == "up_to_date":
            self.status.setText(self._t("upd_uptodate"))
            self.notes.setPlainText(chk.latest.notes if chk.latest else "")
        else:
            self.status.setText(self._t("upd_error", e=update_state.friendly_error(chk.error)))
        self._refresh()

    # ------------------------------------------------------------------ download
    def download(self):
        if not (self.check and self.check.status == "available"):
            return
        if self.asset is None:
            self.shell.notify(self._t("upd_no_asset"), "error")
            return
        a = self.asset
        size = self._t("upd_mb", n=a.size / 1024 / 1024) if a.size else "?"
        if not self._confirm(self._t("upd_confirm_download", name=a.name, size=size, src=urlparse(a.url).netloc)):
            return
        rel, dest, opener = self.check.latest, updates_dir(), self.opener

        def work(ctx):
            try:
                cs = um.find_checksum(rel, a, opener)
                return um.download_asset(a, dest, cs, confirmed=True, opener=opener,
                                         progress=lambda d, t: ctx.progress(d, t or d),
                                         cancel=ctx.cancelled)
            except um.UpdateError as e:
                if e.code == "cancelled":
                    raise workers.Cancelled()
                raise RuntimeError(update_state.friendly_error(e))
        self.shell.run(work, "updates.download", inputs=[a.url], on_done=self._downloaded)

    def _downloaded(self, res):
        self.dl = res
        key = "upd_downloaded_ok" if res.verified else "upd_downloaded_unverified"
        msg = self._t(key, p=res.path)
        if not res.path.lower().endswith((".zip", ".tar.gz", ".tgz")):
            msg += "\n" + self._t("upd_manual", p=res.path)
        self.status.setText(msg)
        self._refresh()

    # ------------------------------------------------------------------ install / rollback
    def install(self):
        if self.dl is None or self.check is None:
            return
        target, bk = um.default_app_dir(), backups_dir()
        ver = self.check.latest.version
        if not self._confirm(self._t("upd_confirm_install", v=ver, dir=target, bk=bk)):
            return
        allow = False
        if not self.dl.verified:
            if not self._confirm(self._t("upd_confirm_unverified")):
                return
            allow = True
        dl = self.dl

        def work(ctx):
            try:
                return um.install_update(dl.path, target, bk, ver, confirmed=True, verified=dl.verified,
                                         allow_unverified=allow, progress=lambda i, n: ctx.progress(i, n),
                                         log=ctx.log)
            except um.UpdateError as e:
                raise RuntimeError(update_state.friendly_error(e))
        self.shell.run(work, "updates.install", inputs=[dl.path], params={"version": ver},
                       on_done=self._installed)

    def _installed(self, res):
        um.prune_backups(backups_dir(), keep=3)
        self.dl = None
        msg = self._t("upd_installed", r=len(res.replaced), a=len(res.added), bk=res.backup_dir)
        self.status.setText(msg)
        self.shell.notify(msg)
        self._refresh()

    def rollback(self):
        items = um.list_backups(backups_dir())
        if not items:
            self.shell.notify(self._t("upd_no_backup"), "error")
            return
        b = items[0]
        if not self._confirm(self._t("upd_confirm_rollback", v=b.get("version_before", "?"), bk=b["dir"])):
            return

        def work(ctx):
            try:
                return um.rollback_update(b["dir"], confirmed=True)
            except um.UpdateError as e:
                raise RuntimeError(update_state.friendly_error(e))
        self.shell.run(work, "updates.rollback", inputs=[b["dir"]], on_done=self._rolled_back)

    def _rolled_back(self, _m):
        self.status.setText(self._t("upd_rolled_back"))
        self.shell.notify(self._t("upd_rolled_back"))
        self._refresh()
