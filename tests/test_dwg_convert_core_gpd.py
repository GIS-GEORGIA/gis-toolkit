# -*- coding: utf-8 -*-
"""dwg_convert_core — კონვერტაციის ტესტები (geopandas/pyogrio საჭირო).

წყაროდ, DXF-write დრაივერზე დამოკიდებულების ასაცილებლად, ვწერთ პატარა GPKG-ს
(``convert_file`` ნებისმიერ GDAL-ვექტორს კითხულობს — შეზღუდვა მხოლოდ UI-ის
ფაილის ფილტრშია, არა ლოგიკაში). ცალკე ფაილშია, რადგან ``pytest.importorskip``
მოდულის დონეზე **მთელ ფაილს** გამოტოვებს — GDAL-ისგან დამოუკიდებელი დამხმარეები
(``test_dwg_convert_core.py``) ცალკე დარჩა, რომ CI-ში (სადაც geopandas არაა)
მაინც გაეშვას.
"""

import os
import subprocess

import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point, LineString, Polygon  # noqa: E402
from tools.dwg_convert_core import convert_file, convert_batch  # noqa: E402
import tools.gdb2postgis_core as g2p_core                # noqa: E402


def _make_source(path, mixed=True):
    """სინთეზური წყარო (.gpkg — DXF-write დრაივერზე დამოკიდებულების გარეშე)."""
    if mixed:
        gdf = gpd.GeoDataFrame(
            {"Layer": ["L1", "L1", "L2"], "Text": ["a", "b", "c"]},
            geometry=[Point(0, 0), LineString([(0, 0), (1, 1)]),
                     Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])],
            crs="EPSG:32638")
    else:
        gdf = gpd.GeoDataFrame({"a": [1, 2]},
                               geometry=[Point(0, 0), Point(1, 1)],
                               crs="EPSG:32638")
    gdf.to_file(path, layer="entities", driver="GPKG")
    return path


def test_convert_to_gpkg_keeps_mixed_geometry_and_attributes(tmp_path):
    src = _make_source(str(tmp_path / "src.gpkg"))
    r = convert_file(src, str(tmp_path / "out"), "gpkg")
    assert r["error"] is None
    assert r["layers"] == [("entities", 3)]
    back = gpd.read_file(r["out_path"], layer="entities")
    assert sorted(back.geom_type.unique()) == ["LineString", "Point", "Polygon"]
    assert "Text" in back.columns


def test_convert_to_gdb_splits_mixed_geometry_by_type(tmp_path):
    src = _make_source(str(tmp_path / "src.gpkg"))
    r = convert_file(src, str(tmp_path / "out"), "gdb")
    assert r["error"] is None
    names = sorted(n for n, _c in r["layers"])
    assert names == ["entities_line", "entities_point", "entities_polygon"]


def test_convert_to_shp_splits_into_separate_files(tmp_path):
    src = _make_source(str(tmp_path / "src.gpkg"))
    r = convert_file(src, str(tmp_path / "out"), "shp")
    assert r["error"] is None
    files = set(os.listdir(r["out_path"]))
    assert "entities_point.shp" in files
    assert "entities_line.shp" in files
    assert "entities_polygon.shp" in files


def test_convert_uniform_geometry_no_type_suffix(tmp_path):
    src = _make_source(str(tmp_path / "src.gpkg"), mixed=False)
    r = convert_file(src, str(tmp_path / "out"), "gdb")
    assert [n for n, _c in r["layers"]] == ["entities"]     # ერთი ტიპი — სუფიქსის გარეშე


def test_convert_reprojects_to_target_crs(tmp_path):
    src = _make_source(str(tmp_path / "src.gpkg"), mixed=False)
    r = convert_file(src, str(tmp_path / "out"), "gpkg", target_epsg=32637)
    back = gpd.read_file(r["out_path"], layer="entities")
    assert back.crs.to_epsg() == 32637


def test_convert_file_unreadable_source_returns_error(tmp_path):
    bad = tmp_path / "broken.dxf"
    bad.write_bytes(b"not a real dxf")
    r = convert_file(str(bad), str(tmp_path / "out"), "gpkg")
    assert r["error"] is not None
    assert r["layers"] == []


def test_convert_batch_aggregates_and_reports_progress(tmp_path):
    src1 = _make_source(str(tmp_path / "a.gpkg"), mixed=False)
    src2 = _make_source(str(tmp_path / "b.gpkg"), mixed=False)
    prog = []
    res = convert_batch([src1, src2], str(tmp_path / "out"), "gpkg",
                        progress=lambda i, n: prog.append((i, n)))
    assert res["files_ok"] == 2 and res["files_skipped"] == 0
    assert prog == [(1, 2), (2, 2)]


def test_convert_batch_cancel_stops_early(tmp_path):
    src1 = _make_source(str(tmp_path / "a.gpkg"), mixed=False)
    src2 = _make_source(str(tmp_path / "b.gpkg"), mixed=False)
    res = convert_batch([src1, src2], str(tmp_path / "out"), "gpkg",
                        cancel=lambda: True)
    assert res["cancelled"] is True


def test_dwg_bridge_success_reads_via_temp_gpkg_and_names_output_from_dwg(
        tmp_path, monkeypatch):
    """DWG-ის „წარმატებული" ბილიკის სრული ინტეგრაცია: system ogr2ogr (მოსახსნელი)
    ქმნის GPKG-ს → convert_file ისევე აგრძელებს, როგორც ჩვეულებრივ წყაროზე,
    და გამომავალს **.dwg-ის საწყისი სახელით** ასახელებს (არა დროებითი GPKG-ის)."""
    prepared = _make_source(str(tmp_path / "prepared.gpkg"), mixed=False)

    def _fake_run(cmd, **kwargs):
        # cmd = [ogr2ogr, "-f", "GPKG", tmp_out, dwg_src] — ვბაძავთ წარმატებულ
        # კონვერტაციას: მოთხოვნილ დროებით გზაზე ვდებთ უკვე მზა GPKG-ს.
        tmp_out = cmd[3]
        import shutil
        shutil.copyfile(prepared, tmp_out)

        class _R:
            returncode = 0
            stderr = ""
            stdout = ""
        return _R()

    monkeypatch.setattr(g2p_core, "find_tool", lambda exe: "ogr2ogr")
    monkeypatch.setattr(g2p_core, "_no_window", lambda: 0)
    monkeypatch.setattr(g2p_core, "_child_env", lambda tool: {})
    monkeypatch.setattr(subprocess, "run", _fake_run)

    dwg = tmp_path / "Real Plan.dwg"
    dwg.write_bytes(b"")
    r = convert_file(str(dwg), str(tmp_path / "out"), "gpkg")
    assert r["error"] is None
    assert r["reason"] is None
    assert os.path.basename(r["out_path"]) == "Real_Plan.gpkg"    # წყაროს (dwg) სახელი
    back = gpd.read_file(r["out_path"], layer="entities")
    assert len(back) == 2
