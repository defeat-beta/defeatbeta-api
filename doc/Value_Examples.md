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
- [10. Stock Historical Equity Multiplier](#10-stock-historical-equity-multiplier)
- [11. Stock Historical Assert Turnover](#11-stock-historical-assert-turnover)
- [12. Stock Historical WACC](#12-stock-historical-wacc)
- [13. Industry Historical TTM PE](#13-industry-historical-ttm-pe)
- [14. Industry Historical PS Ratio](#14-industry-historical-ps-ratio)
- [15. Industry Historical PB Ratio](#15-industry-historical-pb-ratio)
- [16. Industry Historical ROE](#16-industry-historical-roe)
- [17. Industry Historical ROA](#17-industry-historical-roa)

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
Equity\ Multiplier = \frac{avg\ assets}{avg\ equity} = \frac{net\ income}{avg\ equity} \times \frac{avg\ assets}{net\ income} = ROE \times \frac{1}{ROA} = \frac{ROE}{ROA}
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

## 11. Stock Historical Assert Turnover

The DuPont Analysis allows us to derive that the Assert Turnover is equal to `ROA / Net Margin`, based on its definitional formula.

$$
Assert\ Turnover = \frac{total\ revenue}{avg\ assert} = \frac{net\ income}{avg\ assert} \times \frac{total\ revenue}{net\ income} = ROA \times \frac{1}{Net\ Margin} = \frac{ROA}{Net\ Margin}
$$

```python
ticker.asset_turnover()
```

```text
  report_date     roa  net_margin  asset_turnover
0  2023-09-30  0.0201      0.0793            0.25
1  2023-12-31  0.0790      0.3150            0.25
2  2024-03-31  0.0133      0.0672            0.20
3  2024-06-30  0.0126      0.0549            0.23
4  2024-09-30  0.0186      0.0861            0.22
5  2024-12-31  0.0191      0.0900            0.21
6  2025-03-31  0.0033      0.0212            0.16
7  2025-06-30  0.0092      0.0521            0.18
```

## 12. Stock Historical WACC
$$
\text{WACC} = \text{Weight of Debt} \times \text{Cost of Debt} \times (1 - \text{Tax Rate}) + \text{Weight of Equity} \times \text{Cost of Equity}
$$

---

$$
\Downarrow
$$
$$
\begin{aligned}
& \text{Weight of Debt} = \frac{\text{Total Debt}}{{\text{Total Debt}} + {\text{Market Capitalization}}} \\
\\
& \text{Cost of Debt} = \frac{\text{Interest Expense}}{\text{Total Debt}} \\
\\
& \text{Weight of Equity} = \frac{\text{Market Capitalization}}{{\text{Total Debt}} + {\text{Market Capitalization}}} \\
\\
& \text{Cost of Equity} = \text{Risk-Free Rate of Return} + \text{Beta of Asset} \times (\text{Expected Return of the Market} - \text{Risk-Free Rate of Return})
\end{aligned}
$$

$$
\Downarrow
$$

| Variable                                         | Source                                    | Description                                                                                                                                                                                                             | Unit  |
|--------------------------------------------------|-------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------|
| Market Capitalization (`market_capitalization`)  | `market_capitalization()`                 | Market cap data from the past 5 years, `report_date` serves as the baseline timeline                                                                                                                                    | USD   |
| Total Debt (`total_debt_usd`)                    | Financial statements (`total_debt`)       | Reported total debt, converted into USD using the spot FX rate at the fiscal quarter end; aligned to market capitalization `report_date` using `merge_asof` (looking back to the most recent available value)           | USD   |
| Interest Expense (`interest_expense_usd`)        | Financial statements (`interest_expense`) | Reported interest expense, converted into USD using the spot FX rate at the fiscal quarter end; aligned to market capitalization `report_date` using `merge_asof` (looking back to the most recent available value)     | USD   |
| Pretax Income (`pretax_incvome_usd`)             | Financial statements (`pretax_income`)    | Reported pretax income, converted into USD using the spot FX rate at the fiscal quarter end; aligned to market capitalization `report_date` using `merge_asof` (looking back to the most recent available value)        | USD   |
| Tax Provision (`tax_provision_usd`)              | Financial statements (`tax_provision`)    | Reported income tax provision, converted into USD using the spot FX rate at the fiscal quarter end; aligned to market capitalization `report_date` using `merge_asof` (looking back to the most recent available value) | USD   |
| Tax Rate for Calcs (`tax_rate_for_calcs`)        | Financial statements / Derived            | Taken directly from financial statements; if missing, falls back to `tax_provision_usd / pretax_income_usd`                                                                                                             | %     |
| Risk-Free Rate of Return (`treasure_10y_yield`)  | `treasure.daily_treasure_yield()`         | 10-Year U.S. Treasury Constant Maturity Rate; aligned to market capitalization `report_date` using `merge_asof` (looking back to the most recent available value)                                                       | %     |
| Beta of the Asset (`beta_5y`)                    | `summary()`                               | 5-year rolling beta                                                                                                                                                                                                     | -     |
| Expected Return of the Market (`sp500_10y_cagr`) | `sp500_cagr_returns_rolling(10)`          | 10-year rolling compounded annual growth rate (CAGR) of the S&P 500; aligned to market capitalization `report_date` using `merge_asof` (looking back to the most recent available value)                                | %     |
| Exchange Rate (`exchange_rate`)                  | FX data / synthetic =X symbol             | Spot FX rate at fiscal quarter end; for USD-denominated statements, fixed at 1. Converted as `value_usd = value / exchange_rate` (where `exchange_rate` = local currency per 1 USD). Aligned via `merge_asof` lookup    | ratio |

```python
ticker.wacc()
```
```text
   symbol report_date  market_capitalization  exchange_rate    total_debt  total_debt_usd  interest_expense  interest_expense_usd  pretax_income  pretax_income_usd  tax_provision  tax_provision_usd  tax_rate_for_calcs  sp500_cagr_end  sp500_10y_cagr  treasure_10y_yield  beta_5y  weight_of_debt  weight_of_equity  cost_of_debt  cost_of_equity    wacc
0    TSLA  2023-06-30           8.308580e+11            1.0  5.811000e+09    5.811000e+09        28000000.0            28000000.0   2.937000e+09       2.937000e+09   3.230000e+08       3.230000e+08                0.11            2022          0.1041              0.0381     2.07          0.0069            0.9931        0.0048          0.1747  0.1735
1    TSLA  2023-09-30           7.941969e+11            1.0  8.187000e+09    8.187000e+09        38000000.0            38000000.0   2.045000e+09       2.045000e+09   1.670000e+08       1.670000e+08                0.08            2022          0.1041              0.0459     2.07          0.0102            0.9898        0.0046          0.1664  0.1647
2    TSLA  2023-12-31           7.898984e+11            1.0  9.573000e+09    9.573000e+09        61000000.0            61000000.0   2.191000e+09       2.191000e+09  -5.752000e+09      -5.752000e+09                0.21            2023          0.0994              0.0388     2.07          0.0120            0.9880        0.0064          0.1642  0.1623
3    TSLA  2024-03-31           5.598543e+11            1.0  9.911000e+09    9.911000e+09        76000000.0            76000000.0   1.888000e+09       1.888000e+09   4.830000e+08       4.830000e+08                0.26            2023          0.0994              0.0420     2.07          0.0174            0.9826        0.0077          0.1608  0.1581
4    TSLA  2024-06-30           6.310781e+11            1.0  1.251500e+10    1.251500e+10        86000000.0            86000000.0   1.787000e+09       1.787000e+09   3.710000e+08       3.710000e+08                0.21            2023          0.0994              0.0436     2.07          0.0194            0.9806        0.0069          0.1591  0.1561
5    TSLA  2024-09-30           8.390474e+11            1.0  1.278300e+10    1.278300e+10        92000000.0            92000000.0   2.784000e+09       2.784000e+09   6.010000e+08       6.010000e+08                0.22            2023          0.0994              0.0381     2.07          0.0150            0.9850        0.0072          0.1650  0.1626
6    TSLA  2024-12-31           1.298749e+12            1.0  1.362300e+10    1.362300e+10        96000000.0            96000000.0   2.766000e+09       2.766000e+09   4.340000e+08       4.340000e+08                0.16            2024          0.1107              0.0458     2.07          0.0104            0.9896        0.0070          0.1801  0.1783
7    TSLA  2025-03-31           8.344952e+11            1.0  1.312800e+10    1.312800e+10        91000000.0            91000000.0   5.890000e+08       5.890000e+08   1.690000e+08       1.690000e+08                0.29            2024          0.1107              0.0423     2.07          0.0155            0.9845        0.0069          0.1839  0.1811
8    TSLA  2025-06-30           1.024136e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0424     2.07          0.0127            0.9873        0.0065          0.1838  0.1815
9    TSLA  2025-07-01           9.694890e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0426     2.07          0.0134            0.9866        0.0065          0.1836  0.1812
10   TSLA  2025-07-02           1.017656e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0430     2.07          0.0127            0.9873        0.0065          0.1831  0.1808
11   TSLA  2025-07-03           1.016688e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0435     2.07          0.0128            0.9872        0.0065          0.1826  0.1803
12   TSLA  2025-07-07           9.476626e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0440     2.07          0.0137            0.9863        0.0065          0.1821  0.1797
13   TSLA  2025-07-08           9.601394e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0442     2.07          0.0135            0.9865        0.0065          0.1819  0.1795
14   TSLA  2025-07-09           9.539171e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0434     2.07          0.0136            0.9864        0.0065          0.1827  0.1803
15   TSLA  2025-07-10           9.990209e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0435     2.07          0.0130            0.9870        0.0065          0.1826  0.1803
16   TSLA  2025-07-11           1.010756e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0443     2.07          0.0128            0.9872        0.0065          0.1817  0.1794
17   TSLA  2025-07-14           1.021686e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0443     2.07          0.0127            0.9873        0.0065          0.1817  0.1795
18   TSLA  2025-07-15           1.001955e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0450     2.07          0.0129            0.9871        0.0065          0.1810  0.1787
19   TSLA  2025-07-16           1.037064e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0446     2.07          0.0125            0.9875        0.0065          0.1814  0.1792
20   TSLA  2025-07-17           1.030241e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0447     2.07          0.0126            0.9874        0.0065          0.1813  0.1791
21   TSLA  2025-07-18           1.063269e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0444     2.07          0.0122            0.9878        0.0065          0.1816  0.1794
22   TSLA  2025-07-21           1.059528e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0438     2.07          0.0122            0.9878        0.0065          0.1823  0.1801
23   TSLA  2025-07-22           1.071204e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0435     2.07          0.0121            0.9879        0.0065          0.1826  0.1805
24   TSLA  2025-07-23           1.072655e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0440     2.07          0.0121            0.9879        0.0065          0.1821  0.1800
25   TSLA  2025-07-24           9.847295e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0443     2.07          0.0132            0.9868        0.0065          0.1817  0.1794
26   TSLA  2025-07-25           1.019435e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0440     2.07          0.0127            0.9873        0.0065          0.1821  0.1799
27   TSLA  2025-07-28           1.050174e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0442     2.07          0.0124            0.9876        0.0065          0.1819  0.1797
28   TSLA  2025-07-29           1.036014e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0434     2.07          0.0125            0.9875        0.0065          0.1827  0.1805
29   TSLA  2025-07-30           1.029047e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0438     2.07          0.0126            0.9874        0.0065          0.1823  0.1801
30   TSLA  2025-07-31           9.943091e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0437     2.07          0.0130            0.9870        0.0065          0.1824  0.1801
31   TSLA  2025-08-01           9.761176e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0423     2.07          0.0133            0.9867        0.0065          0.1839  0.1815
32   TSLA  2025-08-04           9.975023e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0422     2.07          0.0130            0.9870        0.0065          0.1840  0.1817
33   TSLA  2025-08-05           9.957606e+11            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0422     2.07          0.0130            0.9870        0.0065          0.1840  0.1817
34   TSLA  2025-08-06           1.031853e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0422     2.07          0.0126            0.9874        0.0065          0.1840  0.1817
35   TSLA  2025-08-07           1.039465e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0423     2.07          0.0125            0.9875        0.0065          0.1839  0.1817
36   TSLA  2025-08-08           1.063269e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0427     2.07          0.0122            0.9878        0.0065          0.1835  0.1813
37   TSLA  2025-08-11           1.093524e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0427     2.07          0.0119            0.9881        0.0065          0.1835  0.1814
38   TSLA  2025-08-12           1.099362e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0429     2.07          0.0118            0.9882        0.0065          0.1832  0.1811
39   TSLA  2025-08-13           1.094653e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0424     2.07          0.0119            0.9881        0.0065          0.1838  0.1817
40   TSLA  2025-08-14           1.082396e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0429     2.07          0.0120            0.9880        0.0065          0.1832  0.1811
41   TSLA  2025-08-15           1.066204e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0433     2.07          0.0122            0.9878        0.0065          0.1828  0.1806
42   TSLA  2025-08-18           1.081041e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0434     2.07          0.0120            0.9880        0.0065          0.1827  0.1806
43   TSLA  2025-08-19           1.062173e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0430     2.07          0.0122            0.9878        0.0065          0.1831  0.1809
44   TSLA  2025-08-20           1.044723e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0429     2.07          0.0124            0.9876        0.0065          0.1832  0.1810
45   TSLA  2025-08-21           1.032498e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0433     2.07          0.0126            0.9874        0.0065          0.1828  0.1806
46   TSLA  2025-08-22           1.096685e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0426     2.07          0.0118            0.9882        0.0065          0.1836  0.1815
47   TSLA  2025-08-25           1.117941e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0428     2.07          0.0116            0.9884        0.0065          0.1834  0.1813
48   TSLA  2025-08-26           1.134294e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0426     2.07          0.0114            0.9886        0.0065          0.1836  0.1816
49   TSLA  2025-08-27           1.127617e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0424     2.07          0.0115            0.9885        0.0065          0.1838  0.1817
50   TSLA  2025-08-28           1.115941e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0422     2.07          0.0116            0.9884        0.0065          0.1840  0.1819
51   TSLA  2025-08-29           1.076881e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0423     2.07          0.0120            0.9880        0.0065          0.1839  0.1818
52   TSLA  2025-09-02           1.062334e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0428     2.07          0.0122            0.9878        0.0065          0.1834  0.1812
53   TSLA  2025-09-03           1.077590e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0422     2.07          0.0120            0.9880        0.0065          0.1840  0.1819
54   TSLA  2025-09-04           1.091911e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0417     2.07          0.0119            0.9881        0.0065          0.1845  0.1824
55   TSLA  2025-09-05           1.131616e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0410     2.07          0.0115            0.9885        0.0065          0.1853  0.1832
56   TSLA  2025-09-08           1.117295e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0405     2.07          0.0116            0.9884        0.0065          0.1858  0.1837
57   TSLA  2025-09-09           1.119134e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0408     2.07          0.0116            0.9884        0.0065          0.1855  0.1834
58   TSLA  2025-09-10           1.121779e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0404     2.07          0.0116            0.9884        0.0065          0.1859  0.1838
59   TSLA  2025-09-11           1.189578e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0401     2.07          0.0109            0.9891        0.0065          0.1862  0.1842
60   TSLA  2025-09-12           1.277084e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0406     2.07          0.0102            0.9898        0.0065          0.1857  0.1839
61   TSLA  2025-09-15           1.322563e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0405     2.07          0.0098            0.9902        0.0065          0.1858  0.1840
62   TSLA  2025-09-16           1.359914e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0404     2.07          0.0096            0.9904        0.0065          0.1859  0.1842
63   TSLA  2025-09-17           1.373590e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0406     2.07          0.0095            0.9905        0.0065          0.1857  0.1840
64   TSLA  2025-09-18           1.344528e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0411     2.07          0.0097            0.9903        0.0065          0.1852  0.1835
65   TSLA  2025-09-19           1.374267e+12            1.0  1.313400e+10    1.313400e+10        86000000.0            86000000.0   1.549000e+09       1.549000e+09   3.590000e+08       3.590000e+08                0.23            2024          0.1107              0.0414     2.07          0.0095            0.9905        0.0065          0.1849  0.1832
```

## 13. Industry Historical TTM PE
```markdown
total_market_cap          = sum of the market cap of all stocks in the industry  

total_ttm_net_income      = sum of the trailing twelve months (TTM) net income of all stocks in the industry

industry_pe               = total_market_cap / total_ttm_net_income
```

```python
ticker.industry_ttm_pe()
```
```text
     report_date            industry  ...  total_ttm_net_income  industry_pe
0     1994-11-30  Auto Manufacturers  ...                   NaN          NaN
1     1994-12-01  Auto Manufacturers  ...                   NaN          NaN
2     1994-12-02  Auto Manufacturers  ...                   NaN          NaN
3     1994-12-05  Auto Manufacturers  ...                   NaN          NaN
4     1994-12-06  Auto Manufacturers  ...                   NaN          NaN
...          ...                 ...  ...                   ...          ...
7788  2025-11-10  Auto Manufacturers  ...          3.084231e+10        68.63
7789  2025-11-11  Auto Manufacturers  ...          3.084231e+10        68.37
7790  2025-11-12  Auto Manufacturers  ...          3.084231e+10        67.39
7791  2025-11-13  Auto Manufacturers  ...          3.084231e+10        63.96
7792  2025-11-14  Auto Manufacturers  ...          3.084231e+10        64.06

[7793 rows x 5 columns]

```

## 14. Industry Historical PS Ratio
```markdown
total_market_cap       = sum of the market cap of all stocks in the industry  

total_ttm_revenue      = sum of the trailing twelve months (TTM) revenue of all stocks in the industry

industry_ps_ratio      = total_market_cap / total_ttm_revenue
```

```python
ticker.industry_ps_ratio()
```
```text
     report_date            industry  ...  total_ttm_revenue  industry_ps_ratio
0     1994-11-30  Auto Manufacturers  ...                NaN                NaN
1     1994-12-01  Auto Manufacturers  ...                NaN                NaN
2     1994-12-02  Auto Manufacturers  ...                NaN                NaN
3     1994-12-05  Auto Manufacturers  ...                NaN                NaN
4     1994-12-06  Auto Manufacturers  ...                NaN                NaN
...          ...                 ...  ...                ...                ...
7788  2025-11-10  Auto Manufacturers  ...       1.026618e+12               2.06
7789  2025-11-11  Auto Manufacturers  ...       1.026618e+12               2.05
7790  2025-11-12  Auto Manufacturers  ...       1.026618e+12               2.02
7791  2025-11-13  Auto Manufacturers  ...       1.026618e+12               1.92
7792  2025-11-14  Auto Manufacturers  ...       1.026618e+12               1.92

[7793 rows x 5 columns]
```

## 15. Industry Historical PB Ratio
```markdown
total_market_cap                = sum of the market cap of all stocks in the industry  

total_book_value_of_equity      = sum of the book value of equity of all stocks in the industry

industry_pb_ratio               = total_market_cap / total_book_value_of_equity
```

```python
ticker.industry_pb_ratio()
```
```text
     report_date            industry  ...     total_bve  industry_pb_ratio
0     1994-11-30  Auto Manufacturers  ...           NaN                NaN
1     1994-12-01  Auto Manufacturers  ...           NaN                NaN
2     1994-12-02  Auto Manufacturers  ...           NaN                NaN
3     1994-12-05  Auto Manufacturers  ...           NaN                NaN
4     1994-12-06  Auto Manufacturers  ...           NaN                NaN
...          ...                 ...  ...           ...                ...
7788  2025-11-10  Auto Manufacturers  ...  6.133932e+11               3.45
7789  2025-11-11  Auto Manufacturers  ...  6.133932e+11               3.44
7790  2025-11-12  Auto Manufacturers  ...  6.133932e+11               3.39
7791  2025-11-13  Auto Manufacturers  ...  6.133932e+11               3.22
7792  2025-11-14  Auto Manufacturers  ...  6.133932e+11               3.22

[7793 rows x 5 columns]
```

## 16. Industry Historical ROE
```markdown
total_net_income_common_stockholders  
    = the sum of the net income attributable to common shareholders across all stocks in the industry  

total_avg_equity  
    = for each stock, compute the average shareholders' equity  
        avg_equity(symbol) = (beginning_stockholders_equity + ending_stockholders_equity) / 2  
      then sum the average equity of all stocks in the industry  
        total_avg_equity = Σ avg_equity(symbol)

industry_roe  
    = total_net_income_common_stockholders / total_avg_equity
```

```python
ticker.industry_roe()
```
```text
  report_date            industry  total_net_income_common_stockholders  total_avg_equity  industry_roe
0  2023-06-30  Auto Manufacturers                         -1.407448e+07      1.547128e+08       -0.0910
1  2023-09-30  Auto Manufacturers                          1.224270e+10      4.807896e+11        0.0255
2  2023-12-31  Auto Manufacturers                          1.574871e+10      5.068826e+11        0.0311
3  2024-03-31  Auto Manufacturers                          8.833054e+09      4.915669e+11        0.0180
4  2024-06-30  Auto Manufacturers                          1.143964e+10      4.897561e+11        0.0234
5  2024-09-30  Auto Manufacturers                          6.302880e+09      5.294544e+11        0.0119
6  2024-12-31  Auto Manufacturers                          1.273238e+10      4.982886e+11        0.0256
7  2025-03-31  Auto Manufacturers                          4.782458e+09      5.161979e+11        0.0093
8  2025-06-30  Auto Manufacturers                          5.536484e+09      5.253515e+11        0.0105
9  2025-09-30  Auto Manufacturers                          7.128733e+09      5.245579e+11        0.0136
```

## 17. Industry Historical ROA
```markdown
total_net_income_common_stockholders  
    = the sum of the net income attributable to common shareholders across all stocks in the industry  

total_avg_asserts  
    = for each stock, compute the average shareholders' equity  
        avg_asserts(symbol) = (beginning_asserts + ending_asserts) / 2  
      then sum the average equity of all stocks in the industry  
        total_avg_asserts = Σ avg_asserts(symbol)

industry_roa  
    = total_net_income_common_stockholders / total_avg_asserts
```

```python
ticker.industry_roa()
```
```text
  report_date            industry  total_net_income_common_stockholders  total_avg_asserts  industry_roa
0  2023-06-30  Auto Manufacturers                         -1.407448e+07       2.135580e+08       -0.0659
1  2023-09-30  Auto Manufacturers                          1.224270e+10       1.461015e+12        0.0084
2  2023-12-31  Auto Manufacturers                          1.574871e+10       1.539417e+12        0.0102
3  2024-03-31  Auto Manufacturers                          8.833054e+09       1.531480e+12        0.0058
4  2024-06-30  Auto Manufacturers                          1.143964e+10       1.537488e+12        0.0074
5  2024-09-30  Auto Manufacturers                          6.302880e+09       1.648691e+12        0.0038
6  2024-12-31  Auto Manufacturers                          1.273238e+10       1.581029e+12        0.0081
7  2025-03-31  Auto Manufacturers                          4.782458e+09       1.641880e+12        0.0029
8  2025-06-30  Auto Manufacturers                          5.536484e+09       1.678078e+12        0.0033
9  2025-09-30  Auto Manufacturers                          7.128733e+09       1.685806e+12        0.0042
```