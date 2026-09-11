# GIS_BOX

პატარა GIS ინსტრუმენტების კრებული ერთ ფანჯარაში (tkinter).
A small collection of GIS tools in one window (tkinter).

ინტერფეისი **ორენოვანია** — ქართული / English (ზედა ზოლის გადამრთველი).
The UI is **bilingual** — Georgian / English (top-bar switch).

GIS_BOX-ში მხოლოდ **სივრცითი / GIS** ხელსაწყოებია — მათ შორის **რუკის სერვისები**.
საოფისე-დოკუმენტური ხელსაწყოები (**დოკუმენტებში ძებნა**, **ფაილების შეგროვება**)
ცალკე პროექტშია — [Toolbox](../Toolbox).

GIS_BOX holds **spatial / GIS** tools only — Map services included. Office-document
tools (Document search, Collect files) live in a separate project — [Toolbox](../Toolbox).

---

## ინსტრუმენტები / Tools

| ინსტრუმენტი | აღწერა |
|---|---|
| **შაბლონის კოპირება** / Template copy | კოპირებს შაბლონურ shapefile-ს ყველა თანმხლები ფაილით (`.shp/.shx/.dbf/.prj/…`), ზრდადი სუფიქსით. რამდენიმე ნაკრები (მდინარის ნაპირი, გაზსადენის გადაკვეთა, დაცვის ზონა, UTM ბადე) — ახლის დამატება ერთი ჩანაწერით. |
| **ნაკვეთის ძებნა** / Parcel search | ეძებს საკადასტრო კოდებს File Geodatabase-ში და ქმნის Shapefile + GeoPackage; ვერ ნაპოვნ კოდებს ცალკე ინახავს. **რამდენიმე ბაზა** ჩამოსაშლელ სიაში; შრეები ავტომატურად იკითხება (CadData-ის რეგიონები ქართული სახელით — „R02 — ქვემო ქართლი“), შრე და კოდის ველი არჩევადია. |
| **კოორდინატების ამომღები** / Coordinate extractor | რუკის სურათიდან/PDF-იდან ამოიღებს კოორდინატების ცხრილს (OCR) ან გეო-რეფერენსით ითვლის პოლიგონის წვეროებსა და ფართობს; Excel-ში გატანა და ფორმატირება. |
| **სახელების გადარქმევა** / Rename → Latin | საქაღალდის ქართულ-სახელიან shapefile-ებს გადაარქმევს ლათინურად (სფეისი/სიმბოლო → `_`), წინასწარი სიით. ასევე ამოწმებს რომელ shapefile-ში დევს მასალა და რომელი ცარიელია. |
| **Shp → კოორდინატები** / Shp → coordinates | წერტილოვანი shapefile-იდან კითხულობს X/Y-ს UTM ზონით (37/38, .prj-დან ან ხელით), წინასწარი ცხრილით; გააქვს დაფორმატებულ Excel-ში — ტექსტური ქუდი, `№/X/Y`, არჩევითი „გადაკვეთის კუთხე“ (°), center+borders. **Batch** — საქაღალდის ყველა წერტილოვანი shapefile ერთბაშად. |
| **GDB → PostGIS** / GDB → PostGIS | ატანს ESRI Geodatabase-ის (`.gdb`/`.mdb`) შრეებს PostgreSQL/PostGIS-ში `ogr2ogr`-ით — შრეების არჩევა, კავშირის შემოწმება, რეჟიმები (overwrite/append/update), რეპროექცია, **ინკრემენტული სინქრონი**, **განრიგი** და **ისტორია/აუდიტი**. სჭირდება GDAL (QGIS/OSGeo4W) და PostGIS ბაზა. → იხ. [ცალკე სექცია](#gdb--postgis). |
| **გეომეტრიების შეგროვება** / Geometry → GeoPackage | საქაღალდის ხეში პოულობს **მონიშნული ვექტორული ფორმატის** ფაილებს (SHP, DXF, DWG, GPKG, GeoJSON, KML, GML, MapInfo, .gdb და სხვ. — **ნებისმიერი GDAL ვექტორული ფორმატი**, `+ სხვა` ველით), კითხულობს გეომეტრიებს და აერთიანებს **ერთ GeoPackage-ში სამ შრედ**: წერტილები, ხაზები, პოლიგონები (Multi-გეომეტრიად, `src_file`/`src_layer`/`src_type` ველებით). გამომავალი CRS — ავტომატური (პირველი ნაპოვნი) ან UTM 37N/38N. ფონურ ნაკადში, დათვლა/გაუქმებით. DWG-ს სჭირდება GDAL-ის CAD დრაივერი (QGIS/OSGeo4W); წაუკითხავი ფაილი გამოტოვდება და ლოგში აისახება. |
| **რუკის სერვისები** / Map services | tile / WMS სერვისების URL-ები (Google basemaps, ორთოფოტო, NAPR) — ArcMap / QGIS-ში ჩასასმელად, ერთი ღილაკით კოპირებით. სია იკითხება რეპოს ძირის `map_services.txt`-იდან (სახელის ხაზი, შემდეგ URL-ის ხაზი) — ახლის დამატება ფაილის რედაქტირებით, კოდის შეხების გარეშე. ზოგი სერვისი მოითხოვს VPN-ს / წვდომას. |

---

## GDB → PostGIS

ESRI File/Personal Geodatabase-ის (`.gdb` / `.mdb`) შრეების PostgreSQL/PostGIS-ში
ატანა `ogr2ogr`-ით. ძრავა აღებულია დამოუკიდებელი MIT პროექტიდან (`gdb2postgis`) და
GIS_BOX-ში ჩაშენებულია **native tkinter**-ით — ახალი pip-პაკეტის გარეშე.

Loads ESRI File/Personal Geodatabase (`.gdb` / `.mdb`) layers into PostgreSQL/PostGIS
with `ogr2ogr`. The engine is reused from the standalone MIT `gdb2postgis` project and
embedded natively in tkinter — no extra pip dependency.

**მოთხოვნები / Requirements**
- GDAL-ის `ogr2ogr` / `ogrinfo` სისტემაში (მაგ. **QGIS** ან **OSGeo4W**) — ავტომატურად აღმოაჩენს.
- ხელმისაწვდომი **PostgreSQL/PostGIS** ბაზა.

**ფუნქციები / Features**
- **წყარო + შრეები** — მიუთითებ საქაღალდეს, ირჩევ `.gdb`/`.mdb`-ს და მონიშნავ ასატან შრეებს.
- **კავშირი** — host / port / database / user / password / schema; ღილაკი „კავშირის შემოწმება“.
- **რეჟიმები** — `overwrite` / `append` / `update`; რეპროექცია (`EPSG:…`), ცხრილის პრეფიქსი,
  PROMOTE_TO_MULTI, GiST ინდექსი, სწრაფი COPY.
- **ინკრემენტული სინქრონი** — მხოლოდ ცვლილებების ატანა: `key` ველით (მაგ. `OBJECTID`) და
  `change` ველით (მაგ. `last_edited_date`), watermark-ის მიხედვით (ველების ავტო-აღმოჩენით);
  არჩევით — წაშლილების დეტექცია. პირველი გაშვება = სრული load + watermark; შემდეგ = მხოლოდ
  `change > watermark` რიგები, upsert-ით.
- **განრიგი** — ავტომატური გაშვება ყოველ N წუთი/საათი/დღეში (tkinter `after()`, გარე
  დამოკიდებულების გარეშე); „შემდეგი გაშვების“ ჩვენებით, overlap-ის გარეშე.
  ☑ **„GIS_BOX-ის დახურვის შემდეგაც“** — Windows-ზე რეგისტრირდება **Task Scheduler**-ის
  დავალება, რომელიც headless-ად (`gis_box.py --gdb2pg-run`) უშვებს იმპორტს აპის გარეშეც.
  ამისთვის საჭიროა შენახული პაროლი („პაროლის დამახსოვრება“) ან `PGPASSWORD`/`GDB2PG_PGPASSWORD`.
- **ისტორია / აუდიტი** — „🕘 ისტორია…“: თარიღით ნახავ ყოველ გაშვებას (რამდენი ობიექტი,
  მათი ID-ებით), წაშლი ჩანაწერს, ან ამ ობიექტებს ბაზიდანაც მოაშორებ.

**უსაფრთხოება / Security**
- კავშირის პარამეტრები ინახება ლოკალურ `gis_box_settings.json`-ში (git-ignored).
  **პაროლი ნაგულისხმევად მხოლოდ სესიაშია** — ინახება მხოლოდ თოლიის მონიშვნისას, ლოკალურად.
- watermark-ები და აუდიტი ლოკალურ, **git-ignored** ფაილებშია
  (`gdb2postgis_sync_state.json`, `gdb2postgis_audit.db`) — რეპოზე არასდროს ადის.
  პაროლი ლოგებში ინიღბება.

Connection settings live in a git-ignored `gis_box_settings.json`; the **password is
session-only by default** (stored locally only if you tick the box). Sync watermarks and
the audit history are kept in git-ignored files and never committed; passwords are masked in logs.

---

## ჩამოტვირთვა (მზა ბილდი) / Download (prebuilt)

Python-ის გარეშე გასაშვებად იხილე **[Releases](https://github.com/kapo-Toolkits/gis-toolkit/releases)** —
`v*` ტეგზე CI ავტომატურად აწყობს დამოუკიდებელ ბილდებს:

For a no-Python run, see the **[Releases](https://github.com/kapo-Toolkits/gis-toolkit/releases)** page —
each `v*` tag builds standalone artifacts:

| პლატფორმა | ფაილი |
|---|---|
| Windows | `GIS_BOX-windows-x64.zip` (გახსენი და გაუშვი `GIS_BOX.exe`) |
| Linux | `GIS_BOX-linux-x64.tar.gz`, `.deb`, `.rpm`, `.AppImage` |

ლოკალურად ასაწყობად: `pip install pyinstaller -r requirements.txt && pyinstaller gis_box.spec`
(გამოსავალი — `dist/GIS_BOX/`).

---

## გაშვება / Run

```bash
python gis_box.py
```

ან Windows-ზე ორმაგი დაწკაპუნებით: `GIS_BOX.bat`.
Or on Windows double-click `GIS_BOX.bat`.

### დამოკიდებულებები / Dependencies

ბაზისური ხელსაწყო (შაბლონის კოპირება) მხოლოდ სტანდარტულ ბიბლიოთეკას იყენებს.
დანარჩენი ხელსაწყოებისთვის:

The base tool (template copy) uses only the standard library. For the other tools:

```bash
pip install -r requirements.txt
```

თუ პაკეტი აკლია, GIS_BOX მაინც გაიხსნება — შესაბამისი ხელსაწყო უბრალოდ შეცდომას აჩვენებს.
If a package is missing, GIS_BOX still opens — the affected tool just shows an error.

**GDB → PostGIS** ხელსაწყოს pip-პაკეტი არ სჭირდება, მაგრამ სისტემაში უნდა იყოს
GDAL-ის `ogr2ogr`/`ogrinfo` (მაგ. QGIS ან OSGeo4W) და ხელმისაწვდომი PostgreSQL/PostGIS ბაზა.

The **GDB → PostGIS** tool needs no pip package, but requires GDAL's `ogr2ogr`/`ogrinfo`
on the system (e.g. QGIS or OSGeo4W) and a reachable PostgreSQL/PostGIS database.

---

## კონფიგურაცია / Configuration

**ნაკვეთის ძებნა** მოითხოვს შენი File Geodatabase-ის გზას. ეს გზა **კოდში არ იწერება**:

The **Parcel search** tool needs the path to your File Geodatabase. This path is **not stored in the code**:

1. ხელსაწყოში ჩაწერე GDB-ის გზა, შრე და კოდის ველი.
   Enter the GDB path, layer and code field in the tool.
2. დააჭირე **„💾 პარამეტრების დამახსოვრება“**.
   Click **“💾 Remember settings”**.
3. პარამეტრები შეინახება ლოკალურ `gis_box_settings.json`-ში და მომდევნო გაშვებაზეც დაიმახსოვრდება.
   Settings are saved to the local `gis_box_settings.json` and remembered next time.

`gis_box_settings.json` და `config.txt` **`.gitignore`-შია** და GitHub-ზე არ აიტვირთება.
`gis_box_settings.json` and `config.txt` are **git-ignored** and never uploaded to GitHub.

ალტერნატივა (არასავალდებულო): დააკოპირე `config.example.txt` → `config.txt` და ჩაწერე გზა.
Alternative (optional): copy `config.example.txt` → `config.txt` and set your path.

რამდენიმე ბაზა ერთბაშად — `config.txt`-ში: `GDBS=path1;path2;path3` (ან ხელსაწყოში
თითო ბაზა დაამატე „💾 დამახსოვრებით“). ხელსაწყო ჩამოსაშლელ სიაში გადაგირთავს.

Several databases at once — in `config.txt`: `GDBS=path1;path2;path3` (or add each one in the
tool via “💾 Remember”). The tool switches between them via the dropdown.

---

## პროექტის სტრუქტურა / Project layout

```
GIS_BOX/
├─ gis_box.py                # მთავარი აპლიკაცია / main app (sidebar + lazy loading)
├─ tools/
│  ├─ base.py                # ToolFrame ბაზისური კლასი
│  ├─ parcel_search.py       # ნაკვეთის ძებნა (მრავალი ბაზა)
│  ├─ rename_transliterate.py# სახელების გადარქმევა + მასალის შემოწმება
│  ├─ shp_coords.py          # Shp → კოორდინატები (Excel, batch)
│  ├─ gdb2postgis.py         # GDB → PostGIS (tkinter UI)
│  ├─ gdb2postgis_core.py    # ↳ ძრავა (ogr2ogr, GUI-free; MIT, vendored)
│  ├─ geom_collect.py        # გეომეტრიების შეგროვება → GeoPackage (tkinter UI)
│  ├─ geom_collect_core.py   # ↳ წაკითხვა/კლასიფიკაცია/ჩაწერა (GUI-free)
│  ├─ map_services.py       # რუკის სერვისები (tile/WMS URL-ები, კოპირება)
│  ├─ coord_tool.py          # კოორდინატების ამომღების wrapper
│  ├─ coordextract/          # OCR + გეო-რეფერენსის პაკეტი
│  ├─ translit.py            # ქართული→ლათინური (სუფთა ლოგიკა)
│  ├─ fields.py              # კოდის ველის ავტო-შერჩევა
│  ├─ regions.py             # CadData რეგიონების სახელები
│  └─ xlsx_format.py         # საერთო Excel-ფორმატირება
├─ tests/                    # pytest — სუფთა ლოგიკის ტესტები
├─ packaging/                # nfpm (.deb/.rpm) + .desktop
├─ gis_box.spec              # PyInstaller — დამოუკიდებელი ბილდი
├─ shp/                      # შაბლონური shapefile-ები (ცარიელი / საჯარო UTM ბადე)
├─ config.example.txt        # კონფიგის ნიმუში (config.txt git-ignored)
├─ map_services.txt          # რუკის სერვისების სია (სახელი / URL ხაზ-ხაზ)
├─ GIS_BOX.bat / .command / .desktop  # გამშვებები Windows / macOS / Linux
├─ requirements.txt          # ხელსაწყოების დამოკიდებულებები
└─ requirements-dev.txt      # ტესტების/დეველოპმენტის დამოკიდებულებები
```

ახალი ხელსაწყოს დასამატებლად: შექმენი `ToolFrame`-ის მემკვიდრე კლასი და დაარეგისტრირე
`gis_box.py`-ის `_build_tool_specs()`-ში. სუფთა ლოგიკა (გამოთვლა/ფორმატირება) ცალკე
მოდულში გაიტანე (`tools/`-ში), რომ GUI-ს გარეშე დატესტვადი იყოს.

To add a new tool: subclass `ToolFrame` and register it in `_build_tool_specs()` in `gis_box.py`.
Keep pure logic (computation/formatting) in a separate module so it is testable without the GUI.

---

## ტესტები / Tests

სუფთა ლოგიკა (ტრანსლიტერაცია, ველის შერჩევა, რეგიონები, Excel-ფორმატირება) დაფარულია
pytest-ით; CI ყოველ push/PR-ზე უშვებს მათ Python 3.11/3.12-ზე.

Pure logic (transliteration, field selection, regions, Excel formatting) is covered by pytest;
CI runs it on every push/PR (Python 3.11/3.12).

```bash
pip install -r requirements-dev.txt
pytest
```

---

## ლიცენზია / License

MIT — იხ. [LICENSE](LICENSE).
