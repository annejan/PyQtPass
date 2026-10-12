"""Store templates (.templates, .default_template) and the fields editor."""

# pylint: disable=missing-function-docstring,redefined-outer-name,unused-argument,import-outside-toplevel

import os

from pyqtpass.templates import (
    default_template,
    parse_templates,
    read_templates,
    template_fields_for,
)

TEMPLATES = """# shared templates
[website]
login
url

[server]
user
# not a field
host
[]
ignored
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def test_parse_templates():
    assert parse_templates(TEMPLATES) == {
        "website": ["login", "url"],
        "server": ["user", "host"],
    }


def test_default_template_is_inherited(tmp_path):
    store_dir = str(tmp_path)
    write(os.path.join(store_dir, ".templates"), TEMPLATES)
    write(os.path.join(store_dir, "hosts", ".default_template"), "server\n")
    write(os.path.join(store_dir, "hosts", "lab", "deep", ".keep"), "")
    assert read_templates(store_dir)["server"] == ["user", "host"]
    assert default_template(store_dir, "hosts/lab/deep") == "server"
    assert default_template(store_dir, "web") == ""
    write(os.path.join(store_dir, ".default_template"), "website")
    assert default_template(store_dir, "web") == "website"
    assert default_template(store_dir, "hosts") == "server"


def test_links_are_not_followed(tmp_path):
    store_dir = str(tmp_path / "store")
    outside = str(tmp_path / "outside")
    write(outside, TEMPLATES)
    os.makedirs(store_dir)
    os.symlink(outside, os.path.join(store_dir, ".templates"))
    assert not read_templates(store_dir)


def test_template_fields_for_falls_back_to_settings(tmp_path, settings):
    store_dir = str(tmp_path)
    settings.set("use_template", True)
    settings.set("pass_template", "login\nemail")
    assert template_fields_for(store_dir, "x", settings) == ["login", "email"]
    write(os.path.join(store_dir, ".templates"), TEMPLATES)
    write(os.path.join(store_dir, "x", ".default_template"), "server")
    assert template_fields_for(store_dir, "x", settings) == ["user", "host"]
    write(os.path.join(store_dir, "x", ".default_template"), "missing")
    assert template_fields_for(store_dir, "x", settings) == ["login", "email"]


def test_fields_editor_rename_add_remove(qapp):
    from pyqtpass.fields_editor import FieldsEditor

    editor = FieldsEditor()
    changes = []
    editor.changed.connect(lambda: changes.append(1))
    editor.set_fields(["login"], [("login", "me"), ("pin", "1234")])
    assert editor.template_names() == ["login"]
    assert editor.fields() == [("login", "me"), ("pin", "1234")]
    editor.rows[1]["name_edit"].setText("code")
    assert editor.fields() == [("login", "me"), ("code", "1234")]
    editor.add_field("note", "hi")
    editor.add_field()
    assert editor.fields()[-1] == ("note", "hi")
    assert not editor.problem()
    editor.rows[-1]["value_edit"].setText("orphan")
    assert editor.problem()
    editor.rows[-1]["name_edit"].setText("a:b")
    assert "a:b" in editor.problem()
    entry = editor.rows[1]
    row = entry["name_edit"].parentWidget()
    changes.clear()
    editor.remove_field(row, entry)
    assert changes and ("code", "1234") not in editor.fields()


def test_fields_editor_checks_otp(qapp):
    from pyqtpass.fields_editor import FieldsEditor

    editor = FieldsEditor()
    editor.otp_label = lambda: "site"
    editor.set_fields(["login", "otp"], [("login", "me"), ("totp", "23456723")])
    template_otp, totp = editor.rows[1]["value_edit"], editor.rows[2]["value_edit"]
    # The filled TOTP field is the OTP one, not the empty template field.
    assert totp.placeholderText() == "otpauth:// URI or base32 secret"
    assert template_otp.placeholderText() == ""
    assert not totp.actions() and not totp.toolTip()
    # A value that was already there and is no URI is left alone.
    editor.normalize_otp()
    assert totp.text() == "23456723"
    totp.setText("not a secret!")
    assert totp.actions() and totp.toolTip() == "Invalid OTP secret"
    totp.clear()
    assert not totp.actions() and not totp.toolTip()
    assert template_otp.placeholderText() == "otpauth:// URI or base32 secret"
    template_otp.textEdited.emit("jbswy3dpehpk3pxp")
    template_otp.setText("jbswy3dpehpk3pxp")
    template_otp.editingFinished.emit()
    assert template_otp.text() == (
        "otpauth://totp/site?secret=JBSWY3DPEHPK3PXP&digits=6&period=30"
    )
    # Renaming a field away from 'totp' drops its check.
    editor.rows[2]["name_edit"].setText("code")
    totp.setText("not a secret!")
    assert not totp.actions() and totp.placeholderText() == "Value"


def test_edit_dialog_switches_template(qapp, settings, store):
    from pyqtpass.edit_password_window import EditPasswordDialog

    settings.set("use_template", True)
    settings.set("template_all_fields", True)
    write(os.path.join(store.store_dir, ".templates"), TEMPLATES)
    write(os.path.join(store.store_dir, "hosts", ".default_template"), "server")
    store.set_key("hosts/box", "pw\nuser: root\nhost: box.lan\nlogin: admin\nfree text")
    dialog = EditPasswordDialog(store, "hosts/box", "box")
    assert dialog.template_combo.currentData() == "server"
    assert dialog.fields_editor.template_names() == ["user", "host"]
    dialog.template_combo.setCurrentIndex(dialog.template_combo.findData("website"))
    assert dialog.fields_editor.template_names() == ["login", "url"]
    data = dialog.entry_data()
    for line in ("pw", "user: root", "host: box.lan", "login: admin", "free text"):
        assert line in data.splitlines()
    assert dialog.fields_editor.fields()[-2:] == [("user", "root"), ("host", "box.lan")]
    dialog.fields_editor.rows[-1]["name_edit"].setText("hostname")
    assert "hostname: box.lan" in dialog.entry_data().splitlines()
