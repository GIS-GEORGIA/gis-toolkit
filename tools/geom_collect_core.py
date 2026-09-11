# -*- coding: utf-8 -*-
"""გეომეტრიების შეგროვება — SHP/DXF/DWG ხიდან ერთ GeoPackage-ში (სუფთა ლოგიკა).

საქაღალდის ხეში პოულობს ყველა ``.shp``/``.dxf``/``.dwg`` ფაილს, კითხულობს
გეომეტრიებს და აჯგუფებს **სამ შრედ**: წერტილები, ხაზები, პოლიგონები — თითო
ცალკე შრედ ერთ GeoPackage-ში.

მძიმე პაკეტები (geopandas/pyogrio/shapely) „რბილად“ იმპორტდება — მოდული მათ
გარეშეც იმპორტადია (ტესტში/CI-ში სუფთა დამხმარეები მაინც მოწმდება). DWG-ის
წაკითხვა დამოკიდებულია GDAL-ის CAD დრაივერზე; თუ არაა, ფაილი გამოტოვდება.
"""

import os

# ნაგულისხმევად მონიშნული ფორმატები (თავდაპირველი მოთხოვნა)
GEOM_EXT = (".shp", ".dxf", ".dwg")

# დირექტორია-დატასეტები (ფაილი კი არა, საქაღალდეა) — მათში არ ვიძვრებით
DIR_DATASETS = (".gdb",)

# GDAL-ის ვექტორული ფორმატები გაფართოებით — UI-ის მოსანიშნი სია.
# (label, (გაფართოებები…)). read/collect ისედაც ნებისმიერ GDAL ფორმატს კითხულობს;
# ეს სია მხოლოდ ფაილების პოვნის ფილტრია. სიაში რომ არ იყოს — „სხვა“ ველი არსებობს.
VECTOR_FORMATS = [
    ("ESRI Shapefile (.shp)", (".shp",)),
    ("AutoCAD DXF (.dxf)", (".dxf",)),
    ("AutoCAD DWG (.dwg)", (".dwg",)),
    ("GeoPackage (.gpkg)", (".gpkg",)),
    ("GeoJSON (.geojson/.json)", (".geojson", ".json")),
    ("KML / KMZ (.kml/.kmz)", (".kml", ".kmz")),
    ("GML (.gml)", (".gml",)),
    ("GPX (.gpx)", (".gpx",)),
    ("MapInfo (.tab/.mif)", (".tab", ".mif")),
    ("FlatGeobuf (.fgb)", (".fgb",)),
    ("SpatiaLite / SQLite (.sqlite/.db)", (".sqlite", ".db")),
    ("GeoParquet (.parquet)", (".parquet",)),
    ("Microstation DGN (.dgn)", (".dgn",)),
    ("File Geodatabase (.gdb)", (".gdb",)),
    ("Personal Geodatabase (.mdb)", (".mdb",)),
    ("OpenStreetMap (.osm/.pbf)", (".osm", ".pbf")),
    ("S-57 (.000)", (".000",)),
    ("CSV (.csv)", (".csv",)),
]


def normalize_exts(text):
    """მძიმით/სფეისით გამოყოფილი გაფართოებები → ('.ext', …) (lower, უნიკ.)."""
    out = []
    for part in str(text or "").replace(",", " ").split():
        e = part.strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = "." + e
        if e not in out:
            out.append(e)
    return tuple(out)

# geopandas/shapely-ის geom_type სტრიქონები → სამი კალათა
POINT_TYPES = {"Point", "MultiPoint"}
LINE_TYPES = {"LineString", "MultiLineString", "LinearRing"}
POLYGON_TYPES = {"Polygon", "MultiPolygon"}

# GeoPackage-ის შრეების სახელები (ascii — GIS-თან თავსებადობისთვის)
LAYER_POINTS = "points"
LAYER_LINES = "lines"
LAYER_POLYGONS = "polygons"


