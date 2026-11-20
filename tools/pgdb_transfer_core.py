# -*- coding: utf-8 -*-
"""ბაზებს შორის სივრცითი მონაცემების გადატანა — ESRI Personal Geodatabase (.mdb) → .mdb.

სუფთა ლოგიკა (tkinter-ის გარეშე). UI: ``tools.pgdb_transfer``.

რატომ ODBC
----------
Personal Geodatabase (.mdb) GDAL-ში **მხოლოდ წასაკითხია** (PGeo), ArcGIS Pro 3.x ამ ფორმატს
ვერ კითხულობს, ხოლო ArcMap-ის arcpy აქ არ მუშაობს. ამიტომ ვწერთ პირდაპირ Access ODBC-ით
(``pyodbc``) და ვიცავთ იმ სტრუქტურას, რასაც ArcGIS ინახავს. გადამოწმებულია რეალურ ბაზებზე:

* ``SHAPE`` — ESRI shape-buffer (წერტილი: ტიპი 1 + X + Y; ხაზი 3 / პოლიგონი 5: ტიპი + bbox(4 double)
  + …). გადაგვაქვს **ბაიტ-ბაიტ**, ამიტომ გეომეტრია და სიზუსტე უცვლელია (CRS-ის დამთხვევისას);
* ``<fc>_SHAPE_Index`` — სივრცითი ინდექსი: ``(IndexedObjectId, MinGX, MinGY, MaxGX, MaxGY)``, სადაც
  ``MinGX = floor((xmin - IdxOriginX) / IdxGridSize)`` (პარამეტრები ``GDB_GeomColumns``-შია).
  ფორმულა ემთხვევა არსებული ჩანაწერების **100%-ს**; ახალ ჩანაწერებს ინდექსს ვუმატებთ;
* ``GDB_GeomColumns.Extent*`` — ფენის ექსტენტი (მხოლოდ ფართოვდება).

უსაფრთხოება: წყარო იხსნება ReadOnly-ით, მიმღები — Exclusive-ით (თუ სხვა პროგრამას — მაგ. ArcGIS Pro —
ღია აქვს, გვატყობინებს), ყველა ჩაწერა **ერთ ტრანზაქციაშია** (ყველა ფენა ერთად — ან არაფერი),
არსებული ჩანაწერები არასდროს იშლება/იცვლება, SQL — პარამეტრიზებული.
"""

import datetime
import math
import os
import shutil
import struct
import time

KINDS = ("point", "line", "polygon")                       # გადასატანი ფენების ტიპები
SHAPE_TYPE_TO_KIND = {1: "point", 3: "line", 4: "polygon"}  # GDB_GeomColumns.ShapeType
KEY_FIELD = "werilis_no"
DATE_FIELD = "tariri"                                      # შედარება case-insensitive
SYSTEM_COPY_SKIP = ("objectid",)                           # ავტონომერი — ახალს ანიჭებს ბაზა
MIN_VALID_YEAR, MAX_VALID_YEAR = 1990, 2100                # ამ დიაპაზონს გარეთ — „არასწორი თარიღი“
MAX_LOGGED_IDS = 40                                        # ლოგში ჩამოსათვლელი ჩანაწერების ზღვარი

ODBC_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


# ---------------------------------------------------------------------------
# შეცდომები
# ---------------------------------------------------------------------------
class TransferError(Exception):
    """გასაგები (მომხმარებლისთვის საჩვენებელი) შეცდომა. ``code`` — თარგმნადი გასაღები."""

    def __init__(self, code, detail=""):
        super().__init__("{}: {}".format(code, detail) if detail else code)
        self.code = code
        self.detail = detail


def friendly_error(exc):
    """pyodbc-ის შეცდომა → ``TransferError`` (დაბლოკილი/ვერ მოიძებნა/ფორმატი/დრაივერი)."""
    text = str(exc)
    low = text.lower()
    if "already in use" in low or "-1024" in low or "could not lock" in low or "locked" in low:
        return TransferError("locked", text)
    if "could not find file" in low or "not a valid path" in low or "cannot open" in low and "file" in low:
        return TransferError("not_found", text)
    if "unrecognized database format" in low or "not a valid" in low:
        return TransferError("bad_format", text)
    if "data source name not found" in low or "im002" in low:
        return TransferError("no_driver", text)
    if "read-only" in low or "cannot update" in low:
        return TransferError("readonly", text)
    return TransferError("db_error", text)


def _pyodbc():
    try:
        import pyodbc
    except ImportError as e:
        raise TransferError("no_pyodbc", str(e))
    return pyodbc


def pyodbc_error():
    """``pyodbc.Error`` კლასი (lazy იმპორტი; pyodbc-ის გარეშე — ვერასდროს დაიჭერს არაფერს)."""
    try:
        import pyodbc
        return pyodbc.Error
    except ImportError:                                   # pragma: no cover
        return ()


def driver_available():
    """True, თუ pyodbc და Access ODBC დრაივერი (64-ბიტი) ხელმისაწვდომია."""
    try:
        import pyodbc
        return ODBC_DRIVER in pyodbc.drivers()
    except Exception:                                    # noqa: BLE001
        return False


