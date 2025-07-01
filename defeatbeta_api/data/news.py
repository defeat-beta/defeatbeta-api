import textwrap
from dataclasses import dataclass

import pandas as pd
from rich.box import ROUNDED
from rich.console import Console
from rich.table import Table
from rich.text import Text


@dataclass
class News:
    def __init__(self, news: pd.DataFrame):
        self.news = news

    def get_news_list(self) -> pd.DataFrame:
        return self.news

    def get_news(self, uuid: str) -> pd.DataFrame:
        record = self._find_news(uuid)
        if record.empty:
            raise ValueError(f"No news found for uuid {uuid}")
        return record

    def print_pretty_table(self, uuid):
        record = self._find_news(uuid)
        if record.empty:
            raise ValueError(f"No news found for uuid: {uuid}")

        data = record.iloc[0]
        title = data['title']
        publisher = data['publisher']
        news_type = data['type']
        report_date = data['report_date']
        related_symbols = data['related_symbols']
        link = data['link']
        news = data['news']
        length = 120

        console = Console(width=length)
        main_table = Table(show_header=False, title=title, box=ROUNDED, padding=(0, 0))
        main_table.add_row(Text(textwrap.fill(publisher + " / " + report_date + " / " + news_type, int(length * 0.9)), justify="center"))
        main_table.add_row(Text(textwrap.fill("[" + ', '.join(related_symbols) + "]", int(length * 0.9)), justify="center"))
        main_table.add_row(Text(textwrap.fill(link, int(length * 0.9)), justify="center"))
        main_table.add_row("")
        for item in news:
            if item.get('highlight'):
                main_table.add_row(Text(textwrap.fill(item.get('highlight'), int(length * 0.99)), justify="left"))
            for line in item['paragraph'].split("\n"):
                main_table.add_row("")
                main_table.add_row(Text(textwrap.fill(line.strip(), int(length * 0.99)), justify="left"))
            main_table.add_row("")
        console.print(main_table, justify="left")


    def __str__(self):
        return self.news.to_string(columns=["uuid", "title", "publisher", "report_date", "type", "link"])

    def _find_news(self, uuid):
        mask = (self.news['uuid'] == uuid)
        record = self.news.loc[mask]
        return record


