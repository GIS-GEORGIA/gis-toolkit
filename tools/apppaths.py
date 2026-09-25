# -*- coding: utf-8 -*-
"""აპლიკაციის საქაღალდეები — ჩაშენებული რესურსები vs ჩასაწერი კონფიგი.

ორი განსხვავებული ადგილია:

* **რესურსები** (read-only: shp შაბლონები, ხატულა…) — ბანდლშია, ``_internal``
  (``sys._MEIPASS``), ან რეპოს ძირი. ``resource_dir()``.
* **მომხმარებლის კონფიგი** (ჩასაწერი: პარამეტრები, GDB გზა, ქუდები…) —
  ცალკე, სტაბილურ საქაღალდეში. ``data_dir()``.

⚠️ PyInstaller-ის ``dist\\GIS_BOX\\`` მთლიანად იშლება ყოველ აწყობაზე, ხოლო
დაინსტალირებული Linux პაკეტი (``/opt/gis-box``) read-only-ა — ამიტომ კონფიგი
პროგრამის საქაღალდეში არ უნდა ინახებოდეს. არჩევანი (პრიორიტეტით):

  1. ``GIS_BOX_DATA_DIR`` გარემოს ცვლადი — თუ დაყენებულია (ყველა რეჟიმში).
  2. „პორტატული“ (frozen): exe-ს გვერდით ``GIS_BOX_config`` საქაღალდე — თუ არსებობს.
  3. dev checkout (არა-frozen) და რეპოს ძირი **ჩასაწერია** → რეპოს ძირი
     (ძველი ქცევა, უცვლელი).
  4. სხვა შემთხვევაში — მომხმარებლის კონფიგ-საქაღალდე OS-ის კონვენციით:
       Windows ``%LOCALAPPDATA%\\GIS_BOX`` · macOS ``~/Library/Application Support/GIS_BOX``
       · Linux ``$XDG_CONFIG_HOME/GIS_BOX`` (ნაგულისხმევად ``~/.config/GIS_BOX``).
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


def user_config_base():
    """მომხმარებლის კონფიგების ზოგადი საქაღალდე ამ OS-ისთვის (აპის სახელის გარეშე)."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        return (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                or os.path.join(home, "AppData", "Local"))
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support")
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")


def _writable(path):
    """საქაღალდე არსებობს და ჩასაწერია."""
    return os.path.isdir(path) and os.access(path, os.W_OK)


def data_dir():
    """ჩასაწერი მომხმარებლის კონფიგის ბაზა (იქმნება, თუ არ არსებობს)."""
    env = os.environ.get("GIS_BOX_DATA_DIR")
    if env:
        d = env
    elif is_frozen():
        portable = os.path.join(os.path.dirname(sys.executable), "GIS_BOX_config")
        d = portable if os.path.isdir(portable) \
            else os.path.join(user_config_base(), _APP_NAME)
    elif _writable(_REPO_ROOT):
        return _REPO_ROOT                     # dev checkout — ძველი ქცევა
    else:                                     # read-only install (მაგ. /opt, /usr/share)
        d = os.path.join(user_config_base(), _APP_NAME)
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
