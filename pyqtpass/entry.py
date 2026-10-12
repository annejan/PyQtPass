"""
Parsing and assembling of password entries, a port of QtPass's FileContent.

The first line of an entry is the password. Following 'name: value' lines
become fields when their name is in the template, or when all fields are
templated (except values starting with '//', so URLs are left alone).
Everything else is remaining text. One-time password configuration is
found in an otpauth:// URI or an 'otp:'/'totp:' field and is kept out of
the displayed text.
"""

from dataclasses import dataclass, field

from pyqtpass.otp import is_otp_field_name, is_otp_uri


@dataclass
class EntryContent:
    """The parts of a decrypted password entry."""

    password: str = ""
    fields: list = field(default_factory=list)
    remaining: str = ""
    remaining_display: str = ""
    otp: str = ""

    @property
    def password_for_display(self):
        """
        :return: The password, or '' when the first line is an OTP URI.
        """
        return "" if is_otp_uri(self.password) else self.password


def _is_line_hidden(line):
    if is_otp_uri(line):
        return True
    if ":" not in line:
        return False
    name, value = line.split(":", 1)
    return is_otp_field_name(name) or is_otp_uri(value)


def parse_entry(content, template_fields=(), all_fields=False):
    """
    Split a decrypted entry into its parts.

    :param content: The decrypted contents.
    :param template_fields: Field names that are always shown as fields.
    :param all_fields: Treat every 'name: value' line as a field.
    :return: An EntryContent.
    """
    lines = content.rstrip("\n").split("\n") if content else []
    password = lines.pop(0) if lines else ""
    fields = []
    remaining = []
    remaining_display = []
    otp_field = ""
    otp_bare = password.strip() if is_otp_uri(password) else ""
    otp_remaining = ""
    for line in lines:
        if ":" in line:
            name, value = line.split(":", 1)
            if name in template_fields or (
                all_fields and name.strip() and not value.startswith("//")
            ):
                fields.append((name.strip(), value.strip()))
                if not otp_field and (is_otp_field_name(name) or is_otp_uri(value)):
                    otp_field = value.strip()
                continue
            if not otp_remaining and is_otp_field_name(name):
                otp_remaining = value.strip()
        remaining.append(line)
        if is_otp_uri(line) and not otp_bare:
            otp_bare = line.strip()
        if not _is_line_hidden(line):
            remaining_display.append(line)
    return EntryContent(
        password=password,
        fields=fields,
        remaining="\n".join(remaining),
        remaining_display="\n".join(remaining_display),
        otp=otp_field or otp_bare or otp_remaining,
    )


def build_entry(password, fields, remaining):
    """
    Assemble an entry from its parts, the inverse of parse_entry.

    Fields with an empty value are left out.

    :param password: The password line.
    :param fields: List of (name, value) tuples.
    :param remaining: The remaining free text.
    :return: The entry contents.
    """
    lines = [password]
    lines += [f"{name}: {value}" for name, value in fields if value]
    if remaining.strip():
        lines.append(remaining.rstrip("\n"))
    return "\n".join(lines) + "\n"
