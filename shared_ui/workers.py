"""
Generic QThread worker for running functions off the main UI thread.
"""
try:
    from PySide6.QtCore import QThread, Signal
except ImportError:
    class QThread: pass
    class Signal:
        def __init__(self, *args, **kwargs): pass
        def emit(self, *args, **kwargs): pass


class FunctionWorker(QThread):
    """
    Runs callable *fn* with *args* and *kwargs* in a background thread.

    Keep a reference to the worker in the parent widget to prevent premature
    garbage collection before the thread finishes, e.g.:
        self._worker = FunctionWorker(my_fn, arg1, arg2)
        self._worker.finished_ok.connect(self.on_done)
        self._worker.failed.connect(self.on_error)
        self._worker.start()
    """

    finished_ok: Signal = Signal(object)
    failed: Signal = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
