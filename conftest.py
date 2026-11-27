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


def pytest_sessionfinish(session, exitstatus):
    """Clear the clipboard before the interpreter shuts down.

    With the Qt `offscreen` platform (tests / CI) a clipboard that still holds data set by a test
    (QMimeData / an image) crashes the process during shutdown - access violation on Windows,
    segmentation fault on Linux - AFTER all tests passed, so CI reported a failure. The real
    window platforms are not affected (checked: same script exits cleanly on `windows`)."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is not None:
        import gc
        from PySide6.QtCore import QCoreApplication, QEvent
        app.clipboard().clear()
        # Destroy the windows the tests left behind and collect them NOW, while Qt is still alive,
        # instead of during interpreter finalization. (Not the cause of the Linux / Python 3.11
        # "bool_dealloc" abort: that is PySide6 6.12.0 - see tests/test_pyside_emit_refcount.py.)
        for w in app.topLevelWidgets():
            w.close()
            w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        gc.collect()


@pytest.fixture(autouse=True)
def _isolated_v2_dir(tmp_path_factory, monkeypatch):
    """V2 settings/updates/backups must never touch the real per-user folder in tests."""
    monkeypatch.setenv("GIS_BOX_V2_DIR", str(tmp_path_factory.mktemp("gisbox_v2")))
