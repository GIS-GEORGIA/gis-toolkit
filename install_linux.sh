#!/usr/bin/env sh
# GIS_BOX — Linux-ზე ერთი ბრძანებით დაყენება (გამოიყენება საწყისი კოდიდან გასაშვებად).
#
#   sh install_linux.sh            # .venv + დამოკიდებულებები + მენიუს ჩანაწერი
#   sh install_linux.sh --no-deps  # მხოლოდ მენიუს ჩანაწერი (პაკეტები უკვე გაქვს)
#
# რას აკეთებს: ამოწმებს python3-ს და tkinter-ს, ქმნის .venv-ს, აყენებს
# requirements.txt-ს და წერს ~/.local/share/applications/gis-box.desktop-ს
# სწორი აბსოლუტური გზებით (ხელით /PATH/TO/... შეცვლა არ სჭირდება).
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PY="$(command -v python3 || true)"
[ -n "$PY" ] || { echo "✗ python3 ვერ მოიძებნა. დააყენე: sudo apt install python3  (ან dnf/pacman ანალოგი)"; exit 1; }

if ! "$PY" -c "import tkinter" 2>/dev/null; then
    echo "✗ tkinter არ არის დაყენებული (GUI-ს სჭირდება)."
    echo "   Debian/Ubuntu: sudo apt install python3-tk"
    echo "   Fedora:        sudo dnf install python3-tkinter"
    echo "   Arch:          sudo pacman -S tk"
    exit 1
fi

if [ "${1:-}" != "--no-deps" ]; then
    if [ ! -x "$DIR/.venv/bin/python" ]; then
        echo "→ ვქმნი .venv-ს…"
        "$PY" -m venv "$DIR/.venv" || {
            echo "✗ venv ვერ შეიქმნა. Debian/Ubuntu: sudo apt install python3-venv"; exit 1; }
    fi
    echo "→ ვაყენებ დამოკიდებულებებს (geopandas, openpyxl, …) — შეიძლება რამდენიმე წუთი დასჭირდეს"
    "$DIR/.venv/bin/python" -m pip install --upgrade pip
    "$DIR/.venv/bin/python" -m pip install -r "$DIR/requirements.txt"
fi

chmod +x "$DIR/GIS_BOX.sh"

APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS"
cat > "$APPS/gis-box.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GIS_BOX
Comment=GIS tools
Exec="$DIR/GIS_BOX.sh"
Path=$DIR
Icon=$DIR/gis_box.png
Terminal=false
Categories=Utility;Science;Geoscience;
StartupWMClass=GIS_BOX
EOF
chmod +x "$APPS/gis-box.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true

echo "✓ მზადაა. გაუშვი: $DIR/GIS_BOX.sh  (ან მენიუდან: GIS_BOX)"
echo "ℹ ქართული ტექსტისთვის საჭიროა შრიფტი: sudo apt install fonts-dejavu-core  (ჩვეულებრივ უკვე არის)"
