"""
This module provides a PyQt6 GUI for 'pass', the standard Unix password
manager. It is a Python port of QtPass: it shows the password store in a
tree view, the selected entry with its fields and one-time password in a
content panel, and talks to gpg and git directly to change the store.

Dependencies:
    - PyQt6
    - Markdown
    - gpg (and optionally git and qrencode) on the PATH
"""

import argparse
import html
import os
import sys
import time
import weakref

import markdown
from PyQt6.QtCore import (
    Qt,
    QCoreApplication,
    QByteArray,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QFont,
    QFontDatabase,
    QIcon,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QSystemTrayIcon,
)

from pyqtpass import __version__, executor
from pyqtpass.clipboard_actions import ClipboardActionsMixin
from pyqtpass.config_dialog import ConfigDialog
from pyqtpass.entry import parse_entry
from pyqtpass.git_actions import GitActionsMixin
from pyqtpass.settings_manager import SettingsManager
from pyqtpass.store_setup import (
    apply_executables,
    configured_store_dir,
    ensure_store,
    make_store,
)
from pyqtpass.single_instance import activate_running_instance, listen_for_instances
from pyqtpass import tasks
from pyqtpass.tasks import run_task
from pyqtpass.templates import template_fields_for
from pyqtpass.store_actions import StoreActionsMixin
from pyqtpass.ui_container import UiContainer
from pyqtpass.window_actions import WindowActionsMixin
from pyqtpass.utilities import (
    create_tree_model,
    get_icon_path,
    get_item_folder,
    get_item_full_path,
    get_lato_font_path,
    is_folder_item,
    set_locale,
)


