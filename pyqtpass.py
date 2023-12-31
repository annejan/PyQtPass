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
import sys

import passpy
import markdown
from PyQt5.QtCore import (
    Qt,
    QByteArray,
    QTimer,
)
from PyQt5.QtGui import QIcon, QFontDatabase, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QSplitter,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QMessageBox,
    QInputDialog,
)

from settings_manager import SettingsManager
from config_dialog import ConfigDialog
from ui_container import UiContainer
from edit_password_window import EditPasswordDialog
from utilities import (
    get_icon_path,
    get_lato_font_path,
    set_locale,
    create_tree_model,
    get_item_folder,
    get_item_full_path,
    set_widgets_enabled,
)


class QtPassGUI(QMainWindow):
    """
    PyQt GUI class for the passpy password store.
    """

    def __init__(self, verbose=False):
        super().__init__()
        set_locale()
        self.splitter = None
        self.ui = UiContainer()
        self.verbose = verbose
        try:
            self.store = passpy.Store()
            self.ui.tree_model = create_tree_model(self.store)
        except passpy.StoreNotInitialisedError as e:
            print(self.tr("Error initializing passpy store: {}").format(e))
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

    def open_item(self, index):
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
            fixed_font = QFont("monospace", 10, QFont.Normal)
            fixed_font.setFixedPitch(True)
            self.ui.text_edit.setFont(fixed_font)
            self.verbose_print(f"Double-clicked on: {path}")
        except FileNotFoundError:
            self.verbose_print(
                f"Cannot retrieve key for a directory or non-existent key: {path}"
            )
        set_widgets_enabled(self, True)

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
        password_dialog = EditPasswordDialog(self.store, path, item.text())
        password_dialog.exec()

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
                self.open_item(indexes[0])

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
        self.ui.tray_icon.setToolTip(self.tr("PyQtPass"))
        self.ui.tray_icon.activated.connect(self.on_tray_icon_clicked)

        tray_menu = QMenu()
        open_action = QAction(self.tr("Open PyQtPass"), self)
        open_action.triggered.connect(self.show)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit)
        tray_menu.addAction(open_action)
        tray_menu.addAction(exit_action)
        self.ui.tray_icon.setContextMenu(tray_menu)

    def refresh_tree(self):
        """Refresh the tree_view"""
        self.ui.tree_model = create_tree_model(self.store)
        self.ui.proxy_model.setSourceModel(self.ui.tree_model)
        self.ui.tree_view.setModel(self.ui.proxy_model)

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

        add_action = context_menu.addAction(self.tr("Add"))
        add_action.triggered.connect(lambda: self.add_item(index))

        index = self.ui.tree_view.indexAt(position)
        if not index.isValid():
            context_menu.exec_(self.ui.tree_view.mapToGlobal(position))
            return  # No item under the cursor, might need to add New or something there?

        open_action = context_menu.addAction(self.tr("Open"))
        edit_action = context_menu.addAction(self.tr("Edit"))
        rename_action = context_menu.addAction(self.tr("Rename"))
        delete_action = context_menu.addAction(self.tr("Delete"))

        open_action.triggered.connect(lambda: self.on_item_double_clicked(index))
        edit_action.triggered.connect(lambda: self.edit_item(index))
        rename_action.triggered.connect(lambda: self.rename_item(index))
        delete_action.triggered.connect(lambda: self.delete_item(index))

        context_menu.exec_(self.ui.tree_view.mapToGlobal(position))

    def add_item(self, index):
        """Add item"""
        folder = ""
        if index:
            source_index = self.ui.proxy_model.mapToSource(index)
            item = self.ui.tree_model.itemFromIndex(source_index)
            if item:
                folder = get_item_folder(item)
        if folder.startswith("/"):
            folder = folder[1:]

        name, ok = QInputDialog.getText(
            self, self.tr("Item Name"), self.tr("Enter name:")
        )
        if ok and name:
            try:
                if self.store.get_key(folder + name):
                    QMessageBox.warning(
                        self,
                        self.tr("Password exists"),
                        self.tr("Password already exists at: {}").format(folder + name),
                    )
                    return
            except FileNotFoundError:
                self.verbose_print("Password does not exists")
            content, ok = QInputDialog.getText(
                self, self.tr("Item Content"), self.tr("Enter content:")
            )
            if ok:
                self.store.set_key(name, content)
                self.refresh_tree()

    def edit_item(self, index):
        """Edit item"""
        source_index = self.ui.proxy_model.mapToSource(index)
        item = self.ui.tree_model.itemFromIndex(source_index)
        path = get_item_full_path(item)
        set_widgets_enabled(self, False)
        try:
            password = self.store.get_key(path)
            new_content, ok = QInputDialog.getText(
                self, self.tr("Update password"), self.tr("New content:"), text=password
            )
            if ok and new_content:
                self.store.set_key(path, new_content)
            else:
                self.verbose_print("Update password cancelled")
        except FileNotFoundError:
            self.verbose_print(
                f"Cannot retrieve key for a directory or non-existent key: {path}"
            )
        set_widgets_enabled(self, True)

    def rename_item(self, index):
        """Rename item"""
        source_index = self.ui.proxy_model.mapToSource(index)
        item = self.ui.tree_model.itemFromIndex(source_index)
        path = get_item_full_path(item)
        new_path, ok = QInputDialog.getText(
            self, self.tr("Rename Item"), self.tr("New Path:"), text=path
        )
        if ok and new_path:
            self.store.move_path(path, new_path)
            self.refresh_tree()
        else:
            self.verbose_print("Rename cancelled")

    def delete_item(self, index):
        """Delete item"""
        source_index = self.ui.proxy_model.mapToSource(index)
        item = self.ui.tree_model.itemFromIndex(source_index)
        path = get_item_full_path(item)

        reply = QMessageBox.question(
            self,
            self.tr("Confirm Delete"),
            self.tr("Are you sure you want to delete {}?").format(path),
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
        font_id = QFontDatabase.addApplicationFont(
            get_lato_font_path()
        )  # Update the path to the font file
        if font_id == -1:
            print("Failed to load font. Check the file path.")
        else:
            lato = QFontDatabase.applicationFontFamilies(font_id)[0]

        self.splitter = QSplitter(self)
        self.ui.setup_ui(self.splitter)
        self.ui.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        self.ui.tree_view.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )
        self.ui.tree_view.customContextMenuRequested.connect(self.show_context_menu)

        self.ui.text_edit.setText(
            markdown.markdown(
                self.tr(
                    """# Welcome to PyQtPass!

PyQtPass is your password manager. With it, managing passwords is a breeze.

- Generate secure passwords
- Manage passwords with ease
- Clipboard integration for quick access
- Supports multiple password stores

Check out the [documentation](https://github.com/annejan/PyQtPass/) for more info.
"""
                )
            )
        )
        self.ui.text_edit.setFont(QFont(lato, 16))

        self.setCentralWidget(self.ui.central_widget)

        self.setGeometry(300, 300, 768, 596)
        self.setWindowTitle(self.tr("PyQtPass Experimental"))

        menubar = self.menuBar()
        settings_menu = menubar.addMenu(self.tr("System"))
        settings_action = QAction(self.tr("Configuration"), self)
        settings_action.triggered.connect(self.open_config_dialog)
        settings_menu.addAction(settings_action)
        quit_action = QAction(self.tr("Quit"), self)
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
