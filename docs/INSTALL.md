# ინსტალაცია და გაშვება / Install & run

> **სტატუსი.** V2 მუშავდება ცალკე ფილიალზე `feature/gis-box-v2` და `main`-ში არ არის შეერთებული.
> კლასიკური `gis_box.py` / `GIS_BOX.exe` უცვლელია და ისევ ცალკე მუშაობს.
> Status: V2 lives on branch `feature/gis-box-v2`, not merged into `main`. The classic app is unchanged.

## 1. საერთო მოთხოვნები
- **Python 3.11 ან 3.12** (ორივე CI-ში ტესტირდება).
- ინტერნეტი პირველი ინსტალაციისთვის (pip).
- დამოკიდებულებები **ორ ფაილადაა გაყოფილი**:
  - `requirements-core.txt` — ძირითადი GIS ხელსაწყოები (geopandas, shapely, pyproj, pyogrio, pandas, openpyxl);
  - `requirements-optional.txt` — თითო დამატებითი ფუნქცია (PySide6 — V2 ინტერფეისი, ezdxf, psycopg, OCR, pyodbc ...). მათ გარეშეც აპი იხსნება.
  სრული სია და სისტემური ბიბლიოთეკები: [DEPENDENCIES.md](DEPENDENCIES.md).

## 2. Windows

