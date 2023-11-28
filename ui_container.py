"""
This module defines the UiContainer class, which serves as a container for the user interface (UI) components
of the PyQtPass application. The class encapsulates the functionality for initializing and managing the
different UI elements such as tree views, text edits, and filter text boxes. It is designed to abstract the
complexity of UI setup and interactions, thereby promoting a cleaner and more modular design in the PyQtPass
application. UiContainer facilitates the creation and configuration of UI elements, ensuring a consistent and
efficient UI setup process.
"""

import sys
from PyQt5.QtCore import Qt, QSortFilterProxyModel
from PyQt5.QtWidgets import QTreeView, QTextEdit, QVBoxLayout, QLineEdit, QWidget


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
