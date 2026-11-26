# -*- coding: utf-8 -*-
"""Database Data Transfer - the workflow WITHOUT a user interface, shared by the classic (Tk) and the V2 (Qt) tool.

The pure transfer engine is ``pgdb_transfer_core`` (ODBC, analysis, duplicate rules, writing in one transaction).
This module holds what both windows do around it, so they cannot drift apart:

* ``Stager``      - a File Geodatabase (.gdb) is converted to a temporary .mdb for the engine; the .gdb itself is
                    never modified;
* ``check`` / ``analysis`` / ``write`` / ``merge`` - the worker steps (they run in a background thread and report
                    through ``progress`` / ``sink`` / ``status`` callbacks);
* ``close_out``   - final log summary, records CSV, history index, central operation history;
* text builders   - check report, confirmation text, summary, completion message (catalogue ``DTR``).

Nothing here shows a dialog; the windows ask the user between the steps.
"""

import os
import time

from tools import pgdb_transfer_core as core
from tools import pgdb_gdb_bridge as gdbx
from tools import gdb_fidelity as fid

DEFAULT_YEAR = 2026

KIND_LABEL = {"point": {"en": "POINT", "ka": "წერტილი (POINT)"},
              "line": {"en": "LINE", "ka": "ხაზი (LINE)"},
              "polygon": {"en": "POLYGON", "ka": "პოლიგონი (POLYGON)"}}

