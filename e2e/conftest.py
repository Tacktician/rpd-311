"""Pytest fixtures for the E2E suite.

Assumes the stack is already up (docker compose or minikube) and reachable
at the configured service URLs. A session-scoped health gate fails fast with a
clear message if it isn't.
"""
import httpx
import pytest

import flows


@pytest.fixture(scope="session", autouse=True)
def _services_up():
    flows.wait_for_health(timeout=float(__import__("os").environ.get("E2E_HEALTH_TIMEOUT", "60")))


@pytest.fixture
def client():
    with httpx.Client(timeout=10.0) as c:
        yield c
