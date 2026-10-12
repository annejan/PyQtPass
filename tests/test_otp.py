"""Tests for the built-in TOTP generator against the RFC 6238 vectors."""

# pylint: disable=missing-function-docstring

import base64

import pytest

import otp  # pylint: disable=wrong-import-order
from conftest import TEST_OTP_SEED

SEEDS = {
    "SHA1": b"12345678901234567890",
    "SHA256": b"12345678901234567890123456789012",
    "SHA512": b"1234567890123456789012345678901234567890123456789012345678901234",
}

# (time, sha1, sha256, sha512) from RFC 6238 appendix B.
VECTORS = [
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
]


@pytest.mark.parametrize("vector", VECTORS)
@pytest.mark.parametrize(
    "column,algorithm", [(1, "SHA1"), (2, "SHA256"), (3, "SHA512")]
)
def test_rfc6238(vector, column, algorithm):
    secret = base64.b32encode(SEEDS[algorithm]).decode().rstrip("=")
    settings = otp.parse(
        f"otpauth://totp/Test?secret={secret}&digits=8&algorithm={algorithm}"
    )
    assert settings is not None
    assert otp.generate(settings, vector[0]) == vector[column]


def test_bare_secret_and_defaults():
    settings = otp.parse("gezd gnbv gy3t qojq gezd gnbv gy3t qojq")
    assert settings.key == SEEDS["SHA1"]
    assert settings.digits == 6 and settings.period == 30
    assert otp.generate(settings, 59) == "287082"
    assert otp.seconds_remaining(settings, 59) == 1


def test_invalid():
    assert otp.parse("") is None
    assert otp.parse("otpauth://hotp/x?secret=GEZDGNBV") is None
    assert otp.parse("otpauth://totp/x") is None
    assert otp.parse("not base32 !!") is None


def test_steam():
    settings = otp.parse(f"otpauth://totp/Steam?secret={TEST_OTP_SEED}&encoder=steam")
    code = otp.generate(settings, 59)
    assert len(code) == 5
    assert all(char in otp.STEAM_ALPHABET for char in code)
