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
]
binaries = []
# ხელსაწყოები lazy-ად იტვირთება — ცხადად ჩავრთოთ ყველა submodule
hiddenimports = collect_submodules("tools")
# Excel-ის ღია ფაილის დახურვა COM-ით (Shp → კოორდინატები) — pywin32
hiddenimports += ["win32com", "win32com.client", "pythoncom", "pywintypes"]

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
    ],
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
