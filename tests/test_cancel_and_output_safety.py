# -*- coding: utf-8 -*-
"""Cancellation checkpoints and output integrity: a cancelled or failed run leaves either the COMPLETE output
or nothing at all (no partial GPKG / SHP / GDB / XLSX, no hidden staging files), on Windows and Linux.

The "cancel at every checkpoint" tests first count how often a full run polls ``cancel()`` and then repeat the
run cancelling at each of those polls in turn - so every checkpoint is exercised without depending on exactly
where the checkpoints are."""
import os
import time

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import LineString, Point, Polygon  # noqa: E402

from tools import safe_output  # noqa: E402
from tools.safe_output import leftover_staging, staged_file, staged_shapefile  # noqa: E402

# a folder name with a space and Georgian letters - the path handling must not depend on ASCII / no spaces
ODD = "გამოსავალი out dir"


def _all_files(folder):
    out = []
    for root, dirs, files in os.walk(folder):
        out += [os.path.relpath(os.path.join(root, f), folder) for f in files]
        out += [os.path.relpath(os.path.join(root, d), folder) + os.sep for d in dirs]
    return sorted(out)


def _no_staging_anywhere(folder):
    for root, dirs, files in os.walk(folder):
        assert not leftover_staging(root), (root, os.listdir(root))


class _CancelAt:
    """cancel() that returns True from the k-th call on (k=None: never); counts calls."""

    def __init__(self, k=None):
        self.k, self.calls = k, 0

    def __call__(self):
        self.calls += 1
        return self.k is not None and self.calls >= self.k


# ---------------------------------------------------------------- safe_output helpers
def test_staged_file_success_failure_and_no_overwrite(tmp_path):
    out = tmp_path / ODD
    final = out / "r.gpkg"
    gdf = gpd.GeoDataFrame({"a": [1]}, geometry=[Point(0, 0)], crs=32638)
    with pytest.raises(RuntimeError):
        with staged_file(str(final)) as tmp:
            gdf.to_file(tmp, layer="one", driver="GPKG")
            raise RuntimeError("disk full / cancelled half way")
    assert not final.exists() and os.listdir(out) == []
    with staged_file(str(final)) as tmp:
        assert os.path.dirname(tmp) == str(out)                  # same folder -> rename, not copy
        gdf.to_file(tmp, layer="one", driver="GPKG")
        gdf.to_file(tmp, layer="two", driver="GPKG", mode="a")
    assert sorted(gpd.list_layers(str(final))["name"]) == ["one", "two"]
    assert os.listdir(out) == ["r.gpkg"]
    with pytest.raises(FileExistsError):
        with staged_file(str(final)):
            pass
    with staged_file(str(out / "empty.gpkg")):
        pass                                                     # writer produced nothing -> nothing appears
    assert os.listdir(out) == ["r.gpkg"]


def test_staged_shapefile_moves_all_sidecars_or_nothing(tmp_path):
    out = tmp_path / ODD
    gdf = gpd.GeoDataFrame({"name": ["ქართ"]}, geometry=[Point(1, 2)], crs=32638)
    with pytest.raises(ValueError):
        with staged_shapefile(str(out / "z.shp")) as tmp:
            gdf.to_file(tmp, driver="ESRI Shapefile", encoding="utf-8")
            raise ValueError("boom")
    assert os.listdir(out) == []
    with staged_shapefile(str(out / "z.shp")) as tmp:
        gdf.to_file(tmp, driver="ESRI Shapefile", encoding="utf-8")
    names = sorted(os.listdir(out))
    assert {"z.shp", "z.shx", "z.dbf", "z.prj"} <= set(names) and not leftover_staging(str(out))
    back = gpd.read_file(str(out / "z.shp"))
    assert back["name"][0] == "ქართ" and back.crs.to_epsg() == 32638


def test_staged_shapefile_never_overwrites(tmp_path):
    gdf = gpd.GeoDataFrame({"a": [1]}, geometry=[Point(0, 0)], crs=32638)
    p = tmp_path / "x.shp"
    gdf.to_file(str(p))
    before = p.read_bytes()
    with pytest.raises(FileExistsError):
        with staged_shapefile(str(p)) as tmp:
            gpd.GeoDataFrame({"a": [2, 3]}, geometry=[Point(5, 5), Point(6, 6)], crs=32638).to_file(tmp)
    assert p.read_bytes() == before and not leftover_staging(str(tmp_path))


