"""
This module defines the UiContainer class, which serves as a container for the user interface
components of the PyQtPass application.
The class encapsulates the functionality for initializing and managing the different UI elements
such as tree views, the content panel, and filter text boxes. It is designed to abstract
the complexity of UI setup and interactions, thereby promoting a cleaner and more
modular design in the PyQtPass application.
"""

import sys

from PyQt6.QtCore import (
    QModelIndex,
    QRegularExpression,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLineEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from password_panel import PasswordPanel
from utilities import IS_FOLDER_ROLE, PATH_ROLE, filter_pattern


class StoreFilterProxyModel(QSortFilterProxyModel):
    """
    Filters the store tree on the full path of its items and, after a
    content search, on the set of matching entries.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.content_matches = None
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setRecursiveFilteringEnabled(True)

    def set_name_filter(self, text):
        """
        :param text: The search box text; its words match in order.
        """
        self.content_matches = None
        self.setFilterRegularExpression(
            QRegularExpression(
                filter_pattern(text),
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
        )

    def set_content_matches(self, paths):
        """
        Only show these entries, or everything again for None.

        :param paths: Set of entry paths, or None.
        """
        self.content_matches = paths
        self.setFilterRegularExpression(QRegularExpression(""))
        self.invalidate()

    def filterAcceptsRow(
        self, source_row, source_parent
    ):  # pylint: disable=invalid-name
        """Accept rows whose path matches the current filter."""
        index = self.sourceModel().index(source_row, 0, source_parent)
        path = index.data(PATH_ROLE) or index.data() or ""
        if self.content_matches is not None:
            return not index.data(IS_FOLDER_ROLE) and path in self.content_matches
        return self.filterRegularExpression().match(path).hasMatch()


class StoreTreeView(QTreeView):
    """
    The tree of the password store. Clicking empty space deselects, and
    entries and folders can be dragged onto folders to move them (or copy
    them, with Ctrl held).
    """

    move_requested = pyqtSignal(str, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def mousePressEvent(self, event):  # pylint: disable=invalid-name
        """Deselect when clicking outside of the items."""
        if not self.indexAt(event.position().toPoint()).isValid():
            self.clearSelection()
            self.setCurrentIndex(QModelIndex())
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):  # pylint: disable=invalid-name
        """Only accept drags from this tree."""
        if event.source() is self:
            super().dragEnterEvent(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # pylint: disable=invalid-name
        """Only accept drags from this tree."""
        if event.source() is self:
            super().dragMoveEvent(event)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):  # pylint: disable=invalid-name
        """
        Translate a drop into a move request; the store does the work and
        the tree is rebuilt, so the model itself is never changed here.
        """
        source = self.currentIndex()
        if event.source() is not self or not source.isValid():
            event.ignore()
            return
        target = self.indexAt(event.position().toPoint())
        if not target.isValid():
            folder = ""
        elif target.data(IS_FOLDER_ROLE):
            folder = target.data(PATH_ROLE)
        else:
            path = target.data(PATH_ROLE)
            folder = path.rsplit("/", 1)[0] if "/" in path else ""
        copy = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.ignore()
        self.move_requested.emit(source.data(PATH_ROLE), folder, copy)


class UiContainer(QWidget):
    """
    User Interface Container Class
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self):
        super().__init__()
        self.tree_model = None

        self.panel = None
        self.text_edit = None
        self.tree_view = None
        self.tray_icon = None

        self.central_widget = QWidget()
        self.filter_text_box = QLineEdit()
        self.filter_text_box.setClearButtonEnabled(True)
        self.proxy_model = StoreFilterProxyModel()

        self.filter_text_box.setPlaceholderText(
            self.tr("Type here to filter passwords...")
        )
        self.filter_text_box.textChanged.connect(self.filter_tree_view)

    def setup_ui(self, splitter):
        """
        Set up the User Interface items
        :param splitter:
        """
        if not self.tree_model:
            print("No tree model")
            sys.exit(1)
        self.proxy_model.setSourceModel(self.tree_model)

        self.tree_view = StoreTreeView()
        self.tree_view.setModel(self.proxy_model)

        top_layout = QVBoxLayout()
        top_layout.addWidget(self.filter_text_box)
        top_layout.addWidget(self.tree_view)

        top_widget = QWidget()
        top_widget.setLayout(top_layout)

        self.panel = PasswordPanel()
        self.text_edit = self.panel.text_browser

        splitter.addWidget(top_widget)
        splitter.addWidget(self.panel)

        splitter.setSizes([200, 400])  # Adjust these values as needed

        vbox = QVBoxLayout()
        vbox.addWidget(splitter)
        self.central_widget.setLayout(vbox)

    def filter_tree_view(self, text):
        """
        Filter the tree view on the text in the filter text box: its words
        are matched literally and in order against the full path.

        :param text: Text to filter the tree view.
        """
        self.proxy_model.set_name_filter(text)
        if text:
            self.tree_view.expandAll()
