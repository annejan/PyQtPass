"""
Translation for the modules that do not use Qt themselves, like the
password store: their messages reach the user in dialogs and the status bar.

Call translate() with literal strings, so pylupdate6 finds them, and fill in
placeholders after translating:

    translate("PasswordStore", "{} already exists").format(path)
"""


def translate(context, text):
    """
    :param context: The translation context, like "PasswordStore".
    :param text: The English source text.
    :return: The text in the language of the installed translator, or the
             text itself when there is none (or no Qt).
    """
    try:
        from PyQt6.QtCore import (  # pylint: disable=import-outside-toplevel
            QCoreApplication,
        )
    except ImportError:
        return text
    return QCoreApplication.translate(context, text)
