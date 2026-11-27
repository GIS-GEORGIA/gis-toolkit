# -*- coding: utf-8 -*-
"""pgdb_transfer_core — ინტეგრაციული ტესტები რეალურ .mdb ფაილებზე (Windows + Access ODBC დრაივერი).

ტესტი ბაზას აკოპირებს **ცარიელი სქემა-შაბლონიდან** დროებით საქაღალდეში და ავსებს სინთეტიკური
მონაცემებით (``pgdb_fixtures``). ნამდვილ ბაზებს არ ეხება. დრაივერის გარეშე გარემოში (Linux/CI) — skip.
"""

import hashlib
import os
import sys

import pytest

from tools import pgdb_transfer_core as c
import pgdb_fixtures as fx
from pgdb_fixtures import d

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not c.driver_available(),
                                reason="needs Windows + Microsoft Access ODBC driver")

KINDS = c.KINDS


def mapping():
    return {k: (k, k) for k in KINDS}


def run(src, dst, year=2026, backup=False, cancel=None, kinds=None):
    m = mapping() if kinds is None else {k: (k, k) for k in kinds}
    plan = c.analyze(src, dst, m, year, cancel=cancel)
    return c.execute(plan, backup=backup, cancel=cancel)


@pytest.fixture
def dbs(tmp_path):
    return fx.make_db(tmp_path, "src.mdb"), fx.make_db(tmp_path, "dst.mdb")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- ბაზასთან კავშირი / ინსპექცია ----
def test_connect_and_inspect_template(tmp_path):
    p = fx.make_db(tmp_path, "a.mdb")
    info = c.inspect_db(p)
    assert sorted(info.layers) == ["line", "point", "polygon"]
    assert {l.kind for l in info.layers.values()} == set(KINDS)
    assert all(not l.has_z and not l.has_m and l.count == 0 for l in info.layers.values())
    pl = info.layers["point"]
    assert pl.grid and pl.origin_x is not None and "WGS_1984_UTM_Zone_38N" in pl.srtext
    assert c.find_field(pl.field_names(), "tariri") == "TariRI"
    assert c.find_field(info.layers["line"].field_names(), "tariri") == "TariRi"      # რეგისტრი ფენებს შორის განსხვავებულია


def test_layers_are_matched_by_geometry_type_not_by_name(tmp_path):
    a, b = fx.make_db(tmp_path, "a.mdb"), fx.make_db(tmp_path, "b.mdb")
    m, amb = c.match_layers(c.inspect_db(a), c.inspect_db(b))
    assert m == {"point": ("point", "point"), "line": ("line", "line"), "polygon": ("polygon", "polygon")}
    assert amb == {}


def test_missing_file_and_non_database_give_clear_errors(tmp_path):
    with pytest.raises(c.TransferError) as e:
        c.connect(str(tmp_path / "nope.mdb"), "ro")
    assert e.value.code in ("not_found", "db_error")
    junk = tmp_path / "junk.mdb"
    junk.write_bytes(b"this is not an access database" * 100)
    with pytest.raises(c.TransferError) as e2:
        c.connect(str(junk), "ro")
    assert e2.value.code in ("bad_format", "db_error", "not_found")


def test_non_personal_geodatabase_is_rejected(tmp_path):
    # შაბლონი, რომელშიც GDB_GeomColumns წაშლილია — „არ არის PGDB“
    p = fx.make_db(tmp_path, "x.mdb")
    cn = c.connect(p, "excl")
    cn.cursor().execute("DROP TABLE GDB_GeomColumns")
    cn.commit()
    cn.close()
    with pytest.raises(c.TransferError) as e:
        c.inspect_db(p)
    assert e.value.code == "not_pgdb"


# ---- წლის ფილტრი ----
@pytest.mark.parametrize("kind", KINDS)
def test_year_2026_filter_includes_whole_year_and_excludes_neighbours(dbs, kind):
    src, dst = dbs
    fx.seed(src, kind, [
        {"no": "A", "date": d(2025, 12, 31, 23, 59, 59)},      # გარეთ
        {"no": "B", "date": d(2026, 1, 1, 0, 0, 0)},           # შიგნით (პირველი წამი)
        {"no": "C", "date": d(2026, 6, 15, 12, 30)},           # შიგნით
        {"no": "D", "date": d(2026, 12, 31, 23, 59, 59)},      # შიგნით (ბოლო წამი)
        {"no": "E", "date": d(2027, 1, 1, 0, 0, 0)},           # გარეთ
    ])
    plan = c.analyze(src, dst, mapping(), 2026)
    lp = [l for l in plan.layers if l.kind == kind][0]
    assert lp.found == 3 and sorted(i["no"] for i in lp.to_insert) == ["B", "C", "D"]
    c.execute(plan, backup=False)
    assert [r[1] for r in fx.fetch_all(dst, kind)] == ["B", "C", "D"]


def test_other_year_can_be_selected(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2025, 3, 3)}, {"no": "B", "date": d(2026, 3, 3)}])
    run(src, dst, year=2025)
    assert [r[1] for r in fx.fetch_all(dst, "point")] == ["A"]


# ---- დუბლიკატის წესი ----
def test_duplicate_same_number_and_same_year_is_not_inserted(dbs):
    src, dst = dbs
    fx.seed(dst, "point", [{"no": "1_100", "date": d(2026, 2, 2)}])
    fx.seed(src, "point", [{"no": "1_100", "date": d(2026, 5, 5)}, {"no": "1_101", "date": d(2026, 5, 5)}])
    plan = run(src, dst)
    lp = plan.layers[0]
    assert (lp.found, lp.duplicates, lp.inserted) == (2, 1, 1)
    assert sorted(r[1] for r in fx.fetch_all(dst, "point")) == ["1_100", "1_101"]


