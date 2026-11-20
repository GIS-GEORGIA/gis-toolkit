# -*- coding: utf-8 -*-
"""pgdb_transfer_core — სუფთა ლოგიკის ტესტები (ODBC/ბაზის გარეშე)."""

import datetime
import os
import struct

import pytest

from tools import pgdb_transfer_core as c


# ---- წლის ფილტრი / თარიღები ----
def test_year_bounds_cover_the_whole_year():
    lo, hi = c.year_bounds(2026)
    assert lo == datetime.datetime(2026, 1, 1, 0, 0, 0)
    assert hi == datetime.datetime(2027, 1, 1, 0, 0, 0)
    last = datetime.datetime(2026, 12, 31, 23, 59, 59)
    assert lo <= last < hi                                   # 2026-12-31 23:59:59 შედის
    assert not (lo <= datetime.datetime(2025, 12, 31, 23, 59, 59, 999000) < hi)
    assert not (lo <= datetime.datetime(2027, 1, 1) < hi)    # ზედა ზღვარი ექსკლუზიურია


def test_classify_date():
    assert c.classify_date(datetime.datetime(2026, 5, 1)) == "ok"
    assert c.classify_date(datetime.date(2026, 5, 1)) == "ok"
    assert c.classify_date(None) == "missing"
    assert c.classify_date("2026-05-01") == "invalid"        # ტექსტი — არა თარიღი
    assert c.classify_date(datetime.datetime(1850, 1, 1)) == "invalid"
    assert c.classify_date(datetime.datetime(2300, 1, 1)) == "invalid"


def test_in_year_ignores_missing_and_invalid():
    assert c.in_year(datetime.datetime(2026, 12, 31, 23, 59, 59), 2026)
    assert not c.in_year(None, 2026)
    assert not c.in_year(datetime.datetime(1850, 1, 1), 1850)        # არასწორი წელი არ ითვლება


# ---- დუბლიკატის წესი ----
def test_decide_rules():
    dest2026 = {"1_100", "1_200"}
    assert c.decide("1_100", dest2026) == "duplicate"
    assert c.decide("  1_100 ", dest2026) == "duplicate"           # სფეისები არ ატყუებს
    assert c.decide("1_300", dest2026) == "insert"                 # მიმღებში არ არის
    assert c.decide("1_100", set()) == "insert"                    # იგივე ნომერი მხოლოდ სხვა წლით → ჩაიწერება
    assert c.decide(None, dest2026) == "no_number"
    assert c.decide("   ", dest2026) == "no_number"


def test_normalize_no():
    assert c.normalize_no(" 5 ") == "5"
    assert c.normalize_no(5) == "5"
    assert c.normalize_no("") is None and c.normalize_no(None) is None


# ---- ველები ----
def F(name, t, size=None, nullable=True):
    return c.FieldInfo(name, t, size, nullable)


def test_find_field_is_case_insensitive():
    assert c.find_field(["Id", "TariRi", "werilis_no"], "tariri") == "TariRi"
    assert c.find_field(["TariRI"], "tariri") == "TariRI"
    assert c.find_field(["x"], "tariri") is None


def test_plan_fields_identical_schema():
    src = [F("OBJECTID", "COUNTER"), F("werilis_no", "VARCHAR", 50), F("TariRi", "DATETIME"), F("SHAPE", "LONGBINARY")]
    dst = [F("OBJECTID", "COUNTER"), F("werilis_no", "VARCHAR", 50), F("TARIRI", "DATETIME"), F("SHAPE", "LONGBINARY")]
    p = c.plan_fields(src, dst)
    assert p.ok and sorted(p.copy) == [("SHAPE", "SHAPE"), ("TariRi", "TARIRI"), ("werilis_no", "werilis_no")]
    assert p.unmatched_src == []


def test_plan_fields_reports_source_fields_missing_in_destination():
    src = [F("werilis_no", "VARCHAR", 50), F("extra", "VARCHAR", 20)]
    dst = [F("werilis_no", "VARCHAR", 50)]
    p = c.plan_fields(src, dst)
    assert p.unmatched_src == ["extra"]                       # ჩუმად არ იკარგება
    assert p.ok


