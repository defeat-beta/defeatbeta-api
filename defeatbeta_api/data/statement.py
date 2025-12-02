from dataclasses import dataclass

import pandas as pd
from rich.console import Console

from defeatbeta_api.utils.util import in_notebook
try:
    from IPython.core.display import display, HTML
except ImportError:
    from IPython.display import display
    from IPython.core.display import HTML


@dataclass
class Statement:
    def __init__(self, data : pd.DataFrame, content : str):
        self.data = data
        self.table = content

    def print_pretty_table(self):
        if in_notebook():
            console = Console(record=True)
            console.print(self.table)
            html = console.export_html(inline_styles=True)
            HTML(html)
        else:
            print(self.table)

    def df(self):
        return self.data