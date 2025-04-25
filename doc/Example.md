
# Main Usage:
```markdown
0. Stock Price
1. Stock Statement
2. Stock Info 
3. Stock Officers 
4. Stock Calendar 
5. Stock Earnings 
6. Stock Splits 
7. Stock Dividends 
8. Stock Revenue Forecast 
9. Stock Earnings Forecast 
10. Stock Summary 
11. Stock TTM EPS
```

## 0. Stock Price

```python
import defeatbeta_api
from defeatbeta_api.data.ticker import Ticker

ticker = Ticker("TSLA")
ticker.price()
```
```text
>>> ticker.price()
     symbol report_date    open   close    high     low     volume
0      TSLA  2010-06-29    1.27    1.59    1.67    1.17  281494500
1      TSLA  2010-06-30    1.72    1.59    2.03    1.55  257806500
2      TSLA  2010-07-01    1.67    1.46    1.73    1.35  123282000
3      TSLA  2010-07-02    1.53    1.28    1.54    1.25   77097000
4      TSLA  2010-07-06    1.33    1.07    1.33    1.06  103003500
...     ...         ...     ...     ...     ...     ...        ...
3716   TSLA  2025-04-07  223.78  233.29  252.00  214.25  183453800
3717   TSLA  2025-04-08  245.00  221.86  250.44  217.80  171603500
3718   TSLA  2025-04-09  224.69  272.20  274.69  223.88  219433400
3719   TSLA  2025-04-10  260.00  252.40  262.49  239.33  181722600
3720   TSLA  2025-04-11  251.84  252.31  257.74  241.36  128656900

[3721 rows x 7 columns]
```

## 1. Stock Statement