# ---------------------------------------------------------------- DWG/DXF converter
def _multi_layer_source(path, n_layers=6, n_feat=50):
    for i in range(n_layers):
        gdf = gpd.GeoDataFrame(
            {"k": list(range(n_feat))},
            geometry=[Point(i, j) if j % 2 else LineString([(i, j), (i + 1, j + 1)]) for j in range(n_feat)],
            crs=32638)
        gdf.to_file(path, layer="L{}".format(i), driver="GPKG", mode="w" if i == 0 else "a")
    return path


@pytest.mark.parametrize("fmt", ["gpkg", "gdb", "shp"])
def test_dwg_convert_cancel_at_every_checkpoint_leaves_complete_output_or_nothing(tmp_path, fmt):
    from tools.dwg_convert_core import convert_batch
    src = _multi_layer_source(str(tmp_path / "src.gpkg"))
    probe = _CancelAt()
    full = convert_batch([src], str(tmp_path / "full"), fmt, cancel=probe)
    assert not full["cancelled"] and full["files_ok"] == 1
    n = probe.calls
    assert n >= 6                                  # checked per layer, not only per file
    for k in range(1, n + 1):
        out = tmp_path / "o{}".format(k)
        r = convert_batch([src], str(out), fmt, cancel=_CancelAt(k))
        if r["cancelled"]:
            assert _all_files(out) == [] if out.exists() else True, (k, _all_files(out))
        else:
            assert r["files_ok"] == 1
        if out.exists():
            _no_staging_anywhere(str(out))


def test_dwg_convert_error_while_writing_leaves_nothing(tmp_path, monkeypatch):
    from tools import dwg_convert_core as core
    src = _multi_layer_source(str(tmp_path / "src.gpkg"), n_layers=3)
    real = core._normalize_crs
    calls = []

    def flaky(sub, *a, **k):
        calls.append(1)
        if len(calls) == 3:
            raise OSError("No space left on device")
        return real(sub, *a, **k)
    monkeypatch.setattr(core, "_normalize_crs", flaky)
    out = tmp_path / "out"
    with pytest.raises(OSError):
        core.convert_file(src, str(out), "gpkg")
    assert os.listdir(out) == []


# ---------------------------------------------------------------- geometry collector
def test_geom_collect_cancel_at_every_checkpoint(tmp_path):
    from tools.geom_collect_core import collect_to_geopackage
    a = str(tmp_path / "a.gpkg")
    gpd.GeoDataFrame({"x": [1, 2]}, geometry=[Point(0, 0), LineString([(0, 0), (1, 1)])],
                     crs=32638).to_file(a, driver="GPKG")
    b = str(tmp_path / "b.gpkg")
    gpd.GeoDataFrame({"x": [3]}, geometry=[Polygon([(0, 0), (1, 0), (1, 1)])], crs=32638).to_file(b, driver="GPKG")
    probe = _CancelAt()
    full = collect_to_geopackage([a, b], str(tmp_path / "full.gpkg"), cancel=probe)
    assert not full["cancelled"] and full["out_files"] and probe.calls >= 5
    for k in range(1, probe.calls + 1):
        out = tmp_path / "o{}".format(k)
        out.mkdir()
        r = collect_to_geopackage([a, b], str(out / "res.gpkg"), cancel=_CancelAt(k))
        if r["cancelled"]:
            assert os.listdir(out) == [], (k, os.listdir(out))
        else:
            assert sorted(gpd.list_layers(str(out / "res.gpkg"))["name"]) == sorted(full["out_files"])
            assert os.listdir(out) == ["res.gpkg"]


# ---------------------------------------------------------------- line buffer
def test_line_buffer_cancel_keeps_finished_zones_complete_and_nothing_partial(tmp_path):
    from tools import line_buffer_core as core
    src = str(tmp_path / "gas.shp")
    gpd.GeoDataFrame({"id": [1]}, geometry=[LineString([(500000, 4650000), (501000, 4650000)])],
                     crs=32638).to_file(src)
    zones = [(4, "a"), (25, "b"), (100, "c")]
    probe = _CancelAt()
    (tmp_path / "full").mkdir()
    core.build_buffers(src, str(tmp_path / "full"), zones, 32638, cancel=probe)
    for k in range(1, probe.calls + 1):
        out = tmp_path / "o{}".format(k)
        out.mkdir()
        try:
            written = core.build_buffers(src, str(out), zones, 32638, cancel=_CancelAt(k))
        except core.Cancelled:
            written = None
        shps = sorted(f for f in os.listdir(out) if f.endswith(".shp"))
        for f in shps:                                   # every shapefile that exists is complete & readable
            assert len(gpd.read_file(str(out / f))) == 1
            for ext in (".shx", ".dbf", ".prj"):
                assert os.path.exists(str(out / f)[:-4] + ext)
        assert not leftover_staging(str(out))
        if written is not None:
            assert len(shps) == len(zones)