def classify_geom_type(name):
    """geom_type-ის სახელი → 'point' | 'line' | 'polygon' | None."""
    if name in POINT_TYPES:
        return "point"
    if name in LINE_TYPES:
        return "line"
    if name in POLYGON_TYPES:
        return "polygon"
    return None


def iter_geometry_files(folder, exts=GEOM_EXT, recursive=True):
    """საქაღალდის ხეში მითითებული გაფართოების ვექტორული ფაილები (დალაგებული).

    ``exts`` — გაფართოებების tuple/set (მაგ. ('.shp', '.gpkg')). დირექტორია-
    დატასეტები (``.gdb``) საქაღალდედ იძებნება და მათში აღარ ვიძვრებით.
    დროებითი (``~$``) და ფარული ფაილები/საქაღალდეები გამოტოვდება.
    """
    exts = tuple(e.lower() for e in exts)
    file_exts = tuple(e for e in exts if e not in DIR_DATASETS)
    dir_exts = tuple(e for e in exts if e in DIR_DATASETS)
    found = []
    for root, dirs, names in os.walk(folder):
        keep = []
        for d in sorted(dirs):
            if d.startswith((".", "~$")):
                continue
            low = d.lower()
            if dir_exts and low.endswith(dir_exts):
                found.append(os.path.join(root, d))    # დატასეტი — არ ჩავიხედოთ
            else:
                keep.append(d)
        dirs[:] = keep
        for name in sorted(names):
            if name.startswith("~$"):
                continue
            if file_exts and name.lower().endswith(file_exts):
                found.append(os.path.join(root, name))
        if not recursive:
            break
    return sorted(found)


def _to_multi(geom):
    """ერთეული გეომეტრია → შესაბამისი Multi-ტიპი (შრეში ერთგვაროვნებისთვის)."""
    from shapely.geometry import MultiPoint, MultiLineString, MultiPolygon
    gt = geom.geom_type
    if gt == "Point":
        return MultiPoint([geom])
    if gt == "LineString":
        return MultiLineString([geom])
    if gt == "LinearRing":
        return MultiLineString([geom])
    if gt == "Polygon":
        return MultiPolygon([geom])
    return geom                        # Multi* — უცვლელი


def _read_layers(path):
    """ფაილის ყველა შრის (name, GeoDataFrame) — GDAL/pyogrio-ით."""
    import pyogrio
    out = []
    try:
        layers = [row[0] for row in pyogrio.list_layers(path)]
    except Exception:                  # noqa: BLE001 — ვცადოთ ერთი უსახელო წაკითხვა
        layers = [None]
    for lyr in layers:
        gdf = pyogrio.read_dataframe(path, layer=lyr) if lyr is not None \
            else pyogrio.read_dataframe(path)
        out.append((lyr, gdf))
    return out


def _bucketize(gdf, src_file, src_layer):
    """GeoDataFrame → {'point'|'line'|'polygon': GeoDataFrame} (მინიმ. ველებით).

    თითო რიგი კლასიფიცირდება რეალური geom_type-ით; ინახება მხოლოდ src_file /
    src_layer / src_type + გეომეტრია, ხოლო გეომეტრია Multi-დ ნორმალდება.
    """
    import geopandas as gpd

    result = {}
    if gdf is None or len(gdf) == 0 or gdf.geometry.name not in gdf:
        return result
    g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if len(g) == 0:
        return result
    gt = g.geom_type
    for bucket, types in (("point", POINT_TYPES), ("line", LINE_TYPES),
                          ("polygon", POLYGON_TYPES)):
        sub = g[gt.isin(types)]
        if len(sub) == 0:
            continue
        geoms = sub.geometry.apply(_to_multi)
        out = gpd.GeoDataFrame(
            {
                "src_file": src_file,
                "src_layer": "" if src_layer is None else str(src_layer),
                "src_type": sub.geom_type.values,
            },
            geometry=geoms.values, crs=sub.crs,
        )
        result[bucket] = out
    return result


