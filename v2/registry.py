"""Tool registry (no Qt): categories, names, descriptions, how each tool is opened.

kind="native"  -> a PySide6 page (``page`` = dotted path ``module:Class``)
kind="legacy"  -> the existing tkinter tool, opened in the classic window (``legacy_key``)
"""
from dataclasses import dataclass

CATEGORIES = [
    ("crs", {"ka": "კოორდინატები და CRS", "en": "Coordinates & CRS"}),
    ("analysis", {"ka": "ანალიზი და გაზომვა", "en": "Analysis & measurement"}),
    ("data", {"ka": "მონაცემთა გადატანა და კონვერტაცია", "en": "Data transfer & conversion"}),
    ("search", {"ka": "ძებნა და რუკები", "en": "Search & maps"}),
    ("system", {"ka": "პარამეტრები და განახლებები", "en": "Settings & updates"}),
]


@dataclass(frozen=True)
class ToolInfo:
    id: str
    category: str
    name: dict
    desc: dict
    kind: str = "legacy"
    legacy_key: str = ""
    page: str = ""


def _t(id, cat, ka, en, dka, den, kind="legacy", key="", page=""):
    return ToolInfo(id, cat, {"ka": ka, "en": en}, {"ka": dka, "en": den}, kind, key, page)


TOOLS = [
    _t("crs_manager", "crs", "CRS მენეჯერი", "CRS Manager",
       "კოორდინატთა სისტემის აღმოჩენა, ჭდის მინიჭება (დადასტურებით) და გადაყვანა ახალ ფაილში; ანგარიშით.",
       "Detect a CRS, assign it (with confirmation) or reproject into a NEW file, with a report.",
       "native", page="v2.pages.crs_page:CrsPage"),
    _t("shp_coords", "crs", "Shp → კოორდინატები", "Shp → coordinates",
       "shapefile-ის წერტილების/წვეროების კოორდინატების ექსპორტი Excel-ში.",
       "Export point/vertex coordinates of shapefiles to Excel.", key="shp_coords"),
    _t("coord_extractor", "crs", "კოორდ. ამომღები", "Coord. extractor",
       "კოორდინატების ამოღება ეკრანიდან/PDF-იდან (OCR).",
       "Extract coordinates from the screen / PDF (OCR).", key="Coord. extractor"),
    _t("zone_intersect", "analysis", "დაცვის ზონის კვეთა", "Zone intersection",
       "ნაკვეთის გადაკვეთა დაცვის ზონასთან: წერტილები, ფართობები.",
       "Parcel vs protection zone: crossing points and areas.", key="zone_intersect"),
    _t("line_intersect", "analysis", "კვეთა და შაბლონი", "Crossing & templates",
       "ხაზების გადაკვეთა და შაბლონების შევსება.", "Line crossings and templates.", key="line_intersect"),
    _t("line_buffer", "analysis", "ბუფერების აგება", "Line buffers",
       "ხაზების ბუფერი მეტრებში (UTM 37N/38N).", "Metric line buffers (UTM 37N/38N).", key="line_buffer",
       kind="native", page="v2.pages.line_buffer_page:LineBufferPage"),
    _t("db_transfer", "data", "ბაზებს შორის მონაცემთა გადატანა", "Database Data Transfer",
       "Personal Geodatabase (.mdb) → .mdb, წლების ფილტრით და დუბლიკატების დაცვით.",
       "Personal Geodatabase (.mdb) → .mdb with year filter and duplicate protection.", key="db_transfer"),
    _t("gdb2pg", "data", "GDB → PostGIS", "GDB → PostGIS",
       "GDB/MDB-ის შრეების იმპორტი PostgreSQL/PostGIS-ში.", "Import GDB/MDB layers into PostGIS.",
       key="GDB → PostGIS"),
    _t("geom_collect", "data", "გეომეტრიების შეგროვება", "Geometry → GeoPackage",
       "SHP/DXF/DWG გეომეტრიების შეგროვება ერთ GeoPackage-ში.", "Collect SHP/DXF/DWG geometry in one GeoPackage.",
       key="Geometry → GeoPackage"),
    _t("dwg_convert", "data", "DWG/DXF → SHP/GPKG/GDB", "DWG/DXF → SHP/GPKG/GDB",
       "DWG/DXF-ის კონვერტაცია GIS ფორმატებში.", "Convert DWG/DXF to GIS formats.", key="dwg_convert"),
    _t("rename", "data", "სახელების გადარქმევა", "Rename → Latin",
       "ფაილების სახელების ტრანსლიტერაცია.", "Transliterate file names.", key="Rename → Latin"),
    _t("updates", "system", "განახლებები", "Updates",
       "ახალი ვერსიის შემოწმება GitHub Releases-დან, ჩამოტვირთვა, ინსტალაცია ბექაპით და უკან დაბრუნება.",
       "Check GitHub Releases for a new version, download, install with backup, roll back.",
       "native", page="v2.pages.updates_page:UpdatesPage"),
    _t("parcel_search", "search", "ნაკვეთის ძებნა", "Parcel search",
       "ნაკვეთის ძებნა კოდით / ნომრით.", "Find parcels by code/number.", key="Parcel search"),
    _t("map_services", "search", "რუკის სერვისები", "Map services",
       "რუკის სერვისების სია და გახსნა.", "Map services list and launcher.", key="Map services",
       kind="native", page="v2.pages.map_services_page:MapServicesPage"),
]

BY_ID = {t.id: t for t in TOOLS}


def category_name(cat_id, lang):
    return dict(CATEGORIES)[cat_id][lang]


def search(query, tools=None):
    """Case-insensitive match on name/description in BOTH languages."""
    q = (query or "").strip().lower()
    out = []
    for t in (tools if tools is not None else TOOLS):
        hay = " ".join([t.name["ka"], t.name["en"], t.desc["ka"], t.desc["en"], t.id]).lower()
        if not q or q in hay:
            out.append(t)
    return out
