# -*- coding: utf-8 -*-
"""V2 GDB -> PostGIS page. External effects (ogr2ogr runs, PostGIS, schtasks, the user's settings / history files)
are replaced by fakes; one test lists the layers of a generated .gdb with the real ogrinfo when GDAL is installed."""
import importlib.util
import json
import os
import time

import pytest

from tools import gdb2postgis_cli as cli
from tools import gdb2postgis_core as core

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")


# ----------------------------------------------------------------------------- shared settings file
def test_save_cfg_replaces_only_its_own_key(tmp_path):
    p = str(tmp_path / "gis_box_settings.json")
    json.dump({"lang": "ka", "tool_config": {"other": {"a": 1}}}, open(p, "w", encoding="utf-8"))
    cli.save_cfg({"host": "h", "layers": ["x"]}, p)
    data = json.load(open(p, encoding="utf-8"))
    assert data["lang"] == "ka" and data["tool_config"]["other"] == {"a": 1}
    assert cli.load_cfg(p) == {"host": "h", "layers": ["x"]} and not os.path.exists(p + ".tmp")
    open(p, "w").write("{broken")
    with pytest.raises(ValueError):
        cli.save_cfg({"x": 1}, p)                               # a corrupt file is not overwritten
    assert open(p).read() == "{broken"
    assert cli.load_cfg(str(tmp_path / "missing.json")) == {}


# ----------------------------------------------------------------------------- page
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class FakeState:
    marks = {}

    def get(self, source, layer):
        return type("S", (), {"watermark": self.marks.get(layer, "")})()


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    settings = str(tmp_path / "gis_box_settings.json")
    monkeypatch.setattr(cli, "SETTINGS_FILE", settings)         # never the user's real settings file
    import tools.gdb2postgis_state as st
    import tools.gdb2postgis_audit as au
    real_audit = au.AuditStore
    monkeypatch.setattr(st, "SyncState", FakeState)
    monkeypatch.setattr(au, "AuditStore", lambda *a, **k: None)
    from tools import gdb2postgis as classic
    sched = []
    monkeypatch.setattr(classic, "register_task", lambda sc, mo: sched.append(("reg", sc, mo)) or (True, ""))
    monkeypatch.setattr(classic, "unregister_task", lambda: sched.append(("unreg",)))
    exe = str(tmp_path / "ogr2ogr.exe")
    monkeypatch.setattr(core, "find_tool", lambda name, override=None: exe)
    monkeypatch.setattr(core, "gdal_version", lambda p: "GDAL 9.9")
    src = tmp_path / "src"
    (src / "city.gdb").mkdir(parents=True)
    monkeypatch.setattr(core, "list_layers", lambda ogrinfo, s: [core.LayerInfo("roads", "Line String"),
                                                                 core.LayerInfo("parcels", "Multi Polygon")])
    calls = {"import": [], "exists": []}

    def fake_import(ogr2ogr, source, layers, pg, opt, log, **kw):
        calls["import"].append((source, list(layers), pg, opt))
        log("INFO", "Done. OK=2 FAILED=0")
        r = core.RunResult(started="x")
        r.results = [core.LayerResult(lyr, True, 0.1) for lyr in layers]
        return r
    monkeypatch.setattr(core, "run_import", fake_import)
    monkeypatch.setattr(core, "test_pg_connection", lambda ogrinfo, pg: (True, "ok"))
    monkeypatch.setattr(core, "_pg_table_exists", lambda o, pg, t: calls["exists"].append(t) or t == "roads")
    from v2.main_window import MainWindow
    from v2.settings import Settings
    w = MainWindow(Settings(str(tmp_path / "s.json")))
    w.real_audit = real_audit
    yield w, calls, sched, settings, str(src)
    w.task = None
    w.close()


def wait_for(cond, timeout=30):
    from PySide6.QtCore import QCoreApplication
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return cond()


