"""
Runs slow work (git, re-encryption, content search, key generation) on a
worker thread so the window stays responsive, delivering the result back
on the GUI thread.
"""

import threading

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot


class _Worker(QObject):
    """Runs one function on the worker thread."""

    finished = pyqtSignal(object, object)
    progress = pyqtSignal(int, int)

    def __init__(self, function):
        super().__init__()
        self.function = function
        self.cancel_event = threading.Event()

    @pyqtSlot()
    def run(self):
        """Run the function and report its result or exception."""
        try:
            result = self.function(self.progress.emit, self.cancel_event.is_set)
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.finished.emit(None, error)
            return
        self.finished.emit(result, None)


class Task(QObject):
    """
    A running background task. Lives on the GUI thread, so its callbacks
    run there.
    """

    def __init__(self, function, on_done, on_progress=None, parent=None):
        super().__init__(parent)
        self.on_done = on_done
        self.on_progress = on_progress
        self.thread = QThread()
        self.worker = _Worker(function)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._finished)
        self.worker.progress.connect(self._progress)

    def start(self):
        """Start the task."""
        _running.add(self)
        self.thread.start()

    def cancel(self):
        """Ask the task to stop; the function decides when it checks."""
        self.worker.cancel_event.set()

    def wait(self):
        """Block until the worker thread has stopped."""
        self.thread.wait()

    @pyqtSlot(int, int)
    def _progress(self, done, total):
        if self.on_progress:
            self.on_progress(done, total)

    @pyqtSlot(object, object)
    def _finished(self, result, error):
        self.thread.quit()
        self.thread.wait()
        _running.discard(self)
        self.on_done(result, error)


_running = set()


def run_task(function, on_done, on_progress=None):
    """
    Run function(progress, cancelled) on a worker thread.

    :param function: Callable taking a progress(done, total) callable and a
                     cancelled() callable; its return value is the result.
    :param on_done: Called on the GUI thread with (result, error).
    :param on_progress: Optional, called on the GUI thread with (done, total).
    :return: The started Task.
    """
    task = Task(function, on_done, on_progress)
    task.start()
    return task


def wait_for_all():
    """Wait for all running tasks, used when quitting."""
    for task in list(_running):
        task.cancel()
        task.wait()
