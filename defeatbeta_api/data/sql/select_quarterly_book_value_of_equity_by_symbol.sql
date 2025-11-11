SELECT symbol, report_date, item_value as book_value_of_equity
FROM
    '{stockholders_equity_url}'
WHERE
    symbol = '{ticker}'
    AND item_name = 'stockholders_equity'
    AND period_type = 'quarterly'
    AND item_value IS NOT NULL
    AND report_date != 'TTM'