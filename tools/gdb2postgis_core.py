"""
Core logic: locate GDAL tools, list layers in a GDB/MDB source,
and import selected layers into PostgreSQL/PostGIS using ogr2ogr.

No GUI dependencies here — everything is callable/testable on its own.

Vendored into GIS_BOX from the standalone MIT-licensed ``gdb2postgis`` project
(© 2026 GGTC). Only the GUI-free engine is reused; the tkinter UI lives in
``tools/gdb2postgis.py``. Passwords are masked in logs (see ``_mask``).
"""
from __future__ import annotations

import os
import re
import glob
import json
import shutil
import subprocess
from dataclasses import dataclass, field, asdict, replace
from datetime import datetime
from typing import Callable, Iterable

# ---------------------------------------------------------------------------
# Locating ogr2ogr / ogrinfo
# ---------------------------------------------------------------------------

_COMMON_GLOBS = [
    r"C:\Program Files\QGIS *\bin",
    r"C:\Program Files\QGIS*\bin",
    r"C:\OSGeo4W*\bin",
    r"C:\OSGeo4W*\apps\gdal\bin",
    r"C:\Program Files\GDAL",
]


def _candidates(exe: str) -> Iterable[str]:
    # 1) on PATH
    onpath = shutil.which(exe)
    if onpath:
        yield onpath
    # 2) common install locations (newest QGIS last -> we sort desc later)
    hits: list[str] = []
    for pattern in _COMMON_GLOBS:
        for d in glob.glob(pattern):
            p = os.path.join(d, exe + (".exe" if os.name == "nt" else ""))
            if os.path.isfile(p):
                hits.append(p)
    # prefer newest QGIS version (reverse-sorted path string is a decent proxy)
    for p in sorted(set(hits), reverse=True):
        yield p


def find_tool(exe: str, override: str | None = None) -> str | None:
    """Return a working path to `exe` (ogr2ogr/ogrinfo), or None."""
    if override and os.path.isfile(override):
        return override
    for cand in _candidates(exe):
        return cand
    return None


