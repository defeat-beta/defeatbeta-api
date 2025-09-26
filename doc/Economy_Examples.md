<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [1. SP500 Historical Annual Returns](#1-sp500-historical-annual-returns)
- [2. SP500 CAGR Returns](#2-sp500-cagr-returns)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## 1. SP500 Historical Annual Returns

```python
from defeatbeta_api.utils.util import load_sp500_historical_annual_returns
load_sp500_historical_annual_returns()
```
```text
>>> load_sp500_historical_annual_returns()
   report_date  annual_returns
0   1928-12-31          0.3788
1   1929-12-31         -0.1191
2   1930-12-31         -0.2848
3   1931-12-31         -0.4707
4   1932-12-31         -0.1515
..         ...             ...
92  2020-12-31          0.1626
93  2021-12-31          0.2689
94  2022-12-31         -0.1944
95  2023-12-31          0.2423
96  2024-12-31          0.2331
```

## 2. SP500 CAGR Returns

```python
from defeatbeta_api.utils.util import sp500_cagr_returns
sp500_cagr_returns(10)
```
```text
   years  cagr_returns
0     10        0.1107
```