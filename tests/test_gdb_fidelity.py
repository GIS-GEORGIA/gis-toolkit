import copy
import hashlib
import sys

import pytest

pytest.importorskip("PySide6")
import pgdb_fixtures as fx
from pgdb_fixtures import d
from tools import gdb_fidelity as fid
from tools import pgdb_transfer_core as c

DOMAIN_XML = ("<GPCodedValueDomain2 xsi:type='typens:GPCodedValueDomain2' xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' "
              "xmlns:xs='http://www.w3.org/2001/XMLSchema' xmlns:typens='http://www.esri.com/schemas/ArcGIS/10.8'>"
              "<DomainName>St</DomainName><FieldType>esriFieldTypeInteger</FieldType><CodedValues xsi:type='typens:ArrayOfCodedValue'>"
              "<CodedValue xsi:type='typens:CodedValue'><Name>a</Name><Code xsi:type='xs:int'>0</Code></CodedValue>"
              "<CodedValue xsi:type='typens:CodedValue'><Name>b</Name><Code xsi:type='xs:int'>1</Code></CodedValue>"
              "</CodedValues></GPCodedValueDomain2>")
LAYER_XML = ("<DEFeatureClassInfo xsi:type='typens:DEFeatureClassInfo' xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' "
             "xmlns:typens='http://www.esri.com/schemas/ArcGIS/10.8'><Name>l</Name><GPFieldInfoExs><GPFieldInfoEx>"
             "<Name>S</Name><DomainName>St</DomainName><FieldType>esriFieldTypeInteger</FieldType><IsNullable>true</IsNullable>"
             "</GPFieldInfoEx></GPFieldInfoExs><SubtypeFieldName>T</SubtypeFieldName><Subtypes><Subtype><SubtypeName>x</SubtypeName>"
             "<SubtypeCode>5</SubtypeCode></Subtype></Subtypes><HasGlobalID>false</HasGlobalID>"
             "<Extent><XMin>1</XMin><YMin>2</YMin></Extent></DEFeatureClassInfo>")


def test_parsers_and_violations():
    dom = fid._parse_domain(DOMAIN_XML)
    assert dom["coded"] == {"0": "a", "1": "b"}
    lay = fid._parse_layer(LAYER_XML)
    assert lay["fields"]["S"]["domain"] == "St" and lay["subtype_field"] == "T" and "5" in lay["subtypes"]
    a = {"domains": {"St": dom}, "layers": {"l": lay}}
    v = fid.domain_violations(a, "l", [(1, {"S": 1, "T": 5}), (2, {"S": 9, "T": 5}), (3, {"S": None, "T": 7}), (4, {"S": 0.0})])
    assert [(o, f) for o, f, _v, _w in v] == [(2, "S"), (3, "T")]          # NULL ნორმალურია; 9 და ქვეტიპი 7 — არა


def test_compare_detects_every_kind_of_loss():
    base = {"kind": "gdb", "domains": {"St": fid._parse_domain(DOMAIN_XML)}, "layers": {"l": fid._parse_layer(LAYER_XML)},
            "items": {"\\l": "h1", "St": "h2"}, "files": {"a.gdbtable": 1, "a.atx": 1}}
    assert fid.compare(base, copy.deepcopy(base)) == []
    b = copy.deepcopy(base)
    del b["domains"]["St"]
    b["layers"]["l"]["fields"]["S"]["domain"] = None
    b["layers"]["l"]["subtypes"] = {}
    b["items"]["\\l"] = "other"
    del b["files"]["a.atx"]
    out = " | ".join(fid.compare(base, b))
    for must in ("domain MISSING: St", "field property CHANGED: l.S domain", "layer property CHANGED: l subtypes",
                 "item definition CHANGED", "file MISSING"):
        assert must in out, out


def test_extent_changes_are_not_differences():
    n1 = fid._DYN_RE.sub("", LAYER_XML)
    n2 = fid._DYN_RE.sub("", LAYER_XML.replace("<XMin>1</XMin>", "<XMin>-99.5</XMin>"))
    assert hashlib.sha1(n1.encode()).hexdigest() == hashlib.sha1(n2.encode()).hexdigest()


@pytest.mark.skipif(sys.platform != "win32" or not c.driver_available(), reason="needs Access ODBC driver")
def test_mdb_final_copy_report_ok_and_detects_a_damaged_record(tmp_path):
    dst = fx.make_db(tmp_path, "dst.mdb")
    fx.seed(dst, "point", [{"no": "A", "date": d(2025, 1, 1)}, {"no": "B", "date": d(2025, 2, 1)}])
    final = c.final_output_path(dst, stamp="s")
    c.make_final_copy(dst, final)
    fx.seed(final, "point", [{"no": "C", "date": d(2026, 1, 1)}])                        # ახალი ჩანაწერი ასლში
    ok, lines = fid.report(dst, final, ["point", "line", "polygon"])
    assert ok, lines
    assert any("point: original records 2 / identical in the new database 2" in ln for ln in lines)
    cn = c.connect(final, "excl")                                                       # ასლში არსებულ ჩანაწერს ვაზიანებთ
    cn.cursor().execute("UPDATE [point] SET werilis_no='CHANGED' WHERE werilis_no='A'")
    cn.commit()
    cn.close()
    ok2, lines2 = fid.report(dst, final, ["point", "line", "polygon"])
    assert not ok2 and any("PROBLEM" in ln for ln in lines2)