```python
# get quarterly income_statement
statement=ticker.quarterly_income_statement()
print(statement.pretty_table())
```
```text
>>> statement=ticker.quarterly_income_statement()
>>> print(statement.pretty_table())
|------------------------------------------------------------+------------+---------------+------------+------------+------------+------------+------------+------------+------------+------------+------------+------------|
|                         Breakdown                          |    TTM     |  2024-12-31   | 2024-09-30 | 2024-06-30 | 2024-03-31 | 2023-12-31 | 2023-09-30 | 2023-06-30 | 2023-03-31 | 2022-12-31 | 2022-09-30 | 2022-06-30 |
|------------------------------------------------------------+------------+---------------+------------+------------+------------+------------+------------+------------+------------+------------+------------+------------|
| +Total Revenue                                             | 97,690,000 | 25,707,000    | 25,182,000 | 25,500,000 | 21,301,000 | 25,167,000 | 23,350,000 | 24,927,000 | *          | *          | *          | 16,934,000 |
|  Operating Revenue                                         | 97,690,000 | 25,707,000    | 25,182,000 | 25,500,000 | 21,301,000 | 25,167,000 | 23,350,000 | 24,927,000 | *          | *          | *          | 16,934,000 |
| Cost of Revenue                                            | 80,240,000 | 21,528,000    | 20,185,000 | 20,922,000 | 17,605,000 | 20,729,000 | 19,172,000 | 20,394,000 | *          | *          | *          | 12,700,000 |
| Gross Profit                                               | 17,450,000 | 4,179,000     | 4,997,000  | 4,578,000  | 3,696,000  | 4,438,000  | 4,178,000  | 4,533,000  | *          | *          | *          | 4,234,000  |
| +Operating Expense                                         | 9,690,000  | 2,589,000     | 2,225,000  | 2,351,000  | 2,525,000  | 2,374,000  | 2,414,000  | 2,134,000  | *          | *          | *          | 1,628,000  |
|  Selling General and Administrative                        | 5,150,000  | 1,313,000     | 1,186,000  | 1,277,000  | 1,374,000  | 1,280,000  | 1,253,000  | 1,191,000  | *          | *          | *          | 961,000    |
|  Research & Development                                    | 4,540,000  | 1,276,000     | 1,039,000  | 1,074,000  | 1,151,000  | 1,094,000  | 1,161,000  | 943,000    | *          | *          | *          | 667,000    |
| Operating Income                                           | 7,760,000  | 1,590,000     | 2,772,000  | 2,227,000  | 1,171,000  | 2,064,000  | 1,764,000  | 2,399,000  | *          | *          | *          | 2,606,000  |
| +Net Non-Operating Interest Income Expense                 | 1,219,000  | 346,000       | 337,000    | 262,000    | 274,000    | 272,000    | 244,000    | 210,000    | *          | *          | *          | -18,000    |
|  Non-Operating Interest Income                             | 1,569,000  | 442,000       | 429,000    | 348,000    | 350,000    | 333,000    | 282,000    | 238,000    | *          | *          | *          | 26,000     |
|  Non-Operating Interest Expense                            | 350,000    | 96,000        | 92,000     | 86,000     | 76,000     | 61,000     | 38,000     | 28,000     | *          | *          | *          | 44,000     |
| +Other Income Expense                                      | 11,000     | 830,000       | -325,000   | -602,000   | 108,000    | -145,000   | 37,000     | 328,000    | *          | *          | *          | -114,000   |
|  +Special Income Charges                                   | -684,000   | -7,000        | -55,000    | -622,000   | *          | 0          | 0          | 0          | *          | -34,000    | 0          | -142,000   |
|   Restructuring & Mergers Acquisition                      | 684,000    | 7,000         | 55,000     | 622,000    | *          | 0          | 0          | 0          | *          | 34,000     | 0          | 142,000    |
|  Other Non Operating Income Expenses                       | 695,000    | 837,000       | -270,000   | 20,000     | 108,000    | -145,000   | 37,000     | 328,000    | *          | *          | *          | 28,000     |
| Pretax Income                                              | 8,990,000  | 2,766,000     | 2,784,000  | 1,887,000  | 1,553,000  | 2,191,000  | 2,045,000  | 2,937,000  | *          | *          | *          | 2,474,000  |
| Tax Provision                                              | 1,837,000  | 434,000       | 601,000    | 393,000    | 409,000    | -5,752,000 | 167,000    | 323,000    | *          | *          | *          | 205,000    |
| +Net Income Common Stockholders                            | 7,130,000  | 2,314,000     | 2,167,000  | 1,478,000  | 1,171,000  | 7,927,000  | 1,851,000  | 2,703,000  | *          | *          | *          | 2,256,000  |
|  +Net Income(Attributable to Parent Company Shareholders)  | 7,130,000  | 2,356,000     | 2,167,000  | 1,478,000  | 1,129,000  | 7,930,000  | 1,853,000  | 2,703,000  | *          | *          | *          | 2,259,000  |
|   +Net Income Including Non-Controlling Interests          | 7,153,000  | 2,332,000     | 2,183,000  | 1,494,000  | 1,144,000  | 7,943,000  | 1,878,000  | 2,614,000  | *          | *          | *          | 2,269,000  |
|    Net Income Continuous Operations                        | 7,153,000  | 2,332,000     | 2,183,000  | 1,494,000  | 1,144,000  | 7,943,000  | 1,878,000  | 2,614,000  | *          | *          | *          | 2,269,000  |
|   Minority Interests                                       | -23,000    | 24,000        | -16,000    | -16,000    | -15,000    | -13,000    | -25,000    | 89,000     | *          | *          | *          | -10,000    |
|  Otherunder Preferred Stock Dividend                       | *          | *             | 0          | *          | -42,000    | *          | 2,000      | 0          | -5,000     | *          | 0          | 3,000      |
| Adjustments for Dilutive Securities                        | 0          | *             | *          | *          | *          | 0          | 0          | 0          | *          | 0          | 0          | 0          |
| Diluted NI Available to Com Stockholders                   | 7,130,000  | 2,314,000     | 2,167,000  | 1,478,000  | 1,171,000  | 7,927,000  | 1,851,000  | 2,703,000  | *          | *          | *          | 2,256,000  |
| Basic EPS                                                  | 3.41       | *             | 0.68       | 0.46       | 0.37       | 2.49       | 0.58       | 0.85       | *          | *          | *          | 0.73       |
| Diluted EPS                                                | 3.1        | *             | 0.62       | 0.42       | 0.34       | 2.27       | 0.53       | 0.78       | *          | *          | *          | 0.65       |
| Basic Average Shares                                       | 3,168,250  | *             | 3,198,000  | 3,191,000  | 3,186,000  | 3,181,000  | 3,176,000  | 3,171,000  | *          | *          | *          | 3,111,000  |
| Diluted Average Shares                                     | 3,480,250  | *             | 3,497,000  | 3,481,000  | 3,484,000  | 3,492,000  | 3,493,000  | 3,478,000  | *          | *          | *          | 3,464,000  |
| Total Operating Income as Reported                         | 7,076,000  | 1,583,000     | 2,717,000  | 1,605,000  | 1,171,000  | 2,064,000  | 1,764,000  | 2,399,000  | *          | *          | *          | 2,464,000  |
| Rent Expense Supplemental                                  | 1,003,000  | 242,000       | 247,000    | 245,000    | 269,000    | 296,000    | 301,000    | 338,000    | *          | *          | *          | *          |
| Total Expenses                                             | 89,930,000 | 24,117,000    | 22,410,000 | 23,273,000 | 20,130,000 | 23,103,000 | 21,586,000 | 22,528,000 | *          | *          | *          | 14,328,000 |
| Net Income from Continuing & Discontinued Operation        | 7,130,000  | 2,356,000     | 2,167,000  | 1,478,000  | 1,129,000  | 7,930,000  | 1,853,000  | 2,703,000  | *          | *          | *          | 2,259,000  |
| Normalized Income                                          | 7,677,200  | 2361901663.05 | 2,209,900  | 1,969,380  | 1,129,000  | 7,930,000  | 1,853,000  | 2,703,000  | *          | *          | *          | 2,389,640  |
| Interest Income                                            | 1,569,000  | 442,000       | 429,000    | 348,000    | 350,000    | 333,000    | 282,000    | 238,000    | *          | *          | *          | 26,000     |
| Interest Expense                                           | 350,000    | 96,000        | 92,000     | 86,000     | 76,000     | 61,000     | 38,000     | 28,000     | *          | *          | *          | 44,000     |
| Net Interest Income                                        | 1,219,000  | 346,000       | 337,000    | 262,000    | 274,000    | 272,000    | 244,000    | 210,000    | *          | *          | *          | -18,000    |
| EBIT                                                       | 9,340,000  | 2,862,000     | 2,876,000  | 1,973,000  | 1,629,000  | 2,252,000  | 2,083,000  | 2,965,000  | *          | *          | *          | 2,518,000  |
| EBITDA                                                     | 14,708,000 | 4,358,000     | 4,224,000  | 3,251,000  | 2,875,000  | 3,484,000  | 3,318,000  | 4,119,000  | *          | *          | *          | *          |
| Reconciled Cost of Revenue                                 | 80,240,000 | 21,528,000    | 20,185,000 | 20,922,000 | 17,605,000 | 20,729,000 | 19,172,000 | 20,394,000 | *          | *          | *          | 12,700,000 |
| Reconciled Depreciation                                    | 5,368,000  | 1,496,000     | 1,348,000  | 1,278,000  | 1,246,000  | 1,232,000  | 1,235,000  | 1,154,000  | *          | *          | *          | 922,000    |
| Net Income from Continuing Operation Net Minority Interest | 7,130,000  | 2,356,000     | 2,167,000  | 1,478,000  | 1,129,000  | 7,930,000  | 1,853,000  | 2,703,000  | *          | *          | *          | 2,259,000  |
| Total Unusual Items Excluding Goodwill                     | -684,000   | -7,000        | -55,000    | -622,000   | *          | 0          | 0          | 0          | *          | -34,000    | 0          | -142,000   |
| Total Unusual Items                                        | -684,000   | -7,000        | -55,000    | -622,000   | *          | 0          | 0          | 0          | *          | -34,000    | 0          | -142,000   |
| Normalized EBITDA                                          | 15,392,000 | 4,365,000     | 4,279,000  | 3,873,000  | 2,875,000  | 3,484,000  | 3,318,000  | 4,119,000  | *          | *          | *          | 3,582,000  |
| Tax Rate for Calcs                                         | 0.2        | 0.16          | 0.22       | 0.21       | 0.26       | 0.21       | 0.08       | 0.11       | *          | *          | *          | 0.08       |
| Tax Effect of Unusual Items                                | -136,800   | -1098336.95   | -12,100    | -130,620   | 0          | 0          | 0          | 0          | *          | *          | *          | -11,360    |
|------------------------------------------------------------+------------+---------------+------------+------------+------------+------------+------------+------------+------------+------------+------------+------------|
```

