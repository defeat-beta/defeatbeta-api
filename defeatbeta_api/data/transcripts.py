import pandas as pd
from tabulate import tabulate


def _unnest(record: pd.DataFrame) -> pd.DataFrame:
    transcripts_data = record["transcripts"].iloc[0]
    df_paragraphs = pd.json_normalize(transcripts_data)
    return df_paragraphs

class Transcripts:
    def __init__(self, transcripts: pd.DataFrame):
        self.transcripts = transcripts

    def get_transcripts_list(self) -> pd.DataFrame:
        return self.transcripts

    def get_transcript(self, fiscal_year: int, fiscal_quarter: int) -> pd.DataFrame:
        record = self._find_transcripts(fiscal_quarter, fiscal_year)
        if record.empty:
            raise ValueError(f"No transcript found for FY{fiscal_year} Q{fiscal_quarter}")
        df_paragraphs = _unnest(record)
        return df_paragraphs

    def pretty_table(self, fiscal_year: int, fiscal_quarter: int) -> str:
        record = self._find_transcripts(fiscal_quarter, fiscal_year)
        if record.empty:
            raise ValueError(f"No transcript found for FY{fiscal_year} Q{fiscal_quarter}")
        report_date = record["report_date"].iloc[0]
        df_paragraphs = _unnest(record)
        title = f"Earnings Call Transcripts FY{fiscal_year} Q{fiscal_quarter} (Reported on {report_date})\n"
        table = tabulate(df_paragraphs, headers="keys", tablefmt="grid", showindex=False)
        return title + table

    def __str__(self):
        return self.transcripts.to_string(columns=["symbol", 'fiscal_year', "fiscal_quarter", "report_date"])

    def _find_transcripts(self, fiscal_quarter, fiscal_year):
        mask = (self.transcripts['fiscal_year'] == fiscal_year) & \
               (self.transcripts['fiscal_quarter'] == fiscal_quarter)
        record = self.transcripts.loc[mask]
        return record