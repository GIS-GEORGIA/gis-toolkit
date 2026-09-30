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

import tools.dwg_convert_core as dwg_core
import tools.gdb2postgis_core as g2p_core
from tools.dwg_convert_core import (
    sanitize, iter_source_files, FORMATS, SOURCE_EXT,
    convert_file, DwgReadError, _dwg_to_gpkg_via_system_gdal, _dwg_to_readable,
    _ascii_safe_copy,
)


def _disable_bundled_libredwg(monkeypatch):
    """ტესტებში სისტემურ-GDAL ტოტს იზოლირებულად რომ ამოწმებდეს — ბანდლში
    ატანილი LibreDWG-ის პოვნას ვთიშავთ (მისი ცალკე ტესტები ქვემოთაა)."""
    monkeypatch.setattr(dwg_core, "_bundled_dwg2dxf_path", lambda: None)


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


# ---- _ascii_safe_copy — dwg2dxf.exe-ის Windows argv-encoding შემოვლა -------
def test_ascii_safe_copy_passthrough_for_ascii_path(tmp_path):
    p = tmp_path / "plain.dwg"
    p.write_bytes(b"x")
    out, is_tmp = _ascii_safe_copy(str(p))
    assert out == str(p)
    assert is_tmp is False


def test_ascii_safe_copy_makes_temp_copy_for_non_ascii_path(tmp_path):
    p = tmp_path / ("გეგმა.dwg")   # "გეგმა.dwg"
    p.write_bytes(b"dwg-bytes")
    out, is_tmp = _ascii_safe_copy(str(p))
    assert is_tmp is True
    assert out != str(p)
    out.encode("ascii")                       # არ ისვრის — გარანტირებული ASCII
    assert out.lower().endswith(".dwg")        # გაფართოება შენარჩუნებულია
    assert open(out, "rb").read() == b"dwg-bytes"
    os.remove(out)


def test_iter_source_files_finds_dxf_dwg(tmp_path):
    (tmp_path / "a.dxf").write_bytes(b"")
    (tmp_path / "b.DWG").write_bytes(b"")
    (tmp_path / "c.shp").write_bytes(b"")
    got = [os.path.basename(p) for p in iter_source_files(str(tmp_path))]
    assert got == ["a.dxf", "b.DWG"]


# ---- DWG → fallback system-GDAL bridge (bundled LibreDWG disabled, ცალკე
# იზოლირებულად; subprocess/tempfile ონლი, geopandas არ სჭირდება) -----------
def test_dwg_no_system_gdal_returns_clear_reason(tmp_path, monkeypatch):
    _disable_bundled_libredwg(monkeypatch)
    monkeypatch.setattr(g2p_core, "find_tool", lambda exe: None)
    dwg = tmp_path / "x.dwg"
    dwg.write_bytes(b"")
    r = convert_file(str(dwg), str(tmp_path / "out"), "gpkg")
    assert r["error"] is not None
    assert r["reason"] == "dwg_no_tool"
    assert r["layers"] == []


def test_dwg_old_libopencad_version_classified(tmp_path, monkeypatch):
    _disable_bundled_libredwg(monkeypatch)
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


# ---- _dwg_to_readable — ორსაფეხურიანი დისპეჩერის პრიორიტეტი (მოკებული) -----
def test_dwg_readable_prefers_bundled_libredwg_over_system_gdal(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dwg_core, "_bundled_dwg2dxf_path", lambda: "dwg2dxf.exe")
    monkeypatch.setattr(dwg_core, "_dwg_to_dxf_via_bundled_libredwg",
                        lambda path, exe, log: calls.append("bundled") or "ok.dxf")
    monkeypatch.setattr(dwg_core, "_dwg_to_gpkg_via_system_gdal",
                        lambda path, log: calls.append("system") or "ok.gpkg")
    result = _dwg_to_readable(str(tmp_path / "x.dwg"), log=lambda m: None)
    assert result == "ok.dxf"
    assert calls == ["bundled"]              # system GDAL საერთოდ არ გამოძახებულა