```python
# pandas.DataFrame
ticker.quarterly_income_statement().df()
```
```text
>>> ticker.quarterly_income_statement().df()
                                            Breakdown         TTM     2024-12-31  2024-09-30  2024-06-30  2024-03-31  2023-12-31  2023-09-30  2023-06-30 2023-03-31 2022-12-31 2022-09-30  2022-06-30
0                                       Total Revenue  97,690,000     25,707,000  25,182,000  25,500,000  21,301,000  25,167,000  23,350,000  24,927,000          *          *          *  16,934,000
1                                   Operating Revenue  97,690,000     25,707,000  25,182,000  25,500,000  21,301,000  25,167,000  23,350,000  24,927,000          *          *          *  16,934,000
2                                     Cost of Revenue  80,240,000     21,528,000  20,185,000  20,922,000  17,605,000  20,729,000  19,172,000  20,394,000          *          *          *  12,700,000
3                                        Gross Profit  17,450,000      4,179,000   4,997,000   4,578,000   3,696,000   4,438,000   4,178,000   4,533,000          *          *          *   4,234,000
4                                   Operating Expense   9,690,000      2,589,000   2,225,000   2,351,000   2,525,000   2,374,000   2,414,000   2,134,000          *          *          *   1,628,000
5                  Selling General and Administrative   5,150,000      1,313,000   1,186,000   1,277,000   1,374,000   1,280,000   1,253,000   1,191,000          *          *          *     961,000
6                              Research & Development   4,540,000      1,276,000   1,039,000   1,074,000   1,151,000   1,094,000   1,161,000     943,000          *          *          *     667,000
7                                    Operating Income   7,760,000      1,590,000   2,772,000   2,227,000   1,171,000   2,064,000   1,764,000   2,399,000          *          *          *   2,606,000
8           Net Non-Operating Interest Income Expense   1,219,000        346,000     337,000     262,000     274,000     272,000     244,000     210,000          *          *          *     -18,000
9                       Non-Operating Interest Income   1,569,000        442,000     429,000     348,000     350,000     333,000     282,000     238,000          *          *          *      26,000
10                     Non-Operating Interest Expense     350,000         96,000      92,000      86,000      76,000      61,000      38,000      28,000          *          *          *      44,000
11                               Other Income Expense      11,000        830,000    -325,000    -602,000     108,000    -145,000      37,000     328,000          *          *          *    -114,000
12                             Special Income Charges    -684,000         -7,000     -55,000    -622,000           *           0           0           0          *    -34,000          0    -142,000
13                Restructuring & Mergers Acquisition     684,000          7,000      55,000     622,000           *           0           0           0          *     34,000          0     142,000
14                Other Non Operating Income Expenses     695,000        837,000    -270,000      20,000     108,000    -145,000      37,000     328,000          *          *          *      28,000
15                                      Pretax Income   8,990,000      2,766,000   2,784,000   1,887,000   1,553,000   2,191,000   2,045,000   2,937,000          *          *          *   2,474,000
16                                      Tax Provision   1,837,000        434,000     601,000     393,000     409,000  -5,752,000     167,000     323,000          *          *          *     205,000
17                     Net Income Common Stockholders   7,130,000      2,314,000   2,167,000   1,478,000   1,171,000   7,927,000   1,851,000   2,703,000          *          *          *   2,256,000
18  Net Income(Attributable to Parent Company Shar...   7,130,000      2,356,000   2,167,000   1,478,000   1,129,000   7,930,000   1,853,000   2,703,000          *          *          *   2,259,000
19     Net Income Including Non-Controlling Interests   7,153,000      2,332,000   2,183,000   1,494,000   1,144,000   7,943,000   1,878,000   2,614,000          *          *          *   2,269,000
20                   Net Income Continuous Operations   7,153,000      2,332,000   2,183,000   1,494,000   1,144,000   7,943,000   1,878,000   2,614,000          *          *          *   2,269,000
21                                 Minority Interests     -23,000         24,000     -16,000     -16,000     -15,000     -13,000     -25,000      89,000          *          *          *     -10,000
22                Otherunder Preferred Stock Dividend           *              *           0           *     -42,000           *       2,000           0     -5,000          *          0       3,000
23                Adjustments for Dilutive Securities           0              *           *           *           *           0           0           0          *          0          0           0
24           Diluted NI Available to Com Stockholders   7,130,000      2,314,000   2,167,000   1,478,000   1,171,000   7,927,000   1,851,000   2,703,000          *          *          *   2,256,000
25                                          Basic EPS        3.41              *        0.68        0.46        0.37        2.49        0.58        0.85          *          *          *        0.73
26                                        Diluted EPS         3.1              *        0.62        0.42        0.34        2.27        0.53        0.78          *          *          *        0.65
27                               Basic Average Shares   3,168,250              *   3,198,000   3,191,000   3,186,000   3,181,000   3,176,000   3,171,000          *          *          *   3,111,000
28                             Diluted Average Shares   3,480,250              *   3,497,000   3,481,000   3,484,000   3,492,000   3,493,000   3,478,000          *          *          *   3,464,000
29                 Total Operating Income as Reported   7,076,000      1,583,000   2,717,000   1,605,000   1,171,000   2,064,000   1,764,000   2,399,000          *          *          *   2,464,000
30                          Rent Expense Supplemental   1,003,000        242,000     247,000     245,000     269,000     296,000     301,000     338,000          *          *          *           *
31                                     Total Expenses  89,930,000     24,117,000  22,410,000  23,273,000  20,130,000  23,103,000  21,586,000  22,528,000          *          *          *  14,328,000
32  Net Income from Continuing & Discontinued Oper...   7,130,000      2,356,000   2,167,000   1,478,000   1,129,000   7,930,000   1,853,000   2,703,000          *          *          *   2,259,000
33                                  Normalized Income   7,677,200  2361901663.05   2,209,900   1,969,380   1,129,000   7,930,000   1,853,000   2,703,000          *          *          *   2,389,640
34                                    Interest Income   1,569,000        442,000     429,000     348,000     350,000     333,000     282,000     238,000          *          *          *      26,000
35                                   Interest Expense     350,000         96,000      92,000      86,000      76,000      61,000      38,000      28,000          *          *          *      44,000
36                                Net Interest Income   1,219,000        346,000     337,000     262,000     274,000     272,000     244,000     210,000          *          *          *     -18,000
37                                               EBIT   9,340,000      2,862,000   2,876,000   1,973,000   1,629,000   2,252,000   2,083,000   2,965,000          *          *          *   2,518,000
38                                             EBITDA  14,708,000      4,358,000   4,224,000   3,251,000   2,875,000   3,484,000   3,318,000   4,119,000          *          *          *           *
39                         Reconciled Cost of Revenue  80,240,000     21,528,000  20,185,000  20,922,000  17,605,000  20,729,000  19,172,000  20,394,000          *          *          *  12,700,000
40                            Reconciled Depreciation   5,368,000      1,496,000   1,348,000   1,278,000   1,246,000   1,232,000   1,235,000   1,154,000          *          *          *     922,000
41  Net Income from Continuing Operation Net Minor...   7,130,000      2,356,000   2,167,000   1,478,000   1,129,000   7,930,000   1,853,000   2,703,000          *          *          *   2,259,000
42             Total Unusual Items Excluding Goodwill    -684,000         -7,000     -55,000    -622,000           *           0           0           0          *    -34,000          0    -142,000
43                                Total Unusual Items    -684,000         -7,000     -55,000    -622,000           *           0           0           0          *    -34,000          0    -142,000
44                                  Normalized EBITDA  15,392,000      4,365,000   4,279,000   3,873,000   2,875,000   3,484,000   3,318,000   4,119,000          *          *          *   3,582,000
45                                 Tax Rate for Calcs         0.2           0.16        0.22        0.21        0.26        0.21        0.08        0.11          *          *          *        0.08
46                        Tax Effect of Unusual Items    -136,800    -1098336.95     -12,100    -130,620           0           0           0           0          *          *          *     -11,360
```


