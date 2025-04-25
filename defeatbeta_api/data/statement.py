import pandas as pd


class Statement:
    def __init__(self, data : pd.DataFrame, content : str):
        self.data = data
        self.table = content

    def pretty_table(self):
        return self.table

    def df(self):
        return self.data