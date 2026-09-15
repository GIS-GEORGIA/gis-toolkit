@echo off
rem GIS_BOX გამშვები. თუ აწყობილი .exe არსებობს — მას უშვებს (Task Manager-ში
rem „GIS_BOX.exe“ ჩანს, არა „python“); თუ არა — pythonw-ით. თითო გაშვება ცალკე
rem პროცესია და უნიკალური AppUserModelID-ის წყალობით ერთმანეთს არ ებმის.
cd /d "%~dp0"
if exist "%~dp0dist\GIS_BOX\GIS_BOX.exe" (
    start "" "%~dp0dist\GIS_BOX\GIS_BOX.exe"
) else (
    start "" pythonw "%~dp0gis_box.py"
)
