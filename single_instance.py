"""
Keeps PyQtPass to one window per user: a second start asks the running
instance to show itself, like the QtPass single application.
"""

import getpass

from PyQt6.QtNetwork import QLocalServer, QLocalSocket


def single_instance_name():
    """:return: The local server name shared by this user's instances."""
    return f"PyQtPass-{getpass.getuser()}"


def activate_running_instance():
    """
    Ask an already running PyQtPass to show its window.

    :return: True when another instance was found.
    """
    socket = QLocalSocket()
    socket.connectToServer(single_instance_name())
    if not socket.waitForConnected(500):
        return False
    socket.write(b"show\n")
    socket.flush()
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


def listen_for_instances(window):
    """
    Show the window when another instance is started.

    :param window: The main window.
    :return: The QLocalServer, which has to be kept referenced.
    """
    server = QLocalServer(window)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(single_instance_name()):
        # A crashed instance can leave its socket behind; nobody answered
        # on it, so it is stale.
        QLocalServer.removeServer(single_instance_name())
        server.listen(single_instance_name())
    server.newConnection.connect(lambda: accept_instance(server, window))
    return server


def accept_instance(server, window):
    """
    Handle a connection from a newly started instance.

    :param server: The QLocalServer.
    :param window: The main window to show.
    """
    connection = server.nextPendingConnection()
    if connection is not None:
        connection.disconnected.connect(connection.deleteLater)
    window.show_and_raise()
