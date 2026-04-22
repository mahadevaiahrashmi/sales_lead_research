# agent-notes: { ctx: "file-based HTTP response cache for EDGAR requests", deps: ["httpx"], state: active, last: "sato@2026-04-16" }
"""Local file cache for EDGAR HTTP responses.

Hashes URLs to filenames and stores response bytes under a configurable
directory. Each entry carries a TTL; expired entries are re-fetched.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx


def cached_get(
    client: httpx.Client,
    url: str,
    cache_dir: Path,
    ttl_hours: int = 24,
) -> httpx.Response:
    """Fetch *url* via *client*, caching the response body under *cache_dir*."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.sha256(url.encode()).hexdigest()
    cache_file = cache_dir / url_hash

    if cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours < ttl_hours:
            return httpx.Response(200, content=cache_file.read_bytes())

    resp = client.get(url)
    resp.raise_for_status()
    cache_file.write_bytes(resp.content)
    return resp
