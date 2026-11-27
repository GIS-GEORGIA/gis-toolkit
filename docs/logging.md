# Centralized logging (`tools/logging_manager.py`)

| Level | File | Content |
|---|---|---|
| USER | `user.log` | short messages about finished operations and errors |
| DETAIL | `detailed.log` | + inputs/outputs, CRS, parameters, timestamps, START/END of each operation |
| DEBUG | `debug.log` | + technical diagnostics, tracebacks |
| all | `events.jsonl` | one JSON object per record (level, tool, message, data) |
| operations | `history.sqlite` | one row per tool run: date/time, tool, inputs, outputs, duration, status (`ok`/`error`/`cancelled`), error |

Folder: `GIS_BOX_LOG_DIR`, else Windows `%LOCALAPPDATA%\GIS_BOX\logs`, Linux `$XDG_STATE_HOME/GIS_BOX/logs` (`~/.local/state`), macOS `~/Library/Logs/GIS_BOX`. Files rotate at ~2 MB (3 old copies kept).

```python
from tools.logging_manager import get_manager
lm = get_manager()
with lm.operation("zone_intersect", inputs=[parcel, zone], params={"field": "id"}) as op:
    ...
    op.output(out_path)          # exceptions are recorded and re-raised
lm.history(limit=20, tool="zone_intersect")
lm.export_diagnostics("diagnostics.zip")   # redacted logs + history + environment report
```

## Secrets
Removed **before** writing: `password=`/`token:`/`api_key`/`secret`/`Authorization: Bearer ...`, `scheme://user:pass@host`, GitHub tokens, dict values under secret-looking keys, and any value registered with `register_secret()` (the PostgreSQL password is registered automatically). The diagnostics zip is redacted a second time. Pattern-based redaction is best effort - do not log credentials on purpose.

## Integration status
- `pgdb_transfer` writes every run into the operation history (its own detailed per-year log/CSV stay as they were).
- Other tools keep their current logs for now; they are connected one by one when their UI is ported to PySide6.
- Tests use an isolated temporary log folder (`conftest.py`).
