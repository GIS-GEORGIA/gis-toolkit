"""CRS Manager - safe, transparent coordinate reference system handling (GUI-independent).

Principles
----------
* ``set_crs`` (ASSIGN: only changes the label, coordinates untouched) and ``to_crs``
  (REPROJECT: coordinates are recomputed) are separate functions and never mixed up.
* An unknown / missing CRS is NEVER assigned automatically: ``assign_crs`` needs
  ``confirmed=True`` (the GUI asks the user first).
* Coordinate ranges can only produce *candidates* (``suggest_candidates``) - never a
  definitive identification.
* Source files are never modified: file operations always write a NEW file and refuse to
  overwrite an existing one.
* Every operation returns a :class:`CrsReport` (original/target CRS, EPSG codes, units,
  transformation method, warnings, result).

Heavy dependencies (pyproj, geopandas, pyogrio, rasterio) are imported lazily.
"""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field

# UTM zones used by GIS_BOX for Georgia (metric calculations); the user may pick any other CRS.
DEFAULT_METRIC_EPSGS = (32637, 32638)
RASTER_EXT = (".tif", ".tiff", ".img", ".vrt", ".jp2")


class CrsError(Exception):
    """Raised for unsafe/invalid CRS operations. ``code`` is a stable machine-readable id."""

    def __init__(self, code, detail=""):
        super().__init__("{}: {}".format(code, detail) if detail else code)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- describing
@dataclass
class CrsInfo:
    name: str = ""
    epsg: int | None = None
    kind: str = ""              # geographic / projected / compound / engineering / unknown
    datum: str = ""
    unit: str = ""              # metre / degree / ...
    projection: str = ""        # e.g. "Transverse Mercator"
    axes: list = field(default_factory=list)
    wkt: str = ""

    @property
    def is_geographic(self):
        return self.kind == "geographic"

    @property
    def is_metric(self):
        return self.kind == "projected" and self.unit.lower() in ("metre", "meter", "m")

    def label(self):
        return "EPSG:{}".format(self.epsg) if self.epsg else (self.name or "unknown")


def _pyproj():
    import pyproj
    return pyproj


def as_crs(value):
    """Anything pyproj understands (EPSG int/str, WKT, CRS object) -> ``pyproj.CRS``."""
    pp = _pyproj()
    try:
        return pp.CRS.from_user_input(value)
    except Exception as e:  # noqa: BLE001
        raise CrsError("invalid_crs", str(e)) from e


def describe(crs) -> CrsInfo:
    """Human-readable description of a CRS (name, EPSG, type, datum, unit, axes)."""
    if crs is None:
        return CrsInfo(kind="unknown", name="(missing)")
    c = as_crs(crs)
    if c.is_projected:
        kind = "projected"
    elif c.is_geographic:
        kind = "geographic"
    elif c.is_compound:
        kind = "compound"
    elif c.is_engineering:
        kind = "engineering"
    else:
        kind = "unknown"
    unit = ""
    if c.axis_info:
        unit = c.axis_info[0].unit_name or ""
    proj = ""
    try:
        if c.coordinate_operation is not None:
            proj = c.coordinate_operation.method_name or ""
    except Exception:  # noqa: BLE001
        pass
    try:
        epsg = c.to_epsg()
    except Exception:  # noqa: BLE001
        epsg = None
    datum = ""
    try:
        datum = c.datum.name if c.datum is not None else (c.geodetic_crs.datum.name if c.geodetic_crs else "")
    except Exception:  # noqa: BLE001
        pass
    return CrsInfo(
        name=c.name, epsg=epsg, kind=kind, datum=datum, unit=unit, projection=proj,
        axes=["{} ({}, {})".format(a.name, a.direction, a.unit_name) for a in c.axis_info],
        wkt=c.to_wkt())


# --------------------------------------------------------------------------- detection
@dataclass
class Detection:
    path: str
    crs: object = None                 # pyproj.CRS or None
    info: CrsInfo = field(default_factory=CrsInfo)
    bounds: tuple | None = None        # (minx, miny, maxx, maxy) in the file's own coordinates
    warnings: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)   # candidates only, never definitive

    @property
    def has_crs(self):
        return self.crs is not None