def test_same_number_but_destination_has_another_year_is_inserted(dbs):
    src, dst = dbs
    fx.seed(dst, "line", [{"no": "1_200", "date": d(2025, 2, 2)}])           # სხვა წელი
    fx.seed(src, "line", [{"no": "1_200", "date": d(2026, 2, 2)}])
    plan = run(src, dst)
    lp = [l for l in plan.layers if l.kind == "line"][0]
    assert (lp.duplicates, lp.inserted, lp.same_no_other_year) == (0, 1, 1)
    assert len(fx.fetch_all(dst, "line")) == 2


def test_destination_without_the_number_gets_the_record(dbs):
    src, dst = dbs
    fx.seed(src, "polygon", [{"no": "9_9", "date": d(2026, 1, 1)}])
    assert run(src, dst).layers[2].inserted == 1


def test_check_is_per_layer_not_across_layers(dbs):
    src, dst = dbs
    fx.seed(dst, "polygon", [{"no": "X1", "date": d(2026, 1, 1)}])              # იგივე ნომერი, მაგრამ სხვა ფენაში
    fx.seed(src, "point", [{"no": "X1", "date": d(2026, 1, 1)}])
    plan = run(src, dst)
    assert [l for l in plan.layers if l.kind == "point"][0].inserted == 1


def test_destination_duplicate_in_2026_among_many_years(dbs):
    src, dst = dbs
    fx.seed(dst, "point", [{"no": "N", "date": d(2024, 1, 1)}, {"no": "N", "date": d(2025, 1, 1)},
                           {"no": "N", "date": d(2026, 8, 8)}])
    fx.seed(src, "point", [{"no": "N", "date": d(2026, 1, 1)}])
    assert run(src, dst).layers[0].duplicates == 1
    assert len(fx.fetch_all(dst, "point")) == 3


def test_source_internal_duplicates_are_kept_and_reported_as_ambiguous(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "R", "date": d(2026, 1, 1)}, {"no": "R", "date": d(2026, 2, 2)},
                           {"no": "S", "date": d(2026, 3, 3)}])
    plan = run(src, dst)
    lp = plan.layers[0]
    assert lp.inserted == 3                                   # ნომრის დამთხვევით არ ვშლით
    assert lp.src_internal_dup_nos == ["R"]                   # მაგრამ ორაზროვნება ანგარიშშია
    # მეორე გაშვება: ყველა უკვე არსებობს
    again = run(src, dst)
    assert again.layers[0].duplicates == 3 and again.layers[0].inserted == 0


def test_rerun_is_idempotent(dbs):
    src, dst = dbs
    for k in KINDS:
        fx.seed(src, k, [{"no": k + "1", "date": d(2026, 4, 4)}, {"no": k + "2", "date": d(2026, 4, 5)}])
    first = run(src, dst)
    assert first.totals()["inserted"] == 6
    before = fx.counts(dst)
    second = run(src, dst)
    assert second.totals()["inserted"] == 0 and second.totals()["duplicates"] == 6
    assert fx.counts(dst) == before


# ---- ფენების გადატანა: გეომეტრია და ატრიბუტები ----
@pytest.mark.parametrize("kind", KINDS)
def test_geometry_is_copied_byte_for_byte(dbs, kind):
    src, dst = dbs
    blob = fx.geom(kind, 512345.678901234, 4701234.56789, multi=True)
    fx.seed(src, kind, [{"no": "G", "date": d(2026, 7, 7), "blob": blob}])
    run(src, dst)
    (_oid, no, shp), = fx.fetch_all(dst, kind)
    assert no == "G" and bytes(shp) == blob and c.decode_shape(shp) == c.decode_shape(blob)


def test_polygon_holes_and_multipart_lines_survive(dbs):
    src, dst = dbs
    fx.seed(src, "polygon", [{"no": "P", "date": d(2026, 1, 1), "blob": fx.geom("polygon", multi=True)}])
    fx.seed(src, "line", [{"no": "L", "date": d(2026, 1, 1), "blob": fx.geom("line", multi=True)}])
    run(src, dst)
    assert len(c.decode_shape(fx.fetch_all(dst, "polygon")[0][2])[1]) == 2           # გარე რგოლი + ხვრელი
    assert len(c.decode_shape(fx.fetch_all(dst, "line")[0][2])[1]) == 2              # ორნაწილიანი ხაზი


def test_all_attributes_are_preserved_including_georgian_and_nulls(dbs):
    src, dst = dbs
    attrs = {"Id": 77, "ganmcxadeb": "გაზსადენი — შპს „ტესტი“ №5", "teq_piroba": "ტექ. პირობა", "x": 436157.1270000001, "y": 4652169.0041}
    fx.seed(src, "point", [{"no": "ა-17/ბ", "date": d(2026, 9, 9, 14, 5, 6), "attrs": attrs}])
    run(src, dst)
    cols = "werilis_no, TariRI, Id, ganmcxadeb, teq_piroba, x, y"
    a, b = fx.fetch_all(src, "point", cols)[0], fx.fetch_all(dst, "point", cols)[0]
    assert a == b and b[3] == attrs["ganmcxadeb"] and b[1] == d(2026, 9, 9, 14, 5, 6)


def test_null_values_stay_null(dbs):
    src, dst = dbs
    fx.seed(src, "polygon", [{"no": "N", "date": d(2026, 1, 1), "attrs": {"STATUS": None, "SHAPE_Area": None, "SHAPE_Length": 5.5}}])
    run(src, dst)
    cols = "STATUS, SHAPE_Area, SHAPE_Length, sakadastro"
    assert fx.fetch_all(dst, "polygon", cols) == [(None, None, 5.5, "-")]


