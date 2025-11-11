WITH metric_data AS (
    SELECT
        symbol,
        CAST(report_date AS DATE) AS report_date,
        item_value as {metric_name}
    FROM '{url}'
    WHERE symbol='{ticker}'
        AND finance_type = '{finance_type}'
        AND item_name='{item_name}'
        AND period_type='{period_type}'
        {ttm_filter}
),
yoy AS (
    SELECT
        e1.symbol,
        e1.report_date,
        e1.{metric_name} AS {metric_name},
        e2.{metric_name} AS prev_year_{metric_name}
    FROM metric_data e1
    LEFT JOIN metric_data e2
      ON e1.symbol = e2.symbol
     AND strftime(e2.report_date, '%m-%d') = strftime(e1.report_date, '%m-%d')
     AND date_diff('year', e2.report_date, e1.report_date) = 1
)
SELECT
    symbol,
    report_date,
    {metric_name},
    prev_year_{metric_name},
    CASE
        WHEN prev_year_{metric_name} IS NOT NULL AND prev_year_{metric_name} != 0
        THEN ROUND(({metric_name} - prev_year_{metric_name}) / ABS(prev_year_{metric_name}), 4)
        ELSE NULL
    END as yoy_growth
FROM yoy
WHERE {metric_name} IS NOT NULL
ORDER BY report_date;