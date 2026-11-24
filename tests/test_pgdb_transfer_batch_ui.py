import os
import sys
import time, pytest
tk = pytest.importorskip("tkinter")
import pgdb_fixtures as fx
from pgdb_fixtures import d
from tools import pgdb_transfer_core as c

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not c.driver_available(),
                                reason="needs Windows + Microsoft Access ODBC driver")


def test_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(tmp_path / "data"))
    import gis_box
    monkeypatch.setattr(gis_box, "SETTINGS_FILE", str(tmp_path / "s.json"))
    app = gis_box.GisBoxApp(); app.withdraw()
    src, dst = fx.make_db(tmp_path, "src.mdb"), fx.make_db(tmp_path, "dst.mdb")
    fx.seed(src, "point", [{"no": "A", "date": d(2024, 1, 1)}, {"no": "B", "date": d(2025, 1, 1)},
                           {"no": "B", "date": d(2025, 2, 2)}, {"no": "C", "date": d(2026, 1, 1)}])
    fx.seed(src, "line", [{"no": "L", "date": d(2025, 5, 5)}])
    from tools import pgdb_transfer as T
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(T.messagebox, n, lambda *a, **k: shown.append(a))
    asks = []
    monkeypatch.setattr(T.messagebox, "askyesno", lambda *a, **k: asks.append(a) or True)
    fr = app.show_tool_by_tid("db_transfer")
    fr.src_var.set(src); fr.dst_var.set(dst); fr.year_var.set("ყველა")
    fr.backup_var.set(False); fr.copyall_var.set(True)
    t0 = time.time()
    def poll():
        if time.time() - t0 > 90 or (len(asks) >= 3 and time.time() - t0 > 3 and not (fr.busy or fr._year_queue or fr._pending_start)):
            app.after(1500, app.quit)
        else:
            app.after(200, poll)
    fr._start()
    app.after(200, poll)
    app.mainloop()
    cnt = fx.counts(dst)
    assert cnt["point"][0] == 4 and cnt["line"][0] == 1, cnt
    assert len(asks) == 3                                  # თითო წელზე დადასტურება
    assert any("2024" in str(s) and "2026" in str(s) for s in shown), shown
    common = c.all_years_output_path(dst)
    assert fx.counts(common)["point"][0] == 4 and fx.counts(common)["line"][0] == 1
    app.destroy()


def _run(tmp_path, monkeypatch, final, onego):
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(tmp_path / "data"))
    import gis_box
    monkeypatch.setattr(gis_box, "SETTINGS_FILE", str(tmp_path / "s.json"))
    app = gis_box.GisBoxApp(); app.withdraw()
    src, dst = fx.make_db(tmp_path, "src.mdb"), fx.make_db(tmp_path, "dst.mdb")
    fx.seed(src, "point", [{"no": "A", "date": d(2024, 1, 1)}, {"no": "B", "date": d(2025, 1, 1)},
                           {"no": "C", "date": d(2026, 1, 1)}])
    fx.seed(src, "line", [{"no": "L", "date": d(2025, 5, 5)}])
    from tools import pgdb_transfer as T
    shown, asks = [], []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(T.messagebox, n, lambda *a, **k: shown.append(a))
    monkeypatch.setattr(T.messagebox, "askyesno", lambda *a, **k: asks.append(a) or True)
    fr = app.show_tool_by_tid("db_transfer")
    fr.src_var.set(src); fr.dst_var.set(dst); fr.year_var.set("ყველა")
    fr.backup_var.set(True); fr.final_var.set(final); fr.onego_var.set(onego)
    before = open(dst, "rb").read()
    t0 = time.time()

    def poll():
        done = len(shown) >= 1 and not (fr.busy or fr._year_queue or fr._pending_start)
        if time.time() - t0 > 120 or (done and time.time() - t0 > 3):
            app.after(1500, app.quit)
        else:
            app.after(200, poll)
    fr._start()
    app.after(200, poll)
    app.mainloop()
    out = (fx.counts(dst), asks, shown, before == open(dst, "rb").read(), getattr(fr, "_final_path", None))
    app.destroy()
    return out


def test_one_click_all_years_into_destination(tmp_path, monkeypatch):
    cnt, asks, shown, _same, _fp = _run(tmp_path, monkeypatch, final=False, onego=True)
    assert cnt["point"][0] == 3 and cnt["line"][0] == 1, cnt
    assert len(asks) == 1                                   # ერთი საერთო დადასტურება, წელზე არა
    assert len([f for f in os.listdir(tmp_path) if "_backup_" in f]) == 1   # ბექაპი ერთხელ


def test_final_database_is_a_new_file_and_destination_untouched(tmp_path, monkeypatch):
    cnt, asks, shown, same, fp = _run(tmp_path, monkeypatch, final=True, onego=True)
    assert same, "destination must not change"
    assert cnt["point"][0] == 0 and cnt["line"][0] == 0
    assert fp and os.path.isfile(fp) and "_FINAL_" in fp
    fc = fx.counts(fp)
    assert fc["point"][0] == 3 and fc["line"][0] == 1, fc
    assert not [f for f in os.listdir(tmp_path) if "_backup_" in f]       # ბექაპი საჭირო არაა


def test_years_are_tick_boxes_and_only_ticked_years_are_transferred(tmp_path, monkeypatch):
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(tmp_path / "data"))
    import gis_box
    monkeypatch.setattr(gis_box, "SETTINGS_FILE", str(tmp_path / "s.json"))
    app = gis_box.GisBoxApp(); app.withdraw()
    src, dst = fx.make_db(tmp_path, "src.mdb"), fx.make_db(tmp_path, "dst.mdb")
    fx.seed(src, "point", [{"no": "A", "date": d(2024, 1, 1)}, {"no": "B", "date": d(2025, 1, 1)},
                           {"no": "C", "date": d(2026, 1, 1)}])
    from tools import pgdb_transfer as T
    shown, asks = [], []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(T.messagebox, n, lambda *a, **k: shown.append(a))
    monkeypatch.setattr(T.messagebox, "askyesno", lambda *a, **k: asks.append(a) or True)
    fr = app.show_tool_by_tid("db_transfer")
    fr.src_var.set(src); fr.dst_var.set(dst); fr.year_var.set("2025")
    fr.backup_var.set(False)
    fr._check()
    t0 = time.time()

    def poll():
        if fr._infos is not None and fr.year_checks:
            app.quit()
        elif time.time() - t0 > 60:
            app.quit()
        else:
            app.after(200, poll)
    app.after(200, poll)
    app.mainloop()
    assert sorted(fr.year_checks) == [2024, 2025, 2026]
    assert [y for y, v in fr.year_checks.items() if v.get()] == [2025]       # წინასწარ მონიშნულია ჩაწერილი წელი
    fr.year_checks[2026].set(True); fr._years_changed()
    assert fr.year_var.get() == "2025, 2026" and not fr.all_years_var.get()
    fr.all_years_var.set(True); fr._years_all_toggled()
    assert fr.year_var.get() == "2024, 2025, 2026"
    fr.year_checks[2024].set(False); fr._years_changed()
    assert fr.year_var.get() == "2025, 2026"

    t0 = time.time()

    def poll2():
        if time.time() - t0 > 90 or (len(shown) >= 1 and time.time() - t0 > 3 and not (fr.busy or fr._year_queue or fr._pending_start)):
            app.after(1500, app.quit)
        else:
            app.after(200, poll2)
    fr._start()
    app.after(200, poll2)
    app.mainloop()
    assert fx.counts(dst)["point"][0] == 2                                   # 2024 არ გადავიდა
    app.destroy()
