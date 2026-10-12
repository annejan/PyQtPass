"""
Keeps PyQtPass to one window per user: a second start asks the running
instance to show itself, like the QtPass single application.

The socket lives in the user's private runtime directory (on Linux
$XDG_RUNTIME_DIR, mode 0700), not in the shared temporary directory, so
another account cannot put a listener there first. A running instance also
answers with a fixed greeting; a socket that does not answer is not taken
for one, so a stale or foreign socket never stops PyQtPass from starting.
"""

import getpass
import os

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

GREETING = b"PyQtPass\n"
TIMEOUT_MS = 1000


def single_instance_name():
    """
    :return: The local server name or socket path shared by this user's
             instances.
    """
    runtime = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.RuntimeLocation
    )
    if os.name == "posix" and runtime and os.path.isdir(runtime):
        return os.path.join(runtime, "PyQtPass.socket")
    return f"PyQtPass-{getpass.getuser()}"


def ask_running_instance(command):
    """
    Send a command to a running instance.

    :param command: b"show" or b"ping".
    :return: True when a PyQtPass instance answered.
    """
    socket = QLocalSocket()
    socket.connectToServer(single_instance_name())
    if not socket.waitForConnected(TIMEOUT_MS):
        return False
    socket.write(command + b"\n")
    socket.flush()
    answer = b""
    while len(answer) < len(GREETING) and socket.waitForReadyRead(TIMEOUT_MS):
        answer += bytes(socket.readAll())
    socket.disconnectFromServer()
    return answer.startswith(GREETING)


def activate_running_instance():
    """
    Ask an already running PyQtPass to show its window.

    :return: True when another instance answered.
    """
    return ask_running_instance(b"show")


def listen_for_instances(window):
    """
    Show the window when another instance is started.

    :param window: The main window.
    :return: The QLocalServer, which has to be kept referenced.
    """
    server = QLocalServer(window)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    name = single_instance_name()
    if not server.listen(name):
        if ask_running_instance(b"ping"):
            # Another instance (--new-instance) owns the name; leave it be.
            return server
        # A crashed instance can leave its socket behind; nobody answered
        # on it, so it is stale.
        QLocalServer.removeServer(name)
        server.listen(name)
    server.newConnection.connect(lambda: accept_instance(server, window))
    return server


def accept_instance(server, window):
    """
    Handle a connection from a newly started instance.

    :param server: The QLocalServer.
    :param window: The main window to show.
    """
    connection = server.nextPendingConnection()
    if connection is None:
        return
    connection.disconnected.connect(connection.deleteLater)

    def read_command():
        command = bytes(connection.readAll()).strip()
        connection.write(GREETING)
        connection.flush()
        if command == b"show":
            window.show_and_raise()

    connection.readyRead.connect(read_command)
