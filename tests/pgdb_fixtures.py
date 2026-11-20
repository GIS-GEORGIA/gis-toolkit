# -*- coding: utf-8 -*-
"""ტესტ-ფიქსჩერები Personal Geodatabase-ის გადატანის ტესტებისთვის.

``tests/data/pgdb_template.mdb`` — **ცარიელი სქემა-შაბლონი** (ნამდვილი ბაზის სტრუქტურა, ერთი ჩანაწერიც
არა). ტესტი მას აკოპირებს დროებით საქაღალდეში და ავსებს **სინთეტიკური** მონაცემებით ``seed``-ით —
ისევე, როგორც ბაზა სტრუქტურას ინახავს (shape-buffer + სივრცითი ინდექსი). ნამდვილ ბაზებს არ ვეხებით.
"""

import datetime
import os
import shutil

from tools import pgdb_transfer_core as core

TEMPLATE = os.path.join(os.path.dirname(__file__), "data", "pgdb_template.mdb")

# ველების სიები ფენების მიხედვით (როგორც ნამდვილ ბაზაშია)
EXTRA_FIELDS = {
    "point": ["Id", "ganmcxadeb", "teq_piroba", "x", "y"],
    "line": ["Id", "ganmcxadeb", "teqnikuri", "SHAPE_Length", "STATUS"],
    "polygon": ["ganmcxadeb", "STATUS", "sakadastro", "SHAPE_Length", "SHAPE_Area"],
}
# ბაზაში „Required“ ველებია (ODBC-ის nullable ამას არ აჩვენებს) — შემოწმებულია INSERT-ით შაბლონზე
REQUIRED_DEFAULTS = {"point": {"Id": 0, "ganmcxadeb": "-", "teq_piroba": "-", "x": 0.0, "y": 0.0},
                     "line": {"Id": 0, "ganmcxadeb": "-", "teqnikuri": "-"},
                     "polygon": {"ganmcxadeb": "-", "sakadastro": "-"}}
DATE_COL = {"point": "TariRI", "line": "TariRi", "polygon": "TariRi"}      # რეგისტრი სხვადასხვაა (როგორც ბაზაში)


def d(y, m=1, dd=1, h=0, mi=0, s=0):
    return datetime.datetime(y, m, dd, h, mi, s)


def geom(kind, x=500000.0, y=4650000.0, multi=False):
    """მარტივი გეომეტრია-ბუფერი ტიპის მიხედვით."""
    if kind == "point":
        return core.encode_shape(1, [[(x, y)]])
    if kind == "line":
        parts = [[(x, y), (x + 10, y + 5), (x + 20, y)]]
        if multi:
            parts.append([(x + 100, y), (x + 120, y + 30)])
        return core.encode_shape(3, parts)
    outer = [(x, y), (x, y + 100), (x + 100, y + 100), (x + 100, y), (x, y)]           # საათის ისრის მიმართულებით
    parts = [outer]
    if multi:
        parts.append([(x + 20, y + 20), (x + 80, y + 20), (x + 80, y + 80), (x + 20, y + 80), (x + 20, y + 20)])
    return core.encode_shape(5, parts)


def relax(path, kind, column, sql_type="TEXT(50)"):
    """სვეტის „Required“ შეზღუდვის მოხსნა: ცარიელ ცხრილში სვეტს ვშლით და შეზღუდვის გარეშე ვამატებთ
    (ALTER COLUMN Required-ს არ ცვლის). რომ წყაროში ცარიელი მნიშვნელობა ჩავწეროთ და მიმღებმა (Required) უარყოს."""
    cn = core.connect(path, "excl")
    cur = cn.cursor()
    cur.execute("ALTER TABLE [{}] DROP COLUMN [{}]".format(kind, column))
    cur.execute("ALTER TABLE [{}] ADD COLUMN [{}] {}".format(kind, column, sql_type))
    cn.commit()
    cn.close()