def _page(w, src_dir, answers=True):
    w.show_tool("gdb2pg")
    p = w.pages["gdb2pg"].native
    p.asks, p.shown = [], []
    p._ask = lambda text: p.asks.append(text) or (answers.pop(0) if isinstance(answers, list) else answers)
    for n in ("_info", "_warn", "_error"):
        setattr(p, n, lambda text, *a: p.shown.append(text))
    p.dir_edit.setText(src_dir)
    p._scan_sources()
    assert wait_for(lambda: p.layers_list.count() == 2 and w.task is None)
    return p


@needs_qt
def test_overwrite_names_the_tables_it_replaces_and_decline_imports_nothing(env):
    w, calls, _s, _set, src = env
    p = _page(w, src, answers=[False, True])
    assert p.source_combo.currentText() == "city.gdb" and "roads" in p.layers_list.item(0).text()
    p.import_btn.click()
    assert p.shown[-1] == p._z("warn_layers")                   # nothing selected
    p.layers_list.selectAll()
    p.pw_edit.setText("s3cret-pw")
    assert p.mode_combo.currentText() == "overwrite"
    p.start_import()
    assert wait_for(lambda: p.asks and w.task is None)
    assert "public.roads" in p.asks[0] and "parcels" not in p.asks[0]     # only the existing table is named
    assert calls["import"] == []                                # declined
    p.start_import()
    assert wait_for(lambda: calls["import"] and w.task is None
                    and p._z("done", ok=2, fail=0) in p.log_view.toPlainText())
    source, layers, pg, opt = calls["import"][0]
    assert source.endswith("city.gdb") and layers == ["roads", "parcels"] and opt.mode == "overwrite"
    assert pg.password == "s3cret-pw" and "s3cret-pw" not in p.log_view.toPlainText()


@needs_qt
def test_no_connection_means_no_guess_and_no_import(env, monkeypatch):
    w, calls, _s, _set, src = env
    monkeypatch.setattr(core, "test_pg_connection", lambda o, pg: (False, "password authentication failed"))
    p = _page(w, src)
    p.layers_list.selectAll()
    p.start_import()
    assert wait_for(lambda: p.shown and w.task is None)
    assert "password authentication failed" in p.shown[-1] and not p.asks and calls["import"] == []


@needs_qt
def test_append_asks_once_and_incremental_lists_only_first_loads(env):
    w, calls, _s, _set, src = env
    p = _page(w, src)
    p.layers_list.item(0).setSelected(True)
    p.mode_combo.setCurrentText("append")
    p.start_import()
    assert wait_for(lambda: calls["import"] and w.task is None)
    assert len(p.asks) == 1 and calls["exists"] == []           # append never replaces: no table check
    FakeState.marks = {"roads": "2026-11-01"}                   # roads already synced -> delta, not a reload
    p.incr_box.setChecked(True)
    p.start_import()
    assert wait_for(lambda: len(calls["import"]) == 2 and w.task is None)
    assert "public.roads" not in p.asks[-1] and calls["import"][1][3].incremental
    FakeState.marks = {}


@needs_qt
def test_schedule_asks_registers_and_removes_the_windows_task(env):
    w, _c, sched, settings, src = env
    p = _page(w, src, answers=[False, True])
    p.layers_list.selectAll()
    p.bg_box.setChecked(True)
    p.sched_box.setChecked(True)
    assert p.apply_schedule() is False and not p.sched_box.isChecked() and sched == []   # declined: nothing
    p.sched_box.setChecked(True)
    p.every_spin.setValue(2)
    p.unit_combo.setCurrentIndex(p.unit_combo.findData("hours"))
    assert p.apply_schedule() is True
    assert ("reg", "HOURLY", 2) in sched and "GIS_BOX_gdb2postgis" in p.asks[-1]
    cfg = cli.load_cfg(settings)
    assert cfg["sched_on"] and cfg["layers"] == ["roads", "parcels"] and "password" not in cfg
    p.sched_box.setChecked(False)
    p.apply_schedule()
    assert sched[-1] == ("unreg",) and p.next_run.text() == p._z("sched_off")


