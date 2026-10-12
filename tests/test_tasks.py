"""Tests for background tasks and the command runner."""

# pylint: disable=missing-function-docstring

import os
import subprocess
import sys
import time

import executor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUIT_WHILE_RUNNING = """
import sys
sys.path.insert(0, {root!r})
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import executor
import tasks

app = QApplication([])
app.aboutToQuit.connect(tasks.wait_for_all)
tasks.run_task(lambda _p, _c: executor.run(["sleep", "30"]), lambda *_: None)
QTimer.singleShot(100, app.quit)
app.exec()
print("exited")
"""


def test_quitting_while_a_task_runs_does_not_hang():
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-c", QUIT_WHILE_RUNNING.format(root=ROOT)],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=False,
    )
    assert "exited" in result.stdout, result.stderr
    assert time.monotonic() - start < 20


def test_timeout_ends_the_whole_process_group(tmp_path):
    marker = tmp_path / "grandchild-ran"
    script = f"sleep 3 && touch {marker}"
    returncode, _, _ = executor.run(["sh", "-c", f"({script}) & wait"], timeout=0.5)
    assert returncode == -1
    time.sleep(4)
    assert not marker.exists()


def test_commands_get_no_terminal_input():
    returncode, stdout, _ = executor.run(["sh", "-c", "cat; echo done"], timeout=5)
    assert returncode == 0 and stdout == b"done\n"


SECOND_START = """
import sys
sys.path.insert(0, {root!r})
from PyQt6.QtWidgets import QApplication
import single_instance

app = QApplication([])
print("found" if single_instance.activate_running_instance() else "none")
"""


def test_single_instance_answers_and_ignores_strangers(qapp, tmp_path, monkeypatch):
    # pylint: disable=import-outside-toplevel,unused-argument
    from PyQt6.QtCore import QTimer
    from PyQt6.QtNetwork import QLocalServer
    from PyQt6.QtWidgets import QWidget

    import single_instance

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    os.chmod(tmp_path, 0o700)
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}

    def second_start():
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            [sys.executable, "-c", SECOND_START.format(root=ROOT)],
            stdout=subprocess.PIPE,
            text=True,
            env=env,
        )
        while process.poll() is None:
            qapp.processEvents()
            time.sleep(0.01)
        return process.stdout.read().strip()

    # A listener that is not PyQtPass does not stop PyQtPass from starting.
    stranger = QLocalServer()
    assert stranger.listen(single_instance.single_instance_name())
    assert second_start() == "none"
    stranger.close()

    shown = []
    window = QWidget()
    window.show_and_raise = lambda: shown.append(True)
    server = single_instance.listen_for_instances(window)
    assert server.isListening()
    assert second_start() == "found"
    QTimer.singleShot(0, lambda: None)
    qapp.processEvents()
    assert shown == [True]
    server.close()
