# -*- coding: utf-8 -*-
"""ნაკვეთის ძებნის სუფთა ლოგიკა — GUI-სგან დამოუკიდებელი (ტესტირებადი).

აქ არ არის tkinter. მძიმე პაკეტები (pandas / geopandas) იტვირთება მხოლოდ
შედეგის ჩაწერისას; ``pyogrio`` კი მოდულის დონეზე იმპორტდება „რბილად“, რომ
მოდული პაკეტის გარეშეც იმპორტადი იყოს (ტესტში monkeypatch-ით იცვლება).
"""

import os
import re
import traceback

# pyogrio (GDAL) მძიმეა და ~0.6 წმ სჭირდება — მოდულის დონეზე არ ვტვირთავთ, რომ
# ხელსაწყოს პირველი გახსნა არ შეანელოს. run_search-ში lazy-ად იტვირთება (ფონურ
# ნაკადში). ტესტში monkeypatch-ით იცვლება, ამიტომ მოდულის გლობალად რჩება.
pyogrio = None

CHUNK_SIZE = 1000          # რამდენ კოდს ვეძებთ ერთ მოთხოვნაში


def normalize(code):
    """საკადასტრო კოდის სტანდარტიზება CADCODE-ის ფორმატში (NN.NN.NN.NNN).

    სხვადასხვა ფორმით ჩაწერილი კოდი — ჰარეებით, წერტილებით ან შერეულად
    ('71 63 80 094', '71.63 .80 094', '71,63,80,094') — ერთ კანონიკურ,
    წერტილებით გამოყოფილ ფორმას მიჰყავს, რომ CADCODE სვეტს ზუსტად დაემთხვეს.
    ჯგუფებად დაყოფა ხდება ციფრების მიხედვით; წამყვანი ნულები რჩება.
    """
    if code is None:
        return ""
    s = str(code).strip()
    if not s:
        return ""
    groups = re.findall(r"\d+", s)
    if not groups:
        return s
    # უგამყოფოდ ჩაწერილი კოდი სტანდარტული სიგრძით — დავყოთ 2.2.2.3(.3) ჯგუფებად
    if len(groups) == 1:
        d = groups[0]
        if len(d) == 9:       # NN.NN.NN.NNN
            groups = [d[0:2], d[2:4], d[4:6], d[6:9]]
        elif len(d) == 12:    # NN.NN.NN.NNN.NNN (ქვენაკვეთი)
            groups = [d[0:2], d[2:4], d[4:6], d[6:9], d[9:12]]
    return ".".join(groups)


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def parse_manual_codes(text):
    """ხელით ჩაწერილი ტექსტიდან კოდების ამოღება (ხაზი, მძიმე, წერტილ-მძიმე, ტაბი)."""
    parts = re.split(r"[\r\n,;\t]+", text)
    seen = set()
    result = []
    for p in parts:
        c = normalize(p)
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result


def run_search(gdb, layer, field, codes, out_path, log, done, tr,
               formats=("shp", "gpkg"), progress=None, cancel=None):
    """
    log(msg)  -> სტატუსის ჩაწერა
    done(result_dict) -> დასრულებისას გამოძახება
    tr(key, **fmt) -> თარგმანი
    formats -> რომელი ფაილები შეიქმნას: ("shp", "gpkg"); ცარიელი => მხოლოდ ძებნა
    progress(i, n) -> პროგრესის განახლება (არჩევით)
    cancel() -> True თუ მომხმარებელმა გააუქმა (არჩევით)
    """
    formats = set(formats or ())
    try:
        global pyogrio                 # lazy — ფონურ ნაკადში (ტესტში monkeypatch-ია)
        if pyogrio is None:
            import pyogrio as _pg
            pyogrio = _pg
        # უნიკალური, ნორმალიზებული კოდები, თანმიმდევრობის შენარჩუნებით
        requested = []
        seen = set()
        for c in codes:
            n = normalize(c)
            if n and n not in seen:
                seen.add(n)
                requested.append(n)

        if not requested:
            done({"error": tr("rs_empty_list")})
            return

        log(tr("rs_count", n=len(requested)))
        log(tr("rs_db", gdb=gdb))
        log(tr("rs_layer", layer=layer, field=field))
        log(tr("rs_searching"))

        frames = []
        found_norm = set()
        total_chunks = (len(requested) + CHUNK_SIZE - 1) // CHUNK_SIZE

        for idx, chunk in enumerate(chunked(requested, CHUNK_SIZE), start=1):
            if cancel and cancel():                 # მომხმარებელმა გააუქმა
                done({"cancelled": True})
                return
            vals = ",".join("'" + c.replace("'", "''") + "'" for c in chunk)
            where = f'"{field}" IN ({vals})'
            gdf = pyogrio.read_dataframe(gdb, layer=layer, where=where)
            if len(gdf) > 0:
                frames.append(gdf)
                for v in gdf[field].tolist():
                    found_norm.add(normalize(v))
            log(tr("rs_block", i=idx, n=total_chunks, k=len(found_norm)))
            if progress:
                progress(idx, total_chunks)

        not_found = [c for c in requested if c not in found_norm]
        found_list = [c for c in requested if c in found_norm]

        # შედეგის ჩაწერა — ორივე ფორმატში (Shapefile + GeoPackage), თუ მოთხოვნილია
        written = 0
        matched = 0
        out_files = []
        result_out_path = None
        if frames:
            import warnings
            import pandas as pd
            import geopandas as gpd
            result = pd.concat(frames, ignore_index=True)
            result = gpd.GeoDataFrame(result, geometry="geometry", crs=frames[0].crs)
            matched = len(result)

            if formats:
                base = os.path.splitext(out_path)[0]
                os.makedirs(os.path.dirname(base), exist_ok=True)
                log(tr("rs_writing", n=matched))

                # GeoPackage — სრული ინფო, უჭრელი
                if "gpkg" in formats:
                    gpkg_path = base + ".gpkg"
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        result.to_file(gpkg_path, driver="GPKG", encoding="utf-8")
                    out_files.append(gpkg_path)
                    result_out_path = gpkg_path
                    log(f"  ✓ GeoPackage: {gpkg_path}")

                # Shapefile
                if "shp" in formats:
                    shp_path = base + ".shp"
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        result.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")
                    out_files.append(shp_path)
                    result_out_path = shp_path  # ვერ ნაპოვნის .txt ამის გვერდით შეინახება
                    log(f"  ✓ Shapefile:  {shp_path}")

                written = matched
            else:
                log(tr("rs_search_only", n=matched))
        else:
            log(tr("rs_none"))

        done({
            "requested": requested,
            "found_list": found_list,
            "not_found": not_found,
            "written": written,
            "matched": matched,
            "out_path": result_out_path,
            "out_files": out_files,
            "search_only": not formats,
        })

    except Exception as e:
        done({"error": f"{e}\n\n{traceback.format_exc()}"})
