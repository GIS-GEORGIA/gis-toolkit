# -*- coding: utf-8 -*-
"""zone_intersect_core — საზღვრების კვეთის წერტილების ტესტები (shapely)."""

import pytest

pytest.importorskip("shapely")   # shapely-ის გარეშე გარემოში — skip, არა error

from shapely.geometry import Polygon, LineString, MultiPoint, GeometryCollection
from tools.zone_intersect_core import (
    _iter_points, _as_curve, crossing_points, collect_points, clip_areas,
    crossing_angle, shallow_crossings,
)


def test_as_curve_polygon_to_boundary_line_unchanged():
    poly = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    assert _as_curve(poly).geom_type in ("LineString", "LinearRing")
    ln = LineString([(0, 0), (1, 1)])
    assert _as_curve(ln) is ln                      # ხაზი უცვლელი


def test_crossing_points_line_x_line():
    # გაზსადენი (ჰორიზონტ.) × კომუნიკაცია (ვერტიკ.) — იკვეთება (5,0)
    gas = LineString([(0, 0), (10, 0)])
    comm = LineString([(5, -5), (5, 5)])
    pts = crossing_points(gas, comm)
    assert [(round(x), round(y)) for x, y in pts] == [(5, 0)]


def test_collect_points_line_x_line_multiple_ordered():
    gas = LineString([(0, 0), (10, 0)])
    # ორი ვერტიკალური კომუნიკაცია → ორი კვეთა (3,0) და (7,0)
    c1 = LineString([(3, -1), (3, 1)])
    c2 = LineString([(7, -1), (7, 1)])
    pts = collect_points([gas], [c1, c2])
    xs = [round(x) for x, _ in pts]
    assert sorted(xs) == [3, 7]
    assert len(pts) == 2


def test_iter_points_point_and_multipoint():
    out = []
    _iter_points(MultiPoint([(0, 0), (1, 1)]), out)
    assert out == [(0.0, 0.0), (1.0, 1.0)]


def test_iter_points_linestring_takes_endpoints():
    out = []
    _iter_points(LineString([(0, 0), (5, 0)]), out)   # კოლინეარული გადაფარვა
    assert out == [(0.0, 0.0), (5.0, 0.0)]


def test_iter_points_ignores_empty():
    out = []
    _iter_points(GeometryCollection(), out)
    assert out == []


def test_crossing_points_square_over_square():
    # ნაკვეთი: [0..10]x[0..10]; ზონა: [5..15]x[-5..5] — საზღვრები იკვეთება (5,5) და (10,... ?)
    parcel = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    zone = Polygon([(5, -5), (15, -5), (15, 5), (5, 5)])
    pts = crossing_points(parcel, zone)
    # კვეთის წერტილები: (5,5) [ნაკვეთის ზედა-მარცხ. ზონის კუთხე] და (10,5), (5,0)?
    # საკმარისია დავრწმუნდეთ, რომ (10,5) და (5,0) კვეთებია ნაპოვნი
    s = {(round(x), round(y)) for x, y in pts}
    assert (10, 5) in s
    assert (5, 0) in s


def test_collect_points_dedup_and_order():
    parcel = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    # ორი ზონა, რომლებიც ერთსა და იმავე წერტილს (10,5) აჩენს — დუბლი უნდა მოიშალოს
    zone1 = Polygon([(5, -5), (15, -5), (15, 5), (5, 5)])
    zone2 = Polygon([(8, 4), (15, 4), (15, 6), (8, 6)])
    pts = collect_points([parcel], [zone1, zone2])
    keys = [(round(x), round(y)) for x, y in pts]
    assert len(keys) == len(set(keys))            # უნიკალურია
    assert (10, 5) in keys                          # საერთო კვეთა ერთხელ


