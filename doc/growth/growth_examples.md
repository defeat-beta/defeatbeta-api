<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [26. Stock Quarterly Revenue YoY Growth](#26-stock-quarterly-revenue-yoy-growth)
- [27. Stock Annual Revenue YoY Growth](#27-stock-annual-revenue-yoy-growth)
- [28. Stock Quarterly Operating Income YoY Growth](#28-stock-quarterly-operating-income-yoy-growth)
- [29. Stock Annual Operating Income YoY Growth](#29-stock-annual-operating-income-yoy-growth)
- [30. Stock Quarterly Net Income YoY Growth](#30-stock-quarterly-net-income-yoy-growth)
- [31. Stock Annual Net Income YoY Growth](#31-stock-annual-net-income-yoy-growth)
- [32. Stock Quarterly Free Cash Flow YoY Growth](#32-stock-quarterly-free-cash-flow-yoy-growth)
- [33. Stock Annual Free Cash Flow YoY Growth](#33-stock-annual-free-cash-flow-yoy-growth)
- [34. Stock Quarterly EPS YoY Growth](#34-stock-quarterly-eps-yoy-growth)
- [35. Stock Quarterly TTM EPS YoY Growth](#35-stock-quarterly-ttm-eps-yoy-growth)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## 26. Stock Quarterly Revenue YoY Growth
```python
ticker.quarterly_revenue_yoy_growth()
```
```text
>>> ticker.quarterly_revenue_yoy_growth()
  symbol report_date       revenue  prev_year_revenue  yoy_growth
0   TSLA  2022-06-30  1.693400e+10                NaN         NaN
1   TSLA  2023-06-30  2.492700e+10       1.693400e+10      0.4720
2   TSLA  2023-09-30  2.335000e+10                NaN         NaN
3   TSLA  2023-12-31  2.516700e+10                NaN         NaN
4   TSLA  2024-03-31  2.130100e+10                NaN         NaN
5   TSLA  2024-06-30  2.550000e+10       2.492700e+10      0.0230
6   TSLA  2024-09-30  2.518200e+10       2.335000e+10      0.0785
7   TSLA  2024-12-31  2.570700e+10       2.516700e+10      0.0215
8   TSLA  2025-03-31  1.933500e+10       2.130100e+10     -0.0923
9   TSLA  2025-06-30  2.249600e+10       2.550000e+10     -0.1178
```

## 27. Stock Annual Revenue YoY Growth
```python
ticker.annual_revenue_yoy_growth()
```
```text
>>> ticker.annual_revenue_yoy_growth()
  symbol report_date       revenue  prev_year_revenue  yoy_growth
0   TSLA  2020-12-31  3.153600e+10                NaN         NaN
1   TSLA  2021-12-31  5.382300e+10       3.153600e+10      0.7067
2   TSLA  2022-12-31  8.146200e+10       5.382300e+10      0.5135
3   TSLA  2023-12-31  9.677300e+10       8.146200e+10      0.1880
4   TSLA  2024-12-31  9.769000e+10       9.677300e+10      0.0095
```

## 28. Stock Quarterly Operating Income YoY Growth
```python
ticker.quarterly_operating_income_yoy_growth()
```
```text
>>> ticker.quarterly_operating_income_yoy_growth()
  symbol report_date  operating_income  prev_year_operating_income  yoy_growth
0   TSLA  2022-06-30      2.606000e+09                         NaN         NaN
1   TSLA  2023-06-30      2.399000e+09                2.606000e+09     -0.0794
2   TSLA  2023-09-30      1.764000e+09                         NaN         NaN
3   TSLA  2023-12-31      2.064000e+09                         NaN         NaN
4   TSLA  2024-03-31      1.171000e+09                         NaN         NaN
5   TSLA  2024-06-30      2.227000e+09                2.399000e+09     -0.0717
6   TSLA  2024-09-30      2.772000e+09                1.764000e+09      0.5714
7   TSLA  2024-12-31      1.590000e+09                2.064000e+09     -0.2297
8   TSLA  2025-03-31      4.930000e+08                1.171000e+09     -0.5790
9   TSLA  2025-06-30      9.230000e+08                2.227000e+09     -0.5855
```

## 29. Stock Annual Operating Income YoY Growth
```python
ticker.annual_operating_income_yoy_growth()
```
```text
>>> ticker.annual_operating_income_yoy_growth()
  symbol report_date  operating_income  prev_year_operating_income  yoy_growth
0   TSLA  2020-12-31      1.994000e+09                         NaN         NaN
1   TSLA  2021-12-31      6.496000e+09                1.994000e+09      2.2578
2   TSLA  2022-12-31      1.383200e+10                6.496000e+09      1.1293
3   TSLA  2023-12-31      8.891000e+09                1.383200e+10     -0.3572
4   TSLA  2024-12-31      7.760000e+09                8.891000e+09     -0.1272
```

## 30. Stock Quarterly Net Income YoY Growth
```python
ticker.quarterly_net_income_yoy_growth()
```
```text
>>> ticker.quarterly_net_income_yoy_growth()
  symbol report_date  net_income_common_stockholders  prev_year_net_income_common_stockholders  yoy_growth
0   TSLA  2022-06-30                    2.256000e+09                                       NaN         NaN
1   TSLA  2023-06-30                    2.703000e+09                              2.256000e+09      0.1981
2   TSLA  2023-09-30                    1.851000e+09                                       NaN         NaN
3   TSLA  2023-12-31                    7.927000e+09                                       NaN         NaN
4   TSLA  2024-03-31                    1.432000e+09                                       NaN         NaN
5   TSLA  2024-06-30                    1.400000e+09                              2.703000e+09     -0.4821
6   TSLA  2024-09-30                    2.167000e+09                              1.851000e+09      0.1707
7   TSLA  2024-12-31                    2.314000e+09                              7.927000e+09     -0.7081
8   TSLA  2025-03-31                    4.090000e+08                              1.432000e+09     -0.7144
9   TSLA  2025-06-30                    1.172000e+09                              1.400000e+09     -0.1629
```

## 31. Stock Annual Net Income YoY Growth
```python
ticker.annual_net_income_yoy_growth()
```
```text
>>> ticker.annual_net_income_yoy_growth()
  symbol report_date  net_income_common_stockholders  prev_year_net_income_common_stockholders  yoy_growth
0   TSLA  2020-12-31                    6.900000e+08                                       NaN         NaN
1   TSLA  2021-12-31                    5.524000e+09                              6.900000e+08      7.0058
2   TSLA  2022-12-31                    1.258300e+10                              5.524000e+09      1.2779
3   TSLA  2023-12-31                    1.499900e+10                              1.258300e+10      0.1920
4   TSLA  2024-12-31                    7.130000e+09                              1.499900e+10     -0.5246
```

## 32. Stock Quarterly Free Cash Flow YoY Growth
```python
ticker.quarterly_fcf_yoy_growth()
```
```text
>>> ticker.quarterly_fcf_yoy_growth()
  symbol report_date  free_cash_flow  prev_year_free_cash_flow  yoy_growth
0   TSLA  2022-06-30    6.210000e+08                       NaN         NaN
1   TSLA  2023-06-30    1.005000e+09              6.210000e+08      0.6184
2   TSLA  2023-09-30    8.490000e+08                       NaN         NaN
3   TSLA  2023-12-31    2.063000e+09                       NaN         NaN
4   TSLA  2024-03-31   -2.535000e+09                       NaN         NaN
5   TSLA  2024-06-30    1.340000e+09              1.005000e+09      0.3333
6   TSLA  2024-09-30    2.742000e+09              8.490000e+08      2.2297
7   TSLA  2024-12-31    2.034000e+09              2.063000e+09     -0.0141
8   TSLA  2025-03-31    6.640000e+08             -2.535000e+09      1.2619
9   TSLA  2025-06-30    1.460000e+08              1.340000e+09     -0.8910
```

## 33. Stock Annual Free Cash Flow YoY Growth
```python
ticker.annual_fcf_yoy_growth()
```
```text
>>> ticker.annual_fcf_yoy_growth()
  symbol report_date  free_cash_flow  prev_year_free_cash_flow  yoy_growth
0   TSLA  2020-12-31    2.701000e+09                       NaN         NaN
1   TSLA  2021-12-31    3.483000e+09              2.701000e+09      0.2895
2   TSLA  2022-12-31    7.552000e+09              3.483000e+09      1.1682
3   TSLA  2023-12-31    4.357000e+09              7.552000e+09     -0.4231
4   TSLA  2024-12-31    3.581000e+09              4.357000e+09     -0.1781
```

## 34. Stock Quarterly EPS YoY Growth
```python
ticker.quarterly_eps_yoy_growth()
```
```text
>>> ticker.quarterly_eps_yoy_growth()
   symbol report_date   eps  prev_year_eps  yoy_growth
0    TSLA  2008-12-31 -0.02            NaN         NaN
1    TSLA  2009-03-31 -0.01            NaN         NaN
2    TSLA  2009-06-30 -0.01            NaN         NaN
3    TSLA  2009-09-30  0.00            NaN         NaN
4    TSLA  2009-12-31 -0.02          -0.02      0.0000
5    TSLA  2010-03-31 -0.02          -0.01     -1.0000
6    TSLA  2010-06-30 -0.34          -0.01    -33.0000
7    TSLA  2010-09-30 -0.03           0.00     -1.0000
8    TSLA  2010-12-31 -0.04          -0.02     -1.0000
9    TSLA  2011-03-31 -0.03          -0.02     -0.5000
10   TSLA  2011-06-30 -0.04          -0.34      0.8824
11   TSLA  2011-09-30 -0.04          -0.03     -0.3333
12   TSLA  2011-12-31 -0.05          -0.04     -0.2500
13   TSLA  2012-03-31 -0.06          -0.03     -1.0000
14   TSLA  2012-06-30 -0.07          -0.04     -0.7500
15   TSLA  2012-09-30 -0.07          -0.04     -0.7500
16   TSLA  2012-12-31 -0.05          -0.05      0.0000
17   TSLA  2013-03-31  0.01          -0.06      1.1667
18   TSLA  2013-06-30 -0.02          -0.07      0.7143
19   TSLA  2013-09-30 -0.02          -0.07      0.7143
20   TSLA  2013-12-31 -0.01          -0.05      0.8000
21   TSLA  2014-03-31 -0.03           0.01     -4.0000
22   TSLA  2014-06-30 -0.03          -0.02     -0.5000
23   TSLA  2014-09-30 -0.04          -0.02     -1.0000
24   TSLA  2014-12-31 -0.06          -0.01     -5.0000
25   TSLA  2015-03-31 -0.08          -0.03     -1.6667
26   TSLA  2015-06-30 -0.10          -0.03     -2.3333
27   TSLA  2015-09-30 -0.12          -0.04     -2.0000
28   TSLA  2015-12-31 -0.16          -0.06     -1.6667
29   TSLA  2016-03-31 -0.14          -0.08     -0.7500
30   TSLA  2016-06-30 -0.14          -0.10     -0.4000
31   TSLA  2016-09-30  0.01          -0.12      1.0833
32   TSLA  2016-12-31 -0.05          -0.16      0.6875
33   TSLA  2017-03-31 -0.14          -0.14      0.0000
34   TSLA  2017-06-30 -0.14          -0.14      0.0000
35   TSLA  2017-09-30 -0.25           0.01    -26.0000
36   TSLA  2017-12-31 -0.27          -0.05     -4.4000
37   TSLA  2018-03-31 -0.28          -0.14     -1.0000
38   TSLA  2018-06-30 -0.28          -0.14     -1.0000
39   TSLA  2018-09-30  0.12          -0.25      1.4800
40   TSLA  2018-12-31  0.05          -0.27      1.1852
41   TSLA  2019-03-31 -0.27          -0.28      0.0357
42   TSLA  2019-06-30 -0.15          -0.28      0.4643
43   TSLA  2019-09-30  0.05           0.12     -0.5833
44   TSLA  2019-12-31  0.04           0.05     -0.2000
45   TSLA  2020-03-31  0.01          -0.27      1.0370
46   TSLA  2020-06-30  0.03          -0.15      1.2000
47   TSLA  2020-09-30  0.09           0.05      0.8000
48   TSLA  2020-12-31  0.08           0.04      1.0000
49   TSLA  2021-03-31  0.13           0.01     12.0000
50   TSLA  2021-06-30  0.34           0.03     10.3333
51   TSLA  2021-09-30  0.48           0.09      4.3333
52   TSLA  2021-12-31  0.68           0.08      7.5000
53   TSLA  2022-03-31  0.95           0.13      6.3077
54   TSLA  2022-06-30  0.65           0.34      0.9118
55   TSLA  2022-09-30  0.95           0.48      0.9792
56   TSLA  2022-12-31  1.07           0.68      0.5735
57   TSLA  2023-03-31  0.73           0.95     -0.2316
58   TSLA  2023-06-30  0.78           0.65      0.2000
59   TSLA  2023-09-30  0.53           0.95     -0.4421
60   TSLA  2023-12-31  2.27           1.07      1.1215
61   TSLA  2024-03-31  0.41           0.73     -0.4384
62   TSLA  2024-06-30  0.40           0.78     -0.4872
63   TSLA  2024-09-30  0.62           0.53      0.1698
64   TSLA  2024-12-31  0.66           2.27     -0.7093
65   TSLA  2025-03-31  0.12           0.41     -0.7073
66   TSLA  2025-06-30  0.33           0.40     -0.1750
```

## 35. Stock Quarterly TTM EPS YoY Growth
```python
ticker.quarterly_ttm_eps_yoy_growth()
```
```text
>>> ticker.quarterly_ttm_eps_yoy_growth()
   symbol report_date  ttm_eps  prev_year_ttm_eps  yoy_growth
0    TSLA  2009-09-30    -0.05                NaN         NaN
1    TSLA  2009-12-31    -0.05                NaN         NaN
2    TSLA  2010-03-31    -0.06                NaN         NaN
3    TSLA  2010-06-30    -0.38                NaN         NaN
4    TSLA  2010-09-30    -0.40              -0.05     -7.0000
5    TSLA  2010-12-31    -0.42              -0.05     -7.4000
6    TSLA  2011-03-31    -0.43              -0.06     -6.1667
7    TSLA  2011-06-30    -0.14              -0.38      0.6316
8    TSLA  2011-09-30    -0.15              -0.40      0.6250
9    TSLA  2011-12-31    -0.17              -0.42      0.5952
10   TSLA  2012-03-31    -0.19              -0.43      0.5581
11   TSLA  2012-06-30    -0.22              -0.14     -0.5714
12   TSLA  2012-09-30    -0.25              -0.15     -0.6667
13   TSLA  2012-12-31    -0.25              -0.17     -0.4706
14   TSLA  2013-03-31    -0.18              -0.19      0.0526
15   TSLA  2013-06-30    -0.13              -0.22      0.4091
16   TSLA  2013-09-30    -0.09              -0.25      0.6400
17   TSLA  2013-12-31    -0.04              -0.25      0.8400
18   TSLA  2014-03-31    -0.07              -0.18      0.6111
19   TSLA  2014-06-30    -0.09              -0.13      0.3077
20   TSLA  2014-09-30    -0.11              -0.09     -0.2222
21   TSLA  2014-12-31    -0.16              -0.04     -3.0000
22   TSLA  2015-03-31    -0.21              -0.07     -2.0000
23   TSLA  2015-06-30    -0.28              -0.09     -2.1111
24   TSLA  2015-09-30    -0.35              -0.11     -2.1818
25   TSLA  2015-12-31    -0.46              -0.16     -1.8750
26   TSLA  2016-03-31    -0.52              -0.21     -1.4762
27   TSLA  2016-06-30    -0.56              -0.28     -1.0000
28   TSLA  2016-09-30    -0.43              -0.35     -0.2286
29   TSLA  2016-12-31    -0.32              -0.46      0.3043
30   TSLA  2017-03-31    -0.32              -0.52      0.3846
31   TSLA  2017-06-30    -0.31              -0.56      0.4464
32   TSLA  2017-09-30    -0.57              -0.43     -0.3256
33   TSLA  2017-12-31    -0.79              -0.32     -1.4687
34   TSLA  2018-03-31    -0.93              -0.32     -1.9063
35   TSLA  2018-06-30    -1.07              -0.31     -2.4516
36   TSLA  2018-09-30    -0.71              -0.57     -0.2456
37   TSLA  2018-12-31    -0.39              -0.79      0.5063
38   TSLA  2019-03-31    -0.39              -0.93      0.5806
39   TSLA  2019-06-30    -0.26              -1.07      0.7570
40   TSLA  2019-09-30    -0.32              -0.71      0.5493
41   TSLA  2019-12-31    -0.34              -0.39      0.1282
42   TSLA  2020-03-31    -0.06              -0.39      0.8462
43   TSLA  2020-06-30     0.13              -0.26      1.5000
44   TSLA  2020-09-30     0.17              -0.32      1.5313
45   TSLA  2020-12-31     0.21              -0.34      1.6176
46   TSLA  2021-03-31     0.33              -0.06      6.5000
47   TSLA  2021-06-30     0.64               0.13      3.9231
48   TSLA  2021-09-30     1.03               0.17      5.0588
49   TSLA  2021-12-31     1.63               0.21      6.7619
50   TSLA  2022-03-31     2.45               0.33      6.4242
51   TSLA  2022-06-30     2.76               0.64      3.3125
52   TSLA  2022-09-30     3.23               1.03      2.1359
53   TSLA  2022-12-31     3.62               1.63      1.2209
54   TSLA  2023-03-31     3.40               2.45      0.3878
55   TSLA  2023-06-30     3.53               2.76      0.2790
56   TSLA  2023-09-30     3.11               3.23     -0.0372
57   TSLA  2023-12-31     4.31               3.62      0.1906
58   TSLA  2024-03-31     3.99               3.40      0.1735
59   TSLA  2024-06-30     3.61               3.53      0.0227
60   TSLA  2024-09-30     3.70               3.11      0.1897
61   TSLA  2024-12-31     2.09               4.31     -0.5151
62   TSLA  2025-03-31     1.80               3.99     -0.5489
63   TSLA  2025-06-30     1.73               3.61     -0.5208
```