def connect(path, mode="ro"):
    """mode: ``ro`` (ReadOnly, autocommit), ``excl`` (Exclusive, ტრანზაქციით — ჩასაწერად)."""
    pyodbc = _pyodbc()
    if ODBC_DRIVER not in pyodbc.drivers():
        raise TransferError("no_driver", ODBC_DRIVER)
    cs = "Driver={{{}}};DBQ={};".format(ODBC_DRIVER, os.path.abspath(path))
    cs += "ReadOnly=1;" if mode == "ro" else "Exclusive=1;"
    try:
        return pyodbc.connect(cs, autocommit=(mode == "ro"))
    except pyodbc.Error as e:
        raise friendly_error(e)


# ---------------------------------------------------------------------------
# სუფთა დამხმარეები (ტესტირებადი, ბაზის გარეშე)
# ---------------------------------------------------------------------------
def year_bounds(year):
    """მთელი წელი: ``[YYYY-01-01 00:00:00, (YYYY+1)-01-01 00:00:00)`` — ზედა ზღვარი ექსკლუზიურია,
    ამიტომ YYYY-12-31 23:59:59(.999) შედის."""
    year = int(year)
    return datetime.datetime(year, 1, 1), datetime.datetime(year + 1, 1, 1)


def classify_date(value):
    """``"ok"`` / ``"missing"`` (NULL) / ``"invalid"`` (არა თარიღი, ან ტყუილად შორეული წელი)."""
    if value is None:
        return "missing"
    if isinstance(value, datetime.datetime):
        d = value
    elif isinstance(value, datetime.date):
        d = datetime.datetime(value.year, value.month, value.day)
    else:
        return "invalid"
    if d.year < MIN_VALID_YEAR or d.year > MAX_VALID_YEAR:
        return "invalid"
    return "ok"


def in_year(value, year):
    return classify_date(value) == "ok" and value.year == int(year)