def test_collect_points_ordered_along_corridor_top_to_bottom():
    # ვერტიკალური დერეფანი, რომელიც სცდება ნაკვეთს ზემოთ/ქვემოთ — კვეთს
    # ზედა და ქვედა კიდეებს. ნუმერაცია ზემოდან ქვევით უნდა წავიდეს.
    parcel = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    corridor = Polygon([(40, -10), (60, -10), (60, 110), (40, 110)])
    pts = collect_points([parcel], [corridor])
    ys = [round(y) for _, y in pts]
    assert ys == [100, 100, 0, 0]                 # ზედა წყვილი, მერე ქვედა
    # დიაგონალურ დერეფანზეც — პირველი წერტილი ზედა ბოლოსთანაა
    dband = Polygon([(-12.9, 127.1), (127.1, -12.9),
                     (112.9, -27.1), (-27.1, 112.9)])
    pts2 = collect_points([parcel], [dband])
    assert pts2[0][1] > pts2[-1][1]               # პირველი — ზემოთ, ბოლო — ქვემოთ


def test_collect_points_no_intersection_empty():
    parcel = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zone = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])
    assert collect_points([parcel], [zone]) == []


def test_collect_points_handles_empty_inputs():
    assert collect_points([], []) == []
    parcel = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    assert collect_points([parcel], []) == []


# ---- clip_areas ----

def test_clip_areas_corner_overlap_sums_to_parcel_area():
    parcel = Polygon([(0, 0), (20, 0), (20, 10), (0, 10)])          # 200 მ2
    zone = Polygon([(-5, 5), (10, 5), (10, 20), (-5, 20)])          # კუთხე ემთხვევა
    res = clip_areas([parcel], [zone])
    assert res["parcel_area"] == pytest.approx(200.0)
    assert res["cut_area"] == pytest.approx(50.0)
    assert res["remainder_area"] == pytest.approx(150.0)
    assert res["cut_area"] + res["remainder_area"] == pytest.approx(res["parcel_area"])
    assert res["cut"].geom_type in ("Polygon", "MultiPolygon")
    assert res["remainder"].geom_type in ("Polygon", "MultiPolygon")


def test_clip_areas_no_overlap_cut_is_none_remainder_is_full_parcel():
    parcel = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zone = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])
    res = clip_areas([parcel], [zone])
    assert res["cut"].is_empty
    assert res["cut_area"] == 0.0
    assert res["remainder_area"] == pytest.approx(1.0)
    assert res["remainder"].equals(parcel)


def test_clip_areas_handles_empty_inputs():
    res = clip_areas([], [])
    assert res == {"parcel": None, "cut": None, "remainder": None,
                   "parcel_area": 0.0, "cut_area": 0.0, "remainder_area": 0.0}
    parcel = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    res = clip_areas([parcel], [])
    assert res["cut"] is None
    assert res["parcel_area"] == pytest.approx(1.0)
    assert res["remainder_area"] == pytest.approx(1.0)


# ---- crossing_angle / shallow_crossings ----

def test_crossing_angle_perpendicular_is_90():
    a = LineString([(0, -5), (0, 5)])
    b = LineString([(-5, 0), (5, 0)])
    assert crossing_angle((0, 0), [a], [b]) == pytest.approx(90.0)


def test_crossing_angle_is_acute_regardless_of_direction():
    a = LineString([(0, 0), (10, 0)])
    b = LineString([(10, 0.8816), (0, -0.8816)])      # ~10° დახრილი (tan 10° = 0.1763), საპირისპირო მიმართულება
    assert crossing_angle((5, 0), [a], [b]) == pytest.approx(10.0, abs=0.05)


def test_shallow_crossings_flags_only_small_angles():
    a = LineString([(0, 0), (100, 0)])
    steep = LineString([(20, -10), (20, 10)])          # 90°
    shallow = LineString([(0, -1.4), (100, 12.6)])     # ~8° → წერტილი (10, 0)
    pts = [(20.0, 0.0), (10.0, 0.0)]
    flagged = shallow_crossings([a], [steep, shallow], pts, threshold_deg=15)
    assert [n for n, _ in flagged] == [2]
    assert flagged[0][1] == pytest.approx(8.0, abs=0.2)


def test_shallow_crossings_uses_polygon_boundaries():
    poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    zone = Polygon([(5, -5), (15, -5), (15, 5), (5, 5)])
    pts = collect_points([poly], [zone])
    assert shallow_crossings([poly], [zone], pts) == []   # კვადრატების გადაკვეთა — 90°
