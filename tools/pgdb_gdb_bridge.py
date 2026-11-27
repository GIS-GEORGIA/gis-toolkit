# -*- coding: utf-8 -*-
"""File Geodatabase (.gdb) ხიდი „ბაზებს შორის მონაცემთა გადატანისთვის“ (tkinter-ის გარეშე).

გადატანის ძრავა (``pgdb_transfer_core``) მუშაობს Personal Geodatabase-ზე (.mdb, ODBC) და გამოცდილია;
მას არ ვცვლით. .gdb-ს ვუერთებთ ორი მხრიდან:

* **შეყვანა (.gdb → ძრავა):** ``gdb_to_mdb`` — .gdb-ს ფენებს (point/line/polygon) GDAL-ით (pyogrio) ვკითხულობთ და
  დროებით .mdb-ში ვწერთ (ცარიელი სქემა-შაბლონი, CRS = .gdb-ს CRS). .gdb **მხოლოდ იკითხება**.
* **გამოტანა (ძრავა → .gdb):** მიმღები .gdb **არასდროს იცვლება ადგილზე**. ძრავა დუბლიკატებს დროებით .mdb-ასლზე
  ამოწმებს და წერს; შემდეგ ``append_plan_to_gdb`` ქმნის მიმღების **სრულ ახალ ასლს** (``copytree``) და მხოლოდ
  ახლად ჩაწერილ ჩანაწერებს ამატებს მის ფენებში. არსებული ფაილი არასდროს გადაიწერება.

CRS-ს არასდროს ვიგულისხმებთ: .gdb ფენა CRS-ის გარეშე → ``TransferError("gdb_no_crs")``.
"""
import datetime
import os
import shutil

from tools import pgdb_transfer_core as core
from tools.pgdb_transfer_core import KINDS, TransferError

SKIP_COLS = {"objectid", "shape", "shape_length", "shape_area", "fid", "geometry"}   # გენერირებადი სისტემური ველები
STAGE_SKIP = {"objectid", "shape", "fid", "geometry"}      # დროებით .mdb-ში Shape_Length/Shape_Area გადადის (არ იკარგება)


def is_gdb(path):
    return bool(path) and str(path).rstrip("\\/").lower().endswith(".gdb")


def is_gdb_dir(path):
    return is_gdb(path) and os.path.isdir(path)


def staged_path(gdb_path, folder, tag=""):
    """დროებითი .mdb-ის გზა: ``<folder>/<gdb-ის სახელი>.gdb<tag>.staged.mdb``."""
    return os.path.join(folder, "{}{}.staged.mdb".format(os.path.basename(gdb_path.rstrip("\\/")), tag))


def final_gdb_path(dst_gdb, stamp=None):
    """ახალი საბოლოო .gdb მიმღების გვერდით: ``<სახელი>_FINAL_<დრო>.gdb``."""
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = os.path.basename(dst_gdb.rstrip("\\/"))[:-4].replace(" ", "_")
    return os.path.join(os.path.dirname(os.path.abspath(dst_gdb.rstrip("\\/"))), "{}_FINAL_{}.gdb".format(stem, stamp))


def _ogr():
    try:
        import pyogrio
    except ImportError as e:
        raise TransferError("no_pyogrio", str(e))
    return pyogrio


def _kind_of(geom_type):
    g = (geom_type or "").lower()
    if "z" in g.split() or g.endswith("z") or " m" in g or g.endswith("zm"):
        return None, True
    if "point" in g:
        return "point", False
    if "line" in g:
        return "line", False
    if "polygon" in g:
        return "polygon", False
    return None, False


