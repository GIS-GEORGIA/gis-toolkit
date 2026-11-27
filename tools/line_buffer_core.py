# -*- coding: utf-8 -*-
"""ხაზოვანი შრიდან ბუფერების (დაცვის ზონების) აგება — სუფთა ლოგიკა.

სამი ტიპი, თითოეულში ცალკე ბუფერი ცალკე shapefile-ად. გამომავალი სახელი:
``<სახელი>_<N>.shp`` — N არის ამ სახელის ბოლო არსებული ინდექსის შემდეგი
(1, 2, 3…) სამიზნე საქაღალდეში.

ბუფერი მეტრებშია და გამოიყენება მხოლოდ UTM 37N/38N (EPSG:32637/32638); სხვა CRS-ს
(მათ შორის გეოგრაფიულ 4326-ს) მომხმარებლის თანხმობით გადავიყვანთ შრის
მდებარეობის შესაბამის ზონაში. აქ tkinter არაა.
UI: ``tools.line_buffer``.
"""

import os
import re

# ტიპი → [(მანძილი მეტრებში, გამომავალი სახელი), …]
BUFFER_TYPES = {
    "1": [(4, "gas_protection_zone_1"),
          (25, "gas_protection_zone_2"),
          (200, "gas_safety_zone_3"),
          (500, "gas_consultation_zone_4")],
    "2": [(4, "gas_protection_zone_1"),
          (10, "gas_protection_zone_2"),
          (500, "gas_consultation_zone_4")],
    "3": [(4, "gas_protection_zone_1"),
          (25, "gas_protection_zone_2"),
          (100, "gas_safety_zone_3")],
}


def next_index(folder, base):
    """შემდეგი ინდექსი ``base``-სთვის: ბოლო არსებული ``base_N``-ის შემდეგი.

    ინდექსი არ ივსება დარჩენილ „ხვრელებში“ (თუ _2 წაშლილია და _3 არსებობს,
    შემდეგი იქნება _4) — რომ ძველი ფაილის სახელი არასდროს გამოიყენო თავიდან."""
    pat = re.compile(re.escape(base) + r"_(\d+)\.shp$", re.IGNORECASE)
    n = 0
    try:
        for f in os.listdir(folder):
            m = pat.match(f)
            if m:
                n = max(n, int(m.group(1)))
    except OSError:
        pass
    return n + 1


def output_path(folder, base):
    return os.path.join(folder, "{}_{}.shp".format(base, next_index(folder, base)))


ALLOWED_EPSG = (32637, 32638)        # ვიყენებთ მხოლოდ WGS84 UTM 37N / 38N


def zone_epsg_for_lon(lon):
    """EPSG ზონის გრძედით: 42°E-მდე — 32637, მის შემდეგ — 32638."""
    return 32637 if lon < 42.0 else 32638


def _epsg_of(c):
    """pyproj CRS → EPSG კოდი; ESRI-სტილის WKT-ს (EPSG-ის გარეშე) ცნობს UTM ზონით."""
    epsg = c.to_epsg()
    if epsg is None and c.is_projected:
        try:
            if c.geodetic_crs.to_epsg() == 4326 and c.utm_zone in ("37N", "38N"):
                epsg = 32600 + int(c.utm_zone[:2])
        except Exception:                          # noqa: BLE001
            pass
    return epsg


def layer_center_lonlat(crs, bounds):
    """შრის ბოუნდინგ-ბოქსის ცენტრი (გრძედი, განედი), WGS84-ში."""
    import pyproj
    minx, miny, maxx, maxy = bounds
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    c = pyproj.CRS.from_user_input(crs)
    if c.is_geographic:
        return cx, cy
    return pyproj.Transformer.from_crs(c, 4326, always_xy=True).transform(cx, cy)


def plan_crs(crs, bounds):
    """რომელ CRS-ში ვაგებთ ბუფერს: აბრუნებს ``(epsg, საჭიროა_კონვერტაცია)``.

    - 32637 / 32638 → უცვლელი, კონვერტაცია არ სჭირდება;
    - სხვა ნებისმიერი (მათ შორის გეოგრაფიული 4326) → შრის მდებარეობის (გრძედის)
      შესაბამისი ზონა, კონვერტაცია საჭიროა — UI მომხმარებელს ჯერ ეკითხება;
    - CRS არ აქვს → ``ValueError`` (ზონას ვერ ვხვდებით, ვერაფერს ვივარაუდებთ)."""
    import pyproj
    if crs is None:
        raise ValueError("no_crs")
    c = pyproj.CRS.from_user_input(crs)
    epsg = _epsg_of(c)
    if epsg in ALLOWED_EPSG:
        return epsg, False
    lon, _lat = layer_center_lonlat(c, bounds)
    return zone_epsg_for_lon(lon), True


