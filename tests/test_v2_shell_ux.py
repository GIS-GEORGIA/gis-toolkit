# -*- coding: utf-8 -*-
"""V2 shell: home cards, sidebar state, error / busy / cancel / close handling, layout persistence, themes."""
import json
import os
import sys
import threading
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from v2 import main_window as mw
from v2 import registry, themes
from v2.main_window import HOME, ROLE, MainWindow
from v2.settings import Settings


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path):
    w = MainWindow(Settings(str(tmp_path / "s.json")))
    yield w
    w.task = None
    w.close()


def wait_for(cond, timeout=15):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return cond()


# ---------------------------------------------------------------- home / sidebar
def test_home_has_one_card_per_tool_and_a_card_opens_its_tool(win):
    assert sorted(c.tool_id for c in win.cards) == sorted(t.id for t in registry.TOOLS)
    assert len({c.height() for c in win.cards}) == 1                  # a tidy grid: one card height
    card = [c for c in win.cards if c.tool_id == "line_buffer"][0]
    card.click()
    assert win.current == "line_buffer" and win.stack.currentWidget() is win.pages["line_buffer"]


def test_home_is_rebuilt_with_new_favorites_and_recents(win):
    win.show_tool("rename")
    win.settings.toggle_favorite("rename")
    win._home_dirty = True
    win.show_tool(HOME)
    fav_cards = [c for c in win.cards if c.tool_id == "rename"]
    assert fav_cards and any(lb.text() == "★" for lb in fav_cards[0].findChildren(type(win.status_label)))
    from PySide6.QtWidgets import QPushButton
    chips = [b for b in win.pages[HOME].findChildren(QPushButton) if b.objectName() == "chip"]
    assert any(registry.BY_ID["rename"].name[win.lang] in b.text() for b in chips)


def test_sidebar_highlights_the_open_tool_and_enter_in_search_opens_first_hit(win):
    win.show_tool("crs_manager")
    assert win.tree.currentItem().data(0, ROLE) == "crs_manager"
    win.search_edit.setText("buffer")
    win._open_first_result()
    assert win.current == "line_buffer" and win.tree.currentItem().data(0, ROLE) == "line_buffer"
    win.search_edit.setText("zzzz-nothing")
    texts = [win.tree.topLevelItem(i).text(0) for i in range(win.tree.topLevelItemCount())]
    assert any("zzzz-nothing" in t for t in texts)                    # "nothing found" row
    win.search_edit.setText("")


def test_every_tool_has_a_badge_and_icon(win):
    for t in registry.TOOLS:
        assert 1 <= len(registry.badge(t)) <= 4
        assert not win.tool_icon(t).isNull()


# ---------------------------------------------------------------- errors
def test_page_that_fails_to_build_shows_an_error_panel_and_can_be_retried(win, monkeypatch):
    real = mw.importlib.import_module

    def broken(name):
        if name == "v2.pages.rename_page":
            raise ImportError("No module named 'fancy_dependency'")
        return real(name)
    monkeypatch.setattr(mw.importlib, "import_module", broken)
    win.show_tool("rename")                                            # must not raise
    page = win.pages["rename"]
    assert page.native is None and "fancy_dependency" in str(page.error)
    monkeypatch.setattr(mw.importlib, "import_module", real)           # "package installed"
    win.retry_tool("rename")
    assert win.pages["rename"].native is not None and win.current == "rename"


def test_second_task_is_refused_with_a_message(win):
    assert win.run(lambda ctx: time.sleep(0.3), "t.busy") is not None
    assert win.run(lambda ctx: 1, "t.second") is None
    assert win.toast.property("kind") == "error" and win.toast.text() == win.t("busy_refused")
    assert wait_for(lambda: win.task is None)


def test_exception_in_a_result_callback_is_reported_and_the_shell_recovers(win, monkeypatch):
    logged = []
    monkeypatch.setattr(mw, "log_ui_error", lambda where, e: logged.append((where, e)))

    def bad(_result):
        raise KeyError("missing column")
    win.run(lambda ctx: 1, "t.badcb", on_done=bad)
    assert wait_for(lambda: win.task is None)
    assert logged and isinstance(logged[0][1], KeyError)
    assert win.toast.property("kind") == "error" and "missing column" in win.toast.text()
    assert win.status_label.text() == win.t("failed")
    assert win.run(lambda ctx: 2, "t.next") is not None                # not stuck in "busy"
    assert wait_for(lambda: win.task is None)


def test_excepthook_logs_and_shows_unexpected_errors(win, monkeypatch):
    logged = []
    monkeypatch.setattr(mw, "log_ui_error", lambda where, e: logged.append(e))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)             # restored after the test
    hook = mw.install_excepthook(win)
    try:
        raise ValueError("boom in a slot")
    except ValueError:
        hook(*sys.exc_info())
    assert logged and "boom in a slot" in win.toast.text() and win.toast.property("kind") == "error"