class QtPassGUI(
    ClipboardActionsMixin,
    GitActionsMixin,
    StoreActionsMixin,
    WindowActionsMixin,
    QMainWindow,
):
    """
    PyQt GUI class for the password store.
    """

    # pylint: disable=too-many-instance-attributes,too-many-public-methods

    process_output = pyqtSignal(str, int, str)

    def __init__(self, verbose=False):
        super().__init__()
        self.splitter = None
        self.ui = UiContainer()
        self.verbose = verbose
        self.settings = SettingsManager()
        self.actions = {}
        self.profile_combo = None
        self.output_dock = None
        self.output_view = None
        self.copied_text = ""
        self.opening_path = None
        self.git_task = None
        self.search_task = None
        self.push_pending = False
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.setSingleShot(True)
        self.clipboard_timer.timeout.connect(self.clear_clipboard)
        self.panel_timer = QTimer(self)
        self.panel_timer.setSingleShot(True)
        self.panel_timer.timeout.connect(self.clear_panel)
        self.store = None
        self.menu_peek = False
        self.alt_alone = False
        problems = apply_executables(self.settings)
        self.load_store()
        self.init_ui()
        self.restore_settings()
        self.process_output.connect(self.append_process_output)
        self.output_listener = make_output_listener(self)
        executor.add_listener(self.output_listener)
        for problem in problems:
            self.show_status(problem, 15000)
        if self.git_enabled() and self.settings.effective("git_pull_on_start"):
            QTimer.singleShot(0, self.on_git_pull)

    def get_store_dir(self):
        """
        :return: The store directory of the currently selected profile.
        """
        return configured_store_dir(self.settings)

    def new_store(self, store_dir):
        """
        :param store_dir: The store directory.
        :return: A PasswordStore for it with the current settings.
        """
        return make_store(self.settings, store_dir)

    def load_store(self):
        """
        Open the password store of the current profile.
        """
        self.store = self.new_store(self.get_store_dir())
        if not os.path.isdir(self.store.store_dir):
            os.makedirs(self.store.store_dir, exist_ok=True)
        self.ui.tree_model = create_tree_model(self.store)

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """
        Handles the close event of the window.

        This method is overridden to control the behavior of the application on window close.
        Depending on the 'close_is_hide' setting, the window will either be hidden or closed.

        Note: The method name 'closeEvent' is a Qt convention and does not follow the PEP8
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
            executor.remove_listener(self.output_listener)
            QApplication.instance().removeEventFilter(self)
            event.accept()
            QApplication.instance().quit()

    def save_settings(self):
        """
        Saves the current settings of the application.

        This method stores the current window geometry, toolbar and dock
        state and splitter sizes into the settings so that these can be
        restored the next time the application is started.
        """
        self.settings.set("window_geometry", self.saveGeometry())
        self.settings.set("window_state", self.saveState())
        self.settings.set("splitter_sizes", self.splitter.sizes())
        self.settings.set(
            "show_process_output", self.actions["process_output"].isChecked()
        )
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
        state = self.settings.get("window_state")
        if isinstance(state, QByteArray):
            self.restoreState(state)
        self.splitter.setSizes(self.settings.get("splitter_sizes"))
        self.output_dock.setVisible(bool(self.settings.get("show_process_output")))

    # Tree helpers

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
        if index.isValid() and self.ui.tree_view.selectionModel().isSelected(index):
            return index
        return None

    def selected_entry_path(self, index=None):
        """
        :param index: The index in the proxy model, or None for the selection.
        :return: The path of the entry at index, or None for a folder or none.
        """
        if index is None:
            index = self.current_index()
        if index is None:
            return None
        item = self.item_from_index(index)
        if item is None or is_folder_item(item):
            return None
        return get_item_full_path(item)

    def required_entry_path(self, index=None, message=None):
        """
        :param index: The index in the proxy model, or None for the selection.
        :param message: What to say when no entry is selected.
        :return: The path of the entry at index, or None after saying so.
        """
        path = self.selected_entry_path(index)
        if path is None:
            self.show_status(message or self.tr("No password selected"))
        return path

    def selected_folder(self, index=None):
        """
        :param index: The index in the proxy model, or None for the selection.
        :return: The folder of the item at index, '' for the root.
        """
        if index is None:
            index = self.current_index()
        if index is None:
            return ""
        return get_item_folder(self.item_from_index(index)).strip("/")

    # Showing entries

    def open_item(self, index):
        """
        Decrypt the entry at index in the background and show it in the
        content panel.

        :param index: The index of the item in the proxy model.
        """
        path = self.selected_entry_path(index)
        if path is None:
            return
        self.opening_path = path
        store = self.store
        self.show_status(self.tr("Decrypting {}").format(path))
        run_task(
            lambda _progress, _cancelled: store.get_key(path),
            lambda data, error: self.on_item_decrypted(path, data, error),
        )

    def on_item_decrypted(self, path, data, error):
        """
        Show a decrypted entry, unless another one was selected meanwhile.

        :param path: The entry path.
        :param data: The decrypted contents.
        :param error: An exception when decryption failed.
        """
        if path != self.opening_path:
            return
        self.opening_path = None
        if error is not None:
            message = self.tr("Could not decrypt {}: {}").format(path, error)
            self.ui.panel.show_message(f"<i>{html.escape(message)}</i>")
            self.show_status(self.tr("Could not decrypt this password entry"))
            return
        self.show_key_content(data, path)
        self.verbose_print(f"Opened: {path}")
        self.statusBar().clearMessage()
        if self.settings.get("always_copy_to_clipboard"):
            self.copy_text_to_clipboard(data.split("\n", 1)[0])

    def show_key_content(self, key_data, path=""):
        """
        Display decrypted key data in the content panel, honouring the
        display settings and the panel autoclear timeout.

        :param key_data: The decrypted contents of a password entry.
        :param path: The entry path, for the template of its folder.
        """
        folder = path.rsplit("/", 1)[0] if "/" in path else ""
        content = parse_entry(
            key_data,
            template_fields_for(self.store.store_dir, folder, self.settings),
            self.settings.get("use_template")
            and self.settings.get("template_all_fields"),
        )
        self.ui.panel.show_entry(content, self.settings)
        if self.settings.get("autoclear_panel"):
            self.panel_timer.start(int(self.settings.get("panel_timeout")) * 1000)

    def clear_panel(self):
        """
        Clear the content panel, called by the panel autoclear timer.
        """
        self.ui.panel.clear()

    # Tree events

    def on_item_double_clicked(self, index):
        """
        Handle the double click event on an item in the tree view.

        :param index: The index of the double-clicked item in the proxy model.
        """
        if self.selected_entry_path(index) is not None:
            self.edit_item(index)

    def on_selection_changed(self, selected, _deselected):
        """
        Handle the selection change event in the tree view.

        :param selected: The new selection.
        :param _deselected: The old selection (unused)
        """
        indexes = selected.indexes()
        if not indexes:
            self.opening_path = None
            self.show_welcome()
            return
        item = self.item_from_index(indexes[0])
        self.verbose_print(f"Selected: {get_item_full_path(item)}")
        if is_folder_item(item):
            self.opening_path = None
            self.ui.panel.clear()
        elif self.settings.get("select_is_open"):
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
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if self.isVisible():
                self.hide()
            else:
                self.show_and_raise()

    def show_and_raise(self):
        """Show the window and bring it to the front."""
        self.show()
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized
            | Qt.WindowState.WindowActive
        )
        self.raise_()
        self.activateWindow()

    def verbose_print(self, *args, **kwargs):
        """
        Prints messages to the console if verbose mode is enabled.
        """
        if self.verbose:
            print(*args, **kwargs)

    def show_status(self, message, timeout=5000):
        """
        Show a message in the status bar.

        :param message: The message to show.
        :param timeout: Milliseconds to show it for.
        """
        self.statusBar().showMessage(message, timeout)
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

        tray_menu = QMenu(self)
        open_action = QAction(self.tr("Open PyQtPass"), self)
        open_action.triggered.connect(self.show_and_raise)
        exit_action = QAction(self.tr("Exit"), self)
        exit_action.triggered.connect(self.exit)
        tray_menu.addAction(open_action)
        tray_menu.addAction(self.actions["add"])
        tray_menu.addAction(self.actions["show_menu_bar"])
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)
        self.ui.tray_icon.setContextMenu(tray_menu)

    def refresh_tree(self):
        """Rebuild the tree, keeping the filter and expanded folders."""
        expanded = set()
        model = self.ui.proxy_model
        for row in range(model.rowCount()):
            self.collect_expanded(model.index(row, 0), expanded)
        self.ui.tree_model = create_tree_model(self.store)
        self.ui.proxy_model.setSourceModel(self.ui.tree_model)
        for row in range(model.rowCount()):
            self.restore_expanded(model.index(row, 0), expanded)
        if self.ui.filter_text_box.text():
            self.ui.tree_view.expandAll()

    def collect_expanded(self, index, expanded):
        """Collect the paths of the expanded folders below index."""
        if self.ui.tree_view.isExpanded(index):
            expanded.add(get_item_full_path(self.item_from_index(index)))
            for row in range(self.ui.proxy_model.rowCount(index)):
                self.collect_expanded(
                    self.ui.proxy_model.index(row, 0, index), expanded
                )

    def restore_expanded(self, index, expanded):
        """Expand the folders below index whose paths were collected."""
        if get_item_full_path(self.item_from_index(index)) in expanded:
            self.ui.tree_view.setExpanded(index, True)
            for row in range(self.ui.proxy_model.rowCount(index)):
                self.restore_expanded(
                    self.ui.proxy_model.index(row, 0, index), expanded
                )

    # Dialogs

    def open_config_dialog(self):
        """
        Opens the configuration dialog.
        """
        dialog = ConfigDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_settings()

    def apply_settings(self):
        """
        Apply the current settings to the running application.
        """
        for problem in apply_executables(self.settings):
            self.show_status(problem, 15000)
        if self.settings.get("use_tray_icon"):
            self.ui.tray_icon.show()
        else:
            self.ui.tray_icon.hide()

        flags = self.windowFlags()
        if self.settings.get("always_on_top"):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        if flags != self.windowFlags():
            self.setWindowFlags(flags)
            self.show()

        self.update_search_placeholder()
        self.update_profile_combo()
        self.apply_menu_bar_setting()
        self.switch_store_if_needed(always=True)

    # Search

    def update_search_placeholder(self):
        """Say in the search box whether Enter searches the content."""
        if self.settings.get("use_grep_search"):
            self.ui.filter_text_box.setPlaceholderText(
                self.tr("Filter passwords, Enter searches the content (regex)")
            )
        else:
            self.ui.filter_text_box.setPlaceholderText(
                self.tr("Type here to filter passwords...")
            )

    def on_search_return(self):
        """Search the content of all entries when content search is on."""
        pattern = self.ui.filter_text_box.text()
        if not self.settings.get("use_grep_search") or not pattern:
            index = self.ui.proxy_model.index(0, 0)
            if index.isValid():
                self.ui.tree_view.setCurrentIndex(index)
            return
        if self.search_task is not None:
            self.search_task.cancel()
        store = self.store
        self.show_status(self.tr("Searching..."), 0)
        task = None

        def done(results, error):
            if task is not self.search_task:
                return  # an older, cancelled search: its results are stale
            self.search_task = None
            if error is not None:
                self.show_status(self.tr("Search failed: {}").format(error))
                return
            if pattern != self.ui.filter_text_box.text():
                return
            self.ui.proxy_model.set_content_matches(set(results))
            self.ui.tree_view.expandAll()
            lines = sum(len(found) for found in results.values())
            if results:
                self.show_status(
                    self.tr("Found {} matches in {} entries").format(
                        lines, len(results)
                    )
                )
            else:
                self.show_status(self.tr("No matches found."))

        task = run_task(
            lambda progress, cancelled: store.search(
                pattern, progress=progress, cancelled=cancelled
            ),
            done,
        )
        self.search_task = task

    # Profiles

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
        self.actions["profile"].setVisible(bool(profiles))

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

    def switch_store_if_needed(self, always=False):
        """
        Reopen the password store when the current profile points elsewhere.

        :param always: Reopen it with the current settings (backend, git,
                       signing keys) even when the folder did not change.
        """
        new_dir = os.path.abspath(os.path.expanduser(self.get_store_dir()))
        if new_dir == self.store.store_dir:
            if always:
                self.store = self.new_store(new_dir)
                self.update_git_actions()
            return
        store = self.new_store(new_dir)
        if not store.is_initialised():
            QMessageBox.warning(
                self,
                self.tr("Store not initialised"),
                self.tr(
                    "{} is not a password store yet. Use Users to choose the "
                    "keys to encrypt it with."
                ).format(new_dir),
            )
            os.makedirs(new_dir, exist_ok=True)
        self.store = store
        self.refresh_tree()
        self.ui.panel.clear()
        self.update_git_actions()
        self.show_status(self.tr("Switched to password store {}").format(new_dir))

    # Process output

    def append_process_output(self, label, returncode, output):
        """
        Add a finished command to the process output panel.

        :param label: The command line.
        :param returncode: Its exit status.
        :param output: What it printed (never decrypted data).
        """
        colour = "palette(text)" if returncode == 0 else "#c0392b"
        escaped = output.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.output_view.appendHtml(
            f"<b>$ {label.replace('&', '&amp;').replace('<', '&lt;')}</b>"
        )
        if escaped:
            self.output_view.appendHtml(f'<pre style="color:{colour}">{escaped}</pre>')
        self.output_view.ensureCursorVisible()

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

        self.ui.panel.show_message(
            markdown.markdown(self.tr("""# Welcome to PyQtPass!

