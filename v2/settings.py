"""V2 user settings (JSON, no Qt). Stored in the per-user config folder, never in the program folder."""
import json
import os
import sys
import tempfile

MAX_RECENT_TOOLS = 8
MAX_RECENT_FILES = 15

DEFAULTS = {
    "theme": "light",            # light | dark
    "lang": "ka",                # ka | en
    "favorites": [],
    "recent_tools": [],
    "recent_files": [],
    "window": {"w": 1180, "h": 760},
    "updates": {"auto_check": False, "notify": True, "prerelease": False, "last_check": ""},
}


def settings_dir():
    env = os.environ.get("GIS_BOX_V2_DIR")
    if env:
        d = env
    else:
        home = os.path.expanduser("~")
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        elif sys.platform == "darwin":
            base = os.path.join(home, "Library", "Application Support")
        else:
            base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
        d = os.path.join(base, "GIS_BOX")
    os.makedirs(d, exist_ok=True)
    return d


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(settings_dir(), "v2_settings.json")
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
                    if isinstance(v, dict):
                        self.data[k].update(v)
                    else:
                        self.data[k] = v
        if self.data["theme"] not in ("light", "dark"):
            self.data["theme"] = "light"
        if self.data["lang"] not in ("ka", "en"):
            self.data["lang"] = "ka"

    def save(self):
        """Atomic write (temp file + replace); failures never break the app."""
        try:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    # ---- favorites / recents
    def is_favorite(self, tool_id):
        return tool_id in self.data["favorites"]

    def toggle_favorite(self, tool_id):
        fav = self.data["favorites"]
        if tool_id in fav:
            fav.remove(tool_id)
        else:
            fav.append(tool_id)
        return tool_id in fav

    @staticmethod
    def _push(lst, item, limit):
        if item in lst:
            lst.remove(item)
        lst.insert(0, item)
        del lst[limit:]

    def add_recent_tool(self, tool_id):
        self._push(self.data["recent_tools"], tool_id, MAX_RECENT_TOOLS)

    def add_recent_file(self, path):
        self._push(self.data["recent_files"], os.path.abspath(path), MAX_RECENT_FILES)
