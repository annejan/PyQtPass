"""
Simple functionality not directly / only used for PyQtPass
"""

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt5.QtWidgets import QWidget

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
                dir_item.setIcon(QIcon.fromTheme("folder"))
                parent.appendRow(dir_item)
                add_items(
                    dir_item, os.path.join(path, directory) if path else directory
                )

            for entry in entries:
                entry_name = os.path.basename(entry)
                entry_item = QStandardItem(entry_name)
                entry_item.setFlags(entry_item.flags() & ~Qt.ItemIsEditable)
                entry_item.setIcon(QIcon(get_icon_path()))
                parent.appendRow(entry_item)
        except (FileNotFoundError, PermissionError) as e:
            print(f"Error accessing {path}: {e}")

    add_items(model.invisibleRootItem(), "")
    return model


def get_item_folder(item):
    """
    Find the folder for a given item in the tree.

    :param item: The item in the tree.
    :return: Full path as a string.
    """
    path = get_item_full_path(item)
    if item.rowCount() == 0:  # get folder for leaf node
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
    path_list = [item.text()]
    while item.parent():
        item = item.parent()
        path_list.insert(0, item.text())
    return "/".join(path_list)


def set_widgets_enabled(container, enabled):
    """
    Enable or disable widget elements
    :param container: widget container
    :param enabled: bool:
    """
    for widget in container.findChildren(QWidget):
        widget.setEnabled(enabled)
