# პრობლემების გადაჭრა / Troubleshooting

პირველი ნაბიჯი ყოველთვის: `python -m tools.env_check` (ან V2-ში **სერვისი → გარემოს შემოწმება**).
დიაგნოსტიკური ანგარიში გასაგზავნად: **სერვისი → დიაგნოსტიკური ანგარიშის ექსპორტი…** — zip, სადაც ლოგები უკვე გაწმენდილია პაროლებისა და ტოკენებისგან.

## გაშვება
| სიმპტომი | მიზეზი | გამოსავალი |
|---|---|---|
| `PySide6 is not installed` | არასავალდებულო პაკეტი აკლია | `python -m pip install PySide6` (ან `-r requirements-optional.txt`) |
| პროცესი ჩუმად ეცემა / `Windows fatal exception: access violation` | geopandas/shapely ჩაიტვირთა PySide6-მდე | PySide6 ყველაზე პირველად დააიმპორტე (იხ. [DEPENDENCIES.md](DEPENDENCIES.md)) |
| Linux: `Could not load the Qt platform plugin "xcb"` | აკლია Qt-ის სისტემური ბიბლიოთეკა | `sudo apt install libxcb-cursor0 libegl1 libxkbcommon-x11-0` |
| Linux: `No module named tkinter` | სისტემური პაკეტი | `sudo apt install python3-tk` |
| Linux: ფანჯრის გარეშე სერვერი | არ არის ეკრანი | `xvfb-run -a python gis_box_v2.py --selftest` |
| ქართული ტექსტის მაგივრად კვადრატები | შრიფტი აკლია, ან Qt `offscreen` პლატფორმა | Linux: `fonts-dejavu-core`. `offscreen` შრიფტებს საერთოდ არ ხატავს — ეს მხოლოდ ტესტებშია |
| `.bat` ამბობს PySide6 არ არის | სისტემურ Python-ს არ აქვს | დააყენე იმავე Python-ში, რომელსაც `python` ეძახის |

## CRS მენეჯერი
| შეტყობინება | მნიშვნელობა |
|---|---|
| `missing_crs` | მონაცემს CRS არ აქვს. გადაყვანა შეუძლებელია — ჯერ **მიანიჭე** (დადასტურებით), თუ ნამდვილად იცი სისტემა |
| `confirmation_required` | CRS-ის მინიჭება მხოლოდ მომხმარებლის თანხმობით ხდება |
| `exists` / `same_file` | გამოსავალი ფაილი უკვე არსებობს ან უდრის წყაროს — აირჩიე ახალი სახელი (არსებულს არასდროს გადაწერს) |
| `⚠ range: coordinates look like degrees ...` | კოორდინატები არ ემთხვევა გამოცხადებულ CRS-ს; შეამოწმე წყარო |
| კანდიდატები „NOT a definitive identification“ | დიაპაზონიდან ვარაუდია; UTM 37N და 38N დიაპაზონით არ განირჩევა |
| გრადუსებში ფართობი / „geographic CRS“ ზონის გადაკვეთაში | ფართობი მეტრულ CRS-ში უნდა გამოითვალოს (მაგ. EPSG:32637/32638) — ჯერ გადაიყვანე |

## განახლებები
| კოდი / შეტყობინება | გამოსავალი |
|---|---|
| `no connection to GitHub` | ქსელი/პროქსი; შემდეგ ხელახლა |
| `GitHub rate limit reached` | დაელოდე (ანონიმური API-ს ლიმიტი საათში) |
| `checksum (SHA256) does not match` | ფაილი წაიშალა; ხელახლა ჩამოტვირთე. განმეორებისას **არ დააინსტალირო** და შეატყობინე |
| `package is not verified` / „SHA256 არ არის გამოქვეყნებული“ | რელიზს ჰეში არ აქვს; დააინსტალირე მხოლოდ თუ წყაროს ენდობი |
| `the package contains unsafe paths` | არქივი უარყოფილია, არაფერი შეცვლილა |
| `files are in use - close GIS_BOX` | Windows-ზე გაშვებული exe-ს ფაილები ჩაკეტილია. ცვლილებები უკან დაბრუნდა. დახურე აპი და გახსენი ჩამოტვირთული ZIP ხელით |
| `this is a git checkout` | დეველოპერის ასლი არ გადაიწერება — `git pull` |
| ინსტალაცია ჩავარდა | ავტომატურად დაბრუნდა; ბექაპი `update_backups`-შია, ხელით: **განახლებები → უკან დაბრუნება** |

## ბაზებს შორის გადატანა (.mdb)
- „Data source name not found“ / დრაივერი ვერ მოიძებნა → დააყენე 64-ბიტიანი Access Database Engine, Python-იც 64-ბიტიანი უნდა იყოს; Linux-ზე ხელსაწყო მიუწვდომელია.
- „ბაზა დაკავებულია“ → დახურე ArcMap/Access, ორივე ბაზა; ჩაწერა Exclusive რეჟიმშია.
- ლოგები: `db_transfer_logs` საქაღალდე მიმღები ბაზის გვერდით — სრული აღწერა [db_transfer.md](db_transfer.md).

## GDB → PostGIS
- `ogr2ogr` ვერ მოიძებნა → `sudo apt install gdal-bin` ან QGIS/OSGeo4W და მიუთითე გზა.
- ავტორიზაციის შეცდომა → პაროლი გადაეცემა `PGPASSWORD` გარემოს ცვლადით; ბრძანების ხაზში/ლოგში არ ჩანს. შეამოწმე მომხმარებელი/ბაზა.

## ლოგები
```text
Windows: %LOCALAPPDATA%\GIS_BOX\logs\     Linux: ~/.local/state/GIS_BOX/logs/
user.log · detailed.log · debug.log · events.jsonl · history.sqlite
```
V2: **სერვისი → ლოგების საქაღალდის გახსნა**. აღწერა: [logging.md](logging.md). ადგილის შეცვლა შეიძლება `GIS_BOX_LOG_DIR` გარემოს ცვლადით.

## ტესტები
- `pytest` ნელა მუშაობს (~2 წთ) — GUI და .mdb ტესტები. ცალკეული ფაილი: `pytest tests/test_crs_manager.py`.
- V2 ტესტები ავტომატურად გამოიტოვება PySide6-ის გარეშე (`importorskip`); იზოლირებული დროებითი საქაღალდეები გამოიყენება — რეალური პარამეტრები/ლოგები არ იცვლება.
