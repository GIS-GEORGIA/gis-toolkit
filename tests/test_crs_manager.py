import os

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import Point, box

from tools import crs_manager as cm


def _gdf(crs=None, x=44.8, y=41.7):
    return gpd.GeoDataFrame({"a": [1]}, geometry=[Point(x, y)], crs=crs)


def test_describe_epsg_utm():
    i = cm.describe(32637)
    assert i.epsg == 32637 and i.kind == "projected" and i.is_metric
    assert "metre" in i.unit.lower() and "UTM" in i.name
    g = cm.describe(4326)
    assert g.is_geographic and not g.is_metric and "degree" in g.unit.lower()


def test_describe_missing():
    assert cm.describe(None).kind == "unknown"


def test_invalid_crs():
    with pytest.raises(cm.CrsError) as e:
        cm.as_crs("not-a-crs")
    assert e.value.code == "invalid_crs"


def test_assign_requires_confirmation():
    with pytest.raises(cm.CrsError) as e:
        cm.assign_crs(_gdf(), 4326)
    assert e.value.code == "confirmation_required"


def test_assign_keeps_coordinates_and_warns_on_override():
    g = _gdf(4326)
    new, rep = cm.assign_crs(g, 32637, confirmed=True)
    assert new.geometry.iloc[0].x == pytest.approx(44.8)       # coordinates NOT transformed
    assert new.crs.to_epsg() == 32637
    assert any(w.startswith("override") for w in rep.warnings)
    assert any(w.startswith("range") for w in rep.warnings)    # degrees under a projected CRS


def test_reproject_requires_source_crs():
    with pytest.raises(cm.CrsError) as e:
        cm.reproject_gdf(_gdf(None), 32638)
    assert e.value.code == "missing_crs"


def test_reproject_changes_coordinates_and_reports():
    out, rep = cm.reproject_gdf(_gdf(4326), 32638)
    assert out.geometry.iloc[0].x > 100000
    assert rep.operation == "reproject" and rep.method and rep.accuracy
    assert rep.original_crs.epsg == 4326 and rep.target_crs.epsg == 32638
    assert "EPSG" in rep.to_text() and rep.to_dict()["target_crs"]["epsg"] == 32638


def test_reproject_same_crs_noop():
    out, rep = cm.reproject_gdf(_gdf(4326), 4326)
    assert rep.method.startswith("none") and out.geometry.iloc[0].x == pytest.approx(44.8)


def test_suggestions_are_candidates_only():
    s = cm.suggest_candidates((44, 41, 45, 42))
    assert s and all("NOT a definitive" in c["note"] for c in s)
    u = cm.suggest_candidates((400000, 4600000, 500000, 4700000))
    assert {c["epsg"] for c in u} >= {32637, 32638}


def test_range_warnings():
    assert cm.range_warnings((400000, 4600000, 500000, 4700000), 4326)
    assert cm.range_warnings((44, 41, 45, 42), 32637)
    assert not cm.range_warnings((44, 41, 45, 42), 4326)


def test_check_units():
    assert cm.check_units(4326) is not None
    assert cm.check_units(32637) is None


def test_metric_candidates_zone_order():
    assert cm.metric_candidates((40, 41, 41, 42))[0]["epsg"] == 32637   # < 42E -> zone 37
    assert cm.metric_candidates((44, 41, 45, 42))[0]["epsg"] == 32638   # >= 42E -> zone 38


def test_ensure_metric_reports_and_respects_choice():
    g = _gdf(4326)
    out, rep = cm.ensure_metric(g, 32637)
    assert out.crs.to_epsg() == 32637 and rep is not None
    auto, rep3 = cm.ensure_metric(g)                      # no choice -> suggested zone, but reported
    assert auto.crs.to_epsg() == 32638 and rep3 is not None
    same, rep2 = cm.ensure_metric(out)
    assert rep2 is None and same is out
    with pytest.raises(cm.CrsError):
        cm.ensure_metric(_gdf(None))


def test_detect_shp_without_prj_and_with(tmp_path):
    p = str(tmp_path / "a.shp")
    _gdf(4326).to_file(p)
    d = cm.detect(p)
    assert d.has_crs and d.info.epsg == 4326 and d.bounds
    os.remove(str(tmp_path / "a.prj"))
    d2 = cm.detect(p)
    assert not d2.has_crs
    assert any(w.startswith("no_prj") for w in d2.warnings)
    assert any(w.startswith("missing_crs") for w in d2.warnings)
    assert d2.suggestions


def test_detect_gpkg_geojson(tmp_path):
    for name in ("a.gpkg", "a.geojson"):
        p = str(tmp_path / name)
        _gdf(4326).to_file(p)
        assert cm.detect(p).info.epsg == 4326


def test_detect_not_found():
    with pytest.raises(cm.CrsError):
        cm.detect("nope.shp")


def test_file_ops_preserve_source_and_never_overwrite(tmp_path):
    src = str(tmp_path / "s.gpkg")
    _gdf(4326).to_file(src)
    before = os.path.getsize(src)
    out = str(tmp_path / "o.gpkg")
    rep = cm.reproject_file(src, out, 32637)
    assert os.path.getsize(src) == before
    assert cm.detect(out).info.epsg == 32637 and rep.output_file == out
    with pytest.raises(cm.CrsError) as e:
        cm.reproject_file(src, out, 32638)
    assert e.value.code == "exists"
    with pytest.raises(cm.CrsError) as e:
        cm.reproject_file(src, src, 32638)
    assert e.value.code == "same_file"


def test_assign_file_confirmation_and_unknown_crs(tmp_path):
    src = str(tmp_path / "u.shp")
    _gdf(None, 500000, 4650000).to_file(src)
    os.path.exists(str(tmp_path / "u.prj")) and os.remove(str(tmp_path / "u.prj"))
    out = str(tmp_path / "u2.gpkg")
    with pytest.raises(cm.CrsError) as e:
        cm.assign_file(src, out, 32637)
    assert e.value.code == "confirmation_required" and not os.path.exists(out)
    rep = cm.assign_file(src, out, 32637, confirmed=True)
    assert cm.detect(out).info.epsg == 32637 and "NOT changed" in rep.to_text()


def test_compare():
    assert cm.compare(4326, "EPSG:4326") and not cm.compare(4326, 32637) and not cm.compare(None, 4326)
