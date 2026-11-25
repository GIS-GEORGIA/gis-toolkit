# -*- coding: utf-8 -*-
"""გეობაზის „სიმდიდრის“ (დომენები, ქვეტიპები, ველების თვისებები, ურთიერთობები…) აუდიტი და შედარება.

რისთვის: გადატანის შემდეგ დავრწმუნდეთ, რომ **ახალ ბაზაში არაფერი დაიკარგა** — არც სქემის ელემენტი, არც არსებული
ჩანაწერი. მუშაობს ორივე ფორმატზე:

* **File Geodatabase (.gdb)** — სისტემური ცხრილი ``GDB_Items`` (XML-განმარტებები) GDAL-ით;
* **Personal Geodatabase (.mdb)** — იგივე ``GDB_Items`` ODBC-ით.

``audit(path)`` → dict; ``compare(a, b)`` → განსხვავებების სია (ცარიელი = სქემა იდენტურია; ფენის ექსტენტი
გამოტოვებულია, რადგან ჩანაწერების დამატებისას კანონიერად იზრდება); ``rows_preserved(...)`` — არსებული ჩანაწერები
უცვლელია; ``domain_violations(...)`` — ახალი მნიშვნელობები ეწინააღმდეგება მიმღების დომენს/ქვეტიპს.
"""
import hashlib
import os
import re
import xml.etree.ElementTree as ET

_DYN_RE = re.compile(r"<(XMin|YMin|XMax|YMax|ZMin|ZMax|MMin|MMax)>[^<]*</\1>")
_SKIP_FILES = (".lock",)


def _kind(path):
    p = str(path).rstrip("\\/").lower()
    if p.endswith(".gdb"):
        return "gdb"
    if p.endswith(".mdb"):
        return "mdb"
    raise ValueError("unsupported database: {}".format(path))


def _items_gdb(path):
    import pyogrio
    df = pyogrio.read_dataframe(path, layer="GDB_Items", LIST_ALL_TABLES="YES")
    out = []
    for _i, r in df.iterrows():
        out.append({"name": str(r["Name"] or ""), "path": str(r["Path"] or ""), "type": str(r["Type"] or ""),
                    "definition": str(r["Definition"] or "")})
    return out


def _items_mdb(path):
    from tools import pgdb_transfer_core as core
    cn = core.connect(path, "ro")
    try:
        cur = cn.cursor()
        out = []
        for r in cur.execute("SELECT [Name], [Path], [Type], [Definition] FROM GDB_Items"):
            d = r[3]
            if isinstance(d, (bytes, bytearray)):
                d = bytes(d).decode("utf-8", "replace")
            out.append({"name": str(r[0] or ""), "path": str(r[1] or ""), "type": str(r[2] or ""),
                        "definition": str(d or "")})
        return out
    finally:
        cn.close()


