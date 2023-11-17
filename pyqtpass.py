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
from PyQt5.QtCore import Qt, QSortFilterProxyModel, QByteArray, QTimer
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
    QMessageBox,
    QInputDialog,
)

from settingsmanager import SettingsManager
from configdialog import ConfigDialog

PLATFORM_ICONS = {
    "win32": "artwork/icon.ico",
    "darwin": "artwork/icon.icns",
    "default": "artwork/icon.svg",
}


def get_icon_path():
    """
    Get correct icon path for platform.

    :return: str path of icon.
    """
    platform = sys.platform if sys.platform in PLATFORM_ICONS else "default"
    icon_path = PLATFORM_ICONS[platform]
    return os.path.join(os.path.dirname(__file__), icon_path)


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
        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)

        top_layout = QVBoxLayout()
        top_layout.addWidget(self.filter_text_box)
        top_layout.addWidget(self.tree_view)

        top_widget = QWidget()
        top_widget.setLayout(top_layout)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)

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


def set_widgets_enabled(container, enabled):
    """
    Enable or disable widget elements
    :param container: widget container
    :param enabled: bool:
    """
    for widget in container.findChildren(QWidget):
        widget.setEnabled(enabled)


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
        if self.settings.get("close_is_hide"):
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
        self.settings.set("window_geometry", self.saveGeometry())
        self.settings.set("splitter_sizes", self.splitter.sizes())
        self.settings.save()

    def restore_settings(self):
        """
        Restores the saved settings of the application.

        This method retrieves the previously saved window geometry and splitter sizes
        from the settings and applies them to restore the state of the application
        as it was in the previous session.
        """
        geometry = self.settings.get("window_geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        self.splitter.setSizes(self.settings.get("splitter_sizes"))

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
        set_widgets_enabled(self, False)
        try:
            password = self.store.get_key(path)
            self.ui.text_edit.setText(password)
            self.verbose_print(f"Double-clicked on: {path}")
        except FileNotFoundError:
            self.verbose_print(
                f"Cannot retrieve key for a directory or non-existent key: {path}"
            )
        set_widgets_enabled(self, True)

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
            if self.settings.get("select_is_open"):
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
        But save first <3
        :return:
        """
        self.save_settings()
        sys.exit(1)

    def setup_tray_icon(self):
        """
        Setup and enable trayicon
        """
        self.ui.tray_icon = QSystemTrayIcon(QIcon(get_icon_path()), self)
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

    def open_config_dialog(self):
        """
        Opens the configuration dialog.
        """
        dialog = ConfigDialog()
        dialog.exec_()
        if self.settings.get("use_tray_icon"):
            self.ui.tray_icon.show()
        else:
            self.ui.tray_icon.hide()

        if self.settings.get("always_on_top"):
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)

    def show_context_menu(self, position):
        """Create context menu"""
        context_menu = QMenu(self.ui.tree_view)

        index = self.ui.tree_view.indexAt(position)
        if not index.isValid():
            return  # No item under the cursor, might need to add New or something there?

        open_action = context_menu.addAction("Open")
        edit_action = context_menu.addAction("Edit")
        rename_action = context_menu.addAction("Rename")
        delete_action = context_menu.addAction("Delete")

        open_action.triggered.connect(lambda: self.on_item_double_clicked(index))
        edit_action.triggered.connect(lambda: self.edit_item(index))
        rename_action.triggered.connect(lambda: self.rename_item(index))
        delete_action.triggered.connect(lambda: self.delete_item(index))

        context_menu.exec_(self.ui.tree_view.mapToGlobal(position))

    def edit_item(self, index):
        """TODO Edit item"""
        self.on_item_double_clicked(index)

    def rename_item(self, index):
        """Rename item"""
        source_index = self.ui.proxy_model.mapToSource(index)
        item = self.ui.tree_model.itemFromIndex(source_index)
        path = get_item_full_path(item)
        new_path, ok = QInputDialog.getText(self, "Rename Item", "New Path:", text=path)
        if ok and new_path:
            self.store.move_path(path, new_path)
            item.setText(new_path)  ## TODO move ?
        else:
            self.verbose_print("Rename cancelled")

    def delete_item(self, index):
        """Delete item"""
        source_index = self.ui.proxy_model.mapToSource(index)
        item = self.ui.tree_model.itemFromIndex(source_index)
        path = get_item_full_path(item)

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete {path}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.verbose_print(f"Deleting {path}")
            try:
                self.store.remove_path(path, True)
                source_model = self.ui.proxy_model.sourceModel()
                source_model.removeRow(source_index.row(), source_index.parent())
            except FileNotFoundError as e:
                print(f"Failure to delete {path}: {e}")
        else:
            self.verbose_print("Deletion cancelled")

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
        self.ui.tree_view.customContextMenuRequested.connect(self.show_context_menu)

        self.ui.text_edit.setText(
            "PyQtPass is a GUI for pass, the standard Unix password manager.\n\n"
            "Please report any issues you might have with this software."
        )

        self.setCentralWidget(self.ui.central_widget)

        self.setGeometry(300, 300, 768, 596)
        self.setWindowTitle("PyQtPass Experimental")

        menubar = self.menuBar()
        settings_menu = menubar.addMenu("System")
        settings_action = QAction("Configuration", self)
        settings_action.triggered.connect(self.open_config_dialog)
        settings_menu.addAction(settings_action)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.exit)
        settings_menu.addAction(quit_action)

        self.setup_tray_icon()
        if self.settings.get("use_tray_icon"):
            self.ui.tray_icon.show()

        if self.settings.get("start_minimized"):
            QTimer.singleShot(0, self.hide)

        if self.settings.get("always_on_top"):
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)


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

    app.setWindowIcon(QIcon(get_icon_path()))
    ex = QtPassGUI(verbose=args.verbose)
    ex.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
