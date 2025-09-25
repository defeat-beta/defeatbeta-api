<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [1. Stock TTM EPS](#1-stock-ttm-eps)
- [2. Stock TTM PE](#2-stock-ttm-pe)
- [3. Stock Historical Market Cap](#3-stock-historical-market-cap)
- [4. Stock Historical PS Ratio](#4-stock-historical-ps-ratio)
- [5. Stock Historical PB Ratio](#5-stock-historical-pb-ratio)
- [6. Stock Historical PEG Ratio](#6-stock-historical-peg-ratio)
- [7. Stock Historical ROE](#7-stock-historical-roe)
- [8. Stock Historical ROA](#8-stock-historical-roa)
- [9. Stock Historical ROIC](#9-stock-historical-roic)

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

## 7. Stock Historical ROE
```markdown
ending_stockholders_equity    = stockholders_equity at the end of the current quarter

beginning_stockholders_equity = stockholders_equity at the beginning of the current quarter (i.e., stockholders_equity from the prior quarter)

avg_equity                    = (beginning_stockholders_equity + ending_stockholders_equity) / 2

roe                           = net_income_common_stockholders / avg_equity
```
```python
ticker.roe()
```
```text
  report_date  net_income_common_stockholders  beginning_stockholders_equity  ending_stockholders_equity    avg_equity     roe
0  2023-09-30                    1.851000e+09                   5.113000e+10                5.346600e+10  5.229800e+10  0.0354
1  2023-12-31                    7.927000e+09                   5.346600e+10                6.263400e+10  5.805000e+10  0.1366
2  2024-03-31                    1.432000e+09                   6.263400e+10                6.437800e+10  6.350600e+10  0.0225
3  2024-06-30                    1.400000e+09                   6.437800e+10                6.646800e+10  6.542300e+10  0.0214
4  2024-09-30                    2.167000e+09                   6.646800e+10                6.993100e+10  6.819950e+10  0.0318
5  2024-12-31                    2.314000e+09                   6.993100e+10                7.291300e+10  7.142200e+10  0.0324
6  2025-03-31                    4.090000e+08                   7.291300e+10                7.465300e+10  7.378300e+10  0.0055
7  2025-06-30                    1.172000e+09                   7.465300e+10                7.731400e+10  7.598350e+10  0.0154
```

## 8. Stock Historical ROA
```markdown
ending_total_assets    = total_assets at the end of the current quarter

beginning_total_assets = total_assets at the beginning of the current quarter (i.e., total_assets from the prior quarter)

avg_assets             = (beginning_total_assets + ending_total_assets) / 2

roa                    = net_income_common_stockholders / avg_assets
```
```python
ticker.roa()
```
```text
  report_date  net_income_common_stockholders  beginning_total_assets  ending_total_assets    avg_assets     roa
0  2023-09-30                    1.851000e+09            9.059100e+10         9.394100e+10  9.226600e+10  0.0201
1  2023-12-31                    7.927000e+09            9.394100e+10         1.066180e+11  1.002795e+11  0.0790
2  2024-03-31                    1.432000e+09            1.066180e+11         1.092260e+11  1.079220e+11  0.0133
3  2024-06-30                    1.400000e+09            1.092260e+11         1.128320e+11  1.110290e+11  0.0126
4  2024-09-30                    2.167000e+09            1.128320e+11         1.198520e+11  1.163420e+11  0.0186
5  2024-12-31                    2.314000e+09            1.198520e+11         1.220700e+11  1.209610e+11  0.0191
6  2025-03-31                    4.090000e+08            1.220700e+11         1.251110e+11  1.235905e+11  0.0033
7  2025-06-30                    1.172000e+09            1.251110e+11         1.285670e+11  1.268390e+11  0.0092
```

## 9. Stock Historical ROIC
```markdown
[!WARN] ROIC % does not apply to banks.

nopat                      = ebit * (1 - tax_rate_for_calcs) (ref net pperating profit after tax)

ending_invested_capital    = invested_capital at the end of the current quarter

beginning_invested_capital = invested_capital at the beginning of the current quarter (i.e., invested_capital from the prior quarter)

avg_invested_capital       = (beginning_invested_capital + ending_invested_capital) / 2

roic                       = ebit / avg_invested_capital
```
```python
ticker.roic()
```
```text
  report_date          ebit  tax_rate_for_calcs         nopat  beginning_invested_capital  ending_invested_capital  avg_invested_capital    roic
0  2022-09-30           NaN                 NaN           NaN                3.952800e+10                      NaN                   NaN     NaN
1  2023-09-30  2.083000e+09                0.08  1.916360e+09                5.264900e+10             5.717000e+10          5.490950e+10  0.0349
2  2023-12-31  2.252000e+09                0.21  1.779080e+09                5.717000e+10             6.729100e+10          6.223050e+10  0.0286
3  2024-03-31  1.964000e+09                0.26  1.453360e+09                6.729100e+10             6.925200e+10          6.827150e+10  0.0213
4  2024-06-30  1.873000e+09                0.21  1.479670e+09                6.925200e+10             7.383000e+10          7.154100e+10  0.0207
5  2024-09-30  2.876000e+09                0.22  2.243280e+09                7.383000e+10             7.732100e+10          7.557550e+10  0.0297
6  2024-12-31  2.862000e+09                0.16  2.404080e+09                7.732100e+10             8.079100e+10          7.905600e+10  0.0304
7  2025-03-31  6.800000e+08                0.29  4.828000e+08                8.079100e+10             8.189700e+10          8.134400e+10  0.0059
8  2025-06-30  1.635000e+09                0.23  1.258950e+09                8.189700e+10             8.427000e+10          8.308350e+10  0.0152
```

## 10. Stock Historical Equity Multiplier

[!WARN] Equity Multiplier does not apply to banks.

The DuPont Analysis allows us to derive that the Equity Multiplier is equal to `ROE / ROA`, based on its definitional formula.

$$
Equity\ Multiplier = \frac{avg\_assets}{\text{avg_equity}} = \frac{net\_income}{avg\_equity} \times \frac{avg\_assets}{net\_income} = ROE \times \frac{1}{ROA} = \frac{ROE}{ROA}
$$

```python
ticker.equity_multiplier()
```
```text
  report_date     roe     roa  equity_multiplier
0  2023-09-30  0.0354  0.0201               1.76
1  2023-12-31  0.1366  0.0790               1.73
2  2024-03-31  0.0225  0.0133               1.69
3  2024-06-30  0.0214  0.0126               1.70
4  2024-09-30  0.0318  0.0186               1.71
5  2024-12-31  0.0324  0.0191               1.70
6  2025-03-31  0.0055  0.0033               1.67
7  2025-06-30  0.0154  0.0092               1.67
```