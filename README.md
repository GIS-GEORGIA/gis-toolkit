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

📘 **ტექნიკური აღწერა / Technical overview:** [docs/TECHNICAL.md](docs/TECHNICAL.md) — არქიტექტურა, ალგორითმები, შეფუთვა, ტესტირება.

---

## GIS_BOX V2 (ფილიალი `feature/gis-box-v2`) / V2 branch

ახალი ინტერფეისი **PySide6**-ზე, ცენტრალური ლოგირებით, უსაფრთხო CRS მენეჯმენტითა და GitHub-ზე დაფუძნებული
განახლებებით. კლასიკური ვერსია (`gis_box.py`, `GIS_BOX.exe`) **უცვლელია და ისევ მუშაობს**; V2 `main`-ში ჯერ არ არის შეერთებული.

A new **PySide6** interface with centralized logging, safe CRS handling and GitHub-based updates.
The classic app is unchanged; V2 is **not merged into `main`** yet.

```bash
python gis_box_v2.py               # V2 (Windows: GIS_BOX_V2.bat · Linux: ./GIS_BOX_V2.sh)
python gis_box_v2.py --selftest    # ფანჯრის აგების შემოწმება GUI-ს გარეშე / headless self-test
python -m tools.env_check          # გარემოს დიაგნოსტიკა / environment diagnostics
```

- გვერდითი მენიუ: ძებნა, ფავორიტები, ბოლოს გამოყენებული, კატეგორიები · ღია/მუქი თემა · ქართული/English ·
  ფონური დამუშავება პროგრესითა და გაუქმებით · შეტყობინებები.
- **ნატიური V2 ხელსაწყოები:** CRS მენეჯერი, განახლებები, ბუფერების აგება, რუკის სერვისები, სახელების გადარქმევა, Shp → კოორდინატები, დაცვის ზონის კვეთა, კვეთა და შაბლონი, გეომეტრიების შეგროვება, DWG/DXF კონვერტაცია, ნაკვეთის ძებნა, კოორდინატების ამომღები, ბაზებს შორის მონაცემთა გადატანა, GDB → PostGIS — ყველა 14 ხელსაწყო. კლასიკური ფანჯარა უცვლელად რჩება და ცალკეც ეშვება.
- **CRS მენეჯერი:** CRS-ის აღმოჩენა, მინიჭება (`set_crs`, **მხოლოდ დადასტურებით**) და გადაყვანა (`to_crs`) **ახალ** ფაილში, ანგარიშით.
- **ლოგირება:** 3 დონე (მომხმარებლის / დეტალური / debug), TXT + JSONL + SQLite ისტორია, პაროლებისა და ტოკენების ამოჭრა.
- **განახლებები:** GitHub Releases, SHA256, ბექაპი და უკან დაბრუნება; ჩამოტვირთვა/ინსტალაცია მხოლოდ დასტურით.

| დოკუმენტი | შინაარსი |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | ინსტალაცია და გაშვება — Windows / Linux, პარამეტრების ადგილები |
| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | core / optional დამოკიდებულებები, სისტემური ბიბლიოთეკები |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | პრობლემების გადაჭრა |
| [docs/v2_shell.md](docs/v2_shell.md) | V2 ინტერფეისის არქიტექტურა და გადატანის სტატუსი |
| [docs/crs_manager.md](docs/crs_manager.md) | CRS მენეჯერი და გაზომვების აუდიტი |
| [docs/logging.md](docs/logging.md) | ცენტრალური ლოგირება |
| [docs/update_manager.md](docs/update_manager.md) | განახლებების მენეჯერი და მისი შეზღუდვები |
| [docs/db_transfer.md](docs/db_transfer.md) · [docs/gdb_to_postgis.md](docs/gdb_to_postgis.md) | ბაზების გადატანა |

---

## ინსტრუმენტები / Tools

