import requests

from utils.const import tables


class HuggingFaceClient:
    def __init__(self):
        self.base_url = "https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data"

    def get_data_update_time(self) -> str:
        url = f"{self.base_url}/resolve/main/spec.json"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            update_time = data.get("update_time", None)
            if update_time:
                return update_time
            else:
                raise ValueError("update_time not found in the spec.json file")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch spec.json: {e}")

    def get_url_path(self, table: str):
        if table not in tables:
            raise ValueError(f"Table '{table}' is not valid. Please choose from: {', '.join(tables)}")

        url = f"{self.base_url}/resolve/main/data/{table}.parquet"
        return url