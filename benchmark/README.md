# End-to-end performance benchmarks

The main benchmark measures the complete public query workload against current
Hugging Face data. Its unit of work is one frozen ticker/operation pair. There
is one main framework, with no protocol experiment or bandwidth score.

Use **Actions > End-to-end performance benchmark > Run workflow**:

| Input | Meaning |
| --- | --- |
| `candidate` | Git ref under evaluation, usually `main`. Resolved once to a full commit. |
| `baseline` | Optional old Git ref. Leave empty to establish the first standalone report. |
| `rounds` | Repetitions per phase. One is development evidence; finalization requires at least six even rounds. |

The initial 16-ticker calibration needed 29 minutes for cold latency alone.
The default sample is now eight well-known issuers approved by the maintainer,
with query availability checked before timing. Full-matrix duration and release
repetitions still require validation. The initial calibration is retained in
[Actions](https://github.com/defeat-beta/defeatbeta-api/actions/runs/38715579086).
Its temporary workflow and runner have been removed; use the main framework for
further measurements. Incomplete phases cannot become complete-coverage claims.
See the [workload contract](e2e/README.md).

## Workload and timing

The fixed sample is AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, and WMT. It is
not a statistically representative sample of the full ticker universe. Discovery
freezes all public query operations and parameters before measurement.
Excel export and diagnostic output are excluded;
`dcf_data()` is included. News and transcript wrappers expand into actual list
and body retrieval. Missing source bodies remain explicit not-applicable tasks.

The complete Cartesian workload is unchanged across worker counts:

| Metric | Scenarios | Preparation |
| --- | --- | --- |
| Individual API latency | Cold and cached | Each ticker/method gets its own empty query cache; cached calls first warm that exact task. |
| Whole-workload throughput | 1, 4, 16, 64, 128 workers, each cold and cached | Every worker count shares the same complete workload, executing each task once. |

Cold throughput starts with one empty shared query cache and allows natural
reuse inside the batch. Cached throughput warms every ticker/method first and
requires zero query-data cache misses during measurement. Capacity is deliberately
generous: memory or disk hits qualify as local hits. Physical disk space remains
a validity condition, rather than a guarantee from the logical cache budget.

API timing ends after full result materialization. Ticker initialization is
recorded separately; warmup and result hashing are outside API timing. Batch
time includes executor startup, scheduling, waiting, and completion. The
report retains every ticker/method latency plus batch duration, successful
calls/second, P95, errors, applicability, and result fingerprints.

## GitHub execution and reports

Discovery freezes one workload for all twelve phases. Phases use separate
GitHub-hosted jobs to avoid requiring one uninterrupted multi-hour runner. Within
each phase the baseline and candidate run sequentially on the same runner, in
alternating AB/BA order. Each product uses isolated source and dependencies from
its declared revision. Different phases can have different hardware; compare
paired changes rather than absolute numbers across jobs.

The report job verifies that every phase, round, version, and applicable task is
present. Missing tasks, errors, invalid cache hits, changed harnesses or dependency
locks, and same-input result mismatches invalidate acceptance. Daily data changes
are accepted and recorded; affected pairs remain inconclusive.

Every run produces development evidence in Actions Summary and 30-day artifacts.
It does not commit a report or attach anything to a Release. The first standalone
report establishes procedure and provenance, not a permanent historical speed
baseline. Future comparisons rerun old and new revisions on the same runner.

For an approved release, use **Finalize release performance report**, selecting a
complete successful manual run and an existing Release tag identifying the
candidate commit. It validates all twelve phases, the declared sample, six even
rounds, sources, dependencies, harness checksums, and one workflow attempt.
Finalization renders saved data without executing downloaded code or rerunning
queries. It attaches `performance-report.md` and `performance-evidence.tar.gz`
to the existing Release, refusing to overwrite assets. See
[report lifecycle](results/README.md) and [design](DESIGN.md).

## Local correctness and reproduction

Local execution is for correctness; official timings come from GitHub. Use
Python 3.11.10 in a dedicated environment:

```sh
python -m pip install -r benchmark/requirements.txt
python -m benchmark discover --candidate HEAD --output /tmp/e2e-plan-001
python -m benchmark compare --candidate HEAD \
  --plan /tmp/e2e-plan-001/plan.json --output /tmp/e2e-first-001 --rounds 1
```

Add `--baseline <old-ref>` for a comparison. `--phase throughput.cached.16`
selects one phase for development; partial runs cannot be finalized. Output
directories must be new. Reuse isolated environments using `python -m benchmark
run --experiment PATH --plan PLAN`. Changes to product sources, installed
dependencies, or the frozen harness require a fresh experiment.

`python -m benchmark report RESULTS.json` renders saved evidence only. `collect`
combines exactly one copy of all twelve phase records. For archived reproduction,
copy the bundled `harness/benchmark` into a disposable repository checkout,
then use the recorded commits and `--baseline-lock` / `--candidate-lock` with
the bundled dependency locks. Current remote data may
have changed because historical Hugging Face revisions are not retained.

## Layout

| Location | Purpose |
| --- | --- |
| `benchmark.py`, `worker.py` | Isolated product environments and paired execution. |
| [e2e/](e2e/) | Workload discovery, cache preparation, full-workload execution. |
| `report.py`, `publication.py` | Evidence validation, reports, and explicit release finalization. |
| [support/](support/) | Synthetic Parquet and local TLS helpers for offline correctness tests. |
| [workloads/](workloads/), [diagnostics/](diagnostics/) | Engineering tools still used for targeted regressions; outside the main report. |
| [reports/](reports/README.md), [results/archive/](results/archive/) | Historical engineering and release evidence, retained unchanged. |

The old 20-operation suite, burst scheduler, three-state report rules, and
suite-specific attribution workflow have been removed. Protocol and network
investigations do not form a second official benchmark. These developer tools
are not installed as part of the public `defeatbeta_api` package.
