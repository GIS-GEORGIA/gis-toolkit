import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import LineString, Point, box

from tools import crs_manager as cm
from tools import dwg_convert_core as dwg
from tools import shp_analysis_core as sa
from tools import zone_intersect_core as zc


def _square_utm38(side=100.0):
    return gpd.GeoDataFrame(geometry=[box(500000, 4650000, 500000 + side, 4650000 + side)], crs=32638)


def test_area_in_degrees_is_meaningless_but_measure_is_exact():
    g4326 = _square_utm38().to_crs(4326)
    assert g4326.geometry.area.iloc[0] < 1e-4                   # square degrees - the trap
    m = cm.measure(g4326, 32638)
    assert m["crs"] == "EPSG:32638" and m["unit"] == "m"
    assert m["area_m2"].iloc[0] == pytest.approx(10000.0, abs=0.01)
    assert m["length_m"].iloc[0] == pytest.approx(400.0, abs=0.01)
    assert m["report"] is not None and m["report"].method


def test_measure_of_metric_data_changes_nothing():
    g = _square_utm38()
    m = cm.measure(g)
    assert m["report"] is None and m["area_m2"].iloc[0] == pytest.approx(10000.0)


def test_measure_other_user_chosen_zone_is_close():
    g = _square_utm38()
    m37 = cm.measure(g, 32637)           # outside its own zone: distortion, but reported and bounded
    assert abs(m37["area_m2"].iloc[0] - 10000) / 10000 < 0.02
    assert m37["crs"] == "EPSG:32637"


def test_measure_requires_crs():
    with pytest.raises(cm.CrsError):
        cm.measure(gpd.GeoDataFrame(geometry=[Point(1, 1)]))


def test_shp_analysis_geographic_input_reported_in_metres(tmp_path):
    p = str(tmp_path / "poly.shp")
    _square_utm38(200).to_crs(4326).to_file(p)
    row = sa.analyze_layer(p)
    assert row["converted"] is True and "→ EPSG:32638" in row["crs_label"]
    assert row["area_total"] == pytest.approx(40000.0, rel=1e-4)


def test_zone_intersect_rejects_geographic_parcels():
    with pytest.raises(ValueError, match="geographic CRS"):
        zc.require_metric_crs(4326)
    zc.require_metric_crs(32638)
    zc.require_metric_crs(None)          # unknown units: allowed (backward compatible)


def test_dwg_normalize_logs_assumed_and_reprojected_crs():
    msgs = []
    g = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 1)])])
    out = dwg._normalize_crs(g, 32638, msgs.append)
    assert out.crs.to_epsg() == 32638 and any("ASSUMED" in m for m in msgs)
    msgs.clear()
    dwg._normalize_crs(out, 32637, msgs.append)
    assert any("reprojecting" in m for m in msgs)
    msgs.clear()
    dwg._normalize_crs(out, 32638, msgs.append)
    assert not msgs                      # same CRS: nothing to report
