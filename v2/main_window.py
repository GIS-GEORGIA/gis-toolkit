"""GIS_BOX V2 main window: sidebar (search, favorites, recent, categories), home page with tool cards, tool pages,
status bar with progress + cancel, toast notifications, light/dark themes, Georgian/English."""
from __future__ import annotations

import datetime
import importlib
import os
import sys
import traceback

import shiboken6
from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter,
                               QStackedWidget, QStatusBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from tools import version
from v2 import launcher, registry, themes, workers
from v2.i18n import tr
from v2.widgets import FlowLayout, ToolCard, badge_icon

ROLE = Qt.ItemDataRole.UserRole
HOME = "__home__"
SIDE_MIN, SIDE_MAX, SIDE_DEFAULT = 220, 460, 290
CLOSE_WAIT_MS = 15000            # closing with a running task: wait at most this long for it to stop


def log_ui_error(where, exc):
    """Write an unexpected UI-side exception with its traceback to the GIS_BOX log (never raises)."""
    try:
        from tools.logging_manager import USER, get_manager
        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        get_manager().log(USER, "UI error in {}: {}\n{}".format(where, exc, text), tool="v2")
    except Exception:                                          # noqa: BLE001 - logging must never break the UI
        pass


def _int(value, default):
    """A stored window size, or ``default`` when the settings file holds something else."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class MainWindow(QMainWindow):
    busy_changed = Signal(bool)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.lang = settings["lang"]
        self.current = HOME
        self.task = None
        self._task_tool = ""
        self._task_settled = False                 # result already delivered, thread only finishing up
        self._closing = False                      # close requested while a task was running
        self._force_close = False
        self._home_dirty = True
        self.pages = {}
        self.update_opener = None                  # tests inject a fake network
        win = settings["window"]
        self.setMinimumSize(900, 600)
        self.resize(_int(win.get("w"), 1180), _int(win.get("h"), 760))
        self.setStatusBar(QStatusBar())
        self._build_status()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)
        self.apply_theme(settings["theme"], save=False)
        self._build_ui()
        self.show_tool(HOME)
        if win.get("max"):
            self.setWindowState(Qt.WindowState.WindowMaximized)
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self.focus_search)
        QTimer.singleShot(2500, self, self.auto_update_check)

    def t(self, key, **f):
        return tr(self.lang, key, **f)

    # ------------------------------------------------------------------ construction
    def _build_status(self):
        sb = self.statusBar()
        self.status_label = QLabel("")
        self.status_label.setMinimumWidth(80)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setVisible(False)
        self.cancel_btn = QPushButton("")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_task)
        sb.addWidget(self.status_label, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.cancel_btn)

    def _build_ui(self):
        """(Re)build everything that carries text - called again when the language changes."""
        self.pages.clear()
        self._home_dirty = True
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        side = QWidget()
        side.setObjectName("sidebar")
        side.setMinimumWidth(SIDE_MIN)
        side.setMaximumWidth(SIDE_MAX)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 14, 10, 10)
        sl.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(badge_icon("GB", themes.palette(self.settings["theme"])["accent"], 30).pixmap(30, 30))
        head.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        brand = QLabel("GIS_BOX")
        brand.setObjectName("brand")
        names.addWidget(brand)
        ver = QLabel("{} {}".format(self.t("version"), version.__version__))
        ver.setObjectName("muted")
        names.addWidget(ver)
        head.addLayout(names, 1)
        sl.addLayout(head)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("{}   (Ctrl+F)".format(self.t("search")))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._populate)
        self.search_edit.returnPressed.connect(self._open_first_result)
        sl.addWidget(self.search_edit)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(10)
        self.tree.setRootIsDecorated(False)
        self.tree.setIconSize(QSize(20, 20))
        self.tree.itemClicked.connect(self._on_item)
        self.tree.itemActivated.connect(self._on_item)          # Enter on the keyboard
        sl.addWidget(self.tree, 1)
        self.splitter.addWidget(side)

        self.stack = QStackedWidget()
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        side_w = min(SIDE_MAX, max(SIDE_MIN, _int(self.settings["window"].get("side"), SIDE_DEFAULT)))
        self.splitter.setSizes([side_w, max(400, self.width() - side_w)])
        self.setCentralWidget(self.splitter)

        self.toast = QLabel("", self.splitter)
        self.toast.setObjectName("toast")
        self.toast.setWordWrap(True)
        self.toast.setVisible(False)

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
    def tool_icon(self, tool):
        return badge_icon(registry.badge(tool), themes.category_color(tool.category), 20)

    def _group(self, title):
        g = QTreeWidgetItem([title])
        g.setFlags(Qt.ItemFlag.ItemIsEnabled)                 # a heading: not selectable
        f = g.font(0)
        f.setBold(True)
        g.setFont(0, f)
        g.setForeground(0, QColor(themes.palette(self.settings["theme"])["muted"]))
        g.setSizeHint(0, QSize(0, 30))
        self.tree.addTopLevelItem(g)
        return g

    def _tool_item(self, parent, tool):
        it = QTreeWidgetItem([tool.name[self.lang]])
        it.setData(0, ROLE, tool.id)
        it.setIcon(0, self.tool_icon(tool))
        it.setToolTip(0, tool.desc[self.lang])
        parent.addChild(it)
        return it

    def _populate(self, *_):
        q = self.search_edit.text() if hasattr(self, "search_edit") else ""
        self.tree.clear()
        home = QTreeWidgetItem(["⌂  " + self.t("home")])
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
                g = self._group("◷ " + self.t("recent"))      # not an emoji: Linux often has no emoji font
                for t in rec:
                    self._tool_item(g, t)
        for cid, names in registry.CATEGORIES:
            items = [t for t in tools if t.category == cid]
            if not items:
                continue
            g = self._group(names[self.lang])
            g.setToolTip(0, names[self.lang])                   # long Georgian names may be elided
            for t in items:
                self._tool_item(g, t)
        if q and not tools:
            empty = QTreeWidgetItem([self.t("no_results", q=q)])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.tree.addTopLevelItem(empty)
        self.tree.expandAll()
        self._select_current()

    def _select_current(self):
        """Highlight the open tool in the sidebar (first occurrence - favorites / recent come first)."""
        it = self._find_item(getattr(self, "current", HOME))
        self.tree.blockSignals(True)
        if it is not None:
            self.tree.setCurrentItem(it)
        else:
            self.tree.clearSelection()
        self.tree.blockSignals(False)

    def _find_item(self, tool_id):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.data(0, ROLE) == tool_id:
                return top
            for j in range(top.childCount()):
                if top.child(j).data(0, ROLE) == tool_id:
                    return top.child(j)
        return None

    def _on_item(self, item, _col=0):
        tid = item.data(0, ROLE)
        if tid:
            self.show_tool(tid)

    def _open_first_result(self):
        q = self.search_edit.text().strip()
        found = registry.search(q) if q else []
        if found:
            self.show_tool(found[0].id)

    def focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ------------------------------------------------------------------ pages
    def show_tool(self, tool_id):
        if tool_id != HOME and tool_id not in registry.BY_ID:
            return
        self.current = tool_id
        if tool_id == HOME and self._home_dirty and HOME in self.pages:
            self._drop_page(HOME)                               # favorites / recents changed: rebuild the cards
        if tool_id not in self.pages:
            self.pages[tool_id] = self._make_home() if tool_id == HOME else self._make_tool_page(
                registry.BY_ID[tool_id])
            self.stack.addWidget(self.pages[tool_id])
            if tool_id == HOME:
                self._home_dirty = False
        self.stack.setCurrentWidget(self.pages[tool_id])
        if tool_id != HOME:
            self.settings.add_recent_tool(tool_id)
            self._home_dirty = True
        self._select_current()

    def _drop_page(self, tool_id):
        w = self.pages.pop(tool_id, None)
        if w is not None:
            self.stack.removeWidget(w)
            w.deleteLater()

    def _make_home(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        w = QWidget()
        outer.setWidget(w)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(32, 26, 32, 24)
        lay.setSpacing(10)
        title = QLabel(self.t("welcome"))
        title.setObjectName("title")
        title.setWordWrap(True)
        lay.addWidget(title)
        sub = QLabel(self.t("welcome_sub"))
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        rec = [registry.BY_ID[i] for i in self.settings["recent_tools"] if i in registry.BY_ID][:6]
        if rec:
            lay.addSpacing(6)
            lay.addWidget(self._caps(self.t("recent")))
            box = QWidget()
            fl = FlowLayout(box, spacing=8)
            for t in rec:
                b = QPushButton(self.tool_icon(t), " " + t.name[self.lang])
                b.setObjectName("chip")
                b.setIconSize(QSize(18, 18))
                b.setToolTip(t.desc[self.lang])
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _c=False, tid=t.id: self.show_tool(tid))
                fl.addWidget(b)
            lay.addWidget(box)

        self.cards = []
        favs = set(self.settings["favorites"])
        for cid, names, tools in registry.by_category():
            lay.addSpacing(8)
            lay.addWidget(self._caps("{}  ·  {}".format(names[self.lang], self.t("tools_n", n=len(tools)))))
            box = QWidget()
            fl = FlowLayout(box, spacing=12)
            for t in tools:
                c = ToolCard(t, self.lang, badge_icon(registry.badge(t), themes.category_color(cid), 28),
                             favorite=t.id in favs)
                c.clicked.connect(lambda _c=False, tid=t.id: self.show_tool(tid))
                fl.addWidget(c)
                self.cards.append(c)
            lay.addWidget(box)
        if self.cards:                                          # one card height for a tidy grid
            h = max(c.height() for c in self.cards)
            for c in self.cards:
                c.setFixedHeight(h)

        lay.addSpacing(8)
        lay.addWidget(self._caps(self.t("recent_files")))
        files = self.settings["recent_files"]
        self.recent_files = QListWidget()
        self.recent_files.addItems(files)
        self.recent_files.setToolTip(self.t("open_file_hint"))
        self.recent_files.itemActivated.connect(lambda it: self.open_file_in_crs(it.text()))
        self.recent_files.setVisible(bool(files))
        self.recent_files.setFixedHeight(min(220, 12 + 30 * max(1, len(files))))
        lay.addWidget(self.recent_files)
        if not files:
            lay.addWidget(self._muted(self.t("none")))
        lay.addStretch(1)
        return outer

    def _caps(self, text):
        lb = QLabel(text.upper() if self.lang == "en" else text)
        lb.setObjectName("caps")
        return lb

    def _bold(self, text):
        lb = QLabel(text)
        lb.setObjectName("section")
        return lb

    def _muted(self, text):
        lb = QLabel(text)
        lb.setObjectName("muted")
        return lb

    def _make_tool_page(self, tool):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 20, 28, 16)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(badge_icon(registry.badge(tool), themes.category_color(tool.category), 36).pixmap(36, 36))
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(0)
        cat = QLabel(registry.category_name(tool.category, self.lang))
        cat.setObjectName("caps")
        names.addWidget(cat)
        title = QLabel(tool.name[self.lang])
        title.setObjectName("title")
        title.setWordWrap(True)
        names.addWidget(title)
        head.addLayout(names, 1)
        fav = QPushButton("")
        fav.setObjectName("ghost")
        fav.setCheckable(True)
        fav.setCursor(Qt.CursorShape.PointingHandCursor)
        fav.clicked.connect(lambda _c=False, t=tool.id, b=fav: self._toggle_fav(t, b))
        self._style_fav(fav, tool.id)
        head.addWidget(fav, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        desc = QLabel(tool.desc[self.lang])
        desc.setObjectName("desc")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        line = QFrame()
        line.setObjectName("hline")
        line.setFixedHeight(1)
        lay.addSpacing(4)
        lay.addWidget(line)
        lay.addSpacing(6)
        if tool.kind == "native":
            try:
                mod, cls = tool.page.split(":")
                page = getattr(importlib.import_module(mod), cls)(self)
            except Exception as e:                              # noqa: BLE001 - shown on the page, logged
                log_ui_error("open " + tool.id, e)
                lay.addWidget(self._error_panel(tool, e), 0)
                lay.addStretch(1)
                w.native = None
                w.error = e
                return w
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

    def _error_panel(self, tool, exc):
        box = QFrame()
        box.setObjectName("errorPanel")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 14, 16, 14)
        head = QLabel(self.t("page_failed"))
        head.setObjectName("section")
        bl.addWidget(head)
        msg = QLabel("{}: {}".format(type(exc).__name__, exc))
        msg.setObjectName("error")
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bl.addWidget(msg)
        hint = QLabel(self.t("page_failed_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        bl.addWidget(hint)
        row = QHBoxLayout()
        retry = QPushButton(self.t("retry"))
        retry.setObjectName("primary")
        retry.clicked.connect(lambda _c=False, tid=tool.id: self.retry_tool(tid))
        row.addWidget(retry)
        logs = QPushButton(self.t("open_logs"))
        logs.clicked.connect(self.open_logs)
        row.addWidget(logs)
        env = QPushButton(self.t("env_check"))
        env.clicked.connect(self.show_env_check)
        row.addWidget(env)
        row.addStretch(1)
        bl.addLayout(row)
        return box

    def retry_tool(self, tool_id):
        """Build a page again that failed to open (e.g. after installing a missing package)."""
        self._drop_page(tool_id)
        self.show_tool(tool_id)

    def _style_fav(self, btn, tool_id):
        on = self.settings.is_favorite(tool_id)
        btn.setText(self.t("fav_remove") if on else self.t("fav_add"))
        btn.setChecked(on)

    def _toggle_fav(self, tool_id, btn):
        self.settings.toggle_favorite(tool_id)
        self.settings.save()
        self._style_fav(btn, tool_id)
        self._home_dirty = True
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
        are skipped (they would touch deleted widgets); the shell still finishes the task and clears ``task``.
        An exception raised by a callback is logged and shown; it never leaves the shell in a busy state.
        Returns the task, or None (and tells the user) when another task is still running."""
        if self.task is not None:
            self.notify(self.t("busy_refused"), "error")
            return None
        if owner is None:
            owner = next((o for o in (getattr(cb, "__self__", None) for cb in (on_done, on_log))
                          if isinstance(o, QObject)), None)

        def alive():
            return owner is None or shiboken6.isValid(owner)

        def guarded(where, cb, *a):
            try:
                cb(*a)
            except Exception as e:                              # noqa: BLE001 - a page bug must not kill the shell
                log_ui_error("{} ({})".format(where, tool), e)
                self.notify("{} {}: {}".format(self.t("ui_error"), type(e).__name__, e), "error")
                return False
            return True

        def log(msg):
            if alive():
                guarded("on_log", on_log, msg)

        def done(result):
            self._task_settled = True
            ok = guarded("on_done", on_done, result) if on_done and alive() else True
            if not ok:
                self.status_label.setText(self.t("failed"))
                return
            if success_msg:
                self.notify(success_msg)
            self.status_label.setText(self.t("done"))

        def failed(msg):
            self._task_settled = True
            self.notify("{}: {}".format(self.t("failed"), msg), "error")
            self.status_label.setText(self.t("failed"))

        def cancelled():
            self._task_settled = True
            self.notify(self.t("cancelled"))
            self.status_label.setText(self.t("cancelled"))

        def progress(i, n, text):
            if n > 0:
                self.progress.setRange(0, n)
                self.progress.setValue(min(i, n))
            if text and not self._cancel_requested():
                self.status_label.setText("{} {}".format(self.t("working"), text))

        def finished():
            self.task = None
            self._task_tool = ""
            self.progress.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText(self.t("cancel"))
            self.busy_changed.emit(False)
            if self._closing:                                   # the user asked to close while it ran
                QTimer.singleShot(0, self, self.close)

        self._task_settled = False
        self._task_tool = tool
        self.status_label.setText(self.t("working"))
        self.progress.setRange(0, 0)               # indeterminate until real progress arrives
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText(self.t("cancel"))
        self.busy_changed.emit(True)
        self.task = workers.run_task(fn, tool, inputs, params, on_done=done, on_error=failed,
                                     on_cancelled=cancelled, on_progress=progress, on_finished=finished,
                                     on_log=log if on_log else None)
        return self.task

    def _cancel_requested(self):
        ev = getattr(self.task, "cancel_event", None)
        return ev is not None and ev.is_set()

    def cancel_task(self):
        if self.task is not None:
            self.task.cancel()
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText(self.t("cancelling"))
            self.status_label.setText(self.t("cancelling"))

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
                 "updates.auto_check", params={"prerelease": pre}, on_done=done, owner=self)

    # ------------------------------------------------------------------ notifications
    def notify(self, message, kind="info"):
        self.toast.setProperty("kind", kind)
        self.toast.style().unpolish(self.toast)
        self.toast.style().polish(self.toast)
        self.toast.setText(message)
        self._place_toast()
        self.toast.raise_()
        self.toast.setVisible(True)
        self._toast_timer.start(8000 if kind == "error" else 5000)

    def _place_toast(self):
        c = self.centralWidget()
        if c is None or not shiboken6.isValid(self.toast):
            return
        self.toast.setMaximumWidth(max(220, min(520, c.width() - 40)))
        self.toast.adjustSize()
        self.toast.move(max(10, c.width() - self.toast.width() - 20),
                        max(10, c.height() - self.toast.height() - 20))

    def _hide_toast(self):
        if shiboken6.isValid(self.toast):
            self.toast.setVisible(False)

    def resizeEvent(self, ev):                                 # noqa: N802 - Qt API
        super().resizeEvent(ev)
        if hasattr(self, "toast") and shiboken6.isValid(self.toast) and self.toast.isVisible():
            self._place_toast()

    # ------------------------------------------------------------------ theme / language
    def apply_theme(self, name, save=True):
        self.settings["theme"] = name
        app = QApplication.instance()
        if app:
            themes.apply(app, name)
        if hasattr(self, "tree"):
            self._populate()                                    # heading colours come from the palette
        if save:
            self.settings.save()

    def set_lang(self, lang):
        if lang == self.lang:
            return
        self.lang = lang
        self.settings["lang"] = lang
        self.settings.save()
        cur = self.current
        self._remember_layout()
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
        try:
            text = env_check.report()
        except Exception as e:                                  # noqa: BLE001
            log_ui_error("env_check", e)
            text = "{}: {}".format(type(e).__name__, e)
        QMessageBox.information(self, self.t("env_check"), text)

    def show_about(self):
        QMessageBox.about(self, self.t("about"), "GIS_BOX {}\n\n{}".format(version.__version__, self.t("about_text")))

    # ------------------------------------------------------------------ lifecycle
    def _confirm_close_running(self):
        """Ask before closing while a task runs (tests replace this)."""
        tool = self._task_tool.split(".")[0]
        name = registry.BY_ID[tool].name[self.lang] if tool in registry.BY_ID else self._task_tool
        return QMessageBox.question(self, self.t("close_running_title"), self.t("close_running", tool=name)) \
            == QMessageBox.StandardButton.Yes

    def _close_timed_out(self):
        if self.task is None:
            return
        try:
            from tools.logging_manager import USER, get_manager
            get_manager().log(USER, "closing: task '{}' did not stop within {} s".format(
                self._task_tool, CLOSE_WAIT_MS // 1000), tool="v2")
        except Exception:                                       # noqa: BLE001
            pass
        self._force_close = True
        self.close()

    def _remember_layout(self):
        win = dict(self.settings["window"])
        maxed = bool(self.windowState() & Qt.WindowState.WindowMaximized)
        win["max"] = maxed
        if not maxed:
            win["w"], win["h"] = self.width(), self.height()
        if hasattr(self, "splitter") and shiboken6.isValid(self.splitter):
            sizes = self.splitter.sizes()
            if sizes and sizes[0] > 0:
                win["side"] = sizes[0]
        self.settings["window"] = win

    def closeEvent(self, ev):                                  # noqa: N802 - Qt API
        if self.task is not None and not self._task_settled and not self._force_close:
            # Worker threads are daemons: quitting now would kill one in the middle of writing a file.
            if not self._closing:
                if not self._confirm_close_running():
                    ev.ignore()
                    return
                self._closing = True
                self.cancel_task()
                self.status_label.setText(self.t("closing_wait"))
                QTimer.singleShot(CLOSE_WAIT_MS, self, self._close_timed_out)
            ev.ignore()
            return
        self.cancel_task()
        self._remember_layout()
        self.settings.save()
        super().closeEvent(ev)


def install_excepthook(window):
    """Log unexpected exceptions (e.g. raised in a Qt slot) and show them as an error toast instead of only
    printing to a console the user never sees. The application keeps running."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return previous(exc_type, exc, tb)
        if exc is None:
            exc = exc_type()
        if exc.__traceback__ is None and tb is not None:
            exc = exc.with_traceback(tb)
        log_ui_error("unhandled", exc)
        try:
            if shiboken6.isValid(window):
                window.notify("{} {}: {}".format(window.t("ui_error"), exc_type.__name__, exc), "error")
        except Exception:                                       # noqa: BLE001
            pass
        if sys.stderr is not None:                              # frozen windowed builds have no console
            traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = hook
    return hook
