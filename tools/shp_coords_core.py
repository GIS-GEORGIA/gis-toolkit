# -*- coding: utf-8 -*-
"""Shp → coordinates: GUI-free logic shared by the classic tool (``tools/shp_coords``) and the V2 page.

Point shapefile → formatted Excel: raw ArcGIS block A:D (FID, Id, POINT_X, POINT_Y) untouched, the cleaned copy
from G (optional 3-row title, № / X / Y [+ crossing angle °]), and optionally the zone-intersection areas block to
the right of the copy (same start row, 2 empty columns gap, ``kv.m``).
"""
import os
import re

from tools.apppaths import data_path
from tools.platform_utils import files_with_suffix
from tools.xlsx_format import save_workbook

AUTO_PATTERNS = ("gas_pipe_crossing", "gas_pipe_protzone_crossing", "crossing")

DEFAULT_TEMPLATES = [
    "nakveTis da dacvis zonis sazRvris kveTis koordinatebi",
    "ნაკვეთის და დაცვის ზონის საზღვრის კვეთის კოორდინატები",
    "ნაკვეთის საზღვრის და დაცვის მეორე ზონის კვეთის კოორდინატები",
]
TEMPLATES_FILE = data_path("shp_coords_templates.txt")

COPY_COL = 7          # G — the copy starts 2 empty columns (E, F) after the raw block
TITLE_ROW = 6
TITLE_ROWS = 3
HEADER_ROW_NO_TITLE = 6
TITLE_FONT = "Sylfaen"
ANGLE_FMT = '0"°"'
ANGLE_HEADERS = {"ka": "გადაკვეთის კუთხე", "en": "gadakveTis kuTxe"}
AREA_LABELS = [("parcel_area", "ნაკვეთის ფართი", "Parcel area"),
               ("cut_area", "მოჭრილი ფართი (ნაკვეთი ∩ ზონა)", "Cut-out area (parcel ∩ zone)"),
               ("remainder_area", "დარჩენილი ფართი", "Remaining area")]


