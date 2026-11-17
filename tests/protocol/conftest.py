"""Protocol regressions replay saved bytes and must never contact a server."""
import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_protocol_test_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Protocol tests attempted real networking")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
