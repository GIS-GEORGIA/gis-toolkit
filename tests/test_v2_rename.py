# -*- coding: utf-8 -*-
import os
import time

import pytest

from tools import translit as core


def _touch(folder, *names):
    for n in names:
        p = os.path.join(str(folder), n)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(n.encode("utf-8"))


SHP = ("არსებული საყრდენი.shp", "არსებული საყრდენი.dbf", "არსებული საყრდენი.shx", "არსებული საყრდენი.shp.xml")


# ----------------------------------------------------------------------------- core
def test_plan_and_apply_renames_whole_dataset_and_undo_restores(tmp_path):
    _touch(tmp_path, *SHP, "ok_latin.shp")
    plan = core.build_plan(str(tmp_path))
    assert sorted(it["new"] for it in plan) == ["arsebuli_sayrdeni.dbf", "arsebuli_sayrdeni.shp",
                                                 "arsebuli_sayrdeni.shp.xml", "arsebuli_sayrdeni.shx"]
    assert {it["status"] for it in plan} == {"ok"}
    logs = []
    ok, sk, undo = core.apply_plan(plan, log=logs.append)
    assert (ok, sk) == (4, 0) and len(undo) == 4 and sum(m.startswith("✓") for m in logs) == 4
    assert sorted(os.listdir(tmp_path)) == ["arsebuli_sayrdeni.dbf", "arsebuli_sayrdeni.shp",
                                            "arsebuli_sayrdeni.shp.xml", "arsebuli_sayrdeni.shx", "ok_latin.shp"]
    assert core.undo_renames(undo) == (4, 0)
    assert sorted(os.listdir(tmp_path)) == sorted(list(SHP) + ["ok_latin.shp"])
    # file contents untouched
    assert open(os.path.join(str(tmp_path), SHP[0]), "rb").read() == SHP[0].encode("utf-8")


def test_conflict_skips_the_whole_dataset_not_just_one_file(tmp_path):
    _touch(tmp_path, *SHP, "arsebuli_sayrdeni.dbf")             # the Latin .dbf already exists
    plan = {it["old"]: it["status"] for it in core.build_plan(str(tmp_path))}
    assert plan["არსებული საყრდენი.dbf"] == "exists"
    assert {plan[n] for n in SHP if not n.endswith(".dbf")} == {"group"}
    ok, sk, undo = core.apply_plan(core.build_plan(str(tmp_path)))
    assert (ok, sk, undo) == (0, 4, [])
    assert all(os.path.exists(os.path.join(str(tmp_path), n)) for n in SHP)


def test_duplicate_targets_are_conflicts(tmp_path):
    _touch(tmp_path, "გზა 1.txt", "გზა-1.txt")
    assert {it["status"] for it in core.build_plan(str(tmp_path))} == {"conflict"}


def test_failure_mid_dataset_rolls_the_dataset_back(tmp_path, monkeypatch):
    _touch(tmp_path, *SHP)
    real = os.rename
    calls = []

    def flaky(src, dst):
        calls.append(src)
        if src.endswith(".shx"):                               # e.g. ArcGIS holds this file open
            raise PermissionError("locked")
        return real(src, dst)

    monkeypatch.setattr(core.os, "rename", flaky)
    logs = []
    ok, sk, undo = core.apply_plan(core.build_plan(str(tmp_path)), log=logs.append)
    monkeypatch.setattr(core.os, "rename", real)
    assert (ok, sk, undo) == (0, 4, [])
    assert sorted(os.listdir(tmp_path)) == sorted(SHP)          # nothing half-renamed
    assert any("left unchanged" in m for m in logs)


def test_recursive_and_undo_never_overwrites(tmp_path):
    _touch(tmp_path, "ქვე/ფაილი.txt", "ზედა.txt")
    assert [it["new"] for it in core.build_plan(str(tmp_path))] == ["zeda.txt"]
    plan = core.build_plan(str(tmp_path), recursive=True)
    assert sorted(it["new"] for it in plan) == ["faili.txt", "zeda.txt"]
    ok, _sk, undo = core.apply_plan(plan)
    assert ok == 2
    _touch(tmp_path, "ზედა.txt")                                # someone re-created the old name
    assert core.undo_renames(undo) == (1, 1)
    assert os.path.exists(os.path.join(str(tmp_path), "zeda.txt"))


def test_check_contents(tmp_path):
    _touch(tmp_path, "a.shp", "b.txt")
    res = core.check_contents(str(tmp_path))
    assert [os.path.basename(p) for p, _ in res] == ["a.shp"]


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


def wait_for(cond, timeout=15):
    from PySide6.QtCore import QCoreApplication
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return cond()


def _page(win):
    win.show_tool("rename")
    return win.pages["rename"].native


@needs_qt
def test_page_is_native_preview_rename_undo(win, tmp_path, monkeypatch):
    d = tmp_path / "data"
    _touch(d, *SHP)
    p = _page(win)
    p.folder_edit.setText(str(d))
    p.preview()
    assert p.table.topLevelItemCount() == 4 and "4" in p.log_view.toPlainText()
    assert sorted(os.listdir(d)) == sorted(SHP)                   # preview changes nothing
    asked = []
    monkeypatch.setattr(p, "_confirm", lambda t: asked.append(t) or False)
    p.rename()
    assert asked and win.task is None and sorted(os.listdir(d)) == sorted(SHP)   # declined -> nothing renamed
    monkeypatch.setattr(p, "_confirm", lambda t: True)
    p.rename()
    assert wait_for(lambda: win.task is None and "arsebuli_sayrdeni.shp" in os.listdir(d))
    assert len(os.listdir(d)) == 4 and p.undo_btn.isEnabled() and p.table.topLevelItemCount() == 0
    p.undo_last()
    assert wait_for(lambda: win.task is None and sorted(os.listdir(d)) == sorted(SHP))
    assert not p.undo_btn.isEnabled()
    from v2.settings import Settings
    assert Settings(win.settings.path)["tool_state"]["rename"]["folder"] == str(d)


@needs_qt
def test_page_validation_and_check(win, tmp_path):
    p = _page(win)
    p.folder_edit.setText(str(tmp_path / "missing"))
    p.rename()
    assert win.toast.property("kind") == "error" and win.task is None
    _touch(tmp_path, "x.shp")
    p.folder_edit.setText(str(tmp_path))
    p.check_contents()
    assert "x.shp" in p.log_view.toPlainText()
