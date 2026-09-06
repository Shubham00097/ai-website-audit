"""
tests/test_rate_limiting.py

A2 + Correction 2: Verify per-host rate limiting behavior:
  - Two rapid calls to same host → measurable delay
  - Calls to different hosts → no cross-host blocking
"""
from __future__ import annotations

import sys
import os
import time
import threading
from unittest.mock import patch, MagicMock

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the rate limiter state between tests."""
    from shared import http_client
    http_client._last_request_time.clear()
    yield
    http_client._last_request_time.clear()


def test_same_host_throttled():
    """Two rapid calls to the same host should enforce MIN_INTERVAL delay."""
    from shared import http_client

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.text = "<html></html>"

    with patch.object(http_client._session(), "get", return_value=mock_response):
        t1 = time.monotonic()
        http_client.get("https://example.com/page1")
        http_client.get("https://example.com/page2")
        t2 = time.monotonic()

    # Second call should have been delayed by at least MIN_INTERVAL
    elapsed = t2 - t1
    assert elapsed >= http_client.MIN_INTERVAL * 0.9, (
        f"Expected delay >= {http_client.MIN_INTERVAL}s, got {elapsed:.3f}s"
    )


def test_different_hosts_not_blocked():
    """
    Correction 2 verification: a throttled call to host A must NOT delay
    a concurrent call to host B. The lock only guards the dict, not the sleep.
    """
    from shared import http_client

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.text = "<html></html>"

    results = {}

    def call_host(host_url, label):
        with patch.object(http_client._session(), "get", return_value=mock_response):
            t_start = time.monotonic()
            http_client.get(host_url)
            results[label] = time.monotonic() - t_start

    # First: prime host-a so the second call will need to sleep
    with patch.object(http_client._session(), "get", return_value=mock_response):
        http_client.get("https://host-a.com/page1")

    # Now launch host-a (will sleep) and host-b (should NOT sleep) concurrently
    thread_a = threading.Thread(target=call_host, args=("https://host-a.com/page2", "host_a"))
    thread_b = threading.Thread(target=call_host, args=("https://host-b.com/page1", "host_b"))

    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    # host-b should complete much faster than host-a's throttle delay
    assert "host_b" in results, "host-b thread did not complete"
    assert results["host_b"] < http_client.MIN_INTERVAL * 0.8, (
        f"host-b was blocked for {results['host_b']:.3f}s — lock may be serializing hosts"
    )
