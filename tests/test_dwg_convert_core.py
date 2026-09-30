# -*- coding: utf-8 -*-
"""dwg_convert_core — სუფთა დამხმარეების ტესტები (GDAL-ის გარეშე).

geopandas-ზე დამოკიდებული კონვერტაციის ტესტები ცალკე ფაილშია
(``test_dwg_convert_core_gpd.py``) — ``pytest.importorskip`` მოდულის დონეზე
**მთელ ფაილს** გამოტოვებს (არა ცალკეულ ტესტს), ამიტომ ეს (GDAL-ისგან
დამოუკიდებელი) ტესტები აქ დარჩა, რომ CI-ში ყოველთვის გაეშვას.
"""

import os

from tools.dwg_convert_core import sanitize, iter_source_files, FORMATS, SOURCE_EXT


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
