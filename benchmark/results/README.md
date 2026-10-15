# Benchmark report lifecycle

| Stage | Trigger | Storage |
| --- | --- | --- |
| Development | Manual end-to-end benchmark | Actions Summary and 30-day artifacts. No report commit or Release attachment. |
| Final release | Explicit finalization of a selected complete run | Markdown report and checksummed evidence bundle on the existing GitHub Release. |

One round is useful during development. A final report requires all twelve
phases, the declared ticker sample and all query operations, at least six even
rounds, one successful manual workflow attempt, and a Release tag identifying
the measured candidate commit. A first standalone report is supported; future
paired comparisons rerun old and new versions on the same runner per phase.

Finalization validates saved evidence and harness checksums without executing
downloaded code or rerunning queries. It preserves original per-phase records,
merged JSON, readable Markdown, source commits, dependency locks, frozen harness,
and a publication checksum manifest. Existing assets are not replaced. It does
not create tags or publish software. Finalize before development artifacts expire.

Public Actions development output remains visible; development status is not a
privacy setting. Git ignore rules concern accidental workstation commits only.

`archive/` retains historical release evidence unchanged. Old absolute timings
and old schemas are not the new executable baseline. `local/` holds ignored
workstation correctness checks and diagnostic evidence. See the
[guide](../README.md) and [design](../DESIGN.md).
