"""
Reuse QtPass's translations for PyQtPass.

QtPass (GPL-3.0-or-later, like PyQtPass) is translated into over 60
languages on Weblate. Many PyQtPass strings are the same as QtPass's, so
this script copies every finished QtPass translation whose source text
matches a PyQtPass string into PyQtPass's .ts files:

    python scripts/import_qtpass_translations.py /path/to/QtPass

It creates a .ts file for every QtPass locale (with pylupdate6), converts
Qt's %1, %2 placeholders to the {0}, {1} that PyQtPass formats with, and
never overwrites a translation PyQtPass already has. Plural (numerus)
messages are skipped.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "pyqtpass")
PLACEHOLDER = re.compile(r"%(\d+)")


def normalise(text):
    """
    :param text: A source string.
    :return: The key both projects' strings are matched on.
    """
    return text.replace("…", "...").strip()


def convert_placeholders(text):
    """
    :param text: A QtPass string with %1-style placeholders.
    :return: The string with {0}-style placeholders, or None when it holds
             braces that str.format would misread.
    """
    if "{" in text or "}" in text:
        return None
    return PLACEHOLDER.sub(lambda m: "{" + str(int(m.group(1)) - 1) + "}", text)


def source_key(text):
    """
    :param text: A PyQtPass or QtPass source string.
    :return: The matching key: placeholders are numbered in order, so
             "Open {} in browser" and "Open %1 in browser" meet.
    """
    counter = iter(range(100))
    text = re.sub(r"\{\d*\}", lambda _m: "%" + str(next(counter) + 1), text)
    return normalise(text)


SUFFIXES = (":", "...")


def loose_key(text):
    """
    :param text: A source string.
    :return: A looser key: case and a trailing ':' or '...' ignored, for
             strings QtPass 2.0 moved to sentence case.
    """
    key = source_key(text)
    for suffix in SUFFIXES:
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return key.strip().lower()


def adapt_suffix(source, text):
    """
    Give a loosely matched translation the trailing ':' or '...' of the
    PyQtPass source, so a label still ends like its source.

    :param source: The PyQtPass source string.
    :param text: The QtPass translation.
    :return: The adapted translation.
    """
    for suffix in SUFFIXES:
        text = text.rstrip()
        for variant in (suffix, "\u2026" if suffix == "..." else "\uff1a"):
            if text.endswith(variant):
                text = text[: -len(variant)].rstrip()
    for suffix in SUFFIXES:
        if normalise(source).endswith(suffix):
            return text + suffix
    return text


def qtpass_translations(path):
    """
    :param path: A QtPass .ts file.
    :return: Tuple of (dict of source key to finished translation, dict of
             loose key to finished translation).
    """
    found = {}
    loose = {}
    for message in ET.parse(path).getroot().iter("message"):
        if message.get("numerus") == "yes":
            continue
        source = message.findtext("source") or ""
        translation = message.find("translation")
        if translation is None or translation.get("type") in (
            "unfinished",
            "vanished",
            "obsolete",
        ):
            continue
        text = translation.text or ""
        converted = convert_placeholders(text)
        if source and converted:
            found.setdefault(source_key(source), converted)
            loose.setdefault(loose_key(source), converted)
    return found, loose


def fill(ts_path, translations):
    """
    Fill the untranslated messages of a PyQtPass .ts file.

    :param ts_path: The PyQtPass .ts file.
    :param translations: The dicts from qtpass_translations().
    :return: Number of messages filled.
    """
    tree = ET.parse(ts_path)
    root = tree.getroot()
    if not root.get("language"):
        locale = os.path.basename(ts_path)[len("localization_") : -len(".ts")]
        root.set("language", locale)
    filled = 0
    for message in tree.getroot().iter("message"):
        source = message.findtext("source") or ""
        translation = message.find("translation")
        if translation is None or translation.get("type") != "unfinished":
            continue
        if (translation.text or "").strip():
            continue
        exact, loose = translations
        text = exact.get(source_key(source))
        if text is None and loose_key(source) in loose:
            text = adapt_suffix(source, loose[loose_key(source)])
        if text is None:
            continue
        # Our strings number their placeholders in order; a translation
        # may reorder them, which {0}/{1} keeps working with str.format.
        if text.count("{") != source.count("{"):
            continue
        translation.text = text
        del translation.attrib["type"]
        filled += 1
    tree.write(ts_path, encoding="utf-8", xml_declaration=True)
    with open(ts_path, "r+", encoding="utf-8") as handle:
        content = handle.read().replace(
            "<?xml version='1.0' encoding='utf-8'?>",
            '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>',
        )
        handle.seek(0)
        handle.write(content)
        handle.truncate()
    return filled


def main():
    """Import the translations."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("qtpass", help="path to a QtPass checkout")
    args = parser.parse_args()
    sources = sorted(
        os.path.basename(path) for path in glob.glob(os.path.join(PACKAGE, "*.py"))
    )
    total = 0
    for qtpass_ts in sorted(
        glob.glob(os.path.join(args.qtpass, "localization", "*.ts"))
    ):
        name = os.path.basename(qtpass_ts)
        ours = os.path.join(PACKAGE, "localization", name)
        subprocess.run(
            ["pylupdate6", "--ts", ours, *sources],
            cwd=PACKAGE,
            check=True,
            capture_output=True,
        )
        filled = fill(ours, qtpass_translations(qtpass_ts))
        total += filled
        print(f"{name}: {filled} strings from QtPass")
    print(f"{total} strings filled in total", file=sys.stderr)


if __name__ == "__main__":
    main()
