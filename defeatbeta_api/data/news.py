import textwrap
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from rich.box import ROUNDED
from rich.console import Console
from rich.table import Table
from rich.text import Text

from defeatbeta_api.client.duckdb_client import DuckDBClient
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.data.sql.sql_loader import load_sql
from defeatbeta_api.utils.const import stock_news
from defeatbeta_api.utils.util import in_notebook

try:
    from IPython.core.display import display, HTML
except ImportError:
    from IPython.display import display
    from IPython.core.display import HTML


@dataclass
class News:
    """
    Lazy accessor for a ticker's financial news.

    Two SQL paths are used so the inline `news` paragraph array is only
    fetched on demand (it accounts for ~99% of the parquet row size):

      - `select_news_list_by_symbol`  → metadata-only list (no `news` column)
      - `select_news_by_uuid`         → single article (1 row, with paragraphs);
        filters by both uuid and ticker because the same article appears once
        per related ticker in the parquet.

    The metadata list is memoised on the instance; article bodies are not
    cached here because DuckDB's httpfs cache already handles repeat reads.
    """

    def __init__(
        self,
        ticker: str,
        duckdb_client: DuckDBClient,
        huggingface_client: HuggingFaceClient,
        log_level: str,
    ):
        self.ticker = ticker
        self.duckdb_client = duckdb_client
        self.huggingface_client = huggingface_client
        self.log_level = log_level
        self._list_cache: Optional[pd.DataFrame] = None

    def get_news_list(self) -> pd.DataFrame:
        if self._list_cache is None:
            url = self.huggingface_client.get_url_path(stock_news)
            sql = load_sql("select_news_list_by_symbol", ticker=self.ticker, url=url)
            self._list_cache = self.duckdb_client.query(sql)
        return self._list_cache

    def get_news(self, uuid: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_news)
        sql = load_sql(
            "select_news_by_uuid",
            uuid=uuid,
            ticker=self.ticker,
            url=url,
        )
        record = self.duckdb_client.query(sql)
        if record.empty:
            raise ValueError(f"No news found for uuid {uuid}")
        return record

    def print_pretty_table(self, uuid):
        record = self.get_news(uuid)
        data = record.iloc[0]
        title = data['title']
        publisher = data['publisher']
        news_type = data['type']
        report_date = data['report_date']
        related_symbols = data['symbol']
        link = data['link']
        news = data['news']
        length = 120

        main_table = Table(show_header=False, title=title, box=ROUNDED, padding=(0, 0))
        main_table.add_row(Text(textwrap.fill(publisher + " / " + report_date + " / " + news_type, int(length * 0.9)), justify="center"))
        main_table.add_row(Text(textwrap.fill("[" + related_symbols + "]", int(length * 0.9)), justify="center"))
        main_table.add_row(Text(textwrap.fill(link, int(length * 0.9)), justify="center"))
        main_table.add_row("")
        for item in news:
            if item.get('highlight'):
                main_table.add_row(Text(textwrap.fill(item.get('highlight'), int(length * 0.99)), justify="left"))
            for line in item['paragraph'].split("\n"):
                main_table.add_row("")
                main_table.add_row(Text(textwrap.fill(line.strip(), int(length * 0.99)), justify="left"))
            main_table.add_row("")
        if in_notebook():
            console = Console(record=True)
            console.print(main_table)
            html = console.export_html(inline_styles=True)
            HTML(html)
        else:
            console = Console(width=length)
            console.print(main_table, justify="left")

    def __str__(self):
        return self.get_news_list().to_string(
            columns=["uuid", "title", "publisher", "report_date", "type", "link"]
        )
