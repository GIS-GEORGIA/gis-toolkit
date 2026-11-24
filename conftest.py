# pytest — რეპოს ძირი sys.path-ზე, რომ `tools.*` იმპორტირებადი იყოს.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Qt must be loaded BEFORE geopandas/shapely/pyogrio (the other order crashes with an access
# violation on Windows). Importing it first here keeps the whole test session safe.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    import PySide6.QtCore  # noqa: F401
except ImportError:
    pass

import pytest


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path_factory, monkeypatch):
    """Tests must never write to the user's real GIS_BOX log folder / history."""
    from tools import logging_manager as lm
    d = tmp_path_factory.mktemp("gisbox_logs")
    monkeypatch.setenv("GIS_BOX_LOG_DIR", str(d))
    lm.set_manager(None)
    yield
    lm.set_manager(None)
