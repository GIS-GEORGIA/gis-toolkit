# -*- coding: utf-8 -*-
"""სხვადასხვა საქაღალდეში მიმოფანტული shapefile-ების შედარება — სუფთა ლოგიკა.

საქაღალდეს რეკურსიულად სკანირებს, თითო shapefile-ს ზომავს (პოლიგონი: ფართი,
პერიმეტრი; ხაზი: სიგრძე; ყველაფერი: ობიექტების რაოდენობა) და აჯგუფებს
რანჟირებებად — „რომელია ყველაზე დიდი“. ყოველ შრეს თან აქვს **საქაღალდის სრული
გზა**, რადგან ერთნაირი სახელი (მაგ. ``nakveTi.shp``) ბევრ საქაღალდეშია.

ფართი/სიგრძე მეტრებშია: 32637/32638-ში მყოფი შრე უცვლელად იზომება; სხვა CRS
(მათ შორის 4326) მდებარეობის ზონაში გადადის (``plan_crs``) მხოლოდ გასაზომად,
ფაილი არ იცვლება. CRS-გარეშე შრეზე მეტრი ვერ დგინდება — რანჟირებაში არ
მონაწილეობს და ცალკე ჩამოითვლება. აქ tkinter არაა. UI: ``tools.parcel_search``.
"""

import os

POLYGON, LINE, POINT, OTHER = "polygon", "line", "point", "other"

# სტატუსები
OK, EMPTY, NO_CRS, ERROR = "ok", "empty", "no_crs", "error"


def scan_shapefiles(root):
    """``root``-ის ქვეშ ყველა ``*.shp`` (რეკურსიულად), გზების დალაგებული სია."""
    found = []
    for folder, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".shp"):
                found.append(os.path.join(folder, f))
    return sorted(found, key=lambda p: p.lower())


def kind_of(geometry_type):
    """pyogrio-ს გეომეტრიის ტიპიდან (მაგ. "Polygon Z") → ტიპის ჯგუფი."""
    g = str(geometry_type or "")
    if "Polygon" in g:
        return POLYGON
    if "Line" in g:
        return LINE
    if "Point" in g:
        return POINT
    return OTHER


def analyze_layer(path):
    """ერთი shapefile-ის გაზომვა → dict (ყოველთვის ბრუნდება, შეცდომაც ჩათვლით).

    გასაღებები: path, folder, name, kind, count, status, error, crs_label, converted,
    area_total, perimeter_total, area_max, length_total, length_max (არარელევანტური — None).
    """
    row = {
        "path": path, "folder": os.path.dirname(path), "name": os.path.basename(path),
        "kind": OTHER, "count": 0, "status": OK, "error": "", "crs_label": "",
        "converted": False, "area_total": None, "perimeter_total": None,
        "area_max": None, "length_total": None, "length_max": None,
    }
    try:
        import pyogrio
        info = pyogrio.read_info(path)
        row["kind"] = kind_of(info.get("geometry_type"))
        row["count"] = int(info.get("features") or 0)
        crs = info.get("crs")
        if row["count"] == 0:
            row["status"] = EMPTY
            return row
        if row["kind"] in (POINT, OTHER):
            return row                      # წერტილებს მხოლოდ რაოდენობა სჭირდება
        if not crs:
            row["status"] = NO_CRS
            return row

        import pyproj
        import geopandas as gpd
        from tools.line_buffer_core import plan_crs

        c = pyproj.CRS.from_user_input(crs)
        row["crs_label"] = "EPSG:{}".format(c.to_epsg()) if c.to_epsg() else c.name
        epsg, convert = plan_crs(crs, info["total_bounds"])
        gdf = gpd.read_file(path, columns=[])
        if convert:
            gdf = gdf.to_crs(epsg=epsg)
            row["converted"] = True
            row["crs_label"] += " → EPSG:{}".format(epsg)
        geoms = gdf.geometry[~(gdf.geometry.isna() | gdf.geometry.is_empty)]
        if row["kind"] == POLYGON:
            areas = geoms.area
            row["area_total"] = float(areas.sum())
            row["area_max"] = float(areas.max()) if len(areas) else 0.0
            row["perimeter_total"] = float(geoms.length.sum())
        else:
            lengths = geoms.length
            row["length_total"] = float(lengths.sum())
            row["length_max"] = float(lengths.max()) if len(lengths) else 0.0
        return row
    except Exception as e:                  # noqa: BLE001 — ცუდი ფაილი სხვებს არ აჩერებს
        row["status"] = ERROR
        row["error"] = str(e).splitlines()[0] if str(e) else e.__class__.__name__
        return row


# რანჟირებები: (გასაღები, ტიპი, მეტრიკის ველი)
RANKINGS = [
    ("poly_area", POLYGON, "area_total"),
    ("poly_perimeter", POLYGON, "perimeter_total"),
    ("poly_area_max", POLYGON, "area_max"),
    ("poly_count", POLYGON, "count"),
    ("line_length", LINE, "length_total"),
    ("line_length_max", LINE, "length_max"),
    ("line_count", LINE, "count"),
    ("point_count", POINT, "count"),
]


def rank_layers(rows, top_n=5):
    """``{რანჟირების_გასაღები: [row, …]}`` — კლებადობით, ``top_n``-მდე.

    მონაწილეობს მხოლოდ ``status == ok`` შრე შესაბამისი ტიპით. ტოლობისას —
    გზის მიხედვით (სტაბილური თანმიმდევრობა)."""
    out = {}
    for key, kind, field in RANKINGS:
        pool = [r for r in rows
                if r["status"] == OK and r["kind"] == kind and r.get(field) is not None]
        pool.sort(key=lambda r: (-r[field], r["path"].lower()))
        out[key] = pool[:max(1, int(top_n))]
    return out


def summarize(rows):
    """რაოდენობები ჩვენებისთვის: ტიპების მიხედვით + გამოტოვებული კატეგორიები."""
    s = {"total": len(rows), POLYGON: 0, LINE: 0, POINT: 0, OTHER: 0,
         EMPTY: [], NO_CRS: [], ERROR: []}
    for r in rows:
        if r["status"] == OK or r["status"] in (EMPTY, NO_CRS, ERROR):
            s[r["kind"]] += 1
        if r["status"] in (EMPTY, NO_CRS, ERROR):
            s[r["status"]].append(r)
    return s


_UNITS = {"ka": {"m2": "მ²", "ha": "ჰა", "m": "მ", "km": "კმ"},
          "en": {"m2": "m²", "ha": "ha", "m": "m", "km": "km"}}


def _num(v, nd=2):
    return "{:,.{nd}f}".format(v, nd=nd).replace(",", " ")


def fmt_area(m2, lang="ka"):
    """ფართი: ``12 345.68 მ² (1.2346 ჰა)`` — ჰექტარი ემატება, თუ ≥ 1 ჰა."""
    u = _UNITS.get(lang, _UNITS["ka"])
    txt = "{} {}".format(_num(m2), u["m2"])
    if m2 >= 10000:
        txt += " ({} {})".format(_num(m2 / 10000.0, 4), u["ha"])
    return txt


def fmt_length(m, lang="ka"):
    """სიგრძე: ``1 234.56 მ (1.235 კმ)`` — კილომეტრი ემატება, თუ ≥ 1 კმ."""
    u = _UNITS.get(lang, _UNITS["ka"])
    txt = "{} {}".format(_num(m), u["m"])
    if m >= 1000:
        txt += " ({} {})".format(_num(m / 1000.0, 3), u["km"])
    return txt
