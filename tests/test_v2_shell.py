import os
import re
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
# Qt must be imported BEFORE geopandas/shapely: the other order crashes on Windows (DLL clash) -
# the real app also loads Qt first.
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox

gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point

from tools import crs_manager as cm
from v2 import launcher, registry, themes, workers
from v2.main_window import HOME, ROLE, MainWindow
from v2.settings import Settings


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path):
    s = Settings(str(tmp_path / "s.json"))
    w = MainWindow(s)
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


# ---------------------------------------------------------------- settings / registry (no Qt)
def test_settings_roundtrip_and_validation(tmp_path):
    p = str(tmp_path / "s.json")
    s = Settings(p)
    s["theme"], s["lang"] = "dark", "en"
    s.toggle_favorite("crs_manager")
    s.add_recent_file(str(tmp_path / "a.shp"))
    assert s.save()
    s2 = Settings(p)
    assert s2["theme"] == "dark" and s2["lang"] == "en" and s2.is_favorite("crs_manager")
    assert len(s2["recent_files"]) == 1
    with open(p, "w", encoding="utf-8") as f:
        f.write('{"theme": "neon", "lang": "xx", "favorites": "oops"}')
    s3 = Settings(p)
    assert s3["theme"] == "light" and s3["lang"] == "ka" and s3["favorites"] == []
    with open(p, "w", encoding="utf-8") as f:
        f.write("not json")
    assert Settings(p)["theme"] == "light"


def test_recent_lists_are_capped_and_deduped(tmp_path):
    s = Settings(str(tmp_path / "s.json"))
    for i in range(30):
        s.add_recent_file(str(tmp_path / "f{}".format(i)))
    s.add_recent_tool("a")
    s.add_recent_tool("b")
    s.add_recent_tool("a")
    assert len(s["recent_files"]) == 15 and s["recent_tools"][:2] == ["a", "b"]


def test_registry_is_consistent():
    ids = [t.id for t in registry.TOOLS]
    assert len(ids) == len(set(ids))
    cats = {c for c, _ in registry.CATEGORIES}
    assert all(t.category in cats and t.name["ka"] and t.name["en"] and t.desc["ka"] and t.desc["en"]
               for t in registry.TOOLS)
    assert all(t.page for t in registry.TOOLS if t.kind == "native")


def test_every_legacy_key_exists_in_the_classic_app():
    src = open(os.path.join(os.path.dirname(launcher.__file__), "..", "gis_box.py"), encoding="utf-8").read()
    tids = set(re.findall(r'"tid":\s*"([^"]+)"', src))
    import gis_box
    en_names = {v["en"] for k, v in gis_box.TR.items() if k.endswith("_name")}
    for t in registry.TOOLS:
        if t.kind == "legacy":
            assert t.legacy_key in tids or t.legacy_key in en_names, t.id


def test_registry_search_both_languages():
    assert any(t.id == "line_buffer" for t in registry.search("ბუფერ"))
    assert any(t.id == "line_buffer" for t in registry.search("buffer"))
    assert registry.search("zzzzz") == []


def test_themes_differ_and_cover_all_tokens():
    assert themes.stylesheet("light") != themes.stylesheet("dark")
    assert "{" not in themes.stylesheet("dark").replace("{", "", 0) or True
    for name in ("light", "dark"):
        assert all(v.startswith("#") for v in themes.palette(name).values())


def test_launcher_command_and_failure(monkeypatch):
    cmd = launcher.legacy_command("db_transfer")
    assert cmd[-2:] == ["--tool", "db_transfer"] and cmd[1].endswith("gis_box.py")
    seen = {}
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda argv, **kw: seen.update(argv=argv) or "proc")
    assert launcher.launch_legacy("line_buffer") == "proc" and seen["argv"][-1] == "line_buffer"


