SELECT
    symbol,
    breakdown,
    breakdown_name,
    period_type,
    report_date,
    series_name,
    value,
    value_type,
    currency
FROM '{url}'
WHERE symbol = '{ticker}'
  AND period_type = '{period_type}'
ORDER BY breakdown, report_date, series_name
