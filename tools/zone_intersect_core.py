# -*- coding: utf-8 -*-
"""ნაკვეთის საზღვრის × დაცვის ზონის საზღვრის კვეთის წერტილები — სუფთა ლოგიკა.

arcpy-ს ანალოგი: ``arcpy.analysis.Intersect([parcels, zones], out, output_type="POINT")``
ორ პოლიგონურ შრეს შორის — ანუ **წერტილები, სადაც ნაკვეთის საზღვარი კვეთს დაცვის
ზონის საზღვარს**. shapely-ით: ``parcel.boundary ∩ zone.boundary`` და შედეგიდან
0-განზომილებიანი (წერტილოვანი) ნაწილების ამოღება.

აქ tkinter/GIS-ი არაა — მხოლოდ shapely (რომელიც geopandas-თან ერთად ისედ არის).
UI: ``tools.zone_intersect``.
"""


def _iter_points(geom, out):
    """კვეთის გეომეტრიიდან 0-D წერტილების ამოკრება ``out``-ში ((x, y) წყვილები).

    Point/MultiPoint → კოორდინატები; LineString/MultiLineString (საზღვრები
    ერთმანეთზე გადის — კოლინეარული) → ბოლო წვეროები; GeometryCollection →
    რეკურსია; პოლიგონი (boundary∩boundary-ში არ უნდა შეგვხვდეს) → იგნორი.
    """
    if geom is None or geom.is_empty:
        return
    gt = geom.geom_type
    if gt == "Point":
        out.append((geom.x, geom.y))
    elif gt == "MultiPoint":
        for g in geom.geoms:
            out.append((g.x, g.y))
    elif gt in ("LineString", "LinearRing"):
        cs = list(geom.coords)
        if cs:
            out.append(cs[0])
            out.append(cs[-1])
    elif gt == "MultiLineString":
        for g in geom.geoms:
            cs = list(g.coords)
            if cs:
                out.append(cs[0])
                out.append(cs[-1])
    elif gt == "GeometryCollection":
        for g in geom.geoms:
            _iter_points(g, out)
    # Polygon/MultiPolygon — უგულებელყოფილი


def crossing_points(parcel, zone):
    """ერთი ნაკვეთისა და ერთი ზონის საზღვრების კვეთის წერტილები [(x, y), …]."""
    out = []
    try:
        inter = parcel.boundary.intersection(zone.boundary)
    except Exception:                       # noqa: BLE001 — გატეხილი გეომეტრია
        return out
    _iter_points(inter, out)
    return out


def collect_points(parcels, zones, ndigits=4):
    """ყველა ნაკვეთი × ყველა ზონა — უნიკალური, საზღვრის გასწვრივ დალაგებული წერტილები.

    parcels/zones — shapely პოლიგონების იტერაცია. აბრუნებს [(x, y), …]-ს, სადაც
    ნაკვეთის საზღვარი კვეთს ზონის საზღვარს. დუბლები (ndigits-ზე დამრგვალებით)
    ერთდება; დალაგება — ნაკვეთების გაერთიანებული საზღვრის გასწვრივ (project),
    რომ ნუმერაცია ბუნებრივი იყოს.
    """
    from shapely.geometry import Point
    from shapely.ops import unary_union

    parcels = [p for p in parcels if p is not None and not p.is_empty]
    zones = [z for z in zones if z is not None and not z.is_empty]
    if not parcels or not zones:
        return []

    raw = []
    for p in parcels:
        for z in zones:
            raw.extend(crossing_points(p, z))

    # დუბლების მოცილება (დამრგვალებით), თანმიმდევრობის შენარჩუნებით
    seen = set()
    uniq = []
    for x, y in raw:
        key = (round(x, ndigits), round(y, ndigits))
        if key not in seen:
            seen.add(key)
            uniq.append((x, y))
    if not uniq:
        return []

    # დალაგება ნაკვეთების საზღვრის გასწვრივ
    try:
        merged = unary_union([p.boundary for p in parcels])
        uniq.sort(key=lambda xy: merged.project(Point(xy)))
    except Exception:                       # noqa: BLE001 — fallback: კოორდინატებით
        uniq.sort()
    return uniq
