# Performance benchmarks

The replacement sampled end-to-end contract is being calibrated in
[e2e/](e2e/README.md). Run **End-to-end benchmark calibration** for the fixed
16-ticker, all-query-method workload. Calibration has a 30-minute budget and
does not generate release evidence. The paired workflow below still describes
the existing suite until calibration establishes a practical replacement size.

GitHub Actions is the primary entry point. Each experiment runs explicit baseline
and candidate commits sequentially on the same runner, with isolated product
environments and one workload. The baseline is reproducible source, dependencies,
and procedure, rather than a historical duration from a developer's network.

See [design](DESIGN.md), [report lifecycle](results/README.md), and
[correctness tests](../test/README.md). Application users can start with
[local caching](../doc/api/Local_File_Cache.md) and the
[HTTP connection pool](../doc/api/HTTP_Connection_Pool.md).

## Development comparisons

Open **Actions > Paired performance benchmark > Run workflow**:

| Input | Meaning |
| --- | --- |
| `baseline` | Explicit Git ref, for example `release-0.0.62`. |
| `candidate` | Revision under evaluation, usually `main`. |
| `suite` | `smoke` for framework checks; `release` for all 70 default-policy cases. |
| `rounds` | Paired repetitions; at least six even rounds for release evidence. |

Refs are resolved once before the jobs start. Fixed-data regression and
live-service regression get separate runners; A/B always share one job and host. Do not
compare absolute durations across jobs. Pull requests run the short controlled
suite. Manual runs also query the real Hugging Face service.

| Experiment | Purpose | Data and network |
| --- | --- | --- |
| Fixed-data regression (`controlled`) | Detect code regressions against repeatable inputs. | Deterministic synthetic files, local TLS server with H2. |
| Live-service regression (`live`) | Evaluate end-to-end latency, concurrency, failures, and resources. | Current Hugging Face files through the normal product route. |

Both exercise the candidate's real H2 transport. Live-service measurements already
include H2 downloads; fixed-data measurements isolate changes from public-network
and daily-data variation. Historical baselines retain their original protocol
behavior. There is no forced-H1 benchmark variant or protocol selection option.

Every run is **development evidence**, including runs of the `release` suite.
Read the Summary and download Artifacts, retained for 30 days. The workflow
neither commits reports nor uploads Release attachments. Public-repository
Actions output is still visible to readers; development status is not privacy.

The candidate and fixture generator currently use DuckDB `2.0.0.dev2610011535`.
Each measured product uses its own declared dependencies: the 0.0.62 baseline
therefore uses DuckDB 1.5.3 in its isolated environment. This comparison includes
the dependency upgrade and intentional changes to product defaults.

The standard workflow preserves each product's native DuckDB file-cache setting.
It records that setting before preparation and during queries. Both products also
use the project's `DatasetCacheFileSystem`; this is separate from DuckDB's native
cache and does not use the `cache_httpfs` extension.

## Finalize a release report

Review the full run, then open **Actions > Finalize release performance report
> Run workflow** on the default branch. Supply `source_run_id` and `release_tag`.
The selected run must be a successful manual benchmark with both experiments
in its latest attempt. The existing GitHub Release tag must point to the exact
measured candidate commit. A draft Release can be used before publication.

Finalization uploads `performance-report.md` and `performance-evidence.tar.gz`.
It validates saved evidence without rerunning queries, discarding slower cases,
replacing assets, changing tags, or publishing software. The bundle retains raw
JSON, readable reports, dependency locks, the harness, and checksums. Promote
accepted evidence before its Actions artifacts expire.

Missing cases, short samples, different candidates, mixed attempts/dependencies,
and missing fixed-data or live-service evidence are rejected. If jobs need retrying, rerun all
jobs to preserve one attempt identity. Earlier attempts remain in Actions history.
Successful validation does not assert that every workload improved.

## Local reproduction

Use a dedicated Python 3.11.10 environment and run from the repository root:

```sh
python -m pip install -r benchmark/requirements.txt
python -m benchmark compare \
  --baseline release-0.0.62 --candidate HEAD \
  --output /tmp/defeatbeta-comparison-001 \
  --mode controlled --suite smoke --rounds 2 \
  --network-label "Local loopback TLS"
```

