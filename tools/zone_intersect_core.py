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


def _corridor_axis(zones):
    """დაცვის ზონის (დერეფნის) გრძელი ღერძის ერთეულოვანი მიმართულება (dx, dy).

    zone-ის გაერთიანების მინიმალური მობრუნებული მართკუთხედის გრძელი გვერდით.
    მიმართულებას ვასწორებთ ისე, რომ „ზემოდან ქვემოთ“ (ან ~ჰორიზონტ. დერეფანზე
    მარცხნიდან მარჯვნივ) წაიკითხოს — რომ ნუმერაცია სურათის ლოგიკას დაემთხვეს.
    """
    import math
    from shapely.ops import unary_union

    try:
        mrr = unary_union(zones).minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)[:4]
        e1 = math.hypot(cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e2 = math.hypot(cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        if e1 >= e2:
            dx, dy = cs[1][0] - cs[0][0], cs[1][1] - cs[0][1]
        else:
            dx, dy = cs[2][0] - cs[1][0], cs[2][1] - cs[1][1]
    except Exception:                       # noqa: BLE001
        return None
    n = math.hypot(dx, dy)
    if n == 0:
        return None
    dx, dy = dx / n, dy / n
    # ორიენტაცია: ვერტიკ./დახრილი დერეფანი → ზემოდან ქვევით (ღერძი ქვევით,
    # dy<0); ~ჰორიზონტ. → მარცხნიდან მარჯვნივ (dx>0)
    if abs(dy) >= abs(dx):
        if dy > 0:
            dx, dy = -dx, -dy
    else:
        if dx < 0:
            dx, dy = -dx, -dy
    return dx, dy


def collect_points(parcels, zones, ndigits=4):
    """ყველა ნაკვეთი × ყველა ზონა — უნიკალური, დერეფნის გასწვრივ დალაგებული წერტილები.

    parcels/zones — shapely პოლიგონების იტერაცია. აბრუნებს [(x, y), …]-ს, სადაც
    ნაკვეთის საზღვარი კვეთს ზონის საზღვარს. დუბლები (ndigits-ზე დამრგვალებით)
    ერთდება; **დალაგება — დაცვის ზონის (დერეფნის) გრძელი ღერძის გასწვრივ**, ზემოდან
    ქვევით — რომ ნუმერაცია (1, 2, 3, …) თანმიმდევრული და სტაბილური იყოს (არ იწყებოდეს
    ნაკვეთის შემთხვევითი წვეროდან). ღერძის ვერ დადგენისას — Y↓ შემდეგ X↑.
    """
    parcels = [p for p in parcels if p is not None and not p.is_empty]
    zones = [z for z in zones if z is not None and not z.is_empty]
    if not parcels or not zones:
        return []

    raw = []
    for p in parcels:
        for z in zones:
            raw.extend(crossing_points(p, z))

    # დუბლების მოცილება (დამრგვალებით)
    seen = set()
    uniq = []
    for x, y in raw:
        key = (round(x, ndigits), round(y, ndigits))
        if key not in seen:
            seen.add(key)
            uniq.append((x, y))
    if len(uniq) < 2:
        return uniq

    axis = _corridor_axis(zones)
    if axis is not None:
        dx, dy = axis
        # ღერძზე პროექცია; ტოლ პროექციაზე — მეორე ღერძით (მდგრადი წყვილებისთვის)
        uniq.sort(key=lambda xy: (xy[0] * dx + xy[1] * dy,
                                  xy[0] * -dy + xy[1] * dx))
    else:                                   # fallback — ზემოდან ქვევით, მერე მარცხნიდან
        uniq.sort(key=lambda xy: (-xy[1], xy[0]))
    return uniq
