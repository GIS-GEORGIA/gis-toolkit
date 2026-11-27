#!/usr/bin/env sh
# GIS_BOX V2 გამშვები — Linux / macOS (PySide6 ინტერფეისი). კლასიკური ვერსია: GIS_BOX.sh
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
if [ -x "$DIR/.venv/bin/python" ]; then
    PY="$DIR/.venv/bin/python"
else
    PY="$(command -v python3 || command -v python)"
fi
[ -n "$PY" ] || { echo "GIS_BOX V2: python3 not found" >&2; exit 1; }
if ! "$PY" -c "import PySide6" 2>/dev/null; then
    echo "GIS_BOX V2: PySide6 is not installed.  Run: sh install_linux.sh   (or: $PY -m pip install PySide6)" >&2
    exit 2
fi
exec "$PY" "$DIR/gis_box_v2.py" "$@"
