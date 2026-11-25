# GIS_BOX V2 - PySide6 shell

```
python gis_box_v2.py             # start the V2 window
python gis_box_v2.py --selftest  # build the window offscreen, print OK (CI / diagnostics)
```
Needs `PySide6` (`requirements-optional.txt`). The PyInstaller build contains it too: `GIS_BOX.exe --v2`. The classic app `gis_box.py` / `GIS_BOX.exe` is untouched and keeps working.

## What the window has
- **Sidebar:** search (names + descriptions, Georgian and English), **favorites**, **recently used**, tool **categories**, tool descriptions as tooltips.
- **Tool pages:** header with favorite toggle, description, then the tool itself.
- **Status bar:** progress bar + **Cancel** for background tasks; **toast notifications** for success/errors.
- **View menu:** light/dark theme, Georgian/English (applied immediately, remembered).
- **Service menu:** open logs folder, export diagnostic report (redacted zip), environment check.
- Settings: `v2_settings.json` in the per-user config folder (`%LOCALAPPDATA%\GIS_BOX`, `~/.config/GIS_BOX`; override `GIS_BOX_V2_DIR`) - atomic writes, corrupt/invalid values fall back to defaults.

## Architecture
| Module | Role |
|---|---|
| `v2/registry.py` | tool list, categories, bilingual names/descriptions, how each tool opens (no Qt) |
| `v2/settings.py` | settings, favorites, recents (no Qt) |
| `v2/workers.py` | `run_task()`: GIS function in a plain Python thread (NOT `QThreadPool`, see below), progress/cancel, callbacks delivered in the GUI thread, every task recorded in the operation history |
| `v2/main_window.py` | window, sidebar, pages, notifications |
| `v2/themes.py`, `v2/i18n.py` | theme palettes + stylesheet, UI strings |
| `v2/pages/*.py` | native tool pages (first one: CRS Manager) |
| `v2/launcher.py` | opens a not-yet-ported tkinter tool in the classic window (`gis_box.py --tool KEY`, separate process, no shell) |

GIS logic stays in `tools/*_core.py`; pages only call it through `shell.run(...)`.

## Porting status
| Tool | V2 |
|---|---|
| CRS Manager | **native PySide6 page** (detect, assign with confirmation, reproject to a NEW file, report) |
| Updates | **native PySide6 page** (see [update_manager.md](update_manager.md)) |
| Line buffers | **native PySide6 page** - same rules as the classic tool (EPSG:32637/32638 only, conversion only with consent, new numbered shapefiles, source never changed); logic in `tools/line_buffer_core.py` (`scan_line_shapefiles`, `plan_layer`, `build_buffers`), tested with exact area checks |
| Map services | **native PySide6 page** (URL cards from `map_services.txt`, copy button, filter); parser in `tools/map_services_core.py`, checked to match the classic parser |
| Rename → Latin | **native PySide6 page** (preview table old / new / status, rename after confirmation in a background task, undo of the last batch, content check); logic in `tools/translit.py` shared with the classic tool. All files of one dataset (`a.shp`, `a.dbf`, `a.shp.xml` …) are renamed together or not at all: a conflict on one file skips the whole set, and a failed rename (e.g. a file held open by ArcGIS) rolls back the files of that set already renamed |
| Shp → coordinates | **native PySide6 page**: folder scan, auto-pick (Gas_Pipe_Crossing…), UTM zone auto / 37 / 38, double / integer, header templates (same `shp_coords_templates.txt` as the classic tool; Latin→Georgian converter), crossing-angle column, Excel export in a background task, formatted clipboard copy, transparent PNG, batch, ° on an existing file. The Excel writer is `tools/shp_coords_core.py`, shared with the classic tool and checked cell-by-cell (values, formats, fonts, borders, merges, widths) against the classic output. V2 differences: a batch skips layers without a CRS (the classic batch assumed the chosen zone) and never overwrites an existing .xlsx; “° on a file” does not re-save a file that has no angle column |
| Zone intersection / Crossing & templates | **native PySide6 pages** (one class, two variants: parcel × protection zone, line × line). Zone filter by attribute or row (FID), crossing points written as a NEW `<name><UTM zone>_<N>.shp` (never overwriting), parcel / cut-out / remaining areas, saving the cut-out and remaining pieces, shallow-crossing warning (< 15°), geographic parcel CRS refused, hand-over to the native “Shp → coordinates” page with the areas (and “Excel table” = hand-over + export), ready-made template copy sections (`_<next N>`, never overwriting). Logic in `tools/zone_intersect_core.py`, shared with the classic tool; texts reuse the classic ZTR / LTR catalogues |
| Geometry → GeoPackage | **native PySide6 page**: format tick boxes (+ “other” extensions), output CRS auto / 32637 / 32638, count, collect in a background task with progress and cancel. Output `…_DDMMYY.gpkg`; if it exists `_2`, `_3` … (both V2 and classic now; the core refuses to overwrite). Files WITHOUT a CRS are skipped and listed unless “treat as the output CRS” is ticked (default off in V2; the classic tool keeps its old behaviour of assuming it, with a log warning) |
| all other 10 tools | open in the classic window from the V2 sidebar; being ported one by one |

To port a tool: add a page class in `v2/pages/`, set `kind="native"` and `page="module:Class"` in `registry.py`.

## Why not QThreadPool
PySide creates a fresh Python thread state for every `QRunnable.run`. pyproj keeps its PROJ context in thread-local storage, so a `detect` task followed by a `reproject` task crashed the process (access violation on Windows, segmentation fault on Linux) with pyproj 3.7 / geopandas 1.2 - found by CI, reproduced locally, gone with a plain `threading.Thread`. Results still reach the GUI thread through queued Qt signals. Do not move GIS work back to `QThreadPool` without re-running `tests/test_v2_shell.py` against the newest geopandas/pyproj.

## Known limitations
- Qt must be imported **before** geopandas/shapely on Windows (the other order crashes with an access violation). `gis_box_v2.py` and `conftest.py` already do this - keep it in new entry points.
- The Qt `offscreen` platform renders no fonts (boxes instead of text); screenshots for review need a real platform.
- Ported tools are not yet feature-complete replacements: until a tool is native, the classic window is the reference.
