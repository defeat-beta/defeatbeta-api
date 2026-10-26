# Development tests

Run the offline product regressions from the repository root:

```sh
python -m unittest -q \
  test.test_dataset_cache_fs test.test_resolve_direct test.test_duckdb_client.TestDuckDBClient \
  test.test_extent_retention test.test_shared_resources test.test_http_pool test.test_http_runtime \
  test.test_http_protocol test.test_http2_receive test.test_query_materialization \
  test.test_catalog_reuse test.test_industry_currency test.test_industry_alignment \
  test.test_industry_market_cap test.test_datetime_conversion test.test_statement_construction
  test.test_test_collection
```

These cover the dataset cache (file identity, version changes, concurrent thread
and process access, footer locks), the shared HTTP/2 connection pool (atomic
stream reservations, global budgets, SETTINGS reductions, idle shrinkage, GOAWAY
recovery), the async HTTP runtime, and industry calculations. They bind random
ports on `127.0.0.1` and do not need internet access. The HTTP/2 fixture requires
an `openssl` executable.

The benchmark harness has its own offline tests and an opt-in TLS integration
suite; see the [benchmark guide](../benchmark/README.md).

The `dataset-cache` GitHub workflow runs the offline regressions on Linux, macOS
and Windows. Its manually dispatched network-smoke job additionally checks direct
Hugging Face HTTP/2 Range reads and live queries on all three platforms. The
complete module list is in the [workflow](../.github/workflows/dataset-cache.yml).

## Opt-in suites

- A small live price sample: `DEFEATBETA_RUN_NETWORK_TESTS=1`.
- Every query method for every US ticker runs in the **All-tickers functional test**
  workflow; see the [benchmark README](../benchmark/README.md#all-tickers-functional-test).
- Set `DEFEATBETA_TEST_HTTP_PROXY` only if the test network needs an explicit proxy.
- Excel formula verification in `TestTicker.test_dcf`: `DEFEATBETA_RUN_EXCEL_TESTS=1`
  (it launches Excel).
- SiliconFlow transcript integration: `DEFEATBETA_RUN_AI_TESTS=1`, with
  `test/siliconflow_api.key`.

Use `pytest -s` to show DEBUG output; pytest otherwise captures output from
passing tests.
