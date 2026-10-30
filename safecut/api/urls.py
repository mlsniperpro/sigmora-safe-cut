"""Signed URLs for uploads and job media: ``?exp=<unix>&sig=<hmac>``, so a link works for a bounded time and only
for the exact file (and, for uploads, the exact size and type) it was made for."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

MEDIA_TTL_S = 3600
UPLOAD_TTL_S = 15 * 60


class Signer:
    def __init__(self, secret: bytes | None, public_url: str | None) -> None:
        self._secret = secret or secrets.token_bytes(32)
        self.base = (public_url or "").rstrip("/")

    def _mac(self, path: str, exp: int, extra: str) -> str:
        message = f"{path}\n{exp}\n{extra}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def sign(self, path: str, *, now: datetime | None = None, ttl_s: int = MEDIA_TTL_S, extra: str = "") -> str:
        """An absolute URL under ``SAFECUT_PUBLIC_URL`` (or a same-origin path when it's unset)."""
        exp = int((now or datetime.now(UTC)).timestamp()) + ttl_s
        query = urlencode({"exp": exp, "sig": self._mac(path, exp, extra)})
        return f"{self.base}{quote(path)}?{query}"

    def verify(
        self, path: str, exp: str | None, sig: str | None, *, extra: str = "", now: datetime | None = None
    ) -> bool:
        if not exp or not sig or not (exp.isascii() and exp.isdigit()) or len(exp) > 12:
            return False
        if int(exp) < int((now or datetime.now(UTC)).timestamp()):
            return False
        return hmac.compare_digest(self._mac(path, int(exp), extra), sig)


def expiry(url: str) -> datetime:
    """When a URL made by :meth:`Signer.sign` stops working."""
    exp = url.rsplit("exp=", 1)[1].split("&", 1)[0]
    return datetime.fromtimestamp(int(exp), UTC)