The output directory must be new. Preparation exports commits and creates two
virtual environments; uncommitted product edits are not measured. Controlled
mode uses a separate TLS server, verified test CA, HTTP/2, and no
proxy. It requires `openssl`. Live mode uses current Hugging Face files and the
normal environment proxy policy. Reuse a prepared environment with:

```sh
python -m benchmark run --experiment /tmp/defeatbeta-comparison-001 \
  --mode controlled --suite release --rounds 6
python -m benchmark report /path/to/results.json
```

Each run gets a new timestamped directory. Changes to the harness or installed
dependencies require a new experiment. The report command reads saved evidence
without requests. For archived reproduction, use the recorded source commits
and frozen `harness/benchmark` directory in a disposable checkout. Install
`harness-dependencies.lock` into the harness environment, then pass
`--baseline-lock /path/to/baseline-dependencies.lock` and
`--candidate-lock /path/to/candidate-dependencies.lock` to `compare` or `prepare`.
These optional inputs constrain reproduction to the original dependencies.
Public data reproduction uses current data because old Hugging Face revisions
may have been removed.

The full default-policy suite covers 20 methods in three states, plus ten mixed concurrency
cases, using a fixed 32-symbol corpus and seeded order. It covers direct reads,
statements, composite calculations, transcript bodies, and news bodies. The
saved manifest identifies methods without independent performance measurements.

Default states are first use, memory-warm reuse, and disk-warm restart. Mixed
queries begin in a fresh process without query-data warmup and preserve natural
cache sharing during the batch. To isolate the project cache locally, add
`--cache-policy project-only` to `compare` or `run`. That diagnostic disables
DuckDB's native file cache and also includes metadata-ready calls, retaining the
90-case diagnostic suite. Its policy is part of the workload identity and every
measurement. It cannot be finalized as default-behavior release evidence.

Read latency, completion rate, CPU, memory, bytes, failures, and pool waits
together. Application bytes/s is not wire bandwidth. Keep home, office, mobile,
and GitHub environments separate when interpreting results.

## Regression attribution

The manual **Performance regression attribution** workflow separates an engine
upgrade from project changes. It runs three arms sequentially on each runner:
baseline source with declared dependencies, baseline source with the candidate
interpreter/dependencies, and candidate source with declared dependencies.
Non-DuckDB dependency locks must match. The middle arm is diagnostic only; it
does not change either package's requirements or the official release baseline.

The diagnostic explicitly selects the project-only cache policy and retains ten
cases from its workload, including four
short warmed APIs and fixed mixed streams at concurrency 1/16/64/128. Six rounds
use every arm ordering. Memory milestones run outside query timing. Additional
warmed cProfile workers run separately, and their instrumented durations never
enter the paired comparisons. Profiles cover the caller thread, so native call
time can include waiting on other threads. RSS after closing the client still
includes shared process resources and retained allocator memory; it is not a
leak measurement.

Controlled HTTP/2 and current Hugging Face get separate jobs. Results include
raw `attribution.json`, three paired comparisons (`engine`, `project`, `total`),
full profiles, memory observations, sources, and dependency locks. They remain
development artifacts and cannot be finalized as a complete release report.

## Layout

| Location | Purpose |
| --- | --- |
| `benchmark.py`, `worker.py`, `suite.py` | Orchestration, isolated measurement, workload contract. |
| `fixture.py`, `server.py`, `adapter.py` | Controlled data and real TLS/Range service. |
| `report.py`, `publication.py` | Evidence rendering and explicit release finalization. |
| [workloads/](workloads/), [diagnostics/](diagnostics/) | Specialized concurrency, protocol, lifetime, and DuckDB diagnostics. |
| [reports/](reports/README.md) | Historical engineering investigations. |
| [results/archive/](results/archive/) | Historical release evidence, retained unchanged. |

Specialized modules run with `python -m benchmark.workloads.NAME` or
`python -m benchmark.diagnostics.NAME`. Some are imported by regression tests.
They are separate from the official paired suite. The retired single-file CLI
and HEAD-based baseline loader have been removed. These developer tools are not
installed as part of the public `defeatbeta_api` package.