@needs_qt
def test_in_app_timer_runs_without_asking(env):
    w, calls, _s, _set, src = env
    p = _page(w, src, answers=[True])
    p.layers_list.selectAll()
    p.bg_box.setChecked(False)
    p.sched_box.setChecked(True)
    assert p.apply_schedule() and p._sched_timer.isActive()
    n_asks = len(p.asks)
    p._sched_tick()                                             # timer fires
    assert wait_for(lambda: calls["import"] and w.task is None)
    assert len(p.asks) == n_asks and p._sched_timer.isActive()  # no dialog; next run scheduled
    p.sched_box.setChecked(False)
    p.apply_schedule()


@needs_qt
def test_password_is_saved_only_when_ticked(env):
    w, _c, _s, settings, src = env
    p = _page(w, src)
    p.pw_edit.setText("pw1")
    p.remember()
    assert "password" not in cli.load_cfg(settings)
    p.remember_pw.setChecked(True)
    p.remember()
    assert cli.load_cfg(settings)["password"] == "pw1"
    p2 = type(p)(w, settings_path=settings)                      # a new page reads the shared settings
    assert p2.pw_edit.text() == "pw1" and p2.remember_pw.isChecked()


@needs_qt
def test_history_delete_features_asks_and_delete_record(env, tmp_path, monkeypatch):
    w, _c, _s, _set, src = env
    audit = w.real_audit(str(tmp_path / "audit.db"))           # a real history store in a temporary file
    audit.record({"profile": "", "source": "s", "layer": "roads", "schema": "public", "target_table": "roads",
                  "key_field": "objectid", "mode": "overwrite", "affected": 2, "deleted": 0, "seconds": 1.0,
                  "ok": True, "message": "", "pg_host": "h", "pg_port": 5432, "pg_db": "d"},
                 upserted_ids=["1", "2"])
    deleted = []
    monkeypatch.setattr(core, "delete_features",
                        lambda o, pg, schema, table, key, ids: deleted.append((schema, table, key, ids)) or (2, ""))
    p = _page(w, src, answers=[False, True])
    dlg = p.open_history(audit)
    assert dlg.runs.rowCount() == 1
    dlg.runs.selectRow(0)
    assert dlg.ids.rowCount() == 2
    dlg.delete_features()
    assert deleted == [] and "public.roads" in p.asks[-1]
    dlg.delete_features()
    assert wait_for(lambda: deleted and w.task is None)
    assert deleted[0] == ("public", "roads", "objectid", ["1", "2"])
    dlg.delete_record()
    assert dlg.runs.rowCount() == 0
    dlg.close()


@needs_qt
def test_real_ogrinfo_lists_layers_of_a_generated_gdb(qapp, tmp_path, monkeypatch):
    ogrinfo = core.find_tool("ogrinfo")
    if not ogrinfo:
        pytest.skip("GDAL ogrinfo not installed")
    gpd = pytest.importorskip("geopandas")                     # after Qt (fixture) - import order safe
    from shapely.geometry import LineString, Point
    gdb = tmp_path / "src" / "test.gdb"
    gdb.parent.mkdir()
    from pyogrio import write_dataframe
    write_dataframe(gpd.GeoDataFrame({"n": [1]}, geometry=[Point(500000, 4650000)], crs="EPSG:32638"),
                    str(gdb), layer="wells", driver="OpenFileGDB")
    write_dataframe(gpd.GeoDataFrame({"n": [1]}, geometry=[LineString([(0, 0), (1, 1)])], crs="EPSG:32638"),
                    str(gdb), layer="pipes", driver="OpenFileGDB")
    monkeypatch.setattr(cli, "SETTINGS_FILE", str(tmp_path / "gis_box_settings.json"))
    from v2.main_window import MainWindow
    from v2.settings import Settings
    w = MainWindow(Settings(str(tmp_path / "s.json")))
    w.show_tool("gdb2pg")
    p = w.pages["gdb2pg"].native
    p.dir_edit.setText(str(gdb.parent))
    p._scan_sources()
    assert wait_for(lambda: p.layers_list.count() == 2 and w.task is None)
    assert sorted(p._layer_names) == ["pipes", "wells"]
    w.task = None
    w.close()