# ---------------------------------------------------------------- progress / cancel / close
def test_progress_text_and_cancelling_state(win):
    go = threading.Event()

    def work(ctx):
        ctx.progress(1, 4, "layer roads")
        go.wait(5)
        ctx.check_cancelled()
    win.run(work, "t.prog")
    assert wait_for(lambda: "layer roads" in win.status_label.text())
    assert win.progress.maximum() == 4 and win.progress.value() == 1
    win.cancel_task()
    assert not win.cancel_btn.isEnabled() and win.cancel_btn.text() == win.t("cancelling")
    go.set()
    assert wait_for(lambda: win.task is None)
    assert win.cancel_btn.isEnabled() and win.cancel_btn.text() == win.t("cancel")
    assert win.status_label.text() == win.t("cancelled")


def test_closing_during_a_task_asks_then_waits_for_the_worker(win, monkeypatch):
    go, stopped = threading.Event(), threading.Event()

    def work(ctx):
        while not go.is_set():
            if ctx.cancelled():
                stopped.set()                      # the worker saw the cancel and can clean up
                break
            time.sleep(0.01)
        ctx.check_cancelled()
    answers = [False, True]
    monkeypatch.setattr(win, "_confirm_close_running", lambda: answers.pop(0))
    win.show()
    win.run(work, "gdb2pg.import")
    assert win.close() is False and win.isVisible() and win.task is not None   # declined: keeps running
    assert win.close() is False and win.isVisible()                            # accepted: cancel, wait
    assert stopped.wait(5) and wait_for(lambda: not win.isVisible())
    assert win.task is None


def test_closing_when_idle_never_asks(win, monkeypatch):
    monkeypatch.setattr(win, "_confirm_close_running", lambda: pytest.fail("must not ask"))
    win.show()
    assert win.close() is True


# ---------------------------------------------------------------- layout / settings / themes
def test_window_layout_is_remembered_and_bad_values_are_ignored(qapp, tmp_path):
    p = str(tmp_path / "s.json")
    w = MainWindow(Settings(p))
    w.splitter.setSizes([350, 800])
    w.close()
    assert Settings(p)["window"]["side"] == 350
    data = json.load(open(p, encoding="utf-8"))
    data["window"].update(side="wide", w=None, h="tall")
    json.dump(data, open(p, "w", encoding="utf-8"))
    w2 = MainWindow(Settings(p))                                       # must not raise
    assert mw.SIDE_MIN <= w2.splitter.sizes()[0] <= mw.SIDE_MAX
    w2.close()


def test_settings_save_failure_leaves_no_temp_file(tmp_path, monkeypatch):
    s = Settings(str(tmp_path / "s.json"))
    s["tool_state"] = {"bad": object()}                                # not JSON-serialisable
    assert s.save() is False
    assert [f for f in os.listdir(tmp_path) if f.endswith(".tmp")] == []


def test_themes_have_interaction_states_and_a_matching_palette(qapp):
    from PySide6.QtGui import QPalette
    for name in ("light", "dark"):
        css = themes.stylesheet(name)
        for state in (":focus", ":hover", ":disabled", ":pressed", ":checked", "QGroupBox", "#card"):
            assert state in css, (name, state)
        pal = themes.qpalette(name)
        assert pal.color(QPalette.ColorRole.Window).name() == themes.palette(name)["window"]
        assert pal.color(QPalette.ColorRole.Highlight).name() == themes.palette(name)["accent"]
    assert set(themes.PALETTES["light"]) == set(themes.PALETTES["dark"])
    assert all(themes.category_color(c).startswith("#") for c, _ in registry.CATEGORIES)


def test_theme_switch_recolors_sidebar_headings(win):
    win.apply_theme("dark")
    heads = [win.tree.topLevelItem(i) for i in range(win.tree.topLevelItemCount())
             if not win.tree.topLevelItem(i).data(0, ROLE)]
    assert heads and heads[0].foreground(0).color().name() == themes.palette("dark")["muted"]
    win.apply_theme("light")


def test_toast_wraps_inside_a_small_window(win):
    win.resize(900, 600)
    win.notify("x " * 400, "error")
    assert win.toast.width() <= win.centralWidget().width() - 20


# ---------------------------------------------------------------- deferred calls on deleted pages
def test_db_transfer_deferred_call_is_dropped_when_the_page_is_deleted(win, monkeypatch):
    import shiboken6
    from v2.pages.db_transfer_page import DbTransferPage
    errors, ran = [], []
    monkeypatch.setattr(sys, "excepthook", lambda *exc: errors.append(exc[1]))
    p = DbTransferPage(win)
    win.task = object()                                                # busy: the call is retried later
    p._when_free(lambda: ran.append(1))
    shiboken6.delete(p)
    win.task = None
    t0 = time.time()
    while time.time() - t0 < 0.3:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert ran == [] and errors == []


