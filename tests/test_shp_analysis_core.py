# -*- coding: utf-8 -*-
"""shp_analysis_core — სკანირება, გაზომვა, რანჟირება (რეალური დროებითი shapefile-ებით)."""

import os

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyproj")
from shapely.geometry import box, LineString, Point

from tools.shp_analysis_core import (
    scan_shapefiles, analyze_layer, rank_layers, summarize, kind_of,
    fmt_area, fmt_length, OK, EMPTY, NO_CRS, POLYGON, LINE, POINT,
)


def _write(tmp_path, rel, geoms, crs="EPSG:32638"):
    folder = tmp_path / os.path.dirname(rel)
    folder.mkdir(parents=True, exist_ok=True)
    path = str(tmp_path / rel)
    gpd.GeoDataFrame({"id": list(range(len(geoms)))}, geometry=geoms, crs=crs).to_file(path)
    return path


def test_kind_of():
    assert kind_of("Polygon") == POLYGON and kind_of("Polygon Z") == POLYGON
    assert kind_of("LineString") == LINE and kind_of("MultiLineString Z") == LINE
    assert kind_of("Point") == POINT and kind_of("MultiPoint") == POINT


def test_scan_is_recursive_and_case_insensitive(tmp_path):
    _write(tmp_path, "a/x.shp", [box(0, 0, 1, 1)])
    _write(tmp_path, "b/c/y.shp", [box(0, 0, 1, 1)])
    (tmp_path / "b" / "z.SHP").write_bytes(b"")
    (tmp_path / "b" / "note.txt").write_text("x")
    names = [os.path.basename(p).lower() for p in scan_shapefiles(str(tmp_path))]
    assert names == ["x.shp", "y.shp", "z.shp"]


def test_analyze_polygon_area_perimeter_and_max(tmp_path):
    p = _write(tmp_path, "d/poly.shp", [box(500000, 4600000, 500010, 4600020),     # 200 მ², პერიმეტრი 60
                                        box(500100, 4600000, 500200, 4600100)])   # 10000 მ², პერიმეტრი 400
    r = analyze_layer(p)
    assert r["status"] == OK and r["kind"] == POLYGON and r["count"] == 2
    assert r["area_total"] == pytest.approx(10200.0)
    assert r["area_max"] == pytest.approx(10000.0)
    assert r["perimeter_total"] == pytest.approx(460.0)
    assert r["folder"] == os.path.dirname(p) and r["converted"] is False


def test_analyze_line_length(tmp_path):
    p = _write(tmp_path, "d/l.shp", [LineString([(500000, 4600000), (500030, 4600040)]),   # 50
                                      LineString([(500000, 4600000), (500100, 4600000)])]) # 100
    r = analyze_layer(p)
    assert r["kind"] == LINE and r["length_total"] == pytest.approx(150.0)
    assert r["length_max"] == pytest.approx(100.0)


def test_analyze_z_line_uses_planar_length(tmp_path):
    p = _write(tmp_path, "d/lz.shp", [LineString([(500000, 4600000, 5), (500100, 4600000, 900)])])
    assert analyze_layer(p)["length_total"] == pytest.approx(100.0)


def test_analyze_points_only_count_even_without_crs(tmp_path):
    p = _write(tmp_path, "d/pts.shp", [Point(1, 2), Point(3, 4), Point(5, 6)], crs=None)
    r = analyze_layer(p)
    assert r["status"] == OK and r["kind"] == POINT and r["count"] == 3


def test_analyze_polygon_without_crs_is_flagged(tmp_path):
    p = _write(tmp_path, "d/nocrs.shp", [box(0, 0, 10, 10)], crs=None)
    assert analyze_layer(p)["status"] == NO_CRS


def test_analyze_empty_layer(tmp_path):
    p = _write(tmp_path, "d/empty.shp", [])
    assert analyze_layer(p)["status"] == EMPTY


def test_analyze_geographic_layer_is_measured_in_metres(tmp_path):
    # ~0.001° × 0.001° თბილისთან ≈ 83 მ × 111 მ ≈ 9200 მ²
    p = _write(tmp_path, "d/geo.shp", [box(44.80, 41.70, 44.801, 41.701)], crs="EPSG:4326")
    r = analyze_layer(p)
    assert r["converted"] is True and "32638" in r["crs_label"]
    assert 8000 < r["area_total"] < 10500


def test_broken_file_does_not_raise(tmp_path):
    bad = tmp_path / "bad.shp"
    bad.write_bytes(b"not a shapefile")
    r = analyze_layer(str(bad))
    assert r["status"] not in (OK,) and r["name"] == "bad.shp"


def test_rankings_order_and_folder_disambiguation(tmp_path):
    # ერთი და იგივე სახელი სხვადასხვა საქაღალდეში
    small = _write(tmp_path, "f1/nakveTi.shp", [box(500000, 4600000, 500010, 4600010)])    # 100
    big = _write(tmp_path, "f2/nakveTi.shp", [box(500000, 4600000, 500100, 4600100)])      # 10000
    mid = _write(tmp_path, "f3/nakveTi.shp", [box(500000, 4600000, 500050, 4600050)])      # 2500
    rows = [analyze_layer(p) for p in (small, big, mid)]
    r = rank_layers(rows, top_n=2)
    assert [x["path"] for x in r["poly_area"]] == [big, mid]              # top_n=2
    assert r["poly_area"][0]["folder"] != r["poly_area"][1]["folder"]
    assert r["line_length"] == [] and r["point_count"] == []


def test_rankings_skip_non_ok_layers(tmp_path):
    ok = _write(tmp_path, "a/p.shp", [box(500000, 4600000, 500010, 4600010)])
    nocrs = _write(tmp_path, "b/p.shp", [box(0, 0, 1000, 1000)], crs=None)
    empty = _write(tmp_path, "c/p.shp", [])
    rows = [analyze_layer(p) for p in (ok, nocrs, empty)]
    assert [x["path"] for x in rank_layers(rows)["poly_area"]] == [ok]
    s = summarize(rows)
    assert [x["path"] for x in s[NO_CRS]] == [nocrs]
    assert [x["path"] for x in s[EMPTY]] == [empty]


def test_rankings_tie_is_stable_by_path(tmp_path):
    a = _write(tmp_path, "a/p.shp", [box(500000, 4600000, 500010, 4600010)])
    b = _write(tmp_path, "b/p.shp", [box(500000, 4600000, 500010, 4600010)])
    rows = [analyze_layer(b), analyze_layer(a)]
    assert [x["path"] for x in rank_layers(rows)["poly_area"]] == [a, b]


def test_formatters():
    assert fmt_area(123.456) == "123.46 მ²"
    assert fmt_area(12345.678) == "12 345.68 მ² (1.2346 ჰა)"
    assert fmt_length(950) == "950.00 მ"
    assert fmt_length(12345.6, "en") == "12 345.60 m (12.346 km)"
