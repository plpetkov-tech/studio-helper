"""SPEC.md §8: 'No outbound network calls at all. A test asserts this
by monkeypatching socket.create_connection.'

Loopback connections (127.0.0.1 / localhost), which the app's own
server and selftest use to talk to itself, are allowed. Anything else
fails the test immediately.

The one deliberate exception (SPEC.md §15, 2026-09-24) is
studio_helper.updater, which talks to GitHub -- but only when the
user explicitly clicks "Check for updates" / "Download & install".
It must never run on its own, including during --selftest, so that's
asserted here too.
"""

import socket

import pytest
from studio_helper import selftest, updater

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@pytest.fixture()
def guard_network(monkeypatch):
    real_create_connection = socket.create_connection

    def guarded(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK_HOSTS:
            raise AssertionError(f"Outbound connection attempted to non-loopback host: {host!r}")
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", guarded)
    yield


def test_selftest_never_leaves_loopback(guard_network):
    assert selftest.run() == 0


def test_selftest_never_calls_the_updater(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("updater.check_for_update must never run automatically")

    monkeypatch.setattr(updater, "check_for_update", fail_if_called)
    assert selftest.run() == 0
