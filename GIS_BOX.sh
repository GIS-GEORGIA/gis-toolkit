#!/usr/bin/env sh
# GIS_BOX გამშვები — Linux / macOS. გზებს თავად ადგენს (სადაც არ უნდა იყოს საქაღალდე).
# თუ install_linux.sh-მა .venv შექმნა — მას იყენებს, თორემ სისტემურ python3-ს.
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
if [ -x "$DIR/.venv/bin/python" ]; then
    PY="$DIR/.venv/bin/python"
else
    PY="$(command -v python3 || command -v python)"
fi
[ -n "$PY" ] || { echo "GIS_BOX: python3 not found" >&2; exit 1; }
exec "$PY" "$DIR/gis_box.py" "$@"
