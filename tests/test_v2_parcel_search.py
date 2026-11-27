# -*- coding: utf-8 -*-
import importlib.util
import os
import time

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import box  # noqa: E402

from tools import search_core  # noqa: E402

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")
X0, Y0 = 500000.0, 4650000.0
CODES = ["01.02.03.004", "01.02.03.005", "01.02.03.006"]


def _gdb(folder):
    path = os.path.join(str(folder), "Cad.gdb")
    gdf = gpd.GeoDataFrame({"CADCODE": CODES, "Name": ["a", "b", "c"]},
                           geometry=[box(X0 + i * 10, Y0, X0 + i * 10 + 5, Y0 + 5) for i in range(3)], crs=32638)
    gdf.to_file(path, layer="R02", driver="OpenFileGDB")
    gdf.head(1).to_file(path, layer="Z01", driver="OpenFileGDB", mode="a")
    return path


# ----------------------------------------------------------------------------- core
def test_free_out_base(tmp_path):
    out = str(tmp_path / "found.shp")
    assert search_core.free_out_base(out) == str(tmp_path / "found")
    open(str(tmp_path / "found.gpkg"), "w").close()
    assert search_core.free_out_base(out) == str(tmp_path / "found_2")
    assert search_core.free_out_base(out, ["shp"]) == str(tmp_path / "found")      # only the requested formats
    open(str(tmp_path / "found_NOT_FOUND.txt"), "w").close()
    assert search_core.free_out_base(out, ["shp"]) == str(tmp_path / "found_2")


def test_run_search_never_overwrites(tmp_path):
    gdb = _gdb(tmp_path)
    out = str(tmp_path / "res" / "found.shp")
    results = []
    for _ in range(2):
        box_ = {}
        search_core.run_search(gdb, "R02", "CADCODE", ["01 02 03 004", "010203005", "99.99.99.999"], out,
                               lambda m: None, box_.update, lambda key, **f: key, ["shp", "gpkg"])
        results.append(box_)
    assert results[0]["out_path"].endswith("found.shp") and results[1]["out_path"].endswith("found_2.shp")
    assert results[0]["found_list"] == ["01.02.03.004", "01.02.03.005"] and results[0]["not_found"] == ["99.99.99.999"]
    assert len(gpd.read_file(results[0]["out_path"])) == 2
    gpkg = results[0]["out_path"][:-4] + ".gpkg"                 # layer named after the result, not the temp file
    assert list(gpd.list_layers(gpkg)["name"]) == ["found"]
    assert not [f for f in os.listdir(str(tmp_path / "res")) if ".part" in f]
    side = search_core.write_not_found(results[0]["out_path"], results[0]["not_found"])
    assert open(side, encoding="utf-8").read() == "99.99.99.999"
    assert search_core.write_not_found(results[0]["out_path"], ["x"]) is None                 # kept, not replaced


# ----------------------------------------------------------------------------- page
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path):
    from v2.main_window import MainWindow
    from v2.settings import Settings
    w = MainWindow(Settings(str(tmp_path / "s.json")))
    yield w
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


@needs_qt
def test_page_layers_search_and_analysis(win, tmp_path, monkeypatch):
    gdb = _gdb(tmp_path)
    win.show_tool("parcel_search")
    p = win.pages["parcel_search"].native
    p.gdb_combo.setEditText(gdb)
    p.read_layers(silent=False)
    assert wait_for(lambda: win.task is None and p.layer_combo.count() == 2)
    assert p.layer_combo.itemText(0).startswith("R02 — ") and p.field_combo.currentText() == "CADCODE"
    p.codes_edit.setPlainText("01 02 03 004\n010203006\n12.34.56.789")
    out = tmp_path / "out" / "found.shp"
    p.out_edit.setText(str(out))
    p.search()
    assert wait_for(lambda: win.task is None and p.last_not_found == ["12.34.56.789"])
    assert len(gpd.read_file(str(out))) == 2 and (tmp_path / "out" / "found.gpkg").exists()
    assert (tmp_path / "out" / "found_NOT_FOUND.txt").exists()
    log = p.log_view.toPlainText()
    assert "12.34.56.789" in log
    # a second search keeps the first result
    p.search()
    assert wait_for(lambda: win.task is None and (tmp_path / "out" / "found_2.shp").exists())
    # remember + remove database
    p.remember_db()
    assert gdb in p.databases
    monkeypatch.setattr(p, "_confirm", lambda t: True)
    p.remove_db()
    assert gdb not in p.databases
    # shapefile analysis section
    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()
    gpd.GeoDataFrame({"a": [1]}, geometry=[box(X0, Y0, X0 + 100, Y0 + 50)], crs=32638).to_file(str(shp_dir / "big.shp"))
    p.an_root.setText(str(shp_dir))
    p.analyse()
    assert wait_for(lambda: win.task is None and "big.shp" in p.log_view.toPlainText())


@needs_qt
def test_page_validation_folder_of_gdbs(win, tmp_path):
    _gdb(tmp_path)
    win.show_tool("parcel_search")
    p = win.pages["parcel_search"].native
    p.gdb_combo.setEditText(str(tmp_path))                     # a folder that CONTAINS Cad.gdb
    p.search()
    assert win.toast.property("kind") == "error" and "Cad.gdb" in win.toast.text() and win.task is None
