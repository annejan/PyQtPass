"""
Built-in TOTP (RFC 6238) support, so no pass-otp extension is needed.

An entry holds its one-time password configuration as an otpauth:// URI
(on any line, or as the value of an 'otp:' or 'totp:' field) or as a bare
base32 secret in such a field. Steam Guard codes (encoder=steam) are
supported as well, like in QtPass.
"""

import base64
import binascii
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlsplit

DEFAULT_DIGITS = 6
DEFAULT_PERIOD = 30
MIN_DIGITS = 6
MAX_DIGITS = 10
MAX_PERIOD = 3600
STEAM_DIGITS = 5
STEAM_ALPHABET = "23456789BCDFGHJKMNPQRTVWXY"

ALGORITHMS = {
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
    "SHA512": hashlib.sha512,
}


@dataclass
class TotpSettings:
    """The parsed configuration of a TOTP generator."""

    key: bytes
    digits: int = DEFAULT_DIGITS
    period: int = DEFAULT_PERIOD
    algorithm: str = "SHA1"
    steam: bool = False
    label: str = ""
    issuer: str = ""


def is_otp_field_name(name):
    """
    :param name: A field name.
    :return: True for 'otp' and 'totp', in any case.
    """
    return name.strip().lower() in ("otp", "totp")


def is_otp_uri(value):
    """
    :param value: A line or field value.
    :return: True when value is an otpauth:// URI.
    """
    return value.strip().lower().startswith("otpauth://")


def decode_base32(secret):
    """
    Decode a base32 secret, tolerating spaces, dashes, lower case and
    missing padding.

    :param secret: The base32 text.
    :return: The decoded bytes, or b'' when it is not valid base32.
    """
    cleaned = "".join(secret.split()).replace("-", "").upper().rstrip("=")
    if not cleaned:
        return b""
    cleaned += "=" * (-len(cleaned) % 8)
    try:
        return base64.b32decode(cleaned)
    except (binascii.Error, ValueError):
        return b""


def _positive_int(value, fallback):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def parse(config):
    """
    Parse an otpauth://totp URI or a bare base32 secret.

    :param config: The configuration text.
    :return: TotpSettings, or None when it is not a usable TOTP setup.
    """
    config = (config or "").strip()
    if not config:
        return None
    settings = TotpSettings(key=b"")
    if config.lower().startswith("otpauth:"):
        parts = urlsplit(config)
        if parts.scheme.lower() != "otpauth" or parts.netloc.lower() != "totp":
            return None
        query = {key.lower(): value for key, value in parse_qsl(parts.query)}
        secret = query.get("secret", "")
        settings.label = unquote(parts.path.lstrip("/"))
        settings.issuer = query.get("issuer", "")
        settings.digits = _positive_int(query.get("digits"), DEFAULT_DIGITS)
        settings.period = _positive_int(query.get("period"), DEFAULT_PERIOD)
        algorithm = query.get("algorithm", "SHA1").upper().replace("HMAC-", "")
        settings.algorithm = algorithm.replace("-", "")
        if settings.algorithm not in ALGORITHMS:
            settings.algorithm = "SHA1"
        settings.steam = query.get("encoder", "").lower() == "steam"
    else:
        secret = config
    settings.key = decode_base32(secret)
    if not settings.key:
        return None
    if settings.steam:
        settings.digits = STEAM_DIGITS
    else:
        settings.digits = min(max(settings.digits, MIN_DIGITS), MAX_DIGITS)
    settings.period = min(max(settings.period, 1), MAX_PERIOD)
    return settings


def generate(settings, unix_time=None):
    """
    Generate the code for a moment in time.

    :param settings: TotpSettings from parse().
    :param unix_time: Seconds since the epoch, now when None.
    :return: The one-time password.
    """
    if unix_time is None:
        unix_time = time.time()
    counter = int(unix_time) // settings.period
    digest = hmac.new(
        settings.key, struct.pack(">Q", counter), ALGORITHMS[settings.algorithm]
    ).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    if settings.steam:
        code = ""
        for _ in range(STEAM_DIGITS):
            code += STEAM_ALPHABET[binary % len(STEAM_ALPHABET)]
            binary //= len(STEAM_ALPHABET)
        return code
    return str(binary % 10**settings.digits).zfill(settings.digits)


def seconds_remaining(settings, unix_time=None):
    """
    :param settings: TotpSettings from parse().
    :param unix_time: Seconds since the epoch, now when None.
    :return: Seconds until the current code changes.
    """
    if unix_time is None:
        unix_time = time.time()
    return settings.period - int(unix_time) % settings.period