```python
# get annual income_statement
statement=ticker.annual_income_statement()
# get quarterly balance_sheet
statement=ticker.quarterly_balance_sheet()
# get annual balance_sheet
statement=ticker.annual_balance_sheet()
# get quarterly cash_flow
statement=ticker.quarterly_cash_flow()
# get annual cash_flow
statement=ticker.annual_cash_flow()
```

## 2. Stock Info

```python
ticker.info()
```
```text
>>> ticker.info()
  symbol       address    city        country         phone    zip            industry             sector                              long_business_summary  full_time_employees               web_site report_date
0   TSLA  1 Tesla Road  Austin  United States  512 516 8177  78725  Auto Manufacturers  Consumer Cyclical  Tesla, Inc. designs, develops, manufactures, l...               125665  https://www.tesla.com  2025-04-12
```

## 3. Stock Officers
```python
ticker.officers()
```
```text
>>> ticker.officers()
  symbol                            name                                            title   age  born     pay  exercised  unexercised
0   TSLA                   Brian  Scelfo         Senior Director of Corporate Development  <NA>  <NA>    <NA>          0            0
1   TSLA                Mr. Elon R. Musk  Co-Founder, Technoking of Tesla, CEO & Director    53  1971    <NA>          0            0
2   TSLA       Mr. Franz  von Holzhausen                                   Chief Designer  <NA>  <NA>    <NA>          0            0
3   TSLA                Mr. John  Walker          Vice President of Sales - North America    61  1963  121550          0            0
4   TSLA               Mr. Peter  Bannon                                   Chip Architect  <NA>  <NA>    <NA>          0            0
5   TSLA  Mr. Rodney D. Westmoreland Jr.              Director of Construction Management  <NA>  <NA>    <NA>          0            0
6   TSLA            Mr. Turner  Caldwell                              Engineering Manager  <NA>  <NA>    <NA>          0            0
7   TSLA             Mr. Vaibhav  Taneja                          Chief Financial Officer    46  1978  278000    8517957    202075632
8   TSLA               Mr. Xiaotong  Zhu              Senior Vice President of Automotive    44  1980  926877          0    344144320
9   TSLA                 Travis  Axelrod                       Head of Investor Relations  <NA>  <NA>    <NA>          0            0
```