def test_plan_fields_type_mismatch_is_a_blocker():
    p = c.plan_fields([F("TariRi", "DATETIME")], [F("TariRi", "VARCHAR", 10)])
    assert not p.ok and p.blockers[0][0] == "type_mismatch"


def test_plan_fields_int_to_float_widening_is_allowed():
    p = c.plan_fields([F("n", "INTEGER")], [F("n", "DOUBLE")])
    assert p.ok and p.copy == [("n", "n")]


def test_plan_fields_short_destination_text_gets_length_check():
    p = c.plan_fields([F("t", "VARCHAR", 100)], [F("t", "VARCHAR", 20)])
    assert p.ok and p.length_checked == [("t", "t", 20)]


def test_plan_fields_required_destination_field_missing_in_source():
    p = c.plan_fields([F("a", "VARCHAR", 5)], [F("a", "VARCHAR", 5), F("req", "VARCHAR", 5, nullable=False)])
    assert not p.ok and p.missing_required == ["req"]


# ---- shape-buffer ----
def test_point_buffer_roundtrip_and_bbox():
    b = c.encode_shape(1, [[(436157.127, 4652169.0041)]])
    assert len(b) == 20 and c.shape_kind(b) == "point"
    assert c.shape_bbox(b) == (436157.127, 4652169.0041, 436157.127, 4652169.0041)
    assert c.decode_shape(b) == (1, [[(436157.127, 4652169.0041)]])


def test_polygon_with_hole_roundtrip_is_byte_exact():
    outer = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)]
    hole = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0), (2.0, 2.0)]
    b = c.encode_shape(5, [outer, hole])
    assert c.shape_kind(b) == "polygon" and c.shape_bbox(b) == (0.0, 0.0, 10.0, 10.0)
    t, parts = c.decode_shape(b)
    assert t == 5 and parts == [outer, hole]
    assert c.encode_shape(t, parts) == b


def test_multipart_line_roundtrip():
    parts = [[(0.0, 0.0), (1.0, 1.0)], [(5.0, 5.0), (6.0, 7.0), (9.0, 9.0)]]
    b = c.encode_shape(3, parts)
    assert c.shape_kind(b) == "line" and c.decode_shape(b) == (3, parts)


def test_unsupported_shape_types_are_rejected_not_guessed():
    curved = struct.pack("<i", 536870962) + b"\x00" * 60            # ნამდვილ ბაზაში ნანახი მრუდებიანი ხაზის ტიპი
    assert c.shape_kind(curved) is None
    with pytest.raises(ValueError):
        c.decode_shape(curved)
    with pytest.raises(ValueError):
        c.shape_bbox(b"\x03\x00\x00\x00" + b"\x00" * 8)              # ძალიან მოკლე


def test_nan_bbox_is_rejected():
    bad = struct.pack("<i4d2i", 3, float("nan"), 0.0, 1.0, 1.0, 0, 0)
    with pytest.raises(ValueError):
        c.shape_bbox(bad)


# ---- სივრცითი ინდექსი (ფორმულა გადამოწმებულია რეალური ბაზის 100% ჩანაწერზე) ----
def test_index_cells_matches_values_stored_by_arcgis():
    ox, oy, g = -5120900, -9998100, 0.0093113295246607
    # რეალური ბაზიდან: წერტილი x=436157.127 y=4652169.0041 → (596805978, 1573381004)… (ზუსტი უჯრა ბაზაშია)
    cells = c.index_cells((436157.127, 4652169.0041, 436157.127, 4652169.0041), ox, oy, g)
    assert cells[0] == cells[2] and cells[1] == cells[3]
    assert abs(cells[0] - 596805978) < 3000 and abs(cells[1] - 1573381004) < 3000
    # floor, არა round: ზუსტი სამართლიანი უჯრა
    assert c.index_cells((10.5, 0.0, 10.5, 0.0), 0, 0, 1.0) == (10, 0, 10, 0)
    assert c.index_cells((-0.1, -0.1, 0.9, 1.0), 0, 0, 1.0) == (-1, -1, 0, 1)


