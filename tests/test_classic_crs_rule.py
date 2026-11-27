# -*- coding: utf-8 -*-
"""Classic Geometry collection / DWG-DXF conversion: a missing CRS is never assumed unless the user ticks the box
(default off) - the same rule as the V2 pages. Real Tk windows, real files."""
import os
import time

import pytest

tk = pytest.importorskip("tkinter")
gpd = pytest.importorskip("geopandas")
ezdxf = pytest.importorskip("ezdxf")
from shapely.geometry import Point  # noqa: E402

X0, Y0 = 500000.0, 4650000.0


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(tmp_path / "data"))
    import gis_box
    monkeypatch.setattr(gis_box, "SETTINGS_FILE", str(tmp_path / "s.json"))
    a = gis_box.GisBoxApp()
    a.withdraw()
    yield a
    a.destroy()


def _dialogs(monkeypatch, module):
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(module.messagebox, n, lambda *a, **k: shown.append(a))
    monkeypatch.setattr(module.messagebox, "askyesno", lambda *a, **k: True)
    return shown


def _run(app, fr, timeout=60):
    fr._start()
    t0 = time.time()
    while (fr.busy or not fr.msg_queue.empty()) and time.time() - t0 < timeout:
        app.update()
        time.sleep(0.02)
    for _ in range(5):
        app.update()
        time.sleep(0.02)


def _dxf(path):
    doc = ezdxf.new()
    doc.modelspace().add_line((X0, Y0), (X0 + 100, Y0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc.saveas(path)
    return path


def test_geom_collect_skips_files_without_crs_unless_ticked(app, tmp_path, monkeypatch):
    from tools import geom_collect as G
    shown = _dialogs(monkeypatch, G)
    src = tmp_path / "src"
    src.mkdir()
    gpd.GeoDataFrame({"a": [1]}, geometry=[Point(X0, Y0)], crs="EPSG:32638").to_file(src / "with_crs.shp")
    gpd.GeoDataFrame({"a": [2]}, geometry=[Point(X0 + 1, Y0)]).to_file(src / "no_crs.shp")
    fr = app.show_tool_by_key("Geometry → GeoPackage")         # this tool has a key, no tid
    assert fr.assume_var.get() is False                         # default: never assume
    fr.src_var.set(str(src))
    fr.out_var.set(str(tmp_path / "out" / "c.gpkg"))
    os.makedirs(tmp_path / "out")
    fr._set_all_formats(False)
    fr.fmt_vars[0][0].set(True)                                 # ESRI Shapefile
    _run(app, fr)
    outs = sorted(os.listdir(tmp_path / "out"))
    assert len(outs) == 1, outs
    pts = gpd.read_file(tmp_path / "out" / outs[0], layer="points")
    assert len(pts) == 1 and pts.crs.to_epsg() == 32638         # only the file with a CRS
    assert any(fr.tr("no_crs_skipped", n=1) in str(s) for s in shown), shown

    fr.assume_var.set(True)                                     # the user's explicit choice
    _run(app, fr)
    outs = sorted(os.listdir(tmp_path / "out"))
    assert len(outs) == 2                                       # a NEW file (_2); the first is not overwritten
    second = [o for o in outs if o.endswith("_2.gpkg")]
    assert len(second) == 1, outs
    pts2 = gpd.read_file(tmp_path / "out" / second[0], layer="points")
    assert len(pts2) == 2 and pts2.crs.to_epsg() == 32638
    fr.save_state()
    assert fr._state()["assume_missing_crs"] is True


def test_dwg_convert_writes_without_crs_unless_ticked(app, tmp_path, monkeypatch):
    from tools import dwg_convert as D
    _dialogs(monkeypatch, D)
    src = _dxf(str(tmp_path / "src" / "plan.dxf"))
    fr = app.show_tool_by_tid("dwg_convert")
    assert fr.assume_var.get() is False
    assert "disabled" in fr.assume_cb.state()                   # native CRS: nothing to label
    fr.src_var.set(src)
    fr.out_var.set(str(tmp_path / "out"))
    fr.fmt_var.set("gpkg")
    label_38 = next(lbl for lbl, e in fr._crs_by_label.items() if e == 32638)
    fr.crs_var.set(label_38)
    fr._sync_assume()
    assert "disabled" not in fr.assume_cb.state()
    _run(app, fr)
    import pyogrio
    p1 = str(tmp_path / "out" / "plan.gpkg")
    lyr = pyogrio.list_layers(p1)[0][0]
    assert gpd.read_file(p1, layer=lyr).crs is None             # not assumed
    fr.assume_var.set(True)
    _run(app, fr)
    p2 = str(tmp_path / "out" / "plan_2.gpkg")
    assert gpd.read_file(p2, layer=lyr).crs.to_epsg() == 32638  # labelled on request; plan.gpkg untouched
    assert gpd.read_file(p1, layer=lyr).crs is None
