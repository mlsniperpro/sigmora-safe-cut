"""Replay mode never touches the network: a process-wide guard that refuses every outbound connection.

Loopback stays open (a local API under test, a storage emulator); everything else raises :class:`NetworkBlocked`
at ``connect``/``getaddrinfo`` time, so a stage that forgot its replay branch fails loudly instead of spending.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"})


class NetworkBlocked(ConnectionError):
    """An outbound connection was attempted in replay mode."""


def _is_local(host: object) -> bool:
    if host is None:
        return True  # getaddrinfo(None, port) resolves the wildcard/loopback address for a local bind
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    name = host.strip("[]").rstrip(".").lower()
    if name in _LOCAL_NAMES or name == "":
        return True
    try:
        address = ipaddress.ip_address(name.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


_saved: dict[str, Any] = {}


def _guarded_connect(self: socket.socket, address: Any, /) -> None:
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
        raise NetworkBlocked(f"replay mode: refused a connection to {address[0]!r}")
    _saved["connect"](self, address)


def _guarded_connect_ex(self: socket.socket, address: Any, /) -> int:
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
        raise NetworkBlocked(f"replay mode: refused a connection to {address[0]!r}")
    return _saved["connect_ex"](self, address)


def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    if not _is_local(host):
        raise NetworkBlocked(f"replay mode: refused to resolve {host!r}")
    return _saved["getaddrinfo"](host, *args, **kwargs)


def active() -> bool:
    return bool(_saved)


def block() -> None:
    """Refuse outbound connections for the rest of the process (idempotent)."""
    if _saved:
        return
    _saved["connect"] = socket.socket.connect
    _saved["connect_ex"] = socket.socket.connect_ex
    _saved["getaddrinfo"] = socket.getaddrinfo
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign] -- the guard is this monkeypatch
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign] -- the guard is this monkeypatch
    socket.getaddrinfo = _guarded_getaddrinfo


def unblock() -> None:
    if not _saved:
        return
    socket.socket.connect = _saved.pop("connect")  # type: ignore[method-assign] -- restoring the original
    socket.socket.connect_ex = _saved.pop("connect_ex")  # type: ignore[method-assign] -- restoring the original
    socket.getaddrinfo = _saved.pop("getaddrinfo")


@contextmanager
def blocked() -> Generator[None]:
    """Block outbound connections inside the ``with`` (restoring the previous state after)."""
    was_active = active()
    block()
    try:
        yield
    finally:
        if not was_active:
            unblock()