def test_line_and_polygon_numeric_attributes_preserved(dbs):
    src, dst = dbs
    fx.seed(src, "line", [{"no": "L", "date": d(2026, 1, 1), "attrs": {"Id": 3, "ganmcxadeb": "x", "teqnikuri": "t",
                                                                        "SHAPE_Length": 123.456789, "STATUS": 4}}])
    fx.seed(src, "polygon", [{"no": "P", "date": d(2026, 1, 1), "attrs": {"STATUS": 2, "sakadastro": "01.02.03.004",
                                                                          "SHAPE_Length": 10.5, "SHAPE_Area": 99.25}}])
    run(src, dst)
    for k, cols in (("line", "Id, ganmcxadeb, teqnikuri, SHAPE_Length, STATUS"),
                    ("polygon", "STATUS, sakadastro, SHAPE_Length, SHAPE_Area")):
        assert fx.fetch_all(src, k, cols) == fx.fetch_all(dst, k, cols)


def test_existing_destination_rows_are_never_changed(dbs):
    src, dst = dbs
    fx.seed(dst, "point", [{"no": "OLD1", "date": d(2026, 1, 1), "attrs": {"ganmcxadeb": "ძველი"}},
                           {"no": "OLD2", "date": d(2025, 1, 1)}])
    snapshot = fx.fetch_all(dst, "point", "OBJECTID, werilis_no, TariRI, ganmcxadeb, SHAPE")
    fx.seed(src, "point", [{"no": "NEW", "date": d(2026, 2, 2)}])
    run(src, dst)
    after = fx.fetch_all(dst, "point", "OBJECTID, werilis_no, TariRI, ganmcxadeb, SHAPE")
    assert after[:2] == snapshot and len(after) == 3 and after[2][1] == "NEW"


def test_source_database_file_is_not_modified(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2026, 1, 1)}])
    h = sha(src)
    run(src, dst)
    assert sha(src) == h


# ---- სივრცითი ინდექსი და ექსტენტი ----
def test_spatial_index_and_extent_are_maintained(dbs):
    src, dst = dbs
    fx.seed(dst, "polygon", [{"no": "old", "date": d(2026, 1, 1), "blob": fx.geom("polygon", 100.0, 200.0)}])
    fx.seed(src, "polygon", [{"no": "n1", "date": d(2026, 1, 1), "blob": fx.geom("polygon", 900000.0, 5000000.0)},
                             {"no": "n2", "date": d(2026, 1, 2), "blob": fx.geom("polygon", 400000.0, 4500000.0, multi=True)}])
    run(src, dst)
    info = c.inspect_db(dst)
    g = info.layers["polygon"]
    cn = c.connect(dst, "ro")
    cur = cn.cursor()
    idx = {r[0]: tuple(r[1:]) for r in cur.execute("SELECT IndexedObjectId, MinGX, MinGY, MaxGX, MaxGY FROM polygon_SHAPE_Index")}
    rows = list(cur.execute("SELECT OBJECTID, SHAPE FROM polygon"))
    cn.close()
    assert len(rows) == 3 and set(idx) == {r[0] for r in rows}                    # ყველას აქვს ინდექსი, ობოლი არ არის
    union = None
    for oid, shp in rows:
        bb = c.shape_bbox(shp)
        assert idx[oid] == c.index_cells(bb, g.origin_x, g.origin_y, g.grid)
        union = bb if union is None else (min(union[0], bb[0]), min(union[1], bb[1]), max(union[2], bb[2]), max(union[3], bb[3]))
    ext = g.extent
    assert ext[0] <= union[0] and ext[1] <= union[1] and ext[2] >= union[2] and ext[3] >= union[3]
    assert ext[2] >= 900100.0 and ext[3] >= 5000100.0                              # ექსტენტი გაფართოვდა


# ---- არასწორი/ცარიელი თარიღები და სხვა ჩანაწერები, რომლებიც ვერ გადავა ----
def test_missing_and_invalid_dates_are_reported_not_silently_skipped(dbs):
    src, dst = dbs
    fx.seed(src, "polygon", [{"no": "OK", "date": d(2026, 1, 1)}, {"no": "NULLDATE", "date": None},
                             {"no": "OLDDATE", "date": d(1850, 1, 1)}, {"no": "FUTURE", "date": d(2300, 1, 1)}])
    plan = c.analyze(src, dst, mapping(), 2026)
    lp = [l for l in plan.layers if l.kind == "polygon"][0]
    assert [n for _o, n in lp.missing_dates] == ["NULLDATE"]
    assert sorted(n for _o, n, _d in lp.invalid_dates) == ["FUTURE", "OLDDATE"]
    assert plan.totals()["bad_dates"] == 3
    c.execute(plan, backup=False)
    assert [r[1] for r in fx.fetch_all(dst, "polygon")] == ["OK"]


def test_record_without_number_is_reported_and_not_inserted(dbs):
    src, dst = dbs
    fx.relax(src, "point", "werilis_no")                         # რომ წყაროში ცარიელი ნომერი ჩაიწეროს
    fx.seed(src, "point", [{"no": None, "date": d(2026, 1, 1)}, {"no": "  ", "date": d(2026, 1, 1)},
                           {"no": "OK", "date": d(2026, 1, 1)}])
    lp = run(src, dst).layers[0]
    assert (lp.found, lp.no_number, lp.inserted) == (3, 2, 1)
    assert [e[2] for e in lp.errors] == ["no_number", "no_number"]


def test_destination_constraint_violation_skips_that_record_only(dbs):
    src, dst = dbs
    fx.relax(src, "polygon", "sakadastro")                       # წყარო უშვებს ცარიელს, მიმღები (Required) — არა
    fx.seed(src, "polygon", [{"no": "BADROW", "date": d(2026, 1, 1), "attrs": {"sakadastro": None}},
                             {"no": "GOODROW", "date": d(2026, 1, 1)}])
    plan = run(src, dst)
    lp = plan.layers[2]
    assert lp.inserted == 1 and len(lp.errors) == 1 and lp.errors[0][1] == "BADROW" and lp.errors[0][2].startswith("insert:")
    assert [r[1] for r in fx.fetch_all(dst, "polygon")] == ["GOODROW"]
    assert fx.counts(dst)["polygon"] == (1, 1)                  # ინდექსი ჩანაწერებთან თანხვედრაშია


