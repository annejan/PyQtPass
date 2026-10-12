"""
Simple functionality not directly / only used for PyQtPass
"""

import html
import os
import re
import sys

from PyQt6.QtCore import Qt, QLocale, QTranslator, QCoreApplication, QLibraryInfo
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt6.QtWidgets import QApplication, QStyle, QWidget

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
IS_FOLDER_ROLE = Qt.ItemDataRole.UserRole + 2

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


def get_lato_font_path():
    """
    :return: str path of Lato TrueType Font file
    """
    return os.path.join(os.path.dirname(__file__), "artwork/fonts/Lato-Regular.ttf")


def get_localization_dir():
    """
    :return: str path of the directory holding the compiled translations.
    """
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "localization")


_translators = []


def set_locale():
    """
    Install the translations for the system locale.

    The translators are kept referenced, otherwise Python would garbage
    collect them and Qt would silently fall back to English.
    """
    system = QLocale.system()
    language_code = system.name()
    app_translator = QTranslator()
    # Tries every UI language, each with and without its country, so a
    # language-only translation (localization_it) serves it_IT too.
    if app_translator.load(system, "localization", "_", get_localization_dir()):
        QCoreApplication.installTranslator(app_translator)
        _translators.append(app_translator)
    qt_translator = QTranslator()
    if qt_translator.load(
        f"qtbase_{language_code}",
        QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
    ):
        QCoreApplication.installTranslator(qt_translator)
        _translators.append(qt_translator)


def create_tree_model(store):
    """
    Create a tree model from the password store.

    :param store: The password store instance from passpy.
    :return: QStandardItemModel populated with the directories and entries.
    """
    model = QStandardItemModel()
    folder_icon = QIcon.fromTheme("folder")
    if folder_icon.isNull() and QApplication.instance() is not None:
        folder_icon = QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_DirIcon
        )
    entry_icon = QIcon(get_icon_path())

    def add_items(parent, path):
        """
        Recursively add items to the tree model.

        :param parent: The parent item in the tree model.
        :param path: The current path of items being added.
        """
        try:
            directories, entries = store.list_dir(path)
            for directory in directories:
                dir_path = f"{path}/{directory}" if path else directory
                dir_item = QStandardItem(directory)
                dir_item.setFlags(dir_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                dir_item.setIcon(folder_icon)
                dir_item.setData(dir_path, PATH_ROLE)
                dir_item.setData(True, IS_FOLDER_ROLE)
                parent.appendRow(dir_item)
                add_items(dir_item, dir_path)

            for entry in entries:
                entry_item = QStandardItem(entry)
                entry_item.setFlags(
                    (entry_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    & ~Qt.ItemFlag.ItemIsDropEnabled
                )
                entry_item.setIcon(entry_icon)
                entry_item.setData(f"{path}/{entry}" if path else entry, PATH_ROLE)
                entry_item.setData(False, IS_FOLDER_ROLE)
                parent.appendRow(entry_item)
        except (OSError, ValueError) as e:
            print(f"Error accessing {path}: {e}")

    add_items(model.invisibleRootItem(), "")
    return model


def is_folder_item(item):
    """
    :param item: An item of the tree model.
    :return: True when the item is a folder.
    """
    is_folder = item.data(IS_FOLDER_ROLE)
    if is_folder is None:
        return item.rowCount() > 0
    return bool(is_folder)


def get_item_folder(item):
    """
    Find the folder for a given item in the tree.

    :param item: The item in the tree.
    :return: Full path as a string.
    """
    path = get_item_full_path(item)
    if not is_folder_item(item):  # get folder for leaf node
        path = path[: -len(item.text())]
    if not path.endswith("/"):
        return path + "/"
    return path


def get_item_full_path(item):
    """
    Construct the full path for a given item in the tree.

    :param item: The item in the tree.
    :return: Full path as a string.
    """
    stored = item.data(PATH_ROLE)
    if stored:
        return stored
    path_list = [item.text()]
    while item.parent():
        item = item.parent()
        path_list.insert(0, item.text())
    return "/".join(path_list)


URL_PATTERN = re.compile(r"(https?://[^\s<]+)")
WEB_URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)


def is_web_url(value):
    """
    :param value: A field value.
    :return: True when the value is a single http(s) address.
    """
    return bool(WEB_URL_PATTERN.match(value.strip()))


HIDDEN_PASSWORD = "●" * 8


def format_key_html(key_data, hide_password=False):
    """
    Format decrypted password data as HTML for the content panel.

    The first line (the password) can be hidden and URLs are turned into
    clickable links, like QtPass does.

    :param key_data: The decrypted contents of a password entry.
    :param hide_password: When True, replace the first line with dots.
    :return: HTML string for display in a QTextBrowser.
    """
    lines = key_data.rstrip("\n").split("\n")
    if lines and hide_password:
        lines[0] = HIDDEN_PASSWORD
    escaped_lines = [
        URL_PATTERN.sub(r'<a href="\1">\1</a>', html.escape(line)) for line in lines
    ]
    return "<br>".join(escaped_lines)


def filter_pattern(text):
    """
    Turn the search box text into a regular expression: its words are
    matched literally, in order, with anything in between, like QtPass.

    :param text: The search box text.
    :return: A regular expression string.
    """
    return ".*".join(re.escape(word) for word in text.split())


def set_widgets_enabled(container, enabled):
    """
    Enable or disable widget elements
    :param container: widget container
    :param enabled: bool:
    """
    for widget in container.findChildren(QWidget):
        widget.setEnabled(enabled)
