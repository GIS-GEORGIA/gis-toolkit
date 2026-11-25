# -*- coding: utf-8 -*-
import importlib.util
import os
import time

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import LineString, box  # noqa: E402

from tools import zone_intersect_core as core  # noqa: E402

X0, Y0 = 500000.0, 4650000.0
needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")


def _layers(folder, crs=32638):
    """parcel 100x100; zone 'I' = vertical strip x 40..60 (cuts 2000 m2, 4 crossings); zone 'II' far away."""
    folder = str(folder)
    parcel = os.path.join(folder, "parcel.shp")
    zone = os.path.join(folder, "zone.shp")
    gpd.GeoDataFrame({"Name": ["p"]}, geometry=[box(X0, Y0, X0 + 100, Y0 + 100)], crs=crs).to_file(parcel)
    gpd.GeoDataFrame({"Zona": ["I", "II"]}, geometry=[box(X0 + 40, Y0 - 50, X0 + 60, Y0 + 150),
                                                     box(X0 + 500, Y0, X0 + 600, Y0 + 100)], crs=crs).to_file(zone)
    return parcel, zone


# ----------------------------------------------------------------------------- core
def test_compute_points_areas_and_filter(tmp_path):
    parcel, zone = _layers(tmp_path)
    meta = core.read_zone_meta(zone)
    assert meta["Zona"] == ["I", "II"] and meta["FID"] == ["0", "1"]
    assert core.auto_zone_field(list(meta)) == "FID" and core.auto_zone_field(["Zona", "x"]) == "Zona"
    res = core.compute(parcel, zone, "Zona", "I")
    assert sorted((round(x - X0), round(y - Y0)) for x, y in res["points"]) == [(40, 0), (40, 100), (60, 0), (60, 100)]
    a = res["areas"]
    assert a["parcel_area"] == pytest.approx(10000) and a["cut_area"] == pytest.approx(2000)
    assert a["remainder_area"] == pytest.approx(8000) and res["crs"].to_epsg() == 32638
    assert core.compute(parcel, zone, "Zona", "II")["points"] == []
    assert len(core.compute(parcel, zone, "FID", "0")["points"]) == 4


def test_geographic_parcel_is_refused(tmp_path):
    parcel, zone = _layers(tmp_path)
    gpd.read_file(parcel).to_crs(4326).to_file(str(tmp_path / "geo.shp"))
    with pytest.raises(ValueError, match="geographic"):
        core.compute(str(tmp_path / "geo.shp"), zone)


def test_names_never_overwrite(tmp_path):
    import pyproj
    crs = pyproj.CRS.from_epsg(32638)
    assert core.output_base("My name!", core.DEFAULT_OUT_NAME, crs) == "My_name38"
    assert core.output_base("", core.DEFAULT_OUT_NAME, crs) == "Gas_Pipe_ProtZone_Crossing38"
    p1 = core.next_free_path(str(tmp_path), "A38")
    core.write_points([(1.0, 2.0)], crs, p1)
    assert p1.endswith("A38_1.shp") and core.next_free_path(str(tmp_path), "A38").endswith("A38_2.shp")
    assert core.piece_path(str(tmp_path), "A38_1").endswith("A38_2.shp")          # taken -> next, no _1_1


