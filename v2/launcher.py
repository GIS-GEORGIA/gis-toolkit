"""Open an existing (tkinter) tool in the classic GIS_BOX window - separate process, no shell."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def legacy_command(key):
    """argv that starts the classic app directly on tool ``key`` (works from source and from the exe)."""
    if getattr(sys, "frozen", False):
        classic = os.path.join(os.path.dirname(sys.executable), "GIS_BOX.exe" if os.name == "nt" else "GIS_BOX")
        return [classic, "--tool", key]
    return [sys.executable, os.path.join(ROOT, "gis_box.py"), "--tool", key]


def launch_legacy(key):
    """Start the classic window on tool ``key``. Returns the Popen object; raises OSError on failure."""
    kw = {"cwd": ROOT}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(legacy_command(key), **kw)
