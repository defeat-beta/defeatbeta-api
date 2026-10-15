# Benchmark report lifecycle

Official measurements run in GitHub Actions. Publication is a separate explicit
operation, independent of Git ignore rules.

| Stage | Trigger | Storage |
| --- | --- | --- |
| Development | PR smoke check or manual paired benchmark | Job Summary and 30-day Actions Artifact; no report commit or Release attachment. |
| Final release | Manual finalization with a selected run and existing Release tag | Detailed Markdown and evidence bundle attached to that GitHub Release. |

Running the full `release` suite does not promote its result. Development runs
can be repeated throughout implementation. On public repositories, readers can
still see Actions output; development status is not private access.

Finalization requires all 70 default-policy cases in both fixed-data regression
and live-service regression (Hugging Face), with at least six even paired rounds.
Both share source commits, exact dependency locks, harness identity, and one
workflow attempt. The Release tag identifies the measured candidate commit.
For retries, rerun all jobs rather than mixing attempts.

Finalization never repeats measurements or drops slower cases. It produces:

- `performance-report.md`: standalone detailed comparisons for all experiments.
- `performance-evidence.tar.gz`: original JSON, per-experiment reports, harness
  sources, dependency locks, and a SHA256 publication manifest.

The upload targets an existing Release, including a draft if desired. It does
not create tags, publish packages, or change visibility. Existing assets are not
replaced. If an upload is interrupted, inspect the assets before deliberate
maintainer recovery. Promote accepted evidence before its Artifacts expire.

The [guide](../README.md) documents workflow inputs and the local CLI. The
[design](../DESIGN.md) defines cache states, timing, data changes, and limitations.

## Historical evidence

`archive/000_*`, `001_*`, and `002_release_0_0_62.*` remain unchanged historical
records from older tools. Current report commands accept the new paired schema.
Historical absolute times are not the new executable baseline; compare both
versions again under the same framework to assess improvement.

`local/` holds workstation development runs and diagnostic logs. Local ignore
rules prevent accidental commits but do not govern Actions or Release assets.