def _txt(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text is not None else ""


def _parse_domain(xml):
    root = ET.fromstring(xml)
    name = _txt(root, "DomainName")
    dom = {"name": name, "field_type": _txt(root, "FieldType"), "coded": None, "range": None}
    cv = root.find("CodedValues")
    if cv is not None:
        dom["coded"] = {}
        for v in cv.findall("CodedValue"):
            dom["coded"][_txt(v, "Code")] = _txt(v, "Name")
    elif root.find("MinValue") is not None:
        dom["range"] = (_txt(root, "MinValue"), _txt(root, "MaxValue"))
    return dom


def _parse_layer(xml):
    root = ET.fromstring(xml)
    lay = {"fields": {}, "subtype_field": _txt(root, "SubtypeFieldName") or None, "subtypes": {},
           "has_globalid": _txt(root, "HasGlobalID").lower() == "true",
           "editor_tracking": _txt(root, "EditorTrackingEnabled").lower() == "true",
           "relationships": sorted(n.text or "" for n in root.findall("RelationshipClassNames/*")),
           "default_subtype": _txt(root, "DefaultSubtypeCode")}
    for f in root.findall("GPFieldInfoExs/GPFieldInfoEx"):
        lay["fields"][_txt(f, "Name")] = {"domain": _txt(f, "DomainName") or None, "type": _txt(f, "FieldType"),
                                          "nullable": _txt(f, "IsNullable").lower() != "false",
                                          "alias": _txt(f, "AliasName"), "required": _txt(f, "Required").lower() == "true",
                                          "editable": _txt(f, "Editable").lower() != "false"}
    for s in root.findall("Subtypes/Subtype"):
        code = _txt(s, "SubtypeCode")
        lay["subtypes"][code] = {"name": _txt(s, "SubtypeName"),
                                 "field_domains": {_txt(fi, "FieldName"): _txt(fi, "DomainName") or None
                                                   for fi in s.findall("FieldInfos/SubtypeFieldInfo")}}
    return lay


def _files(path):
    if os.path.isdir(path):
        out = {}
        for root, _d, fs in os.walk(path):
            for f in fs:
                if f.endswith(_SKIP_FILES):
                    continue
                out[os.path.relpath(os.path.join(root, f), path)] = os.path.getsize(os.path.join(root, f))
        return out
    return {}


def audit(path):
    """``{"kind", "domains", "layers", "items", "files", "item_count"}`` — ბაზის სქემის ანაბეჭდი."""
    kind = _kind(path)
    items = _items_gdb(path) if kind == "gdb" else _items_mdb(path)
    res = {"kind": kind, "domains": {}, "layers": {}, "items": {}, "files": _files(path) if kind == "gdb" else {},
           "item_count": len(items), "errors": []}
    for it in items:
        d = it["definition"]
        if not d.strip():
            continue
        norm = _DYN_RE.sub("", d)
        res["items"][it["path"] or it["name"]] = hashlib.sha1(norm.encode("utf-8")).hexdigest()
        try:
            if "<GPCodedValueDomain" in d[:200] or "<GPRangeDomain" in d[:200]:
                dom = _parse_domain(d)
                res["domains"][dom["name"] or it["name"]] = dom
            elif "<DEFeatureClassInfo" in d[:200] or "<DETableInfo" in d[:200]:
                res["layers"][it["name"]] = _parse_layer(d)
        except ET.ParseError as e:
            res["errors"].append("{}: {}".format(it["name"], e))
    return res


def compare(a, b):
    """``a`` (ორიგინალი) vs ``b`` (ახალი): რა დაიკარგა/შეიცვალა. ცარიელი სია = სქემა იდენტურია."""
    diffs = []
    for name, da in a["domains"].items():
        db = b["domains"].get(name)
        if db is None:
            diffs.append("domain MISSING: {}".format(name))
        elif da["coded"] != db["coded"] or da["range"] != db["range"] or da["field_type"] != db["field_type"]:
            diffs.append("domain CHANGED: {}".format(name))
    for name, la in a["layers"].items():
        lb = b["layers"].get(name)
        if lb is None:
            diffs.append("layer definition MISSING: {}".format(name))
            continue
        for fn, fa in la["fields"].items():
            fb = lb["fields"].get(fn)
            if fb is None:
                diffs.append("field MISSING: {}.{}".format(name, fn))
                continue
            for key in ("domain", "type", "nullable", "alias", "required", "editable"):
                if fa[key] != fb[key]:
                    diffs.append("field property CHANGED: {}.{} {}: {!r} -> {!r}".format(name, fn, key, fa[key], fb[key]))
        for key in ("subtype_field", "subtypes", "has_globalid", "editor_tracking", "relationships", "default_subtype"):
            if la[key] != lb[key]:
                diffs.append("layer property CHANGED: {} {}".format(name, key))
    for path, h in a["items"].items():
        hb = b["items"].get(path)
        if hb is None:
            diffs.append("item MISSING: {}".format(path))
        elif hb != h:
            diffs.append("item definition CHANGED (beyond extent): {}".format(path))
    for f in a["files"]:
        if f not in b["files"]:
            diffs.append("file MISSING in the new database: {}".format(f))
    return diffs


def describe(a):
    """ხალხისთვის გასაგები მოკლე აღწერა: რას შეიცავს ბაზა."""
    nsub = sum(len(l["subtypes"]) for l in a["layers"].values())
    nrel = sum(len(l["relationships"]) for l in a["layers"].values())
    nfd = sum(1 for l in a["layers"].values() for f in l["fields"].values() if f["domain"])
    return "domains: {} | fields with a domain: {} | subtypes: {} | relationship classes: {} | layers/tables described: {}".format(
        len(a["domains"]), nfd, nsub, nrel, len(a["layers"]))


def domain_violations(a, layer, rows):
    """``rows`` — [{ველი: მნიშვნელობა}] (ან (oid, dict)). აბრუნებს ``[(oid, ველი, მნიშვნელობა, მიზეზი)]`` —
    მნიშვნელობა, რომელიც მიმღების კოდირებულ/დიაპაზონურ დომენს ან ქვეტიპის კოდს არ ემთხვევა. NULL ნორმალურია."""
    lay = None
    for n, l in a["layers"].items():
        if n.lower() == layer.lower():
            lay = l
            break
    if lay is None:
        return []
    out = []
    fdom = {fn.lower(): (fn, f["domain"]) for fn, f in lay["fields"].items() if f["domain"]}
    for i, r in enumerate(rows):
        oid, row = (r if isinstance(r, tuple) else (i + 1, r))
        low = {k.lower(): v for k, v in row.items()}
        for lf, (fn, dn) in fdom.items():
            v = low.get(lf)
            dom = a["domains"].get(dn)
            if v is None or dom is None or (isinstance(v, float) and v != v):
                continue
            if dom["coded"] is not None:
                key = str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v)
                if key not in dom["coded"]:
                    out.append((oid, fn, v, "not in coded domain {}".format(dn)))
            elif dom["range"]:
                try:
                    lo, hi = float(dom["range"][0]), float(dom["range"][1])
                    if not lo <= float(v) <= hi:
                        out.append((oid, fn, v, "outside range domain {} [{}..{}]".format(dn, lo, hi)))
                except (TypeError, ValueError):
                    pass
        sf = lay["subtype_field"]
        if sf and lay["subtypes"]:
            v = low.get(sf.lower())
            if v is not None and not (isinstance(v, float) and v != v):
                key = str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v)
                if key not in lay["subtypes"]:
                    out.append((oid, sf, v, "not a valid subtype code"))
    return out


