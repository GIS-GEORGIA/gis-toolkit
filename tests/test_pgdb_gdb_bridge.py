import datetime
import hashlib
import os
import sys

import pytest

pytest.importorskip("PySide6")
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

import pgdb_fixtures as fx
from pgdb_fixtures import d
from tools import pgdb_gdb_bridge as br
from tools import pgdb_transfer_core as c

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not c.driver_available(),
                                reason="needs Windows + Microsoft Access ODBC driver")

CRS = "EPSG:32638"


def make_gdb(path, years_nos):
    """3-layer .gdb (point/line/polygon) with the product's attribute names. years_nos: [(no, datetime)]"""
    n = len(years_nos)
    pts = gpd.GeoDataFrame(
        {"werilis_no": [a for a, _ in years_nos], "TariRI": [pd.Timestamp(b) for _, b in years_nos],
         "Id": pd.array(range(n), dtype="int32"), "ganmcxadeb": ["g"] * n, "teq_piroba": ["t"] * n},
        geometry=[Point(500000 + 10 * i, 4650000 + 10 * i) for i in range(n)], crs=CRS)
    lines = gpd.GeoDataFrame(
        {"werilis_no": [a for a, _ in years_nos], "TariRi": [pd.Timestamp(b) for _, b in years_nos],
         "Id": pd.array(range(n), dtype="int32"), "ganmcxadeb": ["g"] * n, "teqnikuri": ["t"] * n, "STATUS": pd.array([1] * n, dtype="int32")},
        geometry=[LineString([(500000 + i, 4650000), (500010 + i, 4650005), (500020 + i, 4650000)]) for i in range(n)],
        crs=CRS)
    ring = [(500000, 4650000), (500000, 4650100), (500100, 4650100), (500100, 4650000), (500000, 4650000)]
    hole = [(500020, 4650020), (500080, 4650020), (500080, 4650080), (500020, 4650080), (500020, 4650020)]
    polys = gpd.GeoDataFrame(
        {"werilis_no": [a for a, _ in years_nos], "TariRi": [pd.Timestamp(b) for _, b in years_nos],
         "ganmcxadeb": ["g"] * n, "STATUS": pd.array([1] * n, dtype="int32"), "sakadastro": ["s"] * n},
        geometry=[MultiPolygon([Polygon(ring, [hole])]) for _ in range(n)], crs=CRS)
    from pyogrio import write_dataframe
    for name, g in (("point", pts), ("line", lines), ("polygon", polys)):
        write_dataframe(g, str(path), layer=name, driver="OpenFileGDB", promote_to_multi=(name != "point"))
    return str(path)


def tree_hash(p):
    h = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(p)):
        for f in sorted(files):
            if f.endswith(".lock"):
                continue
            h.update(f.encode())
            h.update(open(os.path.join(root, f), "rb").read())
    return h.hexdigest()


def test_paths():
    assert br.is_gdb("x/Data.GDB") and not br.is_gdb("x/a.mdb")
    assert br.final_gdb_path("C:/a/My Data.gdb", stamp="s").endswith("My_Data_FINAL_s.gdb")


def test_gdb_to_mdb_keeps_attributes_geometry_and_crs(tmp_path):
    src = make_gdb(tmp_path / "src.gdb", [("A", d(2025, 1, 1)), ("B", d(2026, 2, 2))])
    before = tree_hash(src)
    out = str(tmp_path / "st.mdb")
    stats = br.gdb_to_mdb(src, out)
    assert {k: v[1] for k, v in stats.items()} == {"point": 2, "line": 2, "polygon": 2}
    assert tree_hash(src) == before                                   # .gdb არ შეცვლილა
    rows = fx.fetch_all(out, "point", cols="werilis_no, TariRI, x, y")
    assert [r[0] for r in rows] == ["A", "B"] and rows[1][1] == d(2026, 2, 2)
    assert rows[0][2] == 500000.0 and rows[0][3] == 4650000.0
    info = c.inspect_db(out)
    assert c.crs_relation(info.layers["polygon"].srtext,
                          __import__("pyproj").CRS.from_user_input(CRS).to_wkt(version="WKT1_ESRI")) == "same"
    # polygon with a hole survives the shape-buffer round trip
    blob = fx.fetch_all(out, "polygon", cols="SHAPE")[0][0]
    stype, parts = c.decode_shape(blob)
    assert stype == 5 and len(parts) == 2
    g = br.parts_to_geometry(stype, parts)
    assert abs(g.area - (100 * 100 - 60 * 60)) < 1e-6


def test_missing_crs_is_never_assumed(tmp_path):
    from pyogrio import write_dataframe
    g = gpd.GeoDataFrame({"werilis_no": ["A"]}, geometry=[Point(1, 1)])          # CRS არ აქვს
    p = str(tmp_path / "nocrs.gdb")
    write_dataframe(g, p, layer="point", driver="OpenFileGDB")
    with pytest.raises(c.TransferError) as e:
        br.gdb_to_mdb(p, str(tmp_path / "o.mdb"))
    assert e.value.code == "gdb_no_crs" and not os.path.exists(str(tmp_path / "o.mdb"))


