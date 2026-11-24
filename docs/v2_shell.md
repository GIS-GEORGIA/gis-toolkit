# GIS_BOX V2 - PySide6 shell

```
python gis_box_v2.py             # start the V2 window
python gis_box_v2.py --selftest  # build the window offscreen, print OK (CI / diagnostics)
```
Needs `PySide6` (`requirements-optional.txt`). The classic app `gis_box.py` / `GIS_BOX.exe` is untouched and keeps working.

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
| `v2/workers.py` | `run_task()`: GIS function in `QThreadPool`, progress/cancel, callbacks delivered in the GUI thread, every task recorded in the operation history |
| `v2/main_window.py` | window, sidebar, pages, notifications |
| `v2/themes.py`, `v2/i18n.py` | theme palettes + stylesheet, UI strings |
| `v2/pages/*.py` | native tool pages (first one: CRS Manager) |
| `v2/launcher.py` | opens a not-yet-ported tkinter tool in the classic window (`gis_box.py --tool KEY`, separate process, no shell) |

GIS logic stays in `tools/*_core.py`; pages only call it through `shell.run(...)`.

## Porting status
| Tool | V2 |
|---|---|
| CRS Manager | **native PySide6 page** (detect, assign with confirmation, reproject to a NEW file, report) |
| all other 12 tools | open in the classic window from the V2 sidebar; being ported one by one |

To port a tool: add a page class in `v2/pages/`, set `kind="native"` and `page="module:Class"` in `registry.py`.

## Known limitations
- Qt must be imported **before** geopandas/shapely on Windows (the other order crashes with an access violation). `gis_box_v2.py` and `conftest.py` already do this - keep it in new entry points.
- The Qt `offscreen` platform renders no fonts (boxes instead of text); screenshots for review need a real platform.
- Ported tools are not yet feature-complete replacements: until a tool is native, the classic window is the reference.