def test_unsupported_geometry_record_is_an_error_but_others_transfer(dbs):
    src, dst = dbs
    z_line = c.encode_shape(3, [[(0.0, 0.0), (1.0, 1.0)]])
    z_line = bytes([13]) + z_line[1:]                           # PolyLineZ — არ ვუჭერთ მხარს
    fx.seed(src, "line", [{"no": "BAD", "date": d(2026, 1, 1), "blob": z_line},
                          {"no": "GOOD", "date": d(2026, 1, 1)}])
    lp = [l for l in run(src, dst).layers if l.kind == "line"][0]
    assert lp.inserted == 1 and len(lp.errors) == 1 and "geometry" in lp.errors[0][2]
    assert [r[1] for r in fx.fetch_all(dst, "line")] == ["GOOD"]


# ---- სქემის განსხვავებები ----
def test_source_field_missing_in_destination_is_reported_and_rest_transfers(dbs):
    src, dst = dbs
    cn = c.connect(dst, "excl")
    cn.cursor().execute("ALTER TABLE [point] DROP COLUMN [teq_piroba]")
    cn.commit()
    cn.close()
    fx.seed(src, "point", [{"no": "A", "date": d(2026, 1, 1), "attrs": {"teq_piroba": "t", "ganmcxadeb": "g"}}])
    lp = run(src, dst).layers[0]
    assert lp.unmatched_fields == ["teq_piroba"] and lp.inserted == 1
    assert fx.fetch_all(dst, "point", "ganmcxadeb")[0] == ("g",)


def test_incompatible_key_field_type_blocks_the_layer(dbs):
    src, dst = dbs
    cn = c.connect(dst, "excl")
    cn.cursor().execute("ALTER TABLE [point] ALTER COLUMN [werilis_no] LONG")
    cn.commit()
    cn.close()
    fx.seed(src, "point", [{"no": "A", "date": d(2026, 1, 1)}])
    fx.seed(src, "line", [{"no": "B", "date": d(2026, 1, 1)}])
    plan = run(src, dst)
    by = {l.kind: l for l in plan.layers}
    assert by["point"].blocked and by["point"].blocked[0] == "schema" and by["point"].inserted == 0
    assert by["line"].inserted == 1                                    # დანარჩენ ფენებს ხელს არ უშლის
    assert fx.counts(dst)["point"] == (0, 0)


def test_too_long_text_is_an_error_not_a_silent_truncation(dbs):
    src, dst = dbs
    cn = c.connect(dst, "excl")
    cn.cursor().execute("ALTER TABLE [point] ALTER COLUMN [ganmcxadeb] TEXT(5)")
    cn.commit()
    cn.close()
    fx.seed(src, "point", [{"no": "LONG", "date": d(2026, 1, 1), "attrs": {"ganmcxadeb": "x" * 40}},
                           {"no": "SHORT", "date": d(2026, 1, 1), "attrs": {"ganmcxadeb": "ok"}}])
    lp = run(src, dst).layers[0]
    assert lp.inserted == 1 and "too long" in lp.errors[0][2]
    assert fx.fetch_all(dst, "point", "werilis_no, ganmcxadeb") == [("SHORT", "ok")]


# ---- კოორდინატთა სისტემა ----
UTM37 = ('PROJCS["WGS_1984_UTM_Zone_37N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
         '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
         'PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",39.0],'
         'PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]')


def _set_srtext(path, srid, text):
    cn = c.connect(path, "excl")
    cn.cursor().execute("UPDATE GDB_SpatialRefs SET SRTEXT=? WHERE SRID=?", (text, srid))
    cn.commit()
    cn.close()


def test_different_crs_is_reprojected_when_well_defined(dbs):
    pytest.importorskip("pyproj")
    src, dst = dbs
    _set_srtext(dst, 2, UTM37)
    blob = fx.geom("polygon", 500000.0, 4650000.0, multi=True)
    fx.seed(src, "polygon", [{"no": "RP", "date": d(2026, 1, 1), "blob": blob}])
    fx.seed(src, "point", [{"no": "RPT", "date": d(2026, 1, 1), "blob": fx.geom("point", 500000.0, 4650000.0)}])
    plan = run(src, dst)
    assert all(l.reprojected for l in plan.layers)
    expected = c.reproject_shape(blob, c.make_transformer(c.inspect_db(src).layers["polygon"].srtext, UTM37))
    got = bytes(fx.fetch_all(dst, "polygon")[0][2])
    assert got == expected and got != blob
    assert abs(c.shape_bbox(got)[0] - 500000.0) > 1000                  # აშკარად გადაადგილდა (სხვა ცენტრალური მერიდიანი)
    # ინდექსი ახალი კოორდინატებით დაითვალა
    g = c.inspect_db(dst).layers["polygon"]
    cn = c.connect(dst, "ro")
    idx = tuple(cn.cursor().execute("SELECT MinGX, MinGY, MaxGX, MaxGY FROM polygon_SHAPE_Index").fetchone())
    cn.close()
    assert idx == c.index_cells(c.shape_bbox(got), g.origin_x, g.origin_y, g.grid)


def test_unknown_crs_blocks_that_layer_instead_of_guessing(dbs):
    src, dst = dbs
    _set_srtext(dst, 2, "this is not a coordinate system")
    fx.seed(src, "point", [{"no": "A", "date": d(2026, 1, 1)}])
    lp = c.analyze(src, dst, mapping(), 2026).layers[0]
    assert lp.blocked and lp.blocked[0] == "crs_unknown"


def test_identical_crs_means_no_reprojection(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2026, 1, 1)}])
    assert not c.analyze(src, dst, mapping(), 2026).layers[0].reprojected