def inspect_gdb(path):
    """``{ფენა: dict(kind, has_zm, count, crs_wkt, fields)}`` — მხოლოდ სივრცითი ფენები."""
    og = _ogr()
    if not is_gdb_dir(path):
        raise TransferError("not_found", path)
    out = {}
    try:
        layers = og.list_layers(path)
    except Exception as e:                                # noqa: BLE001
        raise TransferError("gdb_open", str(e))
    for name, gtype in layers:
        if gtype is None:
            continue                                      # არასივრცითი ცხრილი
        info = og.read_info(path, layer=name)
        kind, zm = _kind_of(info.get("geometry_type") or gtype)
        crs = info.get("crs")
        wkt = ""
        if crs:
            import pyproj
            wkt = pyproj.CRS.from_user_input(crs).to_wkt(version="WKT1_ESRI")
        out[name] = {"kind": kind, "has_zm": zm, "count": int(info.get("features") or 0), "crs_wkt": wkt,
                     "fields": [str(f) for f in info.get("fields", [])],
                     "dtypes": [str(t) for t in info.get("dtypes", [])]}
    return out


def pick_layers(info, layers=None):
    """თითო ტიპზე ერთი ფენა: ``{kind: name}``; ორაზროვნებისას ``TransferError("gdb_ambiguous")``."""
    layers = dict(layers or {})
    chosen = {}
    for kind in KINDS:
        if kind in layers:
            if layers[kind] not in info:
                raise TransferError("gdb_open", layers[kind])
            chosen[kind] = layers[kind]
            continue
        names = [n for n, i in info.items() if i["kind"] == kind and not i["has_zm"]]
        if len(names) == 1:
            chosen[kind] = names[0]
        elif len(names) > 1:
            raise TransferError("gdb_ambiguous", "{}: {}".format(kind, ", ".join(names)))
    if not chosen:
        raise TransferError("gdb_no_layers", "")
    return chosen


# ---------------------------------------------------------------------------
# გეომეტრია: shapely <-> ESRI shape-buffer
# ---------------------------------------------------------------------------
def geometry_to_parts(geom, kind):
    """shapely → ``(shape_type, parts)`` ``core.encode_shape``-ისთვის. ``ValueError`` — ცარიელი/შეუსაბამო."""
    from shapely.geometry import MultiLineString, MultiPoint, MultiPolygon
    from shapely.geometry.polygon import orient
    if geom is None or geom.is_empty:
        raise ValueError("empty geometry")
    if kind == "point":
        if isinstance(geom, MultiPoint):
            if len(geom.geoms) != 1:
                raise ValueError("multipoint")
            geom = geom.geoms[0]
        if geom.geom_type != "Point":
            raise ValueError("unexpected geometry {}".format(geom.geom_type))
        return 1, [[(geom.x, geom.y)]]
    if kind == "line":
        lines = list(geom.geoms) if isinstance(geom, MultiLineString) else [geom]
        if any(g.geom_type != "LineString" for g in lines):
            raise ValueError("unexpected geometry {}".format(geom.geom_type))
        return 3, [[(x, y) for x, y, *_ in g.coords] for g in lines]
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    if any(g.geom_type != "Polygon" for g in polys):
        raise ValueError("unexpected geometry {}".format(geom.geom_type))
    parts = []
    for p in polys:
        p = orient(p, sign=-1.0)                          # ESRI: გარე რგოლი საათის ისრის მიმართულებით, ხვრელები — საპირისპირო
        parts.append([(x, y) for x, y, *_ in p.exterior.coords])
        for r in p.interiors:
            parts.append([(x, y) for x, y, *_ in r.coords])
    return 5, parts


def parts_to_geometry(stype, parts):
    """``core.decode_shape`` შედეგი → shapely (ხაზი/პოლიგონი — Multi*)."""
    from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
    if stype == 1:
        (x, y), = parts[0]
        return Point(x, y)
    if stype == 3:
        ls = [LineString(p) for p in parts]
        return MultiLineString(ls)
    polys, cur = [], None
    for ring in parts:
        area2 = sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))
        if area2 < 0 or cur is None:                      # საათის ისრის მიმართულება → ახალი გარე რგოლი
            cur = [ring, []]
            polys.append(cur)
        else:
            cur[1].append(ring)
    return MultiPolygon([Polygon(sh, holes) for sh, holes in polys])


