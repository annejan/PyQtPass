"""
Opening the password store with the configured backend, Git and signing
settings, and setting it up with the first-run wizard when it is new.
"""

from PyQt6.QtWidgets import QDialog

import git_utils
import gpg_utils
from first_run_wizard import FirstRunWizard
from gpgid_trust import GenerationRecord
from password_store import PasswordStore
from real_pass import RealPassStore, find_pass
from settings_manager import profile_options


def configured_store_dir(settings):
    """
    :param settings: The SettingsManager.
    :return: The store directory of the current profile, or the configured
             password store when no profile is selected.
    """
    return settings.store_dir()


def make_store(settings, store_dir=None):
    """
    Open a password store with the backend, git and signing settings of the
    current profile.

    :param settings: The SettingsManager.
    :param store_dir: The store directory, the configured one when None.
    :return: A PasswordStore, or a RealPassStore when pass is to be used.
    """
    options = {
        "gpg_bin": gpg_utils.which_gpg(),
        "use_git": bool(settings.effective("use_git")),
        "signing_keys": settings.signing_keys(),
        "record": GenerationRecord(settings.generation_record_path()),
    }
    store_dir = store_dir or configured_store_dir(settings)
    pass_bin = find_pass(settings.get("pass_executable"))
    if settings.get("use_pass") and pass_bin:
        return RealPassStore(store_dir, pass_bin, **options)
    return PasswordStore(store_dir, **options)


def apply_executables(settings):
    """
    Point the gpg and git helpers at the configured executables.

    :param settings: The SettingsManager.
    """
    gpg_utils.set_gpg_executable(settings.get("gpg_executable"))
    git_utils.set_git_executable(settings.get("git_executable"))


def ensure_store(settings):
    """
    Run the first-run wizard when the configured store is not set up.

    :param settings: The SettingsManager.
    :return: False when the user cancelled the wizard.
    """
    store = make_store(settings)
    if store.is_initialised():
        return True
    wizard = FirstRunWizard(
        store.store_dir, store_factory=lambda d: make_store(settings, d)
    )
    if wizard.exec() != QDialog.DialogCode.Accepted:
        return False
    store_dir = wizard.store_dir()
    profiles = settings.get("profiles") or {}
    current = settings.get("current_profile")
    if current and current in profiles:
        profiles = dict(profiles)
        profiles[current] = {**profile_options(profiles[current]), "path": store_dir}
        settings.set("profiles", profiles)
    else:
        settings.set("pass_store", store_dir)
    settings.set("use_git", wizard.use_git())
    settings.save()
    return True