# ---- ჩაწერის უსაფრთხოება: ლოქი, ROLLBACK, გაუქმება, ბექაპი ----
def test_locked_destination_gives_clear_error_and_changes_nothing(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2026, 1, 1)}])
    plan = c.analyze(src, dst, mapping(), 2026)
    holder = c.connect(dst, "excl")
    try:
        with pytest.raises(c.TransferError) as e:
            c.execute(plan, backup=False)
        assert e.value.code == "locked"
    finally:
        holder.close()
    assert fx.counts(dst)["point"] == (0, 0)
    c.execute(plan, backup=False)                                       # ლოქის მოხსნის შემდეგ მუშაობს
    assert fx.counts(dst)["point"] == (1, 1)


def test_locked_destination_is_detected_while_reading_too(dbs):
    src, dst = dbs
    holder = c.connect(dst, "excl")
    try:
        with pytest.raises(c.TransferError) as e:
            c.analyze(src, dst, mapping(), 2026)
        assert e.value.code == "locked"
    finally:
        holder.close()


def test_failure_in_the_middle_rolls_back_everything(dbs, monkeypatch):
    src, dst = dbs
    for k in KINDS:
        fx.seed(src, k, [{"no": k + str(i), "date": d(2026, 1, 1 + i)} for i in range(3)])
    before_counts, before_ext = fx.counts(dst), {k: c.inspect_db(dst).layers[k].extent for k in KINDS}
    plan = c.analyze(src, dst, mapping(), 2026)
    real, calls = c.index_cells, {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 5:                                              # ფენებს შორის შუაში ვარდება
            raise RuntimeError("simulated crash")
        return real(*a, **kw)
    monkeypatch.setattr(c, "index_cells", flaky)
    with pytest.raises(c.TransferError):
        c.execute(plan, backup=False)
    monkeypatch.setattr(c, "index_cells", real)
    assert fx.counts(dst) == before_counts                               # არც წერტილები, არც ხაზები, არც პოლიგონები
    assert {k: c.inspect_db(dst).layers[k].extent for k in KINDS} == before_ext
    assert all(l.inserted == 0 for l in plan.layers)


def test_cancel_rolls_back(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "p%d" % i, "date": d(2026, 1, 1)} for i in range(5)])
    plan = c.analyze(src, dst, mapping(), 2026)
    n = {"i": 0}

    def cancel():
        n["i"] += 1
        return n["i"] > 3
    with pytest.raises(c.TransferError) as e:
        c.execute(plan, backup=False, cancel=cancel)
    assert e.value.code == "cancelled" and fx.counts(dst)["point"] == (0, 0)


def test_backup_is_created_and_matches_the_destination_before_transfer(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2026, 1, 1)}])
    h = sha(dst)
    plan = run(src, dst, backup=True)
    assert plan.backup_path and os.path.isfile(plan.backup_path) and "_backup_" in plan.backup_path
    assert sha(plan.backup_path) == h and sha(dst) != h
    assert fx.counts(plan.backup_path)["point"] == (0, 0)


def test_no_backup_when_nothing_to_insert(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2025, 1, 1)}])           # სხვა წელი — არაფერია გადასატანი
    plan = run(src, dst, backup=True)
    assert plan.backup_path is None and plan.totals()["inserted"] == 0


def test_analyze_does_not_write_anything(dbs):
    src, dst = dbs
    for k in KINDS:
        fx.seed(src, k, [{"no": k, "date": d(2026, 1, 1)}])
    h = sha(dst)
    plan = c.analyze(src, dst, mapping(), 2026)
    assert plan.totals()["to_insert"] == 3 and sha(dst) == h


def test_totals_and_log_file(dbs, tmp_path):
    src, dst = dbs
    fx.seed(dst, "point", [{"no": "D", "date": d(2026, 1, 1)}])
    fx.seed(src, "point", [{"no": "D", "date": d(2026, 1, 1)}, {"no": "E", "date": d(2026, 1, 1)},
                           {"no": "NULLD", "date": None}])
    log = c.TransferLog(str(tmp_path / "x.log"))
    plan = c.analyze(src, dst, mapping(), 2026, log=log)
    c.execute(plan, log=log, backup=False)
    log.close()
    t = plan.totals()
    assert (t["found"], t["duplicates"], t["inserted"], t["errors"], t["bad_dates"]) == (2, 1, 1, 0, 1)
    text = (tmp_path / "x.log").read_text(encoding="utf-8")
    assert "POINT" in text and "MISSING date" in text and "inserted 1 (verified" in text


# ---- ჩანაწერები თარიღის გარეშე → ახალი ცალკე ბაზა ----
def _undated(src, tmp_path, **kw):
    out = str(tmp_path / "new_no_date.mdb")
    plan = c.export_undated(src, mapping(), out, **kw)
    return out, plan


def test_records_without_date_go_to_a_new_separate_database(dbs, tmp_path):
    src, dst = dbs
    b1, b2 = fx.geom("polygon", 600000.0, 4700000.0), fx.geom("polygon", 610000.0, 4710000.0, multi=True)
    fx.seed(src, "polygon", [{"no": "D1", "date": d(2026, 3, 3)},
                             {"no": "N1", "date": None, "blob": b1, "attrs": {"ganmcxadeb": "უთარიღო", "STATUS": 3}},
                             {"no": "N2", "date": None, "blob": b2},
                             {"no": "OLD", "date": d(1850, 1, 1)}])                 # არასწორი თარიღი ≠ ცარიელი — აქ არ გადადის
    h_src, h_dst = sha(src), sha(dst)
    out, plan = _undated(src, tmp_path)
    assert plan.totals()["inserted"] == 2 and os.path.isfile(out) and out != dst
    rows = fx.fetch_all(out, "polygon", "werilis_no, SHAPE, ganmcxadeb, STATUS")
    assert [r[0] for r in rows] == ["N1", "N2"]
    assert bytes(rows[0][1]) == b1 and bytes(rows[1][1]) == b2                      # გეომეტრია ბაიტ-ბაიტ
    assert rows[0][2] == "უთარიღო" and rows[0][3] == 3
    assert fx.counts(out) == {"point": (0, 0), "line": (0, 0), "polygon": (2, 2)}   # ინდექსი ჩანაწერებთან თანხვედრაშია
    assert sha(src) == h_src and sha(dst) == h_dst                                  # წყარო და მიმღები უცვლელია
    assert fx.counts(dst)["polygon"] == (0, 0)


