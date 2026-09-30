# -*- coding: utf-8 -*-
"""dwg_convert_core — ezdxf rescue-გზის ტესტები (geopandas + ezdxf საჭირო).

ცალკე ფაილშია (და არა ``test_dwg_convert_core_gpd.py``-ში), რადგან
``pytest.importorskip`` მოდულის დონეზე **მთელ ფაილს** გამოტოვებს — თუ ezdxf
გარემოში არაა, ეს ფაილი გამოტოვდება, დანარჩენი geopandas-ტესტები კი მაინც
გაეშვება.

GDAL-ის DXF-რიდერს ზოგჯერ ჩავარდება კონკრეტულ ობიექტზე (რეალურ, რთულ
DWG-ზე გადამოწმებული — 2935 ობიექტიდან GDAL საერთოდ ვერ წაიკითხავდა DXF-ს,
ezdxf-მა 2580 აღადგინა, ბლოკების ამოხსნის ჩათვლით); ``_read_dxf_via_ezdxf``
ამ შემთხვევის rescue-გზაა.
"""

import pytest

gpd = pytest.importorskip("geopandas")
ezdxf = pytest.importorskip("ezdxf")

from shapely.geometry import Point                                    # noqa: E402
from tools.dwg_convert_core import (                                  # noqa: E402
    _dxf_entity_geoms, _read_dxf_via_ezdxf, convert_file,
)


def _make_dxf(path, doctype="R2018"):
    """სინთეზური DXF: LINE (გეომეტრია), TEXT (წმინდა ანოტაცია, გეომეტრიის
    გარეშე), INSERT ბლოკის მითითება (რეალური გეომეტრია ბლოკშია)."""
    doc = ezdxf.new(doctype)
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "L1"})
    msp.add_text("hello", dxfattribs={"layer": "TXT"}).set_placement((1, 1))

    block = doc.blocks.new(name="SYMBOL")
    block.add_circle((0, 0), radius=1)
    block.add_line((-1, 0), (1, 0))
    msp.add_blockref("SYMBOL", (5, 5), dxfattribs={"layer": "BLK"})

    doc.saveas(path)


def test_dxf_entity_geoms_direct_entity(tmp_path):
    _make_dxf(str(tmp_path / "x.dxf"))
    doc = ezdxf.readfile(str(tmp_path / "x.dxf"))
    line = next(e for e in doc.modelspace() if e.dxftype() == "LINE")
    mappings = list(_dxf_entity_geoms(line))
    assert len(mappings) == 1
    assert mappings[0]["type"] == "LineString"


def test_dxf_entity_geoms_skips_pure_annotation(tmp_path):
    _make_dxf(str(tmp_path / "x.dxf"))
    doc = ezdxf.readfile(str(tmp_path / "x.dxf"))
    text = next(e for e in doc.modelspace() if e.dxftype() == "TEXT")
    assert list(_dxf_entity_geoms(text)) == []      # წმინდა ანოტაცია — არაფერი


def test_dxf_entity_geoms_explodes_insert_block(tmp_path):
    _make_dxf(str(tmp_path / "x.dxf"))
    doc = ezdxf.readfile(str(tmp_path / "x.dxf"))
    insert = next(e for e in doc.modelspace() if e.dxftype() == "INSERT")
    mappings = list(_dxf_entity_geoms(insert))
    # ბლოკში ორი ერთეულია (წრე + ხაზი) — ორივემ უნდა გამოსცეს გეომეტრია
    assert len(mappings) == 2
    types = sorted(m["type"] for m in mappings)
    assert types == ["LineString", "Polygon"]        # წრე → Polygon (ezdxf.addons.geo)


def test_read_dxf_via_ezdxf_builds_geodataframe(tmp_path):
    p = str(tmp_path / "x.dxf")
    _make_dxf(p)
    gdf = _read_dxf_via_ezdxf(p, log=lambda m: None)
    assert len(gdf) == 3                             # LINE + წრე + ხაზი (ბლოკიდან)
    assert {"Layer", "EntityType", "geometry"} <= set(gdf.columns)
    assert "TXT" not in set(gdf["Layer"])             # ანოტაციის შრეს გეომეტრია არ ჰქონდა


def test_read_dxf_via_ezdxf_raises_when_nothing_convertible(tmp_path):
    doc = ezdxf.new("R2018")
    doc.modelspace().add_text("only text", dxfattribs={"layer": "0"})
    p = str(tmp_path / "textonly.dxf")
    doc.saveas(p)
    with pytest.raises(RuntimeError):
        _read_dxf_via_ezdxf(p, log=lambda m: None)


def test_convert_file_falls_back_to_ezdxf_when_gdal_dxf_read_fails(
        tmp_path, monkeypatch):
    """GDAL-ის DXF-რიდერი ჩავარდება (მოკებულია) → ezdxf rescue-მ უნდა
    გადაარჩინოს — ნამდვილი DXF-ით, ნამდვილი ezdxf-ითა და pyogrio-თი."""
    import tools.dwg_convert_core as dwg_core
    src = str(tmp_path / "x.dxf")
    _make_dxf(src)

    def _gdal_fails(path):
        raise RuntimeError("simulated ogrdxflayer.cpp parse error")
    monkeypatch.setattr(dwg_core, "_read_layers", _gdal_fails)

    r = convert_file(src, str(tmp_path / "out"), "gpkg")
    assert r["error"] is None
    assert r["reason"] is None
    assert r["layers"] == [("entities", 3)]


def test_convert_file_reports_dwg_gdal_dxf_gap_when_ezdxf_also_fails(
        tmp_path, monkeypatch):
    """DWG-ბრიჯის შემთხვევაში, თუ **ვერც** GDAL-მა, **ვერც** ezdxf-მა
    წაიკითხა — ცხადი ``dwg_gdal_dxf_gap`` მიზეზი უნდა დაბრუნდეს."""
    import tools.dwg_convert_core as dwg_core
    fake_dxf = tmp_path / "bridged.dxf"
    fake_dxf.write_bytes(b"not a real dxf")            # ezdxf-იც ჩავარდება
    monkeypatch.setattr(dwg_core, "_dwg_to_readable",
                        lambda path, log: str(fake_dxf))
    monkeypatch.setattr(dwg_core, "_read_layers",
                        lambda path: (_ for _ in ()).throw(
                            RuntimeError("gdal parse error")))
    r = convert_file(str(tmp_path / "x.dwg"), str(tmp_path / "out"), "gpkg")
    assert r["reason"] == "dwg_gdal_dxf_gap"
    assert not fake_dxf.exists()                        # tmp_source გასუფთავდა
