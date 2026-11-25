# -*- coding: utf-8 -*-
import importlib.util
import os
import time

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
ezdxf = pytest.importorskip("ezdxf")

from tools import dwg_convert_core as core  # noqa: E402

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")
X0, Y0 = 500000.0, 4650000.0


def _dxf(path):
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((X0, Y0), (X0 + 100, Y0))
    msp.add_point((X0 + 5, Y0 + 5))
    msp.add_lwpolyline([(X0, Y0), (X0 + 10, Y0), (X0 + 10, Y0 + 10), (X0, Y0 + 10)], close=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc.saveas(path)
    return path


# ----------------------------------------------------------------------------- core
def test_free_base_and_no_overwrite(tmp_path):
    src = _dxf(str(tmp_path / "src" / "plan.dxf"))
    out = str(tmp_path / "out")
    r1 = core.convert_file(src, out, "gpkg")
    r2 = core.convert_file(src, out, "gpkg")
    assert r1["out_path"].endswith("plan.gpkg") and r2["out_path"].endswith("plan_2.gpkg")
    before = os.path.getmtime(r1["out_path"])
    r3 = core.convert_file(src, out, "gdb")
    r4 = core.convert_file(src, out, "gdb")
    assert r3["out_path"].endswith("plan.gdb") and r4["out_path"].endswith("plan_2.gdb")
    s1 = core.convert_file(src, out, "shp")
    s2 = core.convert_file(src, out, "shp")
    assert os.path.basename(s1["out_path"]) == "plan" and os.path.basename(s2["out_path"]) == "plan_2"
    assert os.path.getmtime(r1["out_path"]) == before and os.path.isdir(r3["out_path"])


def test_same_name_in_two_subfolders_does_not_collide(tmp_path):
    a = _dxf(str(tmp_path / "src" / "a" / "plan.dxf"))
    b = _dxf(str(tmp_path / "src" / "b" / "plan.dxf"))
    res = core.convert_batch([a, b], str(tmp_path / "out"), "gpkg")
    outs = sorted(os.path.basename(r["out_path"]) for r in res["results"])
    assert res["files_ok"] == 2 and outs == ["plan.gpkg", "plan_2.gpkg"]


def test_missing_crs_is_assumed_only_on_request(tmp_path):
    src = _dxf(str(tmp_path / "plan.dxf"))
    logs = []
    r = core.convert_file(src, str(tmp_path / "o1"), "gpkg", target_epsg=32638, log=logs.append,
                          assume_missing_crs=False)
    lyr = r["layers"][0][0]
    assert gpd.read_file(r["out_path"], layer=lyr).crs is None and any("WITHOUT a CRS" in m for m in logs)
    r = core.convert_file(src, str(tmp_path / "o2"), "gpkg", target_epsg=32638, assume_missing_crs=True)
    assert gpd.read_file(r["out_path"], layer=lyr).crs.to_epsg() == 32638


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
def test_page_folder_convert_with_crs_label(win, tmp_path, monkeypatch):
    _dxf(str(tmp_path / "src" / "plan.dxf"))
    _dxf(str(tmp_path / "src" / "sub" / "road.dxf"))
    out = str(tmp_path / "out")
    win.show_tool("dwg_convert")
    p = win.pages["dwg_convert"].native
    p.src_edit.setText(str(tmp_path / "src"))
    p.out_edit.setText(out)
    p.fmt_buttons["gpkg"].setChecked(True)
    assert not p.assume_box.isEnabled()                         # native CRS: nothing to label
    p.crs_combo.setCurrentIndex(p.crs_combo.findData(32638))
    assert p.assume_box.isEnabled() and not p.assume_box.isChecked()
    p.count()
    assert "2" in p.log_view.toPlainText()
    asked = []
    monkeypatch.setattr(p, "_confirm", lambda t: asked.append(t) or len(asked) > 1)    # 1st no, then yes
    p.run()                                                     # first: declined
    assert win.task is None and not os.path.exists(out)
    p.assume_box.setChecked(True)
    p.run()
    assert wait_for(lambda: win.task is None and os.path.exists(os.path.join(out, "road.gpkg")))
    import pyogrio
    lyr = pyogrio.list_layers(os.path.join(out, "plan.gpkg"))[0][0]
    assert gpd.read_file(os.path.join(out, "plan.gpkg"), layer=lyr).crs.to_epsg() == 32638
    from v2.settings import Settings
    st = Settings(win.settings.path)["tool_state"]["dwg_convert"]
    assert st["crs_epsg"] == 32638 and st["assume_missing_crs"] is True and st["format"] == "gpkg"


@needs_qt
def test_page_validation(win, tmp_path):
    win.show_tool("dwg_convert")
    p = win.pages["dwg_convert"].native
    p.src_edit.setText(str(tmp_path / "missing.dxf"))
    p.run()
    assert win.toast.property("kind") == "error" and win.task is None
