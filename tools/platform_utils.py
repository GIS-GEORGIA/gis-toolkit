# -*- coding: utf-8 -*-
"""პლატფორმაზე დამოკიდებული დამხმარეები — Windows / macOS / Linux.

ერთ ადგილას თავმოყრილია ის, რაც ოპერაციული სისტემის მიხედვით იცვლება, რომ
ხელსაწყოებში არ გაიმეოროს ``sys.platform`` ჯაჭვები:

* **შრიფტები** — Tk-ის ოჯახები (``UI_FONT`` / ``MONO_FONT`` / ``GEO_FONT``).
  Windows-ის „Segoe UI“, „Consolas“, „Sylfaen“ Linux-ზე არ არსებობს; იქ
  DejaVu (მას ქართული გლიფები აქვს) გამოიყენება, macOS-ზე — სისტემური.
* ``pil_font_candidates()`` — PIL-ის ``truetype`` სახელები ცხრილის სურათისთვის.
* ``open_path()`` — ფაილის/საქაღალდის გახსნა სისტემურ პროგრამაში.
* ``default_desktop()`` — სამუშაო მაგიდა (ან home, თუ Desktop არ არის).

მოდულს დამოკიდებულება არ აქვს (არც tkinter, არც GIS) — უსაფრთხოა ნებისმიერი
ადგილიდან იმპორტისთვის და ტესტირებადია.
"""

import os
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MAC

# ---- Tk შრიფტების ოჯახები --------------------------------------------------
# DejaVu Sans/Sans Mono — Linux-ის თითქმის ყველა დისტრიბუციაში არის და ქართულს
# (U+10D0–10FF) ფარავს. თუ არ არის, fontconfig/Tk თავად ჩაანაცვლებს.
if IS_WINDOWS:
    UI_FONT, MONO_FONT, GEO_FONT = "Segoe UI", "Consolas", "Sylfaen"
elif IS_MAC:
    UI_FONT, MONO_FONT, GEO_FONT = "Helvetica Neue", "Menlo", "Helvetica Neue"
else:
    UI_FONT, MONO_FONT, GEO_FONT = "DejaVu Sans", "DejaVu Sans Mono", "DejaVu Sans"


def pil_font_candidates():
    """PIL ``ImageFont.truetype``-ის სახელები — პირველი მუშა გამოიყენება.

    Windows: ჯერ Sylfaen (ქართული). Linux-ზე PIL სისტემურ საქაღალდეებში
    (``/usr/share/fonts``, ``~/.fonts``, XDG) თავად ეძებს სახელით.
    """
    if IS_WINDOWS:
        return ("sylfaen.ttf", "segoeui.ttf", "arial.ttf")
    if IS_MAC:
        return ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "Arial Unicode.ttf", "Arial.ttf", "DejaVuSans.ttf")
    return ("NotoSansGeorgian-Regular.ttf", "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf", "FreeSans.ttf")


# ---- ფაილის / საქაღალდის გახსნა ---------------------------------------------
def open_command(path):
    """გახსნის ბრძანება არა-Windows სისტემაზე (list) — ან None Windows-ზე.

    ცალკე ფუნქციად გატანილია, რომ ტესტში გადაამოწმო subprocess-ის გაშვების გარეშე.
    """
    if IS_WINDOWS:
        return None
    return ["open" if IS_MAC else "xdg-open", path]


def open_path(path):
    """ფაილი/საქაღალდე სისტემურ პროგრამაში (Explorer / Finder / xdg-open).

    შეცდომას (მაგ. ``xdg-open`` არაა დაყენებული) აგდებს — გამომძახებელი აჩვენებს.
    """
    if IS_WINDOWS:
        os.startfile(path)                          # noqa: S606
        return
    subprocess.Popen(open_command(path),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---- სამუშაო მაგიდა ---------------------------------------------------------
def _xdg_desktop():
    """XDG-ის ლოკალიზებული Desktop (მაგ. ~/Рабочий стол) user-dirs.dirs-იდან."""
    cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME")
                       or os.path.join(os.path.expanduser("~"), ".config"),
                       "user-dirs.dirs")
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("XDG_DESKTOP_DIR="):
                    val = line.split("=", 1)[1].strip().strip('"')
                    return os.path.normpath(
                        val.replace("$HOME", os.path.expanduser("~")))
    except OSError:
        pass
    return None


def default_desktop():
    """Desktop-ის გზა; თუ არ არსებობს — მომხმარებლის home საქაღალდე."""
    home = os.path.expanduser("~")
    candidates = [os.path.join(home, "Desktop")]
    if IS_LINUX:
        xdg = _xdg_desktop()
        if xdg:
            candidates.insert(0, xdg)
    for d in candidates:
        if os.path.isdir(d):
            return d
    return home