def test_dwg_readable_falls_back_to_system_gdal_when_bundled_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(dwg_core, "_bundled_dwg2dxf_path", lambda: "dwg2dxf.exe")

    def _bundled_fails(path, exe, log):
        raise DwgReadError("bundled conversion failed", reason=None)
    monkeypatch.setattr(dwg_core, "_dwg_to_dxf_via_bundled_libredwg", _bundled_fails)
    monkeypatch.setattr(dwg_core, "_dwg_to_gpkg_via_system_gdal",
                        lambda path, log: "fallback.gpkg")
    result = _dwg_to_readable(str(tmp_path / "x.dwg"), log=lambda m: None)
    assert result == "fallback.gpkg"


def test_dwg_readable_prefers_specific_reason_when_both_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(dwg_core, "_bundled_dwg2dxf_path", lambda: "dwg2dxf.exe")

    def _bundled_fails(path, exe, log):
        raise DwgReadError("bundled: unspecific", reason=None)
    def _system_fails(path, log):
        raise DwgReadError("system: old driver", reason="dwg_old_driver")
    monkeypatch.setattr(dwg_core, "_dwg_to_dxf_via_bundled_libredwg", _bundled_fails)
    monkeypatch.setattr(dwg_core, "_dwg_to_gpkg_via_system_gdal", _system_fails)
    with pytest.raises(DwgReadError) as exc:
        _dwg_to_readable(str(tmp_path / "x.dwg"), log=lambda m: None)
    assert exc.value.reason == "dwg_old_driver"     # კონკრეტული მიზეზი აჯობებს


def test_dwg_gdal_dxf_gap_when_bridge_succeeds_but_gdal_cant_parse_result(
        tmp_path, monkeypatch):
    """DWG → DXF კონვერტაცია (ხიდი) წარმატებულია, მაგრამ GDAL-ის DXF-რიდერი
    კონკრეტულ ობიექტზე ვარდება — ცალკე, თარგმნადი მიზეზით უნდა მოინიშნოს
    (და არა ბუნდოვანი ზოგადი შეცდომით)."""
    fake_dxf = tmp_path / "bridged.dxf"
    fake_dxf.write_bytes(b"fake")
    monkeypatch.setattr(dwg_core, "_dwg_to_readable",
                        lambda path, log: str(fake_dxf))

    def _boom(path):
        raise RuntimeError("ogrdxflayer.cpp, 2158: error at line 1596302")
    monkeypatch.setattr(dwg_core, "_read_layers", _boom)

    r = convert_file(str(tmp_path / "x.dwg"), str(tmp_path / "out"), "gpkg")
    assert r["reason"] == "dwg_gdal_dxf_gap"
    assert "LibreDWG" in r["error"] or "1596302" in r["error"]
    assert not fake_dxf.exists()               # tmp_source გასუფთავდა


# ---- ბანდლში ატანილი LibreDWG — რეალური ბინარი (მხოლოდ Windows, თუ არსებობს) ----
import sys                                                            # noqa: E402
from tools.dwg_convert_core import _bundled_dwg2dxf_path              # noqa: E402

_bundled_exe = _bundled_dwg2dxf_path()


@pytest.mark.skipif(sys.platform != "win32" or not _bundled_exe,
                    reason="Windows + bundled dwg2dxf.exe საჭირო")
def test_bundled_libredwg_binary_runs():
    """თავად ბანდლში ატანილი ბინარი გაშვებადია (DLL-ები გვერდით არის)."""
    import subprocess
    r = subprocess.run([_bundled_exe, "--help"], capture_output=True,
                       text=True, timeout=20)
    assert r.returncode in (0, 1)     # --help ხშირად 1-ს აბრუნებს, ჩვეულებრივია
    assert (r.stdout + r.stderr).strip() != ""
