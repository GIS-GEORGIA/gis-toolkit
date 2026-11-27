# -*- coding: utf-8 -*-
import datetime
import importlib.util
import os
import time

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import LineString, Point, box  # noqa: E402

from tools import geom_collect_core as core  # noqa: E402

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")
X0, Y0 = 500000.0, 4650000.0


def _tree(root):
    """a/pts.shp (32638, 2 points), a/b/lines.shp (32638, 1 line), polys.geojson (4326, 1 polygon), nocrs.shp."""
    root = str(root)
    os.makedirs(os.path.join(root, "a", "b"))
    gpd.GeoDataFrame({"k": [1, 2]}, geometry=[Point(X0, Y0), Point(X0 + 1, Y0 + 1)], crs=32638).to_file(
        os.path.join(root, "a", "pts.shp"))
    gpd.GeoDataFrame({"k": [1]}, geometry=[LineString([(X0, Y0), (X0 + 10, Y0)])], crs=32638).to_file(
        os.path.join(root, "a", "b", "lines.shp"))
    gpd.GeoDataFrame({"k": [1]}, geometry=[box(44.8, 41.7, 44.81, 41.71)], crs=4326).to_file(
        os.path.join(root, "polys.geojson"), driver="GeoJSON")
    gpd.GeoDataFrame({"k": [1]}, geometry=[Point(X0 + 5, Y0 + 5)]).to_file(os.path.join(root, "nocrs.shp"))
    return root


# ----------------------------------------------------------------------------- core
def test_unique_output_path(tmp_path):
    p = str(tmp_path / "c_251126.gpkg")
    assert core.unique_output_path(p) == p
    open(p, "w").close()
    assert core.unique_output_path(p).endswith("c_251126_2.gpkg")
    open(str(tmp_path / "c_251126_2.gpkg"), "w").close()
    assert core.unique_output_path(p).endswith("c_251126_3.gpkg")


def test_collect_without_assuming_crs_skips_nocrs_and_reprojects(tmp_path):
    src = _tree(tmp_path / "src")
    files = core.iter_geometry_files(src, (".shp", ".geojson"))
    assert len(files) == 4
    out = str(tmp_path / "o.gpkg")
    res = core.collect_to_geopackage(files, out, target_epsg=32638, assume_missing_crs=False)
    assert (res["points"], res["lines"], res["polygons"]) == (2, 1, 1)                 # the no-CRS point is NOT in
    assert any("no CRS" in n for _p, n in res["errors"])
    poly = gpd.read_file(out, layer="polygons")
    assert poly.crs.to_epsg() == 32638 and 4_000_000 < poly.geometry.iloc[0].centroid.y < 5_000_000
    with pytest.raises(FileExistsError):                                               # never overwritten
        core.collect_to_geopackage(files, out, target_epsg=32638)


def test_collect_classic_default_still_assumes(tmp_path):
    src = _tree(tmp_path / "src")
    res = core.collect_to_geopackage(core.iter_geometry_files(src, (".shp",)), str(tmp_path / "o.gpkg"),
                                     target_epsg=32638)
    assert res["points"] == 3 and res["errors"] == []


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
def test_page_count_run_and_no_overwrite(win, tmp_path, monkeypatch):
    src = _tree(tmp_path / "src")
    outdir = tmp_path / "out"
    outdir.mkdir()
    win.show_tool("geom_collect")
    p = win.pages["geom_collect"].native
    p.src_edit.setText(src)
    p.out_edit.setText(str(outdir / "collected_geometry.gpkg"))
    p.set_all_formats(False)
    p.other_edit.setText("shp, geojson")
    assert p.selected_exts() == (".shp", ".geojson")
    p.crs_combo.setCurrentIndex(p.crs_combo.findData(32638))
    p.count()
    assert "4" in p.log_view.toPlainText()
    asked = []
    monkeypatch.setattr(p, "_confirm", lambda t: asked.append(t) or True)
    p.run()
    day = datetime.date.today().strftime("%d%m%y")
    first = str(outdir / "collected_geometry_{}.gpkg".format(day))
    assert asked and first in asked[0]
    assert wait_for(lambda: win.task is None and p.last_out == first)
    assert len(gpd.read_file(first, layer="points")) == 2                  # no-CRS file skipped (default off)
    assert "nocrs.shp" in p.log_view.toPlainText()
    before = os.path.getmtime(first)
    p.assume_box.setChecked(True)
    p.run()
    second = str(outdir / "collected_geometry_{}_2.gpkg".format(day))
    assert wait_for(lambda: win.task is None and p.last_out == second)
    assert os.path.getmtime(first) == before                              # the first output is untouched
    assert len(gpd.read_file(second, layer="points")) == 3
    from v2.settings import Settings
    st = Settings(win.settings.path)["tool_state"]["geom_collect"]
    assert st["crs_epsg"] == 32638 and st["exts"] == [".shp", ".geojson"]


@needs_qt
def test_page_validation(win, tmp_path):
    win.show_tool("geom_collect")
    p = win.pages["geom_collect"].native
    p.src_edit.setText(str(tmp_path / "missing"))
    p.run()
    assert win.toast.property("kind") == "error" and win.task is None
    p.src_edit.setText(str(tmp_path))
    p.set_all_formats(False)
    p.other_edit.setText("")
    p.run()
    assert win.toast.property("kind") == "error" and win.task is None
