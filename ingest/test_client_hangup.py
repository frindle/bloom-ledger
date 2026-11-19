"""A client that hangs up before the reply is not a server error: no traceback, the connection just closes."""
from http.server import BaseHTTPRequestHandler

import pytest

import server as SV


@pytest.mark.parametrize("exc", [BrokenPipeError, ConnectionResetError])
def test_hangup_is_quiet(monkeypatch, exc):
    def boom(self):
        raise exc(32, "client went away")

    monkeypatch.setattr(BaseHTTPRequestHandler, "handle_one_request", boom)
    h = SV.Handler.__new__(SV.Handler)
    h.close_connection = False
    h.handle_one_request()
    assert h.close_connection is True


def test_other_errors_still_raise(monkeypatch):
    def boom(self):
        raise ValueError("a real bug")

    monkeypatch.setattr(BaseHTTPRequestHandler, "handle_one_request", boom)
    h = SV.Handler.__new__(SV.Handler)
    with pytest.raises(ValueError):
        h.handle_one_request()
