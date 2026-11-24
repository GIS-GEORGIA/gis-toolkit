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
