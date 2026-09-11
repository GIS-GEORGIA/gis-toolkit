# -*- coding: utf-8 -*-
"""geom_collect_core — სუფთა დამხმარეების ტესტები (GDAL-ის გარეშე)."""

import os

from tools.geom_collect_core import (
    classify_geom_type, iter_geometry_files, GEOM_EXT,
    normalize_exts, VECTOR_FORMATS, DIR_DATASETS,
)


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


# ---- classify_geom_type ----
def test_classify_points():
    assert classify_geom_type("Point") == "point"
    assert classify_geom_type("MultiPoint") == "point"


def test_classify_lines():
    assert classify_geom_type("LineString") == "line"
    assert classify_geom_type("MultiLineString") == "line"
    assert classify_geom_type("LinearRing") == "line"


def test_classify_polygons():
    assert classify_geom_type("Polygon") == "polygon"
    assert classify_geom_type("MultiPolygon") == "polygon"


def test_classify_unknown():
    assert classify_geom_type("GeometryCollection") is None
    assert classify_geom_type("Whatever") is None


# ---- iter_geometry_files ----
def test_iter_finds_shp_dxf_dwg_recursive(tmp_path):
    _touch(str(tmp_path / "a.shp"))
    _touch(str(tmp_path / "b.DXF"))            # რეგისტრი უგულებელყოფილია
    _touch(str(tmp_path / "sub" / "c.dwg"))
    _touch(str(tmp_path / "sub" / "note.txt"))  # არა-გეომეტრიული
    _touch(str(tmp_path / "~$tmp.shp"))         # დროებითი — გამოტოვება

    got = [os.path.basename(p) for p in
           iter_geometry_files(str(tmp_path), recursive=True)]
    assert got == ["a.shp", "b.DXF", "c.dwg"]


def test_iter_non_recursive(tmp_path):
    _touch(str(tmp_path / "a.shp"))
    _touch(str(tmp_path / "sub" / "c.dwg"))
    got = [os.path.basename(p) for p in
           iter_geometry_files(str(tmp_path), recursive=False)]
    assert got == ["a.shp"]


def test_geom_ext_constant():
    assert GEOM_EXT == (".shp", ".dxf", ".dwg")


def test_iter_custom_exts_selection(tmp_path):
    _touch(str(tmp_path / "a.shp"))
    _touch(str(tmp_path / "b.gpkg"))
    _touch(str(tmp_path / "c.geojson"))
    _touch(str(tmp_path / "d.dxf"))
    # მხოლოდ gpkg + geojson მოვნიშნოთ
    got = [os.path.basename(p) for p in
           iter_geometry_files(str(tmp_path), (".gpkg", ".geojson"))]
    assert got == ["b.gpkg", "c.geojson"]


def test_iter_directory_dataset_gdb(tmp_path):
    # .gdb — საქაღალდე-დატასეტი: უნდა დაიჭიროს და მასში არ ჩაიხედოს
    gdb = tmp_path / "data.gdb"
    os.makedirs(str(gdb))
    _touch(str(gdb / "a00000001.gdbtable"))       # შიდა ფაილი — არ ჩამოთვლ.
    _touch(str(tmp_path / "plain.shp"))
    got = [os.path.basename(p) for p in
           iter_geometry_files(str(tmp_path), (".gdb", ".shp"))]
    assert got == ["data.gdb", "plain.shp"]


def test_normalize_exts():
    assert normalize_exts("geojson, tab") == (".geojson", ".tab")
    assert normalize_exts(".GPKG .Shp") == (".gpkg", ".shp")
    assert normalize_exts("shp, shp, .shp") == (".shp",)     # დუბლი იშლება
    assert normalize_exts("") == ()


def test_dir_datasets_and_catalog():
    assert DIR_DATASETS == (".gdb",)
    labels = [lbl for lbl, _e in VECTOR_FORMATS]
    assert any("Shapefile" in x for x in labels)
    assert any("GeoPackage" in x for x in labels)
    assert any("Geodatabase" in x for x in labels)
