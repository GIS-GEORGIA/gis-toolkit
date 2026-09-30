# -*- coding: utf-8 -*-
"""DWG/DXF → SHP/GPKG/GDB კონვერტერი — სუფთა ლოგიკა (GDAL/pyogrio-ით, ღია კოდით).

arcpy არაა საჭირო: GDAL-ის DXF დრაივერი (ღიაა, ყოველთვის ჩართული) კითხულობს
.dxf-ს პირდაპირ. **DWG** სხვანაირად მუშაობს — ბიბლიოთეკა, რომელსაც pyogrio
ბანდლში ატანს, DWG-ს საერთოდ ვერ კითხულობს (drivers-ში „CAD“ არც კი ჩანს).

DWG-ისთვის ორსაფეხურიანი, **სრულად ჩაშენებული** მიდგომაა:

1. **ბანდლში ატანილი GNU LibreDWG** (`tools/vendor/libredwg/dwg2dxf.exe`,
   GPL-3.0 — იხ. იმავე საქაღალდის README/COPYING) — DWG → DXF. LibreDWG-ს
   რეალურად შეუძლია r13–r2018-ის ~99%-იანი წაკითხვა; **გადამოწმებულია 4
   რეალურ, სხვადასხვა AutoCAD-ვერსიის DWG-ზე — ყველა წარმატებით** (1-დან
   15000-მდე ობიექტამდე). **მომხმარებელს არაფრის დაყენება არ სჭირდება** —
   ბინარი GIS_BOX-თან ერთადაა.
2. **Fallback: სისტემური GDAL** (QGIS/OSGeo4W-ის `ogr2ogr`, თუ ინსტალირებულია)
   — მისი ღია კოდის CAD დრაივერი (`libopencad`) საიმედოდ მხოლოდ **DWG
   R2000 (ACAD1015)**-ს კითხულობს (თანამედროვე DWG მისთვის მიუწვდომელია —
   ეს `libopencad`-ის ცნობილი შეზღუდვაა). გამოსადეგია, თუ LibreDWG-ის
   ბანდლი რატომღაც აკლია (packaging პრობლემა) ან ის კონკრეტულად ჩავარდა.

ორივე ჩავარდნისას `convert_file` თარგმნად მიზეზს აბრუნებს
(`reason`): `"dwg_no_tool"` — ვერცერთი მეთოდი ვერ მოიძებნა; `"dwg_old_driver"`
— მხოლოდ fallback GDAL სცადა და `libopencad`-ის ვერსიის შეზღუდვას მიაწყდა;
`None` — სხვა (ნედლი) შეცდომა. წარმატებისას (DWG → დროებითი DXF/GPKG →
ჩვეულებრივი ნაკადი) შედეგი იგივეა, რაც პირდაპირ GPKG/SHP/DXF წყაროზე;
დანარჩენი ფაილები გრძელდება წარუმატებლობის შემთხვევაშიც.

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


class DwgReadError(RuntimeError):
    """DWG ვერ წაიკითხა. ``reason`` — 'dwg_no_tool' | 'dwg_old_driver' | None
    (თარგმნადი მინიშნების ასარჩევად UI-ში; None = ნედლი GDAL შეცდომა)."""

    def __init__(self, message, reason=None):
        super().__init__(message)
        self.reason = reason


def _bundled_dwg2dxf_path():
    """ბანდლში ატანილი ``dwg2dxf.exe``-ის გზა, ან None (Windows-ის გარეთ ან
    packaging-ის შეცდომისას — შედეგად fallback-ზე გადავა)."""
    import sys
    if sys.platform != "win32":
        return None
    from tools.apppaths import resource_path
    p = resource_path(os.path.join("tools", "vendor", "libredwg", "dwg2dxf.exe"))
    return p if os.path.isfile(p) else None


def _ascii_safe_copy(path):
    """თუ ``path`` არა-ASCII სიმბოლოს შეიცავს (მაგ. ქართული), დროებით
    ASCII-სახელიან ასლზე დააკოპირებს და ``(ასლის_გზა, True)`` აბრუნებს;
    სხვაგვარად — ``(path, False)`` (ასლი არ გაკეთებულა).

    **რატომ:** ბანდლში ატანილი ``dwg2dxf.exe`` (Windows-ის კონსოლის
    აპლიკაცია) ბრძანების არგუმენტებს ANSI კოდის-გვერდით კითხულობს (Python-ის
    ``subprocess`` UTF-16-ით უშვებს პროცესს, მაგრამ ბინარის საკუთარი argv
    parsing-ია ANSI) — ქართული (და სხვა non-ASCII) გზა `?`-ებად იქცევა და
    ფაილი „ვერ მოიძებნება“ (გადამოწმებულია რეალურ ფაილზე). ASCII დროებითი
    ასლი ამ პრობლემას გვერდს უვლის."""
    try:
        path.encode("ascii")
        return path, False
    except UnicodeEncodeError:
        pass
    import tempfile
    from tools.translit import transliterate       # „ფაილის სახელი“ → „failis_saxeli“

    base, ext = os.path.splitext(os.path.basename(path))
    safe_base = transliterate(base) or "file"
    d = tempfile.gettempdir()
    tmp = os.path.join(d, safe_base + ext)
    n = 1
    while os.path.exists(tmp):                      # კოლიზია — ზრდადი სუფიქსი
        tmp = os.path.join(d, "{}_{}{}".format(safe_base, n, ext))
        n += 1
    shutil.copyfile(path, tmp)
    return tmp, True


def _dwg_to_dxf_via_bundled_libredwg(path, exe, log):
    """DWG → დროებითი .dxf ბანდლში ატანილი GNU LibreDWG-ის ``dwg2dxf``-ით.

    არაფერი დამატებით არ სჭირდება — ბინარი GIS_BOX-თან ერთადაა. წარმატებისას
    აბრუნებს დროებითი .dxf-ის გზას (წასაშლელია გამომძახებლის მიერ);
    წარუმატებლობისას — ``DwgReadError`` (``reason=None`` — კონკრეტული
    მიზეზი, თუ ცნობილია, fallback GDAL-ის მცდელობამ შეიძლება უფრო ცხადი
    დააბრუნოს)."""
    import subprocess
    import tempfile
    from tools.gdb2postgis_core import _no_window

    safe_path, is_tmp_src = _ascii_safe_copy(path)
    fd, tmp = tempfile.mkstemp(suffix=".dxf")
    os.close(fd)
    os.remove(tmp)                      # dwg2dxf თავად შექმნის
    try:
        r = subprocess.run(
            [exe, "-o", tmp, safe_path],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
            creationflags=_no_window())
        stderr = (r.stderr or "").strip()
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            raise DwgReadError(
                "Bundled LibreDWG (dwg2dxf) could not convert this file:\n"
                + (stderr or "(no output)"), reason=None)
        log("  · bundled LibreDWG (dwg2dxf) → DXF")
        return tmp
    except subprocess.TimeoutExpired as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise DwgReadError("dwg2dxf timeout", reason=None) from e
    finally:
        if is_tmp_src:
            try:
                os.remove(safe_path)
            except OSError:
                pass


def _dwg_to_readable(path, log):
    """DWG → წასაკითხი დროებითი ფაილის (DXF ან GPKG) გზა.

    ჯერ ბანდლში ატანილ LibreDWG-ს სცდის (§1-ლი მიდგომა — არაფერი
    დამატებით არ სჭირდება); თუ ვერ არის ან ჩავარდა — სისტემურ GDAL-ს
    (fallback). ორივე ჩავარდნისას — ``DwgReadError`` ყველაზე კონკრეტული
    (თარგმნადი) მიზეზით."""
    errors = []
    bundled = _bundled_dwg2dxf_path()
    if bundled:
        try:
            return _dwg_to_dxf_via_bundled_libredwg(path, bundled, log)
        except DwgReadError as e:
            errors.append(e)
    else:
        log("  · bundled LibreDWG not found — trying system GDAL")

    try:
        return _dwg_to_gpkg_via_system_gdal(path, log)
    except DwgReadError as e:
        errors.append(e)

    specific = next((e for e in errors if e.reason), None)
    raise specific or errors[-1]


def _dwg_to_gpkg_via_system_gdal(path, log):
    """DWG → დროებითი .gpkg სისტემური GDAL-ის ``ogr2ogr``-ით (QGIS/OSGeo4W).

    pyogrio-ს ბანდლში ატანილ GDAL-ს DWG-ის დრაივერი საერთოდ არ აქვს; სისტემურ
    GDAL-ს (თუ QGIS/OSGeo4W დაყენებულია) — აქვს ღია კოდის ``CAD`` დრაივერი
    (``libopencad``), მაგრამ **მხოლოდ ძველი R2000 DWG-ის** საიმედო მხარდაჭერით
    (გადამოწმებულია). წარმატებისას აბრუნებს დროებითი .gpkg-ის გზას (წასაშლელია
    გამომძახებლის მიერ); წარუმატებლობისას — ``DwgReadError`` შესაბამისი
    ``reason``-ით.
    """
    import subprocess
    import tempfile
    from tools.gdb2postgis_core import find_tool, _no_window, _child_env

    tool = find_tool("ogr2ogr")
    if not tool:
        raise DwgReadError(
            "System GDAL (ogr2ogr) not found — install QGIS or OSGeo4W; "
            "its open-source CAD driver is needed to read DWG.",
            reason="dwg_no_tool")

    safe_path, is_tmp_src = _ascii_safe_copy(path)
    fd, tmp = tempfile.mkstemp(suffix=".gpkg")
    os.close(fd)
    os.remove(tmp)                      # ogr2ogr თავად შექმნის
    try:
        r = subprocess.run(
            [tool, "-f", "GPKG", tmp, safe_path],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
            creationflags=_no_window(), env=_child_env(tool))
        stderr = (r.stderr or "").strip()
        if r.returncode != 0 or not os.path.exists(tmp):
            if "libopencad" in stderr and "does not support this version" in stderr:
                raise DwgReadError(
                    "libopencad (open-source CAD driver) only reliably reads "
                    "DWG R2000 — this file is a newer DWG version:\n" + stderr,
                    reason="dwg_old_driver")
            raise DwgReadError(stderr or "ogr2ogr failed", reason=None)
        log("  · system GDAL CAD driver → GPKG")
        return tmp
    except subprocess.TimeoutExpired as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise DwgReadError("ogr2ogr timeout", reason=None) from e
    finally:
        if is_tmp_src:
            try:
                os.remove(safe_path)
            except OSError:
                pass


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
        {source, out_path, layers: [(name, feature_count), …], error, reason}
    შეცდომისას ``error`` შეივსება (``layers`` ცარიელი); ``reason`` — იხ.
    ``DwgReadError`` (DWG-სთვის) ან None (სხვა შემთხვევებში/ზოგადი შეცდომა).
    .dwg წყაროსთვის ჯერ სისტემურ GDAL-ს (QGIS/OSGeo4W) ცდილობს
    (``_dwg_to_gpkg_via_system_gdal``) — pyogrio-ს ბანდლს DWG დრაივერი
    საერთოდ არ აქვს.
    """
    log = log or (lambda _m: None)
    base = sanitize(os.path.splitext(os.path.basename(path))[0])
    os.makedirs(out_dir, exist_ok=True)

    ext = os.path.splitext(path)[1].lower()
    tmp_source = None
    read_path = path
    if ext == ".dwg":
        try:
            tmp_source = read_path = _dwg_to_readable(path, log)
        except DwgReadError as e:
            return {"source": path, "out_path": None, "layers": [],
                    "error": str(e), "reason": e.reason}

    try:
        try:
            source_layers = _read_layers(read_path)
        except Exception as e:            # noqa: BLE001 — დრაივერი/გატეხილი ფაილი
            reason = None
            msg = str(e)
            if ext == ".dwg" and tmp_source is not None:
                # DWG → DXF კონვერტაცია (LibreDWG) წარმატებული იყო, მაგრამ
                # GDAL-ის საკუთარი DXF-რიდერი ვერ ასწავლის კონკრეტულ
                # ობიექტს (იშვიათი, ცნობილი შეუთავსებლობა ორ სხვადასხვა ღია
                # კოდის პროექტს შორის — არა ამ პროგრამის ხარვეზი).
                reason = "dwg_gdal_dxf_gap"
                msg = ("DWG successfully converted to DXF (LibreDWG), but "
                      "GDAL's own DXF reader could not parse a specific "
                      "entity in the result:\n" + msg)
            return {"source": path, "out_path": None, "layers": [],
                    "error": msg, "reason": reason}
        return _write_converted(source_layers, base, path, out_dir, fmt,
                                target_epsg, log)
    finally:
        if tmp_source is not None:
            try:
                os.remove(tmp_source)
            except OSError:
                pass


def _write_converted(source_layers, base, source_path, out_dir, fmt,
                     target_epsg, log):
    """წაკითხული შრეების ჩაწერა ``fmt``-ში — ``convert_file``-ის შიდა ნაწილი
    (გამოცალკევებული, რომ DWG → GPKG ხიდის შემდეგაც იმავე ნაკადს გაუყვეს)."""
    driver, ext = FORMATS[fmt]
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
        return {"source": source_path, "out_path": out_root, "layers": written,
                "error": None, "reason": None}

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
    return {"source": source_path, "out_path": out_path if written else None,
            "layers": written, "error": None, "reason": None}


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