# ---------------------------------------------------------------- header templates (one shared text file)
def file_templates(path=None):
    """User templates from the text file; tolerant to the encoding Notepad used (BOM / UTF-8 / ANSI)."""
    try:
        data = open(path or TEMPLATES_FILE, "rb").read()
    except OSError:
        return []
    for enc in ("utf-8-sig", "utf-8", "cp1251", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def templates(path=None):
    """Built-in + file templates, no duplicates."""
    merged = list(DEFAULT_TEMPLATES)
    for t in file_templates(path):
        if t not in merged:
            merged.append(t)
    return merged


def write_file_templates(lines, path=None):
    with open(path or TEMPLATES_FILE, "w", encoding="utf-8") as f:
        f.write("# თითო ხაზზე ერთი ტექსტური ქუდი (UTF-8) / one header per line\n")
        for ln in lines:
            f.write(ln + "\n")


def add_template(text, path=None):
    """Adds a user template. Returns False (not saved) for text with “?” (a keyboard / encoding problem)."""
    if not text or "?" in text:
        return False
    files = file_templates(path)
    if text not in files and text not in DEFAULT_TEMPLATES:
        write_file_templates(files + [text], path)
    return True


def delete_template(text, path=None):
    """Removes a user template. Built-in ones cannot be removed (returns False)."""
    files = file_templates(path)
    if text not in files:
        return False
    files.remove(text)
    write_file_templates(files, path)
    return True


# ---------------------------------------------------------------- shapefiles
def scan_point_shapefiles(folder):
    """{basename: path} of the point / multipoint shapefiles directly in ``folder``."""
    import pyogrio
    out = {}
    if not folder or not os.path.isdir(folder):
        return out
    for shp in files_with_suffix(folder, ".shp"):          # .SHP too (Linux is case-sensitive)
        try:
            info = pyogrio.read_info(shp)
        except Exception:                      # noqa: BLE001 — unreadable file: not offered
            continue
        if "Point" in str(info.get("geometry_type") or ""):
            out[os.path.basename(shp)] = shp
    return out


def auto_pick(names):
    """A name matching a known pattern (Gas_Pipe_Crossing…), else the first one, else None."""
    names = list(names)
    return next((n for n in names if any(p in n.lower() for p in AUTO_PATTERNS)), names[0] if names else None)


def detect_zone(shp):
    """UTM zone number from the shapefile's CRS (e.g. 37 / 38), or None."""
    try:
        import pyogrio
        import pyproj
        crs = pyogrio.read_info(shp).get("crs")
        if not crs:
            return None
        uz = pyproj.CRS.from_user_input(crs).utm_zone
        m = re.match(r"(\d+)", uz or "")
        return int(m.group(1)) if m else None
    except Exception:                          # noqa: BLE001
        return None


def count_points(shp):
    try:
        import pyogrio
        return int(pyogrio.read_info(shp).get("features") or 0)
    except Exception:                          # noqa: BLE001
        return 0


def crs_missing(shp):
    try:
        import pyogrio
        return not pyogrio.read_info(shp).get("crs")
    except Exception:                          # noqa: BLE001
        return False


def read_points(shp, zone):
    """[(id, x, y), …] in EPSG:326<zone>. A layer WITH a CRS is reprojected (failure is an error, never silently
    mislabelled); a layer WITHOUT a CRS is used as-is (the caller must have the user's consent for that)."""
    import geopandas as gpd
    gdf = gpd.read_file(shp)
    if gdf.crs is not None:
        try:
            gdf = gdf.to_crs(epsg=32600 + zone)
        except Exception as e:
            raise RuntimeError("reprojection to EPSG:{} failed: {}".format(32600 + zone, e)) from e
    idcol = next((c for c in gdf.columns if c.lower() == "id"), None)
    pts = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type == "Point":
            coords = [(geom.x, geom.y)]
        elif geom.geom_type == "MultiPoint":
            coords = [(p.x, p.y) for p in geom.geoms]
        else:
            c = geom.centroid
            coords = [(c.x, c.y)]
        idv = row[idcol] if idcol is not None else 0
        for x, y in coords:
            pts.append((idv, x, y))
    return pts


# ---------------------------------------------------------------- table content
def parse_angle(raw):
    """“37” / “37,5” → 37 / 37.5; empty or invalid → None."""
    raw = (raw or "").strip().replace(",", ".").replace("°", "")
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def coord_value(v, value_type):
    return int(round(v)) if value_type == "int" else float(v)


def block_rows(points, value_type, angle_on, angle_all, angle_hdr):
    """(headers, rows) exactly as in the Excel copy (angle shown with °) — for the clipboard / PNG."""
    headers = ["№", "X", "Y"] + ([angle_hdr] if angle_on else [])
    rows = []
    for i, (_idv, x, y) in enumerate(points, 1):
        row = [i, coord_value(x, value_type), coord_value(y, value_type)]
        if angle_on:
            row.append("{}°".format(angle_all) if angle_all is not None else "")
        rows.append(row)
    return headers, rows


def clipboard_payload(template, headers, rows):
    """(html_fragment, tsv_text) — bordered, centred table (Word / Excel paste it formatted)."""
    def esc(v):
        return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ncols = len(headers)
    bd = "border:1px solid #000;"
    ce = "text-align:center;vertical-align:middle;padding:2px 10px;"
    html = ['<table border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse;'
            'font-family:Sylfaen,Segoe UI,sans-serif;font-size:11pt;">']
    if template:
        html.append('<tr><td colspan="{}" style="{}{}font-weight:bold;">{}</td></tr>'.format(ncols, bd, ce, esc(template)))
    html.append("<tr>" + "".join('<td style="{}{}font-weight:bold;">{}</td>'.format(bd, ce, esc(h)) for h in headers) + "</tr>")
    for row in rows:
        html.append("<tr>" + "".join('<td style="{}{}">{}</td>'.format(bd, ce, esc(c)) for c in row) + "</tr>")
    html.append("</table>")
    lines = ([template] if template else []) + ["\t".join(str(h) for h in headers)]
    lines += ["\t".join(str(c) for c in row) for row in rows]
    return "".join(html), "\r\n".join(lines)


def has_areas(areas):
    return bool(areas and (areas.get("parcel_area") or areas.get("cut_area") or areas.get("remainder_area")))


# ---------------------------------------------------------------- Excel
def write_workbook(path, sheet_name, points, value_type, template, angle_on, angle_all, angle_hdr, areas=None):
    """Writes the workbook. Raises ``tools.xlsx_format.FileLockedError`` when the file is open in Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter
    from tools.xlsx_format import write_areas_block, write_block, write_title

    wb = Workbook()
    ws = wb.active
    ws.title = (sheet_name[:31] or "Coordinates")
    bold = Font(bold=True)
    hcenter = Alignment(horizontal="center")

    # raw block A:D (FID, Id, POINT_X, POINT_Y) — full precision, untouched
    for c, name in enumerate(["FID", "Id", "POINT_X", "POINT_Y"], 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.font = bold
        cell.alignment = hcenter
    for i, (idv, x, y) in enumerate(points):
        ws.cell(row=2 + i, column=1, value=i)
        ws.cell(row=2 + i, column=2, value=(idv if idv is not None else 0))
        ws.cell(row=2 + i, column=3, value=float(x))
        ws.cell(row=2 + i, column=4, value=float(y))

    col = COPY_COL
    ncols = 4 if angle_on else 3
    copy_widths = [max(4, len(str(len(points)))) + 2, 14, 14] + ([22] if angle_on else [])
    if template:
        end_row = write_title(ws, template, TITLE_ROW, col, ncols, rows=TITLE_ROWS, font_name=TITLE_FONT,
                              total_width_chars=sum(copy_widths))
        header_row = end_row + 1
    else:
        header_row = HEADER_ROW_NO_TITLE
    headers = ["№", "X", "Y"] + ([angle_hdr] if angle_on else [])
    rows = [[i, coord_value(x, value_type), coord_value(y, value_type)] + ([angle_all] if angle_on else [])
            for i, (_idv, x, y) in enumerate(points, 1)]
    write_block(ws, header_row, col, headers, rows, angle_index=(3 if angle_on else None), angle_fmt=ANGLE_FMT,
                col_widths=copy_widths)

    # areas block: to the RIGHT of the copy, same start row, 2 empty columns gap (user-approved layout)
    if has_areas(areas):
        metrics = [(ka, en, areas.get(key, 0.0)) for key, ka, en in AREA_LABELS]
        write_areas_block(ws, TITLE_ROW, col + ncols + 2, metrics)

    for c in range(1, 5):
        ws.column_dimensions[get_column_letter(c)].width = 14
    ws.freeze_panes = "A2"
    save_workbook(wb, path)


def apply_degree(path):
    """Finds the “crossing angle” column in every sheet of an existing workbook and gives its cells the ° format
    (numbers typed as text become numbers). Returns the number of cells changed (0 = no such column; the file is
    then left unsaved)."""
    from openpyxl import load_workbook
    wb = load_workbook(path)
    targets = {"გადაკვეთის კუთხე", "gadakvetis kutxe", "gadakveTis kuTxe"}
    n = 0
    for ws in wb.worksheets:
        hdr = None
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and (v.strip() in targets or "კუთხე" in v or "kutxe" in v.lower()):
                    hdr = cell
                    break
            if hdr:
                break
        if not hdr:
            continue
        for r in range(hdr.row + 1, ws.max_row + 1):
            cell = ws.cell(row=r, column=hdr.column)
            left = ws.cell(row=r, column=hdr.column - 1).value
            if cell.value is None and left is None:
                continue
            if isinstance(cell.value, str):
                s = cell.value.strip().replace("°", "").replace(",", ".")
                try:
                    f = float(s)
                    cell.value = int(f) if f.is_integer() else f
                except ValueError:
                    pass
            cell.number_format = ANGLE_FMT
            n += 1
    if n:
        save_workbook(wb, path)
    return n
