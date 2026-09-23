from typing import Dict, Any
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from defeatbeta_api.utils.const import tables


class HuggingFaceClient:
    def __init__(self, max_retries: int = 3, timeout: int = 30):
        self.base_url = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data"
        self.timeout = timeout
        self.session = requests.Session()

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    def _make_request(self, url: str) -> Dict[str, Any]:
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "HuggingFaceClient/1.0"},
                verify=True
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON response from {url}: {e}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Request to {url} failed: {e}")

    def get_data_update_time(self) -> str:
        url = f"{self.base_url}/resolve/main/spec.json"
        data = self._make_request(url)
        if "update_time" not in data:
            raise ValueError("Missing 'update_time' field in spec.json")
        return data["update_time"]

    def resolve_cdn_url(self, resolve_url: str, proxies=None, timeout: int = 20) -> str:
        """Resolve a pinned HF URL to its signed CDN URL with one HEAD.

        Follows no redirects; HF answers 302 with the time-limited (currently
        ~1 h) signed CDN URL in `Location`. Raises on unexpected status or a
        missing Location header so callers can fall back to the resolve URL.
        `proxies` follows the `requests` convention; None means environment.
        """
        try:
            response = self.session.head(
                resolve_url, timeout=timeout, allow_redirects=False,
                headers={"User-Agent": "HuggingFaceClient/1.0"},
                **({"proxies": proxies} if proxies is not None else {}),
            )
        except Exception as e:
            raise RuntimeError(f"Resolve HEAD to {resolve_url} failed: {e}")
        if response.status_code not in (301, 302, 303, 307, 308):
            raise RuntimeError(
                f"Resolve HEAD to {resolve_url} returned unexpected status "
                f"{response.status_code}"
            )
        location = response.headers.get("Location")
        if not location:
            raise RuntimeError(f"Redirect without Location header for {resolve_url}")
        parts = urlsplit(location)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise RuntimeError(f"Unsafe redirect Location for {resolve_url}")
        return location

    def get_url_path(self, table: str) -> str:
        if table not in tables:
            raise ValueError(
                f"Invalid table '{table}'. Valid options are: {', '.join(tables)}"
            )
        return f"{self.base_url}/resolve/main/data/US/{table}.parquet"
