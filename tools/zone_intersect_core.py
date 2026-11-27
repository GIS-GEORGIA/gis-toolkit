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
            out.append((cs[0][0], cs[0][1]))             # Z-ს ვაგდებთ
            out.append((cs[-1][0], cs[-1][1]))
    elif gt == "MultiLineString":
        for g in geom.geoms:
            cs = list(g.coords)
            if cs:
                out.append((cs[0][0], cs[0][1]))
                out.append((cs[-1][0], cs[-1][1]))
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
        return [[(c[0], c[1]) for c in geom.coords]]     # Z (3D ხაზი) იგნორდება
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


def require_metric_crs(crs):
    """Areas are reported in m2 - refuse a geographic CRS (degrees would be labelled as m2).
    ``None`` (no CRS info) is allowed for backward compatibility: the units cannot be known."""
    if crs is None:
        return
    from tools.crs_manager import describe
    info = describe(crs)
    if info.is_geographic:
        raise ValueError("The parcel layer is in a geographic CRS ({}, units: {}). Areas and distances must "
                         "be computed in a projected metric CRS (e.g. EPSG:32637 / EPSG:32638) - reproject "
                         "the layers first.".format(info.label(), info.unit))


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


SHALLOW_ANGLE_DEG = 15.0
DEFAULT_OUT_NAME = "Gas_Pipe_ProtZone_Crossing"
DEFAULT_LINE_NAME = "Line_Crossing"
DEFAULT_CUT_NAME = "Parcel_clipped_part"
DEFAULT_REMAIN_NAME = "Parcel_remaining_part"
_AUTO_FIELDS_EXACT = ("fid", "objectid", "oid", "gid", "id", "code", "zona", "zone", "ზონა")
_AUTO_FIELDS_SUBSTR = ("fid", "objectid", "id", "zon", "type", "code", "name")


def auto_zone_field(fields):
    """Zone field auto-pick: id/FID-like exact name → substring → the first field."""
    low = {f.lower(): f for f in fields}
    for pref in _AUTO_FIELDS_EXACT:
        if pref in low:
            return low[pref]
    for sub in _AUTO_FIELDS_SUBSTR:
        for f in fields:
            if sub in f.lower():
                return f
    return fields[0] if fields else ""


def read_zone_meta(path):
    """{field: sorted distinct non-empty values} of a layer's attributes; plus a pseudo field ``FID`` (row index)
    for layers with 1..1000 features, so a layer without attributes can still be filtered to one feature."""
    import pyogrio
    df = pyogrio.read_dataframe(path, read_geometry=False)
    meta = {}
    for col in df.columns:
        try:
            vals = sorted({str(v) for v in df[col].tolist() if v is not None and str(v).strip() != ""})
        except Exception:                   # noqa: BLE001
            vals = []
        if vals:
            meta[str(col)] = vals
    if 0 < len(df) <= 1000:
        meta["FID"] = [str(i) for i in range(len(df))]
    return meta


def compute(parcel_path, zone_path, field=None, value=None, threshold_deg=SHALLOW_ANGLE_DEG):
    """Reads both layers, filters the zone layer (attribute ``field == value``, or ``FID`` = row index), brings the
    zones into the parcel CRS and returns {points, crs, areas, shallow}. A geographic parcel CRS is refused."""
    import geopandas as gpd
    pgdf = gpd.read_file(parcel_path)
    zgdf = gpd.read_file(zone_path)
    if value is not None and field:
        if field in zgdf.columns:
            zgdf = zgdf[zgdf[field].astype(str) == str(value)]
        elif field == "FID":
            try:
                i = int(value)
                if 0 <= i < len(zgdf):
                    zgdf = zgdf.iloc[[i]]
            except (ValueError, TypeError):
                pass
    target_crs = pgdf.crs
    require_metric_crs(target_crs)
    if target_crs is not None and zgdf.crs is not None and zgdf.crs != target_crs:
        zgdf = zgdf.to_crs(target_crs)
    parcels = [g for g in pgdf.geometry if g is not None]
    zones = [g for g in zgdf.geometry if g is not None]
    pts = collect_points(parcels, zones)
    return {"points": pts, "crs": target_crs, "areas": clip_areas(parcels, zones),
            "shallow": shallow_crossings(parcels, zones, pts, threshold_deg)}


def sanitize(text, fallback="zone"):
    import re
    s = re.sub(r"[^0-9A-Za-z._-]+", "_", str(text or "")).strip("_")
    return s or fallback


