"""Environment diagnostics: Python, GUI toolkits, GIS libraries, system binaries.

``python -m tools.env_check`` prints a report; exit code 1 if a REQUIRED item is missing.
Every missing item carries an actionable hint for the current OS.
"""
import importlib
import platform
import shutil
import sys

LINUX_HINTS = {
    "tkinter": "sudo apt install python3-tk   (Fedora: python3-tkinter, Arch: tk)",
    "ogr2ogr": "sudo apt install gdal-bin     (needed only for GDB -> PostGIS)",
    "venv": "sudo apt install python3-venv",
}
WIN_HINTS = {
    "tkinter": "reinstall Python with the 'tcl/tk' option ticked",
    "ogr2ogr": "install QGIS / OSGeo4W and point GIS_BOX to ogr2ogr.exe",
    "pyodbc": "pip install pyodbc  + Microsoft Access Database Engine (64-bit)",
}


def _hint(key):
    table = WIN_HINTS if sys.platform == "win32" else LINUX_HINTS
    return table.get(key, "pip install " + key)


def _mod(name, required, key=None):
    try:
        m = importlib.import_module(name)
        return {"name": name, "ok": True, "required": required,
                "detail": str(getattr(m, "__version__", "")), "hint": ""}
    except Exception as e:  # noqa: BLE001
        return {"name": name, "ok": False, "required": required,
                "detail": type(e).__name__, "hint": _hint(key or name)}


def collect():
    items = [{"name": "python", "ok": sys.version_info >= (3, 11), "required": True,
              "detail": platform.python_version(),
              "hint": "Python 3.11 or 3.12 is required"}]
    for n, req in (("tkinter", True), ("geopandas", True), ("shapely", True), ("pyproj", True),
                   ("pyogrio", True), ("pandas", True), ("openpyxl", True),
                   ("PySide6", False), ("ezdxf", False), ("psycopg", False)):
        items.append(_mod(n, req))
    if sys.platform == "win32":
        items.append(_mod("pyodbc", False))
    try:
        import pyproj
        items.append({"name": "PROJ", "ok": True, "required": True,
                      "detail": pyproj.proj_version_str, "hint": ""})
    except Exception:  # noqa: BLE001
        items.append({"name": "PROJ", "ok": False, "required": True, "detail": "",
                      "hint": "pip install pyproj"})
    try:
        import pyogrio
        items.append({"name": "GDAL", "ok": True, "required": True,
                      "detail": pyogrio.__gdal_version_string__, "hint": ""})
    except Exception:  # noqa: BLE001
        items.append({"name": "GDAL", "ok": False, "required": True, "detail": "",
                      "hint": "pip install pyogrio"})
    exe = shutil.which("ogr2ogr")
    items.append({"name": "ogr2ogr", "ok": bool(exe), "required": False,
                  "detail": exe or "", "hint": "" if exe else _hint("ogr2ogr")})
    return items


def report(items=None):
    items = items if items is not None else collect()
    lines = ["GIS_BOX environment ({} {})".format(platform.system(), platform.release())]
    for it in items:
        tag = "OK " if it["ok"] else ("MISSING" if it["required"] else "optional-missing")
        lines.append("  [{:<16}] {:<10} {}".format(tag, it["name"], it["detail"]))
        if not it["ok"] and it["hint"]:
            lines.append("      -> " + it["hint"])
    return "\n".join(lines)


def ok(items=None):
    return all(i["ok"] for i in (items if items is not None else collect()) if i["required"])


if __name__ == "__main__":
    its = collect()
    print(report(its))
    sys.exit(0 if ok(its) else 1)
