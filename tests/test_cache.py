# agent-notes: { ctx: "issue #6 red-phase tests for EDGAR response caching", deps: ["src/sales_lead_research/discovery/cache.py", "src/sales_lead_research/discovery/edgar.py", "tests/fixtures/edgar/"], state: active, last: "sato@2026-04-28" }
"""Failing tests for issue #6: cache EDGAR responses locally.

All tests use ``tmp_path`` for the cache directory and
``httpx.MockTransport`` to count network requests.  No live network
calls.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from sales_lead_research.discovery.cache import cached_get

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"


def _counting_transport(payload: bytes, *, status: int = 200):
    """Return a ``(transport, call_count_list)`` pair.

    ``call_count_list`` is a single-element list whose ``[0]`` entry is
    incremented on every request so tests can assert how many network
    round-trips occurred.
    """
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(status, content=payload)

    return httpx.MockTransport(handler), call_count


# ---------------------------------------------------------------------------
# TestCachedGet — unit-level contract tests
# ---------------------------------------------------------------------------


class TestCachedGet:
    """Core ``cached_get`` behaviour."""

    def test_first_call_fetches_and_caches(self, tmp_path: Path):
        """First call for a URL should hit the network and write a cache
        file under ``cache_dir``."""
        payload = _fixture("company_tickers.json")
        transport, calls = _counting_transport(payload)
        client = httpx.Client(transport=transport)

        resp = cached_get(client, TICKERS_URL, tmp_path, ttl_hours=24)

        assert calls[0] == 1, "Expected exactly one network request"
        assert resp.status_code == 200
        assert resp.content == payload
        # At least one file should now exist in cache_dir
        cached_files = list(tmp_path.iterdir())
        assert len(cached_files) >= 1, "Cache file was not written"

    def test_second_call_returns_cached_without_network(self, tmp_path: Path):
        """A second call for the same URL within TTL should NOT hit the
        network."""
        payload = _fixture("company_tickers.json")
        transport, calls = _counting_transport(payload)
        client = httpx.Client(transport=transport)

        first = cached_get(client, TICKERS_URL, tmp_path, ttl_hours=24)
        second = cached_get(client, TICKERS_URL, tmp_path, ttl_hours=24)

        assert calls[0] == 1, "Second call should NOT have triggered a network request"
        assert second.status_code == 200
        assert second.content == first.content

    def test_expired_entry_triggers_fresh_fetch(self, tmp_path: Path):
        """When the cached file's mtime is older than ``ttl_hours``, the
        cache should re-fetch from the network."""
        payload = _fixture("company_tickers.json")
        transport, calls = _counting_transport(payload)
        client = httpx.Client(transport=transport)

        # Populate cache
        cached_get(client, TICKERS_URL, tmp_path, ttl_hours=1)
        assert calls[0] == 1

        # Backdate every file in the cache dir beyond the 1-hour TTL
        old_time = time.time() - 3700  # 1 hour + 100 seconds
        for f in tmp_path.iterdir():
            import os

            os.utime(f, (old_time, old_time))

        # This call should detect staleness and re-fetch
        resp = cached_get(client, TICKERS_URL, tmp_path, ttl_hours=1)
        assert calls[0] == 2, "Expired cache should have triggered a fresh fetch"
        assert resp.status_code == 200

    def test_cache_miss_fetches(self, tmp_path: Path):
        """When the cache directory is empty, ``cached_get`` must fetch
        from the network (equivalent to a cold start)."""
        payload = b'{"hello": "world"}'
        transport, calls = _counting_transport(payload)
        client = httpx.Client(transport=transport)

        resp = cached_get(client, "https://example.com/data.json", tmp_path)

        assert calls[0] == 1
        assert resp.content == payload

    def test_different_urls_get_different_cache_files(self, tmp_path: Path):
        """Two distinct URLs must map to separate cache files so they
        never collide."""
        payload_a = b'{"url": "a"}'
        payload_b = b'{"url": "b"}'

        call_count = [0]

        def handler(request: httpx.Request) -> httpx.Response:
            call_count[0] += 1
            url = str(request.url)
            if "alpha" in url:
                return httpx.Response(200, content=payload_a)
            return httpx.Response(200, content=payload_b)

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)

        resp_a = cached_get(client, "https://example.com/alpha", tmp_path)
        resp_b = cached_get(client, "https://example.com/beta", tmp_path)

        assert call_count[0] == 2, "Each URL should trigger its own fetch"
        assert resp_a.content == payload_a
        assert resp_b.content == payload_b

        # Both should now be cached -- no more network calls
        cached_get(client, "https://example.com/alpha", tmp_path)
        cached_get(client, "https://example.com/beta", tmp_path)
        assert call_count[0] == 2, "Cached URLs should not trigger additional fetches"

    def test_cache_dir_created_if_missing(self, tmp_path: Path):
        """``cached_get`` should create ``cache_dir`` (including parents)
        if it does not already exist."""
        nested = tmp_path / "deep" / "nested" / "dir"
        assert not nested.exists()

        payload = b"test"
        transport, calls = _counting_transport(payload)
        client = httpx.Client(transport=transport)

        cached_get(client, "https://example.com/x", nested)

        assert nested.exists(), "cache_dir should have been created"
        assert calls[0] == 1


# ---------------------------------------------------------------------------
# TestCacheIntegration — higher-level integration with edgar functions
# ---------------------------------------------------------------------------


class TestCacheIntegration:
    """Verify that EDGAR functions benefit from caching when
    ``cached_get`` is used in place of raw ``client.get``."""

    def test_search_companies_twice_makes_one_network_request(self, tmp_path: Path):
        """When ``search_companies`` is backed by ``cached_get``, two
        consecutive searches should produce only a single HTTP request
        for ``company_tickers.json``."""
        from sales_lead_research.discovery import search_companies

        payload = _fixture("company_tickers.json")
        call_count = [0]

        def handler(request: httpx.Request) -> httpx.Response:
            call_count[0] += 1
            return httpx.Response(200, content=payload)

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)

        # First search -- should hit network
        result_1 = search_companies("Apple", client, cache_dir=tmp_path)
        assert call_count[0] == 1

        # Second search (same or different query, same tickers endpoint)
        result_2 = search_companies("Microsoft", client, cache_dir=tmp_path)
        assert call_count[0] == 1, (
            "Second search_companies call should use cached tickers, not fetch again"
        )

        # Both should still return valid results
        assert len(result_1) >= 1
        assert len(result_2) >= 1
