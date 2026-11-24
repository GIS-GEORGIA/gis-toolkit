# დამოკიდებულებები / Dependencies

GIS_BOX გაიხსნება ნებისმიერი არასავალდებულო პაკეტის გარეშე; აკლებული პაკეტის შემთხვევაში მხოლოდ შესაბამისი ხელსაწყო აჩვენებს შეცდომას.
სრული შემოწმება: `python -m tools.env_check`.

## Python
**3.11 ან 3.12.** (CI ორივეზე ტესტავს.)

## ძირითადი — `requirements-core.txt`
| პაკეტი | რისთვის |
|---|---|
| geopandas ≥ 1.0, shapely ≥ 2.0, pyproj ≥ 3.6, pyogrio ≥ 0.9 | გეომეტრია, CRS, ფაილების წაკითხვა/ჩაწერა (GDAL/PROJ wheel-ებშია ჩაშენებული) |
| pandas ≥ 2.0, openpyxl ≥ 3.1 | ცხრილები, Excel ექსპორტი |

## არასავალდებულო — `requirements-optional.txt`
| პაკეტი | რას რთავს | შენიშვნა |
|---|---|---|
| **PySide6** ≥ 6.6 | V2 ინტერფეისი | Linux-ზე სჭირდება სისტემური ბიბლიოთეკები (იხ. ქვემოთ) |
| ezdxf ≥ 1.4 | DWG/DXF კონვერტაციის სარეზერვო წამკითხველი | |
| psycopg[binary] ≥ 3.1 | PostgreSQL/PostGIS | პაროლი არასდროს გადაეცემა ბრძანების ხაზით (`PGPASSWORD` გარემოს ცვლადი) |
| numpy, opencv-python, Pillow, PyMuPDF, rapidocr-onnxruntime | კოორდინატების ამომღები (OCR) | |
| pyodbc ≥ 5.0 (**მხოლოდ Windows**) | ბაზებს შორის გადატანა (.mdb) | + 64-ბიტიანი *Microsoft Access Database Engine* |
| cryptography | განახლებების ხელმოწერის შემოწმება (Ed25519) | ჯერ გამორთულია, სანამ საჯარო გასაღები არ გამოქვეყნდება |

`requirements.txt` ძველ სრულ სიას ინარჩუნებს (კლასიკური ვერსიისა და exe-ს აწყობისთვის). `requirements-dev.txt` — pytest.

## სისტემური კომპონენტები (pip-ით არ ისმება)
| კომპონენტი | სად სჭირდება | Debian/Ubuntu | Windows |
|---|---|---|---|
| tkinter | კლასიკური ინტერფეისი | `sudo apt install python3-tk` | Python-ის ინსტალატორში „tcl/tk“ |
| venv | ვირტუალური გარემო | `sudo apt install python3-venv` | ჩაშენებულია |
| ქართული შრიფტი | ტექსტი | `sudo apt install fonts-dejavu-core` | Segoe UI (ჩაშენებული) |
| `ogr2ogr`, `ogrinfo` | GDB → PostGIS | `sudo apt install gdal-bin` | QGIS / OSGeo4W |
| Qt-ის სისტემური ბიბლიოთეკები | V2 (PySide6) Linux-ზე | `sudo apt install libxcb-cursor0 libegl1 libxkbcommon-x11-0` | არ სჭირდება |
| Access ODBC დრაივერი | .mdb გადატანა | **მიუწვდომელია** | Microsoft Access Database Engine (64-bit) |

## მნიშვნელოვანი: იმპორტის რიგი (Windows)
**PySide6 უნდა ჩაიტვირთოს geopandas/shapely/pyogrio-მდე.** სხვა თანმიმდევრობა Windows-ზე იწვევს პროცესის ჩამოვარდნას (`access violation`, DLL-ების კონფლიქტი). `gis_box_v2.py` და `conftest.py` ამას ინარჩუნებს — ახალ შესასვლელ წერტილებში იგივე გაიმეორე.

## ვერსიები
აპის ვერსია ერთ ადგილას: `tools/version.py` (`2.0.0-dev`, SemVer). განახლებების მენეჯერი სწორედ მას ადარებს GitHub-ის უახლეს რელიზს.
