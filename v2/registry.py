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
    badge: str = ""             # short code drawn as the tool's icon (no image files needed)


def _t(id, cat, ka, en, dka, den, kind="legacy", key="", page=""):
    return ToolInfo(id, cat, {"ka": ka, "en": en}, {"ka": dka, "en": den}, kind, key, page, BADGES.get(id, ""))


BADGES = {"crs_manager": "CRS", "shp_coords": "XY", "coord_extractor": "OCR", "zone_intersect": "ZN",
          "line_intersect": "LX", "line_buffer": "BUF", "db_transfer": "MDB", "gdb2pg": "PG",
          "geom_collect": "GPK", "dwg_convert": "DWG", "rename": "Aa", "updates": "UP",
          "parcel_search": "PCL", "map_services": "MAP"}


TOOLS = [
    _t("crs_manager", "crs", "CRS მენეჯერი", "CRS Manager",
       "კოორდინატთა სისტემის აღმოჩენა, ჭდის მინიჭება (დადასტურებით) და გადაყვანა ახალ ფაილში; ანგარიშით.",
       "Detect a CRS, assign it (with confirmation) or reproject into a NEW file, with a report.",
       "native", page="v2.pages.crs_page:CrsPage"),
    _t("shp_coords", "crs", "Shp → კოორდინატები", "Shp → coordinates",
       "shapefile-ის წერტილების/წვეროების კოორდინატების ექსპორტი Excel-ში.",
       "Export point/vertex coordinates of shapefiles to Excel.", key="shp_coords",
       kind="native", page="v2.pages.shp_coords_page:ShpCoordsPage"),
    _t("coord_extractor", "crs", "კოორდ. ამომღები", "Coord. extractor",
       "კოორდინატების ამოღება ეკრანიდან/PDF-იდან (OCR).",
       "Extract coordinates from the screen / PDF (OCR).", key="Coord. extractor",
       kind="native", page="v2.pages.coord_extract_page:CoordExtractPage"),
    _t("zone_intersect", "analysis", "დაცვის ზონის კვეთა", "Zone intersection",
       "ნაკვეთის გადაკვეთა დაცვის ზონასთან: წერტილები, ფართობები.",
       "Parcel vs protection zone: crossing points and areas.", key="zone_intersect",
       kind="native", page="v2.pages.zone_intersect_page:ZoneIntersectPage"),
    _t("line_intersect", "analysis", "კვეთა და შაბლონი", "Crossing & templates",
       "ხაზების გადაკვეთა და შაბლონების შევსება.", "Line crossings and templates.", key="line_intersect",
       kind="native", page="v2.pages.zone_intersect_page:LineIntersectPage"),
    _t("line_buffer", "analysis", "ბუფერების აგება", "Line buffers",
       "ხაზების ბუფერი მეტრებში (UTM 37N/38N).", "Metric line buffers (UTM 37N/38N).", key="line_buffer",
       kind="native", page="v2.pages.line_buffer_page:LineBufferPage"),
    _t("db_transfer", "data", "ბაზებს შორის მონაცემთა გადატანა", "Database Data Transfer",
       "Personal Geodatabase (.mdb) → .mdb, წლების ფილტრით და დუბლიკატების დაცვით.",
       "Personal Geodatabase (.mdb) → .mdb with year filter and duplicate protection.", key="db_transfer",
       kind="native", page="v2.pages.db_transfer_page:DbTransferPage"),
    _t("gdb2pg", "data", "GDB → PostGIS", "GDB → PostGIS",
       "GDB/MDB-ის შრეების იმპორტი PostgreSQL/PostGIS-ში.", "Import GDB/MDB layers into PostGIS.",
       key="GDB → PostGIS", kind="native", page="v2.pages.gdb2pg_page:Gdb2PgPage"),
    _t("geom_collect", "data", "გეომეტრიების შეგროვება", "Geometry → GeoPackage",
       "SHP/DXF/DWG გეომეტრიების შეგროვება ერთ GeoPackage-ში.", "Collect SHP/DXF/DWG geometry in one GeoPackage.",
       key="Geometry → GeoPackage",
       kind="native", page="v2.pages.geom_collect_page:GeomCollectPage"),
    _t("dwg_convert", "data", "DWG/DXF → SHP/GPKG/GDB", "DWG/DXF → SHP/GPKG/GDB",
       "DWG/DXF-ის კონვერტაცია GIS ფორმატებში.", "Convert DWG/DXF to GIS formats.", key="dwg_convert",
       kind="native", page="v2.pages.dwg_convert_page:DwgConvertPage"),
    _t("rename", "data", "სახელების გადარქმევა", "Rename → Latin",
       "ფაილების სახელების ტრანსლიტერაცია.", "Transliterate file names.", key="Rename → Latin",
       kind="native", page="v2.pages.rename_page:RenamePage"),
    _t("updates", "system", "განახლებები", "Updates",
       "ახალი ვერსიის შემოწმება GitHub Releases-დან, ჩამოტვირთვა, ინსტალაცია ბექაპით და უკან დაბრუნება.",
       "Check GitHub Releases for a new version, download, install with backup, roll back.",
       "native", page="v2.pages.updates_page:UpdatesPage"),
    _t("parcel_search", "search", "ნაკვეთის ძებნა", "Parcel search",
       "ნაკვეთის ძებნა კოდით / ნომრით.", "Find parcels by code/number.", key="Parcel search",
       kind="native", page="v2.pages.parcel_search_page:ParcelSearchPage"),
    _t("map_services", "search", "რუკის სერვისები", "Map services",
       "რუკის სერვისების სია და გახსნა.", "Map services list and launcher.", key="Map services",
       kind="native", page="v2.pages.map_services_page:MapServicesPage"),
]

BY_ID = {t.id: t for t in TOOLS}


def badge(tool):
    """Short icon code; falls back to the initials of the English name."""
    return tool.badge or "".join(w[0] for w in tool.name["en"].split()[:2]).upper() or "?"


def by_category():
    """[(category_id, names, [tools...]), ...] in display order (categories without tools are left out)."""
    out = []
    for cid, names in CATEGORIES:
        items = [t for t in TOOLS if t.category == cid]
        if items:
            out.append((cid, names, items))
    return out


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
