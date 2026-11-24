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
