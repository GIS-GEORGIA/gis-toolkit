"""
Per-layer incremental-sync state (watermarks), stored separately from config.

Keyed by "<abs-source>::<layer>". Holds the high-watermark value of the
change-tracking field after the last successful sync, plus bookkeeping.

Vendored into GIS_BOX from the MIT gdb2postgis project; the state file lives
next to GIS_BOX (git-ignored) instead of the original per-user app dir.
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime

# state ფაილი — ჩასაწერ კონფიგ-საქაღალდეში (frozen: build-ს გარეთ, სტაბილური)
from tools.apppaths import data_path
STATE_PATH = data_path("gdb2postgis_sync_state.json")


@dataclass
class LayerState:
    watermark: str = ""        # max value of track field at last sync
    last_full: str = ""        # ISO timestamp of last full (re)load
    last_sync: str = ""        # ISO timestamp of last sync of any kind
    rows_last: int = 0         # rows touched last sync


class SyncState:
    def __init__(self, path: str = STATE_PATH):
        self.path = path
        self._data: dict[str, dict] = {}
        self.load()

    @staticmethod
    def key(source: str, layer: str) -> str:
        return f"{os.path.abspath(source)}::{layer}"

    def get(self, source: str, layer: str) -> LayerState:
        raw = self._data.get(self.key(source, layer))
        return LayerState(**raw) if raw else LayerState()

    def put(self, source: str, layer: str, st: LayerState) -> None:
        self._data[self.key(source, layer)] = asdict(st)
        self.save()

    def reset(self, source: str, layer: str) -> None:
        self._data.pop(self.key(source, layer), None)
        self.save()

    def load(self) -> None:
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:  # noqa: BLE001
                self._data = {}

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
