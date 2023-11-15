"""
This module provides a PyQt5 GUI for interfacing with the passpy library, which is a Python
wrapper for the standard Unix password manager 'pass'. It allows users to interact with their
password store through a graphical interface, displaying passwords in a tree view and allowing
password retrieval by double-clicking on a password entry.

Dependencies:
    - PyQt5
    - passpy
"""

import argparse
import os
import sys

import passpy
from PyQt5.QtCore import Qt, QSortFilterProxyModel
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QSplitter,
    QTreeView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QSystemTrayIcon,
    QMenu,
    QAction,
)

from settingsmanager import SettingsManager

PLATFORM_ICONS = {
    "win32": "artwork/icon.ico",
    "darwin": "artwork/icon.icns",
    "default": "artwork/icon.svg",  # Assuming 'linux' for all other platforms
}


def create_tree_model(store):
    """
    Create a tree model from the password store.

    :param store: The password store instance from passpy.
    :return: QStandardItemModel populated with the directories and entries.
    """
    model = QStandardItemModel()

    def add_items(parent, path):
        """
        Recursively add items to the tree model.

        :param parent: The parent item in the tree model.
        :param path: The current path of items being added.
        """
        try:
            directories, entries = store.list_dir(path)
            for directory in directories:
                dir_name = os.path.basename(directory)
                dir_item = QStandardItem(dir_name)
                dir_item.setFlags(dir_item.flags() & ~Qt.ItemIsEditable)
                parent.appendRow(dir_item)
                add_items(
                    dir_item, os.path.join(path, directory) if path else directory
                )

            for entry in entries:
                entry_name = os.path.basename(entry)
                entry_item = QStandardItem(entry_name)
                entry_item.setFlags(entry_item.flags() & ~Qt.ItemIsEditable)
                parent.appendRow(entry_item)
        except (FileNotFoundError, PermissionError) as e:
            print(f"Error accessing {path}: {e}")

    add_items(model.invisibleRootItem(), "")
    return model


def get_item_full_path(item):
    """
    Construct the full path for a given item in the tree.

    :param item: The item in the tree.
    :return: Full path as a string.
    """
    path_list = [item.text()]
    while item.parent():
        item = item.parent()
        path_list.insert(0, item.text())
    return "/".join(path_list)


