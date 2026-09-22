# Raw benchmark records

- `local/<run-id>.json`: one file per invocation, ignored by Git. Completed runs retain the newest 100 within 30 days. Cleanup runs after each benchmark; recent unfinished runs are protected, and unfinished records older than 30 days expire.
- `archive/NNN_<name>.json`: evidence cited by an experiment document, tracked in Git and never automatically deleted or overwritten. Keep unsuccessful experiments too.
- Numbered documents in `../docs/` serve as the experiment index. There is no generated summary table.

Archive an existing record from the project root:

```bash
./.venv/bin/python benchmark/bench.py --archive benchmark/results/local/<run-id>.json --name 001_connection_reuse
```

Link the archive from the experiment document, then commit both files. Archiving does not run queries.

JSON format version 2 uses `shared` entries and `$ref` references for repeated configuration and result metadata. `records.unpack_reports()` expands the records. The baseline archive preserves all five legacy reports, including failed attempts, without changing measurements.
