"""Background processing: QRunnable tasks on QThreadPool with progress, cancel and operation history.

The GIS function runs in a worker thread and receives a :class:`TaskContext`::

    def work(ctx):
        ctx.log("reading...")
        ctx.progress(1, 10)
        ctx.check_cancelled()        # raises Cancelled
        return result

    run_task(work, tool="crs_manager", on_done=..., on_error=..., on_progress=...)

Callbacks are delivered in the GUI thread (through a QObject bridge), the UI never blocks.
Every task is recorded in the central operation history (logging_manager).
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class Cancelled(Exception):
    """Raised inside a task when the user cancelled it."""


class TaskContext:
    def __init__(self, signals, event):
        self._s = signals
        self._ev = event

    def log(self, msg):
        self._s.log.emit(str(msg))

    def progress(self, i, n, text=""):
        self._s.progress.emit(int(i), int(n), str(text))

    def cancelled(self):
        return self._ev.is_set()

    def check_cancelled(self):
        if self._ev.is_set():
            raise Cancelled()


class _Signals(QObject):
    progress = Signal(int, int, str)
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)
    cancelled = Signal()
    finished = Signal()


class _Bridge(QObject):
    """Lives in the GUI thread; turns queued signals into plain callbacks."""

    def __init__(self, signals, cbs, on_finished):
        super().__init__()
        self.cbs = cbs
        self._fin = on_finished
        signals.progress.connect(self.on_progress)
        signals.log.connect(self.on_log)
        signals.done.connect(self.on_done)
        signals.error.connect(self.on_error)
        signals.cancelled.connect(self.on_cancelled)
        signals.finished.connect(self.on_finished)

    def _call(self, name, *a):
        cb = self.cbs.get(name)
        if cb:
            cb(*a)

    @Slot(int, int, str)
    def on_progress(self, i, n, t):
        self._call("progress", i, n, t)

    @Slot(str)
    def on_log(self, m):
        self._call("log", m)

    @Slot(object)
    def on_done(self, r):
        self._call("done", r)

    @Slot(str)
    def on_error(self, m):
        self._call("error", m)

    @Slot()
    def on_cancelled(self):
        self._call("cancelled")

    @Slot()
    def on_finished(self):
        self._call("finished")
        self._fin(self)


class Task(QRunnable):
    def __init__(self, fn, tool, inputs=None, params=None):
        super().__init__()
        self.setAutoDelete(False)              # kept alive until its signals were delivered
        self.fn, self.tool = fn, tool
        self.inputs, self.params = inputs or [], params or {}
        self.signals = _Signals()
        self.cancel_event = threading.Event()
        self.ctx = TaskContext(self.signals, self.cancel_event)
        self.outputs = []

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        from tools.logging_manager import get_manager
        s = self.signals
        try:
            with get_manager().operation(self.tool, self.inputs, self.params) as op:
                try:
                    result = self.fn(self.ctx)
                except Cancelled:
                    op.cancel()
                    result = Cancelled
                out = getattr(result, "output_file", "") or ""
                for o in (getattr(result, "outputs", None) or ([out] if out else [])):
                    op.output(o)
            if result is Cancelled:
                s.cancelled.emit()
            else:
                s.done.emit(result)
        except Exception as e:                  # noqa: BLE001 - reported to the UI, details in the log
            from tools.logging_manager import redact
            s.error.emit(redact("{}: {}".format(type(e).__name__, e)))
        finally:
            s.finished.emit()


_alive = set()


def run_task(fn, tool, inputs=None, params=None, on_done=None, on_error=None, on_cancelled=None,
             on_progress=None, on_log=None, on_finished=None, pool=None):
    """Start ``fn(ctx)`` in the thread pool. Returns the :class:`Task` (call ``.cancel()`` to cancel)."""
    task = Task(fn, tool, inputs, params)
    cbs = {"done": on_done, "error": on_error, "cancelled": on_cancelled, "progress": on_progress,
           "log": on_log, "finished": on_finished}

    def release(bridge):
        _alive.discard((task, bridge))

    bridge = _Bridge(task.signals, cbs, release)
    _alive.add((task, bridge))
    (pool or QThreadPool.globalInstance()).start(task)
    return task
