"""
Field templates kept in the password store, compatible with QtPass.

The store root can hold a .templates file with INI-style sections, each a
template name followed by its field names, one per line:

    [website]
    login
    url

    [server]
    user
    host

A folder (or one of its parents) can hold a .default_template file whose
first line names the template its entries use. Without one, the template
from the settings applies. Links are not followed, like elsewhere in the
store.
"""

import os

from pyqtpass.fs_utils import is_link

TEMPLATES_FILE = ".templates"
DEFAULT_TEMPLATE_FILE = ".default_template"


def _read_text(path):
    if is_link(path) or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def parse_templates(text):
    """
    :param text: The contents of a .templates file.
    :return: Dict of template name to its list of field names.
    """
    templates = {}
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            section = name or None
            if section is not None:
                templates.setdefault(section, [])
        elif section is not None and line and not line.startswith("#"):
            templates[section].append(line)
    return templates


def read_templates(store_dir):
    """
    :param store_dir: The store root.
    :return: Dict of template name to field names; empty without a file.
    """
    text = _read_text(os.path.join(store_dir, TEMPLATES_FILE))
    return parse_templates(text) if text else {}


def default_template(store_dir, folder):
    """
    :param store_dir: The store root.
    :param folder: A folder relative to the store root.
    :return: The template named by the nearest .default_template, or ''.
    """
    parts = [part for part in folder.split("/") if part]
    while True:
        text = _read_text(os.path.join(store_dir, *parts, DEFAULT_TEMPLATE_FILE))
        if text:
            name = text.splitlines()[0].strip() if text.splitlines() else ""
            if name and not name.startswith("#"):
                return name
        if not parts:
            return ""
        parts.pop()


def template_fields_for(store_dir, folder, settings):
    """
    :param store_dir: The store root.
    :param folder: The folder of an entry, relative to the store root.
    :param settings: The SettingsManager.
    :return: The field names of the template that applies to the folder.
    """
    name = default_template(store_dir, folder)
    templates = read_templates(store_dir)
    if name in templates:
        return templates[name]
    return settings.template_fields()
