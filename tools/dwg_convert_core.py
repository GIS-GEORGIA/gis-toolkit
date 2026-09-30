# -*- coding: utf-8 -*-
"""DWG/DXF → SHP/GPKG/GDB კონვერტერი — სუფთა ლოგიკა (GDAL/pyogrio-ით, ღია კოდით).

arcpy არაა საჭირო: GDAL-ის DXF დრაივერი (ღიაა, ყოველთვის ჩართული) კითხულობს
.dxf-ს პირდაპირ; DWG-ს სჭირდება GDAL-ის CAD დრაივერი (ODA/Teigha ბიბლიოთეკით
აწყობილი — ჩვეულებრივ QGIS-ში/OSGeo4W-ში არის, „მარტივ“ GDAL-ის ბილდებში
ლიცენზიის გამო ხშირად არა). თუ დრაივერი არ არსებობს, კონკრეტული DWG
გამოტოვდება და ცხადად ჩაიწერება ლოგში — დანარჩენი ფაილები გრძელდება.

**GPKG** მრავალშრიანი კონტეინერია და **შერეული გეომეტრიის ტიპსაც** იტანს ერთ
შრეში (`GEOMETRY`, generic) — ამიტომ თითო წყარო-შრე პირდაპირ (ატრიბუტებით) ერთ
გამომავალ შრედ გადადის. **SHP და OpenFileGDB** კი ერთ შრეში მხოლოდ ერთგვაროვან
გეომეტრიას იტანენ (გადამოწმებულია: შერეულზე OpenFileGDB-იც „Unsupported geometry
type“-ს იძლევა) — ამიტომ საჭიროებისას (შერეული ტიპის წყარო-შრე, რაც DXF-ში
ხშირია — ერთ „ლეიერზე“ წერტილიც, ხაზიც და პოლიგონიც შეიძლება იყოს) წერტილი/
ხაზი/პოლიგონი ცალ-ცალკე გამომავალ შრედ/ფაილად იყოფა (`<layer>_point` და ა.შ.).

მძიმე პაკეტები (geopandas/pyogrio/shapely) ფუნქციების შიგნით იტვირთება — მოდული
მათ გარეშეც იმპორტადია (ტესტი მხოლოდ სუფთა დამხმარეებს ამოწმებს).
"""

import os
import re
import shutil

from tools.geom_collect_core import (
    iter_geometry_files, classify_geom_type, _to_multi,
)

SOURCE_EXT = (".dxf", ".dwg")

# გამომავალი ფორმატები — (key, GDAL driver, გაფართოება)
FORMATS = {
    "shp":  ("ESRI Shapefile", ".shp"),
    "gpkg": ("GPKG", ".gpkg"),
    "gdb":  ("OpenFileGDB", ".gdb"),
}


def sanitize(text):
    """ფაილის/შრის უსაფრთხო სახელი — არა-ალფანუმერული → „_“."""
    s = re.sub(r"[^0-9A-Za-z._-]+", "_", str(text or "")).strip("_")
    return s or "layer"


def _read_layers(path):
    """ფაილის ყველა შრის (name, GeoDataFrame) სია. ცარიელი — თუ წაუკითხავია."""
    import pyogrio
    out = []
    layers = [row[0] for row in pyogrio.list_layers(path)]
    for lyr in layers:
        gdf = pyogrio.read_dataframe(path, layer=lyr)
        out.append((lyr, gdf))
    return out


def _normalize_crs(gdf, target_epsg):
    if not target_epsg:
        return gdf
    target = "EPSG:{}".format(int(target_epsg))
    if gdf.crs is None:
        return gdf.set_crs(target, allow_override=True)
    if str(gdf.crs) != target:
        return gdf.to_crs(target)
    return gdf


def _split_by_geom_type(gdf):
    """{'point'|'line'|'polygon': GeoDataFrame} — ატრიბუტები შენარჩუნებული,
    გეომეტრია Multi-ტიპად ნორმალიზებული (ერთგვაროვნებისთვის SHP-ში)."""
    import geopandas as gpd

    result = {}
    if gdf is None or len(gdf) == 0 or gdf.geometry.name not in gdf:
        return result
    g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if len(g) == 0:
        return result
    gt = g.geometry.geom_type
    for bucket in ("point", "line", "polygon"):
        types = {t for t in gt.unique() if classify_geom_type(t) == bucket}
        if not types:
            continue
        sub = g[gt.isin(types)].copy()
        sub[sub.geometry.name] = sub.geometry.apply(_to_multi)
        result[bucket] = gpd.GeoDataFrame(sub, geometry=sub.geometry.name,
                                          crs=g.crs)
    return result


