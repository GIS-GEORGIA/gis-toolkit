# -*- coding: utf-8 -*-
"""V2 Database Data Transfer page - the same scenarios as the classic UI tests (test_pgdb_transfer_batch_ui.py),
on real Personal Geodatabases through ODBC, plus decline / merge / validation."""
import importlib.util
import os
import sys
import time

import pytest

import pgdb_fixtures as fx
from pgdb_fixtures import d
from tools import pgdb_transfer_core as c
from tools import pgdb_transfer_flow as flow

needs_qt = pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed")
needs_odbc = pytest.mark.skipif(sys.platform != "win32" or not c.driver_available(),
                                reason="needs Windows + Microsoft Access ODBC driver")


# ----------------------------------------------------------------------------- flow (no UI)
def test_validate_and_texts():
    assert flow.validate("", "b.mdb", "2026") == ("warn", "e_pick_src", {})
    assert flow.validate("a.txt", "b.mdb", "2026")[1] == "e_not_mdb"
    tr = flow.make_tr("ka")
    assert tr("btn_start") == "გადატანის დაწყება" and flow.make_tr("en")("btn_start") == "Start Transfer"
    assert flow.message(tr, c.TransferError("cancelled", "")) == tr("code_cancelled")
    assert flow.batch_lines(tr, [(2024, 3), (2025, 0)], stopped=True)[-1] == tr("batch_stopped")
    assert flow.fidelity_text(tr, None) is None
    assert flow.fidelity_text(tr, {"state": "err", "lines": [], "viol": 0, "err": "x"}) == tr("fid_err", e="x")


# ----------------------------------------------------------------------------- page
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(tmp_path / "data"))
    from v2.main_window import MainWindow
    from v2.settings import Settings
    w = MainWindow(Settings(str(tmp_path / "s.json")))
    yield w
    w.task = None
    w.close()


def wait_for(cond, timeout=120):
    from PySide6.QtCore import QCoreApplication
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    QCoreApplication.processEvents()
    return cond()


def _page(win, answer=True):
    win.show_tool("db_transfer")
    p = win.pages["db_transfer"].native
    p.asks, p.shown = [], []
    p._ask = lambda title, text: p.asks.append(text) or (answer(text) if callable(answer) else answer)
    for n in ("_info", "_warn"):
        setattr(p, n, lambda text, *a, **k: p.shown.append(text))
    p._error = lambda title, text: p.shown.append(text)
    return p


def _idle(p):
    return lambda: not (p.busy or p._year_queue or p._pending_start)


def _dbs(tmp_path, line=True):
    src, dst = fx.make_db(tmp_path, "src.mdb"), fx.make_db(tmp_path, "dst.mdb")
    fx.seed(src, "point", [{"no": "A", "date": d(2024, 1, 1)}, {"no": "B", "date": d(2025, 1, 1)},
                           {"no": "C", "date": d(2026, 1, 1)}])
    if line:
        fx.seed(src, "line", [{"no": "L", "date": d(2025, 5, 5)}])
    return src, dst


@needs_qt
@needs_odbc
def test_all_years_one_confirmation_per_year_and_common_db(win, tmp_path):
    src, dst = _dbs(tmp_path)
    fx.seed(src, "point", [{"no": "B", "date": d(2025, 2, 2)}])      # repeated number inside 2025
    p = _page(win)
    p.src_edit.setText(src)
    p.dst_edit.setText(dst)
    p.year_edit.setText("ყველა")
    p.backup_box.setChecked(False)
    p.copyall_box.setChecked(True)
    p.start()                                                    # check first, then the per-year steps
    assert wait_for(lambda: len(p.asks) >= 3 and _idle(p)() and p.shown)
    cnt = fx.counts(dst)
    assert cnt["point"][0] == 4 and cnt["line"][0] == 1, cnt
    assert len(p.asks) == 3                                      # one confirmation per year
    assert any("2024" in s and "2026" in s for s in p.shown), p.shown   # batch summary
    common = c.all_years_output_path(dst)
    assert fx.counts(common)["point"][0] == 4 and fx.counts(common)["line"][0] == 1
    assert p.table_values()[-1][3] == "1"                        # last year (2026): 1 inserted
    assert p.log_btn.isEnabled() and os.path.isfile(p._log_path)
    from v2.settings import Settings
    st = Settings(win.settings.path)["tool_state"]["db_transfer"]
    assert st["src"] == src and st["copyall"] is True and st["backup"] is False


