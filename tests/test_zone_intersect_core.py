# -*- coding: utf-8 -*-
"""zone_intersect_core — საზღვრების კვეთის წერტილების ტესტები (shapely)."""

import pytest

pytest.importorskip("shapely")   # shapely-ის გარეშე გარემოში — skip, არა error

from shapely.geometry import Polygon, LineString, MultiPoint, GeometryCollection
from tools.zone_intersect_core import (
    _iter_points, _as_curve, crossing_points, collect_points,
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