def rows_preserved(original, final, layers):
    """არსებული ჩანაწერები ახალ ბაზაში უცვლელია? ``layers`` — ორივე ბაზის ფენების სახელები (ერთნაირი).
    აბრუნებს ``{ფენა: (ორიგინალში, იდენტურია, ახალში სულ)}``. გეომეტრია + ყველა ატრიბუტი შედარებულია."""
    kind_o, kind_f = _kind(original), _kind(final)
    out = {}
    for name in layers:
        ho, hf = _row_hashes(original, kind_o, name), _row_hashes(final, kind_f, name)
        same = sum(1 for k, h in ho.items() if hf.get(k) == h)
        out[name] = (len(ho), same, len(hf))
    return out


def _row_hashes(path, kind, layer):
    """``{ობიექტის გასაღები: sha1}`` — .gdb: რიგითობა (FID), .mdb: OBJECTID. გეომეტრია ზუსტი კოორდინატებით."""
    out = {}
    if kind == "gdb":
        import pyogrio
        df = pyogrio.read_dataframe(path, layer=layer)
        geom = df.geometry
        cols = [c for c in df.columns if c != geom.name]
        for i in range(len(df)):
            vals = [repr(df.iloc[i][c]) for c in cols]
            g = geom.iloc[i]
            out[i] = hashlib.sha1((("|".join(vals)) + "|" + (g.wkb_hex if g is not None else "")).encode()).hexdigest()
        return out
    from tools import pgdb_transfer_core as core
    cn = core.connect(path, "ro")
    try:
        cur = cn.cursor()
        for r in cur.execute("SELECT * FROM [{}] ORDER BY OBJECTID".format(layer)):
            vals = ["" if v is None else (bytes(v).hex() if isinstance(v, (bytes, bytearray, memoryview)) else repr(v))
                    for v in r]
            out[r[0]] = hashlib.sha1("|".join(vals).encode()).hexdigest()
        return out
    finally:
        cn.close()


def spatial_layers(path):
    """ბაზის სივრცითი ფენების სახელები (შედარებისთვის)."""
    if _kind(path) == "gdb":
        import pyogrio
        return [n for n, g in pyogrio.list_layers(path) if g is not None]
    from tools import pgdb_transfer_core as core
    return list(core.inspect_db(path).layers)


def report(original, final, layers):
    """სრული შედარება → ``(ok: bool, lines: [str])`` (ლოგში/შეჯამებაში საჩვენებლად)."""
    a, b = audit(original), audit(final)
    lines = ["fidelity check: {} -> {}".format(os.path.basename(original), os.path.basename(final)),
             "  original: " + describe(a), "  new:      " + describe(b)]
    diffs = compare(a, b)
    ok = not diffs
    lines += ["  schema: IDENTICAL (domains, subtypes, field properties, relationship classes, item definitions)"] \
        if ok else ["  schema DIFFERENCES ({}):".format(len(diffs))] + ["    - " + d for d in diffs[:40]]
    pres = rows_preserved(original, final, layers)
    for name, (n_o, same, n_f) in pres.items():
        flag = "OK" if same == n_o else "PROBLEM"
        if same != n_o:
            ok = False
        lines.append("  {}: original records {} / identical in the new database {} | new database total {} -> {}".format(
            name, n_o, same, n_f, flag))
    return ok, lines


if __name__ == "__main__":                       # python -m tools.gdb_fidelity <ორიგინალი> <ახალი>
    import sys
    if len(sys.argv) != 3:
        print("usage: python -m tools.gdb_fidelity <original .gdb|.mdb> <new .gdb|.mdb>")
        sys.exit(2)
    good, text = report(sys.argv[1], sys.argv[2], spatial_layers(sys.argv[1]))
    print("\n".join(text))
    sys.exit(0 if good else 1)