## 4. Stock Calendar
```python
ticker.calendar()
```
```text
>>> ticker.calendar()
  symbol report_date          name fiscal_quarter_ending
0   TSLA  2023-01-25  Tesla, Inc.             2022-12-31
1   TSLA  2023-04-19  Tesla, Inc.             2023-03-31
2   TSLA  2023-07-19  Tesla, Inc.             2023-06-30
3   TSLA  2023-10-18  Tesla, Inc.             2023-09-30
4   TSLA  2024-01-24  Tesla, Inc.             2023-12-31
5   TSLA  2024-04-23  Tesla, Inc.             2024-03-31
6   TSLA  2024-07-23  Tesla, Inc.             2024-06-30
7   TSLA  2024-10-23  Tesla, Inc.             2024-09-30
8   TSLA  2025-01-29  Tesla, Inc.             2024-12-31
```

## 5. Stock Earnings
```python
ticker.earnings()
```
```text
>>> ticker.earnings()
  symbol eps_actual eps_estimate surprise_percent quarter_name quarter_date
0   TSLA       0.66         0.72     -0.083000004       3Q2023   2023-09-30
1   TSLA       0.71      0.74037     -0.040999997       4Q2023   2023-12-31
2   TSLA       0.45       0.4899      -0.08140001       1Q2024   2024-03-31
3   TSLA       0.52      0.62013      -0.16149999       2Q2024   2024-06-30
4   TSLA       0.72      0.59756           0.2049       3Q2024   2024-09-30
5   TSLA       0.73      0.76703     -0.048299998       4Q2024   2024-12-31
```