def test_end_to_end_gdb_source_to_gdb_destination_untouched(tmp_path):
    src = make_gdb(tmp_path / "src.gdb", [("A", d(2025, 1, 1)), ("B", d(2025, 5, 5)), ("C", d(2026, 1, 1))])
    dst = make_gdb(tmp_path / "dst.gdb", [("A", d(2025, 3, 3))])                    # A/2025 უკვე მიმღებშია
    h_src, h_dst = tree_hash(src), tree_hash(dst)
    s_mdb, d_mdb = str(tmp_path / "s.mdb"), str(tmp_path / "d.mdb")
    br.gdb_to_mdb(src, s_mdb)
    br.gdb_to_mdb(dst, d_mdb)
    mapping = {k: (k, k) for k in c.KINDS}
    plan = c.analyze(s_mdb, d_mdb, mapping, 2025)
    assert plan.totals()["found"] == 6 and plan.totals()["duplicates"] == 3 and plan.totals()["to_insert"] == 3
    c.execute(plan, backup=False)
    final = br.final_gdb_path(dst, stamp="t")
    br.append_plan_to_gdb(plan, dst, final)
    assert tree_hash(src) == h_src and tree_hash(dst) == h_dst                      # ორივე ორიგინალი უცვლელია
    from pyogrio import read_dataframe
    pts = read_dataframe(final, layer="point")
    assert sorted(pts["werilis_no"]) == ["A", "B"] and len(pts) == 2
    poly = read_dataframe(final, layer="polygon")
    assert len(poly) == 2 and abs(poly.geometry.iloc[1].area - 6400) < 1e-6
    assert str(read_dataframe(final, layer="point").crs).endswith("32638") or read_dataframe(final, layer="point").crs.to_epsg() == 32638
    # second year goes into the SAME final copy
    plan2 = c.analyze(s_mdb, d_mdb, mapping, 2026)
    c.execute(plan2, backup=False)
    br.append_plan_to_gdb(plan2, dst, final)
    assert sorted(read_dataframe(final, layer="point")["werilis_no"]) == ["A", "B", "C"]
    assert tree_hash(dst) == h_dst


def test_gdb_source_into_mdb_destination(tmp_path):
    src = make_gdb(tmp_path / "src.gdb", [("X", d(2026, 1, 1)), ("Y", d(2026, 2, 1))])
    dst = fx.make_db(tmp_path, "dst.mdb")
    s_mdb = str(tmp_path / "s.mdb")
    br.gdb_to_mdb(src, s_mdb)
    # destination template CRS must match the source before the engine will write (never silently reprojected)
    info_s = c.inspect_db(s_mdb)
    dinfo = c.inspect_db(dst)
    cn = c.connect(dst, "excl")
    cur = cn.cursor()
    for k in c.KINDS:
        nl = dinfo.by_kind(k)[0]
        cur.execute("UPDATE GDB_SpatialRefs SET SRTEXT=? WHERE SRID=?", (info_s.layers[k].srtext, nl.srid))
    cn.commit()
    cn.close()
    plan = c.analyze(s_mdb, dst, {k: (k, k) for k in c.KINDS}, 2026)
    c.execute(plan, backup=False)
    assert fx.counts(dst)["point"][0] == 2 and fx.counts(dst)["polygon"][0] == 2


def test_gui_gdb_to_gdb_one_click_destination_untouched(tmp_path, monkeypatch):
    import time
    pytest.importorskip("tkinter")
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(tmp_path / "data"))
    import gis_box
    monkeypatch.setattr(gis_box, "SETTINGS_FILE", str(tmp_path / "s.json"))
    app = gis_box.GisBoxApp(); app.withdraw()
    src = make_gdb(tmp_path / "src.gdb", [("A", d(2025, 1, 1)), ("B", d(2025, 5, 5)), ("C", d(2026, 1, 1))])
    dst = make_gdb(tmp_path / "dst.gdb", [("A", d(2025, 3, 3))])
    h_src, h_dst = tree_hash(src), tree_hash(dst)
    from tools import pgdb_transfer as T
    shown, asks = [], []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(T.messagebox, n, lambda *a, **k: shown.append(a))
    monkeypatch.setattr(T.messagebox, "askyesno", lambda *a, **k: asks.append(a) or True)
    fr = app.show_tool_by_tid("db_transfer")
    fr.src_var.set(src); fr.dst_var.set(dst); fr.year_var.set("ყველა")
    fr.backup_var.set(True); fr.onego_var.set(True)
    t0 = time.time()

    def poll():
        done = len(shown) >= 1 and not (fr.busy or fr._year_queue or fr._pending_start)
        if time.time() - t0 > 150 or (done and time.time() - t0 > 3):
            app.after(1500, app.quit)
        else:
            app.after(200, poll)
    fr._start()
    app.after(200, poll)
    app.mainloop()
    final = fr._gdb_final
    errs = [s for s in shown if "error" in str(s).lower() or "ვერ" in str(s)]
    app.destroy()
    assert final and os.path.isdir(final) and "_FINAL_" in final, (shown, errs)
    assert tree_hash(src) == h_src and tree_hash(dst) == h_dst
    from pyogrio import read_dataframe
    assert sorted(read_dataframe(final, layer="point")["werilis_no"]) == ["A", "B", "C"]
    assert not [f for f in os.listdir(tmp_path) if "_backup_" in f]
