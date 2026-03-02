SELECT
    symbol,
    report_date,
    MAX(CASE WHEN item_name = 'total_debt' THEN item_value END) AS total_debt,
    MAX(CASE WHEN item_name = 'minority_interest' THEN item_value END) AS minority_interest,
    MAX(CASE WHEN item_name = 'preferred_stock_equity' THEN item_value END) AS preferred_stock_equity,
    MAX(CASE WHEN item_name = 'cash_and_cash_equivalents' THEN item_value END) AS cash_and_cash_equivalents
FROM
    '{url}'
WHERE
    symbol = '{ticker}'
    AND item_name IN ('total_debt', 'minority_interest', 'preferred_stock_equity', 'cash_and_cash_equivalents')
    AND period_type = 'quarterly'
    AND report_date != 'TTM'
    AND finance_type = 'balance_sheet'
GROUP BY symbol, report_date
HAVING total_debt IS NOT NULL OR cash_and_cash_equivalents IS NOT NULL
ORDER BY report_date
