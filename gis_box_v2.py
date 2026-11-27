#!/usr/bin/env python
"""GIS_BOX V2 - modern PySide6 interface. The classic app (gis_box.py) is untouched and still works.

    python gis_box_v2.py            # start the V2 window
    python gis_box_v2.py --selftest # build the window offscreen, print OK, exit (CI / diagnostics)
    python gis_box_v2.py --selftest --all-pages [--report FILE]
                                    # + build all 14 tool pages in both themes, load the theme assets and do a
                                    #   tiny real GIS round trip (GDAL write/read, PROJ transform). For the packaged
                                    #   app, which has no console: --report writes the result to FILE.
"""
import os
import sys


def _qt_import_problem(e):
    """Explain why PySide6 could not be imported. A missing package and a missing *system library* (Linux:
    libEGL, libxkbcommon, xcb …) look alike to Python, but need different fixes."""
    if isinstance(e, ModuleNotFoundError) and (e.name or "").split(".")[0] == "PySide6":
        return "PySide6 is not installed.  pip install PySide6   (see requirements-optional.txt)"
    msg = "PySide6 (Qt) could not be loaded: {}".format(e)
    if sys.platform.startswith("linux"):
        if "GLIBC_" in str(e):            # a build made on a newer distribution than this one
            msg += ("\nThis GIS_BOX build needs a newer Linux (C library) than this system has. Use a build made "
                    "on this or an older distribution, or run from source (see docs/INSTALL.md).")
        else:
            msg += ("\nA Qt system library is missing. Debian/Ubuntu: sudo apt install libegl1 libgl1 libxkbcommon0 "
                    "libxkbcommon-x11-0 libfontconfig1 libdbus-1-3 libxcb-cursor0   (see docs/INSTALL.md)")
    return msg


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as e:
        print(_qt_import_problem(e), file=sys.stderr)
        return 2
    from v2.main_window import MainWindow, install_excepthook
    from v2.settings import Settings

    from tools import update_manager
    update_manager.cleanup_on_start()                  # removes *.gbold-* leftovers of a previous update (frozen only)
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("GIS_BOX")
    win = MainWindow(Settings())
    if "--selftest" in argv:
        lines, ok = ["OK GIS_BOX V2 window built: " + win.windowTitle()], True
        if "--all-pages" in argv:
            ok, more = _selftest_all(app, win)
            lines += more
        text = "\n".join(lines + ["RESULT " + ("OK" if ok else "FAILED")])
        if "--report" in argv and argv.index("--report") + 1 < len(argv):
            with open(argv[argv.index("--report") + 1], "w", encoding="utf-8") as f:
                f.write(text + "\n")
        print(text)
        return 0 if ok else 1
    install_excepthook(win)                            # log + show unexpected errors instead of a silent console
    win.show()
    return app.exec()


def _selftest_all(app, win):
    """Diagnostics for a build: every page, both themes, assets, GIS stack. Returns (ok, lines)."""
    import platform
    import tempfile
    lines, ok = ["platform {} | Python {} | Qt platform {}".format(platform.platform(), platform.python_version(),
                                                                  app.platformName())], True
    from v2 import registry, themes
    assets = themes.register_assets()
    lines.append("theme assets (SVG chevrons / ticks): " + ("OK" if assets else "MISSING"))
    ok &= assets
    bundle = getattr(sys, "_MEIPASS", None)                   # frozen build: assets must come from the bundle,
    inside = bundle is None or os.path.normcase(str(themes.ASSET_DIR)).startswith(os.path.normcase(bundle))
    lines.append("asset folder: {} ({})".format(themes.ASSET_DIR, "bundled" if bundle else "source"))
    if not inside:                                            # never from a developer checkout
        lines.append("asset folder FAILED: outside the packaged application")
    ok &= inside
    for theme in ("dark", "light"):
        win.apply_theme(theme)
        for t in registry.TOOLS:
            try:
                win.show_tool(t.id)
                page = win.pages[t.id]
                good = getattr(page, "native", True) is not None
                err = getattr(page, "error", "")
            except Exception as e:                         # noqa: BLE001 - reported
                good, err = False, e
            ok &= good
            if theme == "dark" or not good:
                lines.append("page {:<16} {} {}".format(t.id, theme, "OK" if good else "FAILED: {}".format(err)))
    for mod, required in (("geopandas", True), ("pyogrio", True), ("pyproj", True), ("shapely", True),
                          ("openpyxl", True), ("ezdxf", False), ("pymupdf", False), ("cv2", False),
                          ("rapidocr_onnxruntime", False)):
        try:
            __import__(mod)
            lines.append("module {:<22} OK".format(mod))
        except Exception as e:                             # noqa: BLE001 - reported
            lines.append("module {:<22} {}: {}".format(mod, "MISSING" if required else "optional, missing", e))
            ok &= not required
    try:
        import geopandas as gpd
        from pyproj import Transformer
        from shapely.geometry import Point

        from tools.safe_output import staged_file
        d = tempfile.mkdtemp(prefix="gisbox_selftest_")
        out = os.path.join(d, "ქართული test.gpkg")
        with staged_file(out) as tmp:
            gpd.GeoDataFrame({"name": ["ტესტი"]}, geometry=[Point(500000, 4650000)], crs=32638).to_file(
                tmp, layer="t", driver="GPKG")
        back = gpd.read_file(out, layer="t")
        x, y = Transformer.from_crs(32638, 4326, always_xy=True).transform(500000, 4650000)
        good = back["name"][0] == "ტესტი" and back.crs.to_epsg() == 32638 and abs(x - 45.0) < 1e-6 and 41 < y < 43
        lines.append("GIS round trip (GPKG write/read, PROJ 32638->4326 = {:.4f},{:.4f}): {}".format(
            x, y, "OK" if good else "FAILED"))
        ok &= good
    except Exception as e:                                 # noqa: BLE001 - reported
        lines.append("GIS round trip FAILED: {}: {}".format(type(e).__name__, e))
        ok = False
    return ok, lines


if __name__ == "__main__":
    sys.exit(main())
