"""
Keeps PyQtPass to one window per user: a second start asks the running
instance to show itself, and to search for the text given on the command
line, like the QtPass single application.

On POSIX the socket lives in the user's private runtime directory (on
Linux $XDG_RUNTIME_DIR, mode 0700), not in the shared temporary directory,
so another account cannot put a listener there first. Elsewhere (Windows
pipe names are global) the name carries a random token kept in the user's
own configuration folder, which other accounts cannot read or guess. A
running instance answers with a greeting holding that token, so only a real
PyQtPass instance of this user is taken for one; a stale or foreign socket
never stops PyQtPass from starting.
"""

import getpass
import os
import secrets

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

TIMEOUT_MS = 1000
# Longest command a running instance reads; a search text is short.
MAX_COMMAND = 4096
_token = {}


def instance_token():
    """
    :return: This user's random single-instance token, created on first use
             in the private configuration folder.
    """
    if "value" in _token:
        return _token["value"]
    folder = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    path = os.path.join(folder, "instance-token")
    token = ""
    try:
        with open(path, "r", encoding="ascii") as handle:
            token = handle.read().strip()
    except OSError:
        pass
    if len(token) != 32 or not token.isalnum():
        token = secrets.token_hex(16)
        try:
            os.makedirs(folder, exist_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                handle.write(token)
        except OSError:
            pass  # this run still works; the next one makes a new token
    _token["value"] = token
    return token


def greeting():
    """:return: What a running instance answers with."""
    return b"PyQtPass " + instance_token().encode() + b"\n"


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
    return f"PyQtPass-{getpass.getuser()}-{instance_token()[:16]}"


def ask_running_instance(command):
    """
    Send a command to a running instance.

    :param command: b"show", b"ping" or b"search " and the UTF-8 text.
    :return: True when a PyQtPass instance answered.
    """
    socket = QLocalSocket()
    socket.connectToServer(single_instance_name())
    if not socket.waitForConnected(TIMEOUT_MS):
        return False
    socket.write(command + b"\n")
    socket.flush()
    answer = b""
    expected = greeting()
    while len(answer) < len(expected) and socket.waitForReadyRead(TIMEOUT_MS):
        answer += bytes(socket.readAll())
    socket.disconnectFromServer()
    return answer.startswith(expected)


def activate_running_instance(search=""):
    """
    Ask an already running PyQtPass to show its window, and to search.

    :param search: Text for the search box, may be ''.
    :return: True when another instance answered.
    """
    # One line: a newline would end the command.
    text = " ".join(search.split()).encode("utf-8")
    if not text:
        return ask_running_instance(b"show")
    return ask_running_instance(b"search " + text[: MAX_COMMAND - 8])


def listen_for_instances(window):
    """
    Show the window, and search, when another instance is started.

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
    received = bytearray()
    answered = []

    def read_command():
        if answered:
            return
        received.extend(bytes(connection.readAll()))
        if b"\n" not in received and len(received) <= MAX_COMMAND:
            return  # the rest of the command is still on its way
        answered.append(True)
        command = bytes(received).split(b"\n", 1)[0][:MAX_COMMAND].strip()
        connection.write(greeting())
        connection.flush()
        if command == b"show":
            window.show_and_raise()
        elif command.startswith(b"search "):
            window.search_for(command[7:].decode("utf-8", "ignore"))

    connection.readyRead.connect(read_command)
