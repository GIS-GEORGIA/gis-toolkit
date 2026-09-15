# -*- coding: utf-8 -*-
"""აპლიკაციის საქაღალდეები — ჩაშენებული რესურსები vs ჩასაწერი კონფიგი.

PyInstaller-ით აწყობისას (``sys.frozen``) ორი სხვადასხვა ადგილია:

* **რესურსები** (read-only: shp შაბლონები, ხატულა…) — ბანდლშია, ``_internal``
  (``sys._MEIPASS``). ``resource_dir()``.
* **მომხმარებლის კონფიგი** (ჩასაწერი: პარამეტრები, GDB გზა, ქუდები…) —
  ცალკე, სტაბილურ საქაღალდეში, რომ **ხელახალ აწყობას არ წაეშალოს**.
  ``data_dir()``.

⚠️ ``dist\\GIS_BOX\\`` მთლიანად იშლება ყოველ აწყობაზე — ამიტომ კონფიგი მის
შიგნით ვერ ვინახავთ. ნაგულისხმევად: ``%LOCALAPPDATA%\\GIS_BOX`` (build-ს არ
ეხება). არჩევანი (პრიორიტეტით):

  1. ``GIS_BOX_DATA_DIR`` გარემოს ცვლადი — თუ დაყენებულია.
  2. „პორტატული“: exe-ს გვერდით ``GIS_BOX_config`` საქაღალდე — თუ არსებობს
     (გამოსადეგი, როცა აპლიკაცია build-ის გარეთაა გადატანილი/deployed).
  3. ``%LOCALAPPDATA%\\GIS_BOX`` (Windows) / ``~/.config/GIS_BOX`` (სხვა).

დეველოპერულ (არა-frozen) რეჟიმში ორივე რეპოს ძირია — ძველი ქცევა უცვლელი.
"""

import os
import sys

# რეპოს ძირი (dev): tools/apppaths.py -> ../ = GIS_BOX ძირი
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_APP_NAME = "GIS_BOX"


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def resource_dir():
    """ჩაშენებული read-only რესურსების ბაზა (frozen: ``_internal``)."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _REPO_ROOT


def data_dir():
    """ჩასაწერი მომხმარებლის კონფიგის ბაზა (frozen: build-ს გარეთ, სტაბილური).

    საქაღალდე იქმნება, თუ არ არსებობს.
    """
    if not is_frozen():
        return _REPO_ROOT

    env = os.environ.get("GIS_BOX_DATA_DIR")
    if env:
        d = env
    else:
        exe_dir = os.path.dirname(sys.executable)
        portable = os.path.join(exe_dir, "GIS_BOX_config")
        if os.path.isdir(portable):
            d = portable
        else:
            base = (os.environ.get("LOCALAPPDATA")
                    or os.environ.get("APPDATA")
                    or os.path.join(os.path.expanduser("~"), ".config"))
            d = os.path.join(base, _APP_NAME)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def data_path(name):
    """ჩასაწერი კონფიგ-ფაილის სრული გზა data_dir-ში."""
    return os.path.join(data_dir(), name)


def resource_path(name):
    """ჩაშენებული რესურსის სრული გზა resource_dir-ში."""
    return os.path.join(resource_dir(), name)


def config_read_path(name):
    """მომხმარებლის კონფიგ-ფაილის წასაკითხი გზა.

    ჯერ ეძებს ჩასაწერ data_dir-ში; თუ იქ არაა, უბრუნდება ჩაშენებულ ნაგულისხმევს
    (resource_dir) — ასე user-editable-ფაილს (მაგ. map_services.txt) მუშა
    ნაგულისხმევი აქვს, სანამ მომხმარებელი თავისას შეინახავს.
    """
    d = data_path(name)
    if os.path.exists(d):
        return d
    r = resource_path(name)
    return r if os.path.exists(r) else d
