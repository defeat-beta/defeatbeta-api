from typing import Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from defeatbeta_api.utils.const import tables


class HuggingFaceClient:
    def __init__(self, max_retries: int = 3, timeout: int = 30):
        self.base_url = "https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data"
        self.timeout = timeout
        self.session = requests.Session()

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"]
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

    def get_url_path(self, table: str) -> str:
        if table not in tables:
            raise ValueError(
                f"Invalid table '{table}'. Valid options are: {', '.join(tables)}"
            )
        return f"{self.base_url}/resolve/main/data/{table}.parquet"
