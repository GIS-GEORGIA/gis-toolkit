"""Write GIS outputs so that a cancelled or failed run never leaves an incomplete file at the final path.

The data is first written to a hidden staging location in the *same* folder as the final output (same
filesystem, so the final step is a cheap rename on Windows and Linux alike). Only when the writer returns
normally is the result moved to the final name; on any exception - including a user cancel raised as an
exception - the staged files are deleted and the final path is left untouched.

    with staged_file("out/result.gpkg") as tmp:      # single-file formats (GPKG, XLSX, DXF ...)
        gdf.to_file(tmp, layer="a", driver="GPKG")
        check_cancel()                                # raising here discards tmp
        gdf2.to_file(tmp, layer="b", driver="GPKG", mode="a")

    with staged_shapefile("out/zone_1.shp") as tmp:   # .shp + .shx/.dbf/.prj/.cpg sidecars
        gdf.to_file(tmp, driver="ESRI Shapefile")

With ``staged_file`` always pass ``layer=`` for multi-layer formats (GPKG / GDB): without it GDAL names the
layer after the (hidden, temporary) file name.

Neither helper overwrites an existing final file: ``FileExistsError`` is raised before anything is moved
(callers already pick free names; this is the last line of defence).
No Qt, no thread handling - usable from the legacy app, the V2 shell and tests.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

# SQLite (GPKG) side files that can exist next to a database while it is open / after a crash
_SQLITE_SIDE = ("-journal", "-wal", "-shm")


def _remove_quietly(p):
    try:
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.lexists(p):
            os.remove(p)
    except OSError:
        pass


@contextmanager
def staged_file(final_path):
    """Yield a temporary path next to ``final_path``; rename it to ``final_path`` on success."""
    final = Path(final_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        raise FileExistsError(str(final))
    fd, tmp = tempfile.mkstemp(prefix=".{}.".format(final.stem), suffix=".part" + final.suffix,
                               dir=str(final.parent))
    os.close(fd)
    os.remove(tmp)                 # GDAL drivers want to create the file themselves
    try:
        yield tmp
        if not os.path.exists(tmp):
            return                 # the writer produced nothing (e.g. every layer was empty)
        if final.exists():
            raise FileExistsError(str(final))
        os.replace(tmp, str(final))
    finally:
        for p in [tmp] + [tmp + s for s in _SQLITE_SIDE]:
            _remove_quietly(p)


@contextmanager
def staged_shapefile(final_shp):
    """Yield ``<hidden dir>/<name>.shp``; move all ``<name>.*`` files next to ``final_shp`` on success.

    The ``.shp`` itself is moved last, so another program never sees a ``.shp`` without its ``.dbf``."""
    final = Path(final_shp)
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=".{}.part-".format(final.stem), dir=str(final.parent))
    tmp = os.path.join(stage, final.name)
    try:
        yield tmp
        stem = final.stem
        made = sorted((f for f in os.listdir(stage) if os.path.splitext(f)[0] == stem),
                      key=lambda f: f.lower().endswith(".shp"))           # .shp last
        targets = [(os.path.join(stage, f), str(final.parent / (stem + os.path.splitext(f)[1]))) for f in made]
        clash = [t for _s, t in targets if os.path.exists(t)]
        if clash:
            raise FileExistsError(clash[0])
        for src, dst in targets:
            os.replace(src, dst)
    finally:
        _remove_quietly(stage)


def discard_partial(paths):
    """Remove files / folders a cancelled step had already produced (best effort)."""
    for p in paths or ():
        _remove_quietly(p)


def leftover_staging(folder):
    """Hidden staging entries (``.<name>.part*``) in ``folder`` - for tests and diagnostics."""
    try:
        return [f for f in os.listdir(folder) if f.startswith(".") and ".part" in f]
    except OSError:
        return []
