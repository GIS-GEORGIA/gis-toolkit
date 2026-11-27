# -*- coding: utf-8 -*-
import os
import time

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
openpyxl = pytest.importorskip("openpyxl")
from shapely.geometry import MultiPoint, Point  # noqa: E402

from tools import shp_coords_core as core  # noqa: E402

PTS = [(500123.456, 4650987.123), (500200.5, 4651000.49)]


def _pts(folder, name="Gas_Pipe_Crossing38.shp", crs=32638, pts=PTS, ids=None):
    p = os.path.join(str(folder), name)
    gpd.GeoDataFrame({"Id": ids or list(range(1, len(pts) + 1))}, geometry=[Point(x, y) for x, y in pts],
                     crs=crs).to_file(p)
    return p


def _cells(path):
    ws = openpyxl.load_workbook(path).active
    return ws, {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}


# ----------------------------------------------------------------------------- core
def test_scan_pick_zone_and_read(tmp_path):
    a = _pts(tmp_path, "other.shp")
    _pts(tmp_path, "Gas_Pipe_Crossing38.shp")
    gpd.GeoDataFrame({"a": [1]}, geometry=[Point(0, 0).buffer(1)], crs=32638).to_file(str(tmp_path / "poly.shp"))
    m = core.scan_point_shapefiles(str(tmp_path))
    assert sorted(m) == ["Gas_Pipe_Crossing38.shp", "other.shp"]
    assert core.auto_pick(m) == "Gas_Pipe_Crossing38.shp" and core.auto_pick(["x.shp"]) == "x.shp"
    assert core.detect_zone(a) == 38 and core.count_points(a) == 2 and not core.crs_missing(a)
    pts = core.read_points(a, 38)
    assert [(i, round(x, 3), round(y, 3)) for i, x, y in pts] == [(1, 500123.456, 4650987.123), (2, 500200.5, 4651000.49)]


def test_reprojection_to_chosen_zone_and_multipoint(tmp_path):
    g = gpd.GeoDataFrame({"Id": [5]}, geometry=[MultiPoint([(44.8, 41.7), (44.81, 41.71)])], crs=4326)
    p = str(tmp_path / "mp.shp")
    g.to_file(p)
    pts = core.read_points(p, 38)
    assert len(pts) == 2 and all(4_000_000 < y < 5_000_000 for _i, _x, y in pts)


def test_parse_angle_block_rows_and_clipboard():
    assert core.parse_angle(" 37,5 ") == 37.5 and core.parse_angle("90°") == 90 and core.parse_angle("x") is None
    h, rows = core.block_rows([(1, 10.6, 20.4)], "int", True, 45, "კუთხე")
    assert h == ["№", "X", "Y", "კუთხე"] and rows == [[1, 11, 20, "45°"]]
    html, text = core.clipboard_payload("<ქუდი>", h, rows)
    assert "&lt;ქუდი&gt;" in html and 'colspan="4"' in html and text.splitlines()[0] == "<ქუდი>"


def test_workbook_layout_title_angle_and_areas(tmp_path):
    out = str(tmp_path / "o.xlsx")
    core.write_workbook(out, "s.shp", [(7, 500123.4567, 4650987.1), (None, 1.0, 2.0)], "double", "ქუდი", True, 37,
                        "გადაკვეთის კუთხე", areas={"parcel_area": 1000.38126, "cut_area": 0, "remainder_area": 1000.38126})
    ws, c = _cells(out)
    assert [c["A1"], c["B1"], c["C1"], c["D1"]] == ["FID", "Id", "POINT_X", "POINT_Y"]
    assert c["B2"] == 7 and c["B3"] == 0 and c["C2"] == 500123.4567
    assert c["G6"] == "ქუდი" and c["G9"] == "№" and c["J9"] == "გადაკვეთის კუთხე" and c["J10"] == 37
    assert ws["J10"].number_format == core.ANGLE_FMT
    # areas: right of the copy (G:J -> starts at M), same start row 6, kv.m
    assert any(isinstance(v, str) and "kv.m" in v for v in c.values())
    assert any(k.startswith("M") and "ნაკვეთის ფართი" in str(v) for k, v in c.items())


def test_templates_file_add_delete(tmp_path):
    f = str(tmp_path / "t.txt")
    assert core.add_template("ჩემი ქუდი", f) and core.file_templates(f) == ["ჩემი ქუდი"]
    assert not core.add_template("ცუდი ?? ქუდი", f)
    assert core.templates(f)[: len(core.DEFAULT_TEMPLATES)] == core.DEFAULT_TEMPLATES
    assert not core.delete_template(core.DEFAULT_TEMPLATES[0], f)
    assert core.delete_template("ჩემი ქუდი", f) and core.file_templates(f) == []


