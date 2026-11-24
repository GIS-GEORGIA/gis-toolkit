@echo off
rem GIS_BOX V2 გამშვები (PySide6 ინტერფეისი). კლასიკური ვერსია: GIS_BOX.bat
cd /d "%~dp0"
python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo PySide6 is not installed.  Run:  python -m pip install -r requirements-optional.txt
    pause
    exit /b 2
)
start "" pythonw "%~dp0gis_box_v2.py"