| ინსტრუმენტი | აღწერა |
|---|---|
| **ნაკვეთის ძებნა** / Parcel search | ეძებს საკადასტრო კოდებს File Geodatabase-ში და ქმნის Shapefile + GeoPackage; ვერ ნაპოვნ კოდებს ცალკე ინახავს. **რამდენიმე ბაზა** ჩამოსაშლელ სიაში; შრეები ავტომატურად იკითხება (CadData-ის რეგიონები ქართული სახელით — „R02 — ქვემო ქართლი“), შრე და კოდის ველი არჩევადია. **დამატებით — შეიპების ანალიზი:** აირჩევ საქაღალდეს, ის რეკურსიულად სკანირდება და ყველა shapefile იზომება (პოლიგონი — ფართი/პერიმეტრი, ხაზი — სიგრძე, ყველა — რაოდენობა; მეტრებში, UTM 37/38). ლოგში იბეჭდება რანჟირებები (ტოპ N): რომელია ყველაზე დიდი ფართით/პერიმეტრით, ყველაზე გრძელი და ა.შ. — ყოველ შრეს თან **საქაღალდის სრული გზა** ახლავს (ერთნაირი სახელები ბევრ საქაღალდეშია). CRS-გარეშე/ცარიელი/წაუკითხავი შრეები ცალკე ჩამოითვლება. |
| **კოორდინატების ამომღები** / Coordinate extractor | რუკის სურათიდან/PDF-იდან ამოიღებს კოორდინატების ცხრილს (OCR) ან გეო-რეფერენსით ითვლის პოლიგონის წვეროებსა და ფართობს; Excel-ში გატანა და ფორმატირება. |
| **სახელების გადარქმევა** / Rename → Latin | საქაღალდის ქართულ-სახელიან shapefile-ებს გადაარქმევს ლათინურად (სფეისი/სიმბოლო → `_`), წინასწარი სიით. ასევე ამოწმებს რომელ shapefile-ში დევს მასალა და რომელი ცარიელია. |
| **Shp → კოორდინატები** / Shp → coordinates | წერტილოვანი shapefile-იდან კითხულობს X/Y-ს UTM ზონით (37/38, .prj-დან ან ხელით), წინასწარი ცხრილით; გააქვს დაფორმატებულ Excel-ში — ტექსტური ქუდი, `№/X/Y`, არჩევითი „გადაკვეთის კუთხე“ (°), center+borders. **Batch** — საქაღალდის ყველა წერტილოვანი shapefile ერთბაშად. |
| **GDB → PostGIS** / GDB → PostGIS | ატანს ESRI Geodatabase-ის (`.gdb`/`.mdb`) შრეებს PostgreSQL/PostGIS-ში `ogr2ogr`-ით — შრეების არჩევა, კავშირის შემოწმება, რეჟიმები (overwrite/append/update), რეპროექცია, **ინკრემენტული სინქრონი**, **განრიგი** და **ისტორია/აუდიტი**. სჭირდება GDAL (QGIS/OSGeo4W) და PostGIS ბაზა. → იხ. [ცალკე სექცია](#gdb--postgis). |
| **გეომეტრიების შეგროვება** / Geometry → GeoPackage | საქაღალდის ხეში პოულობს **მონიშნული ვექტორული ფორმატის** ფაილებს (SHP, DXF, DWG, GPKG, GeoJSON, KML, GML, MapInfo, .gdb და სხვ. — **ნებისმიერი GDAL ვექტორული ფორმატი**, `+ სხვა` ველით), კითხულობს გეომეტრიებს და აერთიანებს **ერთ GeoPackage-ში სამ შრედ**: წერტილები, ხაზები, პოლიგონები (Multi-გეომეტრიად, `src_file`/`src_layer`/`src_type` ველებით). გამომავალი CRS — ავტომატური (პირველი ნაპოვნი) ან UTM 37N/38N. ფონურ ნაკადში, დათვლა/გაუქმებით. DWG-ს სჭირდება GDAL-ის CAD დრაივერი (QGIS/OSGeo4W); წაუკითხავი ფაილი გამოტოვდება და ლოგში აისახება. |
| **DWG/DXF → SHP/GPKG/GDB** | ერთი `.dxf`/`.dwg` ფაილის ან მთელი საქაღალდის **კონვერტაცია** ESRI Shapefile / GeoPackage / File Geodatabase ფორმატში — **ღია კოდით**, **ArcGIS-ის, AutoCAD-ის ან QGIS-ის გარეშე**. თითო წყარო-ფაილს თავისი გამომავალი შეესაბამება (არა შერწყმა); Shapefile/GDB-ისთვის შერეული გეომეტრიის შრე (წერტილი+ხაზი+პოლიგონი ერთად — DXF-ში ხშირია) ავტომატურად იყოფა წერტილად/ხაზად/პოლიგონად, GeoPackage კი ერთ შრეში ინარჩუნებს. ქართული (და სხვა non-ASCII) ფაილის სახელი ლათინურდება. CRS — წყაროსეული ან UTM 37N/38N. **DXF ყოველთვის იკითხება.** **DWG-სთვის GIS_BOX-ს თან ატანია GNU LibreDWG** (`tools/vendor/libredwg/`, GPL-3.0) — **არაფრის დაყენება არ სჭირდება**; საიმედოდ კითხულობს თანამედროვე DWG-საც (r13–r2018), ხოლო QGIS-ის ჩვეული `libopencad`-ის დრაივერი მხოლოდ ძველ R2000-ს (გადამოწმებულია PyQGIS-ითაც — იგივე შედეგი, იმავე დრაივერს იყენებს). თუ GDAL-ის DXF-რიდერი კონკრეტულ ობიექტზე ვარდება, **`ezdxf`** (სუფთა Python, MIT) ავტომატურად აღადგენს. გამომავალ ფაილს შეგროვების თარიღი ეწერება სახელში (დდთთწწ): `collected_geometry.gpkg` → `collected_geometry_041126.gpkg` (იმავე დღეს ხელახლა გაშვება მას გადაწერს). |
| **დაცვის ზონის კვეთა** / Zone intersection | ნაკვეთის და დაცვის ზონის პოლიგონური shapefile-ებიდან პოულობს **წერტილებს, სადაც ნაკვეთის საზღვარი კვეთს ზონის საზღვარს** (arcpy `Intersect(output_type="POINT")`-ის ანალოგი, shapely-ით), და ითვლის **ნაკვეთის/მოჭრილი (ნაკვეთი∩ზონა)/დარჩენილი ნაწილის ფართებს** სწორ UTM ზონაში — ეს უკანასკნელი ჩაიწერება Excel-ში კოორდინატების გვერდით, ასევე „მოჭრილი“ და ნაკვეთის „დარჩენილი“ (ნაკვეთი − ზონა) ნაწილის ცალკე shapefile-ებად შენახვაც შეიძლება (`Parcel_clipped_part38_1`, `Parcel_remaining_part38_1`). ზონა აირჩევა ატრიბუტით (ველი + მნიშვნელობა, მაგ. I/II) ან „ყველა ზონა“; შედეგი იწერება წერტილოვან shapefile-ად (`.prj`-თი, UTM ავტო-ცნობისთვის). შესვლის გზები **💾 დასამახსოვრებელია**. პირდაპირ გადადის **„Shp → კოორდინატებში“** ან იქვე გამოაქვს Excel ცხრილი. გვერდის ბოლოში — დამატებით, **მზა `Gas_Pipe_ProtZone_Crossing37/38`-ის ფაილების კოპირების** სექცია (სხვაგან შექმნილი ფაილისთვის, თავიდან გამოთვლის ნაცვლად). |
| **კვეთა და შაბლონი** / Crossing & templates | იგივე ლოგიკა ორ **ხაზოვან** shapefile-ზე (მაგ. გაზსადენი × კომუნიკაცია) — პოულობს **წერტილებს, სადაც ხაზები იკვეთება** (`line ∩ line`). გეომეტრია ავტომატურად ცნობს: პოლიგონი→საზღვარი, ხაზი→თავად ხაზი. ზუსტად ისეთივე გამოტანა — დანომრილი წერტილოვანი shapefile (`.prj`-თი) + **„Shp → კოორდინატები“** / Excel. გვერდის ბოლოში — დამატებით, 3 ცალკე გამოყოფილი სექცია მზა შაბლონური ფაილების კოპირებისთვის ყველა თანმხლები ფაილით (`.shp/.shx/.dbf/.prj/…`, ზრდადი სუფიქსით): **მდინარის ნაპირი**, **გაზსადენის გადაკვეთა**, **UTM ბადე**. |
| **ბუფერების აგება** / Line buffers | აირჩევ საქაღალდეს და მასში **ხაზოვან shapefile-ს**, ბუფერის ტიპს (1/2/3) და იმ ბუფერებს, რაც გჭირდება; თითო ბუფერი **ცალკე shapefile**-ად ჩაიწერება მითითებულ საქაღალდეში, ინდექსით (`gas_protection_zone_1_1`, `gas_protection_zone_2_1`, `gas_safety_zone_3_1`, `gas_consultation_zone_4_1` …; ხელახლა გაშვებაზე `_2`, `_3`…). ტიპი 1: 4/25/200/500 მ; ტიპი 2: 4/10/500 მ; ტიპი 3: 4/25/100 მ. ხაზები ჯერ ერთიანდება, ამიტომ ბუფერი ერთიანი პოლიგონია. გამოიყენება მხოლოდ **EPSG:32637 / 32638**; სხვა CRS-ზე (მათ შორის გეოგრაფიულ 4326-ზე) შეგთავაზებს გადაყვანას შრის მდებარეობის შესაბამის ზონაში (თანხმობით, საწყისი ფაილი არ იცვლება), CRS-გარეშეს უარყოფს. |
| **ბაზებს შორის მონაცემთა გადატანა** / Database Data Transfer | ერთი ESRI **Personal Geodatabase**-იდან (`.mdb`) მეორეში გადააქვს არჩეული წლის (ნაგულისხმევი 2026: 1 იანვარი 00:00:00 – 31 დეკემბერი 23:59:59) სივრცითი ობიექტები — **წერტილი → წერტილი, ხაზი → ხაზი, პოლიგონი → პოლიგონი**, გეომეტრიით (ბაიტ-ბაიტ, CRS-ის დამთხვევისას) და ყველა ატრიბუტით. ფენები ემთხვევა **გეომეტრიის ტიპით** (არა სახელით; ორაზროვნებისას ხელით არჩევ). **დუბლიკატის წესი:** ჩანაწერი გამოტოვდება მხოლოდ თუ მიმღების იმავე ფენაში უკვე არის იგივე `werilis_no` **ამავე წლის** `TariRI`-თი; იგივე ნომერი სხვა წლით — ჩაიწერება. ცარიელი/არასწორი თარიღის ჩანაწერები ანგარიშში ჩამოითვლება; ჩანაწერები, რომლებსაც თარიღი **საერთოდ არ აქვთ** (NULL), არჩევით (ნაგულისხმევად ჩართული) ინახება **ცალკე ახალ Personal Geodatabase-ში** (`<წყარო>_no_date_თარიღი.mdb`, ყველა ატრიბუტით და ზუსტი გეომეტრიით; წყაროსა და მიმღებში არაფერი იცვლება). არჩევითი თოლია **„გადატანილი ჩანაწერების ცალკე ახალ ბაზაში შენახვა“** — მიმღებში რეალურად ჩაწერილი ზუსტად იგივე ჩანაწერების ასლი ახალ `<მიმღები>_transferred_<წელი>_დრო.mdb`-ში (მიმღები ჩვეულებრივად იწერება). მეორე თოლია — **ერთ საერთო ბაზაშიც ჩაწერა**: ფიქსირებული `<მიმღები>_transferred_ALL_YEARS.mdb` პირველ გაშვებაზე იქმნება, შემდეგ წლებზე/გაშვებებზე ემატება (არსებული არ იცვლება; იგივე `werilis_no` + წელი არ მეორდება). თოლიები დამოუკიდებელია. **წელი:** ერთი (`2026`), დიაპაზონი (`2024-2026`), სია (`2024, 2026`) ან `ყველა` (წყაროში არსებული ყველა წელი) — რამდენიმე წელი მუშავდება ერთიმეორის მიყოლებით: თითო წელი ცალკე ანალიზდება და ადასტურებ, იწერება ცალკე ლოგით; ბოლოს ჯამური შეტყობინება. ღილაკი **„ყველა წლის ერთ ბაზაში გაერთიანება“** — არჩეულ ბაზებს (მაგ. წელი-წლობით გადატანილებს, Ctrl-ით რამდენიმე) აერთიანებს ერთ ახალ `<სახელი>_ALL_YEARS_დრო.mdb`-ში (წერტილი/ხაზი/პოლიგონი; იგივე `werilis_no` + იგივე წელი არ მეორდება; არჩეული ბაზები მხოლოდ იკითხება; ცალკე ლოგით). მუშაობს ეტაპობრივად: **შემოწმება → ანალიზი (არაფერი იწერება) → დადასტურება (ფენების რიცხვებით) → ჩაწერა ერთ ტრანზაქციაში** (ყველა ფენა ერთად — ან არაფერი; ბექაპი ჩაწერამდე), შემდეგ ვერიფიკაცია. **ლოგები:** ყოველი გაშვება/წელი — ცალკე ფაილი საქაღალდეში `db_transfer_logs` (მიმღების გვერდით), სახელში წელი + წყარო + მიმღები + დრო (`db_transfer_2026_baza_to_OMIKO_BAZA_20261120_142600.log`); არსებული ლოგი არასდროს იწერება გადაუწერლად — ანალიზი, ჩაწერა და შეჯამება ერთ ფაილშია. შიგნით: ბაზების ინვენტარი **წლების მიხედვით** (წყარო და მიმღები, ფენა-ფენა), **ყოველი ჩანაწერის** გადაწყვეტილება (გამოტოვებული — მიმღების რომელი OBJECTID-ის გამო; ჩაწერილი — წყაროს OBJECTID → ახალი OBJECTID; შეცდომა/თარიღი არ აქვს/არასწორი თარიღი), ფენა-ფენა და საერთო საბოლოო ცხრილი (წერტილი/ხაზი/პოლიგონი: ნაპოვნი, დუბლიკატი, ჩაიწერა, შეცდომა), მიმღების მწკრივები/ინდექსი/ექსტენტი ჩაწერამდე და შემდეგ, ხანგრძლივობა. გვერდით ინახება `…_records.csv` (ყველა ჩანაწერი, Excel-ში იხსნება) და საერთო ისტორია `db_transfer_history.csv` (ყველა გაშვება/წელი ერთ ცხრილში). წყარო მხოლოდ იკითხება, მიმღებში არაფერი იშლება/იცვლება; ორივე ბაზა უნდა იყოს **დახურული ArcGIS Pro/ArcMap/Access-ში**. სჭირდება `pyodbc` და 64-ბიტიანი „Microsoft Access Database Engine“ ODBC დრაივერი (Windows). რატომ ODBC: PGeo GDAL-ში მხოლოდ წასაკითხია, ArcGIS Pro 3.x ამ ფორმატს ვერ კითხულობს — ჩაწერისას ვინახავთ `SHAPE`-ს, სივრცით ინდექსს (`<ფენა>_SHAPE_Index`) და ექსტენტს (`GDB_GeomColumns`) ისე, როგორც ArcGIS ინახავს. |
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

Python-ის გარეშე გასაშვებად იხილე **[Releases](https://github.com/GIS-GEORGIA/gis-toolkit/releases)** —
`v*` ტეგზე CI ავტომატურად აწყობს დამოუკიდებელ ბილდებს:

For a no-Python run, see the **[Releases](https://github.com/GIS-GEORGIA/gis-toolkit/releases)** page —
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

V2 ინტერფეისი: `python gis_box_v2.py` (`GIS_BOX_V2.bat` / `GIS_BOX_V2.sh`). დეტალურად — [docs/INSTALL.md](docs/INSTALL.md).

### Linux (და macOS)

პროგრამა Linux-ზეც მუშაობს — ერთი და იგივე კოდი, პლატფორმაზე დამოკიდებული ნაწილები
(შრიფტები, ფაილის გახსნა, ხატულა, კონფიგის საქაღალდე) ავტომატურად ირჩევა
(`tools/platform_utils.py`, `tools/apppaths.py`).

The program runs on Linux too — same code; platform-specific parts (fonts, opening files,
window icon, config folder) are chosen automatically.

```bash
sudo apt install python3-tk python3-venv fonts-dejavu-core   # Debian/Ubuntu
sh install_linux.sh          # .venv + დამოკიდებულებები + მენიუს ჩანაწერი / venv + deps + menu entry
./GIS_BOX.sh                 # გაშვება / run
```

- **tkinter** სისტემური პაკეტია (`python3-tk`; Fedora: `python3-tkinter`; Arch: `tk`).
- **ქართული ტექსტი:** DejaVu Sans ფარავს ქართულს (ჩვეულებრივ უკვე დაყენებულია).
- **პარამეტრები** ინახება `~/.config/GIS_BOX/` (ან `$XDG_CONFIG_HOME/GIS_BOX`); `.deb`/`.rpm`-ით
  დაყენებისასაც (`/opt/gis-box` read-only-ა). `GIS_BOX_DATA_DIR`-ით შეგიძლია სხვა ადგილი მიუთითო.
  Settings live in `~/.config/GIS_BOX/`; override with `GIS_BOX_DATA_DIR`.
- **ჯერ მხოლოდ Windows-ზე** (Linux-ზე ჩუმად გამოირთვება, დანარჩენი მუშაობს): Excel-ის ღია
  ფაილის ავტო-დახურვა (COM), ცხრილის HTML-ად კოპირება ბუფერში (Linux-ზე — მხოლოდ ტექსტი),
  GDB → PostGIS-ის ფონური განრიგი Task Scheduler-ით (Linux-ზე გამოიყენე `cron` ბრძანებით
  `python gis_box.py --gdb2pg-run`; აპლიკაციაშივე განრიგი მუშაობს).
  Windows-only for now (silently disabled on Linux): auto-closing an open Excel file,
  HTML clipboard tables (text only on Linux), Task Scheduler background sync (use `cron`).
- GDB → PostGIS-ს სჭირდება `ogr2ogr` (`sudo apt install gdal-bin`) — PATH-ში ავტომატურად ჩანს.
- CI ამოწმებს Linux-ზე მთელ ფანჯარას რეალურად (xvfb + GUI smoke-ტესტი).

### დამოკიდებულებები / Dependencies

ბაზისური ხელსაწყო (შაბლონის კოპირება) მხოლოდ სტანდარტულ ბიბლიოთეკას იყენებს.
დანარჩენი ხელსაწყოებისთვის:

The base tool (template copy) uses only the standard library. For the other tools:

```bash
pip install -r requirements.txt                                  # ძველი სრული სია / full legacy list
pip install -r requirements-core.txt -r requirements-optional.txt # V2: ძირითადი + არასავალდებულო
python -m tools.env_check                                        # რა აკლია და როგორ დავაყენო
```

სრული აღწერა (სისტემური ბიბლიოთეკები, PySide6-ის იმპორტის რიგი Windows-ზე): [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

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
├─ gis_box_v2.py             # V2 შესასვლელი (PySide6) / V2 entry point
├─ v2/                       # V2 გარსი: main_window, workers (thread + Qt signals), registry, settings, themes, pages/
├─ tools/
│  ├─ version.py             # ერთადერთი ვერსიის განსაზღვრა (SemVer)
│  ├─ env_check.py           # გარემოს დიაგნოსტიკა
│  ├─ crs_manager.py         # CRS: აღმოჩენა / set_crs / to_crs / ანგარიში (GUI-free)
│  ├─ logging_manager.py     # ცენტრალური ლოგირება (TXT/JSONL/SQLite, საიდუმლოების ამოჭრა)
│  ├─ update_manager.py      # GitHub Releases განახლებები (stdlib, GUI-free)
│  ├─ base.py                # ToolFrame ბაზისური კლასი
│  ├─ parcel_search.py       # ნაკვეთის ძებნა (მრავალი ბაზა)
│  ├─ rename_transliterate.py# სახელების გადარქმევა + მასალის შემოწმება
│  ├─ shp_coords.py          # Shp → კოორდინატები (Excel, batch)
│  ├─ gdb2postgis.py         # GDB → PostGIS (tkinter UI)
│  ├─ gdb2postgis_core.py    # ↳ ძრავა (ogr2ogr, GUI-free; MIT, vendored)
│  ├─ geom_collect.py        # გეომეტრიების შეგროვება → GeoPackage (tkinter UI)
│  ├─ dwg_convert.py         # DWG/DXF → SHP/GPKG/GDB (tkinter UI)
│  ├─ dwg_convert_core.py    # ↳ კონვერტაცია, გეომეტრიის გახლეჩა (GUI-free)
│  ├─ vendor/libredwg/       # GNU LibreDWG — dwg2dxf.exe + DLL-ები (GPL-3.0, vendored)
│  ├─ geom_collect_core.py   # ↳ წაკითხვა/კლასიფიკაცია/ჩაწერა (GUI-free)
│  ├─ zone_intersect.py      # დაცვის ზონის კვეთა (tkinter UI)
│  ├─ zone_intersect_core.py # ↳ საზღვრების კვეთის წერტილები (GUI-free)
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
├─ GIS_BOX.bat / .command / .sh / .desktop  # გამშვებები Windows / macOS / Linux
├─ install_linux.sh          # Linux: .venv + დამოკიდებულებები + მენიუს ჩანაწერი
│  ├─ platform_utils.py     # შრიფტები / ფაილის გახსნა / Desktop — Win·Mac·Linux
├─ requirements.txt          # ხელსაწყოების დამოკიდებულებები (სრული, ძველი)
├─ requirements-core.txt     # V2: ძირითადი დამოკიდებულებები
├─ requirements-optional.txt # V2: არასავალდებულო (PySide6, OCR, PostgreSQL, ...)
├─ GIS_BOX_V2.bat / .sh      # V2 გამშვებები
├─ docs/                     # INSTALL, DEPENDENCIES, TROUBLESHOOTING, TECHNICAL, ...
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

V2-ის ტესტები (`tests/test_v2_*.py`) საჭიროებს PySide6-ს და იგნორირდება მის გარეშე; ისინი Qt-ის `offscreen` პლატფორმაზე
მუშაობს და დროებით საქაღალდეებს იყენებს — რეალურ პარამეტრებს/ლოგებს არ ეხება.

---

## ლიცენზია / License

MIT — იხ. [LICENSE](LICENSE).
