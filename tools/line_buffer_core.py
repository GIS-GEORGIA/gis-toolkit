# -*- coding: utf-8 -*-
"""ხაზოვანი შრიდან ბუფერების (დაცვის ზონების) აგება — სუფთა ლოგიკა.

სამი ტიპი, თითოეულში ცალკე ბუფერი ცალკე shapefile-ად. გამომავალი სახელი:
``<სახელი>_<N>.shp`` — N არის პირველი თავისუფალი ინდექსი (1, 2, 3…) ამ
სახელისთვის სამიზნე საქაღალდეში.

ბუფერი მეტრებშია, ამიტომ შრე უნდა იყოს მეტრულ (პროექციულ) CRS-ში; გეოგრაფიულს
UTM-ზე გადავიყვანთ (ცენტროიდის გრძედის მიხედვით). აქ tkinter არაა.
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


def metric_crs(crs, lon_lat_center):
    """მეტრულ CRS-ში მუშაობისთვის: აბრუნებს (crs, გადასაყვანია_თუ_არა).

    - პროექციული CRS მეტრებით → უცვლელი;
    - გეოგრაფიული ან არამეტრული → WGS84 UTM (ცენტროიდის გრძედის ზონა);
    - CRS არ აქვს → ``ValueError``."""
    import pyproj
    if crs is None:
        raise ValueError("no_crs")
    c = pyproj.CRS.from_user_input(crs)
    if c.is_projected:
        try:
            unit = (c.axis_info[0].unit_name or "").lower()
        except Exception:                          # noqa: BLE001
            unit = ""
        if unit in ("metre", "meter"):
            return c, False
    lon, _lat = lon_lat_center
    zone = int((lon + 180.0) // 6.0) + 1
    zone = min(max(zone, 1), 60)
    return pyproj.CRS.from_epsg(32600 + zone), True


def build_buffer(geoms, distance):
    """ყველა ხაზის გაერთიანება და ერთიანი ბუფერი ``distance`` მეტრზე."""
    from shapely.ops import unary_union
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return None
    return unary_union(geoms).buffer(distance)