def zone_num_from_crs(crs):
    """CRS → UTM zone number as text ('37', '38', …) or '' — used in output names."""
    try:
        epsg = crs.to_epsg() if crs is not None else None
    except Exception:                       # noqa: BLE001
        epsg = None
    if epsg and 32601 <= epsg <= 32660:
        return str(epsg - 32600)
    if epsg and 32701 <= epsg <= 32760:
        return str(epsg - 32700)
    return ""


def next_free_path(out, base):
    """out/base_<N>.shp with the first free N (1, 2, 3 …) — an existing file is never overwritten."""
    import os
    n = 1
    while True:
        cand = os.path.join(out, "{}_{}.shp".format(base, n))
        if not os.path.exists(cand):
            return cand
        n += 1


def output_base(name, default, crs):
    """<sanitized name><UTM zone> — e.g. Gas_Pipe_ProtZone_Crossing38."""
    base = sanitize(name.strip() if name else "", "") or default
    znum = zone_num_from_crs(crs)
    if znum and not base.endswith(znum):
        base += znum
    return base


def write_points(pts, crs, out_path):
    """Point shapefile with N / X / Y attributes (numbering = order along the zone corridor)."""
    import geopandas as gpd
    from shapely.geometry import Point
    rows = [{"N": i, "X": round(x, 3), "Y": round(y, 3)} for i, (x, y) in enumerate(pts, start=1)]
    gpd.GeoDataFrame(rows, geometry=[Point(x, y) for x, y in pts], crs=crs).to_file(
        out_path, driver="ESRI Shapefile", encoding="utf-8")


def piece_path(out, name):
    """Path for a saved piece: the chosen name, or the next free ``_<N>`` if it is taken (no double ``_1_1``)."""
    import os
    import re
    chosen = sanitize(name.strip())
    path = os.path.join(out, chosen + ".shp")
    if os.path.exists(path):
        path = next_free_path(out, re.sub(r"_\d+$", "", chosen) or chosen)
    return path


def write_piece(geom, crs, out_path):
    """A polygon piece (cut-out / remainder) as its own shapefile, one row per part with ``Area_m2``."""
    import geopandas as gpd
    parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    parts = [g for g in parts if g.area > 0]
    rows = [{"N": i, "Area_m2": round(g.area, 5)} for i, g in enumerate(parts, start=1)]
    gpd.GeoDataFrame(rows, geometry=parts, crs=crs).to_file(out_path, driver="ESRI Shapefile", encoding="utf-8")


def shallow_summary(shallow, threshold_deg=SHALLOW_ANGLE_DEG):
    """{nums, deg, lim, k} for the shallow-crossing warning (k = along-line shift per unit of side offset)."""
    import math
    amin = min(a for _n, a in shallow)
    return {"nums": ", ".join(str(n) for n, _a in shallow), "deg": round(amin, 1), "lim": int(threshold_deg),
            "k": round(1.0 / math.tan(math.radians(max(amin, 0.5))), 1)}


# ---------------------------------------------------------------- ready-made template files (copy by zone)
def template_files(src_dir, base):
    import glob
    import os
    return glob.glob(os.path.join(src_dir or "", base + ".*"))


def next_template_index(dest, base):
    import os
    import re
    pat = re.compile(re.escape(base) + r"_(\d+)(?:\.|$)", re.IGNORECASE)
    n = 0
    try:
        for f in os.listdir(dest):
            m = pat.match(f)
            if m:
                n = max(n, int(m.group(1)))
    except OSError:
        pass
    return n + 1


def copy_template(src_dir, base, dest, log=None):
    """Copies every ``base.*`` file to ``dest`` as ``base_<next N>.*``. Returns (new_base, files_copied)."""
    import os
    import shutil
    log = log or (lambda m: None)
    files = template_files(src_dir, base)
    if not files:
        return None, 0
    new_base = "{}_{}".format(base, next_template_index(dest, base))
    n = 0
    for src in files:
        rest = os.path.basename(src)[len(base):]
        dst = os.path.join(dest, new_base + rest)
        if os.path.exists(dst):                 # never overwrite
            log("✗ {}{}: exists".format(new_base, rest))
            continue
        try:
            shutil.copy2(src, dst)
            n += 1
        except OSError as e:
            log("✗ {}{}: {}".format(new_base, rest, e))
    return new_base, n


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
