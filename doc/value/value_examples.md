<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [11. Stock TTM EPS](#11-stock-ttm-eps)
- [12. Stock TTM PE](#12-stock-ttm-pe)
- [36. Stock Historical Market Cap](#36-stock-historical-market-cap)
- [37. Stock Historical PS Ratio](#37-stock-historical-ps-ratio)
- [38. Stock Historical PB Ratio](#38-stock-historical-pb-ratio)
- [39. Stock Historical PEG Ratio](#39-stock-historical-peg-ratio)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## 1. Stock TTM EPS
```python
ticker.ttm_eps()
```
```text
>>> ticker.ttm_eps()
   symbol report_date  tailing_eps   eps update_time
0    TSLA  2008-12-31          NaN -0.02  2025-03-20
1    TSLA  2009-03-31          NaN -0.01  2025-03-20
2    TSLA  2009-06-30          NaN -0.01  2025-03-20
3    TSLA  2009-09-30        -0.05  0.00  2025-03-20
4    TSLA  2009-12-31        -0.05 -0.02  2025-03-20
..    ...         ...          ...   ...         ...
60   TSLA  2023-12-31         4.31  2.27  2025-03-20
61   TSLA  2024-03-31         3.92  0.34  2025-03-20
62   TSLA  2024-06-30         3.56  0.42  2025-03-20
63   TSLA  2024-09-30         3.65  0.62  2025-03-20
64   TSLA  2024-12-31         2.04  0.66  2025-03-20

[65 rows x 5 columns]
```

## 2. Stock TTM PE
```python
ticker.ttm_pe()
```
```text
>>> ticker.ttm_pe()
     report_date eps_report_date  close_price  ttm_eps  ttm_pe
0     2010-06-29      2010-03-31         1.59    -0.06  -26.50
1     2010-06-30      2010-06-30         1.59    -0.38   -4.18
2     2010-07-01      2010-06-30         1.46    -0.38   -3.84
3     2010-07-02      2010-06-30         1.28    -0.38   -3.37
4     2010-07-06      2010-06-30         1.07    -0.38   -2.82
...          ...             ...          ...      ...     ...
3802  2025-08-11      2025-06-30       339.03     1.73  195.97
3803  2025-08-12      2025-06-30       340.84     1.73  197.02
3804  2025-08-13      2025-06-30       339.38     1.73  196.17
3805  2025-08-14      2025-06-30       335.58     1.73  193.98
3806  2025-08-15      2025-06-30       330.56     1.73  191.08

[3807 rows x 5 columns]
```

## 3. Stock Historical Market Cap
```python
ticker.market_capitalization()
```
```text
>>> ticker.market_capitalization()
     report_date shares_report_date  ...  shares_outstanding  market_capitalization
0     2010-06-29         2010-03-31  ...          1398800900           2.224093e+09
1     2010-06-30         2010-06-30  ...          1423625500           2.263565e+09
2     2010-07-01         2010-06-30  ...          1423625500           2.078493e+09
3     2010-07-02         2010-06-30  ...          1423625500           1.822241e+09
4     2010-07-06         2010-06-30  ...          1423625500           1.523279e+09
...          ...                ...  ...                 ...                    ...
3802  2025-08-11         2025-07-17  ...          3225448900           1.093524e+12
3803  2025-08-12         2025-07-17  ...          3225448900           1.099362e+12
3804  2025-08-13         2025-07-17  ...          3225448900           1.094653e+12
3805  2025-08-14         2025-07-17  ...          3225448900           1.082396e+12
3806  2025-08-15         2025-07-17  ...          3225448900           1.066204e+12

[3807 rows x 5 columns]
```

## 4. Stock Historical PS Ratio
```markdown
ttm_total_revenue_usd = ttm_total_revenue / exchange_rate

ps_ratio = market_capitalization / ttm_total_revenue_usd
```
```python
ticker.ps_ratio()
```
```text
>>> ticker.ps_ratio()
     report_date  market_capitalization  ... ttm_revenue_usd  ps_ratio
3461  2024-04-01           5.587706e+11  ...    9.474500e+10      5.90
3462  2024-04-02           5.313774e+11  ...    9.474500e+10      5.61
3463  2024-04-03           5.369581e+11  ...    9.474500e+10      5.67
3464  2024-04-04           5.456639e+11  ...    9.474500e+10      5.76
3465  2024-04-05           5.258605e+11  ...    9.474500e+10      5.55
...          ...                    ...  ...             ...       ...
3807  2025-08-18           1.081041e+12  ...    9.272000e+10     11.66
3808  2025-08-19           1.062173e+12  ...    9.272000e+10     11.46
3809  2025-08-20           1.044723e+12  ...    9.272000e+10     11.27
3810  2025-08-21           1.032498e+12  ...    9.272000e+10     11.14
3811  2025-08-22           1.096685e+12  ...    9.272000e+10     11.83

[351 rows x 7 columns]
```

## 5. Stock Historical PB Ratio
```markdown
book_value_of_equity = stockholders_equity

book_value_of_equity_usd = book_value_of_equity / exchange_rate

pb_ratio = market_capitalization / book_value_of_equity_usd
```
```python
ticker.pb_ratio()
```
```text
>>> ticker.pb_ratio()
     report_date  market_capitalization  ... book_value_of_equity_usd  pb_ratio
3022  2022-06-30           7.010198e+11  ...             3.637600e+10     19.27
3023  2022-07-01           7.097330e+11  ...             3.637600e+10     19.51
3024  2022-07-05           7.278776e+11  ...             3.637600e+10     20.01
3025  2022-07-06           7.236928e+11  ...             3.637600e+10     19.89
3026  2022-07-07           7.636984e+11  ...             3.637600e+10     20.99
...          ...                    ...  ...                      ...       ...
3807  2025-08-18           1.081041e+12  ...             7.731400e+10     13.98
3808  2025-08-19           1.062173e+12  ...             7.731400e+10     13.74
3809  2025-08-20           1.044723e+12  ...             7.731400e+10     13.51
3810  2025-08-21           1.032498e+12  ...             7.731400e+10     13.35
3811  2025-08-22           1.096685e+12  ...             7.731400e+10     14.18

[790 rows x 7 columns]
```

## 6. Stock Historical PEG Ratio
```markdown
peg_ratio_by_revenue = ttm_pe / revenue_yoy_growth

peg_ratio_by_eps = ttm_pe / eps_yoy_growth
```
```python
ticker.peg_ratio()
```
```text
    report_date  close_price  ... peg_ratio_by_revenue  peg_ratio_by_eps
0    2023-06-30       261.77  ...                 1.57              3.71
1    2023-08-18       215.49  ...                 1.29              3.05
2    2023-08-21       231.28  ...                 1.39              3.28
3    2023-08-22       233.19  ...                 1.40              3.30
4    2023-08-23       236.86  ...                 1.42              3.35
..          ...          ...  ...                  ...               ...
347  2025-07-21       328.49  ...               -16.12            -10.85
348  2025-07-22       332.11  ...               -16.30            -10.97
349  2025-07-23       332.56  ...               -16.32            -10.98
350  2025-07-25       316.06  ...               -15.51            -10.44
351  2025-08-22       340.01  ...               -16.68            -11.23

[352 rows x 9 columns]
```