def collect_to_geopackage(files, out_path, target_epsg=None,
                          log=None, progress=None, cancel=None):
    """ფაილების გეომეტრიების შეგროვება ერთ GeoPackage-ში (3 შრე).

    files       -> SHP/DXF/DWG გზების სია
    out_path    -> გამომავალი .gpkg
    target_epsg -> სამიზნე EPSG (int) ან None (ავტომატური: პირველი ნაპოვნი CRS)
    log/progress/cancel -> იგივე კონვენცია, რაც სხვა ხელსაწყოებში

    აბრუნებს dict-ს: points/lines/polygons (რიცხვები), files_ok, files_skipped,
    errors ([(path, note)]), out_path, out_files, crs, cancelled.
    """
    log = log or (lambda _m: None)
    progress = progress or (lambda _i, _n: None)
    cancel = cancel or (lambda: False)
    import pandas as pd
    import geopandas as gpd

    buckets = {"point": [], "line": [], "polygon": []}
    auto_crs = None
    files_ok = files_skipped = 0
    errors = []
    total = len(files)

    for i, path in enumerate(files, start=1):
        if cancel():
            return {"cancelled": True, "points": 0, "lines": 0, "polygons": 0,
                    "files_ok": files_ok, "files_skipped": files_skipped,
                    "errors": errors, "out_path": out_path, "out_files": [],
                    "crs": None}
        name = os.path.basename(path)
        try:
            got_any = False
            for lyr, gdf in _read_layers(path):
                parts = _bucketize(gdf, name, lyr)
                for bucket, sub in parts.items():
                    if auto_crs is None and sub.crs is not None:
                        auto_crs = sub.crs
                    buckets[bucket].append(sub)
                    got_any = True
            if got_any:
                files_ok += 1
            else:
                files_skipped += 1
                log("• {} — {}".format(name, "no geometry"))
        except Exception as e:          # noqa: BLE001 — DWG დრაივერი და ა.შ.
            files_skipped += 1
            errors.append((path, str(e)))
            log("✗ {}: {}".format(name, str(e).splitlines()[0]))
        progress(i, total)

    # სამიზნე CRS
    target = None
    if target_epsg:
        target = "EPSG:{}".format(int(target_epsg))
    elif auto_crs is not None:
        target = auto_crs

    def _normalize(gdf):
        """ყველა ნაწილი ერთ CRS-ზე — ცნობილი განსხვავებული → რეპროექცია;
        უცნობი → სამიზნედ ჩაითვლება."""
        if target is None:
            return gdf
        if gdf.crs is not None and gdf.crs != target:
            return gdf.to_crs(target)
        if gdf.crs is None:
            return gdf.set_crs(target, allow_override=True)
        return gdf

    # ჩაწერა — ცარიელი შრეები გამოტოვდება
    if os.path.exists(out_path):
        os.remove(out_path)
    counts = {"point": 0, "line": 0, "polygon": 0}
    out_files = []
    first = True
    for bucket, layer_name in (("point", LAYER_POINTS), ("line", LAYER_LINES),
                               ("polygon", LAYER_POLYGONS)):
        parts = buckets[bucket]
        if not parts:
            continue
        parts = [_normalize(p) for p in parts]
        merged = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True),
                                  crs=target)
        counts[bucket] = len(merged)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        merged.to_file(out_path, layer=layer_name, driver="GPKG",
                       mode="w" if first else "a")
        out_files.append(layer_name)
        first = False
        log("✓ {}: {}".format(layer_name, counts[bucket]))

    return {
        "cancelled": False,
        "points": counts["point"], "lines": counts["line"],
        "polygons": counts["polygon"],
        "files_ok": files_ok, "files_skipped": files_skipped,
        "errors": errors, "out_path": out_path, "out_files": out_files,
        "crs": str(target) if target is not None else None,
    }