def build_buffer(geoms, distance):
    """ყველა ხაზის გაერთიანება და ერთიანი ბუფერი ``distance`` მეტრზე."""
    from shapely.ops import unary_union
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return None
    return unary_union(geoms).buffer(distance)


# ---------------------------------------------------------------------------
# GUI-ს გარეშე სამუშაო ფუნქციები (ორივე ინტერფეისისთვის: V2 გვერდი იყენებს)
# ---------------------------------------------------------------------------
class Cancelled(Exception):
    """მომხმარებელმა გააუქმა (ბუფერების აგებისას)."""


def scan_line_shapefiles(folder):
    """``{ფაილის სახელი: სრული გზა}`` — საქაღალდეში არსებული ხაზოვანი shapefile-ები."""
    from tools.platform_utils import files_with_suffix
    out = {}
    if not folder or not os.path.isdir(folder):
        return out
    import pyogrio
    for shp in files_with_suffix(folder, ".shp"):          # .SHP too (Linux is case-sensitive)
        try:
            gtype = str(pyogrio.read_info(shp).get("geometry_type") or "")
        except Exception:                          # noqa: BLE001 - წაუკითხავი ფაილი სხვას არ აჩერებს
            continue
        if "Line" in gtype:
            out[os.path.basename(shp)] = shp
    return out


def plan_layer(shp):
    """რა გვჭირდება ამ შრისთვის: ``{"epsg", "convert", "current", "zone"}``.

    ``ValueError("no_crs")`` — შრეს CRS არ აქვს (არაფერს ვივარაუდებთ)."""
    import pyogrio
    import pyproj
    info = pyogrio.read_info(shp)
    crs = info.get("crs")
    epsg, convert = plan_crs(crs, info["total_bounds"])
    cur = ""
    if crs:
        c = pyproj.CRS.from_user_input(crs)
        cur = "EPSG:{}".format(c.to_epsg()) if c.to_epsg() else c.name
    return {"epsg": epsg, "convert": convert, "current": cur, "zone": epsg - 32600}


def build_buffers(shp, out_dir, zones, target_epsg, log=None, progress=None, cancel=None):
    """ბუფერების აგება: ``zones`` = [(მანძილი_მ, სახელი), …]. აბრუნებს ``[(მანძილი, გზა), …]``.

    - წყარო არასოდეს იცვლება; ყოველი ბუფერი ახალ ფაილში იწერება (``output_path`` — ინდექსი იზრდება);
    - CRS-ის შეცვლა (თუ საჭიროა) ლოგში ჩანს; CRS-ის არქონა → ``ValueError("no_crs")``;
    - ``cancel()`` → ``Cancelled`` ზონებს შორის."""
    import geopandas as gpd

    log = log or (lambda _m: None)
    progress = progress or (lambda _i, _n: None)
    cancel = cancel or (lambda: False)
    gdf = gpd.read_file(shp)
    if gdf.crs is None:
        raise ValueError("no_crs")
    if gdf.crs.to_epsg() != target_epsg:
        from tools import crs_manager
        gdf, rep = crs_manager.reproject_gdf(gdf, target_epsg)
        log("reprojected {} -> EPSG:{}  ({}; accuracy {})".format(
            rep.original_crs.label(), target_epsg, rep.method, rep.accuracy or "n/a"))
        for w in rep.warnings:
            log("WARNING: " + w)
    geoms = [g for g in gdf.geometry if g is not None and not g.is_empty]
    if not geoms:
        raise ValueError("no_geom")
    written = []
    for i, (dist, name) in enumerate(zones, 1):
        if cancel():
            raise Cancelled()
        geom = build_buffer(geoms, dist)
        if cancel():                    # the buffer of a long line can take a while - check before writing
            raise Cancelled()
        path = output_path(out_dir, name)
        from tools.safe_output import staged_shapefile
        with staged_shapefile(path) as tmp:   # a failed write never leaves a half shapefile behind
            gpd.GeoDataFrame([{"Zone": name, "Dist_m": dist}], geometry=[geom], crs=gdf.crs).to_file(
                tmp, driver="ESRI Shapefile", encoding="utf-8")
        written.append((dist, path))
        log("{} m -> {}".format(dist, path))
        progress(i, len(zones))
    return written
