# -*- coding: utf-8 -*-
"""dwg_convert_core — ტესტები. სუფთა დამხმარეები GDAL-ის გარეშე; კონვერტაციის
ტესტები (`pytest.importorskip("geopandas")`) — ლოკალურად, სადაც GIS პაკეტებია.

წყაროდ, DXF-write დრაივერზე დამოკიდებულების ასაცილებლად, ვწერთ პატარა GPKG-ს
(``convert_file`` ნებისმიერ GDAL-ვექტორს კითხულობს — შეზღუდვა მხოლოდ UI-ის
ფაილის ფილტრშია, არა ლოგიკაში).
"""

import os

import pytest

from tools.dwg_convert_core import sanitize, iter_source_files, FORMATS, SOURCE_EXT


# ---- სუფთა დამხმარეები (GDAL-ის გარეშე) ------------------------------------
def test_sanitize_replaces_unsafe_chars():
    assert sanitize("Layer 1/ A") == "Layer_1_A"
    assert sanitize("normal_name") == "normal_name"
    assert sanitize("") == "layer"
    assert sanitize(None) == "layer"


def test_formats_and_source_ext():
    assert set(FORMATS) == {"shp", "gpkg", "gdb"}
    assert FORMATS["shp"] == ("ESRI Shapefile", ".shp")
    assert FORMATS["gpkg"] == ("GPKG", ".gpkg")
    assert FORMATS["gdb"] == ("OpenFileGDB", ".gdb")
    assert SOURCE_EXT == (".dxf", ".dwg")


def test_iter_source_files_finds_dxf_dwg(tmp_path):
    (tmp_path / "a.dxf").write_bytes(b"")
    (tmp_path / "b.DWG").write_bytes(b"")
    (tmp_path / "c.shp").write_bytes(b"")
    got = [os.path.basename(p) for p in iter_source_files(str(tmp_path))]
    assert got == ["a.dxf", "b.DWG"]


# ---- კონვერტაცია (geopandas/pyogrio საჭირო) --------------------------------
gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point, LineString, Polygon  # noqa: E402
from tools.dwg_convert_core import convert_file, convert_batch  # noqa: E402


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
