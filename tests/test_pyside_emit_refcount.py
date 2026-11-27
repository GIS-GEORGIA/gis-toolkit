# -*- coding: utf-8 -*-
"""PySide6 6.12.0 (seen on Linux with Python 3.11; not on Windows; 6.9.3-6.11.3 are fine) drops references to
`True` on Python-side Signal.emit() - with or without receivers, for Python and C++ signals alike. Every
V2 task emits several signals, so a test session (or a long app session) eventually drives True's reference
count to zero and the interpreter aborts at exit with "Fatal Python error: bool_dealloc", after all tests passed.

Python >= 3.12 makes True immortal, so there it is harmless. The version is excluded in requirements-optional.txt
and CI; if the bad release comes back, this test fails with its name (the run still aborts at exit)."""
import importlib.util
import sys

import pytest

pytestmark = [
    pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="PySide6 not installed"),
    pytest.mark.skipif(sys.version_info >= (3, 12), reason="True is immortal on Python >= 3.12"),
]

N = 200


def test_signal_emit_keeps_the_refcount_of_true():
    import PySide6
    from PySide6.QtCore import QObject, Signal

    class Emitter(QObject):
        flag = Signal(bool)

    e = Emitter()
    seen = []
    e.flag.connect(seen.append)
    pad = [True] * (10 * N)                     # keep this process alive even when the bug is present
    before = sys.getrefcount(True)
    for i in range(N):
        e.flag.emit(bool(i % 2))
    lost = before - sys.getrefcount(True)
    del pad
    assert len(seen) == N
    if lost > 0:
        # repair what this test itself broke, so the session can still report the failure and exit cleanly
        import ctypes
        for _ in range(lost):
            ctypes.pythonapi.Py_IncRef(ctypes.py_object(True))
    assert lost <= 0, (
        f"PySide6 {PySide6.__version__} lost {lost} references to True in {N} Signal.emit() calls; the test run "
        f"would abort at exit with 'bool_dealloc'. Install another PySide6 version (6.12.0 is known bad).")