def test_apply_degree(tmp_path):
    out = str(tmp_path / "o.xlsx")
    core.write_workbook(out, "s", [(1, 1.0, 2.0), (2, 3.0, 4.0)], "double", "", True, None, "gadakveTis kuTxe")
    ws = openpyxl.load_workbook(out)
    ws.active["J7"] = "12,5"
    ws.save(out)
    assert core.apply_degree(out) >= 2
    assert openpyxl.load_workbook(out).active["J7"].value == 12.5
    plain = str(tmp_path / "p.xlsx")
    openpyxl.Workbook().save(plain)
    before = os.path.getmtime(plain)
    assert core.apply_degree(plain) == 0 and os.path.getmtime(plain) == before     # untouched


# ----------------------------------------------------------------------------- page
import importlib.util  # noqa: E402

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")


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


def _page(win, tmp_path):
    win.show_tool("shp_coords")
    p = win.pages["shp_coords"].native
    p.tpath = str(tmp_path / "templates.txt")          # never touch the real templates file
    p._refresh_templates()
    return p


@needs_qt
def test_page_scan_preview_export(win, tmp_path, monkeypatch):
    d = tmp_path / "d"
    d.mkdir()
    _pts(d, "aaa.shp")
    _pts(d, "Gas_Pipe_Crossing38.shp")
    p = _page(win, tmp_path)
    p.folder_edit.setText(str(d))
    p.scan()
    assert p.shp_combo.currentText() == "Gas_Pipe_Crossing38.shp" and p.table.topLevelItemCount() == 2
    assert "38" in p.zauto.text()
    p.v_int.setChecked(True)
    assert p.table.topLevelItem(0).text(1) == "500123"
    asked = []
    monkeypatch.setattr(p, "_confirm", lambda t: asked.append(t) or False)
    p.export()
    assert asked and win.task is None                                   # integer rounding needs consent
    monkeypatch.setattr(p, "_confirm", lambda t: True)
    out = str(tmp_path / "out.xlsx")
    monkeypatch.setattr(p, "_save_name", lambda *a: out)
    p.angle_box.setChecked(True)
    p.angle_all_edit.setText("37")
    p.export()
    assert wait_for(lambda: win.task is None and os.path.exists(out))
    _ws, c = _cells(out)
    assert c["H7"] == 500123 and c["J7"] == 37
    from v2.settings import Settings
    st = Settings(win.settings.path)["tool_state"]["shp_coords"]
    assert st["vtype"] == "int" and st["angle_all"] == "37" and st["folder"] == str(d)


@needs_qt
def test_page_no_crs_needs_consent_and_batch_skips_it(win, tmp_path, monkeypatch):
    d = tmp_path / "d"
    d.mkdir()
    nc = _pts(d, "nocrs.shp", crs=None)
    if os.path.exists(nc[:-4] + ".prj"):
        os.remove(nc[:-4] + ".prj")
    _pts(d, "good.shp")
    p = _page(win, tmp_path)
    p.folder_edit.setText(str(d))
    p.scan()
    p.shp_combo.setCurrentText("nocrs.shp")
    p.z38.setChecked(True)
    asked = []
    monkeypatch.setattr(p, "_confirm", lambda t: asked.append(t) or False)
    saved = []
    monkeypatch.setattr(p, "_save_name", lambda *a: saved.append(1) or "")
    p.export()
    assert asked and ".prj" in asked[0] and not saved                  # declined -> nothing asked further
    out = tmp_path / "batch"
    out.mkdir()
    (out / "good.xlsx").write_bytes(b"keep me")                        # existing file must survive
    monkeypatch.setattr(p, "_dir_name", lambda *a: str(out))
    p.batch()
    assert wait_for(lambda: win.task is None and "Batch" in p.log_view.toPlainText())
    assert (out / "good.xlsx").read_bytes() == b"keep me" and not (out / "nocrs.xlsx").exists()
    log = p.log_view.toPlainText()
    assert "nocrs.shp" in log and "good.xlsx" in log


@needs_qt
def test_page_clipboard_and_templates(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    d = tmp_path / "d"
    d.mkdir()
    _pts(d)
    p = _page(win, tmp_path)
    p.folder_edit.setText(str(d))
    p.scan()
    monkeypatch.setattr(p, "_ask_template", lambda: "ჩემი ქუდი")
    p._add_template()
    assert p.tmpl_combo.currentText() == "ჩემი ქუდი" and core.file_templates(p.tpath) == ["ჩემი ქუდი"]
    p.copy_clipboard()
    md = QApplication.clipboard().mimeData()
    assert "ჩემი ქუდი" in md.text() and "500123.456" in md.text()
    monkeypatch.setattr(p, "_confirm", lambda t: True)
    p._delete_template()
    assert core.file_templates(p.tpath) == []
