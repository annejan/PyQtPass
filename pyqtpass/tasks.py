"""
Runs slow work (git, re-encryption, content search, key generation) on a
worker thread so the window stays responsive, delivering the result back
on the GUI thread.
"""

import threading
import time

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot

from pyqtpass import executor


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

    def __init__(
        self, function, on_done, on_progress=None, parent=None, critical=False
    ):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        super().__init__(parent)
        # A critical task (git, a store change) is not killed when quitting:
        # killing a commit or a merge can leave index.lock or a half merge.
        self.critical = critical
        self.on_done = on_done
        self.on_progress = on_progress
        self.thread = QThread()
        self.worker = _Worker(function)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        # Ends the thread from the worker itself: when the app is quitting
        # the GUI thread no longer delivers queued signals, and waiting for
        # _finished to quit the thread would wait forever.
        self.worker.finished.connect(
            self.thread.quit, Qt.ConnectionType.DirectConnection
        )
        self.worker.finished.connect(self._finished)
        self.worker.progress.connect(self._progress)

    def start(self):
        """Start the task."""
        _running.add(self)
        self.thread.start()

    def cancel(self):
        """Ask the task to stop; the function decides when it checks."""
        self.worker.cancel_event.set()

    def wait(self, timeout_ms=None):
        """
        Block until the worker thread has stopped.

        :param timeout_ms: Give up after this many milliseconds.
        :return: True when the thread has stopped.
        """
        if timeout_ms is None:
            return self.thread.wait()
        return self.thread.wait(timeout_ms)

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


def run_task(function, on_done, on_progress=None, critical=False):
    """
    Run function(progress, cancelled) on a worker thread.

    :param function: Callable taking a progress(done, total) callable and a
                     cancelled() callable; its return value is the result.
    :param on_done: Called on the GUI thread with (result, error).
    :param on_progress: Optional, called on the GUI thread with (done, total).
    :param critical: The task changes the store or runs git; see Task.
    :return: The started Task.
    """
    task = Task(function, on_done, on_progress, critical=critical)
    task.start()
    return task


def running():
    """:return: True while any task is running."""
    return bool(_running)


def stuck():
    """
    :return: True when a worker thread is still running after wait_for_all
             gave up on it; Python must then not destroy its QThread.
    """
    return any(task.thread.isRunning() for task in _running)


def wait_for_all(grace_ms=3000, critical_ms=60000, final_ms=10000, idle=None):
    """
    Stop all running tasks, used when quitting. They are asked to cancel;
    other tasks get grace_ms to finish, critical tasks (git, store changes)
    critical_ms in all, since killing them can leave a lock or a half merge
    behind. What still runs after that has its commands terminated and
    gets final_ms to end.

    :param grace_ms: Milliseconds other tasks get to finish on their own.
    :param critical_ms: Milliseconds critical tasks get, together.
    :param final_ms: Milliseconds to wait after terminating, at most.
    :param idle: Optional callable, called about every 100 ms while waiting
                 (to keep a progress window painted); when it returns True
                 the wait for critical tasks ends early.
    :return: True when every task has stopped.
    """
    tasks = list(_running)
    for task in tasks:
        task.cancel()
    start = time.monotonic()
    deadlines = {False: start + grace_ms / 1000, True: start + critical_ms / 1000}
    while True:
        now = time.monotonic()
        waiting = [
            task
            for task in tasks
            if task.thread.isRunning() and now < deadlines[task.critical]
        ]
        if not waiting or (idle is not None and idle()):
            break
        waiting[0].wait(100)
    if any(task.thread.isRunning() for task in tasks):
        executor.terminate_all()
        deadline = time.monotonic() + final_ms / 1000
        for task in tasks:
            task.wait(max(0, int((deadline - time.monotonic()) * 1000)))
    return not any(task.thread.isRunning() for task in tasks)
