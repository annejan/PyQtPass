"""Checks that every translation can be used where its source is."""

# pylint: disable=missing-function-docstring

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
