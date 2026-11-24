# pytest — რეპოს ძირი sys.path-ზე, რომ `tools.*` იმპორტირებადი იყოს.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