# ---------------------------------------------------------------- xlsx
def test_xlsx_save_failure_keeps_previous_file_and_leaves_no_temp(tmp_path):
    from openpyxl import Workbook

    from tools.xlsx_format import save_workbook
    p = tmp_path / ODD / "coords.xlsx"
    p.parent.mkdir()
    wb = Workbook()
    wb.active["A1"] = "v1"
    save_workbook(wb, str(p))
    before = p.read_bytes()

    class Broken:
        def save(self, path):
            open(path, "wb").write(b"PK\x03\x04 half")      # starts writing, then fails
            raise OSError("disk full")
    with pytest.raises(OSError):
        save_workbook(Broken(), str(p))
    assert p.read_bytes() == before and os.listdir(p.parent) == ["coords.xlsx"]


# ---------------------------------------------------------------- larger dataset: cancel responsiveness
def test_large_conversion_cancel_is_responsive(tmp_path):
    """60 layers x 2000 features: cancelling during the run stops within about one layer (not at the end of
    the file) and nothing of the source is left behind."""
    from tools.dwg_convert_core import convert_batch
    src = _multi_layer_source(str(tmp_path / "big.gpkg"), n_layers=60, n_feat=2000)
    t0 = time.perf_counter()
    started = {}

    def cancel():
        started.setdefault("t", time.perf_counter())
        return time.perf_counter() - started["t"] > 0.5         # user presses Cancel after ~0.5 s
    r = convert_batch([src], str(tmp_path / "out"), "gpkg", cancel=cancel)
    took = time.perf_counter() - t0
    assert r["cancelled"]
    assert os.listdir(str(tmp_path / "out")) == []
    assert took < 20, took


# ---------------------------------------------------------------- packaging
def test_pyinstaller_spec_bundles_v2_assets():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = open(os.path.join(root, "gis_box.spec"), encoding="utf-8").read()
    assert '("v2/assets", "v2/assets")' in spec and "PySide6.QtSvg" in spec
    assert safe_output.leftover_staging(os.path.join(root, "v2", "assets")) == []


# ---------------------------------------------------------------- cross-platform path handling
def test_shapefile_scans_and_templates_ignore_letter_case_on_every_platform(tmp_path):
    """``*.shp`` globbing is case-sensitive on Linux: upper-case files from Windows were missed there."""
    from tools import line_buffer_core, shp_coords_core, zone_intersect_core
    from tools.platform_utils import files_with_stem, files_with_suffix
    d = tmp_path / ODD
    d.mkdir()
    gpd.GeoDataFrame({"a": [1]}, geometry=[Point(0, 0)], crs=32638).to_file(str(d / "pts.shp"))
    gpd.GeoDataFrame({"a": [1]}, geometry=[LineString([(0, 0), (5, 5)])], crs=32638).to_file(str(d / "line.shp"))
    for stem in ("pts", "line"):                         # rename to upper case, as copied from Windows
        for f in list(os.listdir(d)):
            if f.startswith(stem + "."):
                os.replace(str(d / f), str(d / (stem.upper() + os.path.splitext(f)[1].upper())))
    assert [os.path.basename(p) for p in files_with_suffix(str(d), ".shp")] == ["LINE.SHP", "PTS.SHP"]
    assert "PTS.SHP" in shp_coords_core.scan_point_shapefiles(str(d))
    assert list(line_buffer_core.scan_line_shapefiles(str(d))) == ["LINE.SHP"]
    assert len(files_with_stem(str(d), "pts")) >= 3
    assert len(zone_intersect_core.template_files(str(d), "Pts")) >= 3
    assert files_with_suffix(str(tmp_path / "missing"), ".shp") == []


def test_settings_dir_follows_the_platform_convention(monkeypatch, tmp_path):
    import sys

    from v2 import settings
    monkeypatch.delenv("GIS_BOX_V2_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    d = settings.settings_dir()
    expect = tmp_path / ("local" if sys.platform == "win32" else "xdg") / "GIS_BOX"
    assert os.path.normcase(d) == os.path.normcase(str(expect)) and os.path.isdir(d)