DTR = {
    "heading": {"en": "Database Data Transfer", "ka": "ბაზებს შორის მონაცემთა გადატანა"},
    "desc": {"en": "Copies the spatial features of one year (point, line, polygon) from the source "
                   "Personal Geodatabase into the destination one. A record is skipped when the destination "
                   "already holds the same werilis_no with a date in that year. Nothing is ever deleted or "
                   "overwritten, the source is only read, and the destination is written in one transaction "
                   "(all layers or nothing).",
             "ka": "საწყისი Personal Geodatabase-დან მიმღებში გადააქვს არჩეული წლის სივრცითი ობიექტები "
                   "(წერტილი, ხაზი, პოლიგონი). ჩანაწერი გამოტოვდება, თუ მიმღებში უკვე არის იგივე werilis_no "
                   "ამავე წლის თარიღით. არაფერი არ იშლება/გადაიწერება, წყარო მხოლოდ იკითხება, მიმღებში "
                   "ჩაწერა ერთ ტრანზაქციაშია (ყველა ფენა ერთად — ან არაფერი)."},
    "src_box": {"en": "SOURCE database (data is read from here)",
                "ka": "საწყისი ბაზა — აქედან იკითხება მონაცემები"},
    "dst_box": {"en": "DESTINATION database (data is written here)",
                "ka": "მიმღები ბაზა — აქ ჩაიწერება მონაცემები"},
    "src_lbl": {"en": "Source Database (აირჩიე საწყისი ბაზა):", "ka": "აირჩიე საწყისი ბაზა:"},
    "dst_lbl": {"en": "Destination Database (აირჩიე მიმღები ბაზა):", "ka": "აირჩიე მიმღები ბაზა:"},
    "src_shown": {"en": "SOURCE:  {name}   ({size})", "ka": "საწყისი:  {name}   ({size})"},
    "dst_shown": {"en": "DESTINATION:  {name}   ({size})", "ka": "მიმღები:  {name}   ({size})"},
    "none_shown": {"en": "— not selected —", "ka": "— არ არის არჩეული —"},
    "flow": {"en": "▼  data flows from SOURCE to DESTINATION  ▼",
             "ka": "▼  მონაცემები გადადის საწყისიდან მიმღებში  ▼"},
    "browse": {"en": "…", "ka": "…"},
    "pick_title": {"en": "Select a Personal Geodatabase (.mdb)", "ka": "აირჩიე Personal Geodatabase (.mdb)"},
    "opts": {"en": "Options", "ka": "პარამეტრები"},
    "year": {"en": "Year to transfer:", "ka": "გადასატანი წელი:"},
    "tip_year": {"en": "One year (2026), a range (2024-2026), a list (2024, 2026) or 'all' - every year found in the "
                       "source. Several years are processed ONE AFTER ANOTHER: each year is analysed, confirmed by you "
                       "and written separately (own log per year). Each year = records whose date (TariRI) is from "
                       "1 Jan 00:00:00 to 31 Dec 23:59:59.",
                 "ka": "ერთი წელი (2026), დიაპაზონი (2024-2026), სია (2024, 2026) ან „ყველა“ — წყაროში არსებული ყველა "
                       "წელი. რამდენიმე წელი მუშავდება ერთიმეორის მიყოლებით: თითო წელი ცალკე ანალიზდება, შენ "
                       "ადასტურებ და იწერება (ლოგი — თითო წელზე ცალკე). წელი = ჩანაწერები, რომელთა თარიღი (TariRI) "
                       "1 იანვარი 00:00:00 — 31 დეკემბერი 23:59:59 შუალედშია."},
    "e_no_years": {"en": "No dated records found in the source.", "ka": "წყაროში თარიღიანი ჩანაწერი ვერ მოიძებნა."},
    "batch_head": {"en": "Years done:", "ka": "დამუშავებული წლები:"},
    "batch_line": {"en": "{y}: inserted {n}", "ka": "{y}: ჩაიწერა {n}"},
    "batch_stopped": {"en": "(stopped - remaining years were not processed)", "ka": "(გაჩერდა — დარჩენილი წლები არ დამუშავებულა)"},
    "backup": {"en": "Back up the destination before writing", "ka": "ჩაწერამდე მიმღების სარეზერვო ასლის შექმნა"},
    "tip_backup": {"en": "Copies the destination .mdb next to it (…_backup_DATE.mdb) before anything is written.",
                   "ka": "ჩაწერამდე მიმღები .mdb-ის ასლს ქმნის გვერდით (…_backup_თარიღი.mdb)."},
    "copyset": {"en": "Also save the transferred records into a separate NEW database (one per run/year)",
                "ka": "გადატანილი ჩანაწერების დამატებით ცალკე ახალ ბაზაში შენახვა (გაშვება/წელი — ცალკე ბაზა)"},
    "copyall": {"en": "Also add the transferred records to ONE common database (all years together)",
                "ka": "გადატანილი ჩანაწერების დამატებით ერთ საერთო ბაზაშიც ჩაწერა (ყველა წელი ერთად)"},
    "tip_copyall": {"en": "The records written into the destination are also added to ONE fixed database "
                          "(<destination>_transferred_ALL_YEARS.mdb next to the destination). It is created on the first run; "
                          "later runs/years are APPENDED to it (existing records are never changed or deleted; the same "
                          "werilis_no + the same year is not repeated).",
                    "ka": "მიმღებში ჩაწერილი ჩანაწერები დამატებით ემატება ერთ ფიქსირებულ ბაზას "
                          "(<მიმღები>_transferred_ALL_YEARS.mdb, მიმღების გვერდით). პირველ გაშვებაზე იქმნება, შემდეგ "
                          "გაშვებებზე/წლებზე ემატება (არსებული ჩანაწერები არასდროს იცვლება/იშლება; იგივე werilis_no + იგივე "
                          "წელი არ მეორდება)."},
    "conf_copyall": {"en": "\nThe transferred records will ALSO be added to the common all-years database:\n{p}",
                     "ka": "\nგადატანილი ჩანაწერები დამატებით ჩაიწერება საერთო (ყველა წლის) ბაზაშიც:\n{p}"},
    "sum_copyall": {"en": "Added to the common all-years database ({n}):\n   {p}",
                    "ka": "საერთო (ყველა წლის) ბაზაში დაემატა ({n}):\n   {p}"},
    "sum_copyall_err": {"en": "NOT added to the common all-years database: {e}",
                        "ka": "საერთო (ყველა წლის) ბაზაში ვერ დაემატა: {e}"},
    "code_crs_mismatch": {"en": "The common database has a different coordinate system than the destination.\n\n{d}",
                          "ka": "საერთო ბაზის კოორდინატთა სისტემა მიმღებისას არ ემთხვევა.\n\n{d}"},
    "tip_copyset": {"en": "After a successful transfer, exactly the records that were written into the destination are also "
                          "copied (all attributes, exact geometry) into a brand-new Personal Geodatabase next to the "
                          "destination - handy for review or sending. The destination itself is written as usual.",
                    "ka": "წარმატებული გადატანის შემდეგ ზუსტად ის ჩანაწერები, რაც მიმღებში ჩაიწერა (ყველა ატრიბუტით და "
                          "ზუსტი გეომეტრიით), დამატებით გადაიწერება სრულიად ახალ Personal Geodatabase-ში — "
                          "გადასახედად/გასაგზავნად. მიმღები ჩვეულებრივად იწერება."},
    "conf_copyset": {"en": "\nThe transferred records will ALSO be saved into a separate NEW database:\n{p}",
                     "ka": "\nგადატანილი ჩანაწერები დამატებით შეინახება ცალკე ახალ ბაზაში:\n{p}"},
    "sum_copyset": {"en": "Transferred records also saved into NEW database ({n}):\n   {p}",
                    "ka": "გადატანილი ჩანაწერები ცალკე ახალ ბაზაშიც შენახულია ({n}):\n   {p}"},
    "sum_copyset_err": {"en": "Transferred records were NOT saved into a separate database: {e}",
                        "ka": "გადატანილი ჩანაწერები ცალკე ბაზაში ვერ შეინახა: {e}"},
    "onego": {"en": "Confirm ONCE for all years (no per-year dialogs)",
              "ka": "ერთი დადასტურება ყველა წელზე (თითო წელზე დიალოგის გარეშე)"},
    "tip_onego": {"en": "With several years you confirm one time at the start (years, destination, backup). Each year is "
                        "still analysed and logged separately. A year with blocked layers, record errors or repeated "
                        "werilis_no is NOT written silently - for that year the normal dialog appears. Backup of the "
                        "destination is made once, before the first year.",
                  "ka": "რამდენიმე წლის დროს ერთხელ ადასტურებ დასაწყისში (წლები, მიმღები, ბექაპი). თითო წელი მაინც "
                        "ცალკე ანალიზდება და ლოგდება. წელი, სადაც ფენა დაბლოკილია, ჩანაწერებს შეცდომა აქვთ ან "
                        "werilis_no მეორდება, ჩუმად არ ჩაიწერება — ამ წელზე ჩვეულებრივი დიალოგი გამოჩნდება. მიმღების "
                        "ბექაპი ერთხელ კეთდება, პირველ წლამდე."},
    "final": {"en": "Build the FINAL database as a NEW file - leave the destination untouched",
              "ka": "საბოლოო ბაზა ახალ ფაილად — მიმღები ხელუხლებელი რჩება"},
    "tip_final": {"en": "A fresh copy of the destination is made (<destination>_FINAL_<date time>.mdb) and ALL chosen "
                        "years are transferred into that copy. The real destination is not modified at all, so no "
                        "backup is needed. Existing records of the destination are kept in the new file; the same "
                        "werilis_no + the same year is not repeated. An existing file is never overwritten.",
                  "ka": "მიმღებისგან კეთდება ახალი ასლი (<მიმღები>_FINAL_<თარიღი დრო>.mdb) და არჩეული ყველა წელი ამ "
                        "ასლში გადადის. რეალური მიმღები საერთოდ არ იცვლება, ამიტომ ბექაპი არ სჭირდება. მიმღების "
                        "არსებული ჩანაწერები ახალ ფაილში რჩება; იგივე werilis_no + იგივე წელი არ მეორდება. არსებული "
                        "ფაილი არასდროს გადაიწერება."},
    "conf_batch": {"en": "Years to transfer: {y}\nFrom: {s}\nTo:   {d}\n{mode}\n{extra}\nYou will NOT be asked again for each "
                         "year (a year with problems still asks).\n\nContinue?",
                   "ka": "გადასატანი წლები: {y}\nსაწყისი: {s}\nმიმღები: {d}\n{mode}\n{extra}\nთითო წელზე აღარ "
                         "გკითხავ (პრობლემიანი წელი მაინც იკითხავს).\n\nგავაგრძელო?"},
    "mode_final": {"en": "NEW final file (destination NOT modified):\n   {p}",
                   "ka": "ახალი საბოლოო ფაილი (მიმღები არ იცვლება):\n   {p}"},
    "mode_direct": {"en": "Written directly INTO the destination.", "ka": "იწერება პირდაპირ მიმღებში."},
    "size_warn": {"en": "\n⚠ The database is already {mb:.0f} MB = {pct:.0f}% of the 2 GB Access limit. Consider "
                        "Compact & Repair, or a PostGIS/other target for further years.",
                  "ka": "\n⚠ ბაზა უკვე {mb:.0f} მბ = Access-ის 2 გბ ზღვრის {pct:.0f}%. გაითვალისწინე Compact & Repair "
                        "ან სხვა სამიზნე (PostGIS) შემდგომი წლებისთვის."},
    "sum_final": {"en": "FINAL database (new file; destination untouched):\n   {p}",
                  "ka": "საბოლოო ბაზა (ახალი ფაილი; მიმღები ხელუხლებელია):\n   {p}"},
    "st_copy": {"en": "Creating the new final database (copy)…", "ka": "იქმნება ახალი საბოლოო ბაზა (ასლი)…"},
    "code_copy_failed": {"en": "Could not create the new final database: {d}", "ka": "ახალი საბოლოო ბაზის შექმნა ვერ მოხერხდა: {d}"},
    "years_hint": {"en": "Years found in the source appear here as tick boxes after \"Check databases\".",
                   "ka": "წყაროში არსებული წლები აქ თოლიებად გამოჩნდება „ბაზების შემოწმების“ შემდეგ."},
    "years_pick": {"en": "Years to transfer (tick):", "ka": "გადასატანი წლები (მონიშნე):"},
    "years_all": {"en": "All years", "ka": "ყველა წელი"},
    "pick_file": {"en": "File (.mdb)…", "ka": "ფაილი (.mdb)…"},
    "pick_folder": {"en": "Folder (.gdb)…", "ka": "საქაღალდე (.gdb)…"},
    "gdb_note": {"en": "File Geodatabase (.gdb) is supported as source and as destination. A .gdb source is only read. "
                       "A .gdb destination is NEVER modified: a full new copy <name>_FINAL_<date time>.gdb is made and "
                       "only the new records are added to it (same duplicate rules).",
                 "ka": "File Geodatabase (.gdb) მხარდაჭერილია წყაროდაც და მიმღებადაც. .gdb წყარო მხოლოდ იკითხება. "
                       ".gdb მიმღები არასდროს იცვლება: კეთდება სრული ახალი ასლი <სახელი>_FINAL_<თარიღი დრო>.gdb და "
                       "მხოლოდ ახალი ჩანაწერები ემატება მას (დუბლიკატების იგივე წესებით)."},
    "st_gdb": {"en": "Reading .gdb…", "ka": ".gdb იკითხება…"},
    "code_gdb_no_crs": {"en": "A .gdb layer has no coordinate system ({d}). It is never guessed - define it first (CRS Manager).",
                        "ka": ".gdb ფენას კოორდინატთა სისტემა არ აქვს ({d}). არასდროს ვიგულისხმებთ — ჯერ განსაზღვრე (CRS მენეჯერი)."},
    "code_gdb_ambiguous": {"en": "More than one .gdb layer of the same geometry type: {d}. Keep one per type "
                                 "(point / line / polygon).",
                           "ka": ".gdb-ში ერთი ტიპის რამდენიმე ფენაა: {d}. დატოვე თითო ტიპზე ერთი (წერტილი / ხაზი / პოლიგონი)."},
    "code_gdb_no_layers": {"en": "No point / line / polygon layers found in the .gdb.",
                           "ka": ".gdb-ში წერტილის / ხაზის / პოლიგონის ფენა ვერ მოიძებნა."},
    "code_gdb_open": {"en": "Could not open the .gdb: {d}", "ka": ".gdb-ის გახსნა ვერ მოხერხდა: {d}"},
    "code_gdb_write": {"en": "Writing to the new .gdb failed (it was removed; the destination is untouched): {d}",
                       "ka": "ახალ .gdb-ში ჩაწერა ვერ მოხერხდა (ის წაიშალა; მიმღები უცვლელია): {d}"},
    "code_no_pyogrio": {"en": "pyogrio (GDAL) is not installed - .gdb is unavailable: {d}",
                        "ka": "pyogrio (GDAL) დაყენებული არ არის — .gdb მიუწვდომელია: {d}"},
    "st_fidelity": {"en": "Checking that nothing was lost (domains, subtypes, records)…",
                    "ka": "მოწმდება, რომ არაფერი დაიკარგა (დომენები, ქვეტიპები, ჩანაწერები)…"},
    "fid_ok": {"en": "Fidelity check: OK - schema (domains, subtypes, field properties, relationships) identical and all "
                     "original records unchanged.",
               "ka": "სიზუსტის შემოწმება: წესრიგშია — სქემა (დომენები, ქვეტიპები, ველების თვისებები, ურთიერთობები) "
                     "იდენტურია და ყველა არსებული ჩანაწერი უცვლელია."},
    "fid_bad": {"en": "Fidelity check: DIFFERENCES FOUND - details below and in the log. Do not delete the original.",
                "ka": "სიზუსტის შემოწმება: ნაპოვნია განსხვავებები — დეტალები ქვემოთ და ლოგში. ორიგინალი არ წაშალო."},
    "fid_viol": {"en": "Warning: {n} new value(s) do not match the destination domain/subtype (written as they are) - see the log.",
                 "ka": "გაფრთხილება: {n} ახალი მნიშვნელობა მიმღების დომენს/ქვეტიპს არ ემთხვევა (ჩაიწერა როგორც არის) — იხილე ლოგი."},
    "fid_err": {"en": "Fidelity check could not run: {e}", "ka": "სიზუსტის შემოწმება ვერ შესრულდა: {e}"},
    "btn_merge": {"en": "Merge all years into ONE database…", "ka": "ყველა წლის ერთ ბაზაში გაერთიანება…"},
    "tip_merge": {"en": "Choose the per-year databases (e.g. the *_transferred_<year>_*.mdb files) - all their records are "
                        "combined into ONE brand-new database (points, lines, polygons). Records with the same werilis_no "
                        "and the same year are not repeated. The chosen databases are only read.",
                  "ka": "აირჩიე წელი-წლობით გადატანილი ბაზები (მაგ. *_transferred_<წელი>_*.mdb) — მათი ყველა ჩანაწერი "
                        "გაერთიანდება ერთ სრულიად ახალ ბაზაში (წერტილი, ხაზი, პოლიგონი). იგივე werilis_no + იგივე წელი "
                        "არ განმეორდება. არჩეული ბაზები მხოლოდ იკითხება."},
    "merge_pick": {"en": "Choose the databases to merge (hold Ctrl for several)",
                   "ka": "აირჩიე გასაერთიანებელი ბაზები (რამდენიმეს — Ctrl)"},
    "merge_few": {"en": "Choose at least two databases.", "ka": "აირჩიე მინიმუმ ორი ბაზა."},
    "merge_ask": {"en": "{n} database(s) will be merged into ONE new database:\n{p}\n\nThe chosen databases are only read. Continue?",
                  "ka": "{n} ბაზა გაერთიანდება ერთ ახალ ბაზაში:\n{p}\n\nარჩეული ბაზები მხოლოდ იკითხება. გავაგრძელო?"},
    "merge_nothing": {"en": "Nothing to merge - no records found.", "ka": "გასაერთიანებელი არაფერია — ჩანაწერი ვერ მოიძებნა."},
    "merge_done": {"en": "Merged into one database: {n} record(s)", "ka": "გაერთიანდა ერთ ბაზაში: {n} ჩანაწერი"},
    "merge_line": {"en": "{k}: found {f}, duplicates skipped {u}, merged {i}, errors {e}",
                   "ka": "{k}: ნაპოვნი {f}, დუბლიკატი გამოტოვდა {u}, გაერთიანდა {i}, შეცდომა {e}"},
    "undated": {"en": "Save records WITHOUT a date into a separate NEW database",
                "ka": "თარიღის გარეშე ჩანაწერების ცალკე ახალ ბაზაში შენახვა"},
    "tip_undated": {"en": "Records whose date (TariRI) is empty cannot belong to any year. They are copied (all attributes, "
                          "exact geometry) into a brand-new Personal Geodatabase next to the log file. Nothing is changed "
                          "in the source or the destination.",
                    "ka": "ჩანაწერები, რომელთაც თარიღი (TariRI) ცარიელი აქვთ, არც ერთ წელს არ მიეკუთვნება. ისინი "
                          "(ყველა ატრიბუტით და ზუსტი გეომეტრიით) გადაიწერება სრულიად ახალ Personal Geodatabase-ში, ლოგის "
                          "ფაილის გვერდით. წყაროსა და მიმღებში არაფერი იცვლება."},
    "conf_undated": {"en": "\n{n} record(s) WITHOUT a date will be saved into a separate NEW database:\n{p}",
                     "ka": "\n{n} ჩანაწერი თარიღის გარეშე შეინახება ცალკე ახალ ბაზაში:\n{p}"},
    "conf_undated_only": {"en": "Nothing to insert into the destination.\n\n{n} record(s) WITHOUT a date can be saved into "
                                "a separate NEW database:\n{p}\n\nSave them now?",
                          "ka": "მიმღებში ჩასაწერი არაფერია.\n\n{n} ჩანაწერი თარიღის გარეშე შეიძლება შეინახოს ცალკე "
                                "ახალ ბაზაში:\n{p}\n\nშევინახო ახლა?"},
    "sum_undated": {"en": "Records without a date: {n} saved into NEW database:\n   {p}",
                    "ka": "თარიღის გარეშე ჩანაწერი: {n} შენახულია ახალ ბაზაში:\n   {p}"},
    "sum_undated_none": {"en": "Records without a date: none", "ka": "თარიღის გარეშე ჩანაწერი: არ არის"},
    "sum_undated_err": {"en": "Records without a date were NOT saved: {e}", "ka": "თარიღის გარეშე ჩანაწერები ვერ შეინახა: {e}"},
    "code_no_template": {"en": "The empty-database template is missing from the installation.\n\n{d}",
                         "ka": "ცარიელი ბაზის შაბლონი ინსტალაციაში არ არის.\n\n{d}"},
    "code_same_db": {"en": "The output database is one of the chosen databases.", "ka": "გამომავალი ბაზა არჩეულ ბაზებს შორისაა."},
    "code_exists": {"en": "The output file already exists (it is never overwritten).\n\n{d}",
                    "ka": "გამომავალი ფაილი უკვე არსებობს (არასდროს გადაიწერება).\n\n{d}"},
    "st_undated": {"en": "Saving records without a date…", "ka": "თარიღის გარეშე ჩანაწერების შენახვა…"},
    "map_box": {"en": "Layers (matched by geometry type, not by name)", "ka": "ფენები (შესაბამისობა გეომეტრიის ტიპით, არა სახელით)"},
    "map_src": {"en": "Source layer", "ka": "საწყისი ფენა"},
    "map_dst": {"en": "Destination layer", "ka": "მიმღები ფენა"},
    "map_ok": {"en": "✓ matched", "ka": "✓ დადგინდა"},
    "map_pick": {"en": "⚠ cannot be matched confidently — choose the layers", "ka": "⚠ დარწმუნებით ვერ დადგინდა — აირჩიე ფენები"},
    "map_missing": {"en": "⚠ no layer of this type", "ka": "⚠ ამ ტიპის ფენა არ არის"},
    "btn_check": {"en": "Check databases", "ka": "ბაზების შემოწმება"},
    "btn_start": {"en": "Start Transfer", "ka": "გადატანის დაწყება"},
    "btn_busy": {"en": "Working…", "ka": "მიმდინარეობს…"},
    "btn_cancel": {"en": "✖ Cancel", "ka": "✖ გაუქმება"},
    "btn_log": {"en": "Open log file", "ka": "ლოგის ფაილის გახსნა"},
    "ready": {"en": "Ready.", "ka": "მზადაა."},
    "t_layer": {"en": "Layer", "ka": "ფენა"},
    "t_found": {"en": "Found in source", "ka": "ნაპოვნია წყაროში"},
    "t_dup": {"en": "Already exists in destination", "ka": "მიმღებში უკვე არის"},
    "t_ins": {"en": "Inserted", "ka": "ჩაიწერა"},
    "t_plan": {"en": "To insert", "ka": "ჩასაწერია"},
    "t_err": {"en": "Errors", "ka": "შეცდომა"},
    "t_total": {"en": "TOTAL", "ka": "ჯამი"},
    "res_box": {"en": "Progress per layer", "ka": "პროგრესი ფენების მიხედვით"},
    "sum_box": {"en": "Transfer summary", "ka": "გადატანის შეჯამება"},
    "err_box": {"en": "Warnings and errors", "ka": "გაფრთხილებები და შეცდომები"},
    "log_path": {"en": "Log file: {p}", "ka": "ლოგის ფაილი: {p}"},

    # ვალიდაცია
    "e_pick_src": {"en": "Select the source database.", "ka": "აირჩიე საწყისი ბაზა."},
    "e_pick_dst": {"en": "Select the destination database.", "ka": "აირჩიე მიმღები ბაზა."},
    "e_not_mdb": {"en": "“{p}” is not an .mdb file.", "ka": "„{p}“ არ არის .mdb ფაილი."},
    "e_missing": {"en": "File not found: {p}", "ka": "ფაილი ვერ მოიძებნა: {p}"},
    "e_same": {"en": "The source and the destination are the same database. Choose two different files.",
               "ka": "საწყისი და მიმღები ერთი და იგივე ბაზაა. აირჩიე ორი განსხვავებული ფაილი."},
    "e_year": {"en": "Enter a valid year (e.g. 2026).", "ka": "მიუთითე სწორი წელი (მაგ. 2026)."},
    "e_map": {"en": "Choose the matching source and destination layer for: {k}.",
              "ka": "აირჩიე შესაბამისი საწყისი და მიმღები ფენა: {k}."},
    "e_nothing": {"en": "No layer can be transferred.", "ka": "ვერცერთი ფენა ვერ გადაიტანება."},
    "code_locked": {"en": "The database is open in another program (ArcGIS Pro, ArcMap, Access…) or locked.\n"
                          "Close it there and try again.\n\n{d}",
                    "ka": "ბაზა ღიაა სხვა პროგრამაში (ArcGIS Pro, ArcMap, Access…) ან დაბლოკილია.\n"
                          "დახურე იქ და სცადე ხელახლა.\n\n{d}"},
    "code_not_found": {"en": "The database file could not be found or opened.\n\n{d}",
                       "ka": "ბაზის ფაილი ვერ მოიძებნა ან ვერ გაიხსნა.\n\n{d}"},
    "code_bad_format": {"en": "This file is not a readable Access (.mdb) database.\n\n{d}",
                        "ka": "ეს ფაილი არ არის წასაკითხი Access (.mdb) ბაზა.\n\n{d}"},
    "code_no_driver": {"en": "The 64-bit “Microsoft Access Database Engine” ODBC driver is not installed.\n"
                             "Install it (Microsoft Access Database Engine 2016 Redistributable, x64).\n\n{d}",
                       "ka": "64-ბიტიანი „Microsoft Access Database Engine“ ODBC დრაივერი დაყენებული არ არის.\n"
                             "დააინსტალირე (Microsoft Access Database Engine 2016 Redistributable, x64).\n\n{d}"},
    "code_no_pyodbc": {"en": "The Python package “pyodbc” is missing. Install it with:  pip install pyodbc\n\n{d}",
                       "ka": "Python-ის პაკეტი „pyodbc“ აკლია. დააინსტალირე:  pip install pyodbc\n\n{d}"},
    "code_not_pgdb": {"en": "This is not an ESRI Personal Geodatabase (the GDB_ system tables are missing).\n\n{d}",
                      "ka": "ეს არ არის ESRI Personal Geodatabase (GDB_ სისტემური ცხრილები არ არის).\n\n{d}"},
    "code_no_space": {"en": "Not enough free disk space for the backup copy.\n\n{d}",
                      "ka": "სარეზერვო ასლისთვის დისკზე საკმარისი ადგილი არ არის.\n\n{d}"},
    "code_verify_failed": {"en": "Verification failed — nothing was written (rolled back).\n\n{d}",
                           "ka": "ვერიფიკაცია ჩავარდა — არაფერი ჩაწერილა (უკან დაბრუნდა).\n\n{d}"},
    "code_cancelled": {"en": "Cancelled — nothing was written.", "ka": "გაუქმდა — არაფერი ჩაწერილა."},
    "code_db_error": {"en": "Database error:\n\n{d}", "ka": "ბაზის შეცდომა:\n\n{d}"},
    "code_readonly": {"en": "The database is read-only.\n\n{d}", "ka": "ბაზა მხოლოდ წასაკითხია.\n\n{d}"},

    # შემოწმება
    "chk_ok": {"en": "Both databases are readable.", "ka": "ორივე ბაზა წაკითხვადია."},
    "chk_dst_locked": {"en": "⚠ The destination is open in another program — close it before transferring.",
                       "ka": "⚠ მიმღები ბაზა ღიაა სხვა პროგრამაში — გადატანამდე დახურე."},
    "chk_dst_writable": {"en": "The destination can be opened for writing.", "ka": "მიმღები ჩაწერისთვის მზადაა."},
    "chk_layer": {"en": "{k}: source '{s}' ({sn} records) → destination '{d}' ({dn} records)",
                  "ka": "{k}: საწყისი '{s}' ({sn} ჩანაწერი) → მიმღები '{d}' ({dn} ჩანაწერი)"},
    "chk_crs_diff": {"en": "   ⚠ coordinate systems differ — geometry will be reprojected",
                     "ka": "   ⚠ კოორდინატთა სისტემები განსხვავდება — გეომეტრია გადაიყვანება"},
    "chk_crs_bad": {"en": "   ⛔ coordinate systems differ and cannot be transformed reliably",
                    "ka": "   ⛔ კოორდინატთა სისტემები განსხვავდება და სანდოდ ვერ გარდაიქმნება"},
    "chk_fields": {"en": "   ⚠ source fields missing in the destination (NOT transferred): {f}",
                   "ka": "   ⚠ წყაროს ველები მიმღებში არ არის (ვერ გადავა): {f}"},
    "chk_schema": {"en": "   ⛔ incompatible schema: {f}", "ka": "   ⛔ სქემა შეუთავსებელია: {f}"},
    "chk_zm": {"en": "   ⛔ Z/M geometry is not supported", "ka": "   ⛔ Z/M გეომეტრია არ მხარდაიჭერება"},

    # დადასტურება
    "conf_title": {"en": "Confirm transfer", "ka": "გადატანის დადასტურება"},
    "conf_head": {"en": "Year {y}.\nFrom: {s}\nTo:   {d}\n", "ka": "წელი {y}.\nსაწყისი: {s}\nმიმღები: {d}\n"},
    "conf_line": {"en": "{k}: found {f}, already in destination {u}, to insert {n}, errors {e}",
                  "ka": "{k}: ნაპოვნია {f}, მიმღებში უკვე არის {u}, ჩასაწერია {n}, შეცდომა {e}"},
    "conf_blocked": {"en": "{k}: SKIPPED — {why}", "ka": "{k}: გამოტოვებულია — {why}"},
    "conf_backup": {"en": "\nA backup copy of the destination will be created first.",
                    "ka": "\nჯერ მიმღების სარეზერვო ასლი შეიქმნება."},
    "conf_nobackup": {"en": "\nNo backup copy will be made.", "ka": "\nსარეზერვო ასლი არ შეიქმნება."},
    "conf_warn": {"en": "\nNotes:", "ka": "\nშენიშვნები:"},
    "conf_ask": {"en": "\nWrite {n} record(s) into the destination now?", "ka": "\nჩაიწეროს {n} ჩანაწერი მიმღებში ახლა?"},
    "conf_nothing": {"en": "There is nothing to insert: every matching record already exists in the destination "
                           "(or no records match the year).",
                     "ka": "ჩასაწერი არაფერია: ყველა შესაბამისი ჩანაწერი მიმღებში უკვე არის (ან წელს ჩანაწერი არ ემთხვევა)."},

    # პროგრესი / შეჯამება
    "st_analysing": {"en": "Analysing (read-only)…", "ka": "ანალიზი (მხოლოდ კითხვა)…"},
    "st_writing": {"en": "Writing to the destination…", "ka": "მიმღებში ჩაწერა…"},
    "st_progress": {"en": "{k}: {i}/{n}", "ka": "{k}: {i}/{n}"},
    "st_done": {"en": "Done — inserted {n} record(s).", "ka": "დასრულდა — ჩაიწერა {n} ჩანაწერი."},
    "st_cancelled": {"en": "Cancelled.", "ka": "გაუქმდა."},
    "st_error": {"en": "Error.", "ka": "შეცდომა."},
    "sum_title": {"en": "TRANSFER SUMMARY", "ka": "გადატანის შეჯამება"},
    "sum_layer": {"en": "{k}:\n   Found in source: {f}\n   Already exists in destination ({y}): {u}\n"
                        "   Inserted: {i}\n   Errors: {e}",
                  "ka": "{k}:\n   ნაპოვნია წყაროში: {f}\n   მიმღებში უკვე არის ({y}): {u}\n"
                        "   ჩაიწერა: {i}\n   შეცდომა: {e}"},
    "sum_total": {"en": "TOTAL:\n   Source records found: {f}\n   Duplicates skipped: {u}\n   Records inserted: {i}\n"
                        "   Records with errors: {e}\n   Records with missing/invalid dates: {b}\n   Duration: {t}",
                  "ka": "ჯამი:\n   წყაროს ჩანაწერი ნაპოვნია: {f}\n   დუბლიკატი გამოტოვებულია: {u}\n"
                        "   ჩაიწერა: {i}\n   შეცდომიანი ჩანაწერი: {e}\n   ცარიელი/არასწორი თარიღით: {b}\n"
                        "   ხანგრძლივობა: {t}"},
    "sum_backup": {"en": "Backup of the destination: {p}", "ka": "მიმღების სარეზერვო ასლი: {p}"},
    "sum_blocked": {"en": "{k}: not transferred — {why}", "ka": "{k}: არ გადაიტანა — {why}"},
    "why_kind_mismatch": {"en": "geometry type mismatch", "ka": "გეომეტრიის ტიპი არ ემთხვევა"},
    "why_has_zm": {"en": "Z/M geometry is not supported", "ka": "Z/M გეომეტრია არ მხარდაიჭერება"},
    "why_crs_unknown": {"en": "coordinate systems differ and cannot be transformed reliably",
                        "ka": "კოორდინატთა სისტემები განსხვავდება და სანდოდ ვერ გარდაიქმნება"},
    "why_schema": {"en": "incompatible fields ({d})", "ka": "შეუთავსებელი ველები ({d})"},
    "why_no_key_fields": {"en": "werilis_no / date fields not found ({d})", "ka": "werilis_no / თარიღის ველები ვერ მოიძებნა ({d})"},
    "err_rec": {"en": "{k}: OBJECTID {o} ({n}) — {why}", "ka": "{k}: OBJECTID {o} ({n}) — {why}"},
    "why_no_number": {"en": "no werilis_no — duplicate check impossible, not inserted",
                      "ka": "werilis_no არ აქვს — დუბლიკატის შემოწმება შეუძლებელია, არ ჩაიწერა"},
    "amb": {"en": "{k}: {n} werilis_no value(s) occur several times inside the source selection; all were inserted "
                  "because the destination had none for {y}: {l}",
            "ka": "{k}: {n} werilis_no მნიშვნელობა განმეორდება წყაროს არჩევანის შიგნით; ყველა ჩაიწერა, რადგან "
                  "მიმღებში {y} წლით არ ჰქონდა: {l}"},
    "bad_dates": {"en": "{k}: {n} source record(s) with a missing/invalid date (not transferred, listed in the log)",
                  "ka": "{k}: {n} წყაროს ჩანაწერს თარიღი ცარიელი/არასწორი აქვს (არ გადაიტანა, ჩამოთვლილია ლოგში)"},
    "tip_check": {"en": "Open both databases (read-only), list their layers and check the destination can be written.",
                  "ka": "ორივე ბაზის გახსნა (მხოლოდ კითხვა), ფენების ჩამოთვლა და მიმღების ჩაწერისთვის მზადობის შემოწმება."},
    "tip_start": {"en": "Analyse first (nothing is written), then ask for confirmation, then write.",
                  "ka": "ჯერ ანალიზი (არაფერი იწერება), შემდეგ დადასტურება, ბოლოს ჩაწერა."},
}


