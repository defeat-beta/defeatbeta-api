# Raw benchmark records

- `local/<run-id>.json`: one file per invocation, ignored by Git. Completed runs retain the newest 100 within 30 days. Cleanup runs after each benchmark; recent unfinished runs are protected, and unfinished records older than 30 days expire.
- `archive/NNN_<name>.json`: evidence cited by an experiment document, tracked in Git and never automatically deleted or overwritten. Keep unsuccessful experiments too.
- Numbered documents in `../docs/` serve as the experiment index. There is no generated summary table.

Run from the project root (one file per invocation, unlimited runs):

```bash
./.venv/bin/python benchmark/bench.py run --runs 3 --tag <attempt-tag> --revision <sha>
```

Archive a satisfying run from the project root (archiving does not run queries):

```bash
# Archive the latest local run for a tag:
./.venv/bin/python benchmark/bench.py archive --tag <attempt-tag> --name 001_connection_reuse
# Or archive a specific earlier run (recommended when the same tag ran multiple times):
./.venv/bin/python benchmark/bench.py archive --source benchmark/results/local/<run-id>.json --name 001_connection_reuse
```

Link the archive from the experiment document, then commit both files. Archiving does not run queries.

JSON format version 2 uses `shared` entries and `$ref` references for repeated configuration and result metadata. `records.unpack_reports()` expands the records. The baseline archive preserves all five legacy reports, including failed attempts, without changing measurements.