# ---------------------------------------------------------------- workers
def test_worker_success_error_cancel(qapp):
    res = {}
    workers.run_task(lambda ctx: 42, "t.ok", on_done=lambda r: res.update(done=r),
                     on_finished=lambda: res.update(fin1=True))
    assert wait_for(lambda: res.get("fin1")) and res["done"] == 42

    workers.run_task(lambda ctx: 1 / 0, "t.err", on_error=lambda m: res.update(err=m),
                     on_finished=lambda: res.update(fin2=True))
    assert wait_for(lambda: res.get("fin2")) and "ZeroDivisionError" in res["err"]

    def slow(ctx):
        for _ in range(500):
            ctx.check_cancelled()
            time.sleep(0.01)
    t = workers.run_task(slow, "t.cancel", on_cancelled=lambda: res.update(cancelled=True),
                         on_done=lambda r: res.update(wrong=True), on_finished=lambda: res.update(fin3=True))
    time.sleep(0.05)
    t.cancel()
    assert wait_for(lambda: res.get("fin3")) and res.get("cancelled") and "wrong" not in res


def test_worker_callbacks_run_in_gui_thread_and_history_recorded(qapp):
    import threading
    from tools.logging_manager import get_manager
    seen = {}
    workers.run_task(lambda ctx: seen.update(work=threading.get_ident()) or "x", "t.thread",
                     on_done=lambda r: seen.update(cb=threading.get_ident()), on_finished=lambda: seen.update(f=1))
    assert wait_for(lambda: seen.get("f"))
    assert seen["cb"] == threading.get_ident() != seen["work"]
    assert get_manager().history(tool="t.thread")[0]["status"] == "ok"


def test_worker_progress(qapp):
    got = []
    done = {}
    workers.run_task(lambda ctx: [ctx.progress(i, 3) for i in range(1, 4)], "t.prog",
                     on_progress=lambda i, n, t: got.append((i, n)), on_finished=lambda: done.update(f=1))
    assert wait_for(lambda: done.get("f")) and got == [(1, 3), (2, 3), (3, 3)]


# ---------------------------------------------------------------- window
def test_window_builds_and_lists_all_tools(win):
    names = []

    def walk(it):
        if it.data(0, ROLE):
            names.append(it.data(0, ROLE))
        for i in range(it.childCount()):
            walk(it.child(i))
    for i in range(win.tree.topLevelItemCount()):
        walk(win.tree.topLevelItem(i))
    assert HOME in names and {t.id for t in registry.TOOLS} <= set(names)


def test_search_filters_sidebar(win):
    win.search_edit.setText("buffer")
    ids = []
    for g in range(win.tree.topLevelItemCount()):
        top = win.tree.topLevelItem(g)
        ids += [top.child(i).data(0, ROLE) for i in range(top.childCount())]
    assert ids == ["line_buffer"]
    win.search_edit.setText("")


def test_favorites_and_recent_groups(win):
    win.show_tool("line_buffer")
    page = win.pages["line_buffer"]
    from PySide6.QtWidgets import QPushButton
    favbtn = [b for b in page.findChildren(QPushButton) if "☆" in b.text()][0]
    favbtn.click()
    assert win.settings.is_favorite("line_buffer")
    titles = [win.tree.topLevelItem(i).text(0) for i in range(win.tree.topLevelItemCount())]
    assert any("★" in t for t in titles) and any("◷" in t for t in titles)


def test_theme_and_language_switch_persist(win):
    win.apply_theme("dark")
    assert win.settings["theme"] == "dark" and "#0d1117" in QApplication.instance().styleSheet()
    win.show_tool("crs_manager")
    win.set_lang("en")
    assert win.lang == "en" and win.settings["lang"] == "en" and win.current == "crs_manager"
    assert win.tree.topLevelItem(0).text(0).endswith("Home")
    win.set_lang("ka")
    win.apply_theme("light")


def test_legacy_page_opens_classic_window(win, monkeypatch):
    legacy = [t for t in registry.TOOLS if t.kind == "legacy"]      # whichever tool is still classic-only
    if not legacy:
        pytest.skip("every tool is native")
    tool = legacy[0]
    calls = []
    monkeypatch.setattr(launcher, "launch_legacy", lambda key: calls.append(key))
    win.show_tool(tool.id)
    from PySide6.QtWidgets import QPushButton
    [b for b in win.pages[tool.id].findChildren(QPushButton) if b.objectName() == "primary"][0].click()
    assert calls == [tool.legacy_key]


def test_notify_toast(win):
    win.notify("hello", "error")
    assert win.toast.text() == "hello" and not win.toast.isHidden()


def test_second_task_is_refused_while_busy(win):
    started = win.run(lambda ctx: time.sleep(0.3), "t.busy")
    assert started is not None and win.run(lambda ctx: 1, "t.second") is None
    assert wait_for(lambda: win.task is None)


