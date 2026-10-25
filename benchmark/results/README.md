# Benchmark results

Results are not committed to the repository. Each run of the
[End-to-end concurrency comparison](https://github.com/defeat-beta/defeatbeta-api/actions/workflows/e2e-concurrency.yml?query=branch%3Amain+is%3Asuccess)
workflow publishes its report as the job summary; the workflow page lists the
latest successful runs on `main`.

Latest result: [run 40174444831](https://github.com/defeat-beta/defeatbeta-api/actions/runs/40174444831)
(`release-0.0.62` versus the 0.0.63 code with the cached query limit, 2026-10-25).

Raw evidence is attached to each run as an artifact for 30 days. Local runs write
to the ignored `local/` directory.
