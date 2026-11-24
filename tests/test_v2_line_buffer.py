import math
import os
import time

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import LineString, Point, Polygon

from tools import line_buffer_core as core
from v2.main_window import MainWindow
from v2.settings import Settings


def _line_shp(folder, name="gas.shp", crs=32638, length=1000.0, x0=500000.0, y0=4650000.0):
    p = os.path.join(str(folder), name)
    gpd.GeoDataFrame({"id": [1]}, geometry=[LineString([(x0, y0), (x0 + length, y0)])], crs=crs).to_file(p)
    return p


def _expected_area(length, d):
    return 2 * d * length + math.pi * d * d


# ----------------------------------------------------------------------------- core
def test_scan_finds_only_line_layers(tmp_path):
    _line_shp(tmp_path, "line.shp")
    gpd.GeoDataFrame({"a": [1]}, geometry=[Point(1, 1)], crs=4326).to_file(str(tmp_path / "pt.shp"))
    gpd.GeoDataFrame({"a": [1]}, geometry=[Polygon([(0, 0), (1, 0), (1, 1)])], crs=4326).to_file(str(tmp_path / "poly.shp"))
    assert list(core.scan_line_shapefiles(str(tmp_path))) == ["line.shp"]
    assert core.scan_line_shapefiles(str(tmp_path / "nope")) == {}


def test_plan_layer_utm_needs_no_conversion_and_4326_does(tmp_path):
    utm = _line_shp(tmp_path, "u.shp", 32637, x0=400000)
    p = core.plan_layer(utm)
    assert p["epsg"] == 32637 and p["convert"] is False
    g = gpd.GeoDataFrame({"a": [1]}, geometry=[LineString([(44.8, 41.7), (44.9, 41.8)])], crs=4326)
    path = str(tmp_path / "geo.shp")
    g.to_file(path)
    p = core.plan_layer(path)
    assert p["convert"] is True and p["epsg"] == 32638 and p["zone"] == 38 and p["current"] == "EPSG:4326"


def test_plan_layer_without_crs_is_an_error_not_a_guess(tmp_path):
    p = _line_shp(tmp_path, "n.shp", crs=None)
    for ext in (".prj",):
        if os.path.exists(p[:-4] + ext):
            os.remove(p[:-4] + ext)
    with pytest.raises(ValueError):
        core.plan_layer(p)


def test_build_buffers_exact_areas_and_never_touches_source(tmp_path):
    src = _line_shp(tmp_path, "gas.shp", length=1000)
    before = open(src, "rb").read()
    out = tmp_path / "out"
    out.mkdir()
    zones = core.BUFFER_TYPES["3"]
    res = core.build_buffers(src, str(out), zones, 32638)
    assert [d for d, _ in res] == [4, 25, 100]
    for dist, path in res:
        g = gpd.read_file(path)
        assert g.crs.to_epsg() == 32638 and len(g) == 1
        assert g.geometry.iloc[0].area == pytest.approx(_expected_area(1000, dist), rel=2e-3)
        assert g["Dist_m"].iloc[0] == dist
    assert open(src, "rb").read() == before


def test_output_index_grows_and_old_files_are_never_overwritten(tmp_path):
    src = _line_shp(tmp_path, "gas.shp")
    out = tmp_path / "out"
    out.mkdir()
    a = core.build_buffers(src, str(out), [(4, "gas_protection_zone_1")], 32638)[0][1]
    b = core.build_buffers(src, str(out), [(4, "gas_protection_zone_1")], 32638)[0][1]
    assert a.endswith("gas_protection_zone_1_1.shp") and b.endswith("gas_protection_zone_1_2.shp")
    assert os.path.exists(a) and os.path.exists(b)


def test_build_buffers_reprojects_with_a_logged_report(tmp_path):
    g = gpd.GeoDataFrame({"a": [1]}, geometry=[LineString([(500000, 4650000), (501000, 4650000)])], crs=32638).to_crs(4326)
    src = str(tmp_path / "geo.shp")
    g.to_file(src)
    out = tmp_path / "o"
    out.mkdir()
    logs = []
    res = core.build_buffers(src, str(out), [(25, "z")], 32638, log=logs.append)
    assert any("reprojected EPSG:4326 -> EPSG:32638" in m for m in logs)
    assert gpd.read_file(res[0][1]).geometry.iloc[0].area == pytest.approx(_expected_area(1000, 25), rel=5e-3)


