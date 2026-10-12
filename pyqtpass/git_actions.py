"""
Pulling and pushing the password store with git on a worker thread.

Like the other main window mixins, the strings are translated in the
context of the main window class.
"""

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import QMessageBox

from pyqtpass.tasks import run_task


class GitActionsMixin:
    """
    The git actions of QtPassGUI.
    """

    def git_enabled(self):
        """
        :return: True when git support is on and the store is a git repository.
        """
        return self.store.git_enabled()

    def update_git_actions(self):
        """
        Show the git actions only when git is used for this store.
        """
        enabled = self.git_enabled()
        for name in ("git_pull", "git_push"):
            self.actions[name].setVisible(enabled)
            self.actions[name].setEnabled(enabled and self.git_task is None)

    def run_git(self, function, done_message, failed_title, refresh=False):
        """
        Run a git operation on a worker thread.

        :param function: Callable(store) returning (success, output).
        :param done_message: Status message on success.
        :param failed_title: Title of the warning on failure.
        :param refresh: Rebuild the tree on success.
        """
        if not self.git_enabled():
            self.show_status(
                QCoreApplication.translate(
                    "QtPassGUI", "Git is not available for this store"
                )
            )
            return
        if self.git_task is not None:
            return
        store = self.store

        def done(result, error):
            self.git_task = None
            self.update_git_actions()
            if self.push_pending:
                self.push_pending = False
                QTimer.singleShot(0, self.auto_push)
            success, output = result if error is None else (False, str(error))
            self.verbose_print(output)
            if success:
                if refresh:
                    self.refresh_tree()
                self.show_status(done_message)
            else:
                QMessageBox.warning(self, failed_title, output)

        self.git_task = run_task(lambda _p, _c: function(store), done, critical=True)
        self.update_git_actions()
        self.show_status(QCoreApplication.translate("QtPassGUI", "Running git..."), 0)

    def on_git_pull(self):
        """
        Update the password store from the remote git repository.
        """
        self.run_git(
            lambda store: store.pull(),
            QCoreApplication.translate("QtPassGUI", "Password store updated"),
            QCoreApplication.translate("QtPassGUI", "Git pull failed"),
            refresh=True,
        )

    def on_git_push(self):
        """
        Push local changes of the password store to the remote git repository.
        """
        self.run_git(
            lambda store: store.push(),
            QCoreApplication.translate("QtPassGUI", "Password store pushed"),
            QCoreApplication.translate("QtPassGUI", "Git push failed"),
        )

    def auto_push(self):
        """
        Push local changes automatically when the auto push setting is on.
        """
        if not self.git_enabled() or not self.settings.effective("auto_push"):
            return
        if self.git_task is not None:
            # Push once the running pull or push is done.
            self.push_pending = True
            return
        self.run_git(
            lambda store: store.push(only_with_remote=True),
            QCoreApplication.translate("QtPassGUI", "Pushed changes to remote"),
            QCoreApplication.translate("QtPassGUI", "Git push failed"),
        )