def detect(path) -> Detection:
    """Detect CRS (+ bounds) of any GDAL-supported vector/raster (shp+prj, gpkg, gdb, geojson, tif...)."""
    if not os.path.exists(path):
        raise CrsError("not_found", path)
    det = Detection(path=path)
    crs, bounds = None, None
    if os.path.splitext(path)[1].lower() in RASTER_EXT:
        try:
            import rasterio
            with rasterio.open(path) as ds:
                crs = ds.crs.to_wkt() if ds.crs else None
                b = ds.bounds
                bounds = (b.left, b.bottom, b.right, b.top)
        except ImportError as e:
            raise CrsError("raster_support_missing", "pip install rasterio") from e
    else:
        import pyogrio
        info = pyogrio.read_info(path)
        crs = info.get("crs")
        fb = info.get("total_bounds")
        bounds = tuple(float(x) for x in fb) if fb is not None and len(fb) == 4 and fb[0] == fb[0] else None
        if path.lower().endswith(".shp") and not os.path.exists(os.path.splitext(path)[0] + ".prj"):
            det.warnings.append("no_prj: the shapefile has no .prj file - CRS is not defined")
    det.bounds = bounds
    if crs:
        det.crs = as_crs(crs)
        det.info = describe(det.crs)
    else:
        det.info = describe(None)
        det.warnings.append("missing_crs: the dataset has no CRS information")
        if bounds:
            det.suggestions = suggest_candidates(bounds)
    det.warnings += range_warnings(bounds, det.crs)
    return det


# --------------------------------------------------------------------------- warnings / guesses
def range_warnings(bounds, crs):
    """Warn when coordinate values look inconsistent with the declared CRS (heuristic only)."""
    out = []
    if not bounds or crs is None:
        return out
    minx, miny, maxx, maxy = bounds
    info = describe(crs)
    if info.is_geographic:
        if not (-180 <= minx <= 180 and -180 <= maxx <= 180 and -90 <= miny <= 90 and -90 <= maxy <= 90):
            out.append("range: coordinates are outside lon/lat limits but the CRS is geographic ({})".format(info.label()))
    elif info.kind == "projected":
        if max(abs(minx), abs(maxx), abs(miny), abs(maxy)) <= 360:
            out.append("range: coordinates look like degrees but the CRS is projected ({})".format(info.label()))
    return out


def suggest_candidates(bounds):
    """CANDIDATE CRSs from the coordinate ranges. Always a guess - never assign automatically."""
    if not bounds:
        return []
    minx, miny, maxx, maxy = bounds
    note = "suggestion only - NOT a definitive identification; confirm with the data owner"
    out = []
    if -180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90:
        out.append({"epsg": 4326, "name": "WGS 84", "reason": "values fit lon/lat degrees", "note": note})
        out.append({"epsg": 4284, "name": "Pulkovo 1942 (geographic)", "reason": "values fit lon/lat degrees", "note": note})
    elif 100_000 <= minx and maxx <= 900_000 and 4_000_000 <= miny and maxy <= 5_500_000:
        out.append({"epsg": 32637, "name": "WGS 84 / UTM 37N", "reason": "easting/northing fit UTM, zone 37 or 38 cannot be told apart by range alone", "note": note})
        out.append({"epsg": 32638, "name": "WGS 84 / UTM 38N", "reason": "same ranges as zone 37", "note": note})
    elif 300_000 <= minx and maxx <= 800_000 and 4_500_000 <= miny and maxy <= 5_200_000:
        out.append({"epsg": 32637, "name": "WGS 84 / UTM 37N", "reason": "plausible", "note": note})
    return out


def metric_candidates(bounds_lonlat=None):
    """Projected metric CRS choices for measurements: GIS_BOX defaults first (UTM 37N/38N).
    If ``bounds_lonlat`` is given, the zone that contains its centre is listed first. The user decides."""
    zones = list(DEFAULT_METRIC_EPSGS)
    if bounds_lonlat:
        lon = (bounds_lonlat[0] + bounds_lonlat[2]) / 2
        first = 32637 if lon < 42.0 else 32638
        zones.sort(key=lambda z: z != first)
    return [{"epsg": z, "name": describe(z).name} for z in zones]


def check_units(crs, operation="metric"):
    """Return a warning string when the CRS units do not fit the operation (or ``None``)."""
    info = describe(crs)
    if operation == "metric" and not info.is_metric:
        return "units: {} uses '{}' - distances/areas must be computed in a projected metric CRS".format(
            info.label(), info.unit or info.kind)
    return None


