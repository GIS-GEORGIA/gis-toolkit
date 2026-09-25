# -*- coding: utf-8 -*-
"""GUI smoke-ტესტი — მთავარი ფანჯარა რეალურად აიგება ყველა პლატფორმაზე.

Linux CI-ში გაეშვება ``xvfb-run``-ით (ვირტუალური ეკრანი). ეკრანის/tkinter-ის
გარეშე გარემოში ტესტი გამოტოვდება (skip), არ ჩავარდება. მძიმე GIS პაკეტები
(geopandas და ა.შ.) არ არის საჭირო: ხელსაწყო, რომელსაც ისინი აკლია, „error
frame“-ს აჩვენებს — სწორედ ესაა გათვალისწინებული ქცევა.
"""

import os

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """GisBoxApp დროებითი კონფიგით (რეალურ პარამეტრებს არ ეხება)."""
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(tmp_path))
    import gis_box
    monkeypatch.setattr(gis_box, "SETTINGS_FILE",
                        str(tmp_path / "gis_box_settings.json"))
    try:
        a = gis_box.GisBoxApp()
    except tk.TclError as e:                       # ეკრანი არ არის (headless)
        pytest.skip("no display available: %s" % e)
    a.withdraw()
    yield a
    try:
        a.destroy()
    except tk.TclError:
        pass


def test_window_builds_with_all_tools_listed(app):
    app.update()
    assert app.tool_list.size() == len(app.tool_specs) >= 10
    assert len(app.frames) == len(app.tool_specs)


def test_every_tool_opens_or_shows_a_graceful_error_frame(app):
    for i in range(len(app.tool_specs)):
        app.show(i)                                # არ უნდა ვარდებოდეს
        app.update()
        assert app.frames[i] is not None


def test_drag_reorder_moves_spec_frame_and_row_together(app):
    first = app.tool_specs[0]["key"]
    last = app.tool_specs[-1]["key"]
    app._move_tool(0, len(app.tool_specs) - 1)
    assert app.tool_specs[-1]["key"] == first
    assert app.tool_specs[0]["key"] != first
    assert app.tool_list.size() == len(app.tool_specs)
    assert last in [s["key"] for s in app.tool_specs]


def test_reorder_persists_across_restart(app, tmp_path):
    import json
    app._move_tool(0, 3)
    expected = [s["key"] for s in app.tool_specs]
    app.save_settings()
    saved = json.loads((tmp_path / "gis_box_settings.json").read_text("utf-8"))
    assert saved["tool_order"] == expected


def test_theme_and_language_rebuild_keeps_working(app):
    for theme in ("dark", "light"):
        app.theme = theme
        app.apply_theme()
        app.rebuild_ui()
        app.update()
    app.lang = "en"
    app.rebuild_ui()
    app.update()
    assert app.tool_list.size() == len(app.tool_specs)