@needs_qt
@needs_odbc
def test_confirm_once_writes_into_destination_with_one_backup(win, tmp_path):
    src, dst = _dbs(tmp_path)
    p = _page(win)
    p.src_edit.setText(src)
    p.dst_edit.setText(dst)
    p.year_edit.setText("ყველა")
    p.backup_box.setChecked(True)
    p.onego_box.setChecked(True)
    p.start()
    assert wait_for(lambda: p.shown and _idle(p)())
    cnt = fx.counts(dst)
    assert cnt["point"][0] == 3 and cnt["line"][0] == 1, cnt
    assert len(p.asks) == 1                                      # one common confirmation
    assert len([f for f in os.listdir(tmp_path) if "_backup_" in f]) == 1


@needs_qt
@needs_odbc
def test_final_database_is_new_file_and_destination_untouched(win, tmp_path):
    src, dst = _dbs(tmp_path)
    before = open(dst, "rb").read()
    p = _page(win)
    p.src_edit.setText(src)
    p.dst_edit.setText(dst)
    p.year_edit.setText("ყველა")
    p.final_box.setChecked(True)
    p.onego_box.setChecked(True)
    p.start()
    assert wait_for(lambda: p.shown and _idle(p)())
    assert open(dst, "rb").read() == before
    fp = p._final_path
    assert fp and os.path.isfile(fp) and "_FINAL_" in fp
    fc = fx.counts(fp)
    assert fc["point"][0] == 3 and fc["line"][0] == 1, fc
    assert not [f for f in os.listdir(tmp_path) if "_backup_" in f]
    assert any(p.tr("sum_final", p=fp) in s for s in p.shown)


@needs_qt
@needs_odbc
def test_year_tick_boxes_and_only_ticked_years(win, tmp_path):
    src, dst = _dbs(tmp_path, line=False)
    p = _page(win)
    p.src_edit.setText(src)
    p.dst_edit.setText(dst)
    p.year_edit.setText("2025")
    p.backup_box.setChecked(False)
    p.check()
    assert wait_for(lambda: p._infos is not None and p.year_checks and not p.busy)
    assert sorted(p.year_checks) == [2024, 2025, 2026]
    assert [y for y, cb in p.year_checks.items() if cb.isChecked()] == [2025]
    assert "✓" in p.map_grid.itemAtPosition(1, 4).widget().text()
    p.year_checks[2026].click()
    assert p.year_edit.text() == "2025, 2026" and not p.all_years_box.isChecked()
    p.all_years_box.click()
    assert p.year_edit.text() == "2024, 2025, 2026"
    p.year_checks[2024].click()
    assert p.year_edit.text() == "2025, 2026"
    p.start()
    assert wait_for(lambda: p.shown and _idle(p)())
    assert fx.counts(dst)["point"][0] == 2                       # 2024 was not transferred


@needs_qt
@needs_odbc
def test_decline_writes_nothing_and_stops_the_batch(win, tmp_path):
    src, dst = _dbs(tmp_path)
    before = open(dst, "rb").read()
    p = _page(win, answer=False)
    p.src_edit.setText(src)
    p.dst_edit.setText(dst)
    p.year_edit.setText("2024-2026")
    p.backup_box.setChecked(True)
    p.start()
    assert wait_for(lambda: p.asks and _idle(p)() and p.shown)
    assert len(p.asks) == 1 and open(dst, "rb").read() == before
    assert not [f for f in os.listdir(tmp_path) if "_backup_" in f]
    assert p.tr("batch_stopped") in p.shown[-1]
    assert p.table_values()[-1][1:4] == ["1", "0", "1"]          # 2024 analysis: found 1, dup 0, to insert 1


