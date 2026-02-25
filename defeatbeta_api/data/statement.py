from dataclasses import dataclass

import pandas as pd

from defeatbeta_api.utils.util import in_notebook

try:
    from IPython.core.display import display, HTML
except ImportError:
    from IPython.display import display
    from IPython.core.display import HTML


@dataclass
class Statement:
    def __init__(self, data: pd.DataFrame, content: str, row_meta: list = None):
        self.data = data
        self.table = content
        self.row_meta = row_meta or []  # list of {"indent": int, "is_section": bool}

    def print_pretty_table(self):
        if in_notebook():
            html = (f"<div style=\"font-family: 'JetBrains Mono', Consolas, monospace; white-space: pre;\">\n"
                        f"{self.table}"
                    f"\n</div>")
            display(HTML(html))
        else:
            print(self.table)

    def df(self):
        return self.data