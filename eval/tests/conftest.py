"""Keep evaluation tests local and independent of provider credentials."""

import socket
from typing import Any, NoReturn

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject socket connections and DNS lookups for every evaluation test.

    Args:
        monkeypatch: Restores socket functions after each test.
    """

    def blocked(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("Evaluation tests must not open network connections.")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
