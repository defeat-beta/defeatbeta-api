<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [16. Stock Quarterly Gross Margin](#16-stock-quarterly-gross-margin)
- [17. Stock Annual Gross Margin](#17-stock-annual-gross-margin)
- [18. Stock Quarterly Operating Margin](#18-stock-quarterly-operating-margin)
- [19. Stock Annual Operating Margin](#19-stock-annual-operating-margin)
- [20. Stock Quarterly Net Margin](#20-stock-quarterly-net-margin)
- [21. Stock Annual Net Margin](#21-stock-annual-net-margin)
- [22. Stock Quarterly EBITDA Margin](#22-stock-quarterly-ebitda-margin)
- [23. Stock Annual EBITDA Margin](#23-stock-annual-ebitda-margin)
- [24. Stock Quarterly FCF Margin](#24-stock-quarterly-fcf-margin)
- [25. Stock Annual FCF Margin](#25-stock-annual-fcf-margin)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## 16. Stock Quarterly Gross Margin
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

## 17. Stock Annual Gross Margin
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

## 18. Stock Quarterly Operating Margin
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

## 19. Stock Annual Operating Margin
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

## 20. Stock Quarterly Net Margin
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

## 21. Stock Annual Net Margin
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

## 22. Stock Quarterly EBITDA Margin
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

## 23. Stock Annual EBITDA Margin
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

## 24. Stock Quarterly FCF Margin
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

## 25. Stock Annual FCF Margin
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