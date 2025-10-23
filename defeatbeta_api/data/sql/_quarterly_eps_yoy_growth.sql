WITH eps_data AS (
    SELECT
        symbol,
        CAST(report_date AS DATE) AS report_date,
        {eps_column}
    FROM '{url}'
    WHERE symbol = '{ticker}'
),
yoy AS (
    SELECT
        e1.symbol,
        e1.report_date,
        e1.{eps_column} AS {current_alias},
        e2.{eps_column} AS {prev_alias}
    FROM eps_data e1
    LEFT JOIN eps_data e2
      ON e1.symbol = e2.symbol
     AND strftime(e2.report_date, '%m-%d') = strftime(e1.report_date, '%m-%d')
     AND date_diff('year', e2.report_date, e1.report_date) = 1
)
SELECT
    symbol,
    report_date,
    {current_alias},
    {prev_alias},
    CASE
        WHEN {prev_alias} IS NOT NULL AND {prev_alias} != 0
            THEN ROUND(({current_alias} - {prev_alias}) / ABS({prev_alias}), 4)
        WHEN {prev_alias} IS NOT NULL AND {prev_alias} = 0 AND {current_alias} > 0
            THEN 1.00
        WHEN {prev_alias} IS NOT NULL AND {prev_alias} = 0 AND {current_alias} < 0
            THEN -1.00
        ELSE NULL
    END AS yoy_growth
FROM yoy
ORDER BY report_date;