def gdal_version(ogr2ogr_path: str) -> str:
    try:
        out = subprocess.run(
            [ogr2ogr_path, "--version"],
            capture_output=True, text=True, timeout=20,
            creationflags=_no_window(), env=_child_env(ogr2ogr_path),
        )
        return (out.stdout or out.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return f"?? ({e})"


def _no_window() -> int:
    # Hide the console window when spawning on Windows.
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


_PG_PASSWORD = ""


def _set_pg_password(password: str) -> None:
    """Remember the PostgreSQL password for child processes (env var only, never argv/log)."""
    global _PG_PASSWORD
    _PG_PASSWORD = password or ""


def _child_env(tool_path: str) -> dict:
    """
    Build an isolated environment for the GDAL binary.

    A common Windows pitfall: PostgreSQL/PostGIS (and other GIS installs) leave
    PROJ_LIB / GDAL_DATA pointing at *their* data folders. When we run QGIS's
    standalone ogr2ogr, those stale vars break PROJ ("proj.db ... from another
    PROJ installation"). We drop the inherited ones and point at the data
    folders that ship next to this specific binary.
    """
    env = dict(os.environ)
    if _PG_PASSWORD:
        env["PGPASSWORD"] = _PG_PASSWORD
    for var in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA", "GDAL_DRIVER_PATH"):
        env.pop(var, None)
    if not tool_path:
        return env
    # tool is <root>\bin\ogr2ogr.exe  ->  root = parent of bin
    root = os.path.dirname(os.path.dirname(os.path.abspath(tool_path)))
    for proj in (os.path.join(root, "share", "proj"),
                 os.path.join(root, "apps", "proj", "share", "proj")):
        if os.path.isfile(os.path.join(proj, "proj.db")):
            env["PROJ_LIB"] = proj
            env["PROJ_DATA"] = proj
            break
    for gdal in (os.path.join(root, "apps", "gdal", "share", "gdal"),
                 os.path.join(root, "share", "gdal")):
        if os.path.isdir(gdal):
            env["GDAL_DATA"] = gdal
            break
    return env


# ---------------------------------------------------------------------------
# Source inspection
# ---------------------------------------------------------------------------

@dataclass
class LayerInfo:
    name: str
    geom_type: str = ""


def list_sources(directory: str) -> list[str]:
    """Find .gdb (directories) and .mdb (files) inside `directory`."""
    out: list[str] = []
    if not directory or not os.path.isdir(directory):
        return out
    for entry in sorted(os.listdir(directory)):
        full = os.path.join(directory, entry)
        low = entry.lower()
        if low.endswith(".gdb") and os.path.isdir(full):
            out.append(full)
        elif low.endswith(".mdb") and os.path.isfile(full):
            out.append(full)
    return out


# Matches both "1: name (Point)" and GDAL 3.x "Layer: name (Point)" forms.
_LAYER_RE = re.compile(r"^\s*(?:\d+|Layer):\s+(.+?)\s+\(([^)]*)\)\s*$")
_LAYER_RE_NOGEOM = re.compile(r"^\s*(?:\d+|Layer):\s+(\S+)\s*$")


def list_layers(ogrinfo_path: str, source: str) -> list[LayerInfo]:
    """Return the layers inside a .gdb/.mdb source."""
    proc = subprocess.run(
        [ogrinfo_path, "-ro", "-q", source],
        capture_output=True, text=True, timeout=120,
        creationflags=_no_window(), env=_child_env(ogrinfo_path),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ogrinfo failed")
    layers: list[LayerInfo] = []
    for line in proc.stdout.splitlines():
        m = _LAYER_RE.match(line)
        if m:
            layers.append(LayerInfo(name=m.group(1).strip(), geom_type=m.group(2).strip()))
            continue
        m = _LAYER_RE_NOGEOM.match(line)
        if m:
            layers.append(LayerInfo(name=m.group(1).strip()))
    return layers


# ---------------------------------------------------------------------------
# Field inspection + auto-detection (for incremental sync)
# ---------------------------------------------------------------------------

# ogrinfo -so attribute lines: "name: String (0.0)" or "last_edited_date: DateTime"
# Anchoring on the known OGR type names cleanly excludes headers ("INFO: Open ...").
_OGR_TYPES = ("String", "Integer64", "Integer", "Real", "DateTime", "Date", "Time",
              "Binary", "StringList", "Integer64List", "IntegerList", "RealList",
              "WideString")
_FIELD_RE = re.compile(r"^\s*([A-Za-z_][\w]*)\s*:\s*(" + "|".join(_OGR_TYPES) + r")\b")
# "FID Column = objectid" / "Geometry Column = SHAPE"
_FIDCOL_RE = re.compile(r"^\s*FID Column\s*=\s*(\S+)", re.IGNORECASE)

# order = preference; first match wins
_KEY_CANDIDATES = ["globalid", "global_id", "objectid", "object_id", "oid", "fid", "id", "gid"]
_TRACK_CANDIDATES = ["last_edited_date", "last_edit_date", "edited_date", "edit_date",
                     "last_modified", "modified_date", "modified", "date_modified",
                     "updated_at", "updated", "created_date", "created_at"]


@dataclass
class FieldInfo:
    name: str
    ftype: str = ""


def list_fields(ogrinfo_path: str, source: str, layer: str) -> list[FieldInfo]:
    proc = subprocess.run(
        [ogrinfo_path, "-ro", "-so", source, layer],
        capture_output=True, text=True, timeout=120,
        creationflags=_no_window(), env=_child_env(ogrinfo_path),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ogrinfo -so failed")
    fields: list[FieldInfo] = []
    seen: set[str] = set()
    for line in proc.stdout.splitlines():
        mf = _FIDCOL_RE.match(line)
        if mf:
            # the FID column (e.g. OBJECTID) is the natural unique key — list it first
            name = mf.group(1)
            if name.lower() not in seen:
                fields.insert(0, FieldInfo(name=name, ftype="FID"))
                seen.add(name.lower())
            continue
        m = _FIELD_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        fields.append(FieldInfo(name=name, ftype=m.group(2)))
    return fields


def _auto_pick(field_names: list[str], candidates: list[str]) -> str:
    lower = {f.lower(): f for f in field_names}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    return ""


def auto_detect_key(field_names: list[str]) -> str:
    return _auto_pick(field_names, _KEY_CANDIDATES)


def auto_detect_track(field_names: list[str]) -> str:
    return _auto_pick(field_names, _TRACK_CANDIDATES)


def scalar_sql(ogrinfo_path: str, dataset: str, sql: str, env_from: str | None = None) -> str | None:
    """Run an OGR-SQL query returning a single value; return it as text."""
    proc = subprocess.run(
        [ogrinfo_path, "-ro", "-q", dataset, "-sql", sql],
        capture_output=True, text=True, timeout=300,
        creationflags=_no_window(), env=_child_env(env_from or ogrinfo_path),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ogrinfo -sql failed")
    # output looks like:  "  m (String) = 2024/05/01 12:00:00"
    for line in proc.stdout.splitlines():
        if "=" in line and "(" in line:
            return line.split("=", 1)[1].strip()
    return None


def run_sql(ogrinfo_path: str, dataset: str, sql: str, env_from: str | None = None) -> tuple[bool, str]:
    """Execute a statement (e.g. DDL/DELETE) against a dataset via ogrinfo."""
    proc = subprocess.run(
        [ogrinfo_path, "-q", dataset, "-sql", sql],
        capture_output=True, text=True, timeout=600,
        creationflags=_no_window(), env=_child_env(env_from or ogrinfo_path),
    )
    ok = proc.returncode == 0
    return ok, (proc.stderr or proc.stdout).strip()


# ---------------------------------------------------------------------------
# Import configuration + execution
# ---------------------------------------------------------------------------

@dataclass
class PgConfig:
    host: str = "localhost"
    port: int = 5432
    dbname: str = "postgis"
    user: str = "postgres"
    password: str = ""
    schema: str = "public"

    def pg_conn_string(self) -> str:
        """OGR connection string WITHOUT the password (it would be visible in the process
        command line). The password is handed to the child process through the
        ``PGPASSWORD`` environment variable instead - see :func:`_child_env`."""
        _set_pg_password(self.password)
        return (
            f"PG:host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} active_schema={self.schema}"
        )


@dataclass
class ImportOptions:
    mode: str = "overwrite"          # overwrite | append | update
    promote_to_multi: bool = True    # -nlt PROMOTE_TO_MULTI
    skip_failures: bool = True       # -skipfailures
    spatial_index: bool = True       # -lco SPATIAL_INDEX=GIST
    use_copy: bool = True            # --config PG_USE_COPY YES (faster)
    geometry_name: str = "geom"
    t_srs: str = ""                  # reproject, e.g. EPSG:4326 (empty = keep)
    prefix: str = ""                 # optional table name prefix
    lowercase_names: bool = True     # -lco LAUNDER=YES (default GDAL behavior)
    # --- incremental sync ---
    incremental: bool = False        # only copy changed rows, upsert by key
    key_field: str = ""              # unique key (e.g. OBJECTID / GlobalID); "" = auto/FID
    track_field: str = ""            # change timestamp (e.g. last_edited_date); "" = auto
    detect_deletes: bool = False     # remove target rows no longer in source
    staging_swap: bool = True        # full loads: load to staging, then atomic swap


def _fid_column(opt: ImportOptions) -> str:
    """Name of the primary-key column created in PostGIS."""
    return (opt.key_field or "fid").lower()


def build_command(
    ogr2ogr_path: str,
    source: str,
    layer: str,
    pg: PgConfig,
    opt: ImportOptions,
    where: str | None = None,
    incremental_append: bool = False,
    nln_override: str | None = None,
) -> list[str]:
    """
    Build an ogr2ogr command.

    incremental_append=True switches to the upsert path: append only the
    (optionally `where`-filtered) rows and update-in-place on primary-key
    conflict, preserving the source FID so keys stay stable across runs.
    """
    cmd = [ogr2ogr_path, "-f", "PostgreSQL", pg.pg_conn_string(), source, layer]

    fid_col = _fid_column(opt)

    if incremental_append:
        # delta upsert: update-in-place on PK conflict, insert new; keep FIDs stable
        cmd += ["-update", "-append", "-upsert", "-preserve_fid"]
    elif opt.incremental:
        # incremental full (re)load: recreate table and lock in stable FIDs/PK
        cmd += ["-overwrite", "-preserve_fid"]
    elif opt.mode == "overwrite":
        cmd.append("-overwrite")
    elif opt.mode == "append":
        cmd.append("-append")
    elif opt.mode == "update":
        cmd += ["-update", "-append"]

    target_table = nln_override or (f"{opt.prefix}{layer}" if opt.prefix else layer)
    cmd += ["-nln", target_table]

    if where:
        cmd += ["-where", where]
    if opt.promote_to_multi:
        cmd += ["-nlt", "PROMOTE_TO_MULTI"]
    if opt.skip_failures:
        cmd.append("-skipfailures")
    if opt.t_srs:
        cmd += ["-t_srs", opt.t_srs]

    # layer creation options (only applied when the table is created)
    cmd += ["-lco", f"GEOMETRY_NAME={opt.geometry_name}"]
    cmd += ["-lco", f"FID={fid_col}"]
    cmd += ["-lco", f"SCHEMA={pg.schema}"]
    cmd += ["-lco", f"SPATIAL_INDEX={'GIST' if opt.spatial_index else 'NONE'}"]
    cmd += ["-lco", f"LAUNDER={'YES' if opt.lowercase_names else 'NO'}"]

    if opt.use_copy and not incremental_append:
        cmd += ["--config", "PG_USE_COPY", "YES"]

    cmd.append("-progress")
    return cmd


@dataclass
class LayerResult:
    layer: str
    ok: bool
    seconds: float
    message: str = ""


@dataclass
class RunResult:
    started: str
    finished: str = ""
    results: list[LayerResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.ok)


def _run_cmd(cmd: list[str], ogr2ogr_path: str, timeout: int = 3600):
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        creationflags=_no_window(), env=_child_env(ogr2ogr_path),
    )


def _mask(cmd: list[str]) -> str:
    return " ".join(re.sub(r"password=\S+", "password=***", a) for a in cmd)


def _pg_table_exists(ogrinfo_path: str, pg: PgConfig, table: str) -> bool:
    try:
        val = scalar_sql(
            ogrinfo_path, pg.pg_conn_string(),
            f"SELECT to_regclass('{pg.schema}.{table.lower()}') AS t",
            env_from=ogrinfo_path,
        )
    except Exception:  # noqa: BLE001
        return False
    return bool(val) and val.lower() not in ("(null)", "null", "")


def _all_key_values(ogrinfo_path: str, dataset: str, sql: str, key: str) -> set[str]:
    proc = subprocess.run(
        [ogrinfo_path, "-ro", "-q", dataset, "-sql", sql],
        capture_output=True, text=True, timeout=600,
        creationflags=_no_window(), env=_child_env(ogrinfo_path),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "key query failed")
    rx = re.compile(rf"^\s*{re.escape(key)}\s*\([^)]*\)\s*=\s*(.+?)\s*$", re.IGNORECASE)
    out: set[str] = set()
    for line in proc.stdout.splitlines():
        m = rx.match(line)
        if m:
            out.add(m.group(1).strip())
    return out


def _reconcile_deletes(ogrinfo_path, source, layer, pg, table, key, log) -> list[str]:
    """Delete target rows whose key is no longer present in the source; return their keys."""
    src = _all_key_values(ogrinfo_path, source, f"SELECT {key} FROM \"{layer}\"", key)
    tgt = _all_key_values(
        ogrinfo_path, pg.pg_conn_string(),
        f"SELECT {key.lower()} AS {key} FROM {pg.schema}.{table.lower()}", key,
    )
    gone = [v for v in (tgt - src) if v and v.lower() not in ("(null)", "null")]
    if not gone:
        log("INFO", f"    deletes: none ({len(tgt)} target / {len(src)} source keys)")
        return []
    deleted: list[str] = []
    for i in range(0, len(gone), 500):
        batch = gone[i:i + 500]
        vals = ",".join("'" + v.replace("'", "''") + "'" for v in batch)
        ok, msg = run_sql(
            ogrinfo_path, pg.pg_conn_string(),
            f"DELETE FROM {pg.schema}.{table.lower()} WHERE {key.lower()} IN ({vals})",
            env_from=ogrinfo_path,
        )
        if ok:
            deleted += batch
        else:
            log("WARN", f"    delete batch failed: {msg[:160]}")
    log("INFO", f"    deletes: removed {len(deleted)} stale row(s)")
    return deleted


def delete_features(ogrinfo_path: str, pg: PgConfig, schema: str, table: str,
                    key: str, ids: list[str], log=None) -> tuple[int, str]:
    """Delete specific features (by key) from a PostGIS table. Used by the History tab."""
    if not (key and ids):
        return 0, "nothing to delete"
    deleted = 0
    for i in range(0, len(ids), 500):
        batch = ids[i:i + 500]
        vals = ",".join("'" + str(v).replace("'", "''") + "'" for v in batch)
        ok, msg = run_sql(
            ogrinfo_path, pg.pg_conn_string(),
            f"DELETE FROM {schema}.{table.lower()} WHERE {key.lower()} IN ({vals})",
            env_from=ogrinfo_path,
        )
        if ok:
            deleted += len(batch)
        elif log:
            log("WARN", f"delete batch failed: {msg[:160]}")
        elif not ok:
            return deleted, msg[:200]
    return deleted, "OK"


def count_features(ogrinfo_path: str, source: str, layer: str, where: str | None = None) -> int:
    sql = f'SELECT COUNT(*) AS n FROM "{layer}"'
    if where:
        sql += f" WHERE {where}"
    try:
        val = scalar_sql(ogrinfo_path, source, sql)
        return int(float(val)) if val and val.lower() not in ("(null)", "null") else 0
    except Exception:  # noqa: BLE001
        return 0


def affected_keys(ogrinfo_path: str, source: str, layer: str, key: str,
                  where: str | None = None) -> list[str]:
    """The source key values in scope for this sync (delta or full)."""
    if not key:
        return []
    sql = f'SELECT {key} FROM "{layer}"'
    if where:
        sql += f" WHERE {where}"
    try:
        return sorted(_all_key_values(ogrinfo_path, source, sql, key))
    except Exception:  # noqa: BLE001
        return []


def _swap_staging(ogrinfo_path, pg, table, staging, log) -> bool:
    """Atomically replace `table` with freshly-loaded `staging` (one transaction)."""
    t = f"{pg.schema}.{table.lower()}"
    s = f"{pg.schema}.{staging.lower()}"
    sql = (f"BEGIN; DROP TABLE IF EXISTS {t} CASCADE; "
           f"ALTER TABLE {s} RENAME TO {table.lower()}; COMMIT;")
    ok, msg = run_sql(ogrinfo_path, pg.pg_conn_string(), sql, env_from=ogrinfo_path)
    if not ok:
        log("ERROR", f"    staging swap failed: {msg[:200]}")
        run_sql(ogrinfo_path, pg.pg_conn_string(),
                f"DROP TABLE IF EXISTS {s} CASCADE", env_from=ogrinfo_path)
    return ok


def check_changes(ogrinfo_path: str, source: str, layers: list[str], opt: ImportOptions,
                  state, log: Callable[[str, str], None]) -> dict[str, int]:
    """
    Report how many source features changed since each layer's last sync,
    without importing anything. Returns {layer: new_count}.
    """
    result: dict[str, int] = {}
    for layer in layers:
        names = [f.name for f in list_fields(ogrinfo_path, source, layer)]
        track = opt.track_field or auto_detect_track(names)
        st = state.get(source, layer) if state is not None else None
        wm = st.watermark if st else ""
        if track and wm:
            where = f"{track} > '{wm}'"
            n = count_features(ogrinfo_path, source, layer, where)
            result[layer] = n
            log("INFO", f"check: {layer} -> {n} changed since {wm}")
        else:
            n = count_features(ogrinfo_path, source, layer)
            result[layer] = n
            reason = "no watermark yet" if track else "no track field"
            log("INFO", f"check: {layer} -> {n} feature(s) ({reason}; full sync)")
    total = sum(result.values())
    log("INFO", f"check: total {total} feature(s) pending across {len(layers)} layer(s)")
    return result


def run_import(
    ogr2ogr_path: str,
    source: str,
    layers: list[str],
    pg: PgConfig,
    opt: ImportOptions,
    log: Callable[[str, str], None],
    should_cancel: Callable[[], bool] | None = None,
    ogrinfo_path: str | None = None,
    state=None,
    audit=None,
    profile: str = "",
) -> RunResult:
    """
    Import each layer. `log(level, message)` receives progress lines.
    `should_cancel()` (optional) lets the caller stop between layers.

    When `opt.incremental` is on and both `ogrinfo_path` and `state` are given,
    each layer is synced as a delta (upsert of changed rows) instead of a full
    reload. The first run per layer (or a missing target table) falls back to a
    full load and records a watermark.
    """
    run = RunResult(started=datetime.now().isoformat(timespec="seconds"))
    incremental = bool(opt.incremental and ogrinfo_path and state is not None)
    log("INFO", f"Source: {source}")
    log("INFO", f"Target: {pg.host}:{pg.port}/{pg.dbname} schema={pg.schema}")
    log("INFO", f"Layers: {len(layers)} | mode={'incremental' if incremental else opt.mode}")

    for i, layer in enumerate(layers, 1):
        if should_cancel and should_cancel():
            log("WARN", "Cancelled by user.")
            break
        tag = f"[{i}/{len(layers)}] {layer}"
        t0 = datetime.now()
        try:
            if incremental:
                res = _sync_layer_incremental(
                    ogr2ogr_path, ogrinfo_path, source, layer, pg, opt, state, log, tag,
                    audit=audit, profile=profile)
            else:
                res = _sync_layer_full(
                    ogr2ogr_path, source, layer, pg, opt, log, tag,
                    ogrinfo_path=ogrinfo_path, audit=audit, profile=profile)
            run.results.append(res)
        except subprocess.TimeoutExpired:
            secs = (datetime.now() - t0).total_seconds()
            log("ERROR", f"{tag} -> TIMEOUT after {secs:.0f}s")
            run.results.append(LayerResult(layer, False, secs, "timeout"))
        except Exception as e:  # noqa: BLE001
            secs = (datetime.now() - t0).total_seconds()
            log("ERROR", f"{tag} -> ERROR: {e}")
            run.results.append(LayerResult(layer, False, secs, str(e)))

    run.finished = datetime.now().isoformat(timespec="seconds")
    log("INFO", f"Done. OK={run.ok_count} FAILED={run.fail_count}")
    return run


def _write_audit(audit, profile, source, layer, pg, opt, key, mode, secs, ok, msg,
                 upserted_ids=None, deleted_ids=None):
    if audit is None:
        return
    table = f"{opt.prefix}{layer}" if opt.prefix else layer
    try:
        audit.record({
            "profile": profile, "source": source, "layer": layer,
            "schema": pg.schema, "target_table": table.lower(), "key_field": (key or "").lower(),
            "mode": mode, "affected": len(upserted_ids or []), "deleted": len(deleted_ids or []),
            "seconds": secs, "ok": ok, "message": msg,
            "pg_host": pg.host, "pg_port": pg.port, "pg_db": pg.dbname,
        }, upserted_ids=upserted_ids, deleted_ids=deleted_ids)
    except Exception:  # noqa: BLE001
        pass


def _sync_layer_full(ogr2ogr_path, source, layer, pg, opt, log, tag,
                     ogrinfo_path=None, audit=None, profile="") -> LayerResult:
    t0 = datetime.now()
    table = f"{opt.prefix}{layer}" if opt.prefix else layer

    # resolve key (for audit IDs), if we can inspect the source
    key = opt.key_field
    if not key and ogrinfo_path:
        try:
            key = auto_detect_key([f.name for f in list_fields(ogrinfo_path, source, layer)])
        except Exception:  # noqa: BLE001
            key = ""
    eopt = replace(opt, key_field=key) if key else opt

    # staging-swap only makes sense for a full recreate (overwrite)
    use_staging = bool(opt.staging_swap and opt.mode == "overwrite" and ogrinfo_path)
    staging = f"_stg_{table}"
    if use_staging:
        log("INFO", f"{tag} -> starting (overwrite via staging swap)")
        cmd = build_command(ogr2ogr_path, source, layer, pg, eopt, nln_override=staging)
    else:
        log("INFO", f"{tag} -> starting ({opt.mode})")
        cmd = build_command(ogr2ogr_path, source, layer, pg, eopt)

    log("DEBUG", _mask(cmd))
    proc = _run_cmd(cmd, ogr2ogr_path)
    secs = (datetime.now() - t0).total_seconds()
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip().splitlines()
        tail = " | ".join(err[-3:]) if err else "unknown error"
        log("ERROR", f"{tag} -> FAILED: {tail}")
        _write_audit(audit, profile, source, layer, pg, opt, key, opt.mode, secs, False, tail)
        return LayerResult(layer, False, secs, tail)

    if use_staging:
        if not _swap_staging(ogrinfo_path, pg, table, staging, log):
            secs = (datetime.now() - t0).total_seconds()
            _write_audit(audit, profile, source, layer, pg, opt, key, opt.mode, secs,
                         False, "staging swap failed")
            return LayerResult(layer, False, secs, "staging swap failed")
        log("INFO", f"{tag} -> swapped staging into {pg.schema}.{table.lower()}")

    ids = affected_keys(ogrinfo_path, source, layer, key) if ogrinfo_path else []
    log("INFO", f"{tag} -> OK in {secs:.1f}s; {len(ids) if key else '?'} feature(s) written")
    _write_audit(audit, profile, source, layer, pg, opt, key, opt.mode, secs, True, "",
                 upserted_ids=ids)
    return LayerResult(layer, True, secs)


def _sync_layer_incremental(ogr2ogr_path, ogrinfo_path, source, layer, pg, opt, state, log, tag,
                            audit=None, profile="") -> LayerResult:
    t0 = datetime.now()
    st = state.get(source, layer)
    table = f"{opt.prefix}{layer}" if opt.prefix else layer

    # resolve key / track fields (explicit override, else auto-detect)
    names = [f.name for f in list_fields(ogrinfo_path, source, layer)]
    key = opt.key_field or auto_detect_key(names)
    track = opt.track_field or auto_detect_track(names)

    # use the resolved key as the PostGIS primary-key column so upserts and
    # delete-reconciliation all reference the same, correctly-named column
    eopt = replace(opt, key_field=key) if key else opt

    target_exists = _pg_table_exists(ogrinfo_path, pg, table)
    do_full = (not target_exists) or (not st.last_full)
    where = None

    if do_full:
        reason = "target missing" if not target_exists else "first sync"
        use_staging = bool(opt.staging_swap and target_exists)  # only swap if there's a table to protect
        staging = f"_stg_{table}"
        log("INFO", f"{tag} -> full load ({reason}); key={key or 'FID'} track={track or '-'}"
                    + (" [staging]" if use_staging else ""))
        cmd = build_command(ogr2ogr_path, source, layer, pg, eopt,
                            incremental_append=False,
                            nln_override=staging if use_staging else None)
    else:
        use_staging = False
        where = f"{track} > '{st.watermark}'" if (track and st.watermark) else None
        detail = f"where={where}" if where else "no track field -> full upsert"
        log("INFO", f"{tag} -> delta upsert; key={key or 'FID'} {detail}")
        cmd = build_command(ogr2ogr_path, source, layer, pg, eopt,
                            where=where, incremental_append=True)

    log("DEBUG", _mask(cmd))
    proc = _run_cmd(cmd, ogr2ogr_path)
    secs = (datetime.now() - t0).total_seconds()
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip().splitlines()
        tail = " | ".join(err[-3:]) if err else "unknown error"
        log("ERROR", f"{tag} -> FAILED: {tail}")
        _write_audit(audit, profile, source, layer, pg, opt, key,
                     "full" if do_full else "delta", secs, False, tail)
        return LayerResult(layer, False, secs, tail)

    if do_full and use_staging:
        if not _swap_staging(ogrinfo_path, pg, table, f"_stg_{table}", log):
            _write_audit(audit, profile, source, layer, pg, opt, key, "full", secs,
                         False, "staging swap failed")
            return LayerResult(layer, False, secs, "staging swap failed")
        log("INFO", f"{tag} -> swapped staging into {pg.schema}.{table.lower()}")

    # which source features were in scope for this sync
    upserted = affected_keys(ogrinfo_path, source, layer, key, where)

    # advance watermark from the source's current max(track)
    now_iso = datetime.now().isoformat(timespec="seconds")
    if track:
        try:
            wm = scalar_sql(ogrinfo_path, source, f'SELECT MAX({track}) AS m FROM "{layer}"')
            if wm and wm.lower() not in ("(null)", "null"):
                st.watermark = wm
        except Exception as e:  # noqa: BLE001
            log("WARN", f"{tag} -> could not read watermark: {e}")
    if do_full:
        st.last_full = now_iso
    st.last_sync = now_iso

    # optional delete reconciliation (needs a stable key; skip on full loads)
    deleted: list[str] = []
    if opt.detect_deletes and key and not do_full:
        try:
            deleted = _reconcile_deletes(ogrinfo_path, source, layer, pg, table, key, log)
        except Exception as e:  # noqa: BLE001
            log("WARN", f"{tag} -> delete reconciliation skipped: {e}")

    state.put(source, layer, st)
    mode_txt = "full" if do_full else "delta"
    st.rows_last = len(upserted)
    log("INFO", f"{tag} -> OK ({mode_txt}) in {secs:.1f}s; "
                f"{len(upserted) if key else '?'} upserted, {len(deleted)} deleted; "
                f"watermark={st.watermark or '-'}")
    _write_audit(audit, profile, source, layer, pg, opt, key, mode_txt, secs, True, "",
                 upserted_ids=upserted, deleted_ids=deleted)
    return LayerResult(layer, True, secs)


def test_pg_connection(ogrinfo_path: str, pg: PgConfig) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [ogrinfo_path, "-ro", "-q", pg.pg_conn_string()],
            capture_output=True, text=True, timeout=30,
            creationflags=_no_window(), env=_child_env(ogrinfo_path),
        )
        if proc.returncode == 0:
            return True, "OK"
        return False, (proc.stderr or proc.stdout).strip()[:400]
    except Exception as e:  # noqa: BLE001
        return False, str(e)
