# -*- coding: utf-8 -*-
"""line_buffer_core — ბუფერის ტიპები, ინდექსაცია, CRS არჩევა, ბუფერის გეომეტრია."""

import math

import pytest

from tools.line_buffer_core import (
    BUFFER_TYPES, next_index, output_path, metric_crs, build_buffer,
)


def test_buffer_types_match_spec():
    assert BUFFER_TYPES["1"] == [(4, "gas_protection_zone_1"),
                                 (25, "gas_protection_zone_2"),
                                 (200, "gas_safety_zone_3"),
                                 (500, "gas_consultation_zone_4")]
    assert BUFFER_TYPES["2"] == [(4, "gas_protection_zone_1"),
                                 (10, "gas_protection_zone_2"),
                                 (500, "gas_consultation_zone_4")]
    assert BUFFER_TYPES["3"] == [(4, "gas_protection_zone_1"),
                                 (25, "gas_protection_zone_2"),
                                 (100, "gas_safety_zone_3")]


def test_output_path_starts_at_1(tmp_path):
    p = output_path(str(tmp_path), "gas_protection_zone_1")
    assert p.endswith("gas_protection_zone_1_1.shp")


def test_next_index_goes_past_highest_existing(tmp_path):
    for n in (1, 3):
        (tmp_path / "gas_safety_zone_3_{}.shp".format(n)).write_bytes(b"")
    (tmp_path / "gas_safety_zone_3_2.dbf").write_bytes(b"")   # სხვა გაფართოება — არ ითვლება
    assert next_index(str(tmp_path), "gas_safety_zone_3") == 4


def test_next_index_does_not_confuse_similar_names(tmp_path):
    (tmp_path / "gas_protection_zone_1_7.shp").write_bytes(b"")
    assert next_index(str(tmp_path), "gas_protection_zone_2") == 1


def test_next_index_missing_folder_is_1(tmp_path):
    assert next_index(str(tmp_path / "nope"), "x") == 1


def test_metric_crs_keeps_projected_metre_crs():
    pytest.importorskip("pyproj")
    crs, changed = metric_crs("EPSG:32638", (44.0, 42.0))
    assert crs.to_epsg() == 32638 and changed is False


def test_metric_crs_geographic_goes_to_utm_by_longitude():
    pytest.importorskip("pyproj")
    crs, changed = metric_crs("EPSG:4326", (44.8, 41.7))      # თბილისი → ზონა 38
    assert crs.to_epsg() == 32638 and changed is True
    crs, _ = metric_crs("EPSG:4326", (41.6, 41.6))             # ბათუმი (36–42°E) → ზონა 37
    assert crs.to_epsg() == 32637


def test_metric_crs_without_crs_raises():
    pytest.importorskip("pyproj")
    with pytest.raises(ValueError):
        metric_crs(None, (44.0, 42.0))


def test_build_buffer_straight_line_area():
    shapely_geom = pytest.importorskip("shapely.geometry")
    line = shapely_geom.LineString([(0, 0), (1000, 0)])
    d = 25.0
    area = build_buffer([line], d).area
    expected = 2 * d * 1000 + math.pi * d * d
    assert area == pytest.approx(expected, rel=0.002)       # წრის აპროქსიმაციის ცდომილება


def test_build_buffer_dissolves_overlapping_lines():
    shapely_geom = pytest.importorskip("shapely.geometry")
    a = shapely_geom.LineString([(0, 0), (100, 0)])
    b = shapely_geom.LineString([(0, 1), (100, 1)])
    merged = build_buffer([a, b], 10)
    assert merged.geom_type == "Polygon"                      # ერთიანდება, არა MultiPolygon
    assert merged.area < build_buffer([a], 10).area * 2


def test_build_buffer_empty_returns_none():
    assert build_buffer([], 10) is None
    assert build_buffer([None], 10) is None
