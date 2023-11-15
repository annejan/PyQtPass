"""
This module provides a PyQt5 GUI for interfacing with the passpy library, which is a Python
wrapper for the standard Unix password manager 'pass'. It allows users to interact with their
password store through a graphical interface, displaying passwords in a tree view and allowing
password retrieval by double-clicking on a password entry.

Dependencies:
    - PyQt5
    - passpy
    - os
    - sys
"""

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
)


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
        directories, entries = store.list_dir(path)

        for directory in directories:
            dir_name = os.path.basename(directory)
            dir_item = QStandardItem(dir_name)
            dir_item.setFlags(dir_item.flags() & ~Qt.ItemIsEditable)
            parent.appendRow(dir_item)
            add_items(dir_item, os.path.join(path, directory) if path else directory)

        for entry in entries:
            entry_name = os.path.basename(entry)
            entry_item = QStandardItem(entry_name)
            entry_item.setFlags(entry_item.flags() & ~Qt.ItemIsEditable)
            parent.appendRow(entry_item)

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


class QtPassGUI(QMainWindow):
    """
    PyQt GUI class for the passpy password store.
    """

    def __init__(self):
        super().__init__()
        self.proxy_model = None
        self.filter_text_box = None
        self.text_edit = None
        self.tree_view = None
        self.store = passpy.Store()
        self.tree_model = create_tree_model(self.store)
        self.init_ui()

    def on_item_double_clicked(self, index):
        """
        Handle the double click event on an item in the tree view.

        :param index: The index of the double-clicked item in the tree model.
        """
        item = self.tree_model.itemFromIndex(index)
        path = get_item_full_path(item)
        try:
            password = self.store.get_key(path)
            self.text_edit.setText(password)
            print(f"Double-clicked on: {path}")
        except FileNotFoundError:
            print(f"Cannot retrieve key for a directory or non-existent key: {path}")
            # self.textEdit.clear()
            # self.textEdit.setText(f"Item at path '{path}' is not a file or does not exist.")

    def on_selection_changed(self, selected, deselected):
        """
        Handle the selection change event in the tree view.

        :param selected: The new selection.
        :param deselected: The old selection.
        """
        indexes = selected.indexes()
        if indexes:
            item = self.tree_model.itemFromIndex(indexes[0])
            print(f"Selected: {get_item_full_path(item)}")

    def filter_tree_view(self, text):
        """
        Filter the tree view based on the text input in the filter text box.

        :param text: Text to filter the tree view.
        """
        # Use a regular expression to filter the tree view
        self.proxy_model.setFilterRegularExpression(text)

    def init_ui(self):
        """
        Initialize the user interface.
        """
        # Create a splitter to divide the tree view and the text area
        splitter = QSplitter(self)

        # Create a layout for the top part of the splitter (search box and tree view)
        top_layout = QVBoxLayout()

        # Create the filter text box
        self.filter_text_box = QLineEdit()
        self.filter_text_box.setPlaceholderText("Type here to filter passwords...")
        self.filter_text_box.textChanged.connect(self.filter_tree_view)
        top_layout.addWidget(self.filter_text_box)

        # Create the proxy model for filtering and set the source model
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.tree_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setRecursiveFilteringEnabled(True)  # Requires PyQt5 >= 5.10

        # Create the tree view
        self.tree_view = QTreeView(splitter)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setModel(self.proxy_model)

        # Add the tree view to the top layout and then to the splitter
        top_layout.addWidget(self.tree_view)
        top_widget = QWidget()  # Create a container widget for the top layout
        top_widget.setLayout(top_layout)
        splitter.addWidget(top_widget)

        # Connect signals to slots
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        self.tree_view.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )

        self.text_edit = QTextEdit(splitter)

        self.text_edit.setText(
            "PyQtPass is a GUI for pass, the standard Unix password manager.\n\n"
            "Please report any issues you might have with this software."
        )

        splitter.setSizes([200, 400])
        vbox = QVBoxLayout()
        vbox.addWidget(splitter)

        central_widget = QWidget()
        central_widget.setLayout(vbox)
        self.setCentralWidget(central_widget)

        self.setGeometry(300, 300, 768, 596)
        self.setWindowTitle("Python QtPass")


def main():
    """
    Main function to start the PyQt application.
    """
    app = QApplication(sys.argv)
    if sys.platform == "win32":
        icon_path = 'artwork/icon.ico'
    elif sys.platform == "darwin":
        icon_path = 'artwork/icon.icns'
    else:
        icon_path = 'artwork/icon.svg'
    icon_full_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), icon_path)
    app.setWindowIcon(QIcon(icon_full_path))
    ex = QtPassGUI()
    ex.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
