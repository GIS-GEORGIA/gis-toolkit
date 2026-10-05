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


def _as_curve(geom):
    """პოლიგონი → საზღვარი (ხაზი); ხაზი/სხვა — უცვლელი.

    ასე ერთი და იგივე ლოგიკა მუშაობს პოლიგონ×პოლიგონ (ნაკვეთი × დაცვის ზონა),
    ხაზი×ხაზ (გაზსადენი × კომუნიკაცია) და შერეულ შემთხვევებზეც.
    """
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom.boundary
    return geom


def crossing_points(a, b):
    """ორი ობიექტის კვეთის წერტილები [(x, y), …].

    პოლიგონები საზღვრად გადაიქცევა; ხაზები თავად რჩება — ამიტომ იჭერს
    როგორც საზღვრების, ისე ხაზების კვეთას.
    """
    out = []
    try:
        inter = _as_curve(a).intersection(_as_curve(b))
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


def _line_parts(geom):
    """გეომეტრიის (საზღვრის/ხაზის) შემადგენელი კოორდინატთა მიმდევრობები."""
    if geom is None or geom.is_empty:
        return []
    gt = geom.geom_type
    if gt in ("LineString", "LinearRing"):
        return [list(geom.coords)]
    if hasattr(geom, "geoms"):
        out = []
        for g in geom.geoms:
            out.extend(_line_parts(g))
        return out
    return []


def _nearest_direction(curves, x, y):
    """(x, y)-თან უახლოესი სეგმენტის მიმართულება (dx, dy) მოცემულ ხაზებს შორის."""
    best, best_d2 = None, None
    for geom in curves:
        for part in _line_parts(_as_curve(geom)):
            for (x1, y1), (x2, y2) in zip(part, part[1:]):
                sx, sy = x2 - x1, y2 - y1
                L2 = sx * sx + sy * sy
                if L2 == 0:
                    continue
                t = max(0.0, min(1.0, ((x - x1) * sx + (y - y1) * sy) / L2))
                px, py = x1 + t * sx, y1 + t * sy
                d2 = (x - px) ** 2 + (y - py) ** 2
                if best_d2 is None or d2 < best_d2:
                    best_d2, best = d2, (sx, sy)
    return best


def crossing_angle(pt, curves_a, curves_b):
    """ორი ხაზის მახვილი გადაკვეთის კუთხე (გრადუსი, 0–90) წერტილში ``pt``.

    თითო მხარეს ვიღებთ წერტილთან უახლოეს სეგმენტს. ``None`` — თუ ვერ დადგინდა."""
    import math
    da = _nearest_direction(curves_a, pt[0], pt[1])
    db = _nearest_direction(curves_b, pt[0], pt[1])
    if da is None or db is None:
        return None
    ang = abs(math.degrees(math.atan2(da[0] * db[1] - da[1] * db[0],
                                      da[0] * db[0] + da[1] * db[1])))
    return min(ang, 180.0 - ang)


def shallow_crossings(parcels, zones, points, threshold_deg=15.0):
    """წერტილები, სადაც გადაკვეთის კუთხე ``threshold_deg``-ზე ნაკლებია.

    აბრუნებს ``[(ნომერი_1დან, კუთხე°), …]``-ს ``points``-ის რიგის მიხედვით.
    ასეთ ადგილას ხაზში პატარა გვერდითი სხვაობაც (ჯვარედინი ხაზის სხვა ვერსია,
    ციფრული ცდომილება) წერტილს ხაზის გასწვრივ ~1/tan(კუთხე)-ჯერ გადაწევს."""
    parcels = [p for p in parcels if p is not None and not p.is_empty]
    zones = [z for z in zones if z is not None and not z.is_empty]
    out = []
    for i, pt in enumerate(points, start=1):
        ang = crossing_angle(pt, parcels, zones)
        if ang is not None and ang < threshold_deg:
            out.append((i, ang))
    return out


def clip_areas(parcels, zones):
    """ნაკვეთის საერთო ფართი, ზონასთან გადაკვეთილი („მოჭრილი“) ნაწილი და დარჩენილი ნაწილი.

    parcels/zones — shapely პოლიგონების იტერაცია, ერთსა და იმავე მეტრულ (UTM) CRS-ში —
    ასე ``.area`` პირდაპირ კვ.მ-შია, დამატებითი გადაყვანის გარეშე. აბრუნებს dict-ს:

    - ``parcel``/``cut``/``remainder`` — გაერთიანებული ნაკვეთის, ნაკვეთი∩ზონის
      („მოჭრილი“) და ნაკვეთი−ზონის („დარჩენილი“) shapely გეომეტრიები (ან ``None``);
    - ``parcel_area``/``cut_area``/``remainder_area`` — შესაბამისი ფართები (float, კვ.მ).
    """
    from shapely.ops import unary_union

    parcels = [p for p in parcels if p is not None and not p.is_empty]
    zones = [z for z in zones if z is not None and not z.is_empty]
    parcel_u = unary_union(parcels) if parcels else None
    if parcel_u is None or parcel_u.is_empty:
        return {"parcel": None, "cut": None, "remainder": None,
                "parcel_area": 0.0, "cut_area": 0.0, "remainder_area": 0.0}

    zone_u = unary_union(zones) if zones else None
    if zone_u is None or zone_u.is_empty:
        cut, remainder = None, parcel_u
    else:
        cut = parcel_u.intersection(zone_u)
        remainder = parcel_u.difference(zone_u)

    cut_area = cut.area if cut is not None and not cut.is_empty else 0.0
    remainder_area = remainder.area if remainder is not None and not remainder.is_empty else 0.0
    return {
        "parcel": parcel_u, "cut": cut, "remainder": remainder,
        "parcel_area": parcel_u.area,
        "cut_area": cut_area,
        "remainder_area": remainder_area,
    }


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
