"""V2 shell strings (Georgian / English)."""
import re

S = {
    "app": {"ka": "GIS_BOX", "en": "GIS_BOX"},
    "search": {"ka": "ძებნა…", "en": "Search…"},
    "home": {"ka": "მთავარი", "en": "Home"},
    "favorites": {"ka": "ფავორიტები", "en": "Favorites"},
    "recent": {"ka": "ბოლოს გამოყენებული", "en": "Recently used"},
    "recent_files": {"ka": "ბოლოს გახსნილი ფაილები", "en": "Recently opened files"},
    "none": {"ka": "ცარიელია", "en": "Empty"},
    "welcome": {"ka": "კეთილი იყოს შენი მობრძანება GIS_BOX-ში", "en": "Welcome to GIS_BOX"},
    "welcome_sub": {"ka": "აირჩიე ხელსაწყო მარცხენა მენიუდან ან მოძებნე სახელით.",
                    "en": "Pick a tool from the sidebar or search by name."},
    "version": {"ka": "ვერსია", "en": "Version"},
    "menu_view": {"ka": "ხედი", "en": "View"},
    "menu_theme": {"ka": "თემა", "en": "Theme"},
    "theme_light": {"ka": "ღია", "en": "Light"},
    "theme_dark": {"ka": "მუქი", "en": "Dark"},
    "menu_lang": {"ka": "ენა", "en": "Language"},
    "menu_tools": {"ka": "სერვისი", "en": "Service"},
    "open_logs": {"ka": "ლოგების საქაღალდის გახსნა", "en": "Open logs folder"},
    "export_diag": {"ka": "დიაგნოსტიკური ანგარიშის ექსპორტი…", "en": "Export diagnostic report…"},
    "env_check": {"ka": "გარემოს შემოწმება", "en": "Environment check"},
    "menu_help": {"ka": "დახმარება", "en": "Help"},
    "about": {"ka": "პროგრამის შესახებ", "en": "About"},
    "fav_add": {"ka": "☆ ფავორიტებში დამატება", "en": "☆ Add to favorites"},
    "fav_remove": {"ka": "★ ფავორიტებიდან მოხსნა", "en": "★ Remove from favorites"},
    "cancel": {"ka": "გაუქმება", "en": "Cancel"},
    "ready": {"ka": "მზადაა", "en": "Ready"},
    "working": {"ka": "მიმდინარეობს…", "en": "Working…"},
    "done": {"ka": "დასრულდა", "en": "Done"},
    "failed": {"ka": "შეცდომა", "en": "Error"},
    "cancelled": {"ka": "გაუქმდა", "en": "Cancelled"},
    "legacy_note": {"ka": "ეს ხელსაწყო ჯერ კლასიკურ ფანჯარაშია (tkinter). V2 ინტერფეისზე გადატანა მიმდინარეობს — ფუნქციონალი უცვლელია.",
                    "en": "This tool still runs in the classic window (tkinter). It is being ported to the V2 interface - functionality is unchanged."},
    "open_classic": {"ka": "გახსნა კლასიკურ ფანჯარაში", "en": "Open in classic window"},
    "launch_failed": {"ka": "ხელსაწყოს გაშვება ვერ მოხერხდა:", "en": "Could not start the tool:"},
    "opened_classic": {"ka": "გაიხსნა კლასიკურ ფანჯარაში", "en": "Opened in the classic window"},
    "diag_saved": {"ka": "ანგარიში შენახულია:", "en": "Report saved:"},
    "diag_exists": {"ka": "ფაილი უკვე არსებობს — აირჩიე სხვა სახელი.", "en": "File already exists - choose another name."},
    "about_text": {"ka": "GIS_BOX — GIS ხელსაწყოების ნაკრები საქართველოსთვის.", "en": "GIS_BOX - a GIS toolkit."},
    # --- shell: home, cards, states, errors
    "all_tools": {"ka": "ყველა ხელსაწყო", "en": "All tools"},
    "tools_n": {"ka": "{n} ხელსაწყო", "en": "{n} tools"},
    "no_results": {"ka": "ვერაფერი მოიძებნა: „{q}“", "en": "Nothing found for “{q}”"},
    "open_file_hint": {"ka": "ორჯერ დააწკაპუნე — გაიხსნება CRS მენეჯერში",
                       "en": "Double-click to open it in the CRS Manager"},
    "busy_refused": {"ka": "ჯერ მიმდინარე ოპერაცია უნდა დასრულდეს (ან გააუქმე).",
                     "en": "Another operation is still running - wait for it or cancel it."},
    "cancelling": {"ka": "უქმდება…", "en": "Cancelling…"},
    "page_failed": {"ka": "ხელსაწყოს გახსნა ვერ მოხერხდა", "en": "This tool could not be opened"},
    "page_failed_hint": {"ka": "სავარაუდოდ აკლია არასავალდებულო პაკეტი ან კომპონენტი. დეტალები ჩაწერილია ლოგში "
                                "(სერვისი → ლოგების საქაღალდის გახსნა); შეამოწმე გარემოც (სერვისი → გარემოს შემოწმება).",
                         "en": "Most likely an optional package or component is missing. The details are in the log "
                               "(Service → Open logs folder); also try Service → Environment check."},
    "retry": {"ka": "თავიდან ცდა", "en": "Try again"},
    "ui_error": {"ka": "შიდა შეცდომა (დეტალები ლოგშია):", "en": "Internal error (details in the log):"},
    "close_running_title": {"ka": "ოპერაცია მიმდინარეობს", "en": "An operation is running"},
    "close_running": {"ka": "„{tool}“ ჯერ არ დასრულებულა.\n\nგავაუქმო და დავხურო პროგრამა? ფანჯარა დაიხურება, "
                            "როგორც კი ოპერაცია უსაფრთხოდ შეჩერდება.",
                      "en": "“{tool}” has not finished yet.\n\nCancel it and close the program? The window closes "
                            "once the operation has stopped safely."},
    "closing_wait": {"ka": "ოპერაცია ჩერდება, შემდეგ პროგრამა დაიხურება…",
                     "en": "Stopping the operation, then the program will close…"},
    # --- CRS page
    "crs_file": {"ka": "ფაილი", "en": "File"},
    "browse": {"ka": "არჩევა…", "en": "Browse…"},
    "crs_detect": {"ka": "CRS-ის აღმოჩენა", "en": "Detect CRS"},
    "crs_info": {"ka": "კოორდინატთა სისტემა", "en": "Coordinate system"},
    "crs_target": {"ka": "სამიზნე CRS", "en": "Target CRS"},
    "crs_custom": {"ka": "ან EPSG კოდი", "en": "or EPSG code"},
    "crs_output": {"ka": "გამოსავალი (ახალი ფაილი)", "en": "Output (NEW file)"},
    "crs_reproject": {"ka": "გადაყვანა (reproject) → ახალ ფაილში", "en": "Reproject → new file"},
    "crs_assign": {"ka": "CRS-ის მინიჭება (ჭდე) → ახალ ფაილში", "en": "Assign CRS (label) → new file"},
    "crs_assign_confirm": {
        "ka": "CRS-ის მინიჭება კოორდინატებს არ ცვლის — მხოლოდ ჭდეს ადებს.\n\nწყარო: {src}\nმისანიჭებელი: {crs}\n\nდარწმუნებული ხარ, რომ მონაცემები ნამდვილად ამ სისტემაშია?",
        "en": "Assigning a CRS does NOT change coordinates - it only sets the label.\n\nSource: {src}\nTo assign: {crs}\n\nAre you sure the data really is in this system?"},
    "crs_need_file": {"ka": "ჯერ აირჩიე ფაილი.", "en": "Choose a file first."},
    "crs_need_target": {"ka": "აირჩიე ან შეიყვანე სამიზნე CRS.", "en": "Choose or enter a target CRS."},
    "crs_need_out": {"ka": "მიუთითე გამოსავალი ფაილი.", "en": "Specify the output file."},
    "crs_suggest": {"ka": "შესაძლო CRS-ები (მხოლოდ ვარაუდი, არა საბოლოო იდენტიფიკაცია):",
                    "en": "Possible CRS (a guess only, not a definitive identification):"},
    "crs_use_candidate": {"ka": "სამიზნედ ამ ვარაუდის გამოყენება", "en": "Use as target"},
    "crs_report": {"ka": "ანგარიში", "en": "Report"},
    "crs_name": {"ka": "სახელი", "en": "Name"},
    "crs_epsg": {"ka": "EPSG", "en": "EPSG"},
    "crs_kind": {"ka": "ტიპი", "en": "Type"},
    "crs_datum": {"ka": "დატუმი", "en": "Datum"},
    "crs_unit": {"ka": "ერთეული", "en": "Unit"},
    "crs_proj": {"ka": "პროექცია", "en": "Projection"},
    "crs_bounds": {"ka": "საზღვრები", "en": "Bounds"},
    "crs_missing": {"ka": "CRS არ არის განსაზღვრული", "en": "CRS is not defined"},
    # --- updates page
    "upd_current": {"ka": "დაყენებული ვერსია", "en": "Installed version"},
    "upd_latest": {"ka": "უახლესი ვერსია", "en": "Latest version"},
    "upd_date": {"ka": "გამოქვეყნების თარიღი", "en": "Release date"},
    "upd_last": {"ka": "ბოლო შემოწმება", "en": "Last check"},
    "upd_never": {"ka": "არასდროს", "en": "never"},
    "upd_auto": {"ka": "განახლებების ავტომატური შემოწმება (დღეში ერთხელ)", "en": "Check for updates automatically (once a day)"},
    "upd_notify": {"ka": "შეტყობინება ახალი ვერსიის შესახებ", "en": "Notify when an update is available"},
    "upd_pre": {"ka": "წინასწარი (prerelease) ვერსიების დაშვება", "en": "Allow prerelease versions"},
    "upd_check": {"ka": "ახლა შემოწმება", "en": "Check now"},
    "upd_download": {"ka": "ჩამოტვირთვა…", "en": "Download…"},
    "upd_install": {"ka": "ინსტალაცია…", "en": "Install…"},
    "upd_rollback": {"ka": "უკან დაბრუნება…", "en": "Roll back…"},
    "upd_notes": {"ka": "რელიზის აღწერა", "en": "Release notes"},
    "upd_available": {"ka": "ხელმისაწვდომია ახალი ვერსია: {v}", "en": "A new version is available: {v}"},
    "upd_uptodate": {"ka": "გაქვს უახლესი ვერსია", "en": "You are up to date"},
    "upd_error": {"ka": "შემოწმება ვერ მოხერხდა: {e}", "en": "Check failed: {e}"},
    "upd_no_asset": {"ka": "ამ ოპერაციული სისტემისთვის პაკეტი რელიზში არ არის.", "en": "The release has no package for this system."},
    "upd_confirm_download": {
        "ka": "ჩამოტვირთვა?\n\nფაილი: {name}\nზომა: {size}\nწყარო: {src}\n\nფაილი შემოწმდება SHA256-ით, ინსტალაცია მხოლოდ შენი ცალკე დადასტურების შემდეგ.",
        "en": "Download?\n\nFile: {name}\nSize: {size}\nSource: {src}\n\nThe file is verified with SHA256; installing needs your separate confirmation."},
    "upd_downloaded_ok": {"ka": "ჩამოტვირთულია და შემოწმებულია (SHA256 ემთხვევა): {p}", "en": "Downloaded and verified (SHA256 matches): {p}"},
    "upd_downloaded_unverified": {"ka": "ჩამოტვირთულია, მაგრამ SHA256 არ არის გამოქვეყნებული — ვერ შემოწმდა: {p}", "en": "Downloaded, but no SHA256 is published - NOT verified: {p}"},
    "upd_manual": {"ka": "ეს ფორმატი ავტომატურად არ ინსტალირდება (ადმინისტრატორის უფლებები არ გამოიყენება). დააყენე ხელით: {p}", "en": "This format is not installed automatically (no admin rights are used). Install it manually: {p}"},
    "upd_confirm_install": {
        "ka": "დაინსტალირდეს ვერსია {v}?\n\nდასაყენებელი საქაღალდე: {dir}\nბექაპი: {bk}\nშენი პარამეტრები და მონაცემები არ გადაიწერება. ჩავარდნის შემთხვევაში ყველაფერი ავტომატურად დაბრუნდება.",
        "en": "Install version {v}?\n\nTarget folder: {dir}\nBackup: {bk}\nYour settings and data are not overwritten. On failure everything is rolled back automatically."},
    "upd_confirm_unverified": {"ka": "პაკეტის SHA256 არ არის გამოქვეყნებული — ავთენტურობა ვერ დამტკიცდა. მაინც დავაინსტალირო?", "en": "No SHA256 is published for this package - authenticity cannot be proven. Install anyway?"},
    "upd_installed": {"ka": "განახლება დაინსტალირდა ({r} ფაილი შეიცვალა, {a} დაემატა). გადატვირთე GIS_BOX. ბექაპი: {bk}", "en": "Update installed ({r} replaced, {a} added). Restart GIS_BOX. Backup: {bk}"},
    "upd_confirm_rollback": {"ka": "დაბრუნდეს წინა ვერსიაზე ({v})?\nბექაპი: {bk}", "en": "Roll back to the previous version ({v})?\nBackup: {bk}"},
    "upd_rolled_back": {"ka": "წინა ვერსია აღდგენილია. გადატვირთე GIS_BOX.", "en": "Previous version restored. Restart GIS_BOX."},
    "upd_no_backup": {"ka": "ბექაპი ვერ მოიძებნა.", "en": "No backup found."},
    "upd_toast": {"ka": "ხელმისაწვდომია GIS_BOX {v} — იხილე „განახლებები“", "en": "GIS_BOX {v} is available - see Updates"},
    "upd_confirm_restart": {"ka": "GIS_BOX ახლავე გადაიტვირთოს ცვლილებების გასააქტიურებლად?", "en": "Restart GIS_BOX now to apply the change?"},
    "lb_folder": {"ka": "ხაზოვანი შრის საქაღალდე", "en": "Line layer folder"},
    "lb_rescan": {"ka": "თავიდან სკანირება", "en": "Rescan"},
    "lb_shp": {"ka": "ხაზოვანი shapefile", "en": "Line shapefile"},
    "lb_out": {"ka": "გამომავალი საქაღალდე", "en": "Output folder"},
    "lb_type": {"ka": "ბუფერის ტიპი", "en": "Buffer type"},
    "lb_type_n": {"ka": "ტიპი {n}", "en": "Type {n}"},
    "lb_zones": {"ka": "აგებული ბუფერები", "en": "Buffers to build"},
    "lb_zone_row": {"ka": "{d} მ  →  {name}", "en": "{d} m  →  {name}"},
    "lb_build": {"ka": "ბუფერების აგება", "en": "Build buffers"},
    "lb_found": {"ka": "ნაპოვნია {n} ხაზოვანი shapefile.", "en": "Found {n} line shapefile(s)."},
    "lb_none": {"ka": "საქაღალდეში ხაზოვანი shapefile ვერ მოიძებნა.", "en": "No line shapefiles found in the folder."},
    "lb_warn_shp": {"ka": "აირჩიე ხაზოვანი shapefile.", "en": "Choose a line shapefile."},
    "lb_warn_out": {"ka": "აირჩიე გამომავალი საქაღალდე.", "en": "Choose an output folder."},
    "lb_warn_zone": {"ka": "მონიშნე მინიმუმ ერთი ბუფერი.", "en": "Tick at least one buffer."},
    "lb_no_crs": {"ka": "shapefile-ს CRS (.prj) არ აქვს — UTM ზონა ვერ დგინდება. ჯერ მიანიჭე EPSG:32637 ან EPSG:32638 (CRS მენეჯერით).",
                  "en": "The shapefile has no CRS (.prj) - the UTM zone cannot be determined. Assign EPSG:32637 or EPSG:32638 first (CRS Manager)."},
    "lb_no_geom": {"ka": "შრეში გამოსადეგი ხაზოვანი გეომეტრია არ არის.", "en": "The layer has no usable line geometry."},
    "lb_convert_q": {
        "ka": "შრე არის {cur}-ში. ბუფერები იგება მხოლოდ EPSG:32637 / EPSG:32638-ში.\n\nგადავიყვანო EPSG:{epsg}-ში (UTM ზონა {zone}, შრის მდებარეობის მიხედვით) და იქ ავაგო ბუფერები? საწყისი ფაილი არ შეიცვლება.",
        "en": "The layer is in {cur}. Buffers are built only in EPSG:32637 / EPSG:32638.\n\nConvert it to EPSG:{epsg} (UTM zone {zone}, by the layer's location) and build the buffers there? The source file is not changed."},
    "lb_done": {"ka": "დასრულდა — {n} ბუფერი ჩაიწერა: {out}", "en": "Done - {n} buffer(s) written to {out}"},
    "lb_dep": {"ka": "ამ ხელსაწყოს სჭირდება geopandas + pyogrio.\n{e}", "en": "This tool needs geopandas + pyogrio.\n{e}"},
    "ms_note": {"ka": "tile / WMS სერვისების URL-ები (Google basemaps, ორთოფოტო) — ArcMap / QGIS-ში გადასაკოპირებლად. ზოგი სერვისი მოითხოვს VPN-ს / წვდომას. ახლის დასამატებლად შეასწორე map_services.txt.",
                "en": "tile / WMS service URLs (Google basemaps, ortho) to copy into ArcMap / QGIS. Some services may require VPN / access. Edit map_services.txt to add your own."},
    "ms_filter": {"ka": "სერვისის ძებნა…", "en": "Filter services…"},
    "ms_copy": {"ka": "კოპირება", "en": "Copy"},
    "ms_tip": {"ka": "URL-ის კოპირება — ჩასვი ArcMap / QGIS-ში ახალ tile / WMS შრედ.", "en": "Copy this URL - paste it into ArcMap / QGIS as a new tile / WMS layer."},
    "ms_copied": {"ka": "დაკოპირდა", "en": "Copied"},
    "ms_empty": {"ka": "map_services.txt ვერ მოიძებნა ან ცარიელია.", "en": "map_services.txt not found or empty."},
    "upd_mb": {"ka": "{n:.1f} მბ", "en": "{n:.1f} MB"},
    # ---- Shp → coordinates
    "sc_note": {"ka": "მიუთითე საქაღალდე, აირჩიე წერტილოვანი shapefile და გაიტანე მისი კოორდინატები დაფორმატებულ Excel-ში "
                      "(ნედლი ცხრილი A:D + გასუფთავებული ასლი G-დან, არჩევითი ქუდით და კუთხით).",
                "en": "Pick a folder, choose a point shapefile and export its coordinates to a formatted Excel file "
                      "(raw table A:D + a cleaned copy from column G, with an optional title and angle)."},
    "sc_folder": {"ka": "საქაღალდე:", "en": "Folder:"},
    "sc_shp": {"ka": "წერტილოვანი shapefile:", "en": "Point shapefile:"},
    "sc_rescan": {"ka": "თავიდან სკანირება", "en": "Rescan"},
    "sc_zone": {"ka": "UTM ზონა:", "en": "UTM zone:"},
    "sc_zone_auto": {"ka": "ავტომატური ({z})", "en": "auto ({z})"},
    "sc_zone_unknown": {"ka": "ვერ ცნობა", "en": "not detected"},
    "sc_vtype": {"ka": "მნიშვნელობები:", "en": "Values:"},
    "sc_v_dbl": {"ka": "ათწილადი (double)", "en": "Decimal (double)"},
    "sc_v_int": {"ka": "მთელი (integer)", "en": "Integer"},
    "sc_tmpl": {"ka": "ტექსტური ქუდი:", "en": "Header template:"},
    "sc_tmpl_none": {"ka": "(არცერთი)", "en": "(none)"},
    "sc_tmpl_add": {"ka": "➕ დამატება…", "en": "➕ Add…"},
    "sc_tmpl_del": {"ka": "🗑 წაშლა", "en": "🗑 Delete"},
    "sc_tmpl_file": {"ka": "📄 ფაილი", "en": "📄 File"},
    "sc_tmpl_file_tip": {"ka": "ქუდები ტექსტურ ფაილში (UTF-8) — იგივე ფაილი, რასაც კლასიკური ხელსაწყო იყენებს.",
                         "en": "Header templates live in a text file (UTF-8) - the same file the classic tool uses."},
    "sc_tmpl_add_q": {"ka": "ახალი ქუდის ტექსტი:", "en": "New header template text:"},
    "sc_conv_hint": {"ka": "აკრიფე ქართულად ან ლათინურით — ლათინური ქვემოთ ქართულად გადაკეთდება "
                           "(t→ტ, T→თ, q→ქ, W→ჭ, S→შ, C→ჩ …).",
                     "en": "Type in Georgian or Latin - Latin is converted to Georgian below (t→ტ, T→თ, q→ქ, W→ჭ, S→შ, C→ჩ …)."},
    "sc_conv_geo": {"ka": "შედეგი:", "en": "Result:"},
    "sc_tmpl_bad": {"ka": "ტექსტში „?“-ია (აკრეფის ხარვეზი) — არ შეინახა.", "en": "The text contains “?” (keyboard issue) - not saved."},
    "sc_tmpl_builtin": {"ka": "ჩაშენებული ქუდები ვერ იშლება (შენს ქუდებს ფაილში მართავ).",
                        "en": "Built-in templates can't be deleted (manage your own in the file)."},
    "sc_tmpl_del_q": {"ka": "წავშალო ეს ტექსტური ქუდი?\n\n{t}", "en": "Delete this header template?\n\n{t}"},
    "sc_angle": {"ka": "„გადაკვეთის კუთხე“ სვეტი (°)", "en": "Add “crossing angle” column (°)"},
    "sc_angle_all": {"ka": "ერთი კუთხე ყველასთვის (არჩევით):", "en": "same angle for all (optional):"},
    "sc_export": {"ka": "ექსპორტი და ფორმატირება (Excel)", "en": "Export & format (Excel)"},
    "sc_copy": {"ka": "📋 კოპირება", "en": "📋 Copy"},
    "sc_copy_tip": {"ka": "დაფორმატებული ბლოკი (ქუდი + ჩარჩოებიანი №/X/Y) ბუფერში — Word/Excel-ში პირდაპირ ჩასვი.",
                    "en": "Copy the formatted block (title + bordered №/X/Y) - paste straight into Word / Excel."},
    "sc_png": {"ka": "📷 PNG", "en": "📷 PNG"},
    "sc_png_tip": {"ka": "ბლოკი გამჭვირვალე PNG-ად — ArcGIS Pro-ში Insert → Picture (არ იწელება).",
                   "en": "Save the block as a transparent PNG - in ArcGIS Pro use Insert → Picture (no stretching)."},
    "sc_batch": {"ka": "Batch: ყველას ექსპორტი…", "en": "Batch: export all…"},
    "sc_batch_tip": {"ka": "საქაღალდის ყველა წერტილოვანი shapefile ერთბაშად (არსებულ ფაილს ზემოდან არ წერს).",
                     "en": "Export every point shapefile in the folder at once (existing files are never overwritten)."},
    "sc_batch_dir": {"ka": "აირჩიე batch-ის გამომავალი საქაღალდე", "en": "Choose the output folder for the batch"},
    "sc_apply_deg": {"ka": "° დაუმატე კუთხის სვეტს…", "en": "Add ° to angle column…"},
    "sc_apply_deg_tip": {"ka": "არსებულ Excel ფაილში „გადაკვეთის კუთხე“ სვეტის ყველა რიცხვს ° ფორმატი.",
                         "en": "Give every number in the “crossing angle” column of an existing Excel file the ° format."},
    "sc_prev_count": {"ka": "{n} წერტილი", "en": "{n} point(s)"},
    "sc_no_folder": {"ka": "მიუთითე არსებული საქაღალდე.", "en": "Specify a valid folder."},
    "sc_no_shp": {"ka": "საქაღალდეში წერტილოვანი shapefile ვერ მოიძებნა.", "en": "No point shapefiles found in the folder."},
    "sc_found": {"ka": "ნაპოვნია {n} წერტილოვანი shapefile.", "en": "Found {n} point shapefile(s)."},
    "sc_detected": {"ka": "არჩეულია: {name} | ზონა {z} | {n} წერტილი.", "en": "Selected: {name} | zone {z} | {n} point(s)."},
    "sc_pick_shp": {"ka": "ჯერ აირჩიე წერტილოვანი shapefile.", "en": "Choose a point shapefile first."},
    "sc_need_zone": {"ka": "UTM ზონა ვერ ცნობა — აირჩიე 37 ან 38.", "en": "Could not detect the UTM zone - choose 37 or 38."},
    "sc_no_crs_q": {"ka": "ამ shapefile-ს კოორდინატთა სისტემა (.prj) არ აქვს. კოორდინატები გამოყენებული იქნება როგორც არის — "
                          "UTM ზონა {z}. გავაგრძელო?",
                    "en": "This shapefile has no CRS (.prj). Coordinates will be used as they are, as UTM zone {z}. Continue?"},
    "sc_no_crs_warn": {"ka": "CRS (.prj) არ არის — გამოტოვდა (batch-ში ზონას არ ვგულისხმობთ)",
                       "en": "no CRS (.prj) - skipped (the batch never assumes a zone)"},
    "sc_int_q": {"ka": "„მთელი (integer)“ ყველა კოორდინატს მეტრამდე ამრგვალებს (წერტილზე ~0.7 მ-მდე გადახრა). მაინც გავაგრძელო?",
                 "en": "“Integer” rounds every coordinate to the whole metre (up to ~0.7 m shift per point). Export anyway?"},
    "sc_no_points": {"ka": "shapefile-ში წერტილები არ არის.", "en": "The shapefile has no points."},
    "sc_load_err": {"ka": "shapefile ვერ წაიკითხა: {e}", "en": "Could not read the shapefile: {e}"},
    "sc_save_title": {"ka": "Excel-ის შენახვა", "en": "Save Excel"},
    "sc_done": {"ka": "გაიტანა {n} წერტილი → {path}", "en": "Exported {n} points → {path}"},
    "sc_locked_q": {"ka": "ფაილი Excel-ში გახსნილია:\n{path}\n\nდავხურო (შეუნახავი ცვლილებები დაიკარგება) და გავაგრძელო?",
                    "en": "The file is open in Excel:\n{path}\n\nClose it (unsaved changes are discarded) and continue?"},
    "sc_locked": {"ka": "ვერ შეინახა — ფაილი Excel-ში გახსნილია. დახურე და სცადე ხელახლა.",
                  "en": "Could not save - the file is open in Excel. Close it and try again."},
    "sc_batch_skip": {"ka": "გამოტოვდა (ზონა/წერტილი არ არის):", "en": "skipped (no zone / no points):"},
    "sc_batch_exists": {"ka": "გამოტოვდა — ფაილი უკვე არსებობს:", "en": "skipped - the file already exists:"},
    "sc_batch_done": {"ka": "Batch დასრულდა — გაიტანა {ok}, გამოტოვდა {sk}.", "en": "Batch done - exported {ok}, skipped {sk}."},
    "sc_clip_done": {"ka": "დაკოპირდა ბუფერში ({n} რიგი).", "en": "Copied to the clipboard ({n} rows)."},
    "sc_png_title": {"ka": "ცხრილის შენახვა PNG-ად", "en": "Save table as PNG"},
    "sc_png_done": {"ka": "შენახულია: {path} (ბუფერშიც დაკოპირდა)", "en": "Saved: {path} (also copied to the clipboard)"},
    "sc_pick_xlsx": {"ka": "აირჩიე Excel ფაილი", "en": "Choose the Excel file"},
    "sc_deg_done": {"ka": "° დაემატა {n} კუთხის უჯრას.", "en": "° applied to {n} angle cell(s)."},
    "sc_deg_nocol": {"ka": "ფაილში „გადაკვეთის კუთხე“ სვეტი ვერ მოიძებნა (ფაილი არ შეცვლილა).",
                     "en": "No “crossing angle” column found in the file (the file was not changed)."},
    "sc_areas": {"ka": "ფართები დაცვის ზონის კვეთიდან დაემატება შემდეგ ექსპორტს.",
                 "en": "Areas from the zone intersection will be added to the next export."},
    # ---- Rename → Latin
    "rn_note": {"ka": "მიუთითე საქაღალდე. ყველა ფაილს, რომლის სახელშიც ქართული ასოებია, გადაერქმევა ლათინურად "
                      "(„არსებული საყრდენი.shp“ → „arsebuli_sayrdeni.shp“); სფეისი და სხვა სიმბოლო ხდება „_“, "
                      "გაფართოება უცვლელია. shapefile-ის ყველა თანმხლები ფაილი ერთად მუშავდება.",
                "en": "Pick a folder. Every file whose name has Georgian letters is renamed to Latin "
                      "(spaces and other symbols become “_”, the extension is kept). All sidecar files of a "
                      "shapefile are handled together."},
    "rn_folder": {"ka": "საქაღალდე:", "en": "Folder:"},
    "rn_recursive": {"ka": "ქვესაქაღალდეებიც", "en": "Include subfolders"},
    "rn_preview": {"ka": "წინასწარი სია", "en": "Preview"},
    "rn_rename": {"ka": "გადარქმევა", "en": "Rename"},
    "rn_undo": {"ka": "↩ დაბრუნება", "en": "↩ Undo"},
    "rn_check": {"ka": "შემოწმება: მასალა დევს თუ ცარიელია", "en": "Check contents (empty or not)"},
    "rn_check_tip": {"ka": "საქაღალდის ყველა .shp-ისთვის ლოგში წერს ობიექტების რაოდენობას და ცარიელია თუ არა. "
                           "არაფერს ცვლის.",
                     "en": "Logs the feature count of every .shp in the folder and whether it is empty. Changes nothing."},
    "rn_col_old": {"ka": "ძველი სახელი", "en": "Old name"},
    "rn_col_new": {"ka": "ახალი სახელი", "en": "New name"},
    "rn_col_status": {"ka": "სტატუსი", "en": "Status"},
    "rn_st_ok": {"ka": "გადაერქმევა", "en": "will be renamed"},
    "rn_st_conflict": {"ka": "⚠ დუბლი სახელი — გამოტოვდება", "en": "⚠ duplicate name - skipped"},
    "rn_st_exists": {"ka": "⚠ სამიზნე არსებობს — გამოტოვდება", "en": "⚠ target exists - skipped"},
    "rn_st_group": {"ka": "⚠ ამ მონაცემის სხვა ფაილი გამოტოვდება — ესეც", "en": "⚠ another file of this dataset is skipped - so is this"},
    "rn_warn_folder": {"ka": "მიუთითე არსებული საქაღალდე.", "en": "Specify a valid folder."},
    "rn_none": {"ka": "ქართული სახელის მქონე ფაილი ვერ მოიძებნა.", "en": "No files with Georgian names found."},
    "rn_scan_n": {"ka": "საგადარქმევოა {n} ფაილი ({c} გამოტოვდება).", "en": "{n} file(s) to rename ({c} will be skipped)."},
    "rn_confirm": {"ka": "გადავარქვათ {n} ფაილს?\n„↩ დაბრუნება“ ღილაკით ბოლო გადარქმევის გაუქმება შეიძლება, "
                         "სანამ ხელსაწყო ღიაა.",
                   "en": "Rename {n} file(s)?\nThe last rename can be reverted with “↩ Undo” while this tool is open."},
    "rn_nothing": {"ka": "გადასარქმევი არაფერია.", "en": "Nothing to rename."},
    "rn_done": {"ka": "დასრულდა — გადაერქვა {ok}, გამოტოვდა {sk}.", "en": "Done - renamed {ok}, skipped {sk}."},
    "rn_undo_none": {"ka": "დასაბრუნებელი არაფერია.", "en": "Nothing to undo."},
    "rn_undo_q": {"ka": "დავაბრუნო ბოლო გადარქმევა ({n} ფაილი)?", "en": "Undo the last rename ({n} file(s))?"},
    "rn_undo_done": {"ka": "დაბრუნდა — აღდგა {ok}, გამოტოვდა {sk}.", "en": "Undone - restored {ok}, skipped {sk}."},
    "rn_chk_none": {"ka": "საქაღალდეში .shp ფაილი ვერ მოიძებნა.", "en": "No .shp files found in the folder."},
    "rn_chk_hdr": {"ka": "— მასალის შემოწმება —", "en": "— Content check —"},
    "rn_chk_has": {"ka": "✓ {name} — {n} ობიექტი", "en": "✓ {name} - {n} feature(s)"},
    "rn_chk_has_x": {"ka": "✓ {name} — მასალა დევს", "en": "✓ {name} - has data"},
    "rn_chk_empty": {"ka": "⚠ {name} — ცარიელია (0 ობიექტი)", "en": "⚠ {name} - EMPTY (0 features)"},
    "rn_chk_unknown": {"ka": "? {name} — ვერ წავიკითხე", "en": "? {name} - could not read"},
    "rn_chk_sum": {"ka": "— შემოწმდა {t}: {d} მასალით, {e} ცარიელი, {u} წაუკითხავი —",
                   "en": "— Checked {t}: {d} with data, {e} empty, {u} unreadable —"},
}


def tr(lang, key, **fmt):
    d = S.get(key)
    if not d:
        return key
    s = plain(d.get(lang) or d.get("en") or key)
    return s.format(**fmt) if fmt else s


_EMOJI_PREFIX = re.compile(r"^[\U0001F000-\U0001FFFF]️?\s*")      # pictographs only - ★ ⚠ ✓ stay
_emoji_font = None


def emoji_supported():
    """True when an emoji font is installed (Windows: Segoe UI Emoji). Many Linux desktops have none, and Qt
    then draws decorative emoji such as the one in "🗑 Delete" as an empty box. Needs a running Qt app."""
    global _emoji_font
    if _emoji_font is None:
        try:
            from PySide6.QtGui import QFontDatabase, QGuiApplication
            if QGuiApplication.instance() is None:
                return True                                # not known yet - do not cache
            _emoji_font = any("emoji" in f.lower() for f in QFontDatabase.families())
        except Exception:                                  # noqa: BLE001 - no Qt: plain text is never wrong
            return True
    return _emoji_font


def plain(text):
    """``text`` without a leading decorative emoji when the system cannot draw it (labels stay readable)."""
    if text and not emoji_supported():
        return _EMOJI_PREFIX.sub("", text)
    return text