def test_build_buffers_errors_and_cancel(tmp_path):
    src = _line_shp(tmp_path)
    out = tmp_path / "o"
    out.mkdir()
    with pytest.raises(core.Cancelled):
        core.build_buffers(src, str(out), [(4, "a"), (25, "b")], 32638, cancel=lambda: True)
    assert os.listdir(out) == []
    nocrs = _line_shp(tmp_path, "nc.shp", crs=None)
    if os.path.exists(nocrs[:-4] + ".prj"):
        os.remove(nocrs[:-4] + ".prj")
    with pytest.raises(ValueError, match="no_crs"):
        core.build_buffers(nocrs, str(out), [(4, "a")], 32638)
    empty = str(tmp_path / "e.shp")
    gpd.GeoDataFrame({"a": []}, geometry=gpd.GeoSeries([], crs=32638)).to_file(empty)
    with pytest.raises(ValueError, match="no_geom"):
        core.build_buffers(empty, str(out), [(4, "a")], 32638)


# ----------------------------------------------------------------------------- page
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


def _page(win):
    win.show_tool("line_buffer")
    return win.pages["line_buffer"].native


def test_page_is_native_and_lists_zones_per_type(win):
    p = _page(win)
    assert len(p.zone_boxes) == 4
    p.type_box.setCurrentIndex(p.type_box.findData("2"))
    assert [k[0] for k in p.zone_boxes] == [4, 10, 500]


def test_page_scan_build_and_remember(win, tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    out.mkdir()
    _line_shp(src, "gas.shp", length=500)
    p = _page(win)
    p.folder_edit.setText(str(src))
    p.out_edit.setText(str(out))
    p.scan()
    assert p.shp_combo.count() == 1 and "1" in p.log_view.toPlainText()
    p.type_box.setCurrentIndex(p.type_box.findData("3"))
    list(p.zone_boxes.values())[2].setChecked(False)               # skip the 100 m buffer
    p.build()
    assert wait_for(lambda: win.task is None and len(os.listdir(out)) >= 6)
    shps = sorted(f for f in os.listdir(out) if f.endswith(".shp"))
    assert shps == ["gas_protection_zone_1_1.shp", "gas_protection_zone_2_1.shp"]
    assert "2" in p.log_view.toPlainText()
    saved = Settings(win.settings.path)["tool_state"]["line_buffer"]
    assert saved["folder"] == str(src) and saved["type"] == "3"


def test_page_conversion_needs_consent(win, tmp_path, monkeypatch):
    src, out = tmp_path / "s", tmp_path / "o"
    src.mkdir()
    out.mkdir()
    g = gpd.GeoDataFrame({"a": [1]}, geometry=[LineString([(44.8, 41.7), (44.81, 41.7)])], crs=4326)
    g.to_file(str(src / "geo.shp"))
    p = _page(win)
    p.folder_edit.setText(str(src))
    p.out_edit.setText(str(out))
    p.scan()
    asked = []
    monkeypatch.setattr(p, "_confirm", lambda t: asked.append(t) or False)
    p.build()
    time.sleep(0.2)
    QCoreApplication.processEvents()
    assert len(asked) == 1 and "EPSG:32638" in asked[0] and os.listdir(out) == [] and win.task is None
    monkeypatch.setattr(p, "_confirm", lambda t: True)
    p.build()
    assert wait_for(lambda: win.task is None and any(f.endswith(".shp") for f in os.listdir(out)))
    assert "reprojected" in p.log_view.toPlainText()


def test_page_missing_crs_is_reported_not_guessed(win, tmp_path):
    src, out = tmp_path / "s", tmp_path / "o"
    src.mkdir()
    out.mkdir()
    pth = _line_shp(src, "nc.shp", crs=None)
    if os.path.exists(pth[:-4] + ".prj"):
        os.remove(pth[:-4] + ".prj")
    p = _page(win)
    p.folder_edit.setText(str(src))
    p.out_edit.setText(str(out))
    p.scan()
    p.build()
    assert win.toast.property("kind") == "error" and "CRS" in win.toast.text()
    assert os.listdir(out) == [] and win.task is None


def test_page_validation(win, tmp_path):
    p = _page(win)
    p.build()
    assert win.toast.property("kind") == "error" and win.task is None
