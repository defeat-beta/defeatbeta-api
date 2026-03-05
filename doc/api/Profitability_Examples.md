<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [1. Stock Quarterly Gross Margin](#1-stock-quarterly-gross-margin)
- [2. Stock Annual Gross Margin](#2-stock-annual-gross-margin)
- [3. Stock Quarterly Operating Margin](#3-stock-quarterly-operating-margin)
- [4. Stock Annual Operating Margin](#4-stock-annual-operating-margin)
- [5. Stock Quarterly Net Margin](#5-stock-quarterly-net-margin)
- [6. Stock Annual Net Margin](#6-stock-annual-net-margin)
- [7. Stock Quarterly EBITDA Margin](#7-stock-quarterly-ebitda-margin)
- [8. Stock Annual EBITDA Margin](#8-stock-annual-ebitda-margin)
- [9. Stock Quarterly FCF Margin](#9-stock-quarterly-fcf-margin)
- [10. Stock Annual FCF Margin](#10-stock-annual-fcf-margin)
- [11. Industry Quarterly Historical Gross Margin](#11-industry-quarterly-historical-gross-margin)
- [12. Industry Quarterly Historical Net Income Margin](#12-industry-quarterly-historical-net-income-margin)
- [13. Industry Quarterly Historical EBITDA Margin](#13-industry-quarterly-historical-ebitda-margin)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## 1. Stock Quarterly Gross Margin
```python
ticker.quarterly_gross_margin()
```
```text
>>> ticker.quarterly_gross_margin()
   symbol report_date  gross_profit  total_revenue  gross_margin
0    TSLA  2022-06-30  4.234000e+09   1.693400e+10          0.25
1    TSLA  2022-09-30           NaN            NaN           NaN
2    TSLA  2022-12-31           NaN            NaN           NaN
3    TSLA  2023-03-31           NaN            NaN           NaN
4    TSLA  2023-06-30  4.533000e+09   2.492700e+10          0.18
5    TSLA  2023-09-30  4.178000e+09   2.335000e+10          0.18
6    TSLA  2023-12-31  4.438000e+09   2.516700e+10          0.18
7    TSLA  2024-03-31  3.696000e+09   2.130100e+10          0.17
8    TSLA  2024-06-30  4.578000e+09   2.550000e+10          0.18
9    TSLA  2024-09-30  4.997000e+09   2.518200e+10          0.20
10   TSLA  2024-12-31  4.179000e+09   2.570700e+10          0.16
11   TSLA  2025-03-31  3.153000e+09   1.933500e+10          0.16
```

## 2. Stock Annual Gross Margin
```python
ticker.quarterly_annual_margin()
```
```text
>>> ticker.quarterly_annual_margin()
  symbol report_date  gross_profit  total_revenue  gross_margin
0   TSLA  2019-12-31           NaN            NaN           NaN
1   TSLA  2020-12-31  6.630000e+09   3.153600e+10          0.21
2   TSLA  2021-12-31  1.360600e+10   5.382300e+10          0.25
3   TSLA  2022-12-31  2.085300e+10   8.146200e+10          0.26
4   TSLA  2023-12-31  1.766000e+10   9.677300e+10          0.18
5   TSLA  2024-12-31  1.745000e+10   9.769000e+10          0.18
```

## 3. Stock Quarterly Operating Margin
```python
ticker.quarterly_operating_margin()
```
```text
>>> ticker.quarterly_operating_margin()
   symbol report_date  operating_income  total_revenue  operating_margin
0    TSLA  2022-06-30      2.606000e+09   1.693400e+10              0.15
1    TSLA  2022-09-30               NaN            NaN               NaN
2    TSLA  2022-12-31               NaN            NaN               NaN
3    TSLA  2023-03-31               NaN            NaN               NaN
4    TSLA  2023-06-30      2.399000e+09   2.492700e+10              0.10
5    TSLA  2023-09-30      1.764000e+09   2.335000e+10              0.08
6    TSLA  2023-12-31      2.064000e+09   2.516700e+10              0.08
7    TSLA  2024-03-31      1.171000e+09   2.130100e+10              0.05
8    TSLA  2024-06-30      2.227000e+09   2.550000e+10              0.09
9    TSLA  2024-09-30      2.772000e+09   2.518200e+10              0.11
10   TSLA  2024-12-31      1.590000e+09   2.570700e+10              0.06
11   TSLA  2025-03-31      4.930000e+08   1.933500e+10              0.03
```

## 4. Stock Annual Operating Margin
```python
ticker.annual_operating_margin()
```
```text
>>> ticker.annual_operating_margin()
  symbol report_date  operating_income  total_revenue  operating_margin
0   TSLA  2019-12-31               NaN            NaN               NaN
1   TSLA  2020-12-31      1.994000e+09   3.153600e+10              0.06
2   TSLA  2021-12-31      6.496000e+09   5.382300e+10              0.12
3   TSLA  2022-12-31      1.383200e+10   8.146200e+10              0.17
4   TSLA  2023-12-31      8.891000e+09   9.677300e+10              0.09
5   TSLA  2024-12-31      7.760000e+09   9.769000e+10              0.08
```

## 5. Stock Quarterly Net Margin
```python
ticker.quarterly_net_margin()
```
```text
>>> ticker.quarterly_net_margin()
   symbol report_date  net_income_common_stockholders  total_revenue  net_margin
0    TSLA  2022-06-30                    2.256000e+09   1.693400e+10        0.13
1    TSLA  2022-09-30                             NaN            NaN         NaN
2    TSLA  2022-12-31                             NaN            NaN         NaN
3    TSLA  2023-03-31                             NaN            NaN         NaN
4    TSLA  2023-06-30                    2.703000e+09   2.492700e+10        0.11
5    TSLA  2023-09-30                    1.851000e+09   2.335000e+10        0.08
6    TSLA  2023-12-31                    7.927000e+09   2.516700e+10        0.31
7    TSLA  2024-03-31                    1.432000e+09   2.130100e+10        0.07
8    TSLA  2024-06-30                    1.478000e+09   2.550000e+10        0.06
9    TSLA  2024-09-30                    2.167000e+09   2.518200e+10        0.09
10   TSLA  2024-12-31                    2.314000e+09   2.570700e+10        0.09
11   TSLA  2025-03-31                    4.090000e+08   1.933500e+10        0.02
```

## 6. Stock Annual Net Margin
```python
ticker.annual_net_margin()
```
```text
>>> ticker.annual_net_margin()
  symbol report_date  net_income_common_stockholders  total_revenue  net_margin
0   TSLA  2019-12-31                             NaN            NaN         NaN
1   TSLA  2020-12-31                    6.900000e+08   3.153600e+10        0.02
2   TSLA  2021-12-31                    5.524000e+09   5.382300e+10        0.10
3   TSLA  2022-12-31                    1.258300e+10   8.146200e+10        0.15
4   TSLA  2023-12-31                    1.499900e+10   9.677300e+10        0.15
5   TSLA  2024-12-31                    7.130000e+09   9.769000e+10        0.07
```

## 7. Stock Quarterly EBITDA Margin
```python
ticker.quarterly_ebitda_margin()
```
```text
>>> ticker.quarterly_ebitda_margin()
   symbol report_date        ebitda  total_revenue  ebitda_margin
0    TSLA  2022-06-30           NaN   1.693400e+10            NaN
1    TSLA  2022-09-30           NaN            NaN            NaN
2    TSLA  2022-12-31           NaN            NaN            NaN
3    TSLA  2023-03-31           NaN            NaN            NaN
4    TSLA  2023-06-30  4.119000e+09   2.492700e+10           0.17
5    TSLA  2023-09-30  3.318000e+09   2.335000e+10           0.14
6    TSLA  2023-12-31  3.484000e+09   2.516700e+10           0.14
7    TSLA  2024-03-31  3.210000e+09   2.130100e+10           0.15
8    TSLA  2024-06-30  3.251000e+09   2.550000e+10           0.13
9    TSLA  2024-09-30  4.224000e+09   2.518200e+10           0.17
10   TSLA  2024-12-31  4.358000e+09   2.570700e+10           0.17
11   TSLA  2025-03-31  2.127000e+09   1.933500e+10           0.11
```

## 8. Stock Annual EBITDA Margin
```python
ticker.annual_ebitda_margin()
```
```text
>>> ticker.annual_ebitda_margin()
  symbol report_date        ebitda  total_revenue  ebitda_margin
0   TSLA  2019-12-31           NaN            NaN            NaN
1   TSLA  2020-12-31  4.224000e+09   3.153600e+10           0.13
2   TSLA  2021-12-31  9.625000e+09   5.382300e+10           0.18
3   TSLA  2022-12-31  1.765700e+10   8.146200e+10           0.22
4   TSLA  2023-12-31  1.479600e+10   9.677300e+10           0.15
5   TSLA  2024-12-31  1.470800e+10   9.769000e+10           0.15
```

## 9. Stock Quarterly FCF Margin
```python
ticker.quarterly_fcf_margin()
```
```text
>>> ticker.quarterly_fcf_margin()
   symbol report_date  free_cash_flow  total_revenue  fcf_margin
0    TSLA  2022-06-30    6.210000e+08   1.693400e+10        0.04
1    TSLA  2022-09-30             NaN            NaN         NaN
2    TSLA  2022-12-31             NaN            NaN         NaN
3    TSLA  2023-03-31             NaN            NaN         NaN
4    TSLA  2023-06-30    1.005000e+09   2.492700e+10        0.04
5    TSLA  2023-09-30    8.490000e+08   2.335000e+10        0.04
6    TSLA  2023-12-31    2.063000e+09   2.516700e+10        0.08
7    TSLA  2024-03-31   -2.535000e+09   2.130100e+10       -0.12
8    TSLA  2024-06-30    1.340000e+09   2.550000e+10        0.05
9    TSLA  2024-09-30    2.742000e+09   2.518200e+10        0.11
10   TSLA  2024-12-31    2.034000e+09   2.570700e+10        0.08
11   TSLA  2025-03-31    6.640000e+08   1.933500e+10        0.03
```

## 10. Stock Annual FCF Margin
```python
ticker.annual_fcf_margin()
```
```text
>>> ticker.annual_fcf_margin()
  symbol report_date  free_cash_flow  total_revenue  fcf_margin
0   TSLA  2019-12-31             NaN            NaN         NaN
1   TSLA  2020-12-31    2.701000e+09   3.153600e+10        0.09
2   TSLA  2021-12-31    3.483000e+09   5.382300e+10        0.06
3   TSLA  2022-12-31    7.552000e+09   8.146200e+10        0.09
4   TSLA  2023-12-31    4.357000e+09   9.677300e+10        0.05
5   TSLA  2024-12-31    3.581000e+09   9.769000e+10        0.04
```


## 11. Industry Quarterly Historical Gross Margin
```markdown
Aggregate method (Damodaran): industry gross margin = Σ(TTM gross profit) / Σ(TTM revenue), not
the mean of individual company gross margins. This gives larger companies more weight, consistent
with how index providers (MSCI, S&P) compute sector-level profitability metrics.

Paired exclusion: a company is included only when BOTH its TTM gross profit AND its TTM revenue
are available on the same date.

TTM gross profit: trailing four consecutive quarters of gross_profit, converted to USD at the spot
FX rate of each fiscal quarter end.

TTM revenue: trailing four consecutive quarters of total_revenue, converted to USD at the spot FX
rate of each fiscal quarter end.

Date baseline: every month end. Each company's quarterly TTM values are forward-filled to the
monthly baseline via merge_asof (backward), so companies with different fiscal year ends all
contribute to every month.

total_ttm_gross_profit = Σ ttm_gross_profit_usd(i)  for companies where both values available
total_ttm_revenue      = Σ ttm_revenue_usd(i)        for the same set of companies

industry_gross_margin  = total_ttm_gross_profit / total_ttm_revenue
```

```python
ticker.industry_quarterly_gross_margin()
```
```text
   report_date        industry  total_ttm_gross_profit  total_ttm_revenue  industry_gross_margin
0   2024-03-31  Semiconductors            1.482105e+11       3.116670e+11                 0.4755
1   2024-04-30  Semiconductors            2.449303e+11       4.509029e+11                 0.5432
2   2024-05-31  Semiconductors            2.473716e+11       4.722735e+11                 0.5238
3   2024-06-30  Semiconductors            2.478755e+11       4.747234e+11                 0.5221
4   2024-07-31  Semiconductors            2.626168e+11       4.946217e+11                 0.5309
5   2024-08-31  Semiconductors            2.657890e+11       4.983616e+11                 0.5333
6   2024-09-30  Semiconductors            2.666104e+11       5.058975e+11                 0.5270
7   2024-10-31  Semiconductors            2.815764e+11       5.275066e+11                 0.5338
8   2024-11-30  Semiconductors            2.849595e+11       5.314892e+11                 0.5362
9   2024-12-31  Semiconductors            2.900923e+11       5.397324e+11                 0.5375
```


## 12. Industry Quarterly Historical Net Income Margin
```markdown
Aggregate method (Damodaran): industry net margin = Σ(TTM net income) / Σ(TTM revenue), not the
mean of individual company net margins. This gives larger companies more weight, consistent with
how index providers (MSCI, S&P) compute sector-level profitability metrics.

Paired exclusion: a company is included only when BOTH its TTM net income AND its TTM revenue are
available on the same date.

TTM net income: trailing four consecutive quarters of net_income_common_stockholders, converted to
USD at the spot FX rate of each fiscal quarter end.

TTM revenue: trailing four consecutive quarters of total_revenue, converted to USD at the spot FX
rate of each fiscal quarter end.

Date baseline: every month end. Each company's quarterly TTM values are forward-filled to the
monthly baseline via merge_asof (backward), so companies with different fiscal year ends all
contribute to every month.

total_ttm_net_income = Σ ttm_net_income_usd(i)  for companies where both values available
total_ttm_revenue    = Σ ttm_revenue_usd(i)      for the same set of companies

industry_net_margin  = total_ttm_net_income / total_ttm_revenue
```

```python
ticker.industry_quarterly_net_margin()
```
```text
   report_date        industry  total_ttm_net_income  total_ttm_revenue  industry_net_margin
0   2024-03-31  Semiconductors          6.231471e+10       3.116672e+11               0.1999
1   2024-04-30  Semiconductors          1.152309e+11       4.509032e+11               0.2556
2   2024-05-31  Semiconductors          1.136923e+11       4.722738e+11               0.2407
3   2024-06-30  Semiconductors          1.104458e+11       4.747235e+11               0.2327
4   2024-07-31  Semiconductors          1.154221e+11       4.946218e+11               0.2334
5   2024-08-31  Semiconductors          1.177394e+11       4.983617e+11               0.2363
6   2024-09-30  Semiconductors          1.046344e+11       5.058976e+11               0.2068
7   2024-10-31  Semiconductors          1.150011e+11       5.275068e+11               0.2180
8   2024-11-30  Semiconductors          1.181051e+11       5.314894e+11               0.2222
9   2024-12-31  Semiconductors          1.176083e+11       5.397324e+11               0.2179
```


## 13. Industry Quarterly Historical EBITDA Margin
```markdown
Aggregate method (Damodaran): industry EBITDA margin = Σ(TTM EBITDA) / Σ(TTM revenue), not the
mean of individual company EBITDA margins. This gives larger companies more weight, consistent with
how index providers (MSCI, S&P) compute sector-level profitability metrics.

Paired exclusion: a company is included only when BOTH its TTM EBITDA AND its TTM revenue are
available on the same date.

TTM EBITDA: trailing four consecutive quarters of ebitda, converted to USD at the spot FX rate of
each fiscal quarter end.

TTM revenue: trailing four consecutive quarters of total_revenue, converted to USD at the spot FX
rate of each fiscal quarter end.

Date baseline: every month end. Each company's quarterly TTM values are forward-filled to the
monthly baseline via merge_asof (backward), so companies with different fiscal year ends all
contribute to every month.

total_ttm_ebitda  = Σ ttm_ebitda_usd(i)   for companies where both values available
total_ttm_revenue = Σ ttm_revenue_usd(i)   for the same set of companies

industry_ebitda_margin = total_ttm_ebitda / total_ttm_revenue
```

```python
ticker.industry_quarterly_ebitda_margin()
```
```text
   report_date        industry  total_ttm_ebitda  total_ttm_revenue  industry_ebitda_margin
0   2024-03-31  Semiconductors      1.155701e+11       3.116672e+11                  0.3708
1   2024-04-30  Semiconductors      1.914041e+11       4.509032e+11                  0.4245
2   2024-05-31  Semiconductors      1.979625e+11       4.722738e+11                  0.4192
3   2024-06-30  Semiconductors      1.991990e+11       4.747235e+11                  0.4196
4   2024-07-31  Semiconductors      2.127406e+11       4.946218e+11                  0.4301
5   2024-08-31  Semiconductors      2.157649e+11       4.983617e+11                  0.4329
6   2024-09-30  Semiconductors      2.086910e+11       5.058976e+11                  0.4125
7   2024-10-31  Semiconductors      2.219666e+11       5.275068e+11                  0.4208
8   2024-11-30  Semiconductors      2.253746e+11       5.314894e+11                  0.4240
9   2024-12-31  Semiconductors      2.280932e+11       5.397324e+11                  0.4226
```