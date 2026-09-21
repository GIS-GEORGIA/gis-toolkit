# -*- coding: utf-8 -*-
"""zone_intersect_core — საზღვრების კვეთის წერტილების ტესტები (shapely)."""

from shapely.geometry import Polygon, LineString, MultiPoint, GeometryCollection
from tools.zone_intersect_core import _iter_points, crossing_points, collect_points


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


def test_collect_points_no_intersection_empty():
    parcel = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zone = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])
    assert collect_points([parcel], [zone]) == []


def test_collect_points_handles_empty_inputs():
    assert collect_points([], []) == []
    parcel = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    assert collect_points([parcel], []) == []
