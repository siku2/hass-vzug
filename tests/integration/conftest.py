# Avoid "pytest_socket.SocketBlockedError: A test tried to use socket.socket." errors during tests
import os
import pytest
from pytest_socket import enable_socket, socket_allow_hosts

def test_directory() -> str:
    return os.path.join(os.getenv("PROJECT_ROOT"), "tests")

@pytest.hookimpl(trylast=True)
def pytest_runtest_setup():
    enable_socket()
    socket_allow_hosts(["127.0.0.1", "localhost", "::1", "10.0.0.90", "10.0.0.91"], allow_unix_socket=True)