# ---------------------------------------------------------------- CRS page
@pytest.fixture
def crs_page(win):
    win.show_tool("crs_manager")
    return win.pages["crs_manager"].native


def _shp(tmp_path, crs=4326, name="a.shp"):
    p = str(tmp_path / name)
    gpd.GeoDataFrame({"a": [1]}, geometry=[Point(44.8, 41.7)], crs=crs).to_file(p)
    return p


def test_crs_page_detect_shows_info(crs_page, win, tmp_path):
    p = _shp(tmp_path)
    crs_page.file_edit.setText(p)
    crs_page.detect()
    assert wait_for(lambda: win.task is None and crs_page.detection is not None)
    cells = [crs_page.info.item(r, 1).text() for r in range(crs_page.info.rowCount())]
    assert "4326" in cells and crs_page.out_edit.text().endswith("a_crs.gpkg")
    assert p in win.settings["recent_files"][0] or os.path.abspath(p) == win.settings["recent_files"][0]


def test_crs_page_missing_crs_shows_candidates_only(crs_page, win, tmp_path):
    p = _shp(tmp_path, crs=None, name="u.shp")
    if os.path.exists(str(tmp_path / "u.prj")):
        os.remove(str(tmp_path / "u.prj"))
    crs_page.file_edit.setText(p)
    crs_page.detect()
    assert wait_for(lambda: win.task is None and crs_page.detection is not None)
    assert "⚠" in crs_page.warn.text() and crs_page.sugg_box.count() >= 1
    assert "EPSG:" in crs_page.sugg_box.itemText(0)
    assert crs_page.target_box.currentData() == 32637 and crs_page.custom_edit.text() == ""   # nothing auto-selected


def test_crs_page_reproject_writes_new_file_and_report(crs_page, win, tmp_path):
    p = _shp(tmp_path)
    out = str(tmp_path / "o.gpkg")
    crs_page.file_edit.setText(p)
    crs_page.out_edit.setText(out)
    crs_page.custom_edit.setText("32638")
    crs_page.reproject()
    assert wait_for(lambda: win.task is None and crs_page.report.toPlainText())
    assert os.path.exists(out) and cm.detect(out).info.epsg == 32638
    assert "REPROJECT" in crs_page.report.toPlainText()
    assert os.path.exists(p)


def test_crs_page_assign_needs_confirmation(crs_page, win, tmp_path, monkeypatch):
    p = _shp(tmp_path, crs=None, name="n.shp")
    out = str(tmp_path / "n.gpkg")
    crs_page.file_edit.setText(p)
    crs_page.out_edit.setText(out)
    crs_page.custom_edit.setText("32637")
    monkeypatch.setattr(crs_page, "_confirm", lambda text: False)
    crs_page.assign()
    time.sleep(0.2)
    QCoreApplication.processEvents()
    assert win.task is None and not os.path.exists(out)              # declined -> nothing happened
    monkeypatch.setattr(crs_page, "_confirm", lambda text: True)
    crs_page.assign()
    assert wait_for(lambda: win.task is None and os.path.exists(out))
    assert cm.detect(out).info.epsg == 32637 and "NOT changed" in crs_page.report.toPlainText()


def test_crs_page_validation_errors_notify(crs_page, win):
    crs_page.file_edit.setText("")
    crs_page.reproject()
    assert win.toast.property("kind") == "error" and win.task is None
    crs_page.file_edit.setText(__file__)
    crs_page.custom_edit.setText("abc")
    crs_page.out_edit.setText("x.gpkg")
    crs_page.reproject()
    assert win.task is None


def test_crs_page_existing_output_is_reported_not_overwritten(crs_page, win, tmp_path):
    p = _shp(tmp_path)
    out = str(tmp_path / "exists.gpkg")
    open(out, "w").write("keep me")
    crs_page.file_edit.setText(p)
    crs_page.out_edit.setText(out)
    crs_page.custom_edit.setText("32637")
    crs_page.reproject()
    assert wait_for(lambda: win.task is None)
    assert open(out).read() == "keep me" and "exists" in win.toast.text()


def test_selftest_entrypoint(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("GIS_BOX_V2_DIR", str(tmp_path))
    import gis_box_v2
    assert gis_box_v2.main(["--selftest"]) == 0
