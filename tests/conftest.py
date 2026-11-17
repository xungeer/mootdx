"""Default tests are offline and never use the developer's Mootdx cache."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import pandas
import pytest


def pytest_addoption(parser):
    parser.addoption('--online', action='store_true', default=False,
                     help='Enable tests marked online against real external services.')


def pytest_configure(config):
    # This runs before test modules import mootdx and resolve cache paths.
    temporary = tempfile.TemporaryDirectory(prefix='mootdx-pytest-home-')
    home_patch = patch.object(Path, 'home', return_value=Path(temporary.name))
    home_patch.start()
    gate = {'active': True, 'allowed': False, 'attempts': []}
    config._mootdx_network_gate = gate

    def audit(event, args):
        if gate['active'] and not gate['allowed'] and event in {
            'socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname',
            'socket.gethostbyaddr', 'socket.sendto',
        }:
            gate['attempts'].append(event)
            raise AssertionError('Real networking requires a test marked online and --online')

    sys.addaudithook(audit)

    def cleanup():
        gate['active'] = False
        home_patch.stop()
        temporary.cleanup()

    config.add_cleanup(cleanup)


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--online'):
        disabled = pytest.mark.skip(reason='requires --online and external quote/HTTP services')
        for item in items:
            if item.get_closest_marker('online'):
                item.add_marker(disabled)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    # Enable marked online setup before class/module fixtures create clients.
    gate = item.config._mootdx_network_gate
    gate['attempts'].clear()
    gate['allowed'] = bool(item.config.getoption('--online')
                           and item.get_closest_marker('online'))


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    gate = item.config._mootdx_network_gate
    gate['allowed'] = False
    assert not gate['attempts'], f"Offline test attempted external networking: {gate['attempts']}"


def is_empty(obj):
    if isinstance(obj, pandas.DataFrame):
        return obj.empty
    return not obj


@pytest.fixture()
def quotes():
    from mootdx.quotes import Quotes
    client = Quotes.factory('std')
    yield client
    client.close()
