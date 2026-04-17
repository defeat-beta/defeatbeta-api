import logging
import unittest

from defeatbeta_api.data.ticker import Ticker

class TestTicker(unittest.TestCase):
    SYMBOL = "QCOM"

    @classmethod
    def setUpClass(cls):
        cls.ticker = Ticker(cls.SYMBOL, http_proxy="http://127.0.0.1:8118", log_level=logging.DEBUG)

    @classmethod
    def tearDownClass(cls):
        result = cls.ticker.download_data_performance()
        print(result)

    def test_info(self):
        result = self.ticker.info()
        print(result.to_string())

    def test_sec_filing(self):
        result = self.ticker.sec_filing()
        print(result)

    def test_officers(self):
        result = self.ticker.officers()
        print(result.to_string())

    def test_calendar(self):
        result = self.ticker.calendar()
        print(result.to_string())

    def test_splits(self):
        result = self.ticker.splits()
        print(result.to_string())

    def test_dividends(self):
        result = self.ticker.dividends()
        print(result.to_string())

    def test_ttm_eps(self):
        result = self.ticker.ttm_eps()
        print(result.to_string(float_format="{:,}".format))

    def test_price(self):
        result = self.ticker.price()
        print(result)

    def test_statement_1(self):
        result = self.ticker.quarterly_income_statement()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_2(self):
        result = self.ticker.annual_income_statement()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_3(self):
        result = self.ticker.quarterly_balance_sheet()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_4(self):
        result = self.ticker.annual_balance_sheet()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_5(self):
        result = self.ticker.quarterly_cash_flow()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_statement_6(self):
        result = self.ticker.annual_cash_flow()
        result.print_pretty_table()
        print(result.df().to_string())

    def test_ttm_pe(self):
        result = self.ticker.ttm_pe()
        print(result)

        # No negative P/E values should exist (Bloomberg/FactSet convention)
        self.assertFalse(
            (result['ttm_pe'] < 0).any(),
            "ttm_pe should never be negative; negative EPS periods must be NaN"
        )

        # Rows with negative EPS must have NaN ttm_pe
        negative_eps_mask = result['ttm_eps'] < 0
        if negative_eps_mask.any():
            self.assertTrue(
                result.loc[negative_eps_mask, 'ttm_pe'].isna().all(),
                "ttm_pe must be NaN when ttm_eps < 0"
            )

        # Rows with positive EPS must have a positive ttm_pe
        positive_eps_mask = result['ttm_eps'] > 0
        if positive_eps_mask.any():
            self.assertTrue(
                (result.loc[positive_eps_mask, 'ttm_pe'] > 0).all(),
                "ttm_pe must be positive when ttm_eps > 0"
            )

    def test_earning_call_transcripts(self):
        transcripts = self.ticker.earning_call_transcripts()
        print(transcripts)
        transcript_list = transcripts.get_transcripts_list()
        print(transcript_list)
        if transcript_list.empty:
            self.skipTest(f"No earning call transcripts available for {self.SYMBOL}")
        row = transcript_list.iloc[0]
        fiscal_year, fiscal_quarter = int(row["fiscal_year"]), int(row["fiscal_quarter"])
        print(transcripts.get_transcript(fiscal_year, fiscal_quarter))
        transcripts.print_pretty_table(fiscal_year, fiscal_quarter)

    def test_news(self):
        news = self.ticker.news()

        df = news.get_news_list()
        print(df.to_string())

        if df.empty:
            self.skipTest(f"No news available for {self.SYMBOL}")

        first_uuid = df.iloc[0]["uuid"]

        print(first_uuid)
        print(news.get_news(first_uuid))
        news.print_pretty_table(first_uuid)

    def test_revenue_by_segment(self):
        result = self.ticker.revenue_by_segment()
        print(result.to_string())

    def test_revenue_by_geography(self):
        result = self.ticker.revenue_by_geography()
        print(result.to_string())

    def test_revenue_by_product(self):
        result = self.ticker.revenue_by_product()
        print(result.to_string())

    def test_quarterly_gross_margin(self):
        result = self.ticker.quarterly_gross_margin()
        print(result.to_string())

    def test_annual_gross_margin(self):
        result = self.ticker.annual_gross_margin()
        print(result.to_string())

    def test_quarterly_operating_margin(self):
        result = self.ticker.quarterly_operating_margin()
        print(result.to_string())

    def test_annual_operating_margin(self):
        result = self.ticker.annual_operating_margin()
        print(result.to_string())

    def test_quarterly_net_margin(self):
        result = self.ticker.quarterly_net_margin()
        print(result.to_string())

    def test_annual_net_margin(self):
        result = self.ticker.annual_net_margin()
        print(result.to_string())

    def test_quarterly_ebitda_margin(self):
        result = self.ticker.quarterly_ebitda_margin()
        print(result.to_string())

    def test_annual_ebitda_margin(self):
        result = self.ticker.annual_ebitda_margin()
        print(result.to_string())

    def test_quarterly_fcf_margin(self):
        result = self.ticker.quarterly_fcf_margin()
        print(result.to_string())

    def test_annual_fcf_margin(self):
        result = self.ticker.annual_fcf_margin()
        print(result.to_string())

    def test_quarterly_revenue_yoy_growth(self):
        result = self.ticker.quarterly_revenue_yoy_growth()
        print(result.to_string())

    def test_annual_revenue_yoy_growth(self):
        result = self.ticker.annual_revenue_yoy_growth()
        print(result.to_string())

    def test_quarterly_operating_income_yoy_growth(self):
        result = self.ticker.quarterly_operating_income_yoy_growth()
        print(result.to_string())

    def test_annual_operating_income_yoy_growth(self):
        result = self.ticker.annual_operating_income_yoy_growth()
        print(result.to_string())

    def test_quarterly_ebitda_yoy_growth(self):
        result = self.ticker.quarterly_ebitda_yoy_growth()
        print(result.to_string())

    def test_annual_ebitda_yoy_growth(self):
        result = self.ticker.annual_ebitda_yoy_growth()
        print(result.to_string())

    def test_quarterly_net_income_yoy_growth(self):
        result = self.ticker.quarterly_net_income_yoy_growth()
        print(result.to_string())

    def test_annual_net_income_yoy_growth(self):
        result = self.ticker.annual_net_income_yoy_growth()
        print(result.to_string())

    def test_quarterly_fcf_yoy_growth(self):
        result = self.ticker.quarterly_fcf_yoy_growth()
        print(result.to_string())

    def test_annual_fcf_yoy_growth(self):
        result = self.ticker.annual_fcf_yoy_growth()
        print(result.to_string())

    def test_quarterly_eps_yoy_growth(self):
        result = self.ticker.quarterly_eps_yoy_growth()
        print(result.to_string())

    def test_quarterly_ttm_eps_yoy_growth(self):
        result = self.ticker.quarterly_ttm_eps_yoy_growth()
        print(result.to_string())

    def test_market_capitalization(self):
        result = self.ticker.market_capitalization()
        print(result.to_string())

    def test_ps_ratio(self):
        result = self.ticker.ps_ratio()
        print(result.to_string())

    def test_pb_ratio(self):
        result = self.ticker.pb_ratio()
        print(result.to_string())

    def test_debt_to_equity(self):
        result = self.ticker.debt_to_equity()
        print(result.tail(10).to_string())

    def test_net_debt_ttm(self):
        result = self.ticker.net_debt_ttm()
        print(result.tail(10).to_string())

    def test_enterprise_value(self):
        result = self.ticker.enterprise_value()
        print(result.tail(10).to_string())

    def test_enterprise_to_revenue(self):
        result = self.ticker.enterprise_to_revenue()
        print(result.tail(10).to_string())

    def test_enterprise_to_ebitda(self):
        result = self.ticker.enterprise_to_ebitda()
        print(result.tail(10).to_string())

    def test_peg_ratio(self):
        result = self.ticker.peg_ratio()
        print(result.to_string())

    def test_ttm_revenue(self):
        result = self.ticker.ttm_revenue()
        print(result.to_string())

    def test_ttm_fcf(self):
        result = self.ticker.ttm_fcf()
        print(result.to_string())

    def test_ttm_ebitda(self):
        result = self.ticker.ttm_ebitda()
        print(result.to_string())

    def test_ttm_net_income_common_stockholders(self):
        result = self.ticker.ttm_net_income_common_stockholders()
        print(result.to_string())

    def test_quarterly_book_value_of_equity(self):
        result = self.ticker._quarterly_book_value_of_equity()
        print(result.to_string())

    def test_roe(self):
        result = self.ticker.roe()
        print(result.to_string())

    def test_roa(self):
        result = self.ticker.roa()
        print(result.to_string())

    def test_roic(self):
        result = self.ticker.roic()
        print(result.to_string())

    def test_roce(self):
        result = self.ticker.roce()
        print(result.tail(10).to_string())

    def test_equity_multiplier(self):
        result = self.ticker.equity_multiplier()
        print(result.to_string())

    def test_asset_turnover(self):
        result = self.ticker.asset_turnover()
        print(result.to_string())

    def test_wacc(self):
        result = self.ticker.wacc()
        print(result.to_string())

    def test_dcf(self):
        import math
        import xlwings as xw

        try:
            # ===== Generate Excel and structured data =====
            data = self.ticker.dcf_data()
            result = self.ticker.dcf()
            self.assertIn("file_path", result)

            dr = data["discount_rate"]
            ge = data["growth_estimates"]
            dt = data["dcf_template"]
            dv = data["dcf_value"]

            # ===== Helpers =====
            log = []  # [(label, xl_display, data_display)]

            def _num(xl_val):
                """Coerce xlwings cell value to float, treating None/NaN as 0."""
                if xl_val is None:
                    return 0.0
                if isinstance(xl_val, float) and math.isnan(xl_val):
                    return 0.0
                return float(xl_val)

            def _fmt(v):
                """Format a value for display."""
                if isinstance(v, str):
                    return v
                if isinstance(v, float) and abs(v) >= 1_000:
                    return f"{v:,.2f}"
                if isinstance(v, float):
                    return f"{v:.8g}"
                return str(v)

            def _approx(xl_val, data_val, label, places=6):
                """Assert Excel-calculated value matches dcf_data value, and log."""
                xl_f = _num(xl_val)
                data_f = float(data_val)
                self.assertAlmostEqual(xl_f, data_f, places=places, msg=label)
                log.append((label, _fmt(xl_f), _fmt(data_f)))

            def _str_eq(xl_val, data_val, label):
                """Assert string equality and log."""
                self.assertEqual(xl_val, data_val, msg=label)
                log.append((label, str(xl_val), str(data_val)))

            def _cagr(xl_val, data_val, label):
                """Assert CAGR: numeric or string (Turned Positive / Turned Negative / N/A)."""
                if isinstance(data_val, str):
                    _str_eq(xl_val, data_val, label)
                else:
                    _approx(xl_val, data_val, label, places=10)

            # ===== Open Excel via xlwings (auto-calculates all formulas) =====
            xw_app = xw.App(visible=False, add_book=False)
            try:
                xw_wb = xw_app.books.open(result["file_path"])
                ws = xw_wb.sheets[0]

                # ========== Discount Rate section (rows 2-9, E2-E9) ==========
                # Raw inputs
                _approx(ws["C2"].value, dr["market_cap"],             "C2  market_cap",             places=0)
                _approx(ws["C3"].value, dr["beta_5y"],                "C3  beta_5y",                places=4)
                _approx(ws["C4"].value, dr["total_debt"],             "C4  total_debt",             places=0)
                _approx(ws["C5"].value, dr["interest_expense"],       "C5  interest_expense",       places=0)
                _approx(ws["C6"].value, dr["pretax_income"],          "C6  pretax_income",          places=0)
                _approx(ws["C7"].value, dr["tax_provision"],          "C7  tax_provision",          places=0)
                # C8 = =L{treasury_avg_row} (Excel AVERAGE formula); places=6 to tolerate fp delta
                _approx(ws["C8"].value, dr["risk_free_rate"],         "C8  risk_free_rate",         places=6)
                _approx(ws["C9"].value, dr["expected_market_return"], "C9  expected_market_return", places=6)
                _approx(ws["E6"].value, dr["tax_rate"],               "E6  tax_rate",               places=6)
                # Formula results
                _approx(ws["E2"].value, dr["weight_of_debt"],   "E2  weight_of_debt",   places=10)
                _approx(ws["E3"].value, dr["weight_of_equity"], "E3  weight_of_equity", places=10)
                _approx(ws["E4"].value, dr["cost_of_debt"],     "E4  cost_of_debt",     places=10)
                _approx(ws["E5"].value, dr["cost_of_equity"],   "E5  cost_of_equity",   places=10)
                _approx(ws["E9"].value, dr["wacc"],             "E9  wacc",             places=10)

                # ========== Growth Estimates section ==========
                # Revenue in G/H/I (rows 3-6)
                # EPS annual snapshots in G/H/I (rows 8..8+n-1), CAGR at row 8+n
                rev_key = ge["revenue"]
                for i, r in enumerate((3, 4, 5)):
                    d = rev_key["details"][i]
                    _str_eq(ws[f"G{r}"].value, d["date"],   f"G{r}  revenue y{i+1} date")
                    _approx(ws[f"H{r}"].value, d["value"],  f"H{r}  revenue y{i+1} value", places=0)
                    _approx(ws[f"I{r}"].value, d["yoy"],    f"I{r}  revenue y{i+1} yoy",   places=6)
                _cagr(ws["H6"].value, rev_key["cagr_3y"], "H6  revenue cagr_3y")

                eps_key = ge["eps"]
                eps_start_row = 8
                for i, d in enumerate(eps_key["details"]):
                    r = eps_start_row + i
                    _str_eq(ws[f"G{r}"].value, d["date"],  f"G{r}  eps y{i+1} date")
                    _approx(ws[f"H{r}"].value, d["value"], f"H{r}  eps y{i+1} value", places=6)
                    _approx(ws[f"I{r}"].value, d["yoy"],   f"I{r}  eps y{i+1} yoy",   places=6)
                eps_avg_row = eps_start_row + len(eps_key["details"])
                # H{eps_avg_row} is now an Excel POWER formula; places=6 to tolerate fp delta
                _approx(ws[f"H{eps_avg_row}"].value, eps_key["cagr_10y"],
                        f"H{eps_avg_row}  eps cagr_10y", places=6)

                # US 10Y Treasury section (K/L cols, fixed at row 2)
                tre_key = ge["treasury"]
                treasury_data_start = 3  # row 2 = header, row 3+ = data
                for i, d in enumerate(tre_key["details"]):
                    r = treasury_data_start + i
                    _approx(ws[f"K{r}"].value, d["year"],      f"K{r}  treasury year {i+1}", places=0)
                    _approx(ws[f"L{r}"].value, d["avg_yield"], f"L{r}  treasury avg_yield {i+1}", places=10)
                treasury_avg_row = treasury_data_start + len(tre_key["details"])
                # L{treasury_avg_row} is Excel AVERAGE formula; places=6 to tolerate fp delta
                _approx(ws[f"L{treasury_avg_row}"].value, tre_key["avg_5y"],
                        f"L{treasury_avg_row}  treasury avg_5y", places=6)

                # ========== DCF Template section ==========
                # Raw parameters
                _approx(ws["C16"].value, dt["ttm_revenue"],  "C16 ttm_revenue",  places=0)
                # TTM date header in year-row (C20)
                proj = dt["projections"]
                _str_eq(ws["C20"].value, f"{proj[0]['date']} (TTM)", "C20 ttm_date_header")
                _approx(ws["C21"].value, dt["base_fcf"],     "C21 base_fcf",     places=0)
                # Formula parameters
                _approx(ws["C12"].value, dt["growth_rate_1_5y"],    "C12 growth_rate_1_5y",    places=10)
                _approx(ws["C13"].value, dt["growth_rate_6_10y"],   "C13 growth_rate_6_10y",   places=10)
                # C14 = =L{treasury_avg_row} (Excel AVERAGE formula); places=6 to tolerate fp delta
                _approx(ws["C14"].value, dt["growth_rate_terminal"], "C14 growth_rate_terminal", places=6)
                _approx(ws["C15"].value, dt["discount_rate"],        "C15 discount_rate",       places=10)
                _approx(ws["C17"].value, dt["revenue_growth_1_5y"],  "C17 revenue_growth_1_5y", places=10)
                _approx(ws["C18"].value, dt["revenue_growth_6_10y"], "C18 revenue_growth_6_10y",places=10)

                # Year header dates: D20:M20 → proj[1..10]["date"]
                year_date_vals = ws.range("D20:M20").value
                for i, xl_date in enumerate(year_date_vals, start=1):
                    _str_eq(str(xl_date), str(proj[i]["date"]),
                            f"D20+{i-1} Year {i} date header")

                # FCF: C21 (Year 0) already checked; D21:M21 → proj[1..10]["fcf"]
                fcf_vals = ws.range("D21:M21").value
                for i, xl_fcf in enumerate(fcf_vals, start=1):
                    _approx(xl_fcf, proj[i]["fcf"], f"FCF row Year {i}", places=2)

                # Terminal value: C22:L22 must be 0; M22 → proj[10]["terminal_value"]
                tv_zero_vals = ws.range("C22:L22").value
                for i, xl_tv in enumerate(tv_zero_vals):
                    col = chr(ord('C') + i)
                    _approx(xl_tv, 0, f"{col}22 terminal_value Year {i} = 0", places=0)
                _approx(ws["M22"].value, proj[10]["terminal_value"], "M22 terminal_value Year 10", places=2)

                # Total values: C23:M23 → proj[0..10]["total_value"]
                total_vals = ws.range("C23:M23").value
                for i, xl_total in enumerate(total_vals):
                    _approx(xl_total, proj[i]["total_value"], f"Total value Year {i}", places=2)

                # FCF margins: C24:M24 → proj[0..10]["fcf_margin"]
                margin_vals = ws.range("C24:M24").value
                for i, xl_margin in enumerate(margin_vals):
                    _approx(xl_margin, proj[i]["fcf_margin"], f"FCF margin Year {i}", places=6)

                # Historical FCF margins: rows 26-27, cols C onwards
                hist = dt["historical_fcf_margin"]
                for i, item in enumerate(hist):
                    col = chr(ord('C') + i)
                    _str_eq(str(ws[f"{col}26"].value), item["date"],
                            f"{col}26 hist date {i}")
                    _approx(ws[f"{col}27"].value, item["margin"],
                            f"{col}27 hist margin {i}", places=6)

                # ========== DCF Value section (rows 31-38) ==========
                # Raw inputs
                _approx(ws["C32"].value, dv["cash"],               "C32 cash",               places=0)
                _approx(ws["C35"].value, dv["shares_outstanding"], "C35 shares_outstanding", places=0)
                _approx(ws["C37"].value, dv["current_price"],      "C37 current_price",      places=2)
                # Formula results
                _approx(ws["C31"].value, dv["enterprise_value"], "C31 enterprise_value", places=2)
                _approx(ws["C33"].value, dv["total_debt"],        "C33 total_debt",       places=0)
                _approx(ws["C34"].value, dv["equity_value"],      "C34 equity_value",     places=2)
                _approx(ws["C36"].value, dv["fair_price"],        "C36 fair_price",       places=2)
                _approx(ws["C38"].value, dv["margin_of_safety"],  "C38 margin_of_safety", places=6)
                # Recommendation derived from fair_price vs current_price
                expected_rec = "Buy" if dv["fair_price"] > dv["current_price"] else "Sell"
                _str_eq(dv["recommendation"], expected_rec, "recommendation")

                # ========== Key Metrics Display (E/F merged cells) ==========
                # F31:F32 merged → =C36 (fair_price)
                _approx(ws["F31"].value, dv["fair_price"],    "F31 key_metrics fair_price",    places=2)
                # F34:F35 merged → =C37 (current_price)
                _approx(ws["F34"].value, dv["current_price"], "F34 key_metrics current_price", places=2)
                # F37:F38 merged → =IF(C36>C37,"Buy","Sell")
                _str_eq(ws["F37"].value, dv["recommendation"], "F37 key_metrics buy_sell")

            finally:
                xw_wb.close()
                xw_app.quit()

            # ===== Print all compared values =====
            col_w = max(len(row[0]) for row in log) + 2
            val_w = max(max(len(row[1]), len(row[2])) for row in log) + 2

            print(f"\n=== DCF Verification Passed  |  Symbol: {data['symbol']}  |  {result['file_path']} ===\n")
            print(f"{'Cell / Field':<{col_w}}  {'Excel (baseline)':<{val_w}}  dcf_data")
            print("-" * (col_w + val_w * 2 + 6))
            for label, xl_v, data_v in log:
                print(f"{label:<{col_w}}  {xl_v:<{val_w}}  {data_v}")

        except ValueError as e:
            self.skipTest(str(e))

    def test_beta(self):
        """Test beta calculation with different time periods"""
        print("\n=== Testing Beta Calculation ===\n")

        periods = ["1y", "3y", "5y"]

        for period in periods:
            result = self.ticker.beta(period)
            print(result.to_string())
