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
import markdown
from PyQt5.QtCore import (
    Qt,
    QByteArray,
    QTimer,
)
from PyQt5.QtGui import QIcon, QFontDatabase, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QMainWindow,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QMessageBox,
    QInputDialog,
)

import git_utils
from settings_manager import SettingsManager
from config_dialog import ConfigDialog
from ui_container import UiContainer
from edit_password_window import EditPasswordDialog
from users_dialog import UsersDialog
from gpg_utils import which_gpg
from utilities import (
    format_key_html,
    get_icon_path,
    get_lato_font_path,
    set_locale,
    create_tree_model,
    get_item_folder,
    get_item_full_path,
    set_widgets_enabled,
)

__version__ = "0.2.0"

DEFAULT_STORE_DIR = "~/.password-store"


class QtPassGUI(QMainWindow):
    """
    PyQt GUI class for the passpy password store.
    """

    # pylint: disable=too-many-instance-attributes,too-many-public-methods

    def __init__(self, verbose=False):
        super().__init__()
        set_locale()
        self.splitter = None
        self.ui = UiContainer()
        self.verbose = verbose
        self.settings = SettingsManager()
        self.actions = {}
        self.profile_combo = None
        self.copied_text = ""
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.setSingleShot(True)
        self.clipboard_timer.timeout.connect(self.clear_clipboard)
        self.panel_timer = QTimer(self)
        self.panel_timer.setSingleShot(True)
        self.panel_timer.timeout.connect(self.clear_panel)
        self.store = None
        self.load_store()
        self.init_ui()
        self.restore_settings()
        if self.git_enabled() and self.settings.get("git_pull_on_start"):
            self.on_git_pull()

    def get_store_dir(self):
        """
        :return: The store directory of the currently selected profile.
        """
        profiles = self.settings.get("profiles") or {}
        current = self.settings.get("current_profile")
        if current and current in profiles:
            return profiles[current]
        return DEFAULT_STORE_DIR

    def load_store(self):
        """
        Open the password store of the current profile.
        """
        try:
            self.store = passpy.Store(
                gpg_bin=which_gpg(), store_dir=self.get_store_dir()
            )
            self.ui.tree_model = create_tree_model(self.store)
        except passpy.StoreNotInitialisedError as e:
            print(self.tr("Error initializing passpy store: {}").format(e))
            sys.exit(1)

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
        if (
            self.settings.get("close_is_hide")
            and self.ui.tray_icon
            and self.ui.tray_icon.isVisible()
        ):
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

    def item_from_index(self, index):
        """
        :param index: An index of the proxy model.
        :return: The corresponding item in the source model.
        """
        source_index = self.ui.proxy_model.mapToSource(index)
        return self.ui.tree_model.itemFromIndex(source_index)

    def current_index(self):
        """
        :return: The currently selected index in the tree view or None.
        """
        index = self.ui.tree_view.currentIndex()
        if index.isValid():
            return index
        return None

    def open_item(self, index):
        """
        Show the content of the item at index in the content panel.

        :param index: The index of the item in the proxy model.
        """
        item = self.item_from_index(index)
        path = get_item_full_path(item)

        set_widgets_enabled(self, False)
        try:
            password = self.store.get_key(path)
            self.show_key_content(password)
            self.verbose_print(f"Opened: {path}")
            set_widgets_enabled(self, True)
            if self.settings.get("always_copy_to_clipboard"):
                self.copy_text_to_clipboard(password.split("\n", 1)[0])
        except FileNotFoundError:
            self.verbose_print(
                f"Cannot retrieve key for a directory or non-existent key: {path}"
            )
            set_widgets_enabled(self, True)

    def show_key_content(self, key_data):
        """
        Display decrypted key data in the content panel, honouring the
        hide password/content settings and the panel autoclear timeout.

        :param key_data: The decrypted contents of a password entry.
        """
        if self.settings.get("hide_content"):
            hidden = self.tr("Content hidden")
            self.ui.text_edit.setHtml(f"<i>{hidden}</i>")
        else:
            fixed_font = QFont("monospace", 10, QFont.Normal)
            fixed_font.setFixedPitch(True)
            self.ui.text_edit.setFont(fixed_font)
            self.ui.text_edit.setHtml(
                format_key_html(key_data, self.settings.get("hide_password"))
            )
        if self.settings.get("autoclear_panel"):
            self.panel_timer.start(int(self.settings.get("panel_timeout")) * 1000)

    def clear_panel(self):
        """
        Clear the content panel, called by the panel autoclear timer.
        """
        self.ui.text_edit.clear()

    def copy_text_to_clipboard(self, text):
        """
        Copy text to the clipboard and start the autoclear timer.

        :param text: The text to copy.
        """
        QApplication.clipboard().setText(text)
        self.copied_text = text
        if self.settings.get("autoclear_clipboard"):
            timeout = int(self.settings.get("clipboard_timeout"))
            self.clipboard_timer.start(timeout * 1000)
            self.show_status(
                self.tr("Copied to clipboard, clearing in {} seconds").format(timeout)
            )
        else:
            self.show_status(self.tr("Copied to clipboard"))

    def clear_clipboard(self):
        """
        Clear the clipboard if it still holds the text we copied.
        """
        clipboard = QApplication.clipboard()
        if clipboard.text() == self.copied_text:
            clipboard.clear()
            self.show_status(self.tr("Clipboard cleared"))
        self.copied_text = ""

    def copy_password(self, index=None):
        """
        Copy the password (first line) of the item at index to the clipboard.

        :param index: The index in the proxy model, or None for the selection.
        """
        if index is None:
            index = self.current_index()
        if index is None:
            self.show_status(self.tr("No password selected"))
            return
        path = get_item_full_path(self.item_from_index(index))
        try:
            password = self.store.get_key(path).split("\n", 1)[0]
        except FileNotFoundError:
            self.show_status(self.tr("No password selected"))
            return
        self.copy_text_to_clipboard(password)

    def on_item_double_clicked(self, index):
        """
        Handle the double click event on an item in the tree view.

        :param index: The index of the double-clicked item in the proxy model.
        """
        self.edit_item(index)

    def on_selection_changed(self, selected, _deselected):
        """
        Handle the selection change event in the tree view.

        :param selected: The new selection.
        :param _deselected: The old selection (unused)
        """
        indexes = selected.indexes()
        if indexes:
            item = self.item_from_index(indexes[0])
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

    def show_status(self, message):
        """
        Show a message in the status bar.

        :param message: The message to show.
        """
        self.statusBar().showMessage(message, 5000)
        self.verbose_print(message)

    def exit(self):
        """
        Really quit that shit.
        But save first <3
        :return:
        """
        self.save_settings()
        QApplication.instance().quit()

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
        exit_action = QAction(self.tr("Exit"), self)
        exit_action.triggered.connect(self.exit)
        tray_menu.addAction(open_action)
        tray_menu.addAction(exit_action)
        self.ui.tray_icon.setContextMenu(tray_menu)

    def refresh_tree(self):
        """Refresh the tree_view"""
        self.ui.tree_model = create_tree_model(self.store)
        self.ui.proxy_model.setSourceModel(self.ui.tree_model)
        self.ui.tree_view.setModel(self.ui.proxy_model)

    def git_enabled(self):
        """
        :return: True when git support is on and the store is a git repository.
        """
        return self.settings.get("use_git") and git_utils.is_git_repo(
            self.store.store_dir
        )

    def update_git_actions(self):
        """
        Enable or disable the git actions based on the current settings.
        """
        enabled = self.git_enabled()
        self.actions["git_pull"].setEnabled(enabled)
        self.actions["git_push"].setEnabled(enabled)

    def on_git_pull(self):
        """
        Update the password store from the remote git repository.
        """
        if not self.git_enabled():
            self.show_status(self.tr("Git is not available for this store"))
            return
        set_widgets_enabled(self, False)
        success, output = git_utils.git_pull(self.store.store_dir)
        set_widgets_enabled(self, True)
        self.verbose_print(output)
        if success:
            self.refresh_tree()
            self.show_status(self.tr("Password store updated"))
        else:
            QMessageBox.warning(self, self.tr("Git pull failed"), output)

    def on_git_push(self):
        """
        Push local changes of the password store to the remote git repository.
        """
        if not self.git_enabled():
            self.show_status(self.tr("Git is not available for this store"))
            return
        set_widgets_enabled(self, False)
        success, output = git_utils.git_push(self.store.store_dir)
        set_widgets_enabled(self, True)
        self.verbose_print(output)
        if success:
            self.show_status(self.tr("Password store pushed"))
        else:
            QMessageBox.warning(self, self.tr("Git push failed"), output)

    def auto_push(self):
        """
        Push local changes automatically when the auto push setting is on.
        """
        if not self.git_enabled() or not self.settings.get("auto_push"):
            return
        if not git_utils.has_remote(self.store.store_dir):
            return
        success, output = git_utils.git_push(self.store.store_dir)
        self.verbose_print(output)
        if success:
            self.show_status(self.tr("Pushed changes to remote"))
        else:
            QMessageBox.warning(self, self.tr("Git push failed"), output)

    def open_config_dialog(self):
        """
        Opens the configuration dialog.
        """
        dialog = ConfigDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.apply_settings()

    def apply_settings(self):
        """
        Apply the current settings to the running application.
        """
        if self.settings.get("use_tray_icon"):
            self.ui.tray_icon.show()
        else:
            self.ui.tray_icon.hide()

        flags = self.windowFlags()
        if self.settings.get("always_on_top"):
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        if flags != self.windowFlags():
            self.setWindowFlags(flags)
            self.show()

        self.update_profile_combo()
        self.update_git_actions()
        self.switch_store_if_needed()

    def open_users_dialog(self, index=None):
        """
        Open the users dialog to select the GPG keys for a folder.

        :param index: The index in the proxy model, or None for the selection.
        """
        folder = ""
        if index is None:
            index = self.current_index()
        if index is not None:
            folder = get_item_folder(self.item_from_index(index)).strip("/")
        dialog = UsersDialog(self.store, folder, self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_tree()
            self.show_status(
                self.tr("Re-encrypted passwords in {}").format(folder or "/")
            )
            self.auto_push()

    def show_context_menu(self, position):
        """Create context menu"""
        context_menu = QMenu(self.ui.tree_view)

        add_action = context_menu.addAction(self.tr("Add"))
        add_action.triggered.connect(lambda: self.add_item(index))

        index = self.ui.tree_view.indexAt(position)
        if not index.isValid():
            index = None
            users_action = context_menu.addAction(self.tr("Users"))
            users_action.triggered.connect(lambda: self.open_users_dialog(None))
            context_menu.exec_(self.ui.tree_view.mapToGlobal(position))
            return

        copy_action = context_menu.addAction(self.tr("Copy password"))
        open_action = context_menu.addAction(self.tr("Open"))
        edit_action = context_menu.addAction(self.tr("Edit"))
        rename_action = context_menu.addAction(self.tr("Rename"))
        delete_action = context_menu.addAction(self.tr("Delete"))
        users_action = context_menu.addAction(self.tr("Users"))

        copy_action.triggered.connect(lambda: self.copy_password(index))
        open_action.triggered.connect(lambda: self.open_item(index))
        edit_action.triggered.connect(lambda: self.edit_item(index))
        rename_action.triggered.connect(lambda: self.rename_item(index))
        delete_action.triggered.connect(lambda: self.delete_item(index))
        users_action.triggered.connect(lambda: self.open_users_dialog(index))

        context_menu.exec_(self.ui.tree_view.mapToGlobal(position))

    def add_item(self, index=None):
        """Add item"""
        folder = ""
        if index is None:
            index = self.current_index()
        if index is not None:
            item = self.item_from_index(index)
            if item:
                folder = get_item_folder(item)
        folder = folder.lstrip("/")

        name, ok = QInputDialog.getText(
            self, self.tr("New password"), self.tr("Enter password name:"), text=folder
        )
        if not ok or not name or name.endswith("/"):
            return
        dialog = EditPasswordDialog(self.store, name, name.split("/")[-1], create=True)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_tree()
            self.show_status(self.tr("Added password {}").format(name))
            self.auto_push()

    def edit_item(self, index=None):
        """Edit item"""
        if index is None:
            index = self.current_index()
        if index is None:
            self.show_status(self.tr("No password selected"))
            return
        item = self.item_from_index(index)
        path = get_item_full_path(item)
        try:
            dialog = EditPasswordDialog(self.store, path, item.text())
        except FileNotFoundError:
            self.verbose_print(
                f"Cannot retrieve key for a directory or non-existent key: {path}"
            )
            return
        if dialog.exec_() == QDialog.Accepted:
            if self.settings.get("select_is_open") and index == self.current_index():
                self.open_item(index)
            self.show_status(self.tr("Saved password {}").format(path))
            self.auto_push()

    def rename_item(self, index=None):
        """Rename item"""
        if index is None:
            index = self.current_index()
        if index is None:
            self.show_status(self.tr("No password selected"))
            return
        path = get_item_full_path(self.item_from_index(index))
        new_path, ok = QInputDialog.getText(
            self, self.tr("Rename Item"), self.tr("New Path:"), text=path
        )
        if ok and new_path and new_path != path:
            try:
                self.store.move_path(path, new_path)
            except (FileNotFoundError, FileExistsError) as e:
                QMessageBox.warning(self, self.tr("Rename failed"), str(e))
                return
            self.refresh_tree()
            self.show_status(self.tr("Renamed {} to {}").format(path, new_path))
            self.auto_push()
        else:
            self.verbose_print("Rename cancelled")

    def delete_item(self, index=None):
        """Delete item"""
        if index is None:
            index = self.current_index()
        if index is None:
            self.show_status(self.tr("No password selected"))
            return
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
                self.show_status(self.tr("Deleted {}").format(path))
                self.auto_push()
            except FileNotFoundError as e:
                print(f"Failure to delete {path}: {e}")
        else:
            self.verbose_print("Deletion cancelled")

    def update_profile_combo(self):
        """
        Fill the profile selector with the configured profiles.
        """
        profiles = self.settings.get("profiles") or {}
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(sorted(profiles))
        current = self.settings.get("current_profile")
        if current in profiles:
            self.profile_combo.setCurrentText(current)
        self.profile_combo.blockSignals(False)
        self.profile_combo.setVisible(bool(profiles))

    def on_profile_changed(self, name):
        """
        Switch to another password store profile.

        :param name: The name of the selected profile.
        """
        if name == self.settings.get("current_profile"):
            return
        self.settings.set("current_profile", name)
        self.settings.save()
        self.switch_store_if_needed()

    def switch_store_if_needed(self):
        """
        Reopen the password store when the current profile points elsewhere.
        """
        new_dir = os.path.expanduser(self.get_store_dir())
        if new_dir == self.store.store_dir:
            return
        try:
            self.store = passpy.Store(gpg_bin=which_gpg(), store_dir=new_dir)
        except passpy.StoreNotInitialisedError as e:
            QMessageBox.warning(
                self,
                self.tr("Store not initialised"),
                self.tr("Cannot open password store {}: {}").format(new_dir, e),
            )
            return
        self.refresh_tree()
        self.update_git_actions()
        self.show_status(self.tr("Switched to password store {}").format(new_dir))

    def make_action(self, text, icon, slot, shortcut=None):
        """
        Create a QAction with a themed icon.

        :param text: The visible text of the action.
        :param icon: Tuple of (icon theme name, QStyle standard pixmap fallback).
        :param slot: The slot to connect the action to.
        :param shortcut: Optional key sequence.
        :return: The created QAction.
        """
        theme_name, standard_pixmap = icon
        qicon = QIcon.fromTheme(theme_name)
        if qicon.isNull():
            qicon = self.style().standardIcon(standard_pixmap)
        action = QAction(qicon, text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.ui.tree_view.addAction(action)
        return action

    def setup_actions(self):
        """
        Create the actions shared by the toolbar and the menus.
        """
        self.actions["add"] = self.make_action(
            self.tr("Add password"),
            ("list-add", QStyle.SP_FileDialogNewFolder),
            self.add_item,
            "Ctrl+N",
        )
        self.actions["edit"] = self.make_action(
            self.tr("Edit password"),
            ("document-edit", QStyle.SP_FileDialogDetailedView),
            self.edit_item,
            "Ctrl+E",
        )
        self.actions["delete"] = self.make_action(
            self.tr("Delete password"),
            ("edit-delete", QStyle.SP_TrashIcon),
            self.delete_item,
            "Del",
        )
        self.actions["copy"] = self.make_action(
            self.tr("Copy password to clipboard"),
            ("edit-copy", QStyle.SP_FileDialogContentsView),
            self.copy_password,
            "Ctrl+C",
        )
        self.actions["users"] = self.make_action(
            self.tr("Users"),
            ("system-users", QStyle.SP_FileDialogInfoView),
            self.open_users_dialog,
        )
        self.actions["git_pull"] = self.make_action(
            self.tr("Update from git remote"),
            ("go-down", QStyle.SP_ArrowDown),
            self.on_git_pull,
            "F5",
        )
        self.actions["git_push"] = self.make_action(
            self.tr("Push to git remote"),
            ("go-up", QStyle.SP_ArrowUp),
            self.on_git_push,
        )
        self.actions["config"] = self.make_action(
            self.tr("Configuration"),
            ("preferences-system", QStyle.SP_ComputerIcon),
            self.open_config_dialog,
        )

    def setup_toolbar(self):
        """
        Create the main toolbar with the shared actions and profile selector.
        """
        toolbar = self.addToolBar(self.tr("Main"))
        toolbar.setMovable(False)
        for name in ("add", "edit", "delete", "copy"):
            toolbar.addAction(self.actions[name])
        toolbar.addSeparator()
        for name in ("users", "git_pull", "git_push"):
            toolbar.addAction(self.actions[name])
        toolbar.addSeparator()
        toolbar.addAction(self.actions["config"])

        self.profile_combo = QComboBox(toolbar)
        self.profile_combo.currentTextChanged.connect(self.on_profile_changed)
        toolbar.addWidget(self.profile_combo)
        self.update_profile_combo()

    def setup_menus(self):
        """
        Create the menu bar.
        """
        menubar = self.menuBar()
        system_menu = menubar.addMenu(self.tr("System"))
        system_menu.addAction(self.actions["config"])
        system_menu.addAction(self.actions["users"])
        system_menu.addSeparator()
        system_menu.addAction(self.actions["git_pull"])
        system_menu.addAction(self.actions["git_push"])
        system_menu.addSeparator()
        quit_action = QAction(self.tr("Quit"), self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.exit)
        system_menu.addAction(quit_action)

        help_menu = menubar.addMenu(self.tr("Help"))
        about_action = QAction(self.tr("About PyQtPass"), self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        about_qt_action = QAction(self.tr("About Qt"), self)
        about_qt_action.triggered.connect(QApplication.instance().aboutQt)
        help_menu.addAction(about_qt_action)

    def show_about(self):
        """
        Show the about dialog.
        """
        QMessageBox.about(
            self,
            self.tr("About PyQtPass"),
            self.tr(
                "<b>PyQtPass {}</b><br><br>"
                "A cross-platform GUI for pass, the standard Unix password manager, "
                "written in Python. A port of "
                '<a href="https://qtpass.org/">QtPass</a>.<br><br>'
                "Please report any issues you might have with this software at "
                '<a href="https://github.com/annejan/PyQtPass">GitHub</a>.'
            ).format(__version__),
        )

    def show_welcome(self):
        """
        Show the welcome text in the content panel.
        """
        font_id = QFontDatabase.addApplicationFont(get_lato_font_path())
        if font_id == -1:
            print("Failed to load font. Check the file path.")
            lato = "sans-serif"
        else:
            lato = QFontDatabase.applicationFontFamilies(font_id)[0]

        self.ui.text_edit.setText(markdown.markdown(self.tr("""# Welcome to PyQtPass!

PyQtPass is your password manager. With it, managing passwords is a breeze.

- Generate secure passwords
- Manage passwords with ease
- Clipboard integration for quick access
- Supports multiple password stores

Check out the [documentation](https://github.com/annejan/PyQtPass/) for more info.
""")))
        self.ui.text_edit.setFont(QFont(lato, 16))

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

        self.setCentralWidget(self.ui.central_widget)

        self.setGeometry(300, 300, 768, 596)
        self.setWindowTitle(self.tr("PyQtPass"))

        self.setup_actions()
        self.setup_toolbar()
        self.setup_menus()
        self.show_welcome()
        self.update_git_actions()

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
    parser.add_argument(
        "--version", action="version", version=f"PyQtPass {__version__}"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(get_icon_path()))
    ex = QtPassGUI(verbose=args.verbose)
    ex.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