def _clean(v):
    """pandas/numpy მნიშვნელობა → ODBC-ისთვის ჩვეულებრივი Python-ის ტიპი (NaN/NaT → None)."""
    import pandas as pd
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, pd.Timestamp):
        return v.tz_localize(None).to_pydatetime() if v.tzinfo is not None else v.to_pydatetime()   # კედლის დრო, ზონის გარეშე
    if hasattr(v, "item"):
        return v.item()
    return v


# ---------------------------------------------------------------------------
# .gdb -> დროებითი .mdb
# ---------------------------------------------------------------------------
def gdb_to_mdb(gdb_path, out_mdb, layers=None, log=None, progress=None, cancel=None):
    """.gdb-ს წერტილი/ხაზი/პოლიგონის ფენები → **ახალი** დროებითი .mdb (შაბლონიდან). .gdb არ იცვლება.

    აბრუნებს ``{kind: (ფენა, ჩაწერილი, ჩაუწერელი)}``. ველები, რომლებიც შაბლონის სქემაში არ არის, არ გადადის
    (ლოგში — გაფრთხილება); ჩანაწერი ცარიელი/შეუსაბამო გეომეტრიით ჩაუწერელია და ლოგში ჩანს."""
    log = log or core.TransferLog()
    cancel = cancel or (lambda: False)
    og = _ogr()
    info = inspect_gdb(gdb_path)
    chosen = pick_layers(info, layers)
    tpl = core.template_path()
    if not os.path.isfile(tpl):
        raise TransferError("no_template", tpl)
    if os.path.exists(out_mdb):
        raise TransferError("exists", out_mdb)
    shutil.copyfile(tpl, out_mdb)
    ok = False
    try:
        for kind, name in chosen.items():
            if not info[name]["crs_wkt"]:
                raise TransferError("gdb_no_crs", "{} ({})".format(name, gdb_path))
        new_info = core.inspect_db(out_mdb)
        wc = core.connect(out_mdb, "excl")
        wcur = wc.cursor()
        for kind, name in chosen.items():
            nl = new_info.by_kind(kind)[0]
            wcur.execute("UPDATE GDB_SpatialRefs SET SRTEXT=? WHERE SRID=?", (info[name]["crs_wkt"], nl.srid))
        wc.commit()
        wc.close()
        new_info = core.inspect_db(out_mdb)
        plan = core.Plan(gdb_path, out_mdb, 0)
        stats = {}
        for kind, name in chosen.items():
            if cancel():
                raise TransferError("cancelled")
            nl = new_info.by_kind(kind)[0]
            have = {f.name.upper(): f.name for f in nl.fields}
            log("gdb {}: {} ({} feature(s)) -> staging database".format(kind.upper(), name, info[name]["count"]))
            gdf = og.read_dataframe(gdb_path, layer=name)
            lp = core.LayerPlan(kind, name, nl.name)
            plan.layers.append(lp)
            cols = [c for c in gdf.columns if c != gdf.geometry.name]
            dropped = [c for c in cols if c.lower() not in SKIP_COLS and c.upper() not in have]
            if dropped:
                log("  gdb fields not in the transfer schema (not carried): {}".format(", ".join(dropped)), "WARN")
            oid_col = next((c for c in cols if c.lower() == "objectid"), None)
            geoms = list(gdf.geometry)
            for i in range(len(gdf)):
                if cancel():
                    raise TransferError("cancelled")
                row = gdf.iloc[i]
                oid = _clean(row[oid_col]) if oid_col else i + 1
                vals = {have[c.upper()]: _clean(row[c]) for c in cols
                        if c.lower() not in STAGE_SKIP and c.upper() in have}
                no_col = core.find_field(list(vals), core.KEY_FIELD)
                no_raw = vals.get(no_col) if no_col else None
                try:
                    stype, parts = geometry_to_parts(geoms[i], kind)
                    blob = core.encode_shape(stype, parts)
                    bb = core.shape_bbox(blob)
                except (ValueError, TypeError) as e:
                    lp.errors.append((oid, no_raw, "geometry: {}".format(e)))
                    log("  gdb OBJECTID {} no={} NOT staged ({})".format(oid, no_raw, e), "WARN")
                    continue
                for meas, val in (("SHAPE_LENGTH", geoms[i].length), ("SHAPE_AREA", geoms[i].area)):
                    if meas in have and vals.get(have[meas]) is None and (meas == "SHAPE_LENGTH" or kind == "polygon"):
                        vals[have[meas]] = float(val)            # .gdb-ში ცარიელია → გეომეტრიიდან (ESRI-სავით, სიბრტყეზე)
                shp = next((have[k] for k in have if k == "SHAPE"), "SHAPE")
                vals[shp] = blob
                # შაბლონის Required ველები: გეომეტრიიდან ვავსებთ, თუ .gdb-ში არ არის
                if kind == "point":
                    vals.setdefault(have.get("X", "x"), bb[0])
                    vals.setdefault(have.get("Y", "y"), bb[1])
                lp.to_insert.append({"src_oid": oid, "no": core.normalize_no(no_raw), "values": vals,
                                     "bbox": bb, "blob": blob})
                if progress:
                    progress(kind, i + 1, len(gdf))
            lp.found = len(gdf)
            stats[kind] = (name, lp.to_insert_count, len(lp.errors))
        core.execute(plan, log=log, backup=False, progress=progress, cancel=cancel)
        for lp in plan.layers:
            name, n_ok, n_err = stats[lp.kind]
            stats[lp.kind] = (name, lp.inserted, n_err + len([e for e in lp.errors if str(e[2]).startswith("insert:")]))
        ok = True
        return stats
    finally:
        if not ok:
            try:
                os.remove(out_mdb)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# გეგმა -> მიმღები .gdb-ს ახალი ასლი
# ---------------------------------------------------------------------------
def append_plan_to_gdb(plan, dst_gdb, final_gdb, log=None, layer_names=None):
    """ჩაწერილი ჩანაწერები (``decision == "inserted"``) → ``final_gdb``.

    ``final_gdb`` ჯერ არ არსებობს → მიმღები .gdb-ს სრული ასლი იქმნება (``copytree``); არსებობს → მას ემატება
    (რამდენიმე წლის გაშვებისას). მიმღები .gdb არასდროს იცვლება. წარუმატებლობისას **ახლად შექმნილი** ასლი იშლება.
    ``layer_names`` — ``{kind: gdb-ფენა}`` (ნაგულისხმევად ავტომატურად)."""
    log = log or core.TransferLog()
    og = _ogr()
    import geopandas as gpd
    import pandas as pd
    import pyproj
    if is_gdb_dir(final_gdb) and os.path.samefile(final_gdb, dst_gdb):
        raise TransferError("same_db")
    from tools import gdb_fidelity as fid
    created = False
    plan.domain_violations = getattr(plan, "domain_violations", {})
    dst_audit = fid.audit(dst_gdb)
    if dst_audit["domains"] or any(l["subtypes"] for l in dst_audit["layers"].values()):
        log("destination schema: " + fid.describe(dst_audit))
    if not os.path.exists(final_gdb):
        try:
            shutil.copytree(dst_gdb, final_gdb, ignore=shutil.ignore_patterns("*.lock"))   # სხვისი ჩაკეტვა არ გადმოვიტანოთ
        except OSError as e:
            shutil.rmtree(final_gdb, ignore_errors=True)
            raise TransferError("copy_failed", str(e))
        created = True
        log("final database (new folder, copy of destination): {}".format(final_gdb))
    try:
        info = inspect_gdb(final_gdb)
        names = pick_layers(info, layer_names)
        for lp in plan.layers:
            items = [it for it in lp.to_insert if it.get("dec") and it["dec"]["decision"] == "inserted"]
            if not items or lp.blocked:
                continue
            name = names.get(lp.kind)
            if name is None:
                raise TransferError("gdb_no_layers", lp.kind)
            wkt = info[name]["crs_wkt"]
            if not wkt:
                raise TransferError("gdb_no_crs", name)
            existing = {f.lower(): f for f in info[name]["fields"]}
            rows, geoms, dropped = [], [], set()
            for it in items:
                row = {}
                for col, v in it["values"].items():
                    low = col.lower()
                    if low in SKIP_COLS:
                        continue
                    if low in existing:
                        row[existing[low]] = v
                    else:
                        dropped.add(col)
                stype, parts = core.decode_shape(it["blob"])
                geom = parts_to_geometry(stype, parts)
                # Shape_Length/Shape_Area: ზუსტი მნიშვნელობა (წყაროს ველიდან, ან გეომეტრიიდან) — GDAL-ის ავტო-გამოთვლა
                # სიზუსტეს ცოტას კარგავს (15.000016 vs 15.0); ცალსახად მითითებულ მნიშვნელობას კი უცვლელად ინახავს.
                src_vals = {k.lower(): v for k, v in it["values"].items()}
                for low, fname in existing.items():
                    if low == "shape_length" and lp.kind != "point":
                        v = src_vals.get("shape_length")
                        row[fname] = float(v) if v is not None else float(geom.length)
                    elif low == "shape_area" and lp.kind == "polygon":
                        v = src_vals.get("shape_area")
                        row[fname] = float(v) if v is not None else float(geom.area)
                rows.append(row)
                geoms.append(geom)
            # pyogrio დამატებისას ველებს ადგილმდებარეობით აწყვილებს → ყველა ველი ფენის თანმიმდევრობით, ფენის ტიპით
            # (რომელი ველი არ გვაქვს — ტიპიზებული ცარიელი მნიშვნელობა)
            n = len(rows)
            data = {}
            for fname, dt in zip(info[name]["fields"], info[name]["dtypes"]):
                col = [r.get(fname) for r in rows]
                if dt.startswith("datetime64"):
                    data[fname] = pd.to_datetime(pd.Series(col, dtype=object)).astype("datetime64[ms]")
                elif dt.startswith("int"):
                    data[fname] = pd.array(col, dtype={"int8": "Int8", "int16": "Int16", "int32": "Int32"}.get(dt, "Int64"))
                elif dt.startswith("float"):
                    data[fname] = pd.Series(col, dtype="float64")
                else:
                    data[fname] = pd.Series(col, dtype=object)
            viol = fid.domain_violations(dst_audit, name, [(it["src_oid"], r) for it, r in zip(items, rows)])
            if viol:                                      # ვწერთ (არაფერს ვკარგავთ), მაგრამ ხმამაღლა ვაფრთხილებთ
                plan.domain_violations.setdefault(lp.kind, []).extend(viol)
                log("  ⚠ {} value(s) do not match the destination domain/subtype (written as they are, please review): {}".format(
                    len(viol), "; ".join("src OBJECTID {} {}={} ({})".format(o, f, v, why) for o, f, v, why in viol[:15])
                    + (" …" if len(viol) > 15 else "")), "WARN")
            gdf = gpd.GeoDataFrame(pd.DataFrame(data, index=range(n)), geometry=geoms, crs=pyproj.CRS.from_wkt(wkt))
            og.write_dataframe(gdf, final_gdb, layer=name, driver="OpenFileGDB", append=True,
                               promote_to_multi=(lp.kind != "point"))
            log("{}: {} record(s) added to {} in the new .gdb".format(lp.kind.upper(), len(items), name))
            if dropped:
                log("  fields not in the .gdb layer (not written): {}".format(", ".join(sorted(dropped))), "WARN")
    except Exception as e:                                # noqa: BLE001
        if created:
            shutil.rmtree(final_gdb, ignore_errors=True)
            log("new .gdb removed after a write failure (the destination was never touched)", "WARN")
        if isinstance(e, TransferError):
            raise
        raise TransferError("gdb_write", str(e))
    return final_gdb
