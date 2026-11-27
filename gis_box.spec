# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — GIS_BOX (onedir).

აწყობს: pyinstaller gis_box.spec  (რეპოს ძირიდან).
lazy-ად ჩატვირთული ხელსაწყოები collect_submodules('tools')-ით ემატება.
მძიმე GIS/OCR პაკეტები collect_all-ით (კოდი + data + dll-ები)."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("shp", "shp"),
    ("gis_box.ico", "."),
    ("gis_box.png", "."),
    ("config.example.txt", "."),
    ("map_services.txt", "."),
    ("tools/coordextract/icon.ico", "tools/coordextract"),
    # GNU LibreDWG (vendored, GPL-3.0) — DWG → DXF კონვერტერისთვის, subprocess-ით
    # გამოძახებული (tools/dwg_convert_core.py); იხ. tools/vendor/libredwg/README.md
    ("tools/vendor/libredwg", "tools/vendor/libredwg"),
    # ცარიელი Personal Geodatabase-ის სქემა-შაბლონი (ახალი ბაზა თარიღის გარეშე ჩანაწერებისთვის)
    ("tools/data/pgdb_template.mdb", "tools/data"),
    # V2 theme assets (combo-box chevrons, SVG) - loaded through the Qt search path "gisbox:" (v2/themes.py)
    ("v2/assets", "v2/assets"),
]
binaries = []
# ხელსაწყოები lazy-ად იტვირთება — ცხადად ჩავრთოთ ყველა submodule
hiddenimports = collect_submodules("tools")
# Excel-ის ღია ფაილის დახურვა COM-ით (Shp → კოორდინატები) — pywin32
hiddenimports += ["win32com", "win32com.client", "pythoncom", "pywintypes"]
# ბაზებს შორის მონაცემთა გადატანა (.mdb) — pyodbc (C-გაფართოება) + სისტემური Access ODBC დრაივერი
hiddenimports += ["pyodbc"]

# V2 ინტერფეისი (PySide6): `GIS_BOX.exe --v2`. v2/ გვერდები importlib-ით იტვირთება → ცხადად ჩავრთოთ.
# PySide6 არასავალდებულოა — თუ დაყენებული არაა, ბილდი მაინც შედგება (კლასიკური ინტერფეისით).
import importlib.util
hiddenimports += collect_submodules("v2") + ["gis_box_v2"]
if importlib.util.find_spec("PySide6") is not None:
    # QtSvg: the qsvg image-format plugin needs it to draw the SVG chevrons of the V2 themes
    hiddenimports += ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtSvg"]
    # PyInstaller supports ONE Qt binding per build - exclude any others present in the environment
    _qt_excludes = [
        "PyQt5", "PyQt6", "PySide2",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
        "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtDesigner", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtSql", "PySide6.QtTest",
    ]
else:
    _qt_excludes = []

# მძიმე პაკეტები — სრული შეგროვება (data ფაილები: GDAL, proj.db, OCR მოდელები…)
for pkg in ["pyogrio", "pyproj", "shapely", "geopandas", "fiona", "rasterio",
            "openpyxl", "pandas", "cv2", "pymupdf", "fitz",
            "rapidocr_onnxruntime", "onnxruntime", "PIL"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["gis_box.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # ბილდის გასამსუბუქებლად — პაკეტები, რომლებიც GIS_BOX-ს არ სჭირდება
    # (torch/tensorflow შესაძლოა სხვა ინსტალაციიდან შემოგვხვდეს — გამოვრიცხოთ).
    excludes=[
        "tkinter.test", "pytest",
        "torch", "torchvision", "torchaudio",
        "tensorflow", "matplotlib", "IPython", "jupyter", "notebook",
    ] + _qt_excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GIS_BOX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # windowed GUI (კონსოლის გარეშე)
    icon="gis_box.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GIS_BOX",
)