def test_undated_works_for_every_layer_type(dbs, tmp_path):
    src, dst = dbs
    for k in KINDS:
        fx.seed(src, k, [{"no": k + "_nd", "date": None}, {"no": k + "_ok", "date": d(2026, 1, 1)}])
    out, plan = _undated(src, tmp_path)
    assert plan.totals()["inserted"] == 3
    for k in KINDS:
        assert [r[1] for r in fx.fetch_all(out, k)] == [k + "_nd"]


def test_no_new_database_when_every_record_has_a_date(dbs, tmp_path):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2026, 1, 1)}])
    out, plan = _undated(src, tmp_path)
    assert plan is None and not os.path.exists(out)


def test_new_database_takes_the_source_crs_and_keeps_geometry_unchanged(dbs, tmp_path):
    src, dst = dbs
    _set_srtext(src, 2, UTM37)
    blob = fx.geom("polygon", 500000.0, 4650000.0)
    fx.seed(src, "polygon", [{"no": "N", "date": None, "blob": blob}])
    out, plan = _undated(src, tmp_path)
    assert not plan.layers[2].reprojected
    assert "UTM_Zone_37N" in c.inspect_db(out).layers["polygon"].srtext
    assert bytes(fx.fetch_all(out, "polygon")[0][2]) == blob


def test_existing_output_is_never_overwritten(dbs, tmp_path):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": None}])
    out = tmp_path / "taken.mdb"
    out.write_bytes(b"keep me")
    with pytest.raises(c.TransferError) as e:
        c.export_undated(src, mapping(), str(out))
    assert e.value.code == "exists" and out.read_bytes() == b"keep me"


def test_failed_undated_export_leaves_no_partial_file(dbs, tmp_path, monkeypatch):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "p%d" % i, "date": None} for i in range(4)])
    real, n = c.index_cells, {"i": 0}

    def flaky(*a, **kw):
        n["i"] += 1
        if n["i"] == 3:
            raise RuntimeError("boom")
        return real(*a, **kw)
    monkeypatch.setattr(c, "index_cells", flaky)
    out = str(tmp_path / "partial.mdb")
    with pytest.raises(c.TransferError):
        c.export_undated(src, mapping(), out)
    assert not os.path.exists(out)


# ---- ლოგები: წელი-წლობით, გადაუწერელი, დეტალური ----
def test_log_path_has_year_and_never_overwrites(tmp_path):
    dst = tmp_path / "OMIKO BAZA.mdb"
    dst.write_bytes(b"x")
    p1 = c.default_log_path(str(dst), None, year=2023, src_path="baza.mdb")
    p2 = c.default_log_path(str(dst), None, year=2026, src_path="baza.mdb")
    assert "2023" in os.path.basename(p1) and "2026" in os.path.basename(p2) and p1 != p2
    assert os.path.basename(os.path.dirname(p1)) == c.LOG_DIR_NAME
    open(p1, "w").write("old")
    p3 = c.default_log_path(str(dst), None, year=2023, src_path="baza.mdb")
    if p3 == p1:                                          # იგივე წამი — ახალი სახელი უნდა მიიღოს
        pytest.fail("existing log path reused")


def test_transferlog_appends_instead_of_overwriting(tmp_path):
    f = str(tmp_path / "a.log")
    l1 = c.TransferLog(f)
    l1("first")
    l1.close()
    l2 = c.TransferLog(f)
    l2("second")
    l2.detail("only in file")
    l2.close()
    text = open(f, encoding="utf-8").read()
    assert "first" in text and "second" in text and "only in file" in text


def test_detailed_log_records_every_decision(dbs, tmp_path):
    src, dst = dbs
    g = fx.geom("point", 500000.0, 4600000.0)
    fx.seed(dst, "point", [{"no": "D", "date": d(2026, 1, 1)}, {"no": "O", "date": d(2025, 5, 5)}])
    fx.seed(src, "point", [{"no": "D", "date": d(2026, 1, 1)}, {"no": "E", "date": d(2026, 2, 2)},
                           {"no": "O", "date": d(2026, 3, 3)}, {"no": "N", "date": None}])
    fx.seed(src, "line", [{"no": "L1", "date": d(2026, 4, 4)}])
    fx.seed(src, "polygon", [{"no": "P1", "date": d(2026, 5, 5)}])
    lf = str(tmp_path / "run.log")
    log = c.TransferLog(lf)
    plan = c.analyze(src, dst, mapping(), 2026, log=log)
    c.execute(plan, log=log, backup=False)
    c.write_final_summary(plan, log, "COMPLETED", elapsed=1.0, written=True)
    csv_path = c.write_records_csv(plan, str(tmp_path / "run_records.csv"))
    hist = c.append_history(lf, plan, "COMPLETED", written=True, elapsed=1.0)
    c.append_history(lf, plan, "COMPLETED", written=True, elapsed=1.0)
    log.close()
    text = open(lf, encoding="utf-8").read()
    # ინვენტარი წლებით, ყველა ფენა, ჩანაწერ-დონის გადაწყვეტილებები და საბოლოო ცხრილი
    assert "by year: 2025=1, 2026=1" in text                                   # მიმღები (point)
    assert "no date=1" in text                                                 # წყარო NULL თარიღი
    assert "SKIPPED (already in destination this year" in text
    assert "INSERTED as dest OBJECTID" in text
    assert "MISSING date" in text
    for k in ("POINT", "LINE", "POLYGON"):
        assert k in text
    assert "FINAL SUMMARY — year 2026 — outcome: COMPLETED" in text
    assert "destination rows 2 -> 4" in text                                   # point: 2 + E + O(2026)
    rows = open(csv_path, encoding="utf-8-sig").read().splitlines()
    assert rows[0].startswith("layer,src_OBJECTID") and any(",duplicate," in r for r in rows)
    assert sum(",inserted," in r for r in rows) == 4 and any(",missing_date," in r for r in rows)
    h = open(hist, encoding="utf-8-sig").read().splitlines()
    assert len(h) == 3 and h[0].startswith("time,year")                        # თავსართი + 2 გაშვება (დამატებით)


