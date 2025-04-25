
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
![example_0.png](img/example_0.png)

## 1. Stock Statement

```python
# get quarterly income_statement
statement=ticker.quarterly_income_statement()
print(statement.pretty_table())
```
![example_11.png](img/example_11.png)

```python
# pandas.DataFrame
ticker.quarterly_income_statement().df()
```
![example_12.png](img/example_12.png)


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
![example_1.png](img/example_1.png)

## 3. Stock Officers
```python
ticker.officers()
```
![example_2.png](img/example_2.png)

## 4. Stock Calendar
```python
ticker.calendar()
```
![example_3.png](img/example_3.png)

## 5. Stock Earnings
```python
ticker.earnings()
```
![example_4.png](img/example_4.png)

## 6. Stock Splits
```python
ticker.splits()
```
![example_5.png](img/example_5.png)

## 7. Stock Dividends
```python
ticker.dividends()
```
![example_6.png](img/example_6.png)

## 8. Stock Revenue Forecast
```python
ticker.revenue_forecast()
```
![example_7.png](img/example_7.png)

## 9. Stock Earnings Forecast
```python
ticker.earnings_forecast()
```
![example_8.png](img/example_8.png)

## 10. Stock Summary
```python
ticker.summary()
```
![example_13.png](img/example_13.png)

## 11. Stock TTM EPS
```python
ticker.ttm_eps()
```
![example_14.png](img/example_14.png)