def compare(a, b):
    """True if two CRS definitions are equivalent (``None`` is never equal to anything)."""
    if a is None or b is None:
        return False
    return as_crs(a).equals(as_crs(b), ignore_axis_order=True)


# --------------------------------------------------------------------------- report
@dataclass
class CrsReport:
    operation: str                      # "assign" | "reproject"
    source_file: str = ""
    output_file: str = ""
    original_crs: CrsInfo = field(default_factory=CrsInfo)
    target_crs: CrsInfo = field(default_factory=CrsInfo)
    method: str = ""
    accuracy: str = ""
    warnings: list = field(default_factory=list)
    result: str = ""
    time: str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds"))

    def to_dict(self):
        d = dict(self.__dict__)
        d["original_crs"] = {k: v for k, v in vars(self.original_crs).items() if k != "wkt"}
        d["target_crs"] = {k: v for k, v in vars(self.target_crs).items() if k != "wkt"}
        return d

    def to_text(self):
        o, t = self.original_crs, self.target_crs
        lines = [
            "CRS operation : {}".format(self.operation.upper()),
            "Time          : {}".format(self.time),
            "Source file   : {}".format(self.source_file or "-"),
            "Output file   : {}".format(self.output_file or "-"),
            "Original CRS  : {} | {} | EPSG {} | unit {}".format(o.name, o.kind, o.epsg, o.unit or "-"),
            "Target CRS    : {} | {} | EPSG {} | unit {}".format(t.name, t.kind, t.epsg, t.unit or "-"),
            "Method        : {}".format(self.method or ("label only - coordinates NOT changed"
                                                       if self.operation == "assign" else "-")),
        ]
        if self.accuracy:
            lines.append("Accuracy      : {}".format(self.accuracy))
        for w in self.warnings:
            lines.append("WARNING       : {}".format(w))
        lines.append("Result        : {}".format(self.result))
        return "\n".join(lines)


# --------------------------------------------------------------------------- operations
def transformation_info(src, dst, bounds_lonlat=None):
    """(method description, accuracy text, warnings) for src -> dst using the best available operation."""
    pp = _pyproj()
    s, d = as_crs(src), as_crs(dst)
    warns = []
    kw = {"always_xy": True}
    if bounds_lonlat:
        w, so, e, n = bounds_lonlat
        pad = 0.01
        kw["area_of_interest"] = pp.transformer.AreaOfInterest(w - pad, so - pad, e + pad, n + pad)
    grp = pp.transformer.TransformerGroup(s, d, **kw)
    if not grp.transformers and "area_of_interest" in kw:      # e.g. a single point = empty area
        grp = pp.transformer.TransformerGroup(s, d, always_xy=True)
    if not grp.transformers:
        raise CrsError("no_transformation", "{} -> {}".format(describe(s).label(), describe(d).label()))
    best = grp.transformers[0]
    acc = best.accuracy
    if acc is None or acc < 0:
        acc_txt = "unknown"
        warns.append("accuracy: the accuracy of this transformation is not known")
    else:
        acc_txt = "{:.2f} m".format(acc)
        if acc > 1.0:
            warns.append("accuracy: this transformation may be inaccurate (~{:.1f} m)".format(acc))
    if grp.unavailable_operations:
        warns.append("grids: {} more accurate operation(s) unavailable (missing grid files)".format(
            len(grp.unavailable_operations)))
    return best.description, acc_txt, warns


def assign_crs(gdf, crs, confirmed=False):
    """``set_crs``: ASSIGN a CRS label (coordinates unchanged). Requires explicit confirmation.

    Returns ``(new_gdf, CrsReport)``. If the data already has a different CRS, that is
    overwritten only with ``confirmed=True`` and a loud warning (it is almost always a mistake;
    use :func:`reproject_gdf` to transform coordinates)."""
    if not confirmed:
        raise CrsError("confirmation_required", "assigning a CRS needs explicit user confirmation")
    tgt = as_crs(crs)
    orig = gdf.crs
    rep = CrsReport("assign", original_crs=describe(orig), target_crs=describe(tgt))
    if orig is not None and not compare(orig, tgt):
        rep.warnings.append("override: the data already had a different CRS ({}). Coordinates were NOT "
                            "transformed - use reproject if you need that".format(describe(orig).label()))
    if len(gdf) and not gdf.geometry.isna().all():
        b = tuple(float(x) for x in gdf.total_bounds)
        rep.warnings += range_warnings(b, tgt)
    out = gdf.set_crs(tgt, allow_override=True)
    rep.result = "CRS label assigned to {} feature(s)".format(len(out))
    return out, rep