# ---- გადატანილი ჩანაწერების ცალკე ახალ ბაზაში ----
def test_transferred_records_copy_into_separate_database(dbs, tmp_path):
    src, dst = dbs
    fx.seed(dst, "point", [{"no": "D", "date": d(2026, 1, 1)}])
    fx.seed(src, "point", [{"no": "D", "date": d(2026, 1, 1)}, {"no": "E", "date": d(2026, 2, 2)},
                           {"no": "F", "date": d(2026, 3, 3)}])
    fx.seed(src, "polygon", [{"no": "P1", "date": d(2026, 5, 5)}])
    h_src = sha(src)
    plan = c.analyze(src, dst, mapping(), 2026)
    c.execute(plan, backup=False)
    dst_counts = fx.counts(dst)
    out = str(tmp_path / "copy.mdb")
    cp = c.export_inserted(plan, out)
    assert cp.totals()["inserted"] == 3                    # E, F, P1 — დუბლიკატი D არა
    cnt = fx.counts(out)
    assert cnt["point"] == (2, 2) and cnt["polygon"] == (1, 1) and cnt["line"] == (0, 0)
    assert fx.counts(dst) == dst_counts and sha(src) == h_src
    # ძირითადი გეგმის გადაწყვეტილებები არ შეცვლილა (new_oid მიმღების OBJECTID-ია)
    assert all(dd["decision"] == "inserted" for lp in plan.layers for dd in lp.decisions if dd["decision"] != "duplicate")
    # არაფერია გადასატანი → ფაილი არ იქმნება
    plan2 = c.analyze(src, dst, mapping(), 2026)
    c.execute(plan2, backup=False)
    out2 = str(tmp_path / "none.mdb")
    assert c.export_inserted(plan2, out2) is None and not os.path.exists(out2)


# ---- ყველა წლის გაერთიანება ერთ ბაზაში ----
def test_merge_all_years_into_one_database(tmp_path):
    a = fx.make_db(tmp_path, "y2025.mdb")
    b = fx.make_db(tmp_path, "y2026.mdb")
    fx.seed(a, "point", [{"no": "A1", "date": d(2025, 1, 1)}, {"no": "A2", "date": d(2025, 2, 2)}])
    fx.seed(a, "polygon", [{"no": "PA", "date": d(2025, 3, 3)}])
    fx.seed(b, "point", [{"no": "A1", "date": d(2026, 1, 1)}, {"no": "B1", "date": d(2026, 2, 2)},
                         {"no": "A2", "date": d(2025, 2, 2)}])           # A2/2025 — დუბლიკატი
    fx.seed(b, "line", [{"no": "LB", "date": d(2026, 4, 4)}])
    ha, hb = sha(a), sha(b)
    out = str(tmp_path / "all.mdb")
    plan = c.merge_databases([a, b], out)
    cnt = fx.counts(out)
    assert cnt["point"] == (4, 4) and cnt["line"] == (1, 1) and cnt["polygon"] == (1, 1)
    assert plan.totals()["duplicates"] == 1 and plan.totals()["inserted"] == 6
    assert sha(a) == ha and sha(b) == hb                                   # წყაროები უცვლელია
    assert fx.fetch_all(out, "point") is not None
    with pytest.raises(c.TransferError):
        c.merge_databases([a, b], out)                                     # გადაწერა არ ხდება
    empty1, empty2 = fx.make_db(tmp_path, "e1.mdb"), fx.make_db(tmp_path, "e2.mdb")
    o2 = str(tmp_path / "none.mdb")
    assert c.merge_databases([empty1, empty2], o2) is None and not os.path.exists(o2)


# ---- ერთი საერთო (ყველა წლის) ბაზა: პირველ გაშვებაზე იქმნება, შემდეგზე ემატება ----
def test_common_all_years_database_is_created_then_appended(dbs, tmp_path):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2025, 1, 1)}, {"no": "B", "date": d(2026, 2, 2)},
                           {"no": "C", "date": d(2026, 3, 3)}])
    fx.seed(src, "polygon", [{"no": "P", "date": d(2026, 4, 4)}])
    common = c.all_years_output_path(dst, str(tmp_path))
    assert common.endswith("_transferred_ALL_YEARS.mdb")
    p25 = c.analyze(src, dst, mapping(), 2025)
    c.execute(p25, backup=False)
    r1 = c.export_inserted(p25, common, append=True)                 # შექმნა
    assert r1.totals()["inserted"] == 1 and fx.counts(common)["point"] == (1, 1)
    p26 = c.analyze(src, dst, mapping(), 2026)
    c.execute(p26, backup=False)
    r2 = c.export_inserted(p26, common, append=True)                 # დამატება
    assert r2.totals()["inserted"] == 3
    cnt = fx.counts(common)
    assert cnt["point"] == (3, 3) and cnt["polygon"] == (1, 1)
    # იგივე ჩანაწერები ხელახლა (მაგ. ხელით განმეორებული ექსპორტი) — არ მეორდება
    r3 = c.export_inserted(p26, common, append=True)
    assert r3.totals()["inserted"] == 0 and r3.totals()["duplicates"] == 3
    assert fx.counts(common)["point"] == (3, 3)
    # ცალკე წლის ბაზა დამოუკიდებლად მუშაობს და არსებულს არ გადაწერს
    per_year = str(tmp_path / "py.mdb")
    assert c.export_inserted(p26, per_year).totals()["inserted"] == 3
    with pytest.raises(c.TransferError):
        c.export_inserted(p26, per_year)


