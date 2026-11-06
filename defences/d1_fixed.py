"""D1fix (extension E4 only): D1 with direction-separated codes.

The receiver's code comes from HMAC-SHA256(secret, b"sign") and the caller's code from
HMAC-SHA256(secret, b"countersign") (each truncated to 20 bytes, base32-encoded, used as a
TOTP secret). A reflected code therefore fails. Replay inside the window and relay are
deliberately left unfixed, so E4 isolates the reflection flaw.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

import pyotp

from defences.d1_totp import D1Totp


def derive_secret(secret: str, label: bytes) -> str:
    digest = hmac.new(secret.encode("ascii"), label, hashlib.sha256).digest()[:20]
    return base64.b32encode(digest).decode("ascii")


class D1Fixed(D1Totp):
    name = "D1fix"

    def _make_totps(self, secret: str):
        sign = pyotp.TOTP(derive_secret(secret, b"sign"), digits=self.digits, interval=self.period)
        counter = pyotp.TOTP(derive_secret(secret, b"countersign"), digits=self.digits, interval=self.period)
        return sign, counter
