# -*- coding: utf-8 -*-
"""GUI smoke-ტესტი — მთავარი ფანჯარა რეალურად აიგება ყველა პლატფორმაზე.

Linux CI-ში გაეშვება ``xvfb-run``-ით (ვირტუალური ეკრანი). ეკრანის/tkinter-ის
გარეშე გარემოში ტესტი გამოტოვდება (skip), არ ჩავარდება. მძიმე GIS პაკეტები
(geopandas და ა.შ.) არ არის საჭირო: ხელსაწყო, რომელსაც ისინი აკლია, „error
frame“-ს აჩვენებს — სწორედ ესაა გათვალისწინებული ქცევა.

**ერთი ფანჯარა მთელ მოდულზე** (module-scoped): Tk-ის ხელახალი შექმნა/განადგურება
ერთ პროცესში არასტაბილურია (განსაკუთრებით Windows-ზე), ხოლო რეალურ პროგრამაშიც
ერთი root არსებობს. ტესტები თანმიმდევრულად მუშაობენ ერთ მდგომარეობაზე; ბოლო
ტესტი (თემა/ენა) აპს გადააგებს, ამიტომ ბოლოშია.
"""

import json

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """GisBoxApp დროებითი კონფიგით (რეალურ პარამეტრებს არ ეხება)."""
    data = tmp_path_factory.mktemp("gis_box_data")
    mp = pytest.MonkeyPatch()
    mp.setenv("GIS_BOX_DATA_DIR", str(data))
    import gis_box
    mp.setattr(gis_box, "SETTINGS_FILE", str(data / "gis_box_settings.json"))
    try:
        a = gis_box.GisBoxApp()
    except tk.TclError as e:                       # ეკრანი არ არის (headless)
        mp.undo()
        pytest.skip("no display available: %s" % e)
    a.withdraw()
    a.data_path = data
    yield a
    try:
        a.destroy()
    except tk.TclError:
        pass
    mp.undo()


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
    keys_before = [s["key"] for s in app.tool_specs]
    n = len(keys_before)
    app._move_tool(0, n - 1)
    keys_after = [s["key"] for s in app.tool_specs]
    assert keys_after[-1] == keys_before[0]
    assert keys_after[:-1] == keys_before[1:]      # დანარჩენი ერთით ავიდა
    assert app.tool_list.size() == n
    assert len(app.frames) == n


def test_reorder_persists_to_settings_file(app):
    app._move_tool(0, 3)
    expected = [s["key"] for s in app.tool_specs]
    app.save_settings()
    saved = json.loads(
        (app.data_path / "gis_box_settings.json").read_text("utf-8"))
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