def make_db(tmp_path, name):
    path = str(tmp_path / name)
    shutil.copyfile(TEMPLATE, path)
    return path


def seed(path, kind, rows):
    """სინთეტიკური ჩანაწერების ჩაწერა. ``rows`` — dict-ების სია:
    ``no`` (werilis_no), ``date`` (datetime/None), ``blob`` (shape-buffer; ნაგულისხმევი — მარტივი),
    ``attrs`` (დამატებითი ველები). აბრუნებს ახალი OBJECTID-ების სიას."""
    cn = core.connect(path, "excl")
    cur = cn.cursor()
    g = cur.execute("SELECT IdxOriginX, IdxOriginY, IdxGridSize FROM GDB_GeomColumns WHERE TableName=?",
                    (kind,)).fetchone()
    ext = cur.execute("SELECT ExtentLeft, ExtentBottom, ExtentRight, ExtentTop FROM GDB_GeomColumns "
                      "WHERE TableName=?", (kind,)).fetchone()
    box = list(ext)
    ids = []
    for i, r in enumerate(rows):
        blob = r.get("blob") or geom(kind, 500000.0 + 1000 * i, 4650000.0 + 1000 * i)
        cols = ["werilis_no", DATE_COL[kind], "SHAPE"]
        vals = [r.get("no"), r.get("date"), blob]
        attrs = dict(r.get("attrs") or {})
        if kind in REQUIRED_DEFAULTS:                                  # ბაზაში „Required“ ველებია (ODBC-ის nullable ამას არ აჩვენებს)
            for k, v in REQUIRED_DEFAULTS[kind].items():
                attrs.setdefault(k, v)
        if kind == "point":
            bx, by = core.shape_bbox(blob)[:2]
            attrs.setdefault("x", bx)                                   # x/y — ბაზაში Required, გეომეტრიიდან ვავსებთ
            attrs.setdefault("y", by)
        for k, v in attrs.items():
            cols.append(k)
            vals.append(v)
        cur.execute("INSERT INTO [{}] ({}) VALUES ({})".format(
            kind, ", ".join("[{}]".format(c) for c in cols), ", ".join("?" * len(cols))), vals)
        oid = cur.execute("SELECT @@IDENTITY").fetchval()
        bb = core.shape_bbox(blob)
        cur.execute("INSERT INTO [{}_SHAPE_Index] (IndexedObjectId, MinGX, MinGY, MaxGX, MaxGY) VALUES (?,?,?,?,?)"
                    .format(kind), (oid,) + core.index_cells(bb, g.IdxOriginX, g.IdxOriginY, g.IdxGridSize))
        box = [bb[0] if box[0] is None else min(box[0], bb[0]), bb[1] if box[1] is None else min(box[1], bb[1]),
               bb[2] if box[2] is None else max(box[2], bb[2]), bb[3] if box[3] is None else max(box[3], bb[3])]
        ids.append(oid)
    cur.execute("UPDATE GDB_GeomColumns SET ExtentLeft=?, ExtentBottom=?, ExtentRight=?, ExtentTop=? WHERE TableName=?",
                (box[0], box[1], box[2], box[3], kind))
    cn.commit()
    cn.close()
    return ids


def fetch_all(path, kind, cols="OBJECTID, werilis_no, SHAPE"):
    cn = core.connect(path, "ro")
    try:
        return [tuple(r) for r in cn.cursor().execute("SELECT {} FROM [{}] ORDER BY OBJECTID".format(cols, kind))]
    finally:
        cn.close()


def counts(path):
    cn = core.connect(path, "ro")
    try:
        cur = cn.cursor()
        out = {}
        for k in core.KINDS:
            out[k] = (cur.execute("SELECT COUNT(*) FROM [{}]".format(k)).fetchval(),
                      cur.execute("SELECT COUNT(*) FROM [{}_SHAPE_Index]".format(k)).fetchval())
        return out
    finally:
        cn.close()
