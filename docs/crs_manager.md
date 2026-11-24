# CRS Manager (`tools/crs_manager.py`)

GUI-independent module for safe coordinate reference system handling.

| Need | Function |
|---|---|
| Describe a CRS (name, EPSG, type, datum, unit, axes) | `describe(crs)` |
| Detect CRS + bounds of a file (shp+prj, GPKG, GDB, GeoJSON, GeoTIFF, any GDAL format) | `detect(path)` |
| **Assign** a CRS label (`set_crs`, coordinates untouched) | `assign_crs(gdf, crs, confirmed=True)` / `assign_file(...)` |
| **Reproject** (`to_crs`, coordinates recomputed) | `reproject_gdf(gdf, crs)` / `reproject_file(...)` |
| Candidate CRSs from coordinate ranges (guess only) | `suggest_candidates(bounds)` |
| Metric CRS for measurements (UTM 37N/38N first, user may choose any) | `metric_candidates(bounds)`, `ensure_metric(gdf, epsg=None)` |
| Warnings | `range_warnings`, `check_units`, `transformation_info` (accuracy, missing grids) |

## Safety rules
- Assigning a CRS **always needs `confirmed=True`** (the GUI must ask the user). A missing CRS is never guessed.
- Coordinate ranges give *candidates* only, never an identification (UTM 37N vs 38N cannot be told apart by range).
- Reprojection needs a defined source CRS; otherwise `CrsError("missing_crs")`.
- File operations write a **new** file; they refuse to overwrite an existing file or the source (`exists`, `same_file`).
- Every operation returns a `CrsReport` (original/target CRS, EPSG, units, method, accuracy, warnings, result) - `to_text()` / `to_dict()`.
- `ensure_metric` never changes the CRS silently: if it reprojects, the report says so.

## Known limitations
- Raster detection needs `rasterio` (optional).
- Transformation accuracy depends on the PROJ grids installed; missing grids are reported as a warning.
- Z/M and compound CRS are described but not specially handled.

## Measurement audit (V2 stage 3)
| Tool | Finding | Status |
|---|---|---|
| Layer analysis (`shp_analysis`) | already converts non-UTM data to UTM 37N/38N and shows `EPSG:x → EPSG:y`; units m / m² | OK, covered by accuracy tests |
| Line buffer | works only in EPSG:32637/32638, asks before converting | OK |
| Zone intersection | areas computed in the parcel CRS; a geographic CRS would give "m²" in square degrees | **fixed**: refuses geographic CRS (`require_metric_crs`); layers without CRS info still allowed (units unknowable) |
| Shp → coordinates | failed reprojection to UTM was swallowed, leaving unprojected coordinates labelled UTM | **fixed**: now raises a clear error |
| DWG convert / Geometry collect | silently assigned the chosen CRS to data without CRS | behaviour kept, now **logged** (`ASSUMED` / `reprojecting a -> b`) |
| `crs_manager.measure()` | new helper: area/length in an explicit metric CRS with the CRS label, unit and reprojection report | new |
