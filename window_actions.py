"""
The actions, menus, toolbar and process output dock of the main window.

They live in a mixin to keep the main window module readable; the strings
are translated in the context of the main window class.
"""

import sys

from PyQt6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PyQt6.QtGui import QAction, QFontDatabase, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QPlainTextEdit,
    QStyle,
)


class WindowActionsMixin:
    """
    Builds the actions, menus and toolbar of QtPassGUI.
    """

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
        action.triggered.connect(lambda _checked=False: slot())
        if shortcut:
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.ui.tree_view.addAction(action)
        return action

    def setup_actions(self):
        """
        Create the actions shared by the toolbar and the menus.
        """
        pixmap = QStyle.StandardPixmap
        definitions = {
            "add": (
                QCoreApplication.translate("QtPassGUI", "Add password"),
                ("list-add", pixmap.SP_FileDialogNewFolder),
                self.add_item,
                "Ctrl+N",
            ),
            "add_folder": (
                QCoreApplication.translate("QtPassGUI", "Add folder"),
                ("folder-new", pixmap.SP_FileDialogNewFolder),
                self.add_folder,
                "Ctrl+Shift+N",
            ),
            "edit": (
                QCoreApplication.translate("QtPassGUI", "Edit password"),
                ("document-edit", pixmap.SP_FileDialogDetailedView),
                self.edit_item,
                "Ctrl+E",
            ),
            "rename": (
                QCoreApplication.translate("QtPassGUI", "Rename"),
                ("edit-rename", pixmap.SP_FileDialogDetailedView),
                self.rename_item,
                "F2",
            ),
            "delete": (
                QCoreApplication.translate("QtPassGUI", "Delete password"),
                ("edit-delete", pixmap.SP_TrashIcon),
                self.delete_item,
                "Del",
            ),
            "copy": (
                QCoreApplication.translate("QtPassGUI", "Copy password to clipboard"),
                ("edit-copy", pixmap.SP_FileDialogContentsView),
                self.copy_password,
                "Ctrl+C",
            ),
            "copy_otp": (
                QCoreApplication.translate("QtPassGUI", "Copy OTP code to clipboard"),
                ("chronometer", pixmap.SP_BrowserReload),
                self.copy_otp,
                "Ctrl+Shift+C",
            ),
            "users": (
                QCoreApplication.translate("QtPassGUI", "Users"),
                ("system-users", pixmap.SP_FileDialogInfoView),
                self.open_users_dialog,
                None,
            ),
            "reencrypt": (
                QCoreApplication.translate("QtPassGUI", "Re-encrypt passwords"),
                ("view-refresh", pixmap.SP_BrowserReload),
                self.reencrypt_folder,
                None,
            ),
            "export_key": (
                QCoreApplication.translate("QtPassGUI", "Export my public key..."),
                ("document-export", pixmap.SP_DialogSaveButton),
                self.export_public_key,
                None,
            ),
            "open_folder": (
                QCoreApplication.translate(
                    "QtPassGUI", "Open folder with file manager"
                ),
                ("folder-open", pixmap.SP_DirOpenIcon),
                self.open_store_folder,
                None,
            ),
            "git_pull": (
                QCoreApplication.translate("QtPassGUI", "Update from git remote"),
                ("go-down", pixmap.SP_ArrowDown),
                self.on_git_pull,
                "F5",
            ),
            "git_push": (
                QCoreApplication.translate("QtPassGUI", "Push to git remote"),
                ("go-up", pixmap.SP_ArrowUp),
                self.on_git_push,
                None,
            ),
            "config": (
                QCoreApplication.translate("QtPassGUI", "Configuration"),
                ("preferences-system", pixmap.SP_ComputerIcon),
                self.open_config_dialog,
                None,
            ),
        }
        for name, (text, icon, slot, shortcut) in definitions.items():
            self.actions[name] = self.make_action(text, icon, slot, shortcut)

        close_action = QAction(
            QCoreApplication.translate("QtPassGUI", "Close window"), self
        )
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close)
        self.actions["close"] = close_action
        quit_action = QAction(QCoreApplication.translate("QtPassGUI", "Quit"), self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.triggered.connect(self.exit)
        self.actions["quit"] = quit_action
        menu_bar_action = QAction(
            QCoreApplication.translate("QtPassGUI", "Show menu bar"), self
        )
        menu_bar_action.setCheckable(True)
        menu_bar_action.setShortcut("Ctrl+M")
        menu_bar_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        menu_bar_action.setChecked(bool(self.settings.get("show_menu_bar")))
        menu_bar_action.toggled.connect(self.on_menu_bar_toggled)
        # The window keeps the shortcut working while the menu bar is hidden.
        self.addAction(menu_bar_action)
        self.actions["show_menu_bar"] = menu_bar_action
        self.actions["process_output"] = self.output_dock.toggleViewAction()
        self.actions["process_output"].setText(
            QCoreApplication.translate("QtPassGUI", "Show process output")
        )

    def setup_toolbar(self):
        """
        Create the main toolbar with the shared actions and profile selector.
        """
        toolbar = self.addToolBar(QCoreApplication.translate("QtPassGUI", "Main"))
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        for name in ("add", "add_folder", "edit", "delete", "copy"):
            toolbar.addAction(self.actions[name])
        toolbar.addSeparator()
        for name in ("users", "git_pull", "git_push"):
            toolbar.addAction(self.actions[name])
        toolbar.addSeparator()
        toolbar.addAction(self.actions["config"])

        self.profile_combo = QComboBox(toolbar)
        self.profile_combo.setToolTip(
            QCoreApplication.translate("QtPassGUI", "Profile")
        )
        self.profile_combo.currentTextChanged.connect(self.on_profile_changed)
        self.actions["profile"] = toolbar.addWidget(self.profile_combo)
        self.update_profile_combo()

    def setup_menus(self):
        """
        Create the menu bar.
        """
        menubar = self.menuBar()
        file_menu = menubar.addMenu(QCoreApplication.translate("QtPassGUI", "&File"))
        for name in ("add", "add_folder", "edit", "rename", "delete"):
            file_menu.addAction(self.actions[name])
        file_menu.addSeparator()
        file_menu.addAction(self.actions["copy"])
        file_menu.addAction(self.actions["copy_otp"])
        file_menu.addSeparator()
        file_menu.addAction(self.actions["close"])
        file_menu.addAction(self.actions["quit"])

        store_menu = menubar.addMenu(QCoreApplication.translate("QtPassGUI", "&Store"))
        for name in ("users", "reencrypt", "export_key"):
            store_menu.addAction(self.actions[name])
        store_menu.addSeparator()
        store_menu.addAction(self.actions["git_pull"])
        store_menu.addAction(self.actions["git_push"])
        store_menu.addSeparator()
        store_menu.addAction(self.actions["open_folder"])

        settings_menu = menubar.addMenu(
            QCoreApplication.translate("QtPassGUI", "S&ettings")
        )
        settings_menu.addAction(self.actions["config"])
        settings_menu.addAction(self.actions["process_output"])
        settings_menu.addAction(self.actions["show_menu_bar"])

        help_menu = menubar.addMenu(QCoreApplication.translate("QtPassGUI", "&Help"))
        about_action = QAction(
            QCoreApplication.translate("QtPassGUI", "About PyQtPass"), self
        )
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        about_qt_action = QAction(
            QCoreApplication.translate("QtPassGUI", "About Qt"), self
        )
        about_qt_action.setMenuRole(QAction.MenuRole.AboutQtRole)
        about_qt_action.triggered.connect(QApplication.instance().aboutQt)
        help_menu.addAction(about_qt_action)
        for menu in (file_menu, store_menu, settings_menu, help_menu):
            menu.aboutToHide.connect(lambda: QTimer.singleShot(0, self.end_menu_peek))
        self.apply_menu_bar_setting()

    def on_menu_bar_toggled(self, checked):
        """
        Show or hide the menu bar and remember the choice.

        :param checked: Whether the menu bar is to be shown.
        """
        self.settings.set("show_menu_bar", checked)
        self.settings.save()
        self.apply_menu_bar_setting()

    def apply_menu_bar_setting(self):
        """Show the menu bar as configured; macOS always has its own."""
        shown = bool(self.settings.get("show_menu_bar")) or sys.platform == "darwin"
        self.actions["show_menu_bar"].blockSignals(True)
        self.actions["show_menu_bar"].setChecked(
            bool(self.settings.get("show_menu_bar"))
        )
        self.actions["show_menu_bar"].blockSignals(False)
        self.menu_peek = False
        self.menuBar().setVisible(shown)

    def peek_menu_bar(self):
        """
        Show the hidden menu bar for as long as it is used, after Alt.
        """
        if not self.menuBar().isHidden() or not self.menuBar().actions():
            return
        self.menu_peek = True
        self.menuBar().show()
        if self.isVisible():
            self.menuBar().setActiveAction(self.menuBar().actions()[0])

    def end_menu_peek(self):
        """Hide the menu bar again once no menu of it is open."""
        if self.menu_peek and self.menuBar().activeAction() is None:
            self.apply_menu_bar_setting()

    def eventFilter(self, watched, event):  # pylint: disable=invalid-name
        """
        Alt pressed and released on its own shows a hidden menu bar, like
        QtPass; it hides again when its menus close.
        """
        if event.type() == QEvent.Type.KeyPress:
            self.alt_alone = event.key() == Qt.Key.Key_Alt
        elif (
            event.type() == QEvent.Type.KeyRelease
            and event.key() == Qt.Key.Key_Alt
            and self.alt_alone
            and self.isActiveWindow()
        ):
            self.alt_alone = False
            self.peek_menu_bar()
        elif event.type() == QEvent.Type.MouseButtonPress:
            self.alt_alone = False
        return super().eventFilter(watched, event)

    def setup_output_dock(self):
        """
        Create the dockable process output panel showing what git, gpg and
        qrencode were asked and what they said.
        """
        self.output_dock = QDockWidget(
            QCoreApplication.translate("QtPassGUI", "Process output"), self
        )
        self.output_dock.setObjectName("process_output")
        self.output_view = QPlainTextEdit(self.output_dock)
        self.output_view.setReadOnly(True)
        self.output_view.setMaximumBlockCount(2000)
        self.output_view.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self.output_dock.setWidget(self.output_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.output_dock)
        self.output_dock.hide()