# ---------------------------------------------------------------- combo-box arrow (both themes)
def test_combo_arrow_assets_exist_match_the_palette_and_load(qapp):
    from PySide6.QtCore import QFile
    from PySide6.QtGui import QImage
    assert themes.register_assets()                                   # SVG plugin + files present
    for name in ("light", "dark"):
        css = themes.stylesheet(name)
        for state, key in themes.ARROW_STATES.items():
            fname = themes.arrow_asset(name, state)
            assert "url({}:{})".format(themes.ASSET_PREFIX, fname) in css
            svg = (themes.ASSET_DIR / fname).read_text(encoding="ascii")
            assert themes.palette(name)[key] in svg                   # chevron colour follows the theme
            assert QFile.exists("{}:{}".format(themes.ASSET_PREFIX, fname))
            img = QImage("{}:{}".format(themes.ASSET_PREFIX, fname))
            assert not img.isNull() and img.width() == 12
        for sel in ("QComboBox::drop-down", "QComboBox::down-arrow:disabled", "QComboBox::down-arrow:on"):
            assert sel in css
        assert "down-arrow" not in themes.stylesheet(name, arrows=False)


def _arrow_pixels(combo, color):
    """Count pixels close to ``color`` in the right-hand arrow area of a rendered combo box."""
    from PySide6.QtGui import QColor
    img = combo.grab().toImage()
    want = QColor(color)
    n = 0
    for x in range(img.width() - 26, img.width() - 4):
        for y in range(2, img.height() - 2):
            c = img.pixelColor(x, y)
            if abs(c.red() - want.red()) + abs(c.green() - want.green()) + abs(c.blue() - want.blue()) < 60:
                n += 1
    return n


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_combo_arrow_is_drawn_in_theme_colour_for_normal_focus_and_disabled(win, theme):
    from PySide6.QtWidgets import QComboBox
    win.apply_theme(theme)
    p = themes.palette(theme)
    box = QComboBox(win)
    box.addItems(["EPSG:32638", "ქართული"])
    box.resize(220, 32)
    box.show()
    QCoreApplication.processEvents()
    assert _arrow_pixels(box, p["muted"]) > 4                         # normal: visible chevron
    box.setFocus()
    QCoreApplication.processEvents()
    if box.hasFocus():                                                # offscreen may not give focus
        assert _arrow_pixels(box, p["accent"]) > 4
    box.setEnabled(False)
    QCoreApplication.processEvents()
    assert _arrow_pixels(box, p["border_strong"]) > 4
    box.setEnabled(True)
    # Wayland only grants a popup after real user input on the parent window ("Failed to create grabbing
    # popup") - also for a plain, unstyled QComboBox - so a programmatic showPopup() cannot be checked there.
    if QApplication.instance().platformName() != "wayland":
        box.showPopup()                                               # native drop-down still works
        assert wait_for(lambda: box.view().isVisible(), 3)
        box.hidePopup()
    box.deleteLater()
    win.apply_theme("light")


def test_every_page_combo_box_gets_the_themed_arrow(win):
    """Every combo box on every tool page shows the themed chevron, in both themes."""
    from PySide6.QtWidgets import QComboBox
    for theme in ("dark", "light"):
        win.apply_theme(theme)
        colour = themes.palette(theme)
        pages_with_combos, checked = set(), 0
        for t in registry.TOOLS:
            win.show_tool(t.id)
            QCoreApplication.processEvents()
            for c in win.pages[t.id].findChildren(QComboBox):
                pages_with_combos.add(t.id)
                if c.width() < 60:
                    c.resize(160, max(c.height(), 30))
                key = "muted" if c.isEnabled() else "border_strong"
                assert _arrow_pixels(c, colour[key]) > 4 or (c.hasFocus() and _arrow_pixels(c, colour["accent"]) > 4),                     (theme, t.id, c.objectName())
                checked += 1
        assert len(pages_with_combos) >= 10 and checked >= 19, (pages_with_combos, checked)


# ---------------------------------------------------------------- worker cleanup after cancel
def test_cancelled_task_releases_the_worker_and_a_new_task_can_start(win):
    from v2 import workers
    before = len(workers._alive)
    go = threading.Event()

    def long(ctx):
        for _ in range(500):
            ctx.check_cancelled()
            go.wait(0.01)
    win.run(long, "t.long")
    win.cancel_task()
    t0 = time.time()
    assert wait_for(lambda: win.task is None, 5)
    assert time.time() - t0 < 2                                       # cancel noticed at the next checkpoint
    assert len(workers._alive) == before                              # bridge + task released
    assert not [th for th in threading.enumerate() if th.name == "gisbox-task-t.long"] or \
        wait_for(lambda: not [th for th in threading.enumerate() if th.name == "gisbox-task-t.long"], 3)
    done = []
    assert win.run(lambda ctx: 42, "t.after", on_done=done.append) is not None
    assert wait_for(lambda: done == [42])


