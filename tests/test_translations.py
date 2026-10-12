"""Checks that every translation can be used where its source is."""

# pylint: disable=missing-function-docstring,import-outside-toplevel

import glob
import os
import re
import string
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS_FILES = sorted(glob.glob(os.path.join(ROOT, "pyqtpass", "localization", "*.ts")))


def placeholders(text):
    """:return: The replacement fields of a str.format string."""
    return [
        field for _, field, _, _ in string.Formatter().parse(text) if field is not None
    ]


@pytest.mark.parametrize("path", TS_FILES, ids=os.path.basename)
def test_translations_format_like_their_source(path):
    root = ET.parse(path).getroot()
    assert root.get("language")
    for message in root.iter("message"):
        source = message.findtext("source") or ""
        translation = message.find("translation")
        if translation is None or translation.get("type") or not translation.text:
            continue
        count = len(placeholders(source))
        args = [f"<{index}>" for index in range(count)]
        # Every finished translation must format with the source's arguments.
        translation.text.format(*args)
        for field in placeholders(translation.text):
            assert field == "" or re.fullmatch(r"\d+", field), (
                source,
                translation.text,
            )


def test_store_messages_go_through_the_translator(qapp, tmp_path):
    from PyQt6.QtCore import QTranslator

    from pyqtpass.password_store import PasswordStore

    class Shouting(QTranslator):
        """Translates the store's messages into upper case."""

        def translate(self, context, source, *_args):
            return source.upper() if context == "PasswordStore" else ""

    translator = Shouting()
    qapp.installTranslator(translator)
    try:
        with pytest.raises(FileNotFoundError, match="IS NOT IN THE PASSWORD STORE"):
            PasswordStore(str(tmp_path)).get_key("missing")
    finally:
        qapp.removeTranslator(translator)
