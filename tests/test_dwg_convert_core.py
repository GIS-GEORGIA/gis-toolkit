# -*- coding: utf-8 -*-
"""dwg_convert_core — სუფთა დამხმარეების ტესტები (GDAL-ის გარეშე).

geopandas-ზე დამოკიდებული კონვერტაციის ტესტები ცალკე ფაილშია
(``test_dwg_convert_core_gpd.py``) — ``pytest.importorskip`` მოდულის დონეზე
**მთელ ფაილს** გამოტოვებს (არა ცალკეულ ტესტს), ამიტომ ეს (GDAL-ისგან
დამოუკიდებელი) ტესტები აქ დარჩა, რომ CI-ში ყოველთვის გაეშვას.
"""

import os
import subprocess

import pytest

import tools.gdb2postgis_core as g2p_core
from tools.dwg_convert_core import (
    sanitize, iter_source_files, FORMATS, SOURCE_EXT,
    convert_file, DwgReadError, _dwg_to_gpkg_via_system_gdal,
)


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


# ---- DWG → system-GDAL bridge (subprocess/tempfile ონლი, geopandas არ სჭირდება) ----
def test_dwg_no_system_gdal_returns_clear_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(g2p_core, "find_tool", lambda exe: None)
    dwg = tmp_path / "x.dwg"
    dwg.write_bytes(b"")
    r = convert_file(str(dwg), str(tmp_path / "out"), "gpkg")
    assert r["error"] is not None
    assert r["reason"] == "dwg_no_tool"
    assert r["layers"] == []


def test_dwg_old_libopencad_version_classified(tmp_path, monkeypatch):
    monkeypatch.setattr(g2p_core, "find_tool", lambda exe: "ogr2ogr")
    monkeypatch.setattr(g2p_core, "_no_window", lambda: 0)
    monkeypatch.setattr(g2p_core, "_child_env", lambda tool: {})

    class _FakeResult:
        returncode = 1
        stderr = ("ERROR 6: libopencad 0.3.4 does not support this version "
                  "of CAD file.\nSupported formats are:\nDWG R2000 [ACAD1015]")
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())
    dwg = tmp_path / "x.dwg"
    dwg.write_bytes(b"")
    r = convert_file(str(dwg), str(tmp_path / "out"), "gpkg")
    assert r["reason"] == "dwg_old_driver"
    assert "libopencad" in r["error"]


def test_dwg_other_ogr2ogr_error_has_no_special_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(g2p_core, "find_tool", lambda exe: "ogr2ogr")
    monkeypatch.setattr(g2p_core, "_no_window", lambda: 0)
    monkeypatch.setattr(g2p_core, "_child_env", lambda tool: {})

    class _FakeResult:
        returncode = 1
        stderr = "ERROR 1: something else went wrong"
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())
    with pytest.raises(DwgReadError) as exc:
        _dwg_to_gpkg_via_system_gdal(str(tmp_path / "x.dwg"), log=lambda m: None)
    assert exc.value.reason is None