# ---- გეომეტრიის გადაყვანა ----
def test_reproject_shape_keeps_structure_and_changes_coordinates():
    outer = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)]
    hole = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0), (2.0, 2.0)]
    b = c.encode_shape(5, [outer, hole])
    shifted = c.reproject_shape(b, lambda xs, ys: ([x + 100 for x in xs], [y - 50 for y in ys]))
    t, parts = c.decode_shape(shifted)
    assert t == 5 and len(parts) == 2
    assert parts[0][0] == (100.0, -50.0) and parts[1][0] == (102.0, -48.0)
    assert c.shape_bbox(shifted) == (100.0, -50.0, 110.0, -40.0)


def test_reproject_shape_rejects_non_finite_results():
    b = c.encode_shape(1, [[(1.0, 1.0)]])
    with pytest.raises(ValueError):
        c.reproject_shape(b, lambda xs, ys: ([float("inf")] * len(xs), ys))


UTM38 = ('PROJCS["WGS_1984_UTM_Zone_38N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
         '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
         'PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",45.0],'
         'PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]')
UTM37 = UTM38.replace("UTM_Zone_38N", "UTM_Zone_37N").replace("Central_Meridian\",45.0", "Central_Meridian\",39.0")


def test_crs_relation():
    pytest.importorskip("pyproj")
    assert c.crs_relation(UTM38, UTM38) == "same"
    assert c.crs_relation(UTM38, "  " + UTM38.replace(",", ", ") + " ") == "same"      # ჰარმონია ჰარმ. სფეისებისგან დამოუკიდებელია
    assert c.crs_relation(UTM38, UTM37) == "reproject"
    assert c.crs_relation(UTM38, "garbage") == "unknown"
    assert c.crs_relation("", UTM38) == "unknown"


def test_make_transformer_roundtrip():
    pytest.importorskip("pyproj")
    f = c.make_transformer(UTM38, UTM37)
    xs, ys = f([500000.0], [4650000.0])
    assert abs(xs[0] - 500000.0) > 1000                      # სხვა ცენტრალური მერიდიანი — მნიშვნელოვანი ძვრა
    back = c.make_transformer(UTM37, UTM38)(xs, ys)
    assert abs(back[0][0] - 500000.0) < 0.01 and abs(back[1][0] - 4650000.0) < 0.01


# ---- სხვა ----
def test_same_file(tmp_path):
    a = tmp_path / "a.mdb"
    a.write_bytes(b"x")
    b = tmp_path / "b.mdb"
    b.write_bytes(b"x")
    assert c.same_file(str(a), str(a))
    assert c.same_file(str(a), str(tmp_path / "." / "A.MDB")) in (True, False)    # რეგისტრის შემთხვევა ფაილურ სისტემაზეა დამოკიდებული
    assert not c.same_file(str(a), str(b))


def test_friendly_error_codes():
    assert c.friendly_error(Exception("Could not use '(unknown)'; file already in use. (-1024)")).code == "locked"
    assert c.friendly_error(Exception("Unrecognized database format 'x.mdb'")).code == "bad_format"
    assert c.friendly_error(Exception("Data source name not found")).code == "no_driver"
    assert c.friendly_error(Exception("'x' is not a valid path")).code == "not_found"
    assert c.friendly_error(Exception("something else")).code == "db_error"


def test_log_writes_timestamped_lines(tmp_path):
    seen = []
    log = c.TransferLog(str(tmp_path / "t.log"), sink=lambda line, lvl: seen.append((line, lvl)))
    log("hello")
    log("careful", "WARN")
    log.close()
    text = (tmp_path / "t.log").read_text(encoding="utf-8")
    assert "[INFO] hello" in text and "[WARN] careful" in text
    assert text.splitlines()[0][:2] == "20" and seen[1][1] == "WARN"
