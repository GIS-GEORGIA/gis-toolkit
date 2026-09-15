# -*- coding: utf-8 -*-
"""GDB → PostGIS — headless (GUI-less) გაშვება შენახული პარამეტრებით.

გამოიძახება `gis_box.py --gdb2pg-run`-ით (Windows Task Scheduler-იდან), რომ
განრიგი GIS_BOX-ის დახურვის შემდეგაც იმუშაოს. კითხულობს ბოლოს „დამახსოვრებულ“
კონფიგს (`gis_box_settings.json` → tool_config.gdb2postgis) და უშვებს ერთ
იმპორტს; შედეგს წერს `gdb2postgis_run.log`-ში.

პაროლი: ან შენახული (თუ „პაროლის დამახსოვრება“ მონიშნულია), ან garemos-ცვლადი
`GDB2PG_PGPASSWORD` / `PGPASSWORD`.
"""

import os
import json
from datetime import datetime

# ჩასაწერ კონფიგ-საქაღალდეში (frozen: build-ს გარეთ, სტაბილური)
from tools.apppaths import data_path
SETTINGS_FILE = data_path("gis_box_settings.json")
LOG_FILE = data_path("gdb2postgis_run.log")


def _log(level, message):
    line = f"{datetime.now().isoformat(timespec='seconds')} {level}: {message}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _load_cfg():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return (json.load(f).get("tool_config") or {}).get("gdb2postgis") or {}
    except (OSError, ValueError):
        return {}


def run_headless():
    """ერთი იმპორტი შენახული პარამეტრებით. აბრუნებს 0/1 (exit code)."""
    from tools import gdb2postgis_core as core
    from tools.gdb2postgis_state import SyncState
    from tools.gdb2postgis_audit import AuditStore

    cfg = _load_cfg()
    if not cfg:
        _log("ERROR", "No saved gdb2postgis config — open GIS_BOX and press Remember.")
        return 1

    ogr2ogr = core.find_tool("ogr2ogr", cfg.get("ogr2ogr") or None)
    ogrinfo = core.find_tool("ogrinfo", cfg.get("ogr2ogr") or None)
    if not (ogr2ogr and ogrinfo):
        _log("ERROR", "GDAL ogr2ogr/ogrinfo not found.")
        return 1

    src = os.path.join(cfg.get("source_dir", ""), cfg.get("source", ""))
    layers = cfg.get("layers") or []
    if not (src and os.path.exists(src) and layers):
        _log("ERROR", f"No source/layers to run (source={src!r}, layers={len(layers)}).")
        return 1

    pw = cfg.get("password") or os.environ.get("GDB2PG_PGPASSWORD") \
        or os.environ.get("PGPASSWORD", "")
    try:
        port = int(cfg.get("port") or 5432)
    except (TypeError, ValueError):
        port = 5432
    pg = core.PgConfig(
        host=cfg.get("host", "localhost"), port=port,
        dbname=cfg.get("dbname", "postgis"), user=cfg.get("user", "postgres"),
        password=pw, schema=cfg.get("schema", "public"))
    opt = core.ImportOptions(
        mode=cfg.get("mode", "overwrite"), t_srs=cfg.get("t_srs", ""),
        prefix=cfg.get("prefix", ""), promote_to_multi=cfg.get("promote", True),
        spatial_index=cfg.get("gist", True), use_copy=cfg.get("copy", True),
        incremental=cfg.get("incremental", False), key_field=cfg.get("key_field", ""),
        track_field=cfg.get("track_field", ""), detect_deletes=cfg.get("detect_deletes", False))

    _log("INFO", f"=== Headless run: {len(layers)} layer(s) from {src} ===")
    try:
        res = core.run_import(ogr2ogr, src, layers, pg, opt, _log,
                              ogrinfo_path=ogrinfo, state=SyncState(),
                              audit=AuditStore(), profile="scheduled")
        _log("INFO", f"Finished: OK={res.ok_count} FAILED={res.fail_count}")
        return 0 if res.fail_count == 0 else 1
    except Exception as e:  # noqa: BLE001
        _log("ERROR", f"Run failed: {e}")
        return 1