def fmt_size(path):
    try:
        if os.path.isdir(path):                       # .gdb — საქაღალდე
            n = sum(os.path.getsize(os.path.join(r, f)) for r, _d, fs in os.walk(path) for f in fs)
        else:
            n = os.path.getsize(path)
    except OSError:
        return "?"
    return "{:.0f} MB".format(n / 1048576.0) if n >= 1048576 else "{:.0f} KB".format(n / 1024.0)


def fmt_duration(sec):
    sec = max(0.0, float(sec))
    return "{:.1f} s".format(sec) if sec < 60 else "{}m {:.0f}s".format(int(sec // 60), sec % 60)


def make_tr(lang):
    """tr(key, **fmt) for the DTR catalogue (COMMON fallback), as the classic ToolFrame.tr does."""
    from tools.i18n import translate

    def tr(key, **fmt):
        return translate(DTR, key, lang, **fmt)
    return tr


def as_transfer_error(exc):
    """Any exception -> TransferError (so the windows show one kind of message)."""
    if isinstance(exc, core.TransferError):
        return exc
    if isinstance(exc, ImportError):
        return core.TransferError("no_pyodbc", str(exc))
    return core.friendly_error(exc)


def data_dir():
    try:
        from tools.apppaths import data_dir as _d
        return _d()
    except Exception:                              # noqa: BLE001
        return None


# ===================================================================================== .gdb staging
class Stager(object):
    """.gdb -> temporary .mdb for the engine (the original .gdb is never modified); .mdb is used as is."""

    def __init__(self):
        self.staged, self.orig = {}, {}            # original .gdb -> staged .mdb ; staged .mdb -> original
        self._dir = None

    def reset(self):
        self.staged, self.orig = {}, {}

    def orig_of(self, path):
        return self.orig.get(path, path)

    def engine_path(self, path):
        return self.staged.get(path, path)

    def stage(self, path, tag, progress=None, cancel=None, status=None):
        if not gdbx.is_gdb(path):
            return path
        if self._dir is None:
            import atexit
            import shutil
            import tempfile
            self._dir = tempfile.mkdtemp(prefix="gisbox_gdb_")
            atexit.register(shutil.rmtree, self._dir, True)
        out = gdbx.staged_path(path, self._dir, "." + tag)
        if os.path.exists(out):
            try:
                os.remove(out)
            except OSError:
                pass
        if status:
            status("st_gdb")
        gdbx.gdb_to_mdb(path, out, progress=progress, cancel=cancel)
        self.staged[path], self.orig[out] = out, path
        return out


# ===================================================================================== worker steps
def check(src, dst, stager, progress=None, cancel=None, status=None):
    """Open both databases read-only -> (src_info, dst_info, mapping, ambiguous, locked_error, years)."""
    if not core.driver_available():
        import pyodbc  # noqa: F401  (ImportError -> no_pyodbc)
        raise core.TransferError("no_driver", core.ODBC_DRIVER)
    src = stager.stage(src, "src", progress, cancel, status)
    dst = stager.stage(dst, "dst", progress, cancel, status)
    si, di = core.inspect_db(src), core.inspect_db(dst)
    mapping, amb = core.match_layers(si, di)
    locked = None
    try:
        core.check_writable(dst)
    except core.TransferError as e:
        locked = e
    years = []
    if mapping:
        try:
            years = core.source_years(src, mapping)
        except Exception:                          # noqa: BLE001  (the year list is a helper; typing works)
            years = []
    return si, di, mapping, amb, locked, years


def make_log(log_path, sink=None):
    return core.TransferLog(log_path, sink=sink)


def analysis(src, dst, year, mapping, log_path, stager, options, gdb_final=None, progress=None, cancel=None,
             sink=None):
    """Read-only analysis of one year -> Plan. ``options``: backup / undated / copyset / copyall (for the log)."""
    log = make_log(log_path, sink)
    try:
        log.raw("=" * 78)
        log.raw("DATABASE DATA TRANSFER — year {}".format(year))
        log.raw("=" * 78)
        log("source:      {}{}".format(stager.orig_of(src),
                                       "  (read via staging database {})".format(src) if src in stager.orig else ""))
        log("destination: {}{}".format(stager.orig_of(dst),
                                       "  (checked on staging copy {}; the .gdb itself is never modified -> new "
                                       "copy {})".format(dst, gdb_final) if dst in stager.orig else ""))
        log("period:      {0}-01-01 00:00:00 .. {0}-12-31 23:59:59".format(year))
        log("layer mapping: " + "; ".join("{}: {} -> {}".format(k.upper(), a, b) for k, (a, b) in mapping.items()))
        log("options: backup={} | undated-export={} | transferred-copy={} | all-years-db={}".format(
            options.get("backup"), options.get("undated"), options.get("copyset"), options.get("copyall")))
        log("log file: {}".format(log_path))
        return core.analyze(src, dst, mapping, year, log=log, progress=progress, cancel=cancel)
    except core.TransferError as e:
        log("{}: {}".format(e.code, e.detail), "ERROR")
        raise
    except Exception as e:                         # noqa: BLE001
        log(str(e), "ERROR")
        raise
    finally:
        log.close()


def write(plan, log_path, backup, undated_path=None, skip_main=False, gdb_dst=None, gdb_final=None,
          copyall_path=None, copyset_path=None, final_path=None, final_origin=None, last_year=True,
          progress=None, cancel=None, sink=None, status=None):
    """Write one analysed year (+ the optional extra databases, + the fidelity check after the last year of a
    FINAL run), then close the log. Sets ``plan.undated_plan/_error``, ``copyset_*``, ``copyall_*`` and
    ``plan.fidelity`` (None or {"state": ok|bad|err, "lines": [...], "viol": n, "err": text})."""
    log = core.TransferLog(log_path, sink=sink)
    plan.fidelity = None
    try:
        if not skip_main:
            log("--- writing ---")
            core.execute(plan, log=log, backup=backup, progress=progress, cancel=cancel)
            if gdb_final:
                log("--- transferred records -> new .gdb (copy of the destination) ---")
                gdbx.append_plan_to_gdb(plan, gdb_dst, gdb_final, log=log)
        plan.undated_plan, plan.undated_error = None, None
        plan.copyset_plan, plan.copyset_error = None, None
        plan.copyall_plan, plan.copyall_error = None, None
        if not skip_main and copyall_path:
            try:
                log("--- transferred records -> common all-years database ---")
                plan.copyall_plan = core.export_inserted(plan, copyall_path, log=log, progress=progress,
                                                         cancel=cancel, append=True)
            except core.TransferError as e:
                plan.copyall_error = e
                log("{}: {}".format(e.code, e.detail), "ERROR")
            except Exception as e:                 # noqa: BLE001
                plan.copyall_error = core.friendly_error(e)
                log(str(e), "ERROR")
        if not skip_main and copyset_path:
            try:
                log("--- transferred records -> separate new database ---")
                plan.copyset_plan = core.export_inserted(plan, copyset_path, log=log, progress=progress,
                                                         cancel=cancel)
            except core.TransferError as e:
                plan.copyset_error = e
                log("{}: {}".format(e.code, e.detail), "ERROR")
            except Exception as e:                 # noqa: BLE001
                plan.copyset_error = core.friendly_error(e)
                log(str(e), "ERROR")
        if undated_path:
            # the main write is already committed - an error here does not undo it, it is reported separately
            try:
                log("--- records without a date -> new database ---")
                mapping = {lp.kind: (lp.src_name, lp.dst_name) for lp in plan.layers}
                src_map = {k: (v[0], v[0]) for k, v in mapping.items()}
                plan.undated_plan = core.export_undated(plan.src_path, src_map, undated_path, log=log,
                                                        progress=progress, cancel=cancel)
            except core.TransferError as e:
                plan.undated_error = e
                log("{}: {}".format(e.code, e.detail), "ERROR")
            except Exception as e:                 # noqa: BLE001
                plan.undated_error = core.friendly_error(e)
                log(str(e), "ERROR")
        if not skip_main and last_year and (gdb_final or (final_path and final_origin)):
            try:                                   # fidelity: domains / subtypes / fields + existing records
                if status:
                    status("st_fidelity")
                if gdb_final:
                    orig, new = gdb_dst, gdb_final
                    layers = list(gdbx.pick_layers(gdbx.inspect_gdb(new)).values())
                else:
                    orig, new = final_origin, final_path
                    layers = [lp.dst_name for lp in plan.layers]
                good, lines = fid.report(orig, new, layers)
                for ln in lines:
                    log.raw(ln)
                viol = sum(len(v) for v in getattr(plan, "domain_violations", {}).values())
                plan.fidelity = {"state": "ok" if good else "bad", "lines": lines, "viol": viol, "err": ""}
            except Exception as e:                 # noqa: BLE001  (a helper check; never undoes the transfer)
                log("fidelity check could not run: {}".format(e), "WARN")
                plan.fidelity = {"state": "err", "lines": [], "viol": 0, "err": str(e)[:200]}
        log.close()
        close_out(plan, log_path, "COMPLETED" if not skip_main else "completed (records without a date only)",
                  written=not skip_main)
        return plan
    except core.TransferError as e:
        log("{}: {}".format(e.code, e.detail), "ERROR")
        log.close()
        close_out(plan, log_path, "FAILED / ROLLED BACK ({})".format(e.code))
        raise
    except Exception as e:                         # noqa: BLE001
        log(str(e), "ERROR")
        raise
    finally:
        log.close()


def merge(paths, out, log_path, progress=None, cancel=None, sink=None):
    """Merge several databases into ONE new database -> Plan or None (nothing to merge)."""
    log = make_log(log_path, sink)
    t0 = time.time()
    try:
        log.raw("=" * 78)
        log.raw("MERGE DATABASES — all years into one")
        log.raw("=" * 78)
        for x in paths:
            log("input: {}".format(x))
        log("output: {}".format(out))
        plan = core.merge_databases(paths, out, log=log, progress=progress, cancel=cancel)
        if plan is not None:
            log.raw("")
            for pth, stats in plan.per_source:
                log.raw("{}: ".format(os.path.basename(pth)) + " | ".join(
                    "{} {}/{}/{}".format(k.upper(), *stats[k]) for k in core.KINDS if k in stats)
                    + "   (found/merged/duplicates)")
            log.raw("duration: {:.1f} s".format(time.time() - t0))
        return plan
    except core.TransferError as e:
        log("{}: {}".format(e.code, e.detail), "ERROR")
        raise
    except Exception as e:                         # noqa: BLE001
        log(str(e), "ERROR")
        raise
    finally:
        log.close()


def close_out(plan, log_path, outcome, written=False):
    """Finish the log: final summary + records CSV + history index (files are only appended to)."""
    if not log_path:
        return
    try:
        log = core.TransferLog(log_path)
        elapsed = time.time() - plan.started
        core.write_final_summary(plan, log, outcome, elapsed=elapsed, written=written,
                                 undated=getattr(plan, "undated_plan", None))
        csv_path = os.path.splitext(log_path)[0] + "_records.csv"
        core.write_records_csv(plan, csv_path)
        log("records file: {}".format(csv_path))
        hist = core.append_history(log_path, plan, outcome, written=written, elapsed=elapsed)
        if hist:
            log("history index: {}".format(hist))
        log.close()
    except Exception:                              # noqa: BLE001
        pass
    try:                                           # central V2 operation history (never breaks the tool)
        from tools.logging_manager import get_manager
        tot = plan.totals() if hasattr(plan, "totals") else {}
        get_manager().record(
            "pgdb_transfer", "ok" if written else "no_write",
            inputs=[plan.src_path, plan.dst_path],
            outputs=[log_path],
            params={"year": plan.year, "outcome": outcome, "totals": tot},
            duration=time.time() - plan.started)
    except Exception:                              # noqa: BLE001
        pass


# ===================================================================================== texts
def kind_name(kind, lang):
    return KIND_LABEL[kind][lang]


def message(tr, exc):
    """TransferError / other -> readable text."""
    if isinstance(exc, core.TransferError):
        key = "code_" + exc.code
        if key in DTR:
            return tr(key, d=(exc.detail or "")[:400])
        return str(exc)
    return str(exc)


def why(tr, lp):
    code, detail = lp.blocked
    key = "why_" + code
    return tr(key, d=detail) if key in DTR else code


def check_lines(tr, lang, si, di, sel_mapping, locked):
    """Report after "Check databases" for the chosen (complete) layer pairs {kind: (src, dst)}."""
    lines = [tr("chk_ok")]
    for k in core.KINDS:
        if k not in sel_mapping:
            continue
        s, d = sel_mapping[k]
        sl, dl = si.layers[s], di.layers[d]
        lines.append(tr("chk_layer", k=kind_name(k, lang), s=s, d=d, sn=sl.count, dn=dl.count))
        if sl.has_z or sl.has_m or dl.has_z or dl.has_m:
            lines.append(tr("chk_zm"))
        rel = core.crs_relation(sl.srtext, dl.srtext)
        if rel == "reproject":
            lines.append(tr("chk_crs_diff"))
        elif rel == "unknown":
            lines.append(tr("chk_crs_bad"))
        fp = core.plan_fields(sl.fields, dl.fields)
        if fp.unmatched_src:
            lines.append(tr("chk_fields", f=", ".join(fp.unmatched_src)))
        if not fp.ok:
            bits = ["{} ({})".format(f, dtl) for _c, f, dtl in fp.blockers] + fp.missing_required
            lines.append(tr("chk_schema", f="; ".join(bits)))
    lines.append(tr("chk_dst_locked") if locked else tr("chk_dst_writable"))
    return lines


def notes(tr, lang, plan):
    out = []
    for lp in plan.layers:
        k = kind_name(lp.kind, lang)
        if lp.unmatched_fields:
            out.append(tr("chk_fields", f=", ".join(lp.unmatched_fields)).strip())
        if lp.reprojected:
            out.append(k + ": " + tr("chk_crs_diff").strip())
        if lp.src_internal_dup_nos:
            out.append(tr("amb", k=k, n=len(lp.src_internal_dup_nos), y=plan.year,
                          l=", ".join(lp.src_internal_dup_nos[:15]) + (" …" if len(lp.src_internal_dup_nos) > 15 else "")))
        n_bad = len(lp.missing_dates) + len(lp.invalid_dates)
        if n_bad:
            out.append(tr("bad_dates", k=k, n=n_bad))
    return out


def issue_lines(tr, lang, lp):
    """Warnings/errors area: records that will not be transferred."""
    k = kind_name(lp.kind, lang)
    out = []
    if lp.blocked:
        out.append(tr("sum_blocked", k=k, why=why(tr, lp)))
    for oid, no, w in lp.errors:
        reason = tr("why_no_number") if w == "no_number" else w
        out.append(tr("err_rec", k=k, o=oid, n=no, why=reason))
    for oid, no in lp.missing_dates:
        out.append("{}: OBJECTID {} ({}) — {}".format(k, oid, no, "NULL date"))
    for oid, no, dt in lp.invalid_dates:
        out.append("{}: OBJECTID {} ({}) — invalid date {}".format(k, oid, no, dt))
    return out


def undated_count(plan, enabled):
    return sum(len(lp.missing_dates) for lp in plan.layers) if enabled else 0


def is_clean(plan):
    """A year that may be written without its own dialog in a "confirm once" batch."""
    return not any(lp.blocked or lp.errors or lp.src_internal_dup_nos for lp in plan.layers)


def confirm_head(tr, lang, plan, o_src, o_dst):
    """Per-layer lines + notes of the confirmation dialog (before the options / question)."""
    text = tr("conf_head", y=plan.year, s=os.path.basename(o_src), d=os.path.basename(o_dst))
    for lp in plan.layers:
        k = kind_name(lp.kind, lang)
        if lp.blocked:
            text += tr("conf_blocked", k=k, why=why(tr, lp)) + "\n"
        else:
            text += tr("conf_line", k=k, f=lp.found, u=lp.duplicates, n=lp.to_insert_count, e=len(lp.errors)) + "\n"
    ns = notes(tr, lang, plan)
    if ns:
        text += tr("conf_warn") + "\n" + "\n".join("• " + n for n in ns) + "\n"
    return text


def fidelity_text(tr, fres):
    if not fres:
        return None
    if fres["state"] == "err":
        return tr("fid_err", e=fres["err"])
    text = tr("fid_ok" if fres["state"] == "ok" else "fid_bad") + "\n" + "\n".join(fres["lines"][1:])
    if fres["viol"]:
        text += "\n" + tr("fid_viol", n=fres["viol"])
    return text


def summary_lines(tr, lang, plan, written, log_path, undated_on):
    t = plan.totals()
    lines = [tr("sum_title"), "=" * 44]
    for lp in plan.layers:
        k = kind_name(lp.kind, lang)
        if lp.blocked:
            lines.append(tr("sum_blocked", k=k, why=why(tr, lp)))
            continue
        lines.append(tr("sum_layer", k=k, f=lp.found, y=plan.year, u=lp.duplicates,
                        i=(lp.inserted if written else 0), e=len(lp.errors)))
    lines.append("-" * 44)
    lines.append(tr("sum_total", f=t["found"], u=t["duplicates"], i=(t["inserted"] if written else 0),
                    e=t["errors"], b=t["bad_dates"], t=fmt_duration(time.time() - plan.started)))
    if getattr(plan, "backup_path", None):
        lines.append(tr("sum_backup", p=plan.backup_path))
    ca = getattr(plan, "copyall_plan", None)
    if ca:
        lines.append(tr("sum_copyall", n=ca.totals()["inserted"], p=ca.dst_path))
    elif getattr(plan, "copyall_error", None):
        lines.append(tr("sum_copyall_err", e=message(tr, plan.copyall_error)))
    cp = getattr(plan, "copyset_plan", None)
    if cp:
        lines.append(tr("sum_copyset", n=cp.totals()["inserted"], p=cp.dst_path))
    elif getattr(plan, "copyset_error", None):
        lines.append(tr("sum_copyset_err", e=message(tr, plan.copyset_error)))
    up = getattr(plan, "undated_plan", None)
    if up:
        lines.append(tr("sum_undated", n=up.totals()["inserted"], p=up.dst_path))
    elif getattr(plan, "undated_error", None):
        lines.append(tr("sum_undated_err", e=message(tr, plan.undated_error)))
    elif written and undated_on:
        lines.append(tr("sum_undated_none"))
    if log_path:
        lines.append(tr("log_path", p=log_path))
    return lines


def done_message(tr, plan, final_shown=None, fid_text=None):
    """The dialog after a successful write of one year."""
    msg = tr("st_done", n=plan.totals()["inserted"])
    if final_shown:
        msg += "\n\n" + tr("sum_final", p=final_shown)
    if fid_text:
        msg += "\n\n" + fid_text
    up = getattr(plan, "undated_plan", None)
    if up:
        msg += "\n\n" + tr("sum_undated", n=up.totals()["inserted"], p=up.dst_path)
    ca = getattr(plan, "copyall_plan", None)
    if ca:
        msg += "\n\n" + tr("sum_copyall", n=ca.totals()["inserted"], p=ca.dst_path)
    if getattr(plan, "copyall_error", None):
        msg += "\n\n" + tr("sum_copyall_err", e=message(tr, plan.copyall_error))
    cp = getattr(plan, "copyset_plan", None)
    if cp:
        msg += "\n\n" + tr("sum_copyset", n=cp.totals()["inserted"], p=cp.dst_path)
    if getattr(plan, "copyset_error", None):
        msg += "\n\n" + tr("sum_copyset_err", e=message(tr, plan.copyset_error))
    if getattr(plan, "undated_error", None):
        msg += "\n\n" + tr("sum_undated_err", e=message(tr, plan.undated_error))
    return msg


def batch_lines(tr, results, stopped=False, final_shown=None, fid_text=None):
    lines = [tr("batch_head")] + [tr("batch_line", y=y, n=n) for y, n in results]
    if stopped:
        lines.append(tr("batch_stopped"))
    if final_shown:
        lines.append(tr("sum_final", p=final_shown))
    if fid_text:
        lines.append("\n" + fid_text)
    return lines


def merge_lines(tr, lang, plan, log_path):
    t = plan.totals()
    lines = [tr("merge_done", n=t["inserted"]), "=" * 44]
    for lp in plan.layers:
        lines.append(tr("merge_line", k=kind_name(lp.kind, lang), f=lp.found, u=lp.duplicates,
                        i=lp.inserted, e=len(lp.errors)))
    lines += ["-" * 44, plan.dst_path, tr("log_path", p=log_path)]
    return lines


def validate(src, dst, year_text):
    """-> (src, dst, years) or ("warn", key, fmt) for the first problem (the window shows it)."""
    if not src:
        return ("warn", "e_pick_src", {})
    if not dst:
        return ("warn", "e_pick_dst", {})
    for p in (src, dst):
        if not (p.lower().endswith(".mdb") or gdbx.is_gdb(p)):
            return ("warn", "e_not_mdb", {"p": p})
        if not (os.path.isdir(p) if gdbx.is_gdb(p) else os.path.isfile(p)):
            return ("warn", "e_missing", {"p": p})
    if core.same_file(src, dst):
        return ("warn", "e_same", {})
    try:
        year = core.parse_years(year_text)
    except ValueError:
        return ("warn", "e_year", {})
    return src, dst, year

