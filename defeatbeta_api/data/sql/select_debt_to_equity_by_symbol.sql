SELECT
    symbol,
    report_date,
    MAX(CASE WHEN item_name = 'total_debt' THEN item_value END) AS total_debt,
    MAX(CASE WHEN item_name = 'stockholders_equity' THEN item_value END) AS stockholders_equity
FROM
    '{url}'
WHERE
    symbol = '{ticker}'
    AND item_name IN ('total_debt', 'stockholders_equity')
    AND period_type = 'quarterly'
    AND report_date != 'TTM'
    AND finance_type = 'balance_sheet'
GROUP BY symbol, report_date
HAVING total_debt IS NOT NULL
ORDER BY report_date