def _clear_output(out_path, is_dir):
    """ძველი გამომავალის მოცილება ხელახლა ჩაწერამდე (gdb — საქაღალდეა)."""
    if is_dir:
        if os.path.isdir(out_path):
            shutil.rmtree(out_path)
    elif os.path.exists(out_path):
        os.remove(out_path)


def convert_file(path, out_dir, fmt, target_epsg=None, log=None):
    """ერთი DXF/DWG (ან ნებისმიერი GDAL-ვექტორის) კონვერტაცია ``fmt``-ში.

    fmt — 'shp' | 'gpkg' | 'gdb'. აბრუნებს dict-ს:
        {source, out_path, layers: [(name, feature_count), …], error}
    შეცდომისას (მაგ. DWG დრაივერი არ არსებობს) — ``error`` შეივსება, ``layers`` ცარიელი.
    """
    log = log or (lambda _m: None)
    driver, ext = FORMATS[fmt]
    base = sanitize(os.path.splitext(os.path.basename(path))[0])
    os.makedirs(out_dir, exist_ok=True)

    try:
        source_layers = _read_layers(path)
    except Exception as e:                  # noqa: BLE001 — არარსებული დრაივერი და ა.შ.
        return {"source": path, "out_path": None, "layers": [], "error": str(e)}

    written = []
    if fmt == "shp":
        # ერთი ფაილი = ერთი შრე/ტიპი → ცალკე საქაღალდე ამ წყაროსთვის
        out_root = os.path.join(out_dir, base)
        os.makedirs(out_root, exist_ok=True)
        for lyr_name, gdf in source_layers:
            buckets = _split_by_geom_type(gdf)
            multi = len(buckets) > 1
            for bucket, sub in buckets.items():
                sub = _normalize_crs(sub, target_epsg)
                name = sanitize(lyr_name)
                if multi:
                    name += "_" + bucket
                out_path = os.path.join(out_root, name + ".shp")
                _clear_output(out_path, is_dir=False)
                sub.to_file(out_path, driver=driver, encoding="utf-8")
                written.append((name, len(sub)))
                log("  ✓ {}: {}".format(name, len(sub)))
        return {"source": path, "out_path": out_root, "layers": written,
                "error": None}

    # gdb — OpenFileGDB-ს, SHP-ის მსგავსად, ერთგვაროვანი გეომეტრია სჭირდება
    # თითო შრეში (შერეულზე „Unsupported geometry type“-ს იძლევა) — იყოფა.
    # gpkg — მრავალშრიანი, შერეული გეომეტრიაც დაიტევს — პირდაპირ იწერება.
    out_path = os.path.join(out_dir, base + ext)
    _clear_output(out_path, is_dir=(fmt == "gdb"))
    first = True
    for lyr_name, gdf in source_layers:
        if gdf is None or len(gdf) == 0:
            continue
        if fmt == "gdb":
            buckets = _split_by_geom_type(gdf)
            multi = len(buckets) > 1
            parts = [(sanitize(lyr_name) + ("_" + b if multi else ""), sub)
                     for b, sub in buckets.items()]
        else:
            parts = [(sanitize(lyr_name), gdf)]
        for name, sub in parts:
            sub = _normalize_crs(sub, target_epsg)
            sub.to_file(out_path, layer=name, driver=driver,
                       mode="w" if first else "a")
            first = False
            written.append((name, len(sub)))
            log("  ✓ {}: {}".format(name, len(sub)))
    return {"source": path, "out_path": out_path if written else None,
            "layers": written, "error": None}


def convert_batch(files, out_dir, fmt, target_epsg=None,
                  log=None, progress=None, cancel=None):
    """რამდენიმე ფაილის კონვერტაცია. აბრუნებს dict-ს: files_ok, files_skipped,
    files_empty, results ([convert_file-ის შედეგი, …]), cancelled."""
    log = log or (lambda _m: None)
    progress = progress or (lambda _i, _n: None)
    cancel = cancel or (lambda: False)

    results = []
    ok = skipped = empty = 0
    total = len(files)
    for i, path in enumerate(files, start=1):
        if cancel():
            return {"cancelled": True, "files_ok": ok, "files_skipped": skipped,
                    "files_empty": empty, "results": results}
        name = os.path.basename(path)
        log(name)
        r = convert_file(path, out_dir, fmt, target_epsg, log=log)
        results.append(r)
        if r["error"]:
            skipped += 1
            log("  ✗ {}".format(r["error"].splitlines()[0]))
        elif not r["layers"]:
            empty += 1
            log("  • no geometry")
        else:
            ok += 1
        progress(i, total)
    return {"cancelled": False, "files_ok": ok, "files_skipped": skipped,
            "files_empty": empty, "results": results}


def iter_source_files(folder, recursive=True, exts=SOURCE_EXT):
    """საქაღალდის ხეში DXF/DWG ფაილები (ან მითითებული გაფართოებები)."""
    return iter_geometry_files(folder, exts, recursive)