def test_common_database_keeps_repeated_numbers_inside_a_year(dbs, tmp_path):
    """წყაროში ერთი ნომერი ერთ წელს რამდენჯერმეა — მიმღებში ყველა ჩაიწერა, საერთო ბაზაშიც ყველა უნდა მოხვდეს."""
    src, dst = dbs
    fx.seed(src, "point", [{"no": "R", "date": d(2025, 1, 1)}, {"no": "R", "date": d(2025, 6, 6)},
                           {"no": "R", "date": d(2025, 9, 9)}, {"no": "S", "date": d(2025, 2, 2)}])
    common = c.all_years_output_path(dst, str(tmp_path))
    plan = c.analyze(src, dst, mapping(), 2025)
    c.execute(plan, backup=False)
    assert plan.totals()["inserted"] == 4
    r = c.export_inserted(plan, common, append=True)
    assert r.totals()["inserted"] == 4 and fx.counts(common)["point"] == (4, 4)
    # ხელახალი ექსპორტი არაფერს ამატებს
    assert c.export_inserted(plan, common, append=True).totals()["inserted"] == 0


def test_merge_keeps_repeated_numbers_inside_one_source(tmp_path):
    a = fx.make_db(tmp_path, "m25.mdb")
    b = fx.make_db(tmp_path, "m26.mdb")
    fx.seed(a, "point", [{"no": "R", "date": d(2025, 1, 1)}, {"no": "R", "date": d(2025, 2, 2)}])
    fx.seed(b, "point", [{"no": "R", "date": d(2025, 3, 3)}, {"no": "R", "date": d(2026, 1, 1)}])
    out = str(tmp_path / "m_all.mdb")
    plan = c.merge_databases([a, b], out)
    # a: 2 ჩანაწერი (შიგა გამეორება არ იკარგება); b: 2025-ის R უკვე a-დან არის → გამოტოვება; 2026 — ახალი
    assert fx.counts(out)["point"] == (3, 3) and plan.totals()["duplicates"] == 1


# ---- რამდენიმე წელი ერთად ----
def test_parse_years():
    assert c.parse_years("2026") == [2026]
    assert c.parse_years("2024-2026") == [2024, 2025, 2026]
    assert c.parse_years("2023, 2026;2024") == [2023, 2024, 2026]
    assert c.parse_years("ყველა") == "all" and c.parse_years("ALL") == "all"
    for bad in ("", "abc", "2026-2024", "20", "1800"):
        with pytest.raises(ValueError):
            c.parse_years(bad)


def test_source_years_and_sequential_years_equal_one_by_one(dbs):
    src, dst = dbs
    fx.seed(src, "point", [{"no": "A", "date": d(2024, 1, 1)}, {"no": "B", "date": d(2025, 1, 1)},
                           {"no": "B", "date": d(2025, 2, 2)}, {"no": "C", "date": d(2026, 1, 1)},
                           {"no": "N", "date": None}])
    fx.seed(src, "line", [{"no": "L", "date": d(2025, 5, 5)}])
    ys = c.source_years(src, mapping())
    assert ys == [2024, 2025, 2026]
    total = 0
    for y in ys:                                   # ისე, როგორც UI-ს რიგი აკეთებს: წელი-წლობით
        pl = c.analyze(src, dst, mapping(), y)
        c.execute(pl, backup=False)
        total += pl.totals()["inserted"]
    assert total == 5 and fx.counts(dst)["point"][0] == 4 and fx.counts(dst)["line"][0] == 1


# ---- a failed / cancelled export never leaves a half-made database behind ----
def _no_db_files(folder, stem):
    return [f for f in os.listdir(folder) if f.lower().startswith(stem.lower() + ".")]


def test_failed_crs_setup_of_a_new_database_leaves_no_file(dbs, tmp_path, monkeypatch):
    """The write connection must be closed even when an UPDATE fails - otherwise the cleanup cannot delete
    the open (locked) .mdb on Windows and a half-made database stays."""
    src, _dst = dbs
    fx.seed(src, "point", [{"no": "N1", "date": None}])
    real = c.connect

    class BrokenCursor:
        def __init__(self, cur):
            self._cur = cur

        def execute(self, sql, *a):
            if sql.startswith("UPDATE GDB_SpatialRefs"):
                raise RuntimeError("simulated driver error")
            return self._cur.execute(sql, *a)

    class Conn:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self):
            return BrokenCursor(self._conn.cursor())

        def __getattr__(self, name):
            return getattr(self._conn, name)

    def connect(path, mode="ro"):
        conn = real(path, mode)
        return Conn(conn) if mode == "excl" and path.endswith("new_no_date.mdb") else conn
    monkeypatch.setattr(c, "connect", connect)
    with pytest.raises(RuntimeError, match="simulated"):
        _undated(src, tmp_path)
    assert _no_db_files(str(tmp_path), "new_no_date") == []


def test_cancel_during_new_database_export_leaves_no_file(dbs, tmp_path):
    src, _dst = dbs
    fx.seed(src, "point", [{"no": "N{}".format(i), "date": None} for i in range(5)])
    calls = []

    def cancel():                                   # cancel inside the insert loop (one transaction)
        calls.append(1)
        return len(calls) > 3
    with pytest.raises(c.TransferError) as e:
        _undated(src, tmp_path, cancel=cancel)
    assert e.value.code == "cancelled"
    assert _no_db_files(str(tmp_path), "new_no_date") == []
    out, plan = _undated(src, tmp_path)               # a new run after the cancel works normally
    assert plan is not None and fx.counts(out)["point"][0] == 5