class UiContainer:
    """
    User Interface Container Class
    """

    def __init__(self):
        self.tree_model = None

        self.text_edit = None
        self.tree_view = None
        self.tray_icon = None

        self.central_widget = QWidget()
        self.filter_text_box = QLineEdit()
        self.proxy_model = QSortFilterProxyModel()

        self.filter_text_box.setPlaceholderText("Type here to filter passwords...")
        self.filter_text_box.textChanged.connect(self.filter_tree_view)

    def setup_ui(self, splitter):
        """
        Set up the User Interface items
        :param splitter:
        """
        if not self.tree_model:
            print("No tree nodel")
            sys.exit(1)
        self.proxy_model.setSourceModel(self.tree_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setRecursiveFilteringEnabled(True)  # Requires PyQt5 >= 5.10

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setModel(self.proxy_model)

        top_layout = QVBoxLayout()
        top_layout.addWidget(self.filter_text_box)
        top_layout.addWidget(self.tree_view)

        top_widget = QWidget()
        top_widget.setLayout(top_layout)

        self.text_edit = QTextEdit()

        splitter.addWidget(top_widget)
        splitter.addWidget(self.text_edit)

        splitter.setSizes([200, 400])  # Adjust these values as needed

        vbox = QVBoxLayout()
        vbox.addWidget(splitter)
        self.central_widget.setLayout(vbox)

    def filter_tree_view(self, text):
        """
        Filter the tree view based on the text input in the filter text box.
        Uses a regular expression to filter the tree view.

        :param text: Text to filter the tree view.
        """
        #
        self.proxy_model.setFilterRegularExpression(text)


class QtPassGUI(QMainWindow):
    """
    PyQt GUI class for the passpy password store.
    """

    def __init__(self, verbose=False):
        super().__init__()
        self.splitter = None
        self.ui = UiContainer()
        self.verbose = verbose
        try:
            self.store = passpy.Store()
            self.ui.tree_model = create_tree_model(self.store)
        except passpy.StoreNotInitialisedError as e:
            print(f"Error initializing passpy store: {e}")
            sys.exit(1)
        self.settings = SettingsManager()
        self.init_ui()
        self.restore_settings()

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """
        Handles the close event of the window.

        This method is overridden to control the behavior of the application on window close.
        Depending on the 'close_is_hide' setting, the window will either be hidden or closed.

        Note: The method name 'closeEvent' is a Qt5 convention and does not follow the PEP8
        snake_case naming style. The Pylint warning for the method name is disabled for this reason.

        Args:
            event: The close event object, which contains information about the close event.
        """
        if self.settings.get_close_is_hide():
            self.hide()
            event.ignore()
        else:
            self.save_settings()
            event.accept()

    def save_settings(self):
        """
        Saves the current settings of the application.

        This method stores the current window geometry and splitter sizes into the settings
        so that these can be restored the next time the application is started.
        """
        self.settings.set_window_geometry(self.saveGeometry())
        self.settings.set_splitter_sizes(self.splitter.sizes())

    def restore_settings(self):
        """
        Restores the saved settings of the application.

        This method retrieves the previously saved window geometry and splitter sizes
        from the settings and applies them to restore the state of the application
        as it was in the previous session.
        """
        self.restoreGeometry(self.settings.get_window_geometry())
        self.splitter.setSizes(self.settings.get_splitter_sizes())

    def on_item_double_clicked(self, index):
        """
        Handle the double click event on an item in the tree view.

        :param index: The index of the double-clicked item in the proxy model.
        """
        # Map the index from the proxy model to the source model
        source_index = self.ui.proxy_model.mapToSource(index)
        # Get the item from the source model
        item = self.ui.tree_model.itemFromIndex(source_index)
        path = get_item_full_path(item)
        try:
            password = self.store.get_key(path)
            self.ui.text_edit.setText(password)
            self.verbose_print(f"Double-clicked on: {path}")
        except FileNotFoundError:
            self.verbose_print(
                f"Cannot retrieve key for a directory or non-existent key: {path}"
            )

    def on_selection_changed(self, selected, _deselected):
        """
        Handle the selection change event in the tree view.

        :param selected: The new selection.
        :param _deselected: The old selection (unused)
        """
        indexes = selected.indexes()
        if indexes:
            source_index = self.ui.proxy_model.mapToSource(indexes[0])
            item = self.ui.tree_model.itemFromIndex(source_index)
            self.verbose_print(f"Selected: {get_item_full_path(item)}")

            # Check if 'select_is_open' setting is True
            if self.settings.get_select_is_open():
                # Perform the double click action or additional logic here
                self.on_item_double_clicked(indexes[0])

    def on_tray_icon_clicked(self, reason):
        """
        Handles the click event on the system tray icon.

        This method is triggered when the tray icon is interacted with, such as
        a single click or double click. Depending on the current visibility of
        the main window, it either hides the window (if visible) or shows it
        (if hidden).

        :param reason: The reason for the trigger, indicating the type of interaction
                       (e.g., single click, double click).
        """
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self.show()

    def verbose_print(self, *args, **kwargs):
        """
        Prints messages to the console if verbose mode is enabled.
        """
        if self.verbose:
            print(*args, **kwargs)

    def exit(self):
        """
        Really quit that shit.
        :return:
        """
        self.save_settings()
        sys.exit(1)

    def init_ui(self):
        """
        Initialize the user interface.
        """
        self.splitter = QSplitter(self)
        self.ui.setup_ui(self.splitter)
        self.ui.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        self.ui.tree_view.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )

        self.ui.text_edit.setText(
            "PyQtPass is a GUI for pass, the standard Unix password manager.\n\n"
            "Please report any issues you might have with this software."
        )

        self.setCentralWidget(self.ui.central_widget)

        self.setGeometry(300, 300, 768, 596)
        self.setWindowTitle("PyQtPass Experimental")

        self.ui.tray_icon = QSystemTrayIcon(QIcon("artwork/icon.svg"), self)
        self.ui.tray_icon.setToolTip("PyQtPass")
        self.ui.tray_icon.activated.connect(self.on_tray_icon_clicked)

        tray_menu = QMenu()
        open_action = QAction("Open PyQtPass", self)
        open_action.triggered.connect(self.show)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit)
        tray_menu.addAction(open_action)
        tray_menu.addAction(exit_action)
        self.ui.tray_icon.setContextMenu(tray_menu)

        self.ui.tray_icon.show()


def main():
    """
    Main function to start the PyQtPass application.
    """
    parser = argparse.ArgumentParser(
        description="PyQtPass: A GUI for the pass password manager."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Increase output verbosity."
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    platform = sys.platform if sys.platform in PLATFORM_ICONS else "default"
    icon_path = PLATFORM_ICONS[platform]
    app.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), icon_path)))
    ex = QtPassGUI(verbose=args.verbose)
    ex.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