def reproject_gdf(gdf, target):
    """``to_crs``: REPROJECT coordinates. Needs a defined source CRS (never guessed)."""
    if gdf.crs is None:
        raise CrsError("missing_crs", "source CRS is not defined - assign it first (with confirmation)")
    tgt = as_crs(target)
    rep = CrsReport("reproject", original_crs=describe(gdf.crs), target_crs=describe(tgt))
    if compare(gdf.crs, tgt):
        rep.method = "none (same CRS)"
        rep.result = "nothing to do - source and target CRS are equivalent"
        return gdf.copy(), rep
    aoi = None
    if len(gdf) and not gdf.geometry.isna().all():
        try:
            minx, miny, maxx, maxy = gdf.to_crs(4326).total_bounds
            aoi = (float(minx), float(miny), float(maxx), float(maxy))
        except Exception:  # noqa: BLE001
            aoi = None
    rep.method, rep.accuracy, w = transformation_info(gdf.crs, tgt, aoi)
    rep.warnings += w
    out = gdf.to_crs(tgt)
    rep.result = "{} feature(s) reprojected".format(len(out))
    return out, rep


def _safe_output(src, out):
    if os.path.abspath(src) == os.path.abspath(out):
        raise CrsError("same_file", "output must differ from the source file")
    if os.path.exists(out):
        raise CrsError("exists", out)


def _write(gdf, out):
    ext = os.path.splitext(out)[1].lower()
    driver = {".gpkg": "GPKG", ".geojson": "GeoJSON", ".json": "GeoJSON", ".shp": "ESRI Shapefile"}.get(ext)
    gdf.to_file(out, driver=driver, engine="pyogrio") if driver else gdf.to_file(out, engine="pyogrio")


def assign_file(src, out, crs, confirmed=False, layer=None):
    """Assign a CRS to a vector file -> NEW file. Source untouched. Needs ``confirmed=True``."""
    import geopandas as gpd
    if not confirmed:
        raise CrsError("confirmation_required", "assigning a CRS needs explicit user confirmation")
    _safe_output(src, out)
    gdf = gpd.read_file(src, layer=layer, engine="pyogrio")
    new, rep = assign_crs(gdf, crs, confirmed=True)
    _write(new, out)
    rep.source_file, rep.output_file = src, out
    return rep


def reproject_file(src, out, target, layer=None):
    """Reproject a vector file -> NEW file. Source untouched. Source CRS must be defined."""
    import geopandas as gpd
    _safe_output(src, out)
    gdf = gpd.read_file(src, layer=layer, engine="pyogrio")
    new, rep = reproject_gdf(gdf, target)
    _write(new, out)
    rep.source_file, rep.output_file = src, out
    return rep


def ensure_metric(gdf, epsg=None):
    """CRS for metric work on ``gdf``: returns ``(gdf_in_metric_crs, CrsReport|None)``.

    Already-metric data is returned unchanged (report ``None``) unless the user explicitly chose a
    different ``epsg``. Otherwise it is reprojected to
    ``epsg`` (user choice) or - if not given - to the suggested UTM zone, and the report states so
    explicitly (no silent CRS change)."""
    if gdf.crs is None:
        raise CrsError("missing_crs", "cannot measure: CRS is not defined")
    if describe(gdf.crs).is_metric and (epsg is None or compare(gdf.crs, epsg)):
        return gdf, None
    if epsg is None:
        lonlat = tuple(float(x) for x in gdf.to_crs(4326).total_bounds)
        epsg = metric_candidates(lonlat)[0]["epsg"]
    return reproject_gdf(gdf, epsg)


def measure(gdf, epsg=None):
    """Areas/lengths in an explicit metric CRS. Returns a dict with the CRS used, units and the
    reprojection report (``None`` if the data already was metric). Never measures in degrees."""
    metric, rep = ensure_metric(gdf, epsg)
    geom = metric.geometry
    return {
        "crs": describe(metric.crs).label(),
        "unit": "m",
        "area_m2": geom.area,
        "length_m": geom.length,
        "report": rep,
    }