## 6. Stock Splits
```python
ticker.splits()
```
```text
>>> ticker.splits()
  symbol report_date split_factor
0   TSLA  2020-08-31          5:1
1   TSLA  2022-08-25          3:1
```

## 7. Stock Dividends
```python
ticker.dividends()
```
```text
>>> ticker.dividends()
Empty DataFrame
Columns: [symbol, report_date, amount]
Index: []
```

## 8. Stock Revenue Forecast
```python
ticker.revenue_forecast()
```
```text
>>> ticker.revenue_forecast()
  symbol report_date  estimate_revenue_growth  number_of_analysts  estimate_avg_revenue  estimate_high_revenue  estimate_low_revenue  year_ago_estimate_avg_revenue period_type currency
0   TSLA  2025-03-31                     0.02                  27          2.180617e+10           2.706900e+10          1.896926e+10                   2.130100e+10   quarterly      USD
1   TSLA  2025-06-30                     0.01                  26          2.577758e+10           2.969100e+10          2.190817e+10                   2.550000e+10   quarterly      USD
2   TSLA  2025-12-31                     0.10                  48          1.072546e+11           1.280580e+11          8.718903e+10                   9.769000e+10      annual      USD
3   TSLA  2026-12-31                     0.20                  45          1.284010e+11           1.624250e+11          1.031536e+11                   1.072546e+11      annual      USD
```

