"""Protect diagnostic isolation, attribution, and result validation."""

from collections import Counter
from copy import deepcopy
import unittest

from benchmark.diagnostics.regression_attribution import (
    ARMS, arm_order, comparison_record, make_arms, make_plan, validate_profile,
)
from benchmark.diagnostics.query_observation import profile_calls, validate_options
from benchmark.report import summarize
from test.test_benchmark import fake_record


class TestRegressionAttribution(unittest.TestCase):
    def test_attribution_keeps_project_cache_isolation_explicit(self):
        plan = make_plan()
        self.assertEqual(plan["cache_policy"], "project-only")
        self.assertEqual(len(plan["cases"]), 10)
        self.assertTrue(all(case["cache_policy"] == "project-only" for case in plan["cases"]))
        self.assertEqual({case["state"] for case in plan["cases"] if case["kind"] == "stream"},
                         {"metadata_ready"})

    def test_engine_arm_changes_interpreter_without_changing_source(self):
        base = {"commit": "old", "source": "/old", "source_hashes": {"file": "old"},
                "python": "/python-old", "environment": {"duckdb": "old"},
                "dependency_lock": "duckdb==old\npandas==same\n"}
        new = {**deepcopy(base), "commit": "new", "source": "/new", "source_hashes": {"file": "new"},
               "python": "/python-new", "environment": {"duckdb": "new"},
               "dependency_lock": "duckdb==new\npandas==same\n"}
        manifest = {"environments": {"baseline": base, "candidate": new}}
        original = deepcopy(manifest)
        arms = make_arms(manifest)
        self.assertEqual(arms["engine_only"]["source_hashes"], base["source_hashes"])
        self.assertEqual(arms["engine_only"]["commit"], base["commit"])
        self.assertEqual(arms["engine_only"]["python"], new["python"])
        self.assertEqual(arms["engine_only"]["dependency_lock"], new["dependency_lock"])
        self.assertEqual(manifest, original)
        new["dependency_lock"] += "other==1\n"
        with self.assertRaisesRegex(ValueError, "identical non-DuckDB"):
            make_arms(manifest)

    def test_every_arm_occupies_every_position_twice(self):
        for index in range(10):
            orders = [arm_order(number, index) for number in range(6)]
            self.assertEqual(len(set(orders)), 6)
            for position in range(3):
                self.assertEqual(Counter(order[position] for order in orders), Counter({arm: 2 for arm in ARMS}))

    def test_profiles_cannot_contaminate_comparisons(self):
        record = fake_record()
        record.update(stage="development", workflow={}, arms={name: {} for name in ARMS},
                      profiles=[{"case": "not-a-measurement", "measurement": {"status": "error"}}])
        for sample in list(record["records"]):
            if sample["variant"] == "baseline":
                record["records"].append({**deepcopy(sample), "variant": "engine_only"})
        self.assertTrue(summarize(comparison_record(record, "engine"))["valid"])
        record["records"][-1]["measurement"]["results"][0]["result"]["sha256"] = "wrong"
        self.assertFalse(summarize(comparison_record(record, "engine"))["valid"])
        self.assertTrue(summarize(comparison_record(record, "total"))["valid"])

    def test_profiles_require_cache_hits_and_matching_results(self):
        reference = fake_record()["records"][0]["measurement"]
        measured = deepcopy(reference)
        measured["cache_total_delta"]["range_requests"] = 0
        measured["diagnostics"] = {"instrumented": True}
        self.assertEqual(validate_profile(measured, reference), "matching result")
        measured["results"][0]["result"]["sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "differs"):
            validate_profile(measured, reference)
        measured["dataset_version"] = "new-data"
        self.assertIn("data changed", validate_profile(measured, reference))
        measured["cache_total_delta"]["range_requests"] = 1
        with self.assertRaisesRegex(ValueError, "network"):
            validate_profile(measured, reference)

    def test_profile_preserves_last_result_and_rejects_concurrent_calls(self):
        calls = []
        result, profile = profile_calls(lambda: calls.append(1) or len(calls), 3)
        self.assertEqual(result, 3)
        self.assertEqual(profile["repetitions"], 3)
        self.assertTrue(profile["functions"])
        case = make_plan()["cases"][-1]
        self.assertEqual(case["kind"], "stream")
        case["diagnostics"]["profile_repeats"] = 1
        with self.assertRaisesRegex(ValueError, "fully warmed"):
            validate_options(case)


if __name__ == "__main__":
    unittest.main()
