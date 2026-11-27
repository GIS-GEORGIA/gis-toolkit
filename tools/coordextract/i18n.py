# -*- coding: utf-8 -*-
"""კოორდინატების ამომღების თარგმანები / translations (en/ka).

თვითკმარი — ხელსაწყო დამოუკიდებლადაც მუშაობს (main() default ენა "en"),
GIS_BOX-ში კი ენა გადაეცემა მთავარი აპლიკაციიდან.
"""

TR = {
    "title":            {"en": "Map Coordinate Extractor", "ka": "რუკის კოორდინატების ამომღები"},

    # toolbar
    "btn_open_image":   {"en": "Open image…",   "ka": "სურათის გახსნა…"},
    "btn_open_pdf":     {"en": "Open PDF…",      "ka": "PDF-ის გახსნა…"},
    "btn_grab":         {"en": "Grab screen",    "ka": "ეკრანის აღება"},
    "btn_zoom_in":      {"en": "Zoom +",         "ka": "მიახლ. +"},
    "btn_zoom_out":     {"en": "Zoom −",         "ka": "დაშ. −"},
    "btn_fit":          {"en": "Fit",            "ka": "მორგება"},
    "status_start":     {"en": "Open an image or PDF, or grab from screen, to begin.",
                         "ka": "დასაწყებად გახსენი სურათი ან PDF, ან აიღე ეკრანიდან."},
    "page_dash":        {"en": "—", "ka": "—"},

    # OCR tab
    "tab_ocr":          {"en": "OCR table",      "ka": "OCR ცხრილი"},
    "lbl_backend":      {"en": "Backend:",       "ka": "ძრავა:"},
    "backend_none":     {"en": "(none installed)", "ka": "(არცერთი დაინსტ.)"},
    "ocr_mark":         {"en": "1. Mark table area (drag on image)",
                         "ka": "1. მონიშნე ცხრილის არე (გადაათრიე სურათზე)"},
    "ocr_read":         {"en": "2. Read table (OCR)", "ka": "2. წაიკითხე ცხრილი (OCR)"},
    "tbl_add_row":      {"en": "Add row",        "ka": "რიგის დამატება"},
    "tbl_del_row":      {"en": "Delete row",     "ka": "რიგის წაშლა"},
    "exp_excel":        {"en": "Export Excel",   "ka": "Excel-ში ექსპორტი"},
    "exp_csv":          {"en": "Export CSV",     "ka": "CSV-ში ექსპორტი"},
    "exp_json":         {"en": "Export JSON",    "ka": "JSON-ში ექსპორტი"},
    "exp_format":       {"en": "Format Excel",   "ka": "Excel-ის ფორმატირება"},
    "pick_xlsx":        {"en": "Choose the Excel file to format",
                         "ka": "აირჩიე დასაფორმატებელი Excel ფაილი"},
    "format_done":      {"en": "Formatted — cleaned copy added ({n} rows).",
                         "ka": "დაფორმატდა — დაემატა გასუფთავებული ასლი ({n} რიგი)."},
    "format_empty":     {"en": "No coordinate rows found in the file.",
                         "ka": "ფაილში კოორდინატების რიგები ვერ მოიძებნა."},
    "format_failed":    {"en": "Formatting failed", "ka": "ფორმატირება ვერ მოხერხდა"},
    "format_busy":      {"en": "Cells from E6 on are already filled ({n} cells) - they will be overwritten. Continue?",
                         "ka": "უჯრები E6-დან უკვე შევსებულია ({n} უჯრა) — გადაიწერება. გავაგრძელო?"},
    "ocr_tip":          {"en": "Tip: double-click a cell to fix an OCR mistake.",
                         "ka": "რჩევა: ორმაგი დაწკაპუნებით ჩაასწორე OCR-ის შეცდომა."},

    # Geo tab
    "tab_geo":          {"en": "Geo-reference",  "ka": "გეო-რეფერენსი"},
    "geo_cp_header":    {"en": "Control points (pixel → real X/Y):",
                         "ka": "საკონტროლო წერტილები (პიქსელი → ნამდვილი X/Y):"},
    "geo_add_cp":       {"en": "+ Add control point (click grid intersection)",
                         "ka": "+ საკონტროლო წერტილი (დააწკაპე ბადის გადაკვეთა)"},
    "geo_del_cp":       {"en": "Delete selected control point",
                         "ka": "მონიშნული საკონტროლო წერტილის წაშლა"},
    "fit_none":         {"en": "Fit: —", "ka": "მორგება: —"},
    "geo_poly_header":  {"en": "Polygon vertices:", "ka": "პოლიგონის წვეროები:"},
    "geo_add_vertex":   {"en": "+ Add polygon vertex (click corners)",
                         "ka": "+ პოლიგონის წვერო (დააწკაპე კუთხეები)"},
    "geo_clear_poly":   {"en": "Clear polygon", "ka": "პოლიგონის გასუფთავება"},
    "geo_compute":      {"en": "Compute coordinates", "ka": "კოორდინატების გამოთვლა"},
    "area_none":        {"en": "Area: —", "ka": "ფართობი: —"},

    # modes / status
    "mode_crop":        {"en": "Drag a box around the coordinate table.",
                         "ka": "შემოხაზე კოორდინატების ცხრილი მართკუთხედით."},
    "mode_control":     {"en": "Click a grid intersection, then type its real X and Y.",
                         "ka": "დააწკაპე ბადის გადაკვეთა, შემდეგ ჩაწერე მისი ნამდვილი X და Y."},
    "mode_polygon":     {"en": "Click each polygon corner in order. Choose another action when done.",
                         "ka": "დააწკაპე პოლიგონის კუთხეები რიგზე. დასრულებისას აირჩიე სხვა მოქმედება."},

    # image sources
    "img_loaded":       {"en": "Loaded {name}", "ka": "ჩაიტვირთა {name}"},
    "img_captured":     {"en": "Captured from screen", "ka": "აღებულია ეკრანიდან"},
    "img_size":         {"en": "{src}  ({w}×{h} px)", "ka": "{src}  ({w}×{h} px)"},
    "pdf_page":         {"en": "{name} — page {page}/{total}", "ka": "{name} — გვ. {page}/{total}"},
    "open_map_title":   {"en": "Open map image", "ka": "რუკის სურათის გახსნა"},
    "ft_images":        {"en": "Images", "ka": "სურათები"},
    "ft_all":           {"en": "All files", "ka": "ყველა ფაილი"},
    "ft_pdf":           {"en": "PDF", "ka": "PDF"},
    "open_pdf_title":   {"en": "Open PDF", "ka": "PDF-ის გახსნა"},

    # dialogs / messages
    "err_title":        {"en": "Error", "ka": "შეცდომა"},
    "img_read_err":     {"en": "Could not read image:\n{path}", "ka": "სურათი ვერ წაიკითხა:\n{path}"},
    "pdf_cannot_title": {"en": "Cannot open PDF", "ka": "PDF ვერ გაიხსნა"},
    "grab_failed_title":{"en": "Screen grab failed", "ka": "ეკრანის აღება ვერ მოხერხდა"},
    "grab_cancelled":   {"en": "Screen grab cancelled.", "ka": "ეკრანის აღება გაუქმდა."},
    "grab_hint":        {"en": "Drag a rectangle over the PDF area to capture  —  Esc to cancel",
                         "ka": "გადაათრიე მართკუთხედი ასაღებ არეზე  —  Esc გასაუქმებლად"},
    "no_image_title":   {"en": "No image", "ka": "სურათი არ არის"},
    "no_image":         {"en": "Open a map image first.", "ka": "ჯერ გახსენი რუკის სურათი."},
    "no_sel_title":     {"en": "No selection", "ka": "არჩევანი არ არის"},
    "no_sel":           {"en": "Mark the table area first (button 1).",
                         "ka": "ჯერ მონიშნე ცხრილის არე (ღილაკი 1)."},
    "ocr_running":      {"en": "Running OCR…", "ka": "OCR მიმდინარეობს…"},
    "ocr_unavail_title":{"en": "OCR not available", "ka": "OCR მიუწვდომელია"},
    "ocr_err_title":    {"en": "OCR error", "ka": "OCR შეცდომა"},
    "ocr_backend_missing": {"en": "OCR backend missing.", "ka": "OCR ძრავა აკლია."},
    "ocr_failed":       {"en": "OCR failed.", "ka": "OCR ვერ შესრულდა."},
    "ocr_done":         {"en": "OCR done via {backend}: {n} rows. Double-click a cell to fix mistakes.",
                         "ka": "OCR შესრულდა ({backend}): {n} რიგი. ორმაგი დაწკაპუნებით ჩაასწორე."},
    "ocr_no_rows_title":{"en": "No rows parsed", "ka": "რიგები ვერ ამოვიცანი"},
    "ocr_no_rows":      {"en": "OCR ran but no coordinate rows were recognised.\n\nRaw text:\n{raw}",
                         "ka": "OCR გაეშვა, მაგრამ კოორდინატების რიგები ვერ ამოვიცანი.\n\nდაუმუშავებელი ტექსტი:\n{raw}"},
    "raw_empty":        {"en": "(empty)", "ka": "(ცარიელი)"},

    # fit
    "fit_need":         {"en": "Fit: need ≥2 control points",
                         "ka": "მორგება: საჭიროა ≥2 საკონტროლო წერტილი"},
    "fit_error":        {"en": "Fit error: {e}", "ka": "მორგების შეცდომა: {e}"},
    "fit_ok":           {"en": "Fit: {n} points, {note}", "ka": "მორგება: {n} წერტილი, {note}"},
    "fit_exact":        {"en": "exact/2-pt", "ka": "ზუსტი/2-წერტ."},
    "fit_rmse":         {"en": "RMSE={v:.2f} units", "ka": "RMSE={v:.2f} ერთ."},
    "no_fit_title":     {"en": "No fit", "ka": "მორგება არ არის"},
    "no_fit":           {"en": "Add at least 2 control points first.",
                         "ka": "ჯერ დაამატე მინიმუმ 2 საკონტროლო წერტილი."},
    "no_poly_title":    {"en": "No polygon", "ka": "პოლიგონი არ არის"},
    "no_poly":          {"en": "Click at least one polygon vertex.",
                         "ka": "დააწკაპე მინიმუმ ერთი პოლიგონის წვერო."},
    "computed":         {"en": "Computed {n} vertices from the affine fit.",
                         "ka": "გამოთვლილია {n} წვერო აფინური მორგებით."},
    "area_val":         {"en": "Area: {u:,.1f} units²  ({ha:,.4f} ha)",
                         "ka": "ფართობი: {u:,.1f} ერთ.²  ({ha:,.4f} ჰა)"},
    "area_need":        {"en": "Area: — (need ≥3 vertices)",
                         "ka": "ფართობი: — (საჭიროა ≥3 წვერო)"},

    # export
    "nothing_exp_title":{"en": "Nothing to export", "ka": "საექსპორტო არაფერია"},
    "nothing_exp":      {"en": "The table is empty.", "ka": "ცხრილი ცარიელია."},
    "export_failed":    {"en": "Export failed", "ka": "ექსპორტი ვერ მოხერხდა"},
    "file_locked":      {"en": "Could not save — the file is open in Excel. Close it and try again.",
                         "ka": "ვერ შეინახა — ფაილი Excel-ში გახსნილია. დახურე და სცადე ხელახლა."},
    "saved":            {"en": "Saved {name}", "ka": "შენახულია {name}"},
    "geo_note":         {"en": "coordinates via affine fit; verify against grid",
                         "ka": "კოორდინატები აფინური მორგებით; შეამოწმე ბადესთან"},

    # control-point dialog
    "cp_title":         {"en": "Control point", "ka": "საკონტროლო წერტილი"},
    "cp_pixel":         {"en": "Pixel: ({px:.0f}, {py:.0f})", "ka": "პიქსელი: ({px:.0f}, {py:.0f})"},
    "cp_realx":         {"en": "Real X:", "ka": "ნამდვილი X:"},
    "cp_realy":         {"en": "Real Y:", "ka": "ნამდვილი Y:"},
    "ok":               {"en": "OK", "ka": "დიახ"},
    "cancel":           {"en": "Cancel", "ka": "გაუქმება"},
    "cp_invalid_title": {"en": "Invalid", "ka": "არასწორი"},
    "cp_invalid":       {"en": "Enter numeric X and Y.", "ka": "ჩაწერე რიცხვითი X და Y."},
}


from ..i18n import translate


def make_tr(lang="en"):
    """დააბრუნებს tr(key, **fmt) ფუნქციას მოცემული ენისთვის (საერთო lookup)."""
    def tr(key, **fmt):
        return translate(TR, key, lang, **fmt)
    return tr
