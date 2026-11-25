# -*- coding: utf-8 -*-
"""ქართული→ლათინური ტრანსლიტერაცია და shapefile-ის ობიექტების დათვლა.

სუფთა ლოგიკა — tkinter/GIS დამოკიდებულებების გარეშე, რომ ცალკე ტესტირებადი
იყოს. აქედან იმპორტს აკეთებს ``tools.rename_transliterate``.
"""

import os
import re

# ---- ქართული → ლათინური ცხრილი --------------------------------------------
# ყ → y (მომხმარებლის მაგალითის მიხედვით: „საყრდენი“ → „sayrdeni“).
GEO2LAT = {
    "ა": "a", "ბ": "b", "გ": "g", "დ": "d", "ე": "e", "ვ": "v", "ზ": "z",
    "თ": "t", "ი": "i", "კ": "k", "ლ": "l", "მ": "m", "ნ": "n", "ო": "o",
    "პ": "p", "ჟ": "zh", "რ": "r", "ს": "s", "ტ": "t", "უ": "u", "ფ": "f",
    "ქ": "k", "ღ": "gh", "ყ": "y", "შ": "sh", "ჩ": "ch", "ც": "ts", "ძ": "dz",
    "წ": "ts", "ჭ": "ch", "ხ": "kh", "ჯ": "j", "ჰ": "h",
    # არქაული / იშვიათი
    "ჱ": "e", "ჲ": "y", "ჳ": "w", "ჴ": "q", "ჵ": "o", "ჶ": "f",
}
GEO_RANGE = re.compile(r"[Ⴀ-ჿ]")   # ქართული ასოს არსებობის შემოწმება


# ---- ლათინური → ქართული (რეგისტრზე დამოკიდებული) ---------------------------
# სტანდარტული სქემა (მომხმარებლის მაგალითის მიხედვით): t→ტ, T→თ, q→ქ, W→ჭ …
# გამოიყენება „კონვერტერისთვის“: მომხმარებელი ლათინურით აკრეფს, ქართული გამოდის.
LAT2GEO = {
    "a": "ა", "b": "ბ", "g": "გ", "d": "დ", "e": "ე", "v": "ვ", "z": "ზ",
    "T": "თ", "i": "ი", "k": "კ", "l": "ლ", "m": "მ", "n": "ნ", "o": "ო",
    "p": "პ", "J": "ჟ", "r": "რ", "s": "ს", "t": "ტ", "u": "უ", "f": "ფ",
    "q": "ქ", "R": "ღ", "y": "ყ", "S": "შ", "C": "ჩ", "c": "ც", "Z": "ძ",
    "w": "წ", "W": "ჭ", "x": "ხ", "j": "ჯ", "h": "ჰ",
}


def lat_to_geo(text):
    """ლათინური (ტრანსლიტ.) → ქართული. უცნობი სიმბოლო (სფეისი/ციფრი/…) უცვლელი."""
    return "".join(LAT2GEO.get(ch, ch) for ch in text or "")


def transliterate(name):
    """ფაილის სახელი → ლათინური.

    • ქართული ასო → ლათინური შესაბამისობა
    • ლათინური ასო, ციფრი და წერტილი (გაფართოებისთვის) — უცვლელი
    • ნებისმიერი სხვა სიმბოლო (სფეისი, მძიმე, ტირე, ფრჩხილი და ა.შ.) → „_“

    ზედიზედ მრავალი „_“ ერთამდე იკუმშება; წერტილის წინ და კიდეებში „_“ იშლება.
    """
    out = []
    for ch in name:
        if ch in GEO2LAT:
            out.append(GEO2LAT[ch])
        elif ch.isascii() and (ch.isalnum() or ch == "."):
            out.append(ch)               # ლათინური/ციფრი/წერტილი — უცვლელი
        else:
            out.append("_")              # სფეისი, მძიმე, ნებისმიერი სხვა სიმბოლო
    s = re.sub(r"_{2,}", "_", "".join(out))
    s = re.sub(r"_+\.", ".", s)          # წერტილის წინ „_“ არ დავტოვოთ
    return s.strip("_")


def _sibling(path, ext):
    """მოცემული ფაილის გვერდით მყოფი იმავე base-ის ფაილი მითითებული
    გაფართოებით (რეგისტრის მიუხედავად). აბრუნებს გზას ან None."""
    base = os.path.splitext(path)[0]
    for e in (ext.lower(), ext.upper()):
        cand = base + e
        if os.path.exists(cand):
            return cand
    return None


def feature_count(shp_path):
    """Shapefile-ის ობიექტების რაოდენობა — დამოკიდებულებების გარეშე.

    ObjectCount == .dbf-ის ჩანაწერების რაოდენობა (header-ის ბაიტები 4..7,
    little-endian uint32). თუ .dbf არ არის — .shp-ის header-ის სიგრძით
    ვადგენთ ცარიელობას (100 ბაიტი = მხოლოდ header, 0 გეომეტრია).
    აბრუნებს int-ს, ან None თუ ვერ წავიკითხეთ."""
    dbf = _sibling(shp_path, ".dbf")
    if dbf:
        try:
            with open(dbf, "rb") as f:
                head = f.read(8)
            if len(head) >= 8:
                return int.from_bytes(head[4:8], "little")
        except OSError:
            pass
    # fallback — .shp-ის header (ბაიტები 24..27, big-endian, 16-ბიტიან სიტყვებში)
    try:
        with open(shp_path, "rb") as f:
            head = f.read(100)
        if len(head) >= 28:
            words = int.from_bytes(head[24:28], "big")
            return 0 if words * 2 <= 100 else -1   # -1 = „მასალა დევს“, ზუსტი N უცნობია
    except OSError:
        pass
    return None