# ---------------------------------------------------------------- build diagnostics
def test_selftest_all_pages_writes_a_report(qapp, tmp_path, monkeypatch):
    import gis_box_v2
    monkeypatch.setenv("GIS_BOX_V2_DIR", str(tmp_path / "cfg"))
    report = tmp_path / "report.txt"
    rc = gis_box_v2.main(["--selftest", "--all-pages", "--report", str(report)])
    text = report.read_text(encoding="utf-8")
    assert rc == 0 and text.strip().endswith("RESULT OK"), text
    assert text.count(" dark OK") == len(registry.TOOLS)
    assert "theme assets (SVG chevrons / ticks): OK" in text and "GIS round trip" in text
    assert "asset folder:" in text and "(source)" in text and "FAILED" not in text


def test_selftest_rejects_assets_from_outside_a_frozen_bundle(qapp, tmp_path, monkeypatch):
    import gis_box_v2
    monkeypatch.setenv("GIS_BOX_V2_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)   # pretend: packaged app
    report = tmp_path / "r.txt"
    assert gis_box_v2.main(["--selftest", "--all-pages", "--report", str(report)]) == 1
    text = report.read_text(encoding="utf-8")
    assert "asset folder FAILED: outside the packaged application" in text and text.strip().endswith("RESULT FAILED")


def test_qt_load_failure_names_the_real_problem(monkeypatch):
    """A packaged app on a minimal Linux said "PySide6 is not installed" although only libEGL was missing."""
    import gis_box_v2
    missing_pkg = ModuleNotFoundError("No module named 'PySide6'", name="PySide6")
    assert "pip install PySide6" in gis_box_v2._qt_import_problem(missing_pkg)
    lib = ImportError("libEGL.so.1: cannot open shared object file: No such file or directory")
    monkeypatch.setattr(sys, "platform", "linux")
    text = gis_box_v2._qt_import_problem(lib)
    assert "could not be loaded" in text and "libEGL.so.1" in text and "apt install" in text
    assert "not installed" not in text
    glibc = ImportError("/lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.43' not found (required by libglib-2.0.so.0)")
    text = gis_box_v2._qt_import_problem(glibc)                      # built on a newer distribution
    assert "newer Linux" in text and "apt install" not in text
    monkeypatch.setattr(sys, "platform", "win32")
    assert "apt install" not in gis_box_v2._qt_import_problem(lib)


def test_deb_package_declares_the_qt_system_libraries():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(root, "packaging", "nfpm.yaml"), encoding="utf-8").read()
    deb = text.split("overrides:", 1)[1]
    for pkg in ("libegl1", "libgl1", "libxkbcommon0", "libfontconfig1", "libdbus-1-3", "libxcb-cursor0",
                "libwayland-client0", "fonts-dejavu-core"):
        assert "- " + pkg in deb, pkg


# ---------------------------------------------------------------- small windows / emoji on Linux
def test_no_page_is_squeezed_at_the_minimum_window_size(win):
    """At 900x600 the long (Georgian) pages scroll instead of being squashed / cut off (7 of 14 were)."""
    win.resize(900, 600)
    win.show()
    for lang in ("ka", "en"):
        if win.lang != lang:
            win.set_lang(lang)
        for t in registry.TOOLS:
            win.show_tool(t.id)
            QCoreApplication.processEvents()
            page = win.pages[t.id]
            if page.native is None:
                continue
            hint = page.native.minimumSizeHint()
            assert page.native.height() >= hint.height() and page.native.width() >= hint.width(), (lang, t.id)
            assert page.scroll.widget() is page.native
    win.set_lang("ka")


def test_decorative_emoji_are_dropped_only_without_an_emoji_font(qapp, monkeypatch):
    from v2 import i18n
    monkeypatch.setattr(i18n, "_emoji_font", False)                  # e.g. a Linux desktop without one
    assert i18n.plain("\U0001F5D1 Delete") == "Delete"
    assert i18n.plain("\U0001F4CB  Copy") == "Copy"
    assert i18n.plain("★ Favorites") == "★ Favorites" and i18n.plain("⚠ check") == "⚠ check"
    assert i18n.tr("en", "sc_tmpl_del") == "Delete" and i18n.tr("ka", "sc_tmpl_del") == "წაშლა"
    monkeypatch.setattr(i18n, "_emoji_font", True)                   # Windows: Segoe UI Emoji
    assert i18n.tr("en", "sc_tmpl_del") == "\U0001F5D1 Delete"