@needs_qt
def test_cancelled_step_is_reported_as_cancelled(win):
    p = _page(win)
    p._year_queue = [2026]
    p._on_error(c.TransferError("cancelled", ""))
    assert p.status.text() == p.tr("st_cancelled") and p.tr("code_cancelled") in p.errlog.toPlainText()
    assert p._year_queue == [] and p.tr("batch_stopped") in p.shown[-1]


@needs_qt
@needs_odbc
def test_gdb_to_gdb_one_click_destination_untouched(win, tmp_path):
    pytest.importorskip("pyogrio")
    from test_pgdb_gdb_bridge import make_gdb, tree_hash          # Qt is already loaded (fixture) - import order safe
    src = make_gdb(tmp_path / "src.gdb", [("A", d(2025, 1, 1)), ("B", d(2025, 5, 5)), ("C", d(2026, 1, 1))])
    dst = make_gdb(tmp_path / "dst.gdb", [("A", d(2025, 3, 3))])
    h_src, h_dst = tree_hash(src), tree_hash(dst)
    p = _page(win)
    p.src_edit.setText(src)
    p.dst_edit.setText(dst)
    p.year_edit.setText("ყველა")
    p.backup_box.setChecked(True)
    p.onego_box.setChecked(True)
    p.start()
    assert wait_for(lambda: p.shown and _idle(p)(), timeout=180)
    final = p._gdb_final
    assert final and os.path.isdir(final) and "_FINAL_" in final, p.shown
    assert tree_hash(src) == h_src and tree_hash(dst) == h_dst
    from pyogrio import read_dataframe
    assert sorted(read_dataframe(final, layer="point")["werilis_no"]) == ["A", "B", "C"]
    assert not [f for f in os.listdir(tmp_path) if "_backup_" in f]
    assert p._fidelity_text and p.tr("fid_ok").split(":")[0] in p._fidelity_text


@needs_qt
@needs_odbc
def test_merge_two_databases(win, tmp_path):
    a = fx.make_db(tmp_path, "a.mdb")
    b = fx.make_db(tmp_path, "b.mdb")
    fx.seed(a, "point", [{"no": "A", "date": d(2024, 1, 1)}])
    fx.seed(b, "point", [{"no": "A", "date": d(2024, 1, 1)}, {"no": "B", "date": d(2025, 1, 1)}])
    p = _page(win)
    p.merge_years([a])
    assert p.shown[-1] == p.tr("merge_few") and win.task is None
    p.merge_years([a, b])
    assert wait_for(lambda: p.shown[-1] != p.tr("merge_few") and not p.busy)
    out = [f for f in os.listdir(tmp_path) if "ALL_YEARS" in f and f.endswith(".mdb")]
    assert len(out) == 1 and fx.counts(str(tmp_path / out[0]))["point"][0] == 2     # A not repeated
    assert os.path.isfile(p._log_path)


@needs_qt
def test_validation_messages(win, tmp_path):
    p = _page(win)
    p.src_edit.setText("")
    p.start()
    assert p.shown[-1] == p.tr("e_pick_src") and win.task is None
    x = tmp_path / "x.mdb"
    x.write_bytes(b"")
    p.src_edit.setText(str(x))
    p.dst_edit.setText(str(x))
    p.check()
    assert p.shown[-1] == p.tr("e_same")
    p.dst_edit.setText(str(tmp_path / "missing.mdb"))
    p.check()
    assert p.shown[-1] == p.tr("e_missing", p=str(tmp_path / "missing.mdb"))
    assert p.src_shown.text().startswith(p.tr("src_shown", name="x.mdb", size="0 KB")[:8])