# ---- ფაილების გადარქმევა (GUI-ს გარეშე; იყენებს კლასიკური და V2 ხელსაწყო) ----
def iter_files(folder, recursive=False):
    """(საქაღალდე, ფაილის სახელი) — მხოლოდ ფაილები; recursive=True — ქვესაქაღალდეებიც."""
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                yield root, f
    else:
        for f in os.listdir(folder):
            if os.path.isfile(os.path.join(folder, f)):
                yield folder, f


def dataset_key(folder, name):
    """ერთი მონაცემის ფაილების ჯგუფი: იგივე საქაღალდე + სახელი პირველ წერტილამდე
    (a.shp, a.dbf, a.shx, a.shp.xml … → ერთი ჯგუფი)."""
    return os.path.normcase(folder), name.split(".", 1)[0].lower()


def build_plan(folder, recursive=False):
    """გადარქმევის გეგმა: dict-ების სია {dir, old, new, status}.

    status: ok / conflict (ორი ფაილი ერთსა და იმავე სახელს იძლევა) / exists (სამიზნე
    უკვე არსებობს) / group (იმავე მონაცემის სხვა ფაილი ვერ გადაერქმევა — მთელი ჯგუფი
    გამოტოვდება, რომ shapefile არ დაიშალოს)."""
    items = []
    target_count = {}
    for d, name in iter_files(folder, recursive):
        if not GEO_RANGE.search(name):
            continue
        new = transliterate(name)
        if new == name:
            continue
        items.append({"dir": d, "old": name, "new": new, "status": "ok"})
        key = (os.path.normcase(d), os.path.normcase(new))
        target_count[key] = target_count.get(key, 0) + 1
    for it in items:
        key = (os.path.normcase(it["dir"]), os.path.normcase(it["new"]))
        dst = os.path.join(it["dir"], it["new"])
        if target_count[key] > 1:
            it["status"] = "conflict"
        elif os.path.exists(dst) and \
                os.path.normcase(dst) != os.path.normcase(os.path.join(it["dir"], it["old"])):
            it["status"] = "exists"
    bad = {dataset_key(it["dir"], it["old"]) for it in items if it["status"] != "ok"}
    for it in items:
        if it["status"] == "ok" and dataset_key(it["dir"], it["old"]) in bad:
            it["status"] = "group"
    items.sort(key=lambda it: (it["dir"].lower(), it["old"].lower()))
    return items


def apply_plan(plan, log=None, cancel=None):
    """გადარქმევა მონაცემის ჯგუფებად. თუ ჯგუფის ერთი ფაილი ვერ გადაერქვა (მაგ.
    ArcGIS-ს აქვს გახსნილი), იმავე ჯგუფის უკვე გადარქმეული ფაილები უკან ბრუნდება.

    აბრუნებს (ok, skipped, undo); undo = [(ახალი_გზა, ძველი_გზა), …]."""
    log = log or (lambda m: None)
    groups = {}
    for it in plan:
        groups.setdefault(dataset_key(it["dir"], it["old"]), []).append(it)
    ok = skipped = 0
    undo = []
    for members in groups.values():
        doable = [it for it in members if it["status"] == "ok"]
        skipped += len(members) - len(doable)
        if not doable:
            continue
        if cancel and cancel():
            skipped += len(doable)
            continue
        done = []
        failed = None
        for it in doable:
            src = os.path.join(it["dir"], it["old"])
            dst = os.path.join(it["dir"], it["new"])
            try:
                if os.path.exists(dst):                      # ბოლო წამის დაცვა — არაფერს ვაწერთ ზემოდან
                    raise FileExistsError(dst)
                os.rename(src, dst)
                done.append((dst, src, it))
            except OSError as e:
                failed = (it, e)
                break
        if failed:
            for dst, src, _it in reversed(done):
                try:
                    os.rename(dst, src)
                except OSError as e:
                    log("✗ {} → {}: could not restore: {}".format(os.path.basename(dst), os.path.basename(src), e))
                    undo.append((dst, src))
            log("✗ {}: {} — {} file(s) of this dataset left unchanged".format(failed[0]["old"], failed[1], len(doable)))
            skipped += len(doable)
            continue
        for dst, src, it in done:
            undo.append((dst, src))
            log("✓ {} → {}".format(it["old"], it["new"]))
            ok += 1
    return ok, skipped, undo


def undo_renames(undo, log=None):
    """ბოლო გადარქმევის დაბრუნება. ახალი უნდა არსებობდეს, ძველი — არა (ზემოდან არ ვწერთ).
    აბრუნებს (ok, skipped)."""
    log = log or (lambda m: None)
    ok = skipped = 0
    for new_path, old_path in reversed(undo):
        if not os.path.exists(new_path) or os.path.exists(old_path):
            log("↷ {}".format(os.path.basename(new_path)))
            skipped += 1
            continue
        try:
            os.rename(new_path, old_path)
            log("↩ {} → {}".format(os.path.basename(new_path), os.path.basename(old_path)))
            ok += 1
        except OSError as e:
            log("✗ {}: {}".format(os.path.basename(new_path), e))
            skipped += 1
    return ok, skipped


def check_contents(folder, recursive=False):
    """საქაღალდის ყველა .shp: [(გზა, რაოდენობა)], რაოდენობა — feature_count-ის შედეგი
    (0 = ცარიელი, -1 = მასალა დევს, None = ვერ წავიკითხეთ)."""
    shps = sorted((os.path.join(d, n) for d, n in iter_files(folder, recursive) if n.lower().endswith(".shp")),
                  key=lambda p: os.path.basename(p).lower())
    return [(p, feature_count(p)) for p in shps]