### 2.1 მზა ბილდი (Python არ სჭირდება)
1. [Releases](https://github.com/GIS-GEORGIA/gis-toolkit/releases) → `GIS_BOX-windows-x64.zip` (რელიზში გვერდით `.sha256` ფაილია ჰეშით).
2. გახსენი ZIP, გაუშვი `GIS_BOX.exe` (კლასიკური ინტერფეისი).
3. ჰეშის შემოწმება PowerShell-ში:
   ```powershell
   (Get-FileHash .\GIS_BOX-windows-x64.zip -Algorithm SHA256).Hash.ToLower()
   ```
   შედეგი უნდა ემთხვეოდეს `.sha256` ფაილში მითითებულს.

> V2 ინტერფეისი იმავე exe-შია ჩაშენებული: `GIS_BOX.exe --v2` (ან `GIS_BOX_V2.bat`). ვერიფიცირებულია ლოკალურად აწყობილ ბილდზე (`--v2 --selftest`); რელიზზე ჯერ არ გამოცდილა. გაითვალისწინე: PySide6-ის გამო ბილდი ~1.2 გბ-ია.

### 2.2 წყაროდან (V2-ის ჩათვლით)
```powershell
git clone https://github.com/GIS-GEORGIA/gis-toolkit.git
cd gis-toolkit
git checkout feature/gis-box-v2
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-core.txt -r requirements-optional.txt
.\.venv\Scripts\python -m tools.env_check      # დიაგნოსტიკა
.\.venv\Scripts\python gis_box_v2.py            # V2
.\.venv\Scripts\python gis_box.py               # კლასიკური
```
ან ორმაგი დაწკაპუნებით: `GIS_BOX_V2.bat` (V2) / `GIS_BOX.bat` (კლასიკური).

**.mdb გადატანის ხელსაწყოსთვის** (ბაზებს შორის მონაცემთა გადატანა) დამატებით საჭიროა 64-ბიტიანი *Microsoft Access Database Engine* (ODBC დრაივერი `*.mdb, *.accdb`) და `pyodbc`.

## 3. Linux (Ubuntu / Debian და სხვა)

```bash
sudo apt install python3 python3-venv python3-tk fonts-dejavu-core   # სისტემური პაკეტები
git clone https://github.com/GIS-GEORGIA/gis-toolkit.git && cd gis-toolkit
git checkout feature/gis-box-v2
sh install_linux.sh          # .venv + core + optional + დიაგნოსტიკა + მენიუს ჩანაწერი
./GIS_BOX_V2.sh              # V2 (PySide6)
./GIS_BOX.sh                 # კლასიკური (tkinter)
```
- `install_linux.sh` ამოწმებს `python3`-ს და `tkinter`-ს და **თითო აკლებულ სისტემურ პაკეტზე წერს ზუსტ ბრძანებას**.
  ბოლოს უშვებს `python -m tools.env_check`-ს.
- **PySide6 Linux-ზე** ხშირად საჭიროებს სისტემურ ბიბლიოთეკებს (ჩვეულებრივ `libxcb-cursor0`, `libegl1`, `libxkbcommon-x11-0`):
  ```bash
  sudo apt install libxcb-cursor0 libegl1 libxkbcommon-x11-0
  ```
  უფრო დეტალურად: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
- GDB → PostGIS-ს სჭირდება `ogr2ogr`: `sudo apt install gdal-bin`.
- **.mdb გადატანა Linux-ზე არ მუშაობს** (Access ODBC დრაივერი მხოლოდ Windows-ზეა).
- მზა პაკეტები Releases-იდან: `.tar.gz`, `.deb`, `.rpm`, `.AppImage` — დაყენება **ხელით**, აპი `sudo`-ს არასდროს იყენებს.

## 4. გარემოს დიაგნოსტიკა
```bash
python -m tools.env_check
```
აჩვენებს Python-ს, tkinter-ს, geopandas/shapely/pyproj/pyogrio-ს, PROJ/GDAL ვერსიებს, PySide6-ს, `ogr2ogr`-ს, `pyodbc`-ს. აკლებულზე — OS-ზე მორგებულ რჩევას. გასვლის კოდი 1 = აკლია **აუცილებელი** კომპონენტი.
V2-ში: მენიუ **სერვისი → გარემოს შემოწმება**. თვითტესტი ფანჯრის გარეშე: `python gis_box_v2.py --selftest`.

## 5. პარამეტრები, ლოგები, განახლებები — სად ინახება
| რა | Windows | Linux |
|---|---|---|
| V2 პარამეტრები, ჩამოტვირთული განახლებები, ბექაპები | `%LOCALAPPDATA%\GIS_BOX\` | `~/.config/GIS_BOX/` |
| ლოგები და ოპერაციების ისტორია | `%LOCALAPPDATA%\GIS_BOX\logs\` | `~/.local/state/GIS_BOX/logs/` |
| კლასიკური ვერსიის პარამეტრები | იხ. [TECHNICAL.md §5](TECHNICAL.md) | იგივე |

გადასაწერი გარემოს ცვლადებით: `GIS_BOX_V2_DIR`, `GIS_BOX_LOG_DIR`, `GIS_BOX_DATA_DIR`. V2 არაფერს წერს კოდის საქაღალდეში და პაროლები არასდროს ხვდება ლოგში.

განახლებები: V2-ში **განახლებები** → შემოწმება / ჩამოტვირთვა / ინსტალაცია / უკან დაბრუნება (ყოველი ნაბიჯი დასტურით). დეტალები: [update_manager.md](update_manager.md).

## 6. ცნობილი შეზღუდვები
- PyInstaller-ის ბილდი აწყობს ერთ exe-ს: კლასიკური ინტერფეისი ნაგულისხმევად, V2 — `--v2` არგუმენტით.
- 14 ხელსაწყოდან V2-ში ნატიურია **CRS მენეჯერი**, **განახლებები**, **ბუფერების აგება**, **რუკის სერვისები**, **სახელების გადარქმევა**, **Shp → კოორდინატები**, **დაცვის ზონის კვეთა**, **კვეთა და შაბლონი**, **გეომეტრიების შეგროვება** და **DWG/DXF კონვერტაცია**; დანარჩენი V2-დან კლასიკურ ფანჯარაში იხსნება.
- exe-ს თვითგანახლება (გადარქმევის ხერხით) რეალურ რელიზზე ბოლომდე ჯერ არ გამოცდილა — იხ. [update_manager.md](update_manager.md).
- ზოგი ფუნქცია მხოლოდ Windows-ზეა (Excel COM, ცხრილის HTML ბუფერში, Task Scheduler, .mdb გადატანა).
