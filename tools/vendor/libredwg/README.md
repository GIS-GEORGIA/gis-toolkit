# GNU LibreDWG (vendored binary)

**რატომ არის აქ:** GIS_BOX-ის „DWG/DXF → SHP/GPKG/GDB" ხელსაწყოს DWG-ის
წასაკითხად სჭირდება რაღაც, რაც თანამედროვე (R2007+) AutoCAD/Civil 3D
DWG-ს ხსნის. GDAL-ის ჩაშენებულ `pyogrio`-ს DWG დრაივერი საერთოდ არ აქვს;
QGIS/OSGeo4W-ის ღია კოდის CAD დრაივერი (`libopencad`) კი მხოლოდ ძველ
DWG R2000-ს კითხულობს საიმედოდ. **GNU LibreDWG** (99%-იანი დაფარვით,
r13–r2018) რეალურად კითხულობს თანამედროვე DWG-ს — გადამოწმებულია 4
რეალურ, სხვადასხვა AutoCAD-ვერსიის DWG-ზე (libopencad ვერ ხსნიდა
არცერთს, LibreDWG — ყველა, 1-დან 15000-მდე ობიექტამდე).

**რა არის ეს ფაილები:** `dwg2dxf.exe` (LibreDWG-ის CLI, DWG → DXF) + მისი
4 DLL დამოკიდებულება — **დამოუკიდებელი, ხელუხლებელი** ბინარები GNU
LibreDWG-ის ოფიციალური Windows გამოშვებიდან:

  https://github.com/LibreDWG/libredwg/releases/tag/0.14.8597
  (`libredwg-0.14.8597-win64.zip`, SHA-256 — `dist.sha256` იმ გამოშვებაში)

**ლიცენზია:** GPL-3.0 (`COPYING`, ამავე საქაღალდეში). GIS_BOX (MIT) ამ
ბინარს **subprocess-ით უშვებს**, არ უკავშირდება (linking) — ე.წ. "mere
aggregation" GPL-ის მნიშვნელობით, ისევე, როგორც GIS_BOX-ის სხვა
ხელსაწყოები QGIS-ის ცალკე ინსტალაციის `ogr2ogr`-ს (ასევე GPL) უშვებენ
subprocess-ით. წყარო საჯაროდ ხელმისაწვდომია ზემოთ მითითებულ ბმულზე.

**განახლება:** ახალი LibreDWG-ის გამოშვების ჩასანაცვლებლად ჩამოტვირთე
`*-win64.zip`, ამოშალე `dwg2dxf.exe` + `lib*.dll` (და, თუ შეიცვალა,
`COPYING`) ამ საქაღალდეში, განაახლე ეს README ახალი ვერსია/ბმულით.
