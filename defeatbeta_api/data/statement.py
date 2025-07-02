from dataclasses import dataclass

import pandas as pd


@dataclass
class Statement:
    def __init__(self, data : pd.DataFrame, content : str):
        self.data = data
        self.table = content

    def print_pretty_table(self):
        print(self.table)

    def df(self):
        return self.data