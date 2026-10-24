"""Keep the microsecond datetime helper identical to the conversion it replaces."""

from datetime import date
import unittest
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_series_equal

from defeatbeta_api.data.ticker import _to_datetime_us


def reference(values):
    return pd.to_datetime(values).astype("datetime64[us]")


class TestDatetimeConversion(unittest.TestCase):
    def cases(self):
        index = pd.Index([10, 20, 30], name="row")
        return {
            "microseconds": pd.Series(pd.to_datetime(["2024-01-01", None, "2024-03-01"]).astype("datetime64[us]"),
                                      index=index, name="report_date"),
            "nanoseconds": pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01", None]), name="report_date"),
            "seconds": pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01"]).astype("datetime64[s]")),
            "strings": pd.Series(["2024-01-01", "2024-02-29", None], index=index, name="report_date"),
            "dates": pd.Series([date(2024, 1, 1), date(2024, 2, 1)], dtype=object, name="report_date"),
            "empty": pd.Series([], dtype="datetime64[us]", name="report_date"),
        }

    def test_matches_the_original_conversion(self):
        for name, values in self.cases().items():
            with self.subTest(name=name):
                assert_series_equal(_to_datetime_us(values), reference(values))

    def test_microsecond_columns_skip_parsing(self):
        values = self.cases()["microseconds"]
        with patch("defeatbeta_api.data.ticker.pd.to_datetime",
                   side_effect=AssertionError("Unexpected parse")):
            assert_series_equal(_to_datetime_us(values), values)

    def test_result_does_not_alias_caller_data(self):
        values = self.cases()["microseconds"]
        result = _to_datetime_us(values)
        result.iloc[0] = pd.Timestamp("2030-01-01")
        self.assertEqual(values.iloc[0], pd.Timestamp("2024-01-01"))

    def test_timezone_aware_values_keep_the_original_behaviour(self):
        values = pd.Series(pd.to_datetime(["2024-01-01"]).tz_localize("UTC"))
        try:
            expected = reference(values)
        except Exception as exc:
            with self.assertRaises(type(exc)):
                _to_datetime_us(values)
        else:
            assert_series_equal(_to_datetime_us(values), expected)


if __name__ == "__main__":
    unittest.main()
