import pandas as pd


class Statement:
    def __init__(self, data : pd.DataFrame, content : str):
        self.data = data
        self.table = content

    def get_table(self):
        return self.table

    def get_data(self):
        return self.data