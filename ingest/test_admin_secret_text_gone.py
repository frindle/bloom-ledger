"""Frozen test: the bloom_admin secret and the ADMIN_PATH constant are gone from the settings and server modules."""
import inspect

import bloom_settings as S
import server as SV


def test_server_has_no_admin_path():
    assert not hasattr(SV, "ADMIN_PATH"), "server.ADMIN_PATH must be deleted"
    assert "ADMIN_PATH" not in inspect.getsource(SV)


def test_no_admin_secret_text_in_the_sources():
    for mod in (S, SV):
        src = inspect.getsource(mod)
        assert "bloom_admin" not in src and "BLOOM_ADMIN" not in src, mod.__name__


def test_the_docstring_names_the_lan_guard():
    assert "LAN write guard" in S.__doc__
