"""Requests-compatible metadata calls backed by the shared HTTPX transport."""

import json
import time
from urllib.parse import urlsplit

import httpx
import requests

from defeatbeta_api.client.shared_resources import SharedHttpClient


class MetadataResponse:
    def __init__(self, response):
        self.response = response
        self.status_code = response.status_code
        self.headers = response.headers

    def json(self):
        try:
            return self.response.json()
        except json.JSONDecodeError as exc:
            raise requests.exceptions.JSONDecodeError(exc.msg, exc.doc, exc.pos) from exc

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP status {self.status_code}")


class MetadataSession:
    """Keep metadata retry policy out of the shared data transport."""

    def __init__(self, max_retries=3):
        self.max_retries = max_retries
        self.trust_env = True
        self.closed = False

    def request(self, method, url, *, proxies=None, verify=True, allow_redirects=True,
                timeout=30, **kwargs):
        if self.closed:
            raise RuntimeError("Metadata session is closed")
        if verify is not True:
            raise ValueError("Metadata requests require TLS verification")
        proxy = None if proxies is None else (proxies.get(urlsplit(url).scheme)
                                              or proxies.get("all") or "")
        client = SharedHttpClient(proxy=proxy, timeout=timeout, trust_env=self.trust_env)
        for attempt in range(self.max_retries + 1):
            try:
                response = client.request(method, url, follow_redirects=allow_redirects, **kwargs)
                if response.status_code not in (500, 502, 503, 504) or attempt == self.max_retries:
                    return MetadataResponse(response)
            except httpx.RequestError as exc:
                if attempt == self.max_retries:
                    raise requests.RequestException(type(exc).__name__) from exc
            if attempt:
                time.sleep(2 ** attempt)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def head(self, url, **kwargs):
        kwargs.setdefault("allow_redirects", False)
        return self.request("HEAD", url, **kwargs)

    def close(self):
        self.closed = True
