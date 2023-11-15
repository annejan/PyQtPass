import os
import sys
import passpy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QApplication, QMainWindow, QSplitter, QTreeView, QTextEdit, QVBoxLayout, QWidget


def create_tree_model(store):
    model = QStandardItemModel()

    # Recursively add items to the model
    def add_items(parent, path):
        # Fetch the directories and entries
        directories, entries = store.list_dir(path)

        # Add directories to the model
        for directory in directories:
            # Use only the base name for the directory
            dir_name = os.path.basename(directory)
            dir_item = QStandardItem(dir_name)
            dir_item.setFlags(dir_item.flags() & ~Qt.ItemIsEditable)
            parent.appendRow(dir_item)
            # Recursively add the contents of the directory
            add_items(dir_item, os.path.join(path, directory) if path else directory)

        # Add entries to the model
        for entry in entries:
            # Use only the base name for the entry
            entry_name = os.path.basename(entry)
            entry_item = QStandardItem(entry_name)
            entry_item.setFlags(entry_item.flags() & ~Qt.ItemIsEditable)
            parent.appendRow(entry_item)

    # Start populating the model
    add_items(model.invisibleRootItem(), '')

    return model


def get_item_full_path(item):
    path_list = [item.text()]
    while item.parent():
        item = item.parent()
        path_list.insert(0, item.text())
    return '/'.join(path_list)


class QtPassGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        # Create the model
        self.store = passpy.Store()
        self.tree_model = create_tree_model(self.store)
        self.initUI()

    def on_item_double_clicked(self, index):
        # Get the item that was double-clicked
        item = self.tree_model.itemFromIndex(index)
        path = get_item_full_path(item)
        print(f"Double-clicked on: {path}")
        self.textEdit.setText(self.store.get_key(path))

    def on_selection_changed(self, selected, deselected):
        # Get the currently selected item(s)
        indexes = selected.indexes()
        if indexes:  # If there is at least one item selected
            item = self.tree_model.itemFromIndex(indexes[0])
            print(f"Selected: {get_item_full_path(item)}")

    def initUI(self):
        # Create a splitter to divide the tree view and the text area
        splitter = QSplitter(self)

        # Create the tree view
        self.treeView = QTreeView(splitter)
        self.treeView.setHeaderHidden(True)
        self.treeView.setModel(self.tree_model)

        # Connect the doubleClicked signal to a slot
        self.treeView.doubleClicked.connect(self.on_item_double_clicked)

        # Connect the selectionChanged signal to a slot
        self.treeView.selectionModel().selectionChanged.connect(self.on_selection_changed)

        # Create the text area
        self.textEdit = QTextEdit(splitter)
        self.textEdit.setText("PyQtPass is a GUI for pass, the standard Unix password manager.\n\n"
                              "Please report any issues you might have with this software.")

        # Set the splitter sizes
        splitter.setSizes([200, 400])

        # Create a vertical layout
        vbox = QVBoxLayout()
        vbox.addWidget(splitter)

        # Set the layout to the central widget
        central_widget = QWidget()
        central_widget.setLayout(vbox)
        self.setCentralWidget(central_widget)

        # Set the main window properties
        self.setGeometry(300, 300, 768, 596)
        self.setWindowTitle('Python QtPass')


def main():
    app = QApplication(sys.argv)
    ex = QtPassGUI()
    ex.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
