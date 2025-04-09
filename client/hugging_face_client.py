import requests

from data.const import TABLES


class HuggingFaceClient:
    def __init__(self):
        self.base_url = "https://huggingface.co/datasets/bwzheng2010/yahoo-finance-data"

    def __get_latest_data_tag(self) -> str:
        url = f"{self.base_url}/resolve/main/spec.json"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            latest_data_tag = data.get("latest_data_tag", None)
            if latest_data_tag:
                return latest_data_tag
            else:
                raise ValueError("latest_data_tag not found in the spec.json file")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch spec.json: {e}")

    def get_url_path(self, table: str):
        if table not in TABLES:
            raise ValueError(f"Table '{table}' is not valid. Please choose from: {', '.join(TABLES)}")

        latest_data_tag = self.__get_latest_data_tag()
        url = f"{self.base_url}/resolve/{latest_data_tag}/{table}/{table}.parquet"
        return url