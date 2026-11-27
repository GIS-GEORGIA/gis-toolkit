"""GIS_BOX V2 main window: sidebar (search, favorites, recent, categories), tool pages, status bar
with progress + cancel, toast notifications, light/dark themes, Georgian/English."""
from __future__ import annotations

import datetime
import importlib
import os

import shiboken6
from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QStackedWidget,
                               QStatusBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from tools import version
from v2 import launcher, registry, themes, workers
from v2.i18n import tr

ROLE = Qt.ItemDataRole.UserRole
HOME = "__home__"


class MainWindow(QMainWindow):
    busy_changed = Signal(bool)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.lang = settings["lang"]
        self.current = HOME
        self.task = None
        self.pages = {}
        self.resize(settings["window"].get("w", 1180), settings["window"].get("h", 760))
        self.setStatusBar(QStatusBar())
        self._build_status()
        self.apply_theme(settings["theme"], save=False)
        self._build_ui()
        self.show_tool(HOME)
        self.update_opener = None                  # tests inject a fake network
        QTimer.singleShot(2500, self.auto_update_check)

    def t(self, key, **f):
        return tr(self.lang, key, **f)

    # ------------------------------------------------------------------ construction
    def _build_status(self):
        sb = self.statusBar()
        self.status_label = QLabel("")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setMaximumHeight(14)
        self.progress.setVisible(False)
        self.cancel_btn = QPushButton("")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_task)
        sb.addWidget(self.status_label, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.cancel_btn)

    def _build_ui(self):
        """(Re)build everything that carries text - called again when the language changes."""
        self.pages.clear()
        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(290)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 14, 12, 12)
        brand = QLabel("GIS_BOX")
        brand.setObjectName("title")
        sl.addWidget(brand)
        ver = QLabel("{} {}".format(self.t("version"), version.__version__))
        ver.setObjectName("muted")
        sl.addWidget(ver)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.t("search"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._populate)
        sl.addWidget(self.search_edit)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.itemClicked.connect(self._on_item)
        sl.addWidget(self.tree, 1)
        lay.addWidget(side)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.toast = QLabel("", central)
        self.toast.setObjectName("toast")
        self.toast.setVisible(False)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(lambda: self.toast.setVisible(False))

        self._build_menus()
        self._populate()
        self.status_label.setText(self.t("ready"))
        self.cancel_btn.setText(self.t("cancel"))
        self.setWindowTitle("GIS_BOX {}".format(version.__version__))

    def _build_menus(self):
        mb = self.menuBar()
        mb.clear()
        view = mb.addMenu(self.t("menu_view"))
        theme_menu = view.addMenu(self.t("menu_theme"))
        grp = QActionGroup(self)
        for name in ("light", "dark"):
            a = QAction(self.t("theme_" + name), self, checkable=True)
            a.setChecked(self.settings["theme"] == name)
            a.triggered.connect(lambda _c=False, n=name: self.apply_theme(n))
            grp.addAction(a)
            theme_menu.addAction(a)
        lang_menu = view.addMenu(self.t("menu_lang"))
        lg = QActionGroup(self)
        for code, label in (("ka", "ქართული"), ("en", "English")):
            a = QAction(label, self, checkable=True)
            a.setChecked(self.lang == code)
            a.triggered.connect(lambda _c=False, c=code: self.set_lang(c))
            lg.addAction(a)
            lang_menu.addAction(a)
        svc = mb.addMenu(self.t("menu_tools"))
        svc.addAction(self.t("open_logs"), self.open_logs)
        svc.addAction(self.t("export_diag"), self.export_diagnostics)
        svc.addAction(self.t("env_check"), self.show_env_check)
        help_menu = mb.addMenu(self.t("menu_help"))
        help_menu.addAction(self.t("about"), self.show_about)

    # ------------------------------------------------------------------ sidebar
    def _group(self, title):
        g = QTreeWidgetItem([title])
        g.setFlags(Qt.ItemFlag.ItemIsEnabled)
        f = g.font(0)
        f.setBold(True)
        g.setFont(0, f)
        self.tree.addTopLevelItem(g)
        return g

    def _tool_item(self, parent, tool):
        star = "★ " if self.settings.is_favorite(tool.id) else ""
        it = QTreeWidgetItem([star + tool.name[self.lang]])
        it.setData(0, ROLE, tool.id)
        it.setToolTip(0, tool.desc[self.lang])
        parent.addChild(it)
        return it

    def _populate(self, *_):
        q = self.search_edit.text() if hasattr(self, "search_edit") else ""
        self.tree.clear()
        home = QTreeWidgetItem(["⌂ " + self.t("home")])
        home.setData(0, ROLE, HOME)
        self.tree.addTopLevelItem(home)
        tools = registry.search(q)
        if not q:
            favs = [registry.BY_ID[i] for i in self.settings["favorites"] if i in registry.BY_ID]
            if favs:
                g = self._group("★ " + self.t("favorites"))
                for t in favs:
                    self._tool_item(g, t)
            rec = [registry.BY_ID[i] for i in self.settings["recent_tools"] if i in registry.BY_ID][:5]
            if rec:
                g = self._group("🕘 " + self.t("recent"))
                for t in rec:
                    self._tool_item(g, t)
        for cid, names in registry.CATEGORIES:
            items = [t for t in tools if t.category == cid]
            if not items:
                continue
            g = self._group(names[self.lang])
            for t in items:
                self._tool_item(g, t)
        self.tree.expandAll()

    def _on_item(self, item, _col=0):
        tid = item.data(0, ROLE)
        if tid:
            self.show_tool(tid)

    # ------------------------------------------------------------------ pages
    def show_tool(self, tool_id):
        if tool_id != HOME and tool_id not in registry.BY_ID:
            return
        self.current = tool_id
        if tool_id not in self.pages:
            self.pages[tool_id] = self._make_home() if tool_id == HOME else self._make_tool_page(
                registry.BY_ID[tool_id])
            self.stack.addWidget(self.pages[tool_id])
        self.stack.setCurrentWidget(self.pages[tool_id])
        if tool_id != HOME:
            self.settings.add_recent_tool(tool_id)

    def _make_home(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 24)
        title = QLabel(self.t("welcome"))
        title.setObjectName("title")
        lay.addWidget(title)
        sub = QLabel(self.t("welcome_sub"))
        sub.setObjectName("muted")
        lay.addWidget(sub)
        lay.addSpacing(12)
        lay.addWidget(self._bold(self.t("recent")))
        rt = self.settings["recent_tools"]
        if rt:
            for tid in rt[:5]:
                if tid in registry.BY_ID:
                    b = QPushButton(registry.BY_ID[tid].name[self.lang])
                    b.setStyleSheet("text-align:left;")
                    b.clicked.connect(lambda _c=False, t=tid: self.show_tool(t))
                    lay.addWidget(b)
        else:
            lay.addWidget(self._muted(self.t("none")))
        lay.addSpacing(8)
        lay.addWidget(self._bold(self.t("recent_files")))
        self.recent_files = QListWidget()
        files = self.settings["recent_files"]
        self.recent_files.addItems(files)
        self.recent_files.itemActivated.connect(lambda it: self.open_file_in_crs(it.text()))
        lay.addWidget(self.recent_files, 1)
        if not files:
            lay.addWidget(self._muted(self.t("none")))
        return w

    def _bold(self, text):
        lb = QLabel(text)
        lb.setStyleSheet("font-weight:600; background:transparent;")
        return lb

    def _muted(self, text):
        lb = QLabel(text)
        lb.setObjectName("muted")
        return lb

    def _make_tool_page(self, tool):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 22, 28, 18)
        head = QHBoxLayout()
        title = QLabel(tool.name[self.lang])
        title.setObjectName("title")
        head.addWidget(title, 1)
        fav = QPushButton("")
        fav.clicked.connect(lambda _c=False, t=tool.id, b=fav: self._toggle_fav(t, b))
        self._style_fav(fav, tool.id)
        head.addWidget(fav)
        lay.addLayout(head)
        desc = QLabel(tool.desc[self.lang])
        desc.setObjectName("desc")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        lay.addSpacing(8)
        if tool.kind == "native":
            mod, cls = tool.page.split(":")
            page = getattr(importlib.import_module(mod), cls)(self)
            w.native = page
            lay.addWidget(page, 1)
        else:
            note = QLabel(self.t("legacy_note"))
            note.setObjectName("muted")
            note.setWordWrap(True)
            lay.addWidget(note)
            btn = QPushButton(self.t("open_classic"))
            btn.setObjectName("primary")
            btn.setMaximumWidth(280)
            btn.clicked.connect(lambda _c=False, t=tool: self.open_legacy(t))
            lay.addWidget(btn)
            lay.addStretch(1)
        return w

    def _style_fav(self, btn, tool_id):
        btn.setText(self.t("fav_remove") if self.settings.is_favorite(tool_id) else self.t("fav_add"))

    def _toggle_fav(self, tool_id, btn):
        self.settings.toggle_favorite(tool_id)
        self.settings.save()
        self._style_fav(btn, tool_id)
        self._populate()

    def open_legacy(self, tool):
        try:
            launcher.launch_legacy(tool.legacy_key)
            self.notify(self.t("opened_classic"))
        except OSError as e:
            self.notify("{} {}".format(self.t("launch_failed"), e), "error")

    def open_file_in_crs(self, path):
        self.show_tool("crs_manager")
        page = getattr(self.pages["crs_manager"], "native", None)
        if page:
            page.set_file(path)

    # ------------------------------------------------------------------ background tasks
    def run(self, fn, tool, inputs=None, params=None, on_done=None, success_msg=None, on_log=None, owner=None):
        """Run a GIS function in a worker thread with progress, cancel and notifications.

        ``owner`` is the QObject (usually the page) that ``on_done`` / ``on_log`` belong to; it defaults to the
        object a bound-method callback is bound to. If the owner is deleted while the task runs, those callbacks
        are skipped (they would touch deleted widgets); the shell still finishes the task and clears ``task``."""
        if self.task is not None:
            return None
        if owner is None:
            owner = next((o for o in (getattr(cb, "__self__", None) for cb in (on_done, on_log))
                          if isinstance(o, QObject)), None)

        def alive():
            return owner is None or shiboken6.isValid(owner)

        def log(msg):
            if alive():
                on_log(msg)

        def done(result):
            if on_done and alive():
                on_done(result)
            if success_msg:
                self.notify(success_msg)
            self.status_label.setText(self.t("done"))

        def failed(msg):
            self.notify("{}: {}".format(self.t("failed"), msg), "error")
            self.status_label.setText(self.t("failed"))

        def cancelled():
            self.notify(self.t("cancelled"))
            self.status_label.setText(self.t("cancelled"))

        def progress(i, n, text):
            if n > 0:
                self.progress.setRange(0, n)
                self.progress.setValue(i)

        def finished():
            self.task = None
            self.progress.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.busy_changed.emit(False)

        self.status_label.setText(self.t("working"))
        self.progress.setRange(0, 0)               # indeterminate until real progress arrives
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.busy_changed.emit(True)
        self.task = workers.run_task(fn, tool, inputs, params, on_done=done, on_error=failed,
                                     on_cancelled=cancelled, on_progress=progress, on_finished=finished,
                                     on_log=log if on_log else None)
        return self.task

    def cancel_task(self):
        if self.task is not None:
            self.task.cancel()

    # ------------------------------------------------------------------ automatic update check
    def auto_update_check(self):
        """Optional (default OFF) background check at most once a day; only ever notifies, never downloads."""
        from tools import update_manager as um
        from v2 import update_state
        u = self.settings["updates"]
        if not u.get("auto_check") or self.task is not None or not um.should_auto_check(u.get("last_check", "")):
            return
        pre = bool(u.get("prerelease"))

        def done(chk):
            if update_state.record_check(self.settings, chk) and u.get("notify"):
                self.notify(self.t("upd_toast", v=chk.latest.version))
        self.run(lambda ctx: um.check_for_updates(allow_prerelease=pre, opener=self.update_opener),
                 "updates.auto_check", params={"prerelease": pre}, on_done=done)

    # ------------------------------------------------------------------ notifications
    def notify(self, message, kind="info"):
        self.toast.setProperty("kind", kind)
        self.toast.style().unpolish(self.toast)
        self.toast.style().polish(self.toast)
        self.toast.setText(message)
        self.toast.adjustSize()
        c = self.centralWidget()
        self.toast.move(max(10, c.width() - self.toast.width() - 20), max(10, c.height() - self.toast.height() - 20))
        self.toast.raise_()
        self.toast.setVisible(True)
        self._toast_timer.start(5000)

    # ------------------------------------------------------------------ theme / language
    def apply_theme(self, name, save=True):
        self.settings["theme"] = name
        app = QApplication.instance()
        if app:
            app.setStyleSheet(themes.stylesheet(name))
        if save:
            self.settings.save()

    def set_lang(self, lang):
        if lang == self.lang:
            return
        self.lang = lang
        self.settings["lang"] = lang
        self.settings.save()
        cur = self.current
        self._build_ui()
        self.show_tool(cur)

    def restart_app(self):
        """Start a fresh V2 process and quit this one (used after an update or a rollback)."""
        try:
            launcher.start_detached(launcher.restart_command())
        except OSError as e:
            self.notify("{} {}".format(self.t("launch_failed"), e), "error")
            return
        self.close()
        app = QApplication.instance()
        if app:
            app.quit()

    # ------------------------------------------------------------------ service menu
    def open_logs(self):
        from tools.logging_manager import open_log_dir
        try:
            open_log_dir()
        except OSError as e:
            self.notify(str(e), "error")

    def export_diagnostics(self):
        from tools.logging_manager import get_manager
        default = "gisbox_diagnostics_{}.zip".format(datetime.date.today().strftime("%Y%m%d"))
        path, _ = QFileDialog.getSaveFileName(self, self.t("export_diag"), default, "ZIP (*.zip)")
        if not path:
            return
        try:
            if os.path.exists(path):
                if not self._confirm_overwrite(path):
                    raise FileExistsError(path)
                os.remove(path)
            get_manager().export_diagnostics(path)
            self.notify("{} {}".format(self.t("diag_saved"), path))
        except FileExistsError:
            self.notify(self.t("diag_exists"), "error")
        except OSError as e:
            self.notify(str(e), "error")

    def _confirm_overwrite(self, path):
        return QMessageBox.question(self, "GIS_BOX", path) == QMessageBox.StandardButton.Yes

    def show_env_check(self):
        from tools import env_check
        QMessageBox.information(self, self.t("env_check"), env_check.report())

    def show_about(self):
        QMessageBox.about(self, self.t("about"), "GIS_BOX {}\n\n{}".format(version.__version__, self.t("about_text")))

    # ------------------------------------------------------------------ lifecycle
    def closeEvent(self, ev):
        self.cancel_task()
        self.settings["window"] = {"w": self.width(), "h": self.height()}
        self.settings.save()
        super().closeEvent(ev)
