"""Tests for background tasks and the command runner."""

# pylint: disable=missing-function-docstring

import os
import subprocess
import sys
import time

from pyqtpass import executor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUIT_WHILE_RUNNING = """
import sys
sys.path.insert(0, {root!r})
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from pyqtpass import executor
from pyqtpass import tasks

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
from pyqtpass import single_instance

app = QApplication([])
app.setOrganizationName("IJHack")
app.setApplicationName("PyQtPass")
found = single_instance.activate_running_instance(" ".join(sys.argv[1:]))
print("found" if found else "none")
"""


def test_single_instance_answers_and_ignores_strangers(qapp, tmp_path, monkeypatch):
    # pylint: disable=import-outside-toplevel,unused-argument
    from PyQt6.QtCore import QTimer
    from PyQt6.QtNetwork import QLocalServer
    from PyQt6.QtWidgets import QWidget

    from pyqtpass import single_instance

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    os.chmod(tmp_path, 0o700)
    qapp.setOrganizationName("IJHack")
    qapp.setApplicationName("PyQtPass")
    single_instance._token.clear()  # pylint: disable=protected-access
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}

    def second_start(*search):
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            [sys.executable, "-c", SECOND_START.format(root=ROOT), *search],
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

    # A listener that answers, but without this user's token, is not one.
    impostor = QLocalServer()
    assert impostor.listen(single_instance.single_instance_name())
    impostor.newConnection.connect(
        lambda: impostor.nextPendingConnection().write(b"PyQtPass\n")
    )
    assert second_start() == "none"
    impostor.close()

    shown = []
    window = QWidget()
    window.show_and_raise = lambda: shown.append(True)
    window.search_for = shown.append
    server = single_instance.listen_for_instances(window)
    assert server.isListening()
    assert second_start() == "found"
    QTimer.singleShot(0, lambda: None)
    qapp.processEvents()
    assert shown == [True]
    # A search text goes to the running instance, on one line.
    assert second_start("git", "hüb\nlab") == "found"
    qapp.processEvents()
    assert shown == [True, "git hüb lab"]
    server.close()


def test_quit_wait_is_one_budget_and_can_be_cut_short(qapp):
    # pylint: disable=import-outside-toplevel,unused-argument
    from pyqtpass import tasks

    def sleeper(_progress, _cancelled):
        return executor.run(["sleep", "20"])

    for _ in range(3):
        tasks.run_task(sleeper, lambda *_: None, critical=True)
    start = time.monotonic()
    assert tasks.wait_for_all(grace_ms=100, critical_ms=600, final_ms=5000)
    # Three critical tasks share 0.6 s, instead of 0.6 s each.
    assert time.monotonic() - start < 3
    executor.allow_commands()
    for _ in range(2):
        tasks.run_task(sleeper, lambda *_: None, critical=True)
    calls = []
    start = time.monotonic()
    assert tasks.wait_for_all(
        critical_ms=60000, final_ms=5000, idle=lambda: calls.append(1) or True
    )
    assert calls and time.monotonic() - start < 3
    # Once quitting has ended the commands, a new one does not start.
    start = time.monotonic()
    assert executor.run(["sleep", "20"])[0] != 0
    assert time.monotonic() - start < 3
    while tasks.running():
        qapp.processEvents()
    assert not tasks.stuck()
    executor.allow_commands()
