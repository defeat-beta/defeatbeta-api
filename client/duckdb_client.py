import duckdb


class DuckDBClient:
    def __init__(self, db_path: str = ':memory:'):
        self.connection = duckdb.connect(database=db_path)

    def create_table(self, table_name: str, source_url: str):
        query = f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM '{source_url}'"
        self.connection.execute(query)

    def query(self, sql: str):
        return self.connection.execute(sql).fetchdf()

    def list_tables(self):
        return self.connection.execute("SHOW TABLES").fetchall()

    def describe_table(self, table_name: str):
        return self.connection.execute(f"DESCRIBE {table_name}").fetchdf()