def normalize_no(value):
    """werilis_no შესადარებლად: ტექსტი, გარე სფეისები მოცილებული; ცარიელი → ``None``."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def decide(src_no, dest_numbers_in_year):
    """``"insert"`` / ``"duplicate"`` (მიმღებში იგივე ნომერი ამავე წლით უკვე არის) /
    ``"no_number"`` (ნომრის გარეშე დუბლიკატობა ვერ შემოწმდება)."""
    n = normalize_no(src_no)
    if n is None:
        return "no_number"
    return "duplicate" if n in dest_numbers_in_year else "insert"


def find_field(names, wanted):
    """ველის სახელი სიაში case-insensitive ძებნით (``TariRi`` / ``TariRI`` ერთია).

    აბრუნებს ნამდვილ სახელს ან ``None``-ს."""
    w = wanted.lower()
    for n in names:
        if n.lower() == w:
            return n
    return None


def _family(type_name):
    t = (type_name or "").upper()
    if t in ("COUNTER", "INTEGER", "LONG", "SMALLINT", "BYTE", "TINYINT", "BIGINT"):
        return "int"
    if t in ("DOUBLE", "REAL", "FLOAT", "NUMERIC", "DECIMAL", "CURRENCY", "SINGLE"):
        return "float"
    if t in ("VARCHAR", "CHAR", "LONGCHAR", "TEXT", "MEMO", "WVARCHAR", "WLONGVARCHAR"):
        return "text"
    if t in ("DATETIME", "DATE", "TIMESTAMP"):
        return "date"
    if t in ("LONGBINARY", "VARBINARY", "BINARY"):
        return "binary"
    if t in ("BIT", "YESNO"):
        return "bool"
    return t or "unknown"


class FieldInfo(object):
    def __init__(self, name, type_name, size=None, nullable=True):
        self.name, self.type_name, self.size, self.nullable = name, type_name, size, bool(nullable)
        self.family = _family(type_name)

    def __repr__(self):
        return "FieldInfo({}, {}, {}, nullable={})".format(self.name, self.type_name, self.size, self.nullable)


class FieldPlan(object):
    """ველების შედარება წყაროსა და მიმღებს შორის."""

    def __init__(self):
        self.copy = []              # [(src_name, dst_name)] — გადასატანი ველები (SHAPE-ც ჩათვლით)
        self.unmatched_src = []     # წყაროს ველი, რომელიც მიმღებში არ არის → ვერ გადავა (ხმამაღლა!)
        self.length_checked = []    # [(src, dst, dst_size)] — ტექსტი, სადაც მიმღები უფრო მოკლეა
        self.blockers = []          # [(კოდი, ველი, დეტალი)] — ფენის გადატანა შეუძლებელია
        self.missing_required = []  # მიმღების აუცილებელი ველი, რომელიც წყაროში არ არის

    @property
    def ok(self):
        return not self.blockers and not self.missing_required


_WIDEN_OK = {("int", "float")}


def plan_fields(src_fields, dst_fields):
    """წყაროსა და მიმღების ველების შედარება; არაფერს ჩუმად არ ვაგდებთ."""
    plan = FieldPlan()
    dst_by_low = {f.name.lower(): f for f in dst_fields}
    src_low = {f.name.lower() for f in src_fields}
    for s in src_fields:
        low = s.name.lower()
        if low in SYSTEM_COPY_SKIP or s.type_name.upper() == "COUNTER":
            continue
        d = dst_by_low.get(low)
        if d is None:
            plan.unmatched_src.append(s.name)
            continue
        if s.family != d.family and (s.family, d.family) not in _WIDEN_OK:
            plan.blockers.append(("type_mismatch", s.name, "{} → {}".format(s.type_name, d.type_name)))
            continue
        if s.family == "text" and d.size and s.size and d.size < s.size:
            plan.length_checked.append((s.name, d.name, d.size))
        plan.copy.append((s.name, d.name))
    for d in dst_fields:
        low = d.name.lower()
        if low in SYSTEM_COPY_SKIP or d.type_name.upper() == "COUNTER":
            continue
        if low not in src_low and not d.nullable:
            plan.missing_required.append(d.name)
    return plan


# ---------------------------------------------------------------------------
# გეომეტრია: shape-buffer (ESRI) + სივრცითი ინდექსი
# ---------------------------------------------------------------------------
def shape_type(blob):
    return struct.unpack("<i", bytes(blob[:4]))[0]


def shape_kind(blob):
    """``point``/``line``/``polygon`` ან ``None`` (Z/M/მრავალწერტილი/სხვა)."""
    t = shape_type(blob)
    return {1: "point", 3: "line", 5: "polygon"}.get(t)


def shape_bbox(blob):
    """(xmin, ymin, xmax, ymax) shape-buffer-იდან. ``ValueError`` — დაზიანებული/უცნობი ბუფერი."""
    b = bytes(blob)
    t = shape_type(b)
    if t == 1:
        if len(b) < 20:
            raise ValueError("point buffer too short")
        x, y = struct.unpack("<2d", b[4:20])
        box = (x, y, x, y)
    else:
        if len(b) < 36:
            raise ValueError("shape buffer too short")
        box = struct.unpack("<4d", b[4:36])
    if not all(math.isfinite(v) for v in box):
        raise ValueError("non-finite bbox")
    return box


def index_cells(bbox, origin_x, origin_y, grid):
    """სივრცითი ინდექსის უჯრები: ``(MinGX, MinGY, MaxGX, MaxGY)``."""
    xmin, ymin, xmax, ymax = bbox
    return (int(math.floor((xmin - origin_x) / grid)), int(math.floor((ymin - origin_y) / grid)),
            int(math.floor((xmax - origin_x) / grid)), int(math.floor((ymax - origin_y) / grid)))


def decode_shape(blob):
    """მარტივი 2D shape-buffer → ``(type, parts)``; ``parts`` — [[(x, y), …], …].

    მხოლოდ ტიპები 1, 3, 5 (Z/M/მრუდების გარეშე). სხვაზე — ``ValueError``."""
    b = bytes(blob)
    t = shape_type(b)
    if t == 1:
        x, y = struct.unpack("<2d", b[4:20])
        return 1, [[(x, y)]]
    if t not in (3, 5):
        raise ValueError("unsupported shape type {}".format(t))
    nparts, npts = struct.unpack("<2i", b[36:44])
    starts = list(struct.unpack("<{}i".format(nparts), b[44:44 + 4 * nparts]))
    off = 44 + 4 * nparts
    if len(b) < off + 16 * npts:
        raise ValueError("shape buffer truncated")
    flat = struct.unpack("<{}d".format(2 * npts), b[off:off + 16 * npts])
    pts = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
    starts.append(npts)
    return t, [pts[starts[i]:starts[i + 1]] for i in range(nparts)]


def encode_shape(stype, parts):
    """``decode_shape``-ის შებრუნებული (bbox თავიდან ითვლება)."""
    if stype == 1:
        (x, y), = parts[0]
        return struct.pack("<i2d", 1, x, y)
    pts = [p for part in parts for p in part]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    starts, n = [], 0
    for part in parts:
        starts.append(n)
        n += len(part)
    out = struct.pack("<i4d2i", stype, min(xs), min(ys), max(xs), max(ys), len(parts), len(pts))
    out += struct.pack("<{}i".format(len(starts)), *starts)
    for x, y in pts:
        out += struct.pack("<2d", x, y)
    return out


def reproject_shape(blob, transform):
    """shape-buffer-ის კოორდინატების გადაყვანა. ``transform(xs, ys) -> (xs2, ys2)``.

    სტრუქტურა (ნაწილები/რგოლების თანმიმდევრობა) უცვლელი რჩება. უსასრულო შედეგი → ``ValueError``."""
    stype, parts = decode_shape(blob)
    new_parts = []
    for part in parts:
        xs, ys = transform([p[0] for p in part], [p[1] for p in part])
        pts = list(zip(xs, ys))
        if not all(math.isfinite(a) and math.isfinite(c) for a, c in pts):
            raise ValueError("reprojection produced non-finite coordinates")
        new_parts.append(pts)
    return encode_shape(stype, new_parts)


def _norm_wkt(s):
    return "".join((s or "").split()).lower()


def crs_relation(src_wkt, dst_wkt):
    """``"same"`` — ერთნაირია; ``"reproject"`` — სხვადასხვაა, pyproj-ს შეუძლია გადაყვანა;
    ``"unknown"`` — გადაყვანა კარგად განსაზღვრული არაა."""
    if _norm_wkt(src_wkt) == _norm_wkt(dst_wkt) and _norm_wkt(src_wkt):
        return "same"
    try:
        import pyproj
        a, b = pyproj.CRS.from_wkt(src_wkt), pyproj.CRS.from_wkt(dst_wkt)
        if a.equals(b, ignore_axis_order=True):
            return "same"
        pyproj.Transformer.from_crs(a, b, always_xy=True)
        return "reproject"
    except Exception:                                    # noqa: BLE001
        return "unknown"


def make_transformer(src_wkt, dst_wkt):
    import pyproj
    t = pyproj.Transformer.from_crs(pyproj.CRS.from_wkt(src_wkt), pyproj.CRS.from_wkt(dst_wkt),
                                    always_xy=True)

    def fn(xs, ys):
        rx, ry = t.transform(xs, ys)
        return list(rx), list(ry)
    return fn


# ---------------------------------------------------------------------------
# ბაზის ინსპექცია
# ---------------------------------------------------------------------------
class LayerInfo(object):
    def __init__(self):
        self.name = ""
        self.kind = None
        self.shape_type = None
        self.has_z = self.has_m = False
        self.srid = None
        self.srtext = ""
        self.fields = []
        self.origin_x = self.origin_y = self.grid = None
        self.extent = None
        self.count = 0

    def field_names(self):
        return [f.name for f in self.fields]


class DbInfo(object):
    def __init__(self, path):
        self.path = path
        self.layers = {}            # სახელი → LayerInfo

    def by_kind(self, kind):
        return [l for l in self.layers.values() if l.kind == kind]


def _columns(cur, table):
    out = []
    for r in cur.columns(table=table):
        out.append(FieldInfo(r.column_name, r.type_name, r.column_size, r.nullable != 0))
    return out


def inspect_db(path, conn=None):
    """ბაზის სივრცითი ფენები (``GDB_GeomColumns``-იდან), ველები, CRS, ინდექსის პარამეტრები, რაოდენობა."""
    own = conn is None
    if own:
        conn = connect(path, "ro")
    try:
        cur = conn.cursor()
        try:
            geo = cur.execute("SELECT TableName, ShapeType, HasZ, HasM, SRID, ExtentLeft, ExtentBottom, "
                              "ExtentRight, ExtentTop, IdxOriginX, IdxOriginY, IdxGridSize "
                              "FROM GDB_GeomColumns").fetchall()
            srefs = {r.SRID: r.SRTEXT for r in cur.execute("SELECT SRID, SRTEXT FROM GDB_SpatialRefs")}
        except Exception as e:                           # noqa: BLE001
            raise TransferError("not_pgdb", str(e))
        info = DbInfo(path)
        for r in geo:
            if r.TableName.upper().startswith("GDB_"):
                continue
            li = LayerInfo()
            li.name, li.shape_type = r.TableName, r.ShapeType
            li.kind = SHAPE_TYPE_TO_KIND.get(r.ShapeType)
            li.has_z, li.has_m = bool(r.HasZ), bool(r.HasM)
            li.srid, li.srtext = r.SRID, srefs.get(r.SRID, "")
            li.extent = (r.ExtentLeft, r.ExtentBottom, r.ExtentRight, r.ExtentTop)
            li.origin_x, li.origin_y, li.grid = r.IdxOriginX, r.IdxOriginY, r.IdxGridSize
            li.fields = _columns(cur, r.TableName)
            li.count = cur.execute("SELECT COUNT(*) FROM [{}]".format(r.TableName)).fetchval()
            info.layers[li.name] = li
        return info
    finally:
        if own:
            conn.close()


def match_layers(src, dst):
    """ფენების შესაბამისობა ტიპის მიხედვით.

    აბრუნებს ``(mapping, ambiguous)``: ``mapping[kind] = (src_name, dst_name)`` — თუ თითო მხარეს
    ზუსტად ერთი ფენაა; ``ambiguous[kind] = (src_names, dst_names)`` — თუ არა (მომხმარებელმა უნდა მიუთითოს).
    სახელები ერთმანეთს არ უნდა ემთხვეოდეს — ვეყრდნობით გეომეტრიის ტიპს."""
    mapping, ambiguous = {}, {}
    for kind in KINDS:
        s = [l.name for l in src.by_kind(kind)]
        d = [l.name for l in dst.by_kind(kind)]
        if len(s) == 1 and len(d) == 1:
            mapping[kind] = (s[0], d[0])
        else:
            ambiguous[kind] = (s, d)
    return mapping, ambiguous


def same_file(a, b):
    """ერთი და იგივე ფაილია? (გზების სხვაობა — რეგისტრი/სიმბოლური ბმული — არ მოგვატყუებს)"""
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


# ---------------------------------------------------------------------------
# ლოგი
# ---------------------------------------------------------------------------
class TransferLog(object):
    """ტექსტური ლოგი დროის ბეჭდით: ფაილში + (არჩევით) UI-ში."""

    def __init__(self, path=None, sink=None):
        self.path, self.sink, self.lines = path, sink, []
        self._fh = None
        if path:
            try:
                self._fh = open(path, "w", encoding="utf-8")
            except OSError:
                self._fh = None
                self.path = None

    def __call__(self, msg, level="INFO"):
        line = "{} [{}] {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), level, msg)
        self.lines.append(line)
        if self._fh:
            self._fh.write(line + "\n")
            self._fh.flush()
        if self.sink:
            self.sink(line, level)

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None


# ---------------------------------------------------------------------------
# ანალიზი (მხოლოდ კითხვა) და ჩაწერა
# ---------------------------------------------------------------------------
class LayerPlan(object):
    """ერთი ფენის გეგმა/შედეგი."""

    def __init__(self, kind, src_name, dst_name):
        self.kind, self.src_name, self.dst_name = kind, src_name, dst_name
        self.found = 0                  # წყაროში არჩეულ წელში
        self.duplicates = 0             # მიმღებში იგივე ნომერი + იგივე წელი → გამოტოვებულია
        self.no_number = 0              # ნომრის გარეშე → ვერ შემოწმდა, გამოტოვებულია
        self.to_insert = []             # [(row_values_dict)] — ჩასასმელი
        self.inserted = 0
        self.errors = []                # [(oid, werilis_no, მიზეზი)] — ჩაუწერელი
        self.missing_dates = []         # [(oid, werilis_no)] — NULL თარიღი (მთელ წყარო ფენაში)
        self.invalid_dates = []         # [(oid, werilis_no, თარიღი)]
        self.same_no_other_year = 0     # მიმღებში იგივე ნომერია, მაგრამ სხვა წლით → ჩაიწერება
        self.src_internal_dup_nos = []  # წყაროს შიგნით განმეორებადი ნომრები (ორაზროვნება — ანგარიშში)
        self.unmatched_fields = []      # წყაროს ველები, რომლებიც მიმღებში არ არის
        self.reprojected = False
        self.blocked = None             # (კოდი, დეტალი) — ფენა არ გადაიტანება
        self.index_missing_in_src = 0   # წყაროს ჩანაწერები სივრცითი ინდექსის გარეშე (ინფო)
        self.verified = False

    @property
    def to_insert_count(self):
        return len(self.to_insert)


class Plan(object):
    def __init__(self, src_path, dst_path, year):
        self.src_path, self.dst_path, self.year = src_path, dst_path, int(year)
        self.layers = []                # [LayerPlan]
        self.started = time.time()
        self.backup_path = None

    def totals(self):
        return {
            "found": sum(l.found for l in self.layers),
            "duplicates": sum(l.duplicates for l in self.layers),
            "no_number": sum(l.no_number for l in self.layers),
            "to_insert": sum(l.to_insert_count for l in self.layers),
            "inserted": sum(l.inserted for l in self.layers),
            "errors": sum(len(l.errors) for l in self.layers),
            "bad_dates": sum(len(l.missing_dates) + len(l.invalid_dates) for l in self.layers),
        }


def analyze(src_path, dst_path, mapping, year, log=None, progress=None, cancel=None,
            src_info=None, dst_info=None):
    """წყაროს წაკითხვა + მიმღების შემოწმება. **არაფერს წერს.** აბრუნებს ``Plan``-ს.

    ``mapping[kind] = (src_layer, dst_layer)``. ``progress(kind, done, total)``; ``cancel()`` — True-ზე წყდება."""
    log = log or TransferLog()
    cancel = cancel or (lambda: False)
    lo, hi = year_bounds(year)
    plan = Plan(src_path, dst_path, year)
    sc = connect(src_path, "ro")
    dc = connect(dst_path, "ro")
    try:
        src_info = src_info or inspect_db(src_path, sc)
        dst_info = dst_info or inspect_db(dst_path, dc)
        s_cur, d_cur = sc.cursor(), dc.cursor()
        for kind in KINDS:
            if kind not in mapping:
                continue
            if cancel():
                raise TransferError("cancelled")
            sname, dname = mapping[kind]
            lp = LayerPlan(kind, sname, dname)
            plan.layers.append(lp)
            sl, dl = src_info.layers[sname], dst_info.layers[dname]
            log("{}: {} → {}".format(kind.upper(), sname, dname))

            # --- გეომეტრიის ტიპი / Z/M / CRS ---
            if sl.kind != kind or dl.kind != kind:
                lp.blocked = ("kind_mismatch", "{}/{}".format(sl.kind, dl.kind))
                log("  ⛔ geometry type mismatch ({}/{}) — layer skipped".format(sl.kind, dl.kind), "ERROR")
                continue
            if sl.has_z or sl.has_m or dl.has_z or dl.has_m:
                lp.blocked = ("has_zm", "")
                log("  ⛔ Z/M geometry is not supported — layer skipped", "ERROR")
                continue
            rel = crs_relation(sl.srtext, dl.srtext)
            transform = None
            if rel == "unknown":
                lp.blocked = ("crs_unknown", "")
                log("  ⛔ coordinate systems differ and no well-defined transformation exists — layer skipped", "ERROR")
                continue
            if rel == "reproject":
                transform = make_transformer(sl.srtext, dl.srtext)
                lp.reprojected = True
                log("  ⚠ coordinate systems differ — geometry will be reprojected", "WARN")

            # --- ველები ---
            fplan = plan_fields(sl.fields, dl.fields)
            lp.unmatched_fields = list(fplan.unmatched_src)
            if fplan.unmatched_src:
                log("  ⚠ source fields NOT present in destination (will not be transferred): {}".format(
                    ", ".join(fplan.unmatched_src)), "WARN")
            if not fplan.ok:
                msgs = ["{} ({})".format(f, d) for _c, f, d in fplan.blockers] + \
                       ["required destination field missing in source: " + f for f in fplan.missing_required]
                lp.blocked = ("schema", "; ".join(msgs))
                log("  ⛔ schema incompatible: " + "; ".join(msgs), "ERROR")
                continue
            key_src = find_field(sl.field_names(), KEY_FIELD)
            key_dst = find_field(dl.field_names(), KEY_FIELD)
            dsrc = find_field(sl.field_names(), DATE_FIELD)
            ddst = find_field(dl.field_names(), DATE_FIELD)
            if not (key_src and key_dst and dsrc and ddst):
                lp.blocked = ("no_key_fields", "{}/{} · {}/{}".format(key_src, key_dst, dsrc, ddst))
                log("  ⛔ cannot identify '{}' / date fields — please map them".format(KEY_FIELD), "ERROR")
                continue

            # --- თარიღები მთელ წყარო ფენაში: NULL და არასწორი ---
            for r in s_cur.execute("SELECT OBJECTID, [{k}] FROM [{t}] WHERE [{d}] IS NULL".format(
                    k=key_src, t=sname, d=dsrc)):
                lp.missing_dates.append((r[0], r[1]))
            for r in s_cur.execute("SELECT OBJECTID, [{k}], [{d}] FROM [{t}] WHERE [{d}] < ? OR [{d}] >= ?".format(
                    k=key_src, t=sname, d=dsrc),
                    (datetime.datetime(MIN_VALID_YEAR, 1, 1), datetime.datetime(MAX_VALID_YEAR + 1, 1, 1))):
                lp.invalid_dates.append((r[0], r[1], r[2]))

            # --- მიმღების „ამ წლის“ ნომრების სნეპშოტი (გადატანამდე!) ---
            dest_year = set()
            dest_any = set()
            for (no, dt) in d_cur.execute("SELECT [{k}], [{d}] FROM [{t}]".format(k=key_dst, d=ddst, t=dname)):
                n = normalize_no(no)
                if n is None:
                    continue
                dest_any.add(n)
                if in_year(dt, year):
                    dest_year.add(n)

            # --- წყარო ჩანაწერები არჩეული წლისთვის ---
            copy_pairs = fplan.copy
            sel = ", ".join("[{}]".format(s) for s, _d in copy_pairs)
            rows = s_cur.execute("SELECT OBJECTID, {sel} FROM [{t}] WHERE [{d}] >= ? AND [{d}] < ? ORDER BY OBJECTID"
                                 .format(sel=sel, t=sname, d=dsrc), (lo, hi)).fetchall()
            lp.found = len(rows)
            log("  found in source ({}): {}".format(year, lp.found))
            col_index = {s: i + 1 for i, (s, _d) in enumerate(copy_pairs)}
            shape_i = col_index.get(find_field([s for s, _ in copy_pairs], "SHAPE") or "SHAPE")
            seen_nos = {}
            for n_done, r in enumerate(rows, start=1):
                if cancel():
                    raise TransferError("cancelled")
                if progress:
                    progress(kind, n_done, lp.found)
                oid = r[0]
                no_raw = r[col_index[key_src]]
                verdict = decide(no_raw, dest_year)
                no = normalize_no(no_raw)
                if no is not None:
                    seen_nos[no] = seen_nos.get(no, 0) + 1
                if verdict == "duplicate":
                    lp.duplicates += 1
                    continue
                if verdict == "no_number":
                    lp.no_number += 1
                    lp.errors.append((oid, no_raw, "no_number"))
                    continue
                if no in dest_any:
                    lp.same_no_other_year += 1
                # გეომეტრია
                blob = r[shape_i] if shape_i else None
                try:
                    if blob is None:
                        raise ValueError("empty geometry")
                    bb = shape_bbox(blob)
                    if shape_kind(blob) != kind:
                        raise ValueError("unexpected shape type {}".format(shape_type(blob)))
                    if transform is not None:
                        blob = reproject_shape(blob, transform)
                        bb = shape_bbox(blob)
                except ValueError as e:
                    lp.errors.append((oid, no_raw, "geometry: {}".format(e)))
                    continue
                # ტექსტის სიგრძეები
                bad = None
                for s, d, size in fplan.length_checked:
                    v = r[col_index[s]]
                    if isinstance(v, str) and len(v) > size:
                        bad = "field {} too long ({} > {})".format(s, len(v), size)
                        break
                if bad:
                    lp.errors.append((oid, no_raw, bad))
                    continue
                values = {}
                for s, d in copy_pairs:
                    v = r[col_index[s]]
                    values[d] = bytes(blob) if (d.upper() == "SHAPE") else v
                lp.to_insert.append({"src_oid": oid, "no": no, "values": values, "bbox": bb,
                                     "blob": bytes(blob)})
            lp.src_internal_dup_nos = sorted(n for n, c in seen_nos.items()
                                             if c > 1 and n not in dest_year)
            if lp.src_internal_dup_nos:
                log("  ⚠ ambiguity: {} werilis_no value(s) occur several times inside the source selection "
                    "(all are inserted because the destination has none for {}): {}".format(
                        len(lp.src_internal_dup_nos), year,
                        ", ".join(lp.src_internal_dup_nos[:MAX_LOGGED_IDS]) +
                        (" …" if len(lp.src_internal_dup_nos) > MAX_LOGGED_IDS else "")), "WARN")
            if lp.missing_dates:
                log("  ⚠ records with MISSING date in source ({}): {}".format(
                    len(lp.missing_dates), ", ".join("OBJECTID {} ({})".format(o, n)
                                                    for o, n in lp.missing_dates[:MAX_LOGGED_IDS])), "WARN")
            if lp.invalid_dates:
                log("  ⚠ records with INVALID date in source ({}): {}".format(
                    len(lp.invalid_dates), ", ".join("OBJECTID {} ({}, {})".format(o, n, d)
                                                    for o, n, d in lp.invalid_dates[:MAX_LOGGED_IDS])), "WARN")
            log("  already in destination ({}): {}".format(year, lp.duplicates))
            log("  to insert: {} (same number but another year in destination: {}) | errors: {}".format(
                lp.to_insert_count, lp.same_no_other_year, len(lp.errors)))
        return plan
    finally:
        sc.close()
        dc.close()


def free_space_ok(path, needed):
    try:
        return shutil.disk_usage(os.path.dirname(os.path.abspath(path))).free > needed * 1.1
    except OSError:
        return True


def check_writable(path):
    """მიმღების ჩაწერისთვის მზადობა: ექსკლუზიურად გახსნა-დახურვა (არაფერს წერს).

    სხვა პროგრამას (მაგ. ArcGIS Pro-ს, Access-ს) ღია აქვს → ``TransferError("locked")``."""
    conn = connect(path, "excl")
    conn.close()


def default_log_path(dst_path, fallback_dir=None):
    """ლოგის ფაილი: მიმღების გვერდით (ჩაუწერელია → fallback საქაღალდეში)."""
    name = "db_transfer_{}.log".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    for folder in (os.path.dirname(os.path.abspath(dst_path)), fallback_dir):
        if folder and os.path.isdir(folder) and os.access(folder, os.W_OK):
            return os.path.join(folder, name)
    return name


def make_backup(dst_path, log=None):
    """მიმღების ასლი ჩაწერამდე: ``<სახელი>_backup_YYYYMMDD_HHMMSS.mdb`` იმავე საქაღალდეში."""
    stem, ext = os.path.splitext(dst_path)
    out = "{}_backup_{}{}".format(stem, datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), ext)
    size = os.path.getsize(dst_path)
    if not free_space_ok(dst_path, size):
        raise TransferError("no_space", out)
    shutil.copy2(dst_path, out)
    if log:
        log("backup of destination: {} ({:.1f} MB)".format(out, size / 1048576.0))
    return out


def execute(plan, dst_info=None, log=None, progress=None, cancel=None, backup=True):
    """გეგმის ჩაწერა მიმღებში — **ერთი ტრანზაქცია ყველა ფენისთვის**.

    ნებისმიერი ბაზისმხრივი შეცდომის/გაუქმების/დადასტურების შეუსაბამობის დროს — სრული ROLLBACK
    (მიმღები უცვლელი რჩება). წარმატებისას: კომიტი + ხელახალი წაკითხვით ვერიფიკაცია."""
    log = log or TransferLog()
    cancel = cancel or (lambda: False)
    todo = [l for l in plan.layers if l.to_insert and not l.blocked]
    if not todo:
        log("nothing to insert")
        return plan
    backup_path = make_backup(plan.dst_path, log) if backup else None
    plan.backup_path = backup_path
    conn = connect(plan.dst_path, "excl")        # Exclusive: სხვა პროგრამას ღია აქვს → გვეტყვის
    try:
        cur = conn.cursor()
        info = dst_info or inspect_db(plan.dst_path, conn)
        before = {}
        for lp in todo:
            dl = info.layers[lp.dst_name]
            before[lp.kind] = (cur.execute("SELECT COUNT(*) FROM [{}]".format(lp.dst_name)).fetchval(),
                               cur.execute("SELECT COUNT(*) FROM [{}_SHAPE_Index]".format(lp.dst_name)).fetchval())
        new_ids = {}
        extents = {}
        total = sum(l.to_insert_count for l in todo)
        done = 0
        for lp in todo:
            dl = info.layers[lp.dst_name]
            cols = list(lp.to_insert[0]["values"].keys())
            sql = "INSERT INTO [{t}] ({c}) VALUES ({p})".format(
                t=lp.dst_name, c=", ".join("[{}]".format(c) for c in cols), p=", ".join("?" * len(cols)))
            isql = "INSERT INTO [{t}_SHAPE_Index] (IndexedObjectId, MinGX, MinGY, MaxGX, MaxGY) VALUES (?,?,?,?,?)".format(
                t=lp.dst_name)
            ids = []
            ext = list(dl.extent) if dl.extent else [None] * 4
            for item in lp.to_insert:
                if cancel():
                    raise TransferError("cancelled")
                try:
                    cur.execute(sql, tuple(item["values"][c] for c in cols))
                except pyodbc_error() as e:
                    # ერთი ჩანაწერის შეზღუდვის დარღვევა (მაგ. აუცილებელი ველი ცარიელია): Jet-ი
                    # მხოლოდ ამ ინსტრუქციას აუქმებს, ტრანზაქცია ცოცხალია. ჩანაწერი ანგარიშში გადადის,
                    # დანარჩენი გრძელდება — არაფერი ნახევრად არ იწერება.
                    lp.errors.append((item["src_oid"], item["no"], "insert: " + str(e).split("]")[-1].strip()[:160]))
                    done += 1
                    continue
                oid = cur.execute("SELECT @@IDENTITY").fetchval()
                gx = index_cells(item["bbox"], dl.origin_x, dl.origin_y, dl.grid)
                cur.execute(isql, (oid,) + gx)
                ids.append((oid, item))
                b = item["bbox"]
                ext = [b[0] if ext[0] is None else min(ext[0], b[0]),
                       b[1] if ext[1] is None else min(ext[1], b[1]),
                       b[2] if ext[2] is None else max(ext[2], b[2]),
                       b[3] if ext[3] is None else max(ext[3], b[3])]
                done += 1
                if progress:
                    progress(lp.kind, done, total)
            new_ids[lp.kind] = ids
            extents[lp.kind] = (ext, dl.extent)
        # ექსტენტი: მხოლოდ თუ გაიზარდა
        for lp in todo:
            ext, old = extents[lp.kind]
            if old is None or tuple(ext) != tuple(old):
                cur.execute("UPDATE GDB_GeomColumns SET ExtentLeft=?, ExtentBottom=?, ExtentRight=?, ExtentTop=? "
                            "WHERE TableName=?", (ext[0], ext[1], ext[2], ext[3], lp.dst_name))
        # ვერიფიკაცია კომიტამდე
        for lp in todo:
            n_before, i_before = before[lp.kind]
            n_after = cur.execute("SELECT COUNT(*) FROM [{}]".format(lp.dst_name)).fetchval()
            i_after = cur.execute("SELECT COUNT(*) FROM [{}_SHAPE_Index]".format(lp.dst_name)).fetchval()
            k = len(new_ids[lp.kind])
            if n_after != n_before + k or i_after != i_before + k:
                raise TransferError("verify_failed", "{}: rows {}→{} (+{} expected), index {}→{}".format(
                    lp.kind, n_before, n_after, k, i_before, i_after))
            # ჩაწერილი ჩანაწერების შედარება (გეომეტრია ბაიტ-ბაიტ, გასაღები, თარიღი)
            kf = find_field(list(lp.to_insert[0]["values"]), KEY_FIELD)
            for oid, item in new_ids[lp.kind]:
                row = cur.execute("SELECT SHAPE, [{k}] FROM [{t}] WHERE OBJECTID=?".format(k=kf, t=lp.dst_name),
                                  (oid,)).fetchone()
                if row is None or bytes(row[0]) != item["blob"] or normalize_no(row[1]) != item["no"]:
                    raise TransferError("verify_failed", "{}: OBJECTID {} differs from source".format(lp.kind, oid))
        if cancel():
            raise TransferError("cancelled")
        conn.commit()
        for lp in todo:
            lp.inserted = len(new_ids[lp.kind])
            lp.verified = True
            log("{}: inserted {} (verified)".format(lp.kind.upper(), lp.inserted))
    except Exception as e:                               # noqa: BLE001
        try:
            conn.rollback()
            log("ROLLBACK — destination left unchanged", "WARN")
        finally:
            conn.close()
        if isinstance(e, TransferError):
            raise
        raise friendly_error(e)
    conn.close()
    return plan
