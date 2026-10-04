from typing import Dict, Any
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from defeatbeta_api.utils.const import tables


class HuggingFaceClient:
    def __init__(self, max_retries: int = 3, timeout: int = 30, http_proxy: str = None):
        self.base_url = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data"
        self.timeout = timeout
        self.http_proxy = http_proxy
        self.session = requests.Session()
        self.dataset_spec: Dict[str, Any] = {}

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    def _make_request(self, url: str) -> Dict[str, Any]:
        try:
            proxy_options = (
                {"proxies": {"http": self.http_proxy, "https": self.http_proxy}}
                if self.http_proxy else {}
            )
            response = self.session.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "HuggingFaceClient/1.0"},
                verify=True,
                **proxy_options,
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
        self.dataset_spec = data
        return data["update_time"]

    def resolve_cdn_url(self, resolve_url: str, proxies=None, timeout: int = 20) -> str:
        """Resolve a pinned HF URL to its signed CDN URL with one HEAD."""
        return self.resolve_cdn_info(resolve_url, proxies, timeout)[0]

    def resolve_cdn_info(self, resolve_url: str, proxies=None, timeout: int = 20):
        """Resolve dataset objects, including Hugging Face's relative JSON redirects."""
        current_url = resolve_url
        for _ in range(5):
            try:
                response = self.session.head(
                    current_url, timeout=timeout, allow_redirects=False,
                    headers={"User-Agent": "HuggingFaceClient/1.0"},
                    **({"proxies": proxies} if proxies is not None else {}),
                )
            except Exception as e:
                raise RuntimeError(f"Resolve HEAD to {resolve_url} failed: {e}") from e
            if response.status_code == 200:
                size_header = response.headers.get("Content-Length")
                try:
                    size = int(size_header) if size_header is not None else None
                except ValueError:
                    size = None
                return current_url, size if size is not None and size > 0 else None
            if response.status_code not in (301, 302, 303, 307, 308):
                raise RuntimeError(
                    f"Resolve HEAD to {resolve_url} returned unexpected status "
                    f"{response.status_code}"
                )
            location = response.headers.get("Location")
            if not location:
                raise RuntimeError(f"Redirect without Location header for {resolve_url}")
            target = urljoin(current_url, location)
            parts = urlsplit(target)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
                raise RuntimeError(f"Unsafe redirect Location for {resolve_url}")
            if parts.hostname == "huggingface.co":
                current_url = target
                continue
            linked_size = response.headers.get("X-Linked-Size")
            try:
                size = int(linked_size) if linked_size is not None else None
            except ValueError:
                size = None
            return target, size if size is not None and size > 0 else None
        raise RuntimeError(f"Too many redirects for {resolve_url}")

    def get_url_path(self, table: str) -> str:
        if table not in tables:
            raise ValueError(
                f"Invalid table '{table}'. Valid options are: {', '.join(tables)}"
            )
        return f"{self.base_url}/resolve/main/data/US/{table}.parquet"
