"""Generate one deterministic, versioned dataset before measuring either product."""

import hashlib
import json
from pathlib import Path

from benchmark.common import SYMBOLS, save_json


GENERATOR_DUCKDB = "2.0.0.dev2610011535"
FIXTURE_VERSION = "2026-01-01T00:00:00Z"


def generate(directory):
    import duckdb

    if duckdb.__version__ != GENERATOR_DUCKDB:
        raise RuntimeError(f"Fixture generation requires DuckDB {GENERATOR_DUCKDB}")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(config={"threads": 1})
    con.execute("CREATE TABLE symbols(symbol VARCHAR, ordinal INTEGER)")
    con.executemany("INSERT INTO symbols VALUES (?, ?)", [(symbol, i) for i, symbol in enumerate((*SYMBOLS, "SPY"))])
    identities = {}

    def write(name, query, compression="ZSTD"):
        path = directory / f"{name}.parquet"
        con.execute(f"COPY ({query}) TO ? (FORMAT PARQUET, COMPRESSION {compression}, ROW_GROUP_SIZE 2048)", [str(path)])
        data = path.read_bytes()
        footer_size = int.from_bytes(data[-8:-4], "little")
        identities[f"US/{name}.parquet"] = {
            "file_size": len(data), "footer_size": footer_size,
            "footer_sha256": hashlib.sha256(data[-footer_size - 8:-8]).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest()}

    try:
        write("stock_prices", """
            SELECT symbol, CAST(DATE '2025-12-31' - CAST(i AS INTEGER) AS VARCHAR) report_date,
                   50.0 + ordinal + (i % 1000) / 100.0 AS close,
                   49.0 + ordinal + (i % 1000) / 100.0 AS open,
                   51.0 + ordinal + (i % 1000) / 100.0 AS high,
                   48.0 + ordinal + (i % 1000) / 100.0 AS low,
                   CAST(1000000 + i AS BIGINT) volume
            FROM symbols CROSS JOIN range(32768) t(i)
            WHERE i < 32768 / (1 + ordinal % 4) ORDER BY symbol, report_date
        """, "UNCOMPRESSED")
        write("stock_profile", """SELECT symbol, symbol || ' Corporation' company,
            'Technology' sector, 'Software' industry, 'United States' country,
            repeat('Company profile. ', 100 + ordinal * 10) description FROM symbols ORDER BY symbol""")
        write("stock_sec_filing", """SELECT symbol, CAST(DATE '2025-01-01' + CAST(i AS INTEGER) AS VARCHAR) filing_date,
            '10-K' form_type, 'https://example.test/filing/' || i url,
            repeat(md5(symbol || i), 20) description FROM symbols, range(128) t(i) ORDER BY symbol, i""")
        for name, field in (("stock_officers", "age"), ("stock_earning_calendar", "eps_estimate"),
                            ("stock_split_events", "split_ratio"), ("stock_dividend_events", "dividend"),
                            ("stock_tailing_eps", "tailing_eps"), ("stock_shares_outstanding", "shares_outstanding")):
            value = "1000000.0 + ordinal * 10000" if field == "shares_outstanding" else "2.0 + ordinal / 100.0"
            write(name, f"""SELECT symbol, CAST(DATE '1900-01-01' + CAST(i * 365 AS INTEGER) AS VARCHAR) report_date,
                 {value} AS {field} FROM symbols, range(126) t(i)
                 WHERE i % (1 + ordinal % 3) = 0 ORDER BY symbol, report_date""")
        write("stock_statement", """SELECT symbol, '2025-09-30' report_date, item_name,
                 1000.0 + ordinal item_value, finance_type, period_type
            FROM symbols,
                 (VALUES ('quarterly'), ('annual')) periods(period_type),
                 (VALUES ('income_statement', 'total_revenue'), ('income_statement', 'net_income'),
                         ('income_statement', 'gross_profit'), ('balance_sheet', 'current_assets'),
                         ('balance_sheet', 'total_assets'), ('cash_flow', 'operating_cash_flow'),
                         ('cash_flow', 'free_cash_flow'), ('cash_flow', 'depreciation_amortization_depletion'))
                 items(finance_type, item_name) ORDER BY symbol, finance_type, period_type, item_name""")
        write("stock_revenue_breakdown", """SELECT symbol, 'revenue-by-segment' breakdown,
            'Revenue by Segment' breakdown_name, 'quarterly' period_type, '2025-09-30' report_date,
            'Software' series_name, 1000.0 + ordinal value, 'CURRENCY' value_type, 'USD' currency
            FROM symbols ORDER BY symbol""")
        write("stock_earning_call_transcripts", """SELECT symbol, 2025 fiscal_year, 3 fiscal_quarter,
            '2025-10-15' report_date,
            list_transform(range(64), lambda p: struct_pack(paragraph_number := p,
                speaker := 'Speaker ' || p % 4, content := repeat(md5(symbol || p), 100))) transcripts
            FROM symbols ORDER BY symbol""")
        write("stock_news", """SELECT symbol || '-article-' || i AS uuid, symbol,
            'Quarterly business update' title, 'Fixture News' publisher, '2025-10-15' report_date,
            'STORY' type, 'https://example.test/article/' || i link,
            [struct_pack(highlight := 'Business update', paragraph := repeat(md5(symbol || i), 200))] news
            FROM symbols, range(4) t(i) ORDER BY symbol, i""")
        spec = {"update_time": FIXTURE_VERSION, "footer_index": identities}
        save_json(directory / "spec.json", spec)
        manifest = {"generator_duckdb": GENERATOR_DUCKDB, "version": 1, "files": identities,
                    "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        save_json(directory / "fixture.json", manifest)
        return manifest
    finally:
        con.close()


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "fixture.json").read_text())
    for relative, identity in manifest["files"].items():
        path = directory / Path(relative).name
        if hashlib.sha256(path.read_bytes()).hexdigest() != identity["sha256"]:
            raise ValueError(f"Fixture checksum mismatch: {relative}")
    return manifest
