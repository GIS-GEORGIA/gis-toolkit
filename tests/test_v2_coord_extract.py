# -*- coding: utf-8 -*-
import csv
import importlib.util
import json
import os
import time

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
openpyxl = pytest.importorskip("openpyxl")

from tools.coordextract import export as ex  # noqa: E402
from tools.coordextract import ocr  # noqa: E402

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")


# ----------------------------------------------------------------------------- core
def test_format_target_filled_counts_cells_before_overwrite(tmp_path):
    p = str(tmp_path / "c.xlsx")
    ex.rows_to_xlsx(p, [("1", "500100", "4650100"), ("2", "500200", "4650200")])
    assert ex.format_target_filled(p) == 0
    _saved, n = ex.format_xlsx(p)
    assert n == 2 and ex.format_target_filled(p) == 9          # header + 2 rows, 3 columns
    ws = openpyxl.load_workbook(p).active
    assert ws["B2"].value == 500100 and ws["E6"].value == "№"   # original block untouched


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


def wait_for(cond, timeout=60):
    from PySide6.QtCore import QCoreApplication
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return cond()


def _table_image(path, rows):
    img = np.full((60 + 50 * len(rows), 720, 3), 255, np.uint8)
    cv2.putText(img, "No      X            Y", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    for i, (n, x, y) in enumerate(rows):
        cv2.putText(img, f"{n}    {x}     {y}", (20, 90 + 50 * i), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    ok, buf = cv2.imencode(".png", img)
    buf.tofile(path)                      # works for non-ASCII paths, like the page's reader
    return img


def _page(win):
    win.show_tool("coord_extractor")
    p = win.pages["coord_extractor"].native
    p._info = lambda *a: p.__dict__.setdefault("infos", []).append(a)
    p._error = lambda *a: p.__dict__.setdefault("errors", []).append(a)
    return p


@needs_qt
def test_image_crop_ocr_edit_export(win, tmp_path, monkeypatch):
    path = str(tmp_path / "რუკა.png")                           # Georgian file name on purpose
    _table_image(path, [("1", "500100", "4650100")])
    p = _page(win)
    assert p.load_image_file(path) and p.cv_img is not None
    p.run_ocr()                                                  # no box yet
    assert p.infos[-1][1] == p._z("no_sel") and win.task is None
    p.set_mode("crop")
    p._on_press(5, 5)
    p._on_move(300, 80)
    p._on_release(900, 2000)                                     # clamped to the image
    assert p.crop_rect == (5, 5, 720, 110)

    fake = ocr.OCRResult(rows=[ocr.CoordRow("1", 500100.0, 4650100.0), ocr.CoordRow("2", 500200.5, None)],
                         raw_text="x", backend="fake")
    seen = {}
    monkeypatch.setattr(ocr, "extract_table", lambda crop, backend=None: seen.setdefault("shape", crop.shape) and fake)
    p.run_ocr()
    assert wait_for(lambda: win.task is None and p.ocr_table.rowCount() == 2)
    assert seen["shape"][:2] == (105, 715)
    assert p.rows_of(p.ocr_table) == [("1", "500100", "4650100"), ("2", "500200.500", "")]
    p.ocr_table.item(1, 2).setText("4650200")                    # user fixes an OCR gap
    p.add_row()
    p.ocr_table.selectRow(2)
    p._delete_rows(p.ocr_table)
    out = p.export(p.ocr_table, "xlsx", path=str(tmp_path / "o.xlsx"))
    ws = openpyxl.load_workbook(out).active
    assert [c.value for c in ws[3]] == ["2", 500200.5, 4650200]
    p.export(p.ocr_table, "csv", path=str(tmp_path / "o.csv"))
    with open(tmp_path / "o.csv", encoding="utf-8-sig") as f:
        assert list(csv.reader(f))[1] == ["1", "500100", "4650100"]
    from v2.settings import Settings
    assert Settings(win.settings.path)["tool_state"]["coord_extractor"]["last_dir"] == str(tmp_path)


@needs_qt
def test_georeference_area_and_json(win, tmp_path):
    p = _page(win)
    p.set_image(np.full((400, 400, 3), 255, np.uint8), "test")
    p.compute_geo()
    assert p.infos[-1][1] == p._z("no_fit")
    # 1 px = 2 m, image y grows downwards, world Y upwards
    for px, py in ((0, 0), (100, 0), (0, 100)):
        p.add_control_point(px, py, xy=(500000 + 2 * px, 4650000 - 2 * py))
    assert p.model is not None and p.model.rmse < 1e-6 and "3" in p.fit_lbl.text()
    for v in ((10, 10), (60, 10), (60, 60), (10, 60)):
        p.polygon_px.append(v)
    p.compute_geo()
    assert p.rows_of(p.geo_table)[0] == ("1", "500020", "4649980")
    assert "10,000.0" in p.area_lbl.text()                       # 100 m x 100 m
    out = p.export(p.geo_table, "json", path=str(tmp_path / "g.json"))
    data = json.load(open(out, encoding="utf-8"))
    assert len(data["points"]) == 4 and data["crs_note"]
    p.cp_table.selectRow(2)
    p.delete_control_points()
    assert len(p.control_points) == 2 and p.model.n_points == 2
    p.clear_polygon()
    assert p.geo_table.rowCount() == 0 and not p.polygon_px


@needs_qt
def test_format_excel_asks_before_overwriting(win, tmp_path):
    p = _page(win)
    x = str(tmp_path / "f.xlsx")
    ex.rows_to_xlsx(x, [("1", "500100", "4650100")])
    answers = []
    p._confirm = lambda t: answers.append(t) or False
    assert p.format_excel(x) is None and openpyxl.load_workbook(x).active["E6"].value is None
    p._confirm = lambda t: answers.append(t) or True
    assert p.format_excel(x) == 1 and len(answers) == 2         # target empty: one question only
    replies = iter([True, False])                                # yes to "add a copy", no to "overwrite?"
    p._confirm = lambda t: answers.append(t) or next(replies)
    assert p.format_excel(x) is None and answers[-1] == p._z("format_busy", n=6)   # header + 1 row, 3 columns


@needs_qt
def test_paste_from_clipboard_and_image_conversion(win):
    from PySide6.QtGui import QGuiApplication
    from v2.pages.coord_extract_page import bgr_to_qimage, qimage_to_bgr
    img = np.zeros((31, 47, 3), np.uint8)
    img[5, 7] = (10, 20, 30)
    assert (qimage_to_bgr(bgr_to_qimage(img)) == img).all()
    p = _page(win)
    QGuiApplication.clipboard().clear()
    assert p.paste_image() is False and win.toast.property("kind") == "error"
    QGuiApplication.clipboard().setImage(bgr_to_qimage(img))
    assert p.paste_image() and p.cv_img.shape == (31, 47, 3) and tuple(p.cv_img[5, 7]) == (10, 20, 30)


@needs_qt
def test_screen_snip_maps_selection_to_image_pixels(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from v2.pages.coord_extract_page import ScreenSnip
    shot = np.zeros((600, 800, 3), np.uint8)
    got = []
    s = ScreenSnip(shot, "hint", got.append)
    s.setGeometry(0, 0, 400, 300)                                # widget at half the image size (HiDPI-like)
    QTest.mousePress(s, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
    QTest.mouseRelease(s, Qt.MouseButton.LeftButton, pos=QPoint(110, 70))
    assert got and got[0].shape[:2] == (100, 200)
    got.clear()
    s2 = ScreenSnip(shot, "hint", got.append)
    QTest.keyClick(s2, Qt.Key.Key_Escape)
    assert got == [None]


@needs_qt
@pytest.mark.skipif(not ocr.available_backends(), reason="no OCR backend installed")
def test_real_ocr_on_generated_table(win, tmp_path):
    path = str(tmp_path / "t.png")
    rows = [("1", "500100", "4650100"), ("2", "500250", "4650375")]
    img = _table_image(path, rows)
    p = _page(win)
    p.load_image_file(path)
    p.set_crop((0, 0), (img.shape[1], img.shape[0]))
    p.run_ocr()
    assert wait_for(lambda: win.task is None and p.ocr_table.rowCount() > 0, timeout=120)
    got = p.rows_of(p.ocr_table)
    assert [(r[1], r[2]) for r in got] == [(x, y) for _n, x, y in rows]
