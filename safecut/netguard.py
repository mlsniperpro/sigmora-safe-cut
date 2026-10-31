"""Replay mode never touches the network: a guard that refuses every outbound connection.

Two scopes: :func:`block` refuses for the whole process (the CLI and an API started with ``SAFECUT_REPLAY=1``),
and :func:`blocked` refuses only in the calling thread while its ``with`` lasts (``pipeline.run_stage`` in replay),
so a replay job can't silence a live job running in another thread. Loopback stays open (a local API under
test), except the ports a configured HTTP(S) proxy listens on; everything else raises :class:`NetworkBlocked` at
``connect``/``getaddrinfo`` time, so a stage that forgot its replay branch fails loudly instead of spending.

One named exception: :func:`permitting` lets the Modal control plane through while the GPU auditor runs (our own
compute on the jobs Volume, never a model API), and only that host and the addresses it resolved to.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

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


_original: dict[str, Any] = {}
#: Hosts :func:`permitting` let through (with a count, since scopes nest across threads), and their addresses.
_permitted_hosts: dict[str, int] = {}
_permitted_addresses: set[str] = set()
_permit_lock = threading.Lock()
_install_lock = threading.Lock()
_global = threading.Event()
_local = threading.local()


def _refusing() -> bool:
    return _global.is_set() or getattr(_local, "depth", 0) > 0


def proxy_ports() -> frozenset[int]:
    """Loopback ports an HTTP(S) proxy listens on (``HTTPS_PROXY=http://127.0.0.1:36343`` and the like): a local
    proxy is a way out to the network, so in replay it is refused like any remote host."""
    ports: set[int] = set()
    for name, value in os.environ.items():
        if not name.lower().endswith("_proxy") or name.lower() == "no_proxy":
            continue
        try:
            parsed = urlsplit(value if "://" in value else f"http://{value}")
            if parsed.port is not None and _is_local(parsed.hostname):
                ports.add(parsed.port)
        except ValueError:
            continue
    return frozenset(ports)


def _name(host: object) -> str:
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    return str(host).strip("[]").rstrip(".").lower()


def _allowed(family: int, address: Any) -> bool:
    if family not in (socket.AF_INET, socket.AF_INET6):
        return True
    with _permit_lock:
        if _permitted_hosts and _name(address[0]) in _permitted_addresses:
            return True
    return _is_local(address[0]) and address[1] not in proxy_ports()


def _guarded_connect(self: socket.socket, address: Any, /) -> None:
    if _refusing() and not _allowed(self.family, address):
        raise NetworkBlocked(f"replay mode: refused a connection to {address[0]!r}:{address[1]}")
    _original["connect"](self, address)


def _guarded_connect_ex(self: socket.socket, address: Any, /) -> int:
    if _refusing() and not _allowed(self.family, address):
        raise NetworkBlocked(f"replay mode: refused a connection to {address[0]!r}:{address[1]}")
    return _original["connect_ex"](self, address)


def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    with _permit_lock:
        permitted = host is not None and _name(host) in _permitted_hosts
    if _refusing() and not _is_local(host) and not permitted:
        raise NetworkBlocked(f"replay mode: refused to resolve {host!r}")
    found = _original["getaddrinfo"](host, *args, **kwargs)
    if permitted:
        with _permit_lock:
            _permitted_addresses.update(_name(entry[4][0]) for entry in found)
    return found


def _install() -> None:
    """Wrap the socket functions once; the wrappers pass through unless a guard is on."""
    with _install_lock:
        if _original:
            return
        _original["connect"] = socket.socket.connect
        _original["connect_ex"] = socket.socket.connect_ex
        _original["getaddrinfo"] = socket.getaddrinfo
        socket.socket.connect = _guarded_connect  # type: ignore[method-assign] -- the guard is this wrapper
        socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign] -- the guard is this wrapper
        socket.getaddrinfo = _guarded_getaddrinfo


def active() -> bool:
    """Whether outbound connections are refused in the calling thread."""
    return _refusing()


def block() -> None:
    """Refuse outbound connections in every thread for the rest of the process (idempotent)."""
    _install()
    _global.set()


def unblock() -> None:
    """Undo :func:`block` (tests only; the CLI never unblocks)."""
    _global.clear()


@contextmanager
def blocked() -> Generator[None]:
    """Refuse outbound connections in this thread inside the ``with`` (nesting is fine)."""
    _install()
    _local.depth = getattr(_local, "depth", 0) + 1
    try:
        yield
    finally:
        _local.depth -= 1


@contextmanager
def permitting(host: str) -> Generator[None]:
    """Let ``host`` (and the addresses it resolves to inside the ``with``) through every guard, in every thread:
    clients such as Modal's resolve and connect on their own threads. Nothing else is let through."""
    _install()
    name = _name(host)
    if _is_local(name) or not name:
        raise ValueError(f"permitting() names a remote host, not {host!r}")
    with _permit_lock:
        _permitted_hosts[name] = _permitted_hosts.get(name, 0) + 1
        try:
            ipaddress.ip_address(name)
            _permitted_addresses.add(name)
        except ValueError:
            pass
    try:
        yield
    finally:
        with _permit_lock:
            _permitted_hosts[name] -= 1
            if not _permitted_hosts[name]:
                del _permitted_hosts[name]
            if not _permitted_hosts:
                _permitted_addresses.clear()