## 9. Stock Earnings Forecast
```python
ticker.earnings_forecast()
```
```text
>>> ticker.earnings_forecast()
  symbol report_date  estimate_eps_growth  number_of_analysts  estimate_avg_eps  ...  sixty_days_ago_estimate_avg_eps  ninety_days_ago_estimate_avg_eps  year_ago_estimate_avg_eps  period_type  currency
0   TSLA  2025-03-31                -0.04                  27              0.43  ...                             0.52                              0.71                       0.45    quarterly       USD
1   TSLA  2025-06-30                 0.19                  25              0.62  ...                             0.68                              0.80                       0.52    quarterly       USD
2   TSLA  2025-12-31                 0.06                  38              2.55  ...                             2.91                              3.25                       2.42       annual       USD
3   TSLA  2026-12-31                 0.35                  36              3.44  ...                             3.83                              4.02                       2.55       annual       USD

[4 rows x 14 columns]
```

## 10. Stock Summary
```python
ticker.summary()
```
```text
>>> ticker.summary()
  symbol    market_cap  enterprise_value  shares_outstanding  implied_shares_outstanding  beta  trailing_pe  forward_pe  tailing_eps  forward_eps  enterprise_to_ebitda  enterprise_to_revenue  peg_ratio currency
0   TSLA  8.115601e+11      7.479576e+11        3.216520e+09                3.216520e+09  2.58       123.68       77.87         2.04         3.24                 57.42                   7.66        NaN      USD
```

## 11. Stock TTM EPS
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