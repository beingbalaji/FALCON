"""HTTP helpers: a cached JSON client for public APIs and an SSRF-safe page fetcher."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import sqlite3
import threading
import time
from urllib.parse import urlencode, urlparse

import requests

from .config import settings

_lock = threading.Lock()
_session = requests.Session()
_session.headers.update({"User-Agent": settings.user_agent})

CACHE_TTL_SECONDS = 7 * 24 * 3600


def _cache():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.data_dir / "http_cache.db", timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, at REAL, body TEXT)")
    return conn


def get_json(url: str, params: dict, use_cache: bool = True) -> dict:
    """GET a JSON API with a small on-disk cache so repeated checks are fast and polite."""
    full = f"{url}?{urlencode(sorted(params.items()))}"
    key = hashlib.sha256(full.encode()).hexdigest()
    if use_cache:
        with _lock, _cache() as conn:
            row = conn.execute("SELECT at, body FROM cache WHERE key=?", (key,)).fetchone()
        if row and time.time() - row[0] < CACHE_TTL_SECONDS:
            return json.loads(row[1])
    response = _session.get(url, params=params, timeout=settings.request_timeout)
    response.raise_for_status()
    data = response.json()
    if use_cache:
        with _lock, _cache() as conn:
            conn.execute("REPLACE INTO cache VALUES (?, ?, ?)", (key, time.time(), json.dumps(data)))
    return data


class UnsafeURLError(ValueError):
    pass


def _check_public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURLError("That website address could not be found.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURLError("Only public websites can be fetched.")


def fetch_public_page(url: str, max_bytes: int = 2_000_000) -> tuple[str, str]:
    """Fetch an http(s) page on the public internet. Returns (final_url, html).

    Blocks private, loopback and link-local addresses (including cloud metadata
    endpoints) on every redirect hop.
    """
    for _ in range(5):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise UnsafeURLError("Enter a full http:// or https:// address.")
        if parsed.username or parsed.password:
            raise UnsafeURLError("Addresses with embedded credentials are not allowed.")
        _check_public_host(parsed.hostname)
        response = _session.get(url, timeout=settings.request_timeout, allow_redirects=False, stream=True)
        if response.is_redirect:
            url = requests.compat.urljoin(url, response.headers.get("Location", ""))
            continue
        response.raise_for_status()
        if "html" not in response.headers.get("Content-Type", "text/html"):
            raise UnsafeURLError("That address does not point to a web page.")
        body = response.raw.read(max_bytes, decode_content=True)
        return url, body.decode(response.encoding or "utf-8", errors="replace")
    raise UnsafeURLError("Too many redirects.")