PyQtPass is your password manager. With it, managing passwords is a breeze.

- Generate secure passwords
- Manage passwords with ease
- Built-in one-time passwords (TOTP)
- Clipboard integration for quick access
- Supports multiple password stores and sharing them with others

Check out the [documentation](https://github.com/annejan/PyQtPass/) for more info.
""")),
            QFont(lato, 16),
        )

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
        self.ui.tree_view.move_requested.connect(self.on_move_requested)
        self.ui.filter_text_box.returnPressed.connect(self.on_search_return)
        self.ui.panel.copy_requested.connect(self.copy_text_to_clipboard)
        self.ui.panel.edit_requested.connect(self.edit_item)

        self.setCentralWidget(self.ui.central_widget)

        self.setGeometry(300, 300, 768, 596)
        self.setWindowTitle(self.tr("PyQtPass"))

        self.setup_output_dock()
        self.setup_actions()
        self.setup_toolbar()
        self.setup_menus()
        self.show_welcome()
        self.update_git_actions()
        self.update_search_placeholder()

        QApplication.instance().installEventFilter(self)
        self.setup_tray_icon()
        if self.settings.get("use_tray_icon"):
            self.ui.tray_icon.show()

        if self.settings.get("start_minimized"):
            QTimer.singleShot(0, self.hide)

        if self.settings.get("always_on_top"):
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)


def make_output_listener(window):
    """
    Create an executor listener forwarding commands to the window's process
    output panel. It holds the window weakly, so a closed window is not
    kept alive or called into.

    :param window: The main window.
    :return: The listener.
    """
    window_ref = weakref.ref(window)

    def listener(label, returncode, output):
        target = window_ref()
        if target is not None:
            target.process_output.emit(label, returncode, output)

    return listener


def finish_tasks_on_quit():
    """
    Let running git and store changes finish before quitting, showing a
    window with a way out when that takes more than a moment.
    """
    if not tasks.running():
        return
    dialog = QProgressDialog(
        QCoreApplication.translate(
            "QtPassGUI", "Finishing git and password store changes..."
        ),
        QCoreApplication.translate("QtPassGUI", "Quit now"),
        0,
        0,
    )
    dialog.setWindowTitle("PyQtPass")
    dialog.setAutoClose(False)
    start = time.monotonic()

    def idle():
        if not dialog.isVisible() and time.monotonic() - start > 1:
            dialog.show()
        QApplication.processEvents()
        return dialog.wasCanceled()

    tasks.wait_for_all(idle=idle)
    dialog.close()


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
    parser.add_argument(
        "--new-instance",
        action="store_true",
        help="Start even when PyQtPass is already running.",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("PyQtPass")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("IJHack")
    app.setWindowIcon(QIcon(get_icon_path()))
    set_locale()
    if not args.new_instance and activate_running_instance():
        return
    settings = SettingsManager()
    apply_executables(settings)
    if not ensure_store(settings):
        return
    window = QtPassGUI(verbose=args.verbose)
    server = listen_for_instances(window)  # pylint: disable=unused-variable
    window.show()
    app.aboutToQuit.connect(finish_tasks_on_quit)
    code = app.exec()
    if tasks.stuck():
        # A worker thread did not stop even after its commands were ended;
        # destroying its QThread would abort, so leave without cleanup.
        # Settings were saved when the window closed.
        os._exit(code)  # pylint: disable=protected-access
    sys.exit(code)


if __name__ == "__main__":
    main()