def test_copy_template_increments_and_never_overwrites(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    for ext in (".shp", ".dbf", ".prj"):
        (src / ("Gas_Pipe_Crossing38" + ext)).write_text(ext)
    assert core.copy_template(str(src), "Gas_Pipe_Crossing38", str(dst)) == ("Gas_Pipe_Crossing38_1", 3)
    assert core.copy_template(str(src), "Gas_Pipe_Crossing38", str(dst)) == ("Gas_Pipe_Crossing38_2", 3)
    assert core.copy_template(str(src), "missing", str(dst)) == (None, 0)
    assert len(os.listdir(dst)) == 6


def test_shallow_summary():
    s = core.shallow_summary([(2, 10.0), (5, 4.0)])
    assert s["nums"] == "2, 5" and s["deg"] == 4.0 and s["lim"] == 15 and s["k"] == pytest.approx(14.3, abs=0.1)


# ----------------------------------------------------------------------------- pages
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


def wait_for(cond, timeout=20):
    from PySide6.QtCore import QCoreApplication
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return cond()


@needs_qt
def test_zone_page_create_pieces_and_handoff(win, tmp_path, monkeypatch):
    parcel, zone = _layers(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    win.show_tool("zone_intersect")
    p = win.pages["zone_intersect"].native
    p.parcel_edit.setText(parcel)
    p.zone_edit.setText(zone)
    p.load_zone_meta()
    p.out_edit.setText(str(out))
    p.field_combo.setCurrentText("Zona")
    p.value_combo.setCurrentText("I")
    assert not p.coords_btn.isEnabled()
    p.create()
    assert wait_for(lambda: win.task is None and p.result is not None)
    assert p.result["out_path"].endswith("Gas_Pipe_ProtZone_Crossing38_1.shp")
    assert len(gpd.read_file(p.result["out_path"])) == 4
    assert p.coords_btn.isEnabled() and p.cut_btn.isEnabled() and p.rem_btn.isEnabled()
    assert "2000.000" in p.areas_label.text()
    # second run -> _2, the first file is kept
    p.create()
    assert wait_for(lambda: win.task is None and p.result["out_path"].endswith("_2.shp"))
    assert os.path.exists(str(out / "Gas_Pipe_ProtZone_Crossing38_1.shp"))
    # save the cut-out piece
    monkeypatch.setattr(p, "_dir_name", lambda *a: str(out))
    monkeypatch.setattr(p, "_ask_name", lambda prompt, sug: sug)
    p.save_cut()
    cut = gpd.read_file(str(out / "Parcel_clipped_part38_1.shp"))
    assert cut["Area_m2"].sum() == pytest.approx(2000)
    # hand over to Shp -> coordinates (native page) with the areas
    p.open_in_coords()
    sc = win.pages["shp_coords"].native
    assert win.current == "shp_coords" and sc.shp_combo.currentText() == "Gas_Pipe_ProtZone_Crossing38_2.shp"
    assert sc.pending_areas["cut_area"] == pytest.approx(2000) and sc.table.topLevelItemCount() == 4
    from v2.settings import Settings
    st = Settings(win.settings.path)["tool_state"]["zone_intersect"]
    assert st["zfield"] == "Zona" and st["zvalue"] == "I" and st["parcel"] == parcel


@needs_qt
def test_zone_page_validation_and_no_points(win, tmp_path):
    parcel, zone = _layers(tmp_path)
    win.show_tool("zone_intersect")
    p = win.pages["zone_intersect"].native
    p.create()
    assert win.toast.property("kind") == "error" and win.task is None
    p.parcel_edit.setText(parcel)
    p.zone_edit.setText(zone)
    p.load_zone_meta()
    p.out_edit.setText(str(tmp_path))
    p.field_combo.setCurrentText("Zona")
    p.value_combo.setCurrentText("II")
    p.create()
    assert wait_for(lambda: win.task is None and p.result is not None)
    assert "out_path" not in p.result and not p.coords_btn.isEnabled()


@needs_qt
def test_line_page_crossings_shallow_warning_and_template_copy(win, tmp_path, monkeypatch):
    a = str(tmp_path / "pipe.shp")
    b = str(tmp_path / "comm.shp")
    gpd.GeoDataFrame({"id": [1]}, geometry=[LineString([(X0, Y0), (X0 + 100, Y0)])], crs=32638).to_file(a)
    gpd.GeoDataFrame({"id": [1, 2]}, geometry=[LineString([(X0 + 50, Y0 - 50), (X0 + 50, Y0 + 50)]),
                                               LineString([(X0 + 10, Y0 - 1), (X0 + 90, Y0 + 3)])],
                     crs=32638).to_file(b)
    win.show_tool("line_intersect")
    p = win.pages["line_intersect"].native
    warned = []
    monkeypatch.setattr(p, "_warn", warned.append)
    p.parcel_edit.setText(a)
    p.zone_edit.setText(b)
    p.load_zone_meta()
    p.out_edit.setText(str(tmp_path))
    p.create()
    assert wait_for(lambda: win.task is None and p.result is not None)
    assert p.result["out_path"].endswith("Line_Crossing38_1.shp") and len(p.result["points"]) == 2
    assert warned and "<" in warned[0]                                 # the 2nd line crosses at ~3°
    assert not p.cut_btn.isEnabled()                                   # lines have no area to cut
    # template copy section (3 sets on this page)
    assert len(p.copy_rows) == 3
    src, dst = tmp_path / "tpl", tmp_path / "dst"
    src.mkdir()
    (src / "riverbank_line38.shp").write_text("x")
    row = p.copy_rows[0]
    row["src"].setText(str(src))
    row["rebuild"]()
    assert row["boxes"]["38"].isEnabled() and not row["boxes"]["37"].isEnabled()
    row["boxes"]["38"].setChecked(True)
    row["dst"].setText(str(dst))
    p.copy_templates(row)
    assert os.listdir(dst) == ["riverbank_line38_1.shp"]
