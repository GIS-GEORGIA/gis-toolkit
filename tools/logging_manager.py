"""Centralized logging for GIS_BOX V2 (GUI-independent, stdlib only).

Three log levels
    USER    short, understandable messages about completed operations and errors
    DETAIL  processing information: input/output files, CRS, parameters, timestamps
    DEBUG   technical diagnostics (tracebacks, internals)

Outputs (all in :func:`log_dir`)
    user.log       TXT, USER only
    detailed.log   TXT, USER + DETAIL
    debug.log      TXT, everything
    events.jsonl   one JSON object per record (all levels)
    history.sqlite one row per OPERATION (tool, inputs, outputs, duration, status, error)

Secrets (passwords, tokens, API keys, ``user:pass@`` in URLs, anything registered with
:func:`register_secret`) are removed BEFORE anything is written. Tracebacks go to debug only.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
import threading
import time
import traceback
import zipfile

USER, DETAIL, DEBUG = 30, 20, 10
LEVEL_NAMES = {USER: "USER", DETAIL: "DETAIL", DEBUG: "DEBUG"}
MAX_BYTES = 2_000_000          # rotate a TXT/JSONL file at ~2 MB
KEEP_ROTATED = 3

# ---------------------------------------------------------------------------- redaction
_SECRET_KEYS = r"(?:pass(?:word|wd)?|pwd|pgpassword|token|api[_-]?key|apikey|secret|authorization|auth|credential[s]?)"
_PATTERNS = [
    # key=value / key: value / "key": "value"
    (re.compile(r"(?i)(\b" + _SECRET_KEYS + r"\b[\"']?\s*[:=]\s*[\"']?)(?:(?:bearer|basic)\s+)?([^\s\"'&;,]+)"), r"\1***"),
    # Authorization: Bearer xxx
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{6,}"), r"\1 ***"),
    # scheme://user:pass@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+):[^@\s/]+@"), r"\1:***@"),
    # GitHub tokens
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "***"),
]
_secrets: set[str] = set()
_secret_lock = threading.Lock()


def register_secret(value):
    """Make sure an exact secret value never appears in any log (e.g. a password typed in the GUI)."""
    if value and len(str(value)) >= 3:
        with _secret_lock:
            _secrets.add(str(value))


def clear_secrets():
    with _secret_lock:
        _secrets.clear()


def redact(text):
    """Remove secrets from a string."""
    if text is None:
        return text
    s = str(text)
    with _secret_lock:
        known = sorted(_secrets, key=len, reverse=True)
    for v in known:
        s = s.replace(v, "***")
    for rx, rep in _PATTERNS:
        s = rx.sub(rep, s)
    return s


def redact_obj(obj):
    """Recursively redact strings; values under secret-looking dict keys are replaced entirely."""
    key_rx = re.compile(r"(?i)^" + _SECRET_KEYS + r"$")
    if isinstance(obj, dict):
        return {k: ("***" if isinstance(k, str) and key_rx.match(k) else redact_obj(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return redact(obj)


# ---------------------------------------------------------------------------- locations
def log_dir():
    """Log folder: ``GIS_BOX_LOG_DIR`` or the per-user state folder (never inside the program folder).

    Windows ``%LOCALAPPDATA%\\GIS_BOX\\logs`` | macOS ``~/Library/Logs/GIS_BOX`` |
    Linux ``$XDG_STATE_HOME/GIS_BOX/logs`` (default ``~/.local/state``)."""
    env = os.environ.get("GIS_BOX_LOG_DIR")
    if env:
        d = env
    else:
        home = os.path.expanduser("~")
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
            d = os.path.join(base, "GIS_BOX", "logs")
        elif sys.platform == "darwin":
            d = os.path.join(home, "Library", "Logs", "GIS_BOX")
        else:
            base = os.environ.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state")
            d = os.path.join(base, "GIS_BOX", "logs")
    os.makedirs(d, exist_ok=True)
    return d


def open_log_dir(path=None):
    """Open the log folder in the system file manager (no admin rights, no shell strings)."""
    import subprocess
    d = path or log_dir()
    if sys.platform == "win32":
        os.startfile(d)                       # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", d])
    else:
        subprocess.Popen(["xdg-open", d])


# ---------------------------------------------------------------------------- manager
class LogManager:
    def __init__(self, directory=None, console=False):
        self.dir = directory or log_dir()
        os.makedirs(self.dir, exist_ok=True)
        self.console = console
        self._lock = threading.RLock()
        self.db_path = os.path.join(self.dir, "history.sqlite")
        self._init_db()

    # ---- files
    def _path(self, name):
        return os.path.join(self.dir, name)

    def _rotate(self, path):
        try:
            if os.path.getsize(path) < MAX_BYTES:
                return
        except OSError:
            return
        for i in range(KEEP_ROTATED - 1, 0, -1):
            a, b = "{}.{}".format(path, i), "{}.{}".format(path, i + 1)
            if os.path.exists(a):
                os.replace(a, b)
        os.replace(path, path + ".1")

    def _append(self, name, line):
        p = self._path(name)
        self._rotate(p)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---- logging
    def log(self, level, message, tool=None, **fields):
        """Write one record. ``fields`` are extra structured data (redacted) kept in the JSONL only."""
        msg = redact(message)
        now = datetime.datetime.now()
        ts = now.isoformat(sep=" ", timespec="seconds")
        tag = LEVEL_NAMES.get(level, str(level))
        line = "{} [{}]{} {}".format(ts, tag, " [{}]".format(tool) if tool else "", msg)
        rec = {"time": now.isoformat(timespec="milliseconds"), "level": tag, "tool": tool,
               "message": msg}
        if fields:
            rec["data"] = redact_obj(fields)
        with self._lock:
            if level >= USER:
                self._append("user.log", line)
            if level >= DETAIL:
                self._append("detailed.log", line)
            self._append("debug.log", line)
            self._append("events.jsonl", json.dumps(rec, ensure_ascii=False, default=str))
        if self.console:
            print(line)
        return line

    def user(self, message, tool=None, **f):
        return self.log(USER, message, tool, **f)

    def detail(self, message, tool=None, **f):
        return self.log(DETAIL, message, tool, **f)

    def debug(self, message, tool=None, **f):
        return self.log(DEBUG, message, tool, **f)

    # ---- history
    def _conn(self):
        return sqlite3.connect(self.db_path, timeout=10)

    def _init_db(self):
        with self._lock, self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS operations(
                id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, tool TEXT,
                status TEXT, duration_s REAL, inputs TEXT, outputs TEXT, params TEXT, error TEXT)""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_ops_tool ON operations(tool, started)")

    def record(self, tool, status, inputs=None, outputs=None, params=None, duration=0.0, error=None,
               started=None, finished=None):
        """Write a finished operation to the history directly (for tools that already time themselves)."""
        op = Operation(self, tool, inputs, params)
        op.outputs = list(outputs or [])
        op.status, op.error, op.duration = status, error, float(duration or 0)
        now = datetime.datetime.now()
        op.finished = finished or now.isoformat(timespec="seconds")
        op.started = started or (now - datetime.timedelta(seconds=op.duration)).isoformat(timespec="seconds")
        self.user("{}: {} ({:.1f}s)".format(status.upper(), tool, op.duration), tool)
        return self._record(op)

    def operation(self, tool, inputs=None, params=None):
        """Context manager recording one tool run (see :class:`Operation`)."""
        return Operation(self, tool, inputs, params)

    def _record(self, op):
        with self._lock, self._conn() as c:
            cur = c.execute(
                "INSERT INTO operations(started,finished,tool,status,duration_s,inputs,outputs,params,error)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (op.started, op.finished, op.tool, op.status, round(op.duration, 3),
                 json.dumps(redact_obj(op.inputs), ensure_ascii=False),
                 json.dumps(redact_obj(op.outputs), ensure_ascii=False),
                 json.dumps(redact_obj(op.params), ensure_ascii=False, default=str),
                 redact(op.error) if op.error else None))
            return cur.lastrowid

    def history(self, limit=100, tool=None, status=None):
        """Latest operations, newest first, as dicts."""
        q, a = "SELECT * FROM operations", []
        where = []
        if tool:
            where.append("tool=?")
            a.append(tool)
        if status:
            where.append("status=?")
            a.append(status)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY id DESC LIMIT ?"
        a.append(int(limit))
        with self._lock, self._conn() as c:
            c.row_factory = sqlite3.Row
            rows = [dict(r) for r in c.execute(q, a)]
        for r in rows:
            for k in ("inputs", "outputs", "params"):
                try:
                    r[k] = json.loads(r[k]) if r[k] else None
                except ValueError:
                    pass
        return rows

    # ---- diagnostics
    def export_diagnostics(self, out_zip, history_limit=500):
        """Zip with logs (already redacted), operation history (JSON) and the environment report.
        Never contains settings files, databases of user data, or credentials."""
        if os.path.exists(out_zip):
            raise FileExistsError(out_zip)
        from tools import env_check, version
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for name in sorted(os.listdir(self.dir)):
                if name.endswith((".log", ".jsonl")) or ".log." in name or ".jsonl." in name:
                    with open(self._path(name), encoding="utf-8", errors="replace") as f:
                        z.writestr("logs/" + name, redact(f.read()))     # second redaction pass
            z.writestr("history.json", json.dumps(redact_obj(self.history(history_limit)),
                                                  ensure_ascii=False, indent=1, default=str))
            z.writestr("environment.txt", redact(
                "GIS_BOX {}\nPython {}\n{}\n".format(version.__version__, sys.version.replace("\n", " "),
                                                    env_check.report())))
        return out_zip


class Operation:
    """``with lm.operation("zone_intersect", inputs=[...]) as op: ... op.output(path)``

    On exit it records date/time, tool, inputs, outputs, duration, status (``ok`` / ``error`` /
    ``cancelled``) and the error text, and writes USER/DETAIL/DEBUG lines. Exceptions propagate."""

    def __init__(self, manager, tool, inputs=None, params=None):
        self.m = manager
        self.tool = tool
        self.inputs = list(inputs or [])
        self.outputs = []
        self.params = dict(params or {})
        self.status = "ok"
        self.error = None
        self.id = None
        self.started = self.finished = None
        self.duration = 0.0
        self._t0 = None
        self.cancelled = False

    def input(self, path):
        self.inputs.append(str(path))

    def output(self, path):
        self.outputs.append(str(path))

    def cancel(self):
        self.cancelled = True

    def detail(self, msg, **f):
        self.m.detail(msg, self.tool, **f)

    def user(self, msg, **f):
        self.m.user(msg, self.tool, **f)

    def debug(self, msg, **f):
        self.m.debug(msg, self.tool, **f)

    def __enter__(self):
        self._t0 = time.monotonic()
        self.started = datetime.datetime.now().isoformat(timespec="seconds")
        self.m.detail("START inputs={} params={}".format(self.inputs, redact_obj(self.params)), self.tool)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.duration = time.monotonic() - self._t0
        self.finished = datetime.datetime.now().isoformat(timespec="seconds")
        if exc_type is not None:
            self.status = "error"
            self.error = "{}: {}".format(exc_type.__name__, exc)
            self.m.debug("".join(traceback.format_exception(exc_type, exc, tb)), self.tool)
            self.m.user("ERROR: {}".format(self.error), self.tool)
        elif self.cancelled:
            self.status = "cancelled"
            self.m.user("CANCELLED after {:.1f}s".format(self.duration), self.tool)
        else:
            self.m.user("OK in {:.1f}s{}".format(
                self.duration, " -> {}".format(", ".join(self.outputs)) if self.outputs else ""), self.tool)
        self.m.detail("END status={} duration={:.3f}s outputs={}".format(
            self.status, self.duration, self.outputs), self.tool)
        try:
            self.id = self.m._record(self)
        except Exception as e:                    # noqa: BLE001 - history must never break the tool
            self.m.debug("history write failed: {}".format(e), self.tool)
        return False


# ---------------------------------------------------------------------------- singleton
_default = None
_default_lock = threading.Lock()


def get_manager():
    global _default
    with _default_lock:
        if _default is None:
            _default = LogManager()
        return _default


def set_manager(manager):
    """Replace the process-wide manager (tests, custom folder)."""
    global _default
    with _default_lock:
        _default